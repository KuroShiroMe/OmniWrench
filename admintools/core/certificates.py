"""Zugriff auf den Windows-Zertifikatspeicher (CurrentUser\\My).

Wird für die Zertifikat-Anmeldung am Tresor verwendet und steht Tools für
Einstellungen vom Typ "certificate" zur Verfügung.

Verschlüsselt wird in Python mit dem öffentlichen Schlüssel, entschlüsselt über
PowerShell/.NET mit dem privaten Schlüssel - so funktionieren auch Smartcards,
deren privater Schlüssel den Kartenleser nie verlässt (PIN-Abfrage durch Windows).
"""

from __future__ import annotations

import base64
import json
import warnings
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .i18n import tr
from .powershell import run_ps, run_ps_json


@dataclass
class CertInfo:
    thumbprint: str
    subject: str
    issuer: str
    not_after: str
    friendly_name: str
    has_private_key: bool
    is_rsa: bool
    can_encrypt: bool

    @property
    def display(self) -> str:
        name = self.friendly_name or self.subject
        return tr("cert.display", name=name, date=self.not_after, thumb=self.thumbprint[:8])


_LIST_SCRIPT = r"""
$now = Get-Date
$certs = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.NotAfter -gt $now } | ForEach-Object {
    $ku = $_.Extensions | Where-Object { $_ -is [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension] }
    $canEnc = $true
    if ($ku) {
        $flags = $ku.KeyUsages
        $canEnc = (($flags -band [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment) -ne 0) -or
                  (($flags -band [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DataEncipherment) -ne 0)
    }
    # CNG-Schlüssel können auf "nur signieren" beschränkt sein (z. B. Intune-/Geräte-Zertifikate im TPM)
    if ($canEnc -and $_.HasPrivateKey) {
        try {
            $key = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($_)
            if ($key -is [System.Security.Cryptography.RSACng]) {
                $usage = [int]$key.Key.KeyUsage
                if ($usage -ne 0xFFFFFF -and ($usage -band 1) -eq 0) { $canEnc = $false }
            }
        } catch { }
    }
    [pscustomobject]@{
        thumbprint = $_.Thumbprint
        subject = $_.Subject
        issuer = $_.Issuer
        not_after = $_.NotAfter.ToString('yyyy-MM-dd')
        friendly_name = $_.FriendlyName
        has_private_key = $_.HasPrivateKey
        is_rsa = ($_.PublicKey.Oid.Value -eq '1.2.840.113549.1.1.1')
        can_encrypt = $canEnc
    }
}
ConvertTo-Json -InputObject @($certs) -Compress
"""


def list_certificates(only_usable_for_encryption: bool = False) -> list[CertInfo]:
    data = run_ps_json(_LIST_SCRIPT, timeout=60) or []
    certs = [CertInfo(**c) for c in data]
    if only_usable_for_encryption:
        certs = [c for c in certs if c.has_private_key and c.is_rsa and c.can_encrypt]
    return certs


def _check_thumbprint(thumbprint: str) -> str:
    tp = thumbprint.strip().upper()
    if not tp or not all(ch in "0123456789ABCDEF" for ch in tp):
        raise ValueError(tr("err.cert_bad_thumbprint"))
    return tp


def get_certificate(thumbprint: str) -> x509.Certificate:
    tp = _check_thumbprint(thumbprint)
    res = run_ps(
        f"$c = Get-Item 'Cert:\\CurrentUser\\My\\{tp}'; [Convert]::ToBase64String($c.RawData)", timeout=60
    )
    if not res.ok or not res.stdout:
        raise RuntimeError(tr("err.cert_not_found", thumb=tp, error=res.stderr))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # z. B. negative Seriennummern bei manchen Unternehmens-CAs
        return x509.load_der_x509_certificate(base64.b64decode(res.stdout))


def encrypt_with_certificate(thumbprint: str, data: bytes) -> bytes:
    public_key = get_certificate(thumbprint).public_key()
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError(tr("err.cert_rsa_only"))
    # OAEP mit SHA-1 wird von nahezu allen CSPs/KSPs und Smartcards unterstützt
    return public_key.encrypt(
        data, padding.OAEP(mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None)
    )


_DECRYPT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$in = [Console]::In.ReadToEnd() | ConvertFrom-Json
$cert = Get-Item ('Cert:\CurrentUser\My\' + $in.thumbprint)
$rsa = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($cert)
if ($null -eq $rsa) { throw 'No RSA private key available.' }
$plain = $rsa.Decrypt([Convert]::FromBase64String($in.data), [System.Security.Cryptography.RSAEncryptionPadding]::OaepSHA1)
[Convert]::ToBase64String($plain)
"""


def decrypt_with_certificate(thumbprint: str, data: bytes) -> bytes:
    payload = json.dumps({"thumbprint": _check_thumbprint(thumbprint), "data": base64.b64encode(data).decode()})
    res = run_ps(_DECRYPT_SCRIPT, stdin=payload, timeout=180)
    if not res.ok or not res.stdout:
        raise RuntimeError(res.stderr or tr("err.cert_decrypt"))
    return base64.b64decode(res.stdout.strip())

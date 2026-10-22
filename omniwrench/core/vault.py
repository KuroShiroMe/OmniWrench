"""Verschlüsselter Tresor für Passwörter, Tokens und andere Geheimnisse.

Aufbau (Envelope-Verschlüsselung):
    * Ein zufälliger 256-Bit-Datenschlüssel (DEK) verschlüsselt den Inhalt mit AES-256-GCM.
    * Der DEK wird von einem oder mehreren "Unlockern" verpackt:
        - password:    Argon2id(Masterpasswort) -> KEK -> AES-GCM(DEK)
        - certificate: RSA-OAEP(DEK) mit dem öffentlichen Schlüssel eines Benutzerzertifikats
    * Dadurch kann man sich wahlweise mit Passwort ODER Zertifikat anmelden, und das
      Ändern des Passworts erfordert kein Neuverschlüsseln aller Daten.

Schlüssel im Tresor sind frei wählbar, Konvention: "app:<name>" bzw. "tool:<tool-id>:<key>".

Zurücksetzen bei verlorenem Masterpasswort (reset()):
    * Bei jedem Speichern wird zusätzlich eine Wiederherstellungskopie OHNE Geheimnisse
      abgelegt ("recovery", per DPAPI an das Windows-Konto gebunden): Einträge des
      eingebauten Managers und credential-Felder ohne Passwort, von allen anderen
      Schlüsseln nur der Name.
    * reset() legt daraus einen neuen Tresor mit neuem Passwort an. Einträge bleiben
      erhalten und sind als "missing" markiert, komplett geheime Werte (Tokens, Zugangsdaten
      von Passwortmanagern …) fehlen und stehen in der Liste LOST_KEY, bis sie neu gesetzt werden.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from . import certificates, dpapi
from .i18n import tr
from .jsonio import read_json, write_json

VAULT_FORMAT = 1
ARGON2_PARAMS = {"iterations": 3, "lanes": 4, "memory_cost": 64 * 1024}  # 64 MiB
CREDENTIALS_KEY = "app:credentials"       # eingebauter Passwortmanager (siehe credentials.LocalProvider)
LOST_KEY = "app:lost_secrets"             # nach reset() fehlende Geheimnisse (Liste von Schlüsseln)

log = logging.getLogger(__name__)


class VaultError(Exception):
    pass


class WrongCredentials(VaultError):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text)


def _derive_key(password: str, salt: bytes, params: dict) -> bytes:
    kdf = Argon2id(
        salt=salt,
        length=32,
        iterations=params["iterations"],
        lanes=params["lanes"],
        memory_cost=params["memory_cost"],
    )
    return kdf.derive(password.encode("utf-8"))


def _seal(key: bytes, plaintext: bytes, aad: bytes) -> str:
    nonce = os.urandom(12)
    return _b64(nonce + AESGCM(key).encrypt(nonce, plaintext, aad))


def _open(key: bytes, blob: str, aad: bytes) -> bytes:
    raw = _unb64(blob)
    return AESGCM(key).decrypt(raw[:12], raw[12:], aad)


def _strip_password(entry: dict) -> dict:
    """Kopie ohne Passwort; "missing" merkt sich, dass vorher eines gesetzt war."""
    out = {k: v for k, v in entry.items() if k != "password"}
    if entry.get("password") or entry.get("missing"):
        out["missing"] = True
    return out


def redact(key: str, value: Any) -> Any:
    """Nicht geheimer Teil eines Tresorwerts für die Wiederherstellung - None = komplett geheim."""
    if key == LOST_KEY:
        return value
    if key == CREDENTIALS_KEY and isinstance(value, dict):
        return {cid: _strip_password(e) for cid, e in value.items() if isinstance(e, dict)}
    if isinstance(value, dict) and isinstance(value.get("items"), list):   # credential-Feld
        return {**value, "items": [_strip_password(i) if isinstance(i, dict) and "ref" not in i else i
                                   for i in value["items"]]}
    return None


class Vault:
    def __init__(self, path: Path):
        self.path = path
        self._dek: bytes | None = None
        self._data: dict[str, Any] = {}
        self._file: dict = read_json(path, default=None) or {}

    # ------------------------------------------------------------------ Status
    @property
    def exists(self) -> bool:
        return bool(self._file.get("unlockers"))

    @property
    def is_unlocked(self) -> bool:
        return self._dek is not None

    def unlockers(self) -> list[dict]:
        """Liste der Anmeldemethoden (ohne geheime Daten)."""
        return [
            {k: v for k, v in u.items() if k not in ("wrapped_key", "salt")}
            for u in self._file.get("unlockers", [])
        ]

    def has_unlocker(self, kind: str) -> bool:
        return any(u["type"] == kind for u in self._file.get("unlockers", []))

    @property
    def has_recovery(self) -> bool:
        """True, wenn eine Wiederherstellungskopie (ohne Geheimnisse) vorliegt."""
        return bool(self._file.get("recovery"))

    # ------------------------------------------------------------- Einrichtung
    def create(self, password: str | None = None, cert_thumbprint: str | None = None) -> None:
        if not password and not cert_thumbprint:
            raise VaultError(tr("err.vault_need_method"))
        self._dek = AESGCM.generate_key(bit_length=256)
        self._data = {}
        self._file = {"format": VAULT_FORMAT, "created": int(time.time()), "unlockers": []}
        if password:
            self._add_password_unlocker(password)
        if cert_thumbprint:
            self._add_cert_unlocker(cert_thumbprint)
        self._save()

    def _add_password_unlocker(self, password: str) -> None:
        salt = os.urandom(16)
        kek = _derive_key(password, salt, ARGON2_PARAMS)
        self._file["unlockers"] = [u for u in self._file["unlockers"] if u["type"] != "password"]
        self._file["unlockers"].append({
            "type": "password",
            "kdf": {"name": "argon2id", **ARGON2_PARAMS},
            "salt": _b64(salt),
            "wrapped_key": _seal(kek, self._dek, b"dek"),
        })

    def _add_cert_unlocker(self, thumbprint: str) -> None:
        thumbprint = thumbprint.upper()
        cert = certificates.get_certificate(thumbprint)
        wrapped = certificates.encrypt_with_certificate(thumbprint, self._dek)
        # Probe: sicherstellen, dass das Entschlüsseln mit dem privaten Schlüssel klappt
        if certificates.decrypt_with_certificate(thumbprint, wrapped) != self._dek:
            raise VaultError(tr("err.vault_cert_test"))
        self._file["unlockers"] = [
            u for u in self._file["unlockers"]
            if not (u["type"] == "certificate" and u["thumbprint"] == thumbprint)
        ]
        self._file["unlockers"].append({
            "type": "certificate",
            "thumbprint": thumbprint,
            "subject": cert.subject.rfc4514_string(),
            "not_after": cert.not_valid_after_utc.strftime("%Y-%m-%d"),
            "wrapped_key": _b64(wrapped),
        })

    # --------------------------------------------------------------- Anmelden
    def unlock_with_password(self, password: str) -> None:
        for u in self._file.get("unlockers", []):
            if u["type"] != "password":
                continue
            kek = _derive_key(password, _unb64(u["salt"]), u["kdf"])
            try:
                dek = _open(kek, u["wrapped_key"], b"dek")
            except InvalidTag:
                raise WrongCredentials(tr("err.vault_wrong_password")) from None
            self._finish_unlock(dek)
            return
        raise VaultError(tr("err.vault_no_password"))

    def unlock_with_certificate(self, thumbprint: str | None = None) -> None:
        candidates = [
            u for u in self._file.get("unlockers", [])
            if u["type"] == "certificate" and (thumbprint is None or u["thumbprint"] == thumbprint.upper())
        ]
        if not candidates:
            raise VaultError(tr("err.vault_no_cert"))
        errors = []
        for u in candidates:
            try:
                dek = certificates.decrypt_with_certificate(u["thumbprint"], _unb64(u["wrapped_key"]))
                self._finish_unlock(dek)
                return
            except Exception as exc:  # noqa: BLE001 - nächstes Zertifikat probieren
                errors.append(f"{u['subject']}: {exc}")
        raise WrongCredentials(tr("err.vault_cert_failed") + "\n" + "\n".join(errors))

    def _finish_unlock(self, dek: bytes) -> None:
        payload = self._file.get("data")
        try:
            self._data = json.loads(_open(dek, payload, b"data")) if payload else {}
        except InvalidTag:
            raise WrongCredentials(tr("err.vault_decrypt")) from None
        self._dek = dek
        if not self.has_recovery:   # Tresore von vor der Zurücksetzen-Funktion nachrüsten
            self._save()

    def lock(self) -> None:
        self._dek = None
        self._data = {}

    # ------------------------------------------------------------ Verwaltung
    def _require_unlocked(self) -> None:
        if not self.is_unlocked:
            raise VaultError(tr("err.vault_locked"))

    def change_password(self, new_password: str) -> None:
        self._require_unlocked()
        self._add_password_unlocker(new_password)
        self._save()

    def add_certificate(self, thumbprint: str) -> None:
        self._require_unlocked()
        self._add_cert_unlocker(thumbprint)
        self._save()

    def remove_unlocker(self, kind: str, thumbprint: str | None = None) -> None:
        self._require_unlocked()
        remaining = [
            u for u in self._file["unlockers"]
            if not (u["type"] == kind and (thumbprint is None or u.get("thumbprint") == thumbprint))
        ]
        if not remaining:
            raise VaultError(tr("err.vault_last_method"))
        self._file["unlockers"] = remaining
        self._save()

    # ------------------------------------------------------------ Zurücksetzen
    def reset(self, new_password: str) -> int:
        """Neuer Tresor mit neuem Passwort - für ein verlorenes Masterpasswort.

        Alle Geheimnisse gehen verloren, Einträge bleiben (ohne Passwort) erhalten, sofern eine
        Wiederherstellungskopie lesbar ist. Die alte Datei wird daneben gesichert. Liefert die
        Zahl der übernommenen Einträge bzw. Werte.
        """
        if not new_password:
            raise VaultError(tr("err.vault_need_method"))
        skeleton: dict[str, Any] = {}
        if self.has_recovery:
            try:
                skeleton = json.loads(dpapi.unprotect(self._file["recovery"]))
            except Exception:  # noqa: BLE001 - anderes Windows-Konto, beschädigt …
                log.exception("Wiederherstellungskopie des Tresors nicht lesbar")
        if self.path.exists():
            backup = self.path.with_name(f"{self.path.stem}.before-reset-{time.strftime('%Y%m%d-%H%M%S')}.json")
            shutil.copy2(self.path, backup)
        data: dict[str, Any] = {}
        lost = set(skeleton.get(LOST_KEY) or [])
        for key, value in skeleton.items():
            if key == LOST_KEY:
                continue
            if value is None:
                lost.add(key)
            else:
                data[key] = value
        if lost:
            data[LOST_KEY] = sorted(lost)
        self._dek = AESGCM.generate_key(bit_length=256)
        self._data = data
        self._file = {"format": VAULT_FORMAT, "created": int(time.time()), "reset": int(time.time()),
                      "unlockers": []}
        self._add_password_unlocker(new_password)
        self._save()
        restored = len(data.get(CREDENTIALS_KEY, {})) + len([k for k in data if k not in (CREDENTIALS_KEY, LOST_KEY)])
        log.warning("Tresor zurückgesetzt: %d Einträge übernommen, %d Geheimnisse verworfen", restored, len(lost))
        return restored

    def is_lost(self, key: str) -> bool:
        """True, wenn das Geheimnis beim Zurücksetzen verloren ging und noch nicht neu gesetzt wurde."""
        return self.is_unlocked and key in (self._data.get(LOST_KEY) or [])

    def lost_keys(self, prefix: str = "") -> list[str]:
        return [k for k in (self._data.get(LOST_KEY) or []) if k.startswith(prefix)] if self.is_unlocked else []

    # --------------------------------------------------------------- Daten
    def get(self, key: str, default: Any = None) -> Any:
        self._require_unlocked()
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._require_unlocked()
        if value is None:
            self._data.pop(key, None)
        else:
            self._data[key] = value
            self._drop_lost(lambda k: k == key)
        self._save()

    def _drop_lost(self, match) -> None:
        """Entfernt Markierungen verlorener Geheimnisse (neu gesetzt bzw. gelöscht)."""
        lost = [k for k in self._data.get(LOST_KEY) or [] if not match(k)]
        if lost:
            self._data[LOST_KEY] = lost
        else:
            self._data.pop(LOST_KEY, None)

    def delete(self, key: str) -> None:
        self.set(key, None)

    def delete_prefix(self, prefix: str) -> None:
        self._require_unlocked()
        for k in [k for k in self._data if k.startswith(prefix)]:
            del self._data[k]
        self._drop_lost(lambda k: k.startswith(prefix))
        self._save()

    def keys(self, prefix: str = "") -> list[str]:
        self._require_unlocked()
        return [k for k in self._data if k.startswith(prefix)]

    def _save(self) -> None:
        self._file["data"] = _seal(self._dek, json.dumps(self._data).encode("utf-8"), b"data")
        try:
            skeleton = {k: redact(k, v) for k, v in self._data.items()}
            self._file["recovery"] = dpapi.protect(json.dumps(skeleton).encode("utf-8"))
        except Exception:  # noqa: BLE001 - Speichern der eigentlichen Daten nie verhindern
            log.exception("Wiederherstellungskopie des Tresors nicht geschrieben")
        write_json(self.path, self._file)

"""Signiert OmniWrench.exe (Authenticode) mit einem Code-Signing-Zertifikat:

    .\\.venv\\Scripts\\python scripts\\sign_exe.py                     # dist\\OmniWrench\\OmniWrench.exe
    .\\.venv\\Scripts\\python scripts\\sign_exe.py --if-configured     # ohne Zertifikat: Hinweis, kein Fehler
    .\\.venv\\Scripts\\python scripts\\sign_exe.py datei.exe …         # andere Dateien

Das Zertifikat kommt aus Umgebungsvariablen (nie aus dem Repository):

    SIGN_CERT_SHA1      Fingerabdruck eines Zertifikats im Windows-Zertifikatspeicher (Benutzer › Eigene
                        Zertifikate), auch auf Smartcard/USB-Token oder SimplySign. Für lokales Signieren.
    SIGN_PFX_BASE64     PFX-Datei als Base64 (GitHub-Secret) …
    SIGN_PFX_PATH       … oder Pfad zu einer PFX-Datei
    SIGN_PFX_PASSWORD   Kennwort der PFX-Datei
    SIGN_TIMESTAMP_URL  Zeitstempeldienst (Standard: DigiCert; Certum: http://time.certum.pl);
                        "none" nur für Tests: ohne Zeitstempel wird die Signatur mit dem Zertifikat ungültig
    SIGNTOOL            Pfad zu signtool.exe, falls es nicht automatisch gefunden wird

Unter Windows wird signtool.exe (Windows SDK) genutzt, sonst osslsigncode (nur PFX).
Azure Artifact Signing und SignPath laufen nicht über dieses Skript, sondern über ihre
GitHub-Actions im Workflow EXE-Build (siehe docs/EXE_SIGNIEREN.md).
"""

from __future__ import annotations

import argparse
import base64
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omniwrench import APP_NAME  # noqa: E402

DEFAULT_EXE = ROOT / "dist" / APP_NAME / f"{APP_NAME}.exe"
DEFAULT_TIMESTAMP = "http://timestamp.digicert.com"
PROJECT_URL = "https://github.com/KuroShiroMe/OmniWrench"


class SignError(RuntimeError):
    pass


def configured() -> bool:
    """True, wenn ein Zertifikat über Umgebungsvariablen angegeben ist."""
    return bool(os.environ.get("SIGN_CERT_SHA1") or os.environ.get("SIGN_PFX_BASE64")
                or os.environ.get("SIGN_PFX_PATH"))


def find_signtool() -> str | None:
    if os.environ.get("SIGNTOOL"):
        return os.environ["SIGNTOOL"]
    if found := shutil.which("signtool"):
        return found
    # Windows SDK: neueste Version, x64 bevorzugt
    base = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Windows Kits", "10", "bin")
    for arch in ("x64", "x86", "arm64"):
        hits = sorted(glob.glob(os.path.join(base, "*", arch, "signtool.exe")))
        if hits:
            return hits[-1]
    return None


def _run(cmd: list[str], secret: str | None = None, attempts: int = 3) -> None:
    """Startet cmd; wiederholt bei Fehlern (Zeitstempeldienste sind gelegentlich nicht erreichbar)."""
    shown = " ".join("***" if secret and part == secret else part for part in cmd)
    for attempt in range(1, attempts + 1):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        out = (proc.stdout + proc.stderr).strip()
        if secret:
            out = out.replace(secret, "***")
        if proc.returncode == 0:
            if out:
                print(out)
            return
        print(f"Versuch {attempt}/{attempts} fehlgeschlagen: {shown}\n{out}", file=sys.stderr)
        if attempt < attempts:
            time.sleep(5 * attempt)
    raise SignError(f"Signieren fehlgeschlagen ({shown})")


def sign_files(files: list[Path]) -> None:
    """Signiert files mit dem Zertifikat aus den Umgebungsvariablen (SHA-256 + RFC-3161-Zeitstempel)."""
    if not configured():
        raise SignError("Kein Zertifikat angegeben (SIGN_CERT_SHA1, SIGN_PFX_BASE64 oder SIGN_PFX_PATH).")
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        raise SignError("Datei nicht gefunden: " + ", ".join(missing))

    timestamp = os.environ.get("SIGN_TIMESTAMP_URL") or DEFAULT_TIMESTAMP
    if timestamp.lower() == "none":
        timestamp = ""
    password = os.environ.get("SIGN_PFX_PASSWORD", "")
    with tempfile.TemporaryDirectory(prefix="omniwrench-sign-") as tmp:
        pfx = os.environ.get("SIGN_PFX_PATH")
        if os.environ.get("SIGN_PFX_BASE64"):
            pfx = os.path.join(tmp, "cert.pfx")
            Path(pfx).write_bytes(base64.b64decode("".join(os.environ["SIGN_PFX_BASE64"].split())))

        signtool = find_signtool() if sys.platform == "win32" else None
        if signtool:
            for file in files:
                cmd = [signtool, "sign", "/fd", "SHA256", "/d", APP_NAME, "/du", PROJECT_URL]
                if timestamp:
                    cmd += ["/tr", timestamp, "/td", "SHA256"]
                if os.environ.get("SIGN_CERT_SHA1"):
                    cmd += ["/sha1", os.environ["SIGN_CERT_SHA1"].replace(" ", "")]
                else:
                    cmd += ["/f", pfx] + (["/p", password] if password else [])
                _run(cmd + [str(file)], secret=password or None)
            return

        osslsigncode = shutil.which("osslsigncode")
        if not osslsigncode or not pfx:
            raise SignError("signtool.exe (Windows SDK) nicht gefunden"
                            + ("" if sys.platform == "win32" else "; außerhalb von Windows nur PFX mit osslsigncode"))
        for file in files:
            out = file.with_name(file.name + ".signed")
            cmd = [osslsigncode, "sign", "-pkcs12", pfx] + (["-pass", password] if password else [])
            cmd += ["-h", "sha256", "-n", APP_NAME, "-i", PROJECT_URL] + (["-ts", timestamp] if timestamp else [])
            cmd += ["-in", str(file), "-out", str(out)]
            out.unlink(missing_ok=True)
            _run(cmd, secret=password or None)
            out.replace(file)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path, help=f"zu signierende Dateien (Standard: {DEFAULT_EXE})")
    parser.add_argument("--if-configured", action="store_true",
                        help="ohne Zertifikat nur einen Hinweis ausgeben statt abzubrechen")
    opts = parser.parse_args()
    if not configured() and opts.if_configured:
        print("Kein Zertifikat angegeben, EXE bleibt unsigniert.")
        return
    files = opts.files or [DEFAULT_EXE]
    try:
        sign_files(files)
    except SignError as exc:
        sys.exit(str(exc))
    for file in files:
        print(f"Signiert: {file}")


if __name__ == "__main__":
    main()

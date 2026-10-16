"""Ausführen von PowerShell-Skripten (normal und mit Administratorrechten)."""

from __future__ import annotations

import base64
import html
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .i18n import tr

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass
class PSResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _powershell_exe(shell: str = "powershell") -> str:
    """shell: "powershell" (Windows PowerShell 5.1) oder "pwsh" (PowerShell 7)."""
    if shell == "pwsh" or os.name != "nt":
        return "pwsh.exe" if os.name == "nt" else "pwsh"
    return "powershell.exe"


def run_ps(script: str, stdin: str | None = None, timeout: float | None = 300, shell: str = "powershell") -> PSResult:
    """Führt ein PowerShell-Skript aus. Ausgabe wird als UTF-8 erzwungen."""
    prologue = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
        "$OutputEncoding=[System.Text.Encoding]::UTF8;"
        "$ProgressPreference='SilentlyContinue';"
    )
    encoded = base64.b64encode((prologue + script).encode("utf-16-le")).decode("ascii")
    proc = subprocess.run(
        [_powershell_exe(shell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", encoded],
        input=stdin.encode("utf-8") if stdin is not None else None,
        capture_output=True,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    return PSResult(
        proc.returncode,
        proc.stdout.decode("utf-8", errors="replace").strip(),
        _clean_stderr(proc.stderr.decode("utf-8", errors="replace")),
    )


def _clean_stderr(text: str) -> str:
    """Wandelt CLIXML-Fehlerausgaben (bei -EncodedCommand) in lesbaren Text um."""
    text = text.strip()
    if not text.startswith("#< CLIXML"):
        return text
    parts = re.findall(r'<S S="Error">(.*?)</S>', text, flags=re.S)
    joined = "".join(html.unescape(p) for p in parts)
    joined = re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), joined)
    lines = [ln.rstrip() for ln in joined.splitlines()]
    # Nur die eigentliche Meldung, ohne "In Zeile:..."/"+ ..."-Positionsangaben
    message = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith(("+", "In Zeile", "At line"))]
    return "\n".join(message).strip() or text


def run_ps_json(script: str, stdin: str | None = None, timeout: float | None = 300):
    """Führt ein Skript aus, das JSON auf stdout schreibt, und gibt das geparste Ergebnis zurück."""
    res = run_ps(script, stdin=stdin, timeout=timeout)
    if not res.ok:
        raise RuntimeError(res.stderr or res.stdout or f"PowerShell error {res.returncode}")
    return json.loads(res.stdout) if res.stdout else None


def run_ps_elevated(script: str, timeout: float | None = 3600) -> PSResult:
    """Führt ein Skript mit Administratorrechten aus (UAC-Abfrage).

    Das Skript wird in eine Temp-Datei geschrieben, die Ausgabe in eine Logdatei
    umgeleitet und nach Abschluss zurückgelesen.
    """
    workdir = Path(tempfile.mkdtemp(prefix="omniwrench_elev_"))
    script_file = workdir / "run.ps1"
    log_file = workdir / "run.log"
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\")
    # Kein Start-Transcript: Die Datei bliebe ggf. gesperrt bzw. gehört dem erhöhten Prozess.
    # Stattdessen Ausgabe sammeln, am Ende in einem Rutsch schreiben und dem
    # aufrufenden (nicht erhöhten) Benutzer explizit Leserechte geben.
    wrapped = (
        "$ErrorActionPreference='Stop'\n"
        "$ProgressPreference='SilentlyContinue'\n"
        "$code = 0\n"
        "$out = try { & {\n" + script + "\n} *>&1 | Out-String -Width 300 }"
        " catch { \"ERROR: \" + $_; $code = 1 }\n"
        f"[IO.File]::WriteAllText({ps_quote(str(log_file))}, [string]$out, [Text.Encoding]::UTF8)\n"
        f"icacls {ps_quote(str(log_file))} /grant {ps_quote(user + ':R')} | Out-Null\n"
        "exit $code\n"
    )
    script_file.write_text(wrapped, encoding="utf-8-sig")
    launcher = (
        f"$p = Start-Process -FilePath powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
        f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"{script_file}\"';"
        "exit $p.ExitCode"
    )
    try:
        res = run_ps(launcher, timeout=timeout)
    except subprocess.TimeoutExpired:
        return PSResult(1, "", tr("err.elevated_timeout"))
    log = _read_log(log_file)
    if not res.ok and not log:
        return PSResult(res.returncode, "", res.stderr or tr("err.elevated_cancelled"))
    return PSResult(res.returncode, log, res.stderr)


def _read_log(path: Path) -> str:
    """Liest die Logdatei der Admin-Sitzung; wartet kurz, falls Virenscanner o. Ä. sie noch sperren."""
    for _ in range(20):
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8-sig", errors="replace").strip()
        except PermissionError:
            time.sleep(0.25)
    return ""


def ps_quote(value: str) -> str:
    """Quotiert einen String als PowerShell-Literal in einfachen Anführungszeichen."""
    return "'" + str(value).replace("'", "''") + "'"

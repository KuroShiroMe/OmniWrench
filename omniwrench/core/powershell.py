"""Ausführen von PowerShell-Skripten (normal und mit Administratorrechten)."""

from __future__ import annotations

import base64
import html
import json
import os
import re
import subprocess
import tempfile
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


def _powershell_exe() -> str:
    return "powershell.exe" if os.name == "nt" else "pwsh"


def run_ps(script: str, stdin: str | None = None, timeout: float | None = 300) -> PSResult:
    """Führt ein PowerShell-Skript aus. Ausgabe wird als UTF-8 erzwungen."""
    prologue = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
        "$OutputEncoding=[System.Text.Encoding]::UTF8;"
        "$ProgressPreference='SilentlyContinue';"
    )
    encoded = base64.b64encode((prologue + script).encode("utf-16-le")).decode("ascii")
    proc = subprocess.run(
        [_powershell_exe(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
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
    wrapped = (
        "$ErrorActionPreference='Stop'\n"
        "$ProgressPreference='SilentlyContinue'\n"
        f"Start-Transcript -Path '{log_file}' -Force | Out-Null\n"
        "$code = 0\n"
        "try {\n" + script + "\n} catch { Write-Output (\"ERROR: \" + $_); $code = 1 }\n"
        "Stop-Transcript | Out-Null\n"
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
    log = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
    if not res.ok and not log:
        return PSResult(res.returncode, "", res.stderr or tr("err.elevated_cancelled"))
    return PSResult(res.returncode, log, res.stderr)


def ps_quote(value: str) -> str:
    """Quotiert einen String als PowerShell-Literal in einfachen Anführungszeichen."""
    return "'" + str(value).replace("'", "''") + "'"

"""Ausführen von PowerShell-Skripten (normal und mit Administratorrechten)."""

from __future__ import annotations

import base64
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import elevation
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


# Zeilenpräfixe im Log der Admin-Sitzung
ERROR_PREFIX = "##ERROR "
MARKER_PREFIX = "##OW "
# Längere Skripte über -File statt -EncodedCommand (Windows-Befehlszeile max. 32767 Zeichen)
_MAX_ENCODED = 30000

_ELEVATED_WRAPPER = """$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$owLog = {log}
$owEnc = New-Object System.Text.UTF8Encoding($false)
function Write-OwLog([string]$text) {{
  foreach ($i in 1..40) {{
    try {{ [IO.File]::AppendAllText($owLog, $text + "`n", $owEnc); return }} catch {{ Start-Sleep -Milliseconds 50 }}
  }}
}}
function Write-OwError([string]$text) {{
  foreach ($l in ($text -split "`r?`n")) {{ if ($l.Trim()) {{ Write-OwLog ('{err}' + $l.TrimEnd()) }} }}
}}
$owCode = 0
try {{
  $owBlock = [ScriptBlock]::Create($owEnc.GetString([Convert]::FromBase64String('{payload}')))
  & $owBlock *>&1 | ForEach-Object {{
    if ($_ -is [System.Management.Automation.ErrorRecord]) {{ Write-OwError ([string]$_) }}
    else {{
      foreach ($l in (($_ | Out-String -Width 300) -split "`r?`n")) {{ if ($l.Trim()) {{ Write-OwLog $l.TrimEnd() }} }}
    }}
  }}
}} catch {{
  Write-OwError $_.Exception.Message
  $owCode = 1
}}
exit $owCode
"""


def elevated_wrapper(script: str, log_file: Path) -> str:
    """PowerShell-Rahmen für die Admin-Sitzung.

    Jede Ausgabezeile wird sofort an die Logdatei angehängt (Fortschritt live sichtbar),
    Fehler mit ERROR_PREFIX. Das eigentliche Skript wird Base64-kodiert eingebettet, damit
    auch Syntaxfehler darin im Log landen statt im unsichtbaren Fenster der Admin-Sitzung.
    """
    payload = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return _ELEVATED_WRAPPER.format(log=ps_quote(str(log_file)), payload=payload, err=ERROR_PREFIX)


class _LogTail:
    """Liest neu angehängte Zeilen der Logdatei (die Datei gehört dem aufrufenden Benutzer)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._offset = 0
        self._rest = b""

    def read(self, final: bool = False) -> list[str]:
        data = b""
        for _ in range(20 if final else 1):
            try:
                with open(self.path, "rb") as fh:
                    fh.seek(self._offset)
                    data = fh.read()
                break
            except FileNotFoundError:
                return []
            except PermissionError:  # Virenscanner o. Ä. sperrt die Datei kurz
                if final:
                    time.sleep(0.25)
        self._offset += len(data)
        chunks = (self._rest + data).split(b"\n")
        self._rest = b"" if final else chunks.pop()
        return [c.decode("utf-8", errors="replace").rstrip("\r") for c in chunks if c.strip()]


def run_ps_elevated(script: str, timeout: float | None = 3600,
                    on_output: Callable[[str], None] | None = None) -> PSResult:
    """Führt ein Skript mit Administratorrechten aus (UAC-Abfrage).

    Läuft das Programm bereits mit Adminrechten, entfällt die Abfrage. on_output erhält jede
    Ausgabezeile, sobald sie entsteht. Fehlerzeilen stehen im Ergebnis in stderr.
    returncode elevation.ERROR_CANCELLED = UAC-Abfrage abgelehnt.
    """
    workdir = Path(tempfile.mkdtemp(prefix="omniwrench_elev_"))
    script_file = workdir / "run.ps1"
    log_file = workdir / "run.log"
    # Logdatei vorab als aufrufender Benutzer anlegen: Sie bleibt so lesbar, auch wenn die
    # Admin-Sitzung unter einem anderen Konto läuft (UAC mit Admin-Anmeldedaten).
    log_file.write_bytes(b"")
    wrapper = elevated_wrapper(script, log_file)
    args = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"]
    encoded = base64.b64encode(wrapper.encode("utf-16-le")).decode("ascii")
    if len(encoded) < _MAX_ENCODED:
        # -EncodedCommand unterliegt keiner Ausführungsrichtlinie (auch nicht AllSigned per GPO)
        args += ["-EncodedCommand", encoded]
    else:
        script_file.write_text(wrapper, encoding="utf-8-sig")
        args += ["-File", str(script_file)]
    try:
        if elevation.needs_uac():
            # Vollständiger Pfad: kein Suchpfad-Lookup für einen Prozess mit Adminrechten
            exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            proc = elevation.start_elevated(str(exe), subprocess.list2cmdline(args))
        else:
            proc = subprocess.Popen([_powershell_exe(), *args], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=CREATE_NO_WINDOW)
    except elevation.ElevationCancelled:
        shutil.rmtree(workdir, ignore_errors=True)
        return PSResult(elevation.ERROR_CANCELLED, "", tr("err.elevated_cancelled"))
    except OSError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        return PSResult(1, "", tr("err.elevated_start", error=exc))

    tail = _LogTail(log_file)
    out: list[str] = []
    errors: list[str] = []

    def collect(lines: list[str]) -> None:
        for line in lines:
            if line.startswith(ERROR_PREFIX):
                errors.append(line[len(ERROR_PREFIX):])
                continue
            out.append(line)
            if on_output:
                on_output(line)

    deadline = time.monotonic() + timeout if timeout else None
    while (code := proc.poll()) is None:
        collect(tail.read())
        if deadline and time.monotonic() > deadline:
            # Die Admin-Sitzung läuft weiter (ein nicht erhöhter Prozess kann sie nicht beenden)
            return PSResult(1, "\n".join(out), tr("err.elevated_timeout"))
        time.sleep(0.2)
    collect(tail.read(final=True))
    shutil.rmtree(workdir, ignore_errors=True)
    if code != 0 and not errors:
        errors.append(tr("err.elevated_failed", code=code))
    return PSResult(code, "\n".join(out), "\n".join(errors))


def ps_quote(value: str) -> str:
    """Quotiert einen String als PowerShell-Literal in einfachen Anführungszeichen."""
    return "'" + str(value).replace("'", "''") + "'"

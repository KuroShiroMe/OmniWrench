"""Dauerhafter PowerShell-Prozess (Windows PowerShell 5.1) für alle DHCP-Zugriffe.

Ein Prozess hält die CIM-Sitzungen und die kompilierte RPC-Hilfsklasse, damit nicht jeder Zugriff
PowerShell neu startet. Protokoll: eine JSON-Zeile je Nachricht über stdin/stdout (siehe host.ps1).
Aufrufe sind über eine Sperre serialisiert und dürfen aus beliebigen Threads kommen.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
RESULT, PROGRESS = "@@OWR ", "@@OWP "

# Startskript: liest das eigentliche Host-Skript (Base64, UTF-8) als erste Zeile von stdin.
# So gibt es weder eine Skriptdatei (Ausführungsrichtlinie) noch eine Längenbegrenzung der Befehlszeile.
_BOOTSTRAP = (
    "$ErrorActionPreference='Stop';"
    "$u=New-Object System.Text.UTF8Encoding $false;"
    "$OwIn=New-Object System.IO.StreamReader([Console]::OpenStandardInput(),$u);"
    "$OwOut=New-Object System.IO.StreamWriter([Console]::OpenStandardOutput(),$u);"
    "$OwOut.AutoFlush=$true;"
    "$c=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($OwIn.ReadLine()));"
    ". ([ScriptBlock]::Create($c))"
)


class HostError(Exception):
    """Fehlermeldung aus dem PowerShell-Host (Text unverändert, ggf. mit @RPC:/@ERR:-Kennung)."""


class HostDied(HostError):
    pass


def _powershell() -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    exe = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(exe) if exe.exists() else "powershell.exe"


class PsHost:
    def __init__(self, script_path: Path):
        self.script_path = script_path
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._next_id = 0
        self._stderr: list[str] = []

    # ----------------------------------------------------------------------------------------------
    def _start(self) -> None:
        enc = base64.b64encode(_BOOTSTRAP.encode("utf-16-le")).decode("ascii")
        self._proc = subprocess.Popen(
            [_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
        self._stderr = []
        threading.Thread(target=self._drain_stderr, args=(self._proc,), daemon=True).start()
        code = base64.b64encode(self.script_path.read_text(encoding="utf-8").encode("utf-8")).decode("ascii")
        self._write(code)
        ready = self._read_message(None)
        if not ready.get("ok"):
            raise HostDied(ready.get("error") or "start")

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        for raw in iter(proc.stderr.readline, b""):
            text = raw.decode("utf-8", errors="replace").rstrip()
            if text:
                self._stderr.append(text)
                del self._stderr[:-40]
                log.debug("ScopeKeeper-Host stderr: %s", text)

    def _write(self, line: str) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((line + "\n").encode("utf-8"))
        self._proc.stdin.flush()

    def _read_message(self, on_progress: Callable[[dict], None] | None) -> dict:
        proc = self._proc
        if not (proc and proc.stdout):
            raise HostDied("PowerShell")
        while True:
            raw = proc.stdout.readline()
            if not raw:
                tail = " | ".join(self._stderr[-5:])
                if self._proc is proc:
                    self._proc = None
                raise HostDied(tail or "PowerShell")
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if text.startswith(PROGRESS):
                if on_progress:
                    try:
                        on_progress(json.loads(text[len(PROGRESS):]))
                    except Exception:  # noqa: BLE001 - Fortschritt darf den Aufruf nicht abbrechen
                        log.exception("Fortschrittsmeldung")
                continue
            if text.startswith(RESULT):
                return json.loads(text[len(RESULT):])
            if text.strip():
                log.debug("ScopeKeeper-Host: %s", text)

    # ----------------------------------------------------------------------------------------------
    def call(self, cmd: str, args: dict | None = None, on_progress: Callable[[dict], None] | None = None):
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()
            self._next_id += 1
            rid = self._next_id
            self._write(json.dumps({"id": rid, "cmd": cmd, "args": args or {}}, ensure_ascii=False))
            while True:
                msg = self._read_message(on_progress)
                if msg.get("id") == rid:
                    break
            if not msg.get("ok"):
                raise HostError(msg.get("error") or "?")
            return msg.get("data")

    def kill(self) -> None:
        """Sofort beenden (Abbruch einer laufenden Abfrage); ein wartender call() endet mit HostDied."""
        proc = self._proc
        self._proc = None
        if proc:
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if not proc:
            return
        try:
            proc.stdin.write(b'{"id":0,"cmd":"exit"}\n')
            proc.stdin.flush()
            proc.wait(timeout=3)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass

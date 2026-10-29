"""Ollama einrichten: installieren (Windows: winget bzw. offizielles Setup, Linux: Befehl zum Kopieren), starten
und Modelle laden – mit Fortschritt, ohne PowerShell. Qt-frei.

Ollama läuft danach als eigener Dienst (http://localhost:11434); OmniWrench spricht es wie jede Verbindung über die
OpenAI-kompatible Schnittstelle an. Modelle lädt /api/pull (JSON-Zeilen mit status/total/completed).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

DEFAULT_URL = "http://localhost:11434"
SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"
LINUX_COMMAND = "curl -fsSL https://ollama.com/install.sh | sh"
WINGET_ID = "Ollama.Ollama"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
# (Modell, ca. GB, Text-Schlüssel ai.ollama.rec.*) – Auswahl für den Einstieg; jedes andere Modell lässt sich eintippen
RECOMMENDED = (
    ("llama3.2:3b", 2.0, "small"),
    ("qwen3:8b", 5.2, "allround"),
    ("gemma3:12b", 8.1, "vision"),
    ("gpt-oss:20b", 14.0, "strong"),
    ("mistral-small3.2", 15.0, "strong_eu"),
)


def root_url(base_url: str = "") -> str:
    """http://host:11434/v1 -> http://host:11434"""
    url = (base_url or DEFAULT_URL).rstrip("/")
    return url[:-3] if url.endswith("/v1") else url


def is_local(base_url: str = "") -> bool:
    host = urllib.parse.urlparse(root_url(base_url)).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")


def executable() -> str:
    """Pfad zu ollama(.exe) oder ""."""
    found = shutil.which("ollama")
    if found:
        return found
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if local.is_file():
            return str(local)
    return ""


def _get(url: str, timeout: float = 3):
    with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def version(base_url: str = "") -> str:
    """Version des laufenden Dienstes oder "" (läuft nicht / nicht erreichbar)."""
    try:
        return str(_get(root_url(base_url) + "/api/version").get("version") or "?")
    except (OSError, ValueError):
        return ""


def models(base_url: str = "") -> list[dict]:
    """Geladene Modelle: [{"name", "size"}] (Größe in Bytes)."""
    data = _get(root_url(base_url) + "/api/tags", timeout=10)
    return [{"name": m.get("name") or m.get("model", ""), "size": int(m.get("size") or 0)}
            for m in data.get("models") or []]


def _run(cmd: list[str], progress: Callable[[str], None] | None) -> int:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                            creationflags=NO_WINDOW)
    for line in proc.stdout or []:
        line = line.strip().strip("\r")
        if line and progress:
            progress(line[-160:])
    return proc.wait()


def install_windows(progress: Callable[[str], None] | None = None) -> None:
    """Installiert Ollama für den angemeldeten Benutzer (keine Adminrechte): winget, sonst das offizielle Setup."""
    if shutil.which("winget"):
        code = _run(["winget", "install", "-e", "--id", WINGET_ID, "--silent", "--accept-package-agreements",
                     "--accept-source-agreements", "--disable-interactivity"], progress)
        if code == 0 or executable():
            return
    from omniwrench.core import net
    tmp = Path(tempfile.mkdtemp(prefix="omniwrench_ollama_"))
    setup = tmp / "OllamaSetup.exe"

    def report(done: int, total: int) -> None:
        if progress:
            progress(f"{done * 100 // total} % ({done // 1_048_576} / {total // 1_048_576} MB)" if total
                     else f"{done // 1_048_576} MB")
    net.download(SETUP_URL, setup, report)
    if progress:
        progress("OllamaSetup.exe /VERYSILENT …")
    code = subprocess.run([str(setup), "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"],
                          creationflags=NO_WINDOW).returncode
    shutil.rmtree(tmp, ignore_errors=True)
    if code != 0 and not executable():
        raise RuntimeError(f"OllamaSetup.exe exit code {code}")


def start(base_url: str = "", wait: float = 20.0) -> bool:
    """Dienst starten, falls er nicht läuft (ollama serve im Hintergrund). True = erreichbar."""
    if version(base_url):
        return True
    exe = executable()
    if not exe:
        return False
    flags = NO_WINDOW | (0x00000008 if sys.platform == "win32" else 0)          # DETACHED_PROCESS
    subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     creationflags=flags, start_new_session=sys.platform != "win32")
    end = time.time() + wait
    while time.time() < end:
        if version(base_url):
            return True
        time.sleep(0.5)
    return False


def pull(name: str, base_url: str = "", progress: Callable[[str], None] | None = None,
         stop: threading.Event | None = None) -> None:
    """Modell laden; progress bekommt „status NN %“. Fehler des Dienstes als RuntimeError."""
    body = json.dumps({"model": name, "stream": True}).encode()
    req = urllib.request.Request(root_url(base_url) + "/api/pull", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        for raw in resp:
            if stop is not None and stop.is_set():
                raise RuntimeError("stopped")
            try:
                msg = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                continue
            if msg.get("error"):
                raise RuntimeError(str(msg["error"]))
            status, total, done = msg.get("status", ""), int(msg.get("total") or 0), int(msg.get("completed") or 0)
            if progress:
                if total:
                    progress(f"{status[:40]} {done * 100 // total} % ({done / 1e9:.1f} / {total / 1e9:.1f} GB)")
                else:
                    progress(status)


def delete(name: str, base_url: str = "") -> None:
    req = urllib.request.Request(root_url(base_url) + "/api/delete", data=json.dumps({"model": name}).encode(),
                                 headers={"Content-Type": "application/json"}, method="DELETE")
    with urllib.request.urlopen(req, timeout=30):
        pass

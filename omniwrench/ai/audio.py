"""Audio aufnehmen: Mikrofon und Systemton (Loopback), in Sprachabschnitte zerlegt.

Systemton und Mikrofon liefert das Paket soundcard (WASAPI-Loopback unter Windows, PulseAudio-/PipeWire-Monitor
unter Linux), Rechnen erledigt numpy. Zusatzpakete der KI-Tools (numpy, soundcard, vosk, faster-whisper, piper-tts)
liegen gemeinsam in <LOCAL_DIR>/ai/lib (install_packages), Modelle und ffmpeg unter <LOCAL_DIR>/ai (shared_dir), damit
Mitschrift, Sprachassistent, Musik und Video nichts doppelt laden.
Qt-frei; die Abschnitte gehen über einen Rückruf im Hintergrund-Thread hinaus.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

RATE = 16000
FRAME = RATE // 10                   # 100 ms
MIN_SPEECH = 1.5                     # Sekunden Sprache, bevor ein Abschnitt abgegeben wird
MAX_CHUNK = 25.0                     # spätestens dann abgeben
SILENCE_END = 0.8                    # so lange Stille beendet einen Abschnitt
PRE_ROLL = 0.3
PACKAGES = ("numpy", "soundcard")


PIP_NAMES = {"faster_whisper": "faster-whisper", "piper": "piper-tts"}       # Import-Name -> pip-Name


def shared_dir() -> Path:
    """Gemeinsamer Ordner der KI-Tools (Pakete, Modelle, ffmpeg)."""
    from omniwrench.core import paths
    d = paths.LOCAL_DIR / "ai"
    d.mkdir(parents=True, exist_ok=True)
    return d


def lib_dir() -> Path:
    return shared_dir() / "lib"


def ensure_path() -> None:
    """Gemeinsamen Paketordner einbinden (beim Start und nach einer Installation)."""
    lib = lib_dir()
    if lib.is_dir() and str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    importlib.invalidate_caches()              # neu installierte Pakete sofort finden


def missing(packages=PACKAGES) -> list[str]:
    ensure_path()
    out = []
    for name in packages:
        try:
            importlib.import_module(name)
        except Exception:  # noqa: BLE001 - auch kaputte Installationen zählen als fehlend
            out.append(name)
    return out


def install_packages(packages: list[str], progress: Callable[[str], None] | None = None,
                     tool_dir: Path | None = None) -> str:
    """pip install in den gemeinsamen Paketordner. Gibt "" oder die Fehlermeldung zurück.

    Ohne --upgrade und mit dem Ordner im PYTHONPATH: pip sieht vorhandene Pakete (z. B. das schon geladene numpy)
    als erfüllt an und ersetzt sie nicht – unter Windows scheitert das Ersetzen geladener .pyd-Dateien mit WinError 5.
    tool_dir wird nicht mehr verwendet (früher <tool>/_lib) und nur noch aus Kompatibilität angenommen.
    """
    target = lib_dir()
    target.mkdir(parents=True, exist_ok=True)
    names = [PIP_NAMES.get(p, p) for p in packages]
    if progress:
        progress(", ".join(names))
    args = ["install", "--disable-pip-version-check", "--target", str(target), "--prefer-binary", *names]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(x for x in (str(target), env.get("PYTHONPATH", "")) if x)
    if getattr(sys, "frozen", False):
        fd, name = tempfile.mkstemp(prefix="omniwrench_pip_", suffix=".log")
        os.close(fd)
        cmd = [sys.executable, "--pip", *args, "--log", name]
    else:
        name = ""
        cmd = [sys.executable, "-m", "pip", *args]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                            creationflags=0x08000000 if sys.platform == "win32" else 0)
    lines: list[str] = []
    for line in proc.stdout or []:
        line = line.strip()
        if not line:
            continue
        lines.append(line)
        if progress and line.startswith(("Collecting", "Downloading", "Installing", "Successfully")):
            progress(line[:160])
    proc.wait()
    details = "\n".join(lines[-40:])
    if name:
        try:
            if not details.strip():
                details = Path(name).read_text(encoding="utf-8", errors="replace")
            Path(name).unlink(missing_ok=True)
        except OSError:
            pass
    if proc.returncode != 0:
        errs = [x for x in details.splitlines() if "error" in x.lower()]
        return (errs[-1] if errs else details.strip().splitlines()[-1]) if details.strip() \
            else f"pip exit code {proc.returncode}"
    ensure_path()
    return ""


# ------------------------------------------------------------------ Abschnitte
class Chunker:
    """Zerlegt einen Strom (float32, 16 kHz, mono) anhand der Lautstärke in Sprachabschnitte."""

    def __init__(self, on_chunk: Callable[[object, float], None], rate: int = RATE, min_speech: float = MIN_SPEECH,
                 silence_end: float = SILENCE_END, max_chunk: float = MAX_CHUNK):
        import numpy as np
        self.np = np
        self.rate = rate
        self.min_speech = min_speech
        self.silence_end = silence_end
        self.max_chunk = max_chunk
        self.on_chunk = on_chunk
        self.buf: list = []
        self.buf_start = 0.0          # Sekunden ab Aufnahmebeginn
        self.pos = 0.0
        self.noise = 0.004
        self.speech = 0.0
        self.silence = 0.0
        self.level = 0.0
        self._rest = np.zeros(0, dtype="float32")

    def threshold(self) -> float:
        return max(0.01, self.noise * 3.0)

    def feed(self, samples) -> None:
        np = self.np
        data = np.concatenate([self._rest, np.asarray(samples, dtype="float32").reshape(-1)])
        n = len(data) // FRAME * FRAME
        self._rest = data[n:]
        for i in range(0, n, FRAME):
            self._frame(data[i:i + FRAME])

    def _frame(self, frame) -> None:
        np = self.np
        rms = float(np.sqrt(np.mean(frame * frame))) if len(frame) else 0.0
        self.level = rms
        dur = len(frame) / self.rate
        loud = rms > self.threshold()
        if not loud:                   # Grundrauschen langsam nachführen
            self.noise = 0.95 * self.noise + 0.05 * rms
        if not self.buf:
            self.buf_start = self.pos
        self.buf.append(frame)
        self.pos += dur
        if loud:
            self.speech += dur
            self.silence = 0.0
        else:
            self.silence += dur
        length = len(self.buf) * dur
        if self.speech == 0.0 and length > PRE_ROLL:      # nur Stille: Vorlauf behalten
            drop = len(self.buf) - max(1, int(PRE_ROLL / dur))
            self.buf = self.buf[drop:]
            self.buf_start += drop * dur
            return
        if (self.speech >= self.min_speech and self.silence >= self.silence_end) or length >= self.max_chunk:
            self.flush()
        elif self.speech < self.min_speech and self.silence >= self.silence_end * 2:
            self.buf, self.speech = [], 0.0               # kurzes Geräusch verwerfen

    def flush(self) -> None:
        if self.buf and self.speech > 0.3:
            self.on_chunk(self.np.concatenate(self.buf), self.buf_start)
        self.buf, self.speech, self.silence = [], 0.0, 0.0


# ------------------------------------------------------------------ Quellen
class Source:
    """Liest ein Gerät in einem eigenen Thread. kind: "mic" oder "system"."""

    def __init__(self, kind: str, device_id: str = ""):
        self.kind = kind
        self.device_id = device_id
        self.error = ""

    def device(self):
        import soundcard as sc
        if self.kind == "system":
            spk = sc.get_speaker(self.device_id) if self.device_id else sc.default_speaker()
            return sc.get_microphone(id=str(spk.name), include_loopback=True)
        return sc.get_microphone(self.device_id, include_loopback=False) if self.device_id \
            else sc.default_microphone()

    def run(self, feed: Callable[[object], None], stop: threading.Event) -> None:
        if sys.platform == "win32":     # soundcard nutzt COM; jeder Thread braucht seine Initialisierung
            import ctypes
            ctypes.windll.ole32.CoInitializeEx(None, 0)
        import numpy as np
        with self.device().recorder(samplerate=RATE, blocksize=FRAME) as rec:
            while not stop.is_set():
                data = rec.record(numframes=FRAME)
                if data.ndim > 1:
                    data = data.mean(axis=1)
                feed(np.asarray(data, dtype="float32"))


def devices() -> dict[str, list[tuple[str, str]]]:
    """Verfügbare Geräte: {"mic": [(id, name)], "system": [(id, name)]}."""
    import soundcard as sc
    return {"mic": [(str(m.id), m.name) for m in sc.all_microphones(include_loopback=False)],
            "system": [(str(s.id), s.name) for s in sc.all_speakers()]}


class Recorder:
    """Nimmt mehrere Quellen gleichzeitig auf; on_chunk(kind, samples, start_sekunden) im Hintergrund."""

    def __init__(self, sources: list, on_chunk: Callable[[str, object, float], None],
                 on_error: Callable[[str, str], None] | None = None):
        self.sources = sources
        self.on_chunk = on_chunk
        self.on_error = on_error or (lambda kind, text: None)
        self.stop_event = threading.Event()
        self.chunkers: dict[str, Chunker] = {}
        self.threads: list[threading.Thread] = []
        self.started = 0.0
        self.paused = False

    def levels(self) -> dict[str, float]:
        return {k: c.level for k, c in self.chunkers.items()}

    def start(self) -> None:
        self.started = time.time()
        for src in self.sources:
            chunker = Chunker(lambda s, t, k=src.kind: self.on_chunk(k, s, t))
            self.chunkers[src.kind] = chunker

            def loop(src=src, chunker=chunker):
                def feed(data):
                    if not self.paused:
                        chunker.feed(data)
                    else:
                        chunker.pos += len(data) / RATE
                try:
                    src.run(feed, self.stop_event)
                except Exception as err:  # noqa: BLE001 - Gerät fehlt, Treiber, Rechte …
                    src.error = str(err) or err.__class__.__name__
                    self.on_error(src.kind, src.error)
                    return
                chunker.flush()
            t = threading.Thread(target=loop, name=f"audio-{src.kind}", daemon=True)
            self.threads.append(t)
            t.start()

    def stop(self) -> None:
        self.stop_event.set()
        for t in self.threads:
            t.join(3)
        self.threads = []

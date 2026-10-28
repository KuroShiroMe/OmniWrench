"""ffmpeg für Musik und Video: finden, unter Windows herunterladen, kleine Bearbeitungen.

Gesucht wird in dieser Reihenfolge: Einstellung "ffmpeg_path", <Datenordner>/ffmpeg/, PATH.
Windows-Download: aktueller GPL-Build von github.com/BtbN/FFmpeg-Builds (ffmpeg.exe + ffprobe.exe werden
nach <Datenordner>/ffmpeg/ entpackt). Unter Linux installiert die Paketverwaltung ffmpeg.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

WIN_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
EXE = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
PROBE = "ffprobe.exe" if os.name == "nt" else "ffprobe"
_FLAGS = 0x08000000 if sys.platform == "win32" else 0     # CREATE_NO_WINDOW


class FFmpegError(Exception):
    pass


def local_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "ffmpeg"


def find(settings, data_dir: Path) -> str:
    """Pfad zu ffmpeg oder ""."""
    own = (settings.get("ffmpeg_path") or "").strip() if settings is not None else ""
    if own and Path(own).is_file():
        return own
    local = local_dir(data_dir) / EXE
    if local.is_file():
        return str(local)
    return shutil.which("ffmpeg") or ""


def probe_path(ffmpeg: str) -> str:
    p = Path(ffmpeg).with_name(PROBE)
    return str(p) if p.is_file() else (shutil.which("ffprobe") or "")


def version(ffmpeg: str) -> str:
    try:
        out = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=15,
                             creationflags=_FLAGS).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.splitlines()[0] if out else ""


def linux_hint() -> str:
    for tool, cmd in (("apt", "sudo apt install ffmpeg"), ("dnf", "sudo dnf install ffmpeg"),
                      ("zypper", "sudo zypper install ffmpeg"), ("pacman", "sudo pacman -S ffmpeg")):
        if shutil.which(tool):
            return cmd
    return "ffmpeg"


def download_windows(data_dir: Path, progress: Callable[[str], None] | None = None) -> str:
    """Lädt ffmpeg (Windows, 64 Bit) herunter und entpackt ffmpeg.exe/ffprobe.exe. Gibt den Pfad zurück."""
    from omniwrench.core import net
    target = local_dir(data_dir)
    target.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="clank_ffmpeg_"))
    try:
        archive = tmp / "ffmpeg.zip"

        def report(done: int, total: int) -> None:
            if progress:
                progress(f"{done // 1_048_576} / {total // 1_048_576} MB" if total else f"{done // 1_048_576} MB")
        net.download(WIN_URL, archive, report)
        found = 0
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                base = name.rsplit("/", 1)[-1].lower()
                if base in ("ffmpeg.exe", "ffprobe.exe") and "/bin/" in name.lower():
                    with zf.open(name) as src, open(target / base, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    found += 1
        if found < 2:
            raise FFmpegError("ffmpeg.exe/ffprobe.exe not found in the archive")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return str(target / EXE)


# ------------------------------------------------------------------ Bearbeitungen
def _run(ffmpeg: str, args: list[str], timeout: float = 600) -> None:
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True,
                              text=True, timeout=timeout, creationflags=_FLAGS)
    except subprocess.TimeoutExpired:
        raise FFmpegError("timeout") from None
    except OSError as e:
        raise FFmpegError(str(e)) from None
    if proc.returncode != 0:
        raise FFmpegError((proc.stderr or "ffmpeg failed").strip()[-800:])


def duration(ffmpeg: str, path: Path) -> float:
    probe = probe_path(ffmpeg)
    if not probe:
        return 0.0
    try:
        out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                             capture_output=True, text=True, timeout=30, creationflags=_FLAGS).stdout
        return float(json.loads(out)["format"]["duration"])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return 0.0


def poster(ffmpeg: str, video: Path, out: Path, at: float = 0.5) -> Path:
    _run(ffmpeg, ["-ss", str(at), "-i", str(video), "-frames:v", "1", "-vf", "scale=320:-2", str(out)], 60)
    return out


def trim(ffmpeg: str, src: Path, dst: Path, start: float, end: float) -> Path:
    args = ["-ss", f"{max(0.0, start):.2f}", "-i", str(src)]
    if end > start:
        args += ["-t", f"{end - start:.2f}"]
    _run(ffmpeg, [*args, "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(dst)]
         if src.suffix.lower() in (".mp4", ".mov", ".webm") else [*args, str(dst)])
    return dst


def to_gif(ffmpeg: str, src: Path, dst: Path, width: int = 480, fps: int = 12) -> Path:
    vf = f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse"
    _run(ffmpeg, ["-i", str(src), "-vf", vf, "-loop", "0", str(dst)])
    return dst


def to_mp3(ffmpeg: str, src: Path, dst: Path) -> Path:
    _run(ffmpeg, ["-i", str(src), "-vn", "-c:a", "libmp3lame", "-q:a", "2", str(dst)])
    return dst


def mux(ffmpeg: str, video: Path, audio: Path, dst: Path, volume: float = 1.0) -> Path:
    """Legt Musik unter ein Video (ersetzt den Ton, Länge = Video)."""
    _run(ffmpeg, ["-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                  "-filter:a", f"volume={volume:.2f}", "-c:a", "aac", "-shortest", str(dst)])
    return dst


def mute(ffmpeg: str, video: Path, dst: Path) -> Path:
    _run(ffmpeg, ["-i", str(video), "-c:v", "copy", "-an", str(dst)])
    return dst

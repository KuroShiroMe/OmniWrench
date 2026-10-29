"""OmniWrench - modulare Toolsammlung für Administratoren, von KuroShiro."""

APP_NAME = "OmniWrench"
APP_ID = "OmniWrench"
VENDOR = "KuroShiro"
# Frühere Herstellernamen (Datenordner werden beim Start übernommen, core/paths.py)
LEGACY_VENDORS = ("DarkMatter",)
# Name des Mutex, an dem das Windows-Installationsprogramm ein laufendes OmniWrench erkennt
# (installer/windows/OmniWrench.iss, AppMutexName)
APP_MUTEX = "KuroShiro.OmniWrench"
__version__ = "0.9.0"

# GitHub-Repository: Updates des Hauptprogramms und offizieller Tool-Store
GITHUB_REPO = "KuroShiroMe/OmniWrench"
OFFICIAL_STORE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/store/index.json"


def _qt_audio_backend() -> None:
    """Linux: Qt Multimedia nimmt PipeWire, sobald die Bibliothek installiert ist. Läuft kein PipeWire-Dienst
    (Server, CI), stürzt der erste QMediaPlayer ab – dann PulseAudio nehmen. Muss vor Qt Multimedia laufen."""
    import os
    import sys
    from pathlib import Path

    if not sys.platform.startswith("linux") or os.environ.get("QT_AUDIO_BACKEND"):
        return
    run = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    if not Path(run, os.environ.get("PIPEWIRE_REMOTE") or "pipewire-0").exists():
        os.environ["QT_AUDIO_BACKEND"] = "pulseaudio"


_qt_audio_backend()

"""Zentrale Pfade der Anwendung.

Programmdateien und Benutzerdaten sind getrennt. Das Programm (APP_DIR) kann schreibgeschützt
im Programmordner liegen (Installation), alle Daten liegen im Benutzerverzeichnis:

    Windows  Roaming  %APPDATA%\\DarkMatter\\OmniWrench              -> Einstellungen, Tresor, Tool-Einstellungen
             Lokal    %LOCALAPPDATA%\\DarkMatter\\OmniWrench         -> installierte Tools, Tool-Daten, Cache, Logs
    Linux    Konfig.  $XDG_CONFIG_HOME/DarkMatter/OmniWrench        (Standard ~/.config/…)
             Daten    $XDG_DATA_HOME/DarkMatter/OmniWrench          (Standard ~/.local/share/…)

Abweichend davon liegt alles in einem Ordner, wenn
  * die Umgebungsvariable OMNIWRENCH_HOME gesetzt ist (Tests, Sonderfälle) oder
  * neben dem Programm ein Ordner "portable-data" existiert (portable Version z. B. auf einem USB-Stick).

Installationsart (INSTALL_KIND): "setup" (Windows-Installationsprogramm), "deb" (Linux-Paket),
"portable" (entpacktes Programmpaket) oder "source" (Start aus dem Quellcode). Die Installations-
programme legen dazu die Datei omniwrench-install.json neben das Programm.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from omniwrench import APP_ID, VENDOR

# Installationsverzeichnis des Hauptprogramms (Quellordner bzw. Ordner der EXE)
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parents[2]

RESOURCES_DIR = Path(__file__).resolve().parents[1] / "resources"

INSTALL_MARKER = APP_DIR / "omniwrench-install.json"
PORTABLE_DATA_DIR = APP_DIR / "portable-data"


def _install_kind() -> str:
    try:
        kind = json.loads(INSTALL_MARKER.read_text(encoding="utf-8")).get("kind", "")
        if kind in ("setup", "deb"):
            return kind
    except (OSError, ValueError, AttributeError):
        pass
    return "portable" if getattr(sys, "frozen", False) else "source"


INSTALL_KIND = _install_kind()


def _user_dirs() -> tuple[Path, Path]:
    """Benutzerverzeichnisse (Konfiguration, lokale Daten) nach den Regeln des Betriebssystems."""
    if sys.platform == "win32":
        roaming = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        roaming = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        local = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return roaming / VENDOR / APP_ID, local / VENDOR / APP_ID


def _base_dirs() -> tuple[Path, Path]:
    home = os.environ.get("OMNIWRENCH_HOME")
    if home:
        base = Path(home)
        return base / "config", base / "local"
    if PORTABLE_DATA_DIR.is_dir():
        return PORTABLE_DATA_DIR / "config", PORTABLE_DATA_DIR / "local"
    return _user_dirs()


CONFIG_DIR, LOCAL_DIR = _base_dirs()

SETTINGS_FILE = CONFIG_DIR / "settings.json"
VAULT_FILE = CONFIG_DIR / "vault.json"
TOOL_SETTINGS_DIR = CONFIG_DIR / "tool_settings"
LAYOUT_FILE = CONFIG_DIR / "layout.json"

TOOLS_DIR = LOCAL_DIR / "tools"
TOOL_DATA_DIR = LOCAL_DIR / "tool_data"
CACHE_DIR = LOCAL_DIR / "cache"
LOG_DIR = LOCAL_DIR / "logs"

# Meldungen der Datenübernahme beim Start (werden nach dem Einrichten des Loggings geschrieben)
MIGRATION_LOG: list[str] = []


def _legacy_dirs() -> list[tuple[Path, Path]]:
    """Frühere Datenorte, die beim ersten Start an den aktuellen Ort übernommen werden.

    Bis 0.6.0 gab es nur Windows-Pfade; außerhalb von Windows landeten die Daten deshalb in
    ~/AppData/Roaming bzw. ~/AppData/Local (fehlende Umgebungsvariablen APPDATA/LOCALAPPDATA).
    """
    if sys.platform == "win32" or os.environ.get("OMNIWRENCH_HOME") or PORTABLE_DATA_DIR.is_dir():
        return []
    old = Path.home() / "AppData"
    return [(old / "Roaming" / VENDOR / APP_ID, CONFIG_DIR), (old / "Local" / VENDOR / APP_ID, LOCAL_DIR)]


def migrate_legacy_data() -> None:
    """Verschiebt Daten von einem früheren Ort, solange am neuen Ort noch nichts liegt."""
    for old, new in _legacy_dirs():
        if not old.is_dir() or (new.exists() and any(new.iterdir())):
            continue
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            if new.exists():
                new.rmdir()
            shutil.move(str(old), str(new))
            MIGRATION_LOG.append(f"Daten übernommen: {old} -> {new}")
            for parent in (old.parent, old.parent.parent, old.parent.parent.parent):  # leere AppData-Reste
                try:
                    parent.rmdir()
                except OSError:
                    break
        except OSError as exc:
            MIGRATION_LOG.append(f"Daten aus {old} konnten nicht nach {new} übernommen werden: {exc}")


def ensure_dirs() -> None:
    migrate_legacy_data()
    for d in (CONFIG_DIR, LOCAL_DIR, TOOL_SETTINGS_DIR, TOOLS_DIR, TOOL_DATA_DIR, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def app_dir_writable() -> bool:
    """True, wenn das Programm seinen eigenen Ordner überschreiben darf (Selbst-Update ohne Adminrechte)."""
    probe = APP_DIR / f".write-test-{os.getpid()}"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False

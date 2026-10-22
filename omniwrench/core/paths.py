"""Zentrale Pfade der Anwendung.

Programmdateien und Benutzerdaten sind getrennt. Das Programm (APP_DIR) kann schreibgeschützt
im Programmordner liegen (Installation), alle Daten liegen im Benutzerverzeichnis:

    Windows  Roaming  %APPDATA%\\KuroShiro\\OmniWrench               -> Einstellungen, Tresor, Tool-Einstellungen
             Lokal    %LOCALAPPDATA%\\KuroShiro\\OmniWrench          -> installierte Tools, Tool-Daten, Cache, Logs
    Linux    Konfig.  $XDG_CONFIG_HOME/KuroShiro/OmniWrench         (Standard ~/.config/…)
             Daten    $XDG_DATA_HOME/KuroShiro/OmniWrench           (Standard ~/.local/share/…)

Daten an früheren Orten (Herstellername DarkMatter bis 0.7.0, unter Linux bis 0.6.0 ~/AppData/…)
werden beim ersten Start übernommen, siehe _migrate().

Abweichend davon liegt alles in einem Ordner, wenn
  * die Umgebungsvariable OMNIWRENCH_HOME gesetzt ist (Tests, Sonderfälle) oder
  * neben dem Programm ein Ordner "portable-data" existiert (portable Version z. B. auf einem USB-Stick).

Installationsart (INSTALL_KIND): "setup" (Windows-Installationsprogramm), "deb" (Linux-Paket),
"portable" (entpacktes Programmpaket) oder "source" (Start aus dem Quellcode). Die Installations-
programme legen dazu die Datei omniwrench-install.json neben das Programm.
"""

from __future__ import annotations

import errno
import json
import os
import shutil
import sys
from pathlib import Path

from omniwrench import APP_ID, LEGACY_VENDORS, VENDOR

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


def _os_dirs() -> tuple[Path, Path]:
    """Basisordner für Konfiguration und lokale Daten nach den Regeln des Betriebssystems."""
    if sys.platform == "win32":
        roaming = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        roaming = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        local = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return roaming, local


def _legacy_dirs() -> tuple[list[Path], list[Path]]:
    """Frühere Datenorte (Konfiguration, lokale Daten), neueste zuerst.

    Bis 0.7.0 hieß der Hersteller DarkMatter. Bis 0.6.0 gab es nur Windows-Pfade; außerhalb von
    Windows landeten die Daten deshalb in ~/AppData/Roaming bzw. ~/AppData/Local.
    """
    roaming, local = _os_dirs()
    config = [roaming / v / APP_ID for v in LEGACY_VENDORS]
    data = [local / v / APP_ID for v in LEGACY_VENDORS]
    if sys.platform != "win32":
        old = Path.home() / "AppData"
        config += [old / "Roaming" / v / APP_ID for v in LEGACY_VENDORS]
        data += [old / "Local" / v / APP_ID for v in LEGACY_VENDORS]
    return config, data


# Meldungen der Datenübernahme beim Start (werden nach dem Einrichten des Loggings geschrieben)
MIGRATION_LOG: list[str] = []


def _has_content(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def _remove_empty_parents(path: Path, levels: int) -> None:
    for parent in list(path.parents)[:levels]:
        try:
            parent.rmdir()
        except OSError:
            break


def _migrate(new: Path, candidates: list[Path]) -> Path:
    """Verschiebt Daten von einem früheren Ort nach new, solange dort noch nichts liegt.

    Gelingt das Verschieben nicht (z. B. Datei gesperrt), bleibt der alte Ort in Gebrauch, damit
    Einstellungen, Tresor und Tools nicht verloren scheinen. Gibt den zu verwendenden Ordner zurück.
    """
    if _has_content(new):
        return new
    for old in candidates:
        if not _has_content(old):
            continue
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            if new.exists():
                new.rmdir()
            try:
                os.rename(old, new)  # in einem Schritt: gesperrte Dateien lassen alles am alten Ort
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                shutil.move(str(old), str(new))  # anderes Dateisystem
        except OSError as exc:
            MIGRATION_LOG.append(f"Daten aus {old} konnten nicht nach {new} übernommen werden, "
                                 f"der bisherige Ort bleibt in Gebrauch: {exc}")
            return old
        MIGRATION_LOG.append(f"Daten übernommen: {old} -> {new}")
        _remove_empty_parents(old, 3)  # leere Herstellerordner (DarkMatter, AppData-Reste)
        return new
    return new


def _base_dirs() -> tuple[Path, Path]:
    home = os.environ.get("OMNIWRENCH_HOME")
    if home:
        base = Path(home)
        return base / "config", base / "local"
    if PORTABLE_DATA_DIR.is_dir():
        return PORTABLE_DATA_DIR / "config", PORTABLE_DATA_DIR / "local"
    roaming, local = _os_dirs()
    old_config, old_local = _legacy_dirs()
    # Beim Import, weil andere Module die Pfade direkt als Konstanten übernehmen
    return (_migrate(roaming / VENDOR / APP_ID, old_config),
            _migrate(local / VENDOR / APP_ID, old_local))


CONFIG_DIR, LOCAL_DIR = _base_dirs()

SETTINGS_FILE = CONFIG_DIR / "settings.json"
VAULT_FILE = CONFIG_DIR / "vault.json"
TOOL_SETTINGS_DIR = CONFIG_DIR / "tool_settings"
LAYOUT_FILE = CONFIG_DIR / "layout.json"

TOOLS_DIR = LOCAL_DIR / "tools"
TOOL_DATA_DIR = LOCAL_DIR / "tool_data"
CACHE_DIR = LOCAL_DIR / "cache"
LOG_DIR = LOCAL_DIR / "logs"

def ensure_dirs() -> None:
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

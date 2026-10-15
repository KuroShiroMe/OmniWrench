"""Zentrale Pfade der Anwendung.

Standard:
    Roaming (%APPDATA%\\AdminTools)       -> Einstellungen, Tresor, Tool-Einstellungen
    Lokal   (%LOCALAPPDATA%\\AdminTools)  -> installierte Tools, Cache, Logs

Mit der Umgebungsvariable ADMINTOOLS_HOME kann alles in einen Ordner
umgeleitet werden (z. B. für eine portable Installation).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from admintools import APP_ID


def _base_dirs() -> tuple[Path, Path]:
    home = os.environ.get("ADMINTOOLS_HOME")
    if home:
        base = Path(home)
        return base / "config", base / "local"
    roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return roaming / APP_ID, local / APP_ID


CONFIG_DIR, LOCAL_DIR = _base_dirs()

SETTINGS_FILE = CONFIG_DIR / "settings.json"
VAULT_FILE = CONFIG_DIR / "vault.json"
TOOL_SETTINGS_DIR = CONFIG_DIR / "tool_settings"
LAYOUT_FILE = CONFIG_DIR / "layout.json"

TOOLS_DIR = LOCAL_DIR / "tools"
TOOL_DATA_DIR = LOCAL_DIR / "tool_data"
CACHE_DIR = LOCAL_DIR / "cache"
LOG_DIR = LOCAL_DIR / "logs"

# Installationsverzeichnis des Hauptprogramms (Quellordner bzw. Ordner der EXE)
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parents[2]

RESOURCES_DIR = Path(__file__).resolve().parents[1] / "resources"


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, LOCAL_DIR, TOOL_SETTINGS_DIR, TOOLS_DIR, TOOL_DATA_DIR, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)

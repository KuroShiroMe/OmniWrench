"""Einstellungen des Hauptprogramms."""

from __future__ import annotations

import copy
from typing import Any

from .jsonio import read_json, write_json
from .paths import APP_DIR, SETTINGS_FILE

DEFAULTS: dict[str, Any] = {
    # GitHub-Repository des Hauptprogramms für Updates ("owner/repo")
    "app_update_repo": "",
    "check_updates_on_start": True,
    "include_prereleases": False,
    # Tool-Repositories: Liste von index.json-URLs (https://, file:// oder lokaler Pfad)
    "repositories": [
        {"name": "Local development store", "url": str(APP_DIR / "store" / "index.json"), "enabled": True},
    ],
    "theme": "dark",
    # Sprache des Hauptprogramms (leer = Windows-Anzeigesprache, sonst Englisch)
    "language": "",
    "auto_lock_minutes": 0,
    "restore_layout": True,
}


class AppSettings:
    def __init__(self):
        stored = read_json(SETTINGS_FILE, default={}) or {}
        self._data = copy.deepcopy(DEFAULTS)
        self._data.update(stored)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self._data[key] = value
        if save:
            self.save()

    def save(self) -> None:
        write_json(SETTINGS_FILE, self._data)

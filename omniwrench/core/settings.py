"""Einstellungen des Hauptprogramms."""

from __future__ import annotations

import copy
from typing import Any

from omniwrench import GITHUB_REPO, LEGACY_VENDORS, OFFICIAL_STORE_URL, VENDOR

from .jsonio import read_json, write_json
from .paths import APP_DIR, SETTINGS_FILE

def _default_repositories() -> list[dict]:
    repos = []
    # Beim Start aus dem Quellcode zusätzlich den lokal gebauten Store anbieten (für Tool-Entwicklung)
    local_store = APP_DIR / "store" / "index.json"
    if local_store.exists():
        repos.append({"name": "Local development store", "url": str(local_store), "enabled": True})
    repos.append({"name": f"{VENDOR} Store", "url": OFFICIAL_STORE_URL, "enabled": True})
    return repos


DEFAULTS: dict[str, Any] = {
    # GitHub-Repository des Hauptprogramms für Updates ("owner/repo")
    "app_update_repo": GITHUB_REPO,
    "check_updates_on_start": True,
    "include_prereleases": False,
    # Tool-Updates beim Start ohne Rückfrage im Hintergrund installieren
    "auto_update_tools": False,
    # Installations-/Update-Fenster nach erfolgreichem Abschluss selbst schließen (Haken im Fenster)
    "close_update_window": False,
    # Tool-Repositories: Liste von index.json-URLs (https://, file:// oder lokaler Pfad)
    "repositories": _default_repositories(),
    "theme": "dark",
    # Zusätzliche Skalierung der Oberfläche (1.0 = Windows-Anzeigeskalierung); wirkt nach Neustart
    "ui_scale": 1.0,
    # Sprache des Hauptprogramms (leer = Windows-Anzeigesprache, sonst Englisch)
    "language": "",
    "auto_lock_minutes": 0,
    "restore_layout": True,
    # Ansicht im Home-Tab: "full" (Karten mit Screenshot wie im Store), "large", "small", "list"
    "home_view": "full",
}

# Frühere GitHub-Namen des Repositorys; gespeicherte Einstellungen werden beim Laden umgeschrieben
_OLD_GITHUB_REPOS = ("Steffi-Tech/OmniWrench",)


def _migrate_repo_name(data: dict) -> bool:
    changed = False
    for old in _OLD_GITHUB_REPOS:
        if data.get("app_update_repo", "").lower() == old.lower():
            data["app_update_repo"] = GITHUB_REPO
            changed = True
        for repo in data.get("repositories") or []:
            url = repo.get("url", "") if isinstance(repo, dict) else ""
            if f"/{old}/" in url:
                repo["url"] = url.replace(f"/{old}/", f"/{GITHUB_REPO}/")
                changed = True
    # Früherer Herstellername im Namen des offiziellen Stores
    for repo in data.get("repositories") or []:
        if isinstance(repo, dict) and repo.get("name") in {f"{v} Store" for v in LEGACY_VENDORS}:
            repo["name"] = f"{VENDOR} Store"
            changed = True
    return changed


class AppSettings:
    def __init__(self):
        stored = read_json(SETTINGS_FILE, default={}) or {}
        self._data = copy.deepcopy(DEFAULTS)
        self._data.update(stored)
        if stored and _migrate_repo_name(self._data):
            self.save()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self._data[key] = value
        if save:
            self.save()

    def save(self) -> None:
        write_json(SETTINGS_FILE, self._data)

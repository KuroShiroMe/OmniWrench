"""Store-Kataloge (index.json) aus einem oder mehreren Repositories.

Format einer index.json:

    {
      "format": 1,
      "name": "Mein Admin-Tools-Store",
      "tools": [
        { ...alle Felder aus tool.json...,
          "download_url": "packages/net.subnet-calculator-1.0.0.zip",   # relativ oder absolut
          "sha256": "…" }
      ]
    }

Erzeugt wird die Datei mit scripts/build_store.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import net
from .i18n import tr
from .manifest import ToolManifest
from .tool_manager import ToolManager
from .versioning import is_newer, parse_version

log = logging.getLogger(__name__)


@dataclass
class CatalogEntry:
    manifest: ToolManifest
    repo_name: str
    download_url: str


@dataclass
class Catalog:
    entries: dict[str, CatalogEntry] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def load_catalog(repositories: list[dict]) -> Catalog:
    catalog = Catalog()
    for repo in repositories:
        if not repo.get("enabled", True):
            continue
        url, name = repo["url"], repo.get("name") or repo["url"]
        try:
            data = json.loads(net.get_bytes(url))
        except Exception as exc:  # noqa: BLE001
            catalog.errors.append(f"{name}: {exc}")
            log.warning("Repository %s nicht erreichbar: %s", url, exc)
            continue
        for item in data.get("tools", []):
            try:
                manifest = ToolManifest.from_dict(item)
            except Exception as exc:  # noqa: BLE001
                catalog.errors.append(f"{name}: " + tr("err.catalog_entry", error=exc))
                continue
            if not manifest.download_url:
                continue
            for shot in manifest.screenshot_list:  # Screenshots liegen getrennt vom Paket im Store
                if shot.get("url"):
                    shot["url"] = net.resolve(url, shot["url"])
            entry = CatalogEntry(manifest, name, net.resolve(url, manifest.download_url))
            existing = catalog.entries.get(manifest.id)
            # Bei mehreren Repos gewinnt die höchste Version
            if existing is None or parse_version(manifest.version) > parse_version(existing.manifest.version):
                catalog.entries[manifest.id] = entry
    return catalog


def available_updates(catalog: Catalog, manager: ToolManager) -> dict[str, CatalogEntry]:
    return {
        tool_id: entry
        for tool_id, entry in catalog.entries.items()
        if (tool := manager.get(tool_id)) and is_newer(entry.manifest.version, tool.manifest.version)
    }


def install_from_catalog(entry: CatalogEntry, manager: ToolManager, progress: Callable[[str], None]) -> None:
    progress(tr("prog.download", name=entry.manifest.display_name, version=entry.manifest.version))
    with tempfile.TemporaryDirectory(prefix="omniwrench_dl_") as tmp:
        zip_path = net.download(entry.download_url, Path(tmp) / "package.zip")
        manager.install_zip(zip_path, progress, expected_sha256=entry.manifest.sha256)
    fetch_screenshots(entry, manager)


def fetch_screenshots(entry: CatalogEntry, manager: ToolManager) -> None:
    """Legt die Screenshots aus dem Store in den Tool-Ordner (für Home, auch offline). Fehler sind egal."""
    tool = manager.get(entry.manifest.id)
    if tool is None:
        return
    for shot in entry.manifest.screenshot_list:
        target = tool.path / shot["file"]
        if not shot.get("url") or tool.path not in target.resolve().parents:
            continue
        try:
            data = net.get_bytes(shot["url"])
            if shot.get("sha256") and hashlib.sha256(data).hexdigest() != shot["sha256"]:
                raise ValueError("sha256")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except Exception as exc:  # noqa: BLE001
            log.info("Screenshot %s von %s nicht geladen: %s", shot["file"], entry.manifest.id, exc)


def update_tools(entries: list[CatalogEntry], manager: ToolManager,
                 progress: Callable[[str], None]) -> tuple[list[str], list[str]]:
    """Installiert mehrere Updates nacheinander. Ein Fehler bricht die übrigen nicht ab.

    Rückgabe: (aktualisierte Namen, fehlgeschlagene "Name: Fehler").
    """
    updated, failed = [], []
    for i, entry in enumerate(entries, 1):
        m = entry.manifest
        tool = manager.get(m.id)
        old = tool.manifest.version if tool else "-"
        progress(("\n" if i > 1 else "") + f"[{i}/{len(entries)}] "
                 + tr("updates.item", name=m.display_name, old=old, new=m.version))
        try:
            install_from_catalog(entry, manager, progress)
        except Exception as exc:  # noqa: BLE001 - nächstes Tool trotzdem aktualisieren
            log.warning("Update von %s fehlgeschlagen: %s", m.id, exc)
            progress(tr("task.error", error=exc))
            failed.append(f"{m.display_name}: {exc}")
        else:
            updated.append(m.display_name)
    return updated, failed

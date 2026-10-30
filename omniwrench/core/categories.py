"""Kategorien der Tools: feste Service-Bereiche, eine Ebene.

tool.json gibt die Kategorie als ID an, z. B. "identity". Die Bereiche übersetzt das Hauptprogramm
(category.area.<id>). Feinere Einordnung (Technologie, Aufgabe) läuft über "tags". Ganz neue Bereiche bringt
ein Tool selbst mit ("tool.category_area" in seinen Sprachdateien). Ältere Angaben mit Unterkategorie
("identity/active_directory") und alte Freitext-Pfade ("Network/IP Tools") werden auf den Bereich reduziert.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .i18n import tr

if TYPE_CHECKING:
    from .manifest import ToolManifest

AREAS: tuple[str, ...] = (
    "workplace", "identity", "network", "infrastructure", "cloud", "security",
    "applications", "operations", "servicedesk", "automation", "documentation", "ai",
)
OTHER = "other"  # Rückfall, übersetzt als category.other

# Erste Ebene alter Freitext-Pfade (klein geschrieben) -> Bereich
LEGACY_AREAS = {
    "ms server tools": "identity", "active directory": "identity",
    "network": "network", "netzwerk": "network",
    "security": "security", "sicherheit": "security",
    "design": "documentation",
}


def translation_keys() -> set[str]:
    """Alle Übersetzungsschlüssel der Kategorien (für check_locales)."""
    return {f"category.area.{a}" for a in AREAS}


def _norm(part: str) -> str:
    return part.strip().lower().replace("-", "_")


def _first(path: str) -> str:
    return next((p.strip() for p in path.split("/") if p.strip()), "")


def category_id(manifest: "ToolManifest") -> str:
    """Bereich als ID; unbekannte Angaben bleiben als Text."""
    head = _first(manifest.category)
    if not head:
        return OTHER
    if _norm(head) in AREAS or _norm(head) == OTHER:
        return _norm(head)
    return LEGACY_AREAS.get(head.lower(), head)


def category_path(manifest: "ToolManifest") -> list[str]:
    """Anzeigepfad (nur der Bereich) in der Sprache des Hauptprogramms."""
    area = category_id(manifest)
    if area in AREAS:
        return [tr(f"category.area.{area}")]
    if area == OTHER:
        return [tr("category.other")]
    return [manifest.localized("category_area") or _first(manifest.localized("category")) or area]

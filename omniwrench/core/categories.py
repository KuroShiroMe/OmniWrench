"""Kategorien der Tools: feste Service-Bereiche mit Unterkategorien.

tool.json gibt die Kategorie als IDs an: "<bereich>/<unterkategorie>", z. B. "identity/active_directory".
Bereiche und häufige Unterkategorien übersetzt das Hauptprogramm (category.area.<id>, category.sub.<id>).
Eigene Unterkategorien oder ganz neue Bereiche bringt ein Tool selbst mit ("tool.subcategory" bzw.
"tool.category_area" in seinen Sprachdateien). Alte Freitext-Pfade ("Network/IP Tools") werden über
LEGACY_AREAS einem Bereich zugeordnet. Höchstens zwei Ebenen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .i18n import tr

if TYPE_CHECKING:
    from .manifest import ToolManifest

AREAS: dict[str, tuple[str, ...]] = {
    "workplace": ("windows_client", "software_deployment", "printing", "mobile_devices", "peripherals"),
    "identity": ("active_directory", "entra_id", "groups_permissions", "mfa_smartcard"),
    "network": ("ip_dns_dhcp", "lan_wlan", "vpn_remote_access", "firewall", "diagnostics"),
    "infrastructure": ("virtualization", "storage", "backup_recovery", "server_operations"),
    "cloud": ("exchange_email", "teams", "sharepoint_onedrive", "azure", "licensing"),
    "security": ("passwords_secrets", "certificates_pki", "encryption", "vulnerabilities"),
    "applications": ("sql_server", "webserver_iis", "business_applications"),
    "operations": ("event_logs", "monitoring", "inventory_cmdb", "performance"),
    "servicedesk": ("remote_support", "user_help", "ticket_tools"),
    "automation": ("powershell_scripts", "api", "converters"),
    "documentation": ("icons", "diagrams", "templates"),
}
OTHER = "other"  # Rückfall, übersetzt als category.other
SUBCATEGORIES: frozenset[str] = frozenset(s for subs in AREAS.values() for s in subs)

# Erste Ebene alter Freitext-Pfade (klein geschrieben) -> Bereich
LEGACY_AREAS = {
    "ms server tools": "identity", "active directory": "identity",
    "network": "network", "netzwerk": "network",
    "security": "security", "sicherheit": "security",
    "design": "documentation",
}


def translation_keys() -> set[str]:
    """Alle Übersetzungsschlüssel der Kategorien (für check_locales)."""
    return {f"category.area.{a}" for a in AREAS} | {f"category.sub.{s}" for s in SUBCATEGORIES}


def _norm(part: str) -> str:
    return part.strip().lower().replace("-", "_")


def _split(path: str) -> list[str]:
    return [p.strip() for p in path.split("/") if p.strip()]


def category_ids(manifest: "ToolManifest") -> tuple[str, str]:
    """(Bereich, Unterkategorie) als IDs; unbekannte Angaben bleiben als Text, leer = keine."""
    parts = _split(manifest.category)
    if not parts:
        return OTHER, ""
    head = _norm(parts[0])
    area = head if head in AREAS or head == OTHER else LEGACY_AREAS.get(parts[0].lower(), parts[0])
    return area, parts[1] if len(parts) > 1 else ""


def category_path(manifest: "ToolManifest") -> list[str]:
    """Anzeigepfad (Bereich, ggf. Unterkategorie) in der Sprache des Hauptprogramms."""
    area, sub = category_ids(manifest)
    old = _split(manifest.localized("category"))  # Freitext-Übersetzung alter Tools
    if area in AREAS:
        path = [tr(f"category.area.{area}")]
    elif area == OTHER:
        path = [tr("category.other")]
    else:
        path = [manifest.localized("category_area") or (old[0] if old else area)]
    if sub:
        if _norm(sub) in SUBCATEGORIES:
            path.append(tr(f"category.sub.{_norm(sub)}"))
        else:
            path.append(manifest.localized("subcategory") or (old[1] if len(old) > 1 else sub))
    return path

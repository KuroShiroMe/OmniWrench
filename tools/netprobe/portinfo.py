"""Zugriff auf die Port-Bibliothek (portlib.json): Name, Gruppe, Kennzeichen und Verwendungsszenarien."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).with_name("portlib.json")


@lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8")).get("ports", {})


PORT_META = _load()


def library_ports() -> list[int]:
    """Alle TCP-Ports der Bibliothek (für das Standard-Scanprofil)."""
    return sorted({int(key.split("/")[0]) for key, meta in PORT_META.items() if key.endswith("/tcp")})


def describe(port: int, proto: str, lang: str) -> dict:
    """Übersetzte Beschreibung und Szenarien eines Ports ({} falls unbekannt)."""
    meta = PORT_META.get(f"{port}/{proto}")
    if not meta:
        return {}
    texts = meta.get(lang) or meta.get("en") or {}
    return {"name": meta.get("name", ""), "group": meta.get("group", ""), "flags": meta.get("flags", []),
            "description": texts.get("d", ""), "uses": texts.get("u", [])}

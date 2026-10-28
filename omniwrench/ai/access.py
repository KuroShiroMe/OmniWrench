"""Zugriffsstufen der Assistenten (Seite „KI-Zugriff“) und Verfremdung je Quelle.

Einstellungen:
    "ai_access": {"level": 1, "pseudo": true, "pseudo_kinds": {...}, "exceptions": {"<verbindung>": 3}}
    "ai_access_tools": {"<tool-id>": {"level": null|int, "pseudo": null|bool, "exceptions": {...}}}

Vererbung: Ein Tool ohne eigene Stufe (null) nutzt die Stufe des Hauptprogramms. Ausnahmen je
Assistent gehen vor. Zur Laufzeit können Tools die Stufe vorübergehend setzen (Anmeldeleiste von
DHCP/DNS mit Favoriten-Abschnitt "ai"), siehe set_runtime().
"""

from __future__ import annotations

import threading

from .functions import LEVEL_CHANGE, LEVEL_DESCRIBE, LEVEL_NONE, LEVEL_OVERVIEW, LEVEL_READ

APP_KEY = "ai_access"
TOOLS_KEY = "ai_access_tools"
LEVELS = (LEVEL_NONE, LEVEL_DESCRIBE, LEVEL_OVERVIEW, LEVEL_READ, LEVEL_CHANGE)
DEFAULT_LEVEL = LEVEL_DESCRIBE
PSEUDO_KINDS = ("ip", "mac", "host", "domain", "user", "email", "keep_network")
DEFAULT_KINDS = {k: True for k in PSEUDO_KINDS}       # Stef: Verfremdung an, und zwar alles

_runtime: dict[str, dict] = {}     # tool_id -> {"level": int|None, "pseudo": bool|None}
_lock = threading.Lock()


def _clamp(level) -> int | None:
    if level is None:
        return None
    try:
        return max(LEVEL_NONE, min(LEVEL_CHANGE, int(level)))
    except (TypeError, ValueError):
        return None


def app_config(settings) -> dict:
    cfg = dict(settings.get(APP_KEY) or {})
    cfg.setdefault("level", DEFAULT_LEVEL)
    cfg.setdefault("pseudo", True)
    cfg["pseudo_kinds"] = {**DEFAULT_KINDS, **(cfg.get("pseudo_kinds") or {})}
    cfg.setdefault("exceptions", {})
    return cfg


def set_app_config(settings, cfg: dict) -> None:
    settings.set(APP_KEY, cfg)


def tool_config(settings, tool_id: str) -> dict:
    cfg = dict((settings.get(TOOLS_KEY) or {}).get(tool_id) or {})
    cfg.setdefault("level", None)
    cfg.setdefault("pseudo", None)
    cfg.setdefault("exceptions", {})
    return cfg


def set_tool_config(settings, tool_id: str, cfg: dict) -> None:
    data = dict(settings.get(TOOLS_KEY) or {})
    data[tool_id] = cfg
    settings.set(TOOLS_KEY, data)


def set_runtime(tool_id: str, level: int | None = None, pseudo: bool | None = None) -> None:
    """Vorübergehende Stufe eines Tools (z. B. aus dem gewählten Favoriten). None = keine Vorgabe."""
    with _lock:
        if level is None and pseudo is None:
            _runtime.pop(tool_id, None)
        else:
            _runtime[tool_id] = {"level": _clamp(level), "pseudo": pseudo}


def runtime(tool_id: str) -> dict:
    with _lock:
        return dict(_runtime.get(tool_id) or {})


def app_level(settings, conn_id: str = "") -> int:
    cfg = app_config(settings)
    exc = _clamp((cfg.get("exceptions") or {}).get(conn_id)) if conn_id else None
    return exc if exc is not None else (_clamp(cfg.get("level")) if _clamp(cfg.get("level")) is not None
                                        else DEFAULT_LEVEL)


def level(settings, source: str, conn_id: str = "") -> int:
    """Wirksame Stufe einer Quelle ("app" oder Tool-ID) für eine Verbindung."""
    if source == "app":
        return app_level(settings, conn_id)
    cfg = tool_config(settings, source)
    exc = _clamp((cfg.get("exceptions") or {}).get(conn_id)) if conn_id else None
    if exc is not None:
        return exc
    rt = runtime(source).get("level")
    if rt is not None:
        return rt
    own = _clamp(cfg.get("level"))
    return own if own is not None else app_level(settings, conn_id)


def pseudo_enabled(settings, source: str = "app") -> bool:
    app = bool(app_config(settings).get("pseudo", True))
    if source == "app":
        return app
    rt = runtime(source).get("pseudo")
    if rt is not None:
        return bool(rt)
    own = tool_config(settings, source).get("pseudo")
    return app if own is None else bool(own)


def pseudo_kinds(settings) -> dict:
    return app_config(settings)["pseudo_kinds"]

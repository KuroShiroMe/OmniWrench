"""Funktionen, die ein Assistent aufrufen darf (Function Calling).

Jede Funktion gehört zu einer Quelle ("app" oder Tool-ID) und braucht eine Mindest-Zugriffsstufe:
    1 Beschreibung   2 Übersicht   3 Lesen   4 Ändern mit Bestätigung
Welche Stufe gilt, entscheidet access.py (Seite „KI-Zugriff“). Funktionen der Stufe 4 laufen
nur nach Bestätigung im Programm.

Handler bekommen (args: dict, ctx: CallContext) und geben Text oder JSON-fähige Daten zurück.
Sie laufen im Hintergrund; wer Qt braucht, nutzt ctx.in_gui().
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

LEVEL_NONE, LEVEL_DESCRIBE, LEVEL_OVERVIEW, LEVEL_READ, LEVEL_CHANGE = 0, 1, 2, 3, 4
MAX_RESULT_CHARS = 30_000


@dataclass
class Function:
    name: str
    description: str
    handler: Callable[[dict, "CallContext"], Any]
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    source: str = "app"
    level: int = LEVEL_DESCRIBE
    confirm: bool = False           # Änderung: vor dem Ausführen nachfragen
    summary: Callable[[dict], str] | None = None   # Text für die Bestätigung
    owner: Any = None               # z. B. ToolContext einer Tab-Instanz (zum Entfernen beim Schließen)

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


@dataclass
class CallContext:
    """Was ein Handler über die Umgebung wissen darf."""
    window: Any = None                       # Hauptfenster (nur im GUI-Thread benutzen)
    connection: Any = None
    level: int = LEVEL_DESCRIBE              # wirksame Stufe für die Quelle der Funktion
    in_gui: Callable[[Callable[[], Any]], Any] = lambda fn: fn()
    stop: threading.Event = field(default_factory=threading.Event)


_registry: dict[str, Function] = {}
_lock = threading.Lock()


def register(fn: Function) -> None:
    with _lock:
        _registry[fn.name] = fn


def unregister_source(source: str) -> None:
    with _lock:
        for name in [n for n, f in _registry.items() if f.source == source]:
            del _registry[name]


def unregister_owner(owner: Any) -> None:
    with _lock:
        for name in [n for n, f in _registry.items() if f.owner is owner]:
            del _registry[name]


def get(name: str) -> Function | None:
    return _registry.get(name)


def all_functions() -> list[Function]:
    with _lock:
        return list(_registry.values())


def available(level_for: Callable[[str], int], supports_change: bool = True) -> list[Function]:
    """Funktionen, die bei den aktuellen Zugriffsstufen erlaubt sind."""
    out = []
    for fn in all_functions():
        lvl = level_for(fn.source)
        if lvl >= fn.level and (supports_change or fn.level < LEVEL_CHANGE):
            out.append(fn)
    return out


def format_result(value: Any) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, indent=1, default=str)
        except (TypeError, ValueError):
            text = str(value)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "\n… (gekürzt)"
    return text

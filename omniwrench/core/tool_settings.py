"""Speicher für tool-spezifische Einstellungen.

Normale Werte landen in tool_settings/<tool-id>.json, Werte vom Typ
"secret" und "credential" ausschließlich verschlüsselt im Tresor.
"""

from __future__ import annotations

from typing import Any, Callable

from .jsonio import read_json, write_json
from .manifest import SettingDef
from .paths import TOOL_SETTINGS_DIR
from .vault import Vault


class ToolSettingsStore:
    def __init__(self, tool_id: str, schema: list[SettingDef], vault: Vault):
        self.tool_id = tool_id
        self.schema = schema
        self._defs = {s.key: s for s in schema}
        self._vault = vault
        self._file = TOOL_SETTINGS_DIR / f"{tool_id}.json"
        self._values: dict[str, Any] = read_json(self._file, default={}) or {}
        self._listeners: list[Callable[[set[str]], None]] = []

    def _vault_key(self, key: str) -> str:
        return f"tool:{self.tool_id}:{key}"

    def get(self, key: str, default: Any = None) -> Any:
        sdef = self._defs.get(key)
        if sdef and sdef.is_secret:
            value = self._vault.get(self._vault_key(key)) if self._vault.is_unlocked else None
        else:
            value = self._values.get(key)
        if value is None:
            return sdef.default if sdef and sdef.default is not None else default
        return value

    def all(self) -> dict[str, Any]:
        return {s.key: self.get(s.key) for s in self.schema}

    def set(self, key: str, value: Any) -> None:
        self.update({key: value})

    def update(self, values: dict[str, Any]) -> None:
        changed: set[str] = set()
        for key, value in values.items():
            if self.get(key) == value:
                continue
            sdef = self._defs.get(key)
            if sdef and sdef.is_secret:
                self._vault.set(self._vault_key(key), value if value not in ("", {}) else None)
            else:
                self._values[key] = value
            changed.add(key)
        if changed:
            write_json(self._file, self._values)
            for cb in list(self._listeners):
                cb(changed)

    def on_change(self, callback: Callable[[set[str]], None]) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[set[str]], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def delete_all(self) -> None:
        """Entfernt alle gespeicherten Einstellungen und Geheimnisse des Tools."""
        self._values = {}
        if self._file.exists():
            self._file.unlink()
        if self._vault.is_unlocked:
            self._vault.delete_prefix(f"tool:{self.tool_id}:")

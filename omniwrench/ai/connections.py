"""Eingerichtete KI-Verbindungen.

Einstellungen ("ai_connections", ohne Geheimnisse):
    {"id", "name", "provider", "auth", "base_url", "model", "models": [...],
     "key_ref": "<anbieter>:<id>"         API-Schlüssel aus dem Passwortmanager (Passwortfeld)
     "oauth": {"client_id", "auth_url", "token_url", "scopes"}   eigenes OAuth
     "entra": {"tenant", "client_id"}                            Microsoft Entra ID
     "created"}

Geheimnisse im Tresor unter "app:ai:<id>":
    {"api_key"} oder {"access_token", "refresh_token", "expires_at", "client_id", "account"}

"ai_primary" ist die ID des Hauptassistenten (Standard für neue Chats und das Kontextmenü).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from omniwrench.core import credentials

from . import providers
from .http import AIError

SETTINGS_KEY = "ai_connections"
PRIMARY_KEY = "ai_primary"
SECRET_PREFIX = "app:ai:conn:"


@dataclass
class Connection:
    id: str
    name: str
    provider: str
    auth: str = providers.AUTH_API_KEY
    base_url: str = ""
    model: str = ""
    models: list[str] = field(default_factory=list)
    key_ref: str = ""
    oauth: dict = field(default_factory=dict)
    entra: dict = field(default_factory=dict)
    created: int = field(default_factory=lambda: int(time.time()))

    @classmethod
    def from_dict(cls, data: dict) -> "Connection":
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def info(self) -> providers.Provider | None:
        return providers.get(self.provider)

    @property
    def url(self) -> str:
        info = self.info
        return (self.base_url or (info.base_url if info else "")).rstrip("/")

    @property
    def api(self) -> str:
        info = self.info
        return info.api if info else "openai"

    def has(self, capability: str) -> bool:
        info = self.info
        return bool(info and info.has(capability))


class ConnectionStore:
    def __init__(self, settings, vault):
        self.settings = settings
        self.vault = vault

    # --------------------------------------------------------- Verbindungen
    def list(self) -> list[Connection]:
        out = []
        for raw in self.settings.get(SETTINGS_KEY, []) or []:
            if isinstance(raw, dict) and raw.get("id"):
                out.append(Connection.from_dict(raw))
        return out

    def chat_connections(self) -> list[Connection]:
        return [c for c in self.list() if c.info is None or c.info.can_chat]

    def get(self, conn_id: str) -> Connection | None:
        return next((c for c in self.list() if c.id == conn_id), None)

    def new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def save(self, conn: Connection) -> None:
        items = [c.to_dict() for c in self.list()]
        for i, item in enumerate(items):
            if item["id"] == conn.id:
                items[i] = conn.to_dict()
                break
        else:
            items.append(conn.to_dict())
        self.settings.set(SETTINGS_KEY, items)
        if not self.primary_id():
            self.settings.set(PRIMARY_KEY, conn.id)

    def remove(self, conn_id: str) -> None:
        items = [c.to_dict() for c in self.list() if c.id != conn_id]
        self.settings.set(SETTINGS_KEY, items)
        self.vault.delete(SECRET_PREFIX + conn_id)
        if self.settings.get(PRIMARY_KEY) == conn_id:
            self.settings.set(PRIMARY_KEY, items[0]["id"] if items else "")

    def move(self, conn_id: str, delta: int) -> None:
        items = [c.to_dict() for c in self.list()]
        idx = next((i for i, c in enumerate(items) if c["id"] == conn_id), -1)
        new = idx + delta
        if idx < 0 or not 0 <= new < len(items):
            return
        items[idx], items[new] = items[new], items[idx]
        self.settings.set(SETTINGS_KEY, items)

    def primary_id(self) -> str:
        pid = self.settings.get(PRIMARY_KEY, "") or ""
        ids = [c.id for c in self.list()]
        if pid in ids:
            return pid
        return ids[0] if ids else ""

    def primary(self) -> Connection | None:
        pid = self.primary_id()
        return self.get(pid) if pid else None

    def set_primary(self, conn_id: str) -> None:
        self.settings.set(PRIMARY_KEY, conn_id)

    def unique_name(self, base: str, exclude: str = "") -> str:
        names = {c.name.lower() for c in self.list() if c.id != exclude}
        if base.lower() not in names:
            return base
        n = 2
        while f"{base} ({n})".lower() in names:
            n += 1
        return f"{base} ({n})"

    # ------------------------------------------------------------ Geheimnisse
    def secrets(self, conn_id: str) -> dict:
        return dict(self.vault.get(SECRET_PREFIX + conn_id) or {})

    def set_secrets(self, conn_id: str, values: dict) -> None:
        if values:
            self.vault.set(SECRET_PREFIX + conn_id, values)
        else:
            self.vault.delete(SECRET_PREFIX + conn_id)

    def update_secrets(self, conn_id: str, **values: Any) -> None:
        data = self.secrets(conn_id)
        data.update(values)
        self.set_secrets(conn_id, data)

    def api_key(self, conn: Connection, interactive: bool = True) -> str:
        """API-Schlüssel aus dem Tresor oder (bei key_ref) aus dem Passwortmanager. Darf im Hintergrund laufen."""
        if conn.key_ref:
            cred = credentials.manager().resolve(conn.key_ref, interactive=interactive)
            if not cred or not cred.password:
                raise AIError("missing key", "auth", code="missing_key")
            return cred.password
        key = self.secrets(conn.id).get("api_key", "")
        if not key:
            raise AIError("missing key", "auth", code="missing_key")
        return key

    def is_signed_in(self, conn: Connection) -> bool:
        if conn.auth == providers.AUTH_NONE:
            return True
        if conn.auth in providers.OAUTH_KINDS and conn.auth != providers.AUTH_OPENROUTER:
            return bool(self.secrets(conn.id).get("refresh_token") or self.secrets(conn.id).get("access_token"))
        return bool(conn.key_ref or self.secrets(conn.id).get("api_key"))

"""Anbieterkatalog der KI-Assistenten.

Mitgeliefert: resources/ai/providers.json. Neuere Fassungen kommen über den Store
(<repository>/ai/providers.json) und landen im Cache; es gilt die Fassung mit dem neuesten
"updated". Anbieter werden nie gelöscht, sondern mit status "removed" markiert: In der Liste
erscheinen sie rot, beim Benutzen gibt es einen Hinweis (status_note).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from omniwrench.core import net
from omniwrench.core.jsonio import read_json, write_json
from omniwrench.core.paths import CACHE_DIR, RESOURCES_DIR

log = logging.getLogger(__name__)

BUNDLED_FILE = RESOURCES_DIR / "ai" / "providers.json"
CACHE_FILE = CACHE_DIR / "ai" / "providers.json"
STORE_PATH = "ai/providers.json"

# Anmeldearten
AUTH_API_KEY = "api_key"
AUTH_NONE = "none"
AUTH_CHATGPT = "oauth_chatgpt"
AUTH_OPENROUTER = "oauth_openrouter"
AUTH_ENTRA = "entra"
AUTH_CUSTOM = "oauth_custom"
OAUTH_KINDS = (AUTH_CHATGPT, AUTH_OPENROUTER, AUTH_ENTRA, AUTH_CUSTOM)

CHAT_APIS = ("openai", "openai_responses", "anthropic", "graph_copilot")


@dataclass
class Provider:
    id: str
    name: str
    api: str
    base_url: str = ""
    vendor: str = ""
    country: str = ""
    categories: list[str] = field(default_factory=list)
    auth: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    key_url: str = ""
    docs_url: str = ""
    status: str = "active"
    status_note: str = ""
    note: str = ""
    recommended: bool = False
    media: dict = field(default_factory=dict)
    key_header: str = ""
    key_prefix: str = ""
    base_url_editable: bool = False
    list_models: bool = False
    models_url: str = ""                            # eigene Adresse der Modellliste (Standard: <base_url>/models)
    requires: dict = field(default_factory=dict)   # Anmeldeart (oder "*") -> Schlüssel ai.req.<…>
    model_tags: dict = field(default_factory=dict)  # Modell -> Merkmale (ai.models.TAGS), sonst aus dem Namen
    nsfw: bool = False                              # kann Inhalte für Erwachsene erzeugen (je nach Modell)

    @classmethod
    def from_dict(cls, data: dict) -> "Provider":
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in known})

    def requirement(self, auth: str) -> str:
        """Was man für diese Anmeldeart braucht (Abo, API-Konto, Lizenz …) als Schlüssel für ai.req.<…>."""
        if auth in self.requires or "*" in self.requires:
            return self.requires.get(auth, self.requires.get("*", ""))
        if auth == AUTH_NONE or "local" in self.categories:
            return "local"
        if auth == AUTH_ENTRA:
            return "m365_license"
        if auth == AUTH_CUSTOM or "custom" in self.categories:
            return ""
        if "enterprise" in self.categories:
            return "cloud_contract"
        return "api_paid"

    @property
    def removed(self) -> bool:
        return self.status == "removed"

    @property
    def available(self) -> bool:
        return self.status == "active" and bool(self.auth)

    @property
    def can_chat(self) -> bool:
        return self.api in CHAT_APIS

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


_catalog: dict | None = None
_providers: dict[str, Provider] = {}


def _newer(a: dict | None, b: dict | None) -> dict | None:
    if not a:
        return b
    if not b:
        return a
    return b if str(b.get("updated", "")) > str(a.get("updated", "")) else a


def _load() -> None:
    global _catalog, _providers
    bundled = read_json(BUNDLED_FILE, default=None)
    try:
        cached = read_json(CACHE_FILE, default=None)
    except ValueError:
        cached = None
    _catalog = _newer(bundled, cached) or {"format": 1, "categories": [], "providers": []}
    # Anbieter aus der mitgelieferten Fassung, die in einer neueren fehlen, bleiben erhalten
    ids = {p.get("id") for p in _catalog.get("providers", [])}
    extra = [p for p in (bundled or {}).get("providers", []) if p.get("id") not in ids]
    _providers = {}
    for raw in list(_catalog.get("providers", [])) + extra:
        try:
            p = Provider.from_dict(raw)
        except TypeError:
            continue
        _providers[p.id] = p


def catalog() -> dict:
    if _catalog is None:
        _load()
    return _catalog or {}


def all_providers() -> list[Provider]:
    if _catalog is None:
        _load()
    return list(_providers.values())


def get(provider_id: str) -> Provider | None:
    if _catalog is None:
        _load()
    return _providers.get(provider_id)


def categories() -> list[str]:
    return list(catalog().get("categories", []))


def updated() -> str:
    return str(catalog().get("updated", ""))


def update_from_store(repo_urls: list[str]) -> bool:
    """Lädt providers.json aus den Store-Repositories. True, wenn sich der Katalog geändert hat."""
    best = None
    for url in repo_urls:
        try:
            data = json.loads(net.get_bytes(net.resolve(url, STORE_PATH), timeout=15))
        except Exception as err:  # Store ohne Anbieterliste oder offline
            log.debug("Anbieterliste aus %s nicht geladen: %s", url, err)
            continue
        if isinstance(data, dict) and isinstance(data.get("providers"), list):
            best = _newer(best, data)
    if not best or str(best.get("updated", "")) <= updated():
        return False
    write_json(CACHE_FILE, best)
    _load()
    return True


def reload() -> None:
    _load()


def to_json(provider: Provider) -> dict[str, Any]:
    return {k: getattr(provider, k) for k in Provider.__dataclass_fields__}

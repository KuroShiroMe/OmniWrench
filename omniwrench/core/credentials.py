"""Passwortmanager: Zugangsdaten aus einem oder mehreren Anbietern ("Providern").

* LocalProvider  - eingebauter Manager, Einträge verschlüsselt im Tresor
* weitere Anbieter registrieren Tools (z. B. "Password Manager Manager": SecretManagement,
  KeePass, Netwrix …) über ToolContext.register_credential_provider()

Regeln:
* Gesucht wird per Volltext über alle Anbieter (search()).
* Tools speichern nur Verweise ("<anbieter>:<id>"), niemals Passwörter externer Anbieter.
* Geheimnisse werden beim ersten Gebrauch abgerufen und nur im Speicher gehalten
  (Sitzungs-Cache). Beim Sperren/Beenden sind sie weg.
* Schlägt die Anmeldung an einem Anbieter fehl, wirft er AuthenticationRequired. Das UI
  (auth_handler) fragt dann nach den Zugangsdaten und versucht es erneut - keine Fehlermeldung.
"""

from __future__ import annotations

import logging
import secrets
import string
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Callable

from .vault import Vault

log = logging.getLogger(__name__)


class AuthenticationRequired(Exception):
    """Anbieter braucht (neue) Zugangsdaten - z. B. weil sich das Passwort geändert hat."""

    def __init__(self, provider: "CredentialProvider", message: str = ""):
        super().__init__(message or provider.name)
        self.provider = provider


@dataclass
class Credential:
    id: str
    name: str
    username: str
    password: str = ""
    provider: str = "local"
    source: str = ""                 # Anzeigename des Anbieters
    changed: int = field(default_factory=lambda: int(time.time()))

    @property
    def ref(self) -> str:
        """Verweis, der in Tool-Einstellungen gespeichert wird ("<anbieter>:<id>")."""
        return f"{self.provider}:{self.id}"


@dataclass
class AuthField:
    key: str
    label: str
    secret: bool = False


class CredentialProvider:
    """Schnittstelle für Quellen von Zugangsdaten.

    Pflicht: search(). get_secret() liefert den Eintrag inkl. Passwort (bei externen
    Anbietern erst hier abgerufen). Für Anmelde-Rückfragen: auth_fields() + set_auth().
    """

    id = "base"
    name = "Base"
    writable = False

    def search(self, query: str) -> list[Credential]:
        raise NotImplementedError

    def get_secret(self, cred_id: str) -> Credential | None:
        raise NotImplementedError

    def auth_fields(self) -> list[AuthField]:
        """Felder, nach denen bei AuthenticationRequired gefragt wird (leer = keine Rückfrage möglich)."""
        return []

    def set_auth(self, values: dict[str, str], save: bool) -> None:
        """Neue Zugangsdaten übernehmen; save=True speichert sie dauerhaft (Tresor)."""

    def close(self) -> None:
        """Aufräumen (offene Datenbanken, Sitzungen) beim Abmelden des Anbieters."""


class LocalProvider(CredentialProvider):
    """Eingebauter Passwortmanager - Einträge liegen verschlüsselt im Tresor."""

    id = "local"
    name = "OmniWrench"
    writable = True
    VAULT_KEY = "app:credentials"

    def __init__(self, vault: Vault):
        self.vault = vault

    def _load(self) -> dict[str, dict]:
        return dict(self.vault.get(self.VAULT_KEY, {}) or {})

    def _save(self, data: dict[str, dict]) -> None:
        self.vault.set(self.VAULT_KEY, data)

    def _make(self, raw: dict) -> Credential:
        cred = Credential(**{k: v for k, v in raw.items() if k in Credential.__dataclass_fields__})
        cred.source = self.name
        return cred

    def list(self) -> list[Credential]:
        return sorted((self._make(v) for v in self._load().values()), key=lambda c: c.name.lower())

    def search(self, query: str) -> list[Credential]:
        q = query.strip().lower()
        return [c for c in self.list() if q in f"{c.name} {c.username}".lower()]

    def get(self, cred_id: str) -> Credential | None:
        raw = self._load().get(cred_id)
        return self._make(raw) if raw else None

    get_secret = get

    def add(self, name: str, username: str, password: str) -> Credential:
        cred = Credential(uuid.uuid4().hex[:12], name.strip(), username.strip(), password, source=self.name)
        data = self._load()
        data[cred.id] = asdict(cred)
        self._save(data)
        return cred

    def update(self, cred: Credential) -> None:
        cred.changed = int(time.time())
        data = self._load()
        data[cred.id] = asdict(cred)
        self._save(data)
        manager().forget(cred.ref)

    def delete(self, cred_id: str) -> None:
        data = self._load()
        data.pop(cred_id, None)
        self._save(data)
        manager().forget(f"{self.id}:{cred_id}")


@dataclass
class SearchResult:
    items: list[Credential]
    errors: dict[str, str]                       # Anbieter-Name -> Fehlertext
    auth_needed: list[CredentialProvider]        # Anbieter, die Zugangsdaten brauchen


class CredentialManager:
    """Fasst alle Anbieter zusammen, sucht, löst Verweise auf, hält den Sitzungs-Cache."""

    MAX_AUTH_ATTEMPTS = 3

    def __init__(self, vault: Vault):
        self.local = LocalProvider(vault)
        self.providers: list[CredentialProvider] = [self.local]
        self._owners: dict[str, str] = {}             # provider-id -> tool-id
        self._cache: dict[str, Credential] = {}       # nur im Speicher!
        # Vom UI gesetzt: fragt nach Zugangsdaten, liefert True wenn neu eingegeben
        self.auth_handler: Callable[[CredentialProvider], bool] | None = None

    # ------------------------------------------------------------ Anbieter
    def register(self, provider: CredentialProvider, owner: str = "") -> None:
        self.unregister(provider.id)
        self.providers.append(provider)
        if owner:
            self._owners[provider.id] = owner
        log.info("Anbieter registriert: %s (%s)", provider.name, provider.id)

    def unregister(self, provider_id: str) -> None:
        for p in [p for p in self.providers if p.id == provider_id and p is not self.local]:
            try:
                p.close()
            except Exception:  # noqa: BLE001
                log.exception("close() von %s fehlgeschlagen", p.id)
            self.providers.remove(p)
        self._owners.pop(provider_id, None)
        self._cache = {k: v for k, v in self._cache.items() if not k.startswith(provider_id + ":")}

    def unregister_owner(self, tool_id: str) -> None:
        for pid in [pid for pid, owner in self._owners.items() if owner == tool_id]:
            self.unregister(pid)

    def provider(self, provider_id: str) -> CredentialProvider | None:
        return next((p for p in self.providers if p.id == provider_id), None)

    # ---------------------------------------------------------------- Suche
    def all(self) -> list[Credential]:
        return self.local.list()

    def search(self, query: str, providers: list[CredentialProvider] | None = None) -> SearchResult:
        """Volltextsuche über alle (oder die angegebenen) Anbieter. Fehler blockieren nichts."""
        result = SearchResult([], {}, [])
        for p in providers or list(self.providers):
            try:
                for c in p.search(query):
                    c.provider, c.source = p.id, c.source or p.name
                    result.items.append(c)
            except AuthenticationRequired:
                result.auth_needed.append(p)
            except Exception as exc:  # noqa: BLE001
                result.errors[p.name] = str(exc)
                log.warning("Suche in %s fehlgeschlagen: %s", p.name, exc)
        return result

    # ------------------------------------------------------------ Auflösen
    def resolve(self, ref: str, interactive: bool = True) -> Credential | None:
        """Liefert den Eintrag inkl. Passwort. Externe Anbieter werden einmal pro Sitzung abgefragt."""
        if not ref:
            return None
        if ref in self._cache:
            return self._cache[ref]
        provider_id, _, cred_id = ref.partition(":")
        provider = self.provider(provider_id)
        if provider is None:
            return None
        for _ in range(self.MAX_AUTH_ATTEMPTS):
            try:
                cred = provider.get_secret(cred_id)
            except AuthenticationRequired:
                if interactive and self.auth_handler and self.auth_handler(provider):
                    continue  # neue Zugangsdaten eingegeben -> erneut versuchen
                return None
            if cred is None:
                return None
            cred.provider, cred.source = provider.id, cred.source or provider.name
            if provider is not self.local:
                self._cache[ref] = cred
            return cred
        return None

    def forget(self, ref: str) -> None:
        self._cache.pop(ref, None)

    def clear_session(self) -> None:
        """Beim Sperren: alle abgerufenen Geheimnisse aus dem Speicher entfernen."""
        self._cache.clear()


def generate_password(length: int = 20) -> str:
    """Zufallspasswort mit Groß-/Kleinbuchstaben, Ziffern und Sonderzeichen."""
    alphabet = string.ascii_letters + string.digits + "!#$%&*+-=?@_"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw)):
            return pw


# ------------------------------------------------- Werte von "credential"-Feldern
def normalize_value(value: dict | None) -> dict:
    """Einheitliches Format für Einstellungen vom Typ "credential":

        {"items": [ {"name", "username", "ref"}            # Verweis (Passwort NICHT gespeichert)
                  | {"name", "username", "password"} ],   # manuell eingegeben
         "selected": <index>}

    Ältere Werte ({"username", "password"[, "ref"]}) werden umgewandelt.
    """
    value = value or {}
    if "items" in value:
        items = [dict(i) for i in value.get("items") or []]
        sel = int(value.get("selected", 0) or 0)
        return {"items": items, "selected": min(max(sel, 0), max(len(items) - 1, 0))}
    if value.get("username") or value.get("ref"):
        item = {"name": value.get("username", ""), "username": value.get("username", "")}
        if value.get("ref"):
            item["ref"] = value["ref"]
        else:
            item["password"] = value.get("password", "")
        return {"items": [item], "selected": 0}
    return {"items": [], "selected": 0}


def resolve_item(item: dict, interactive: bool = True) -> tuple[str, str] | None:
    """(Benutzer, Passwort) eines Eintrags aus einem credential-Feld."""
    if item.get("ref"):
        cred = manager().resolve(item["ref"], interactive=interactive)
        return (cred.username, cred.password) if cred else None
    if item.get("username"):
        return item.get("username", ""), item.get("password", "")
    return None


_manager: CredentialManager | None = None


def init(vault: Vault) -> CredentialManager:
    global _manager
    _manager = CredentialManager(vault)
    return _manager


def manager() -> CredentialManager:
    if _manager is None:
        raise RuntimeError("Passwortmanager nicht initialisiert")
    return _manager

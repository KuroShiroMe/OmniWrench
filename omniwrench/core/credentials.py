"""Passwortmanager: Zugangsdaten (Name, Benutzer, Passwort), verschlüsselt im Tresor.

Aufbau mit Anbietern ("Providern"): Der eingebaute Anbieter speichert im eigenen Tresor.
Später können weitere Anbieter (Bitwarden, KeePassXC, 1Password …) dieselbe Schnittstelle
implementieren und werden dann im Auswahldialog mit angezeigt.

Tools nutzen das nicht direkt, sondern über:
    * Einstellungen vom Typ "credential" (mit Button "Aus Passwortmanager")
    * ToolContext.get_credential(key)       -> (benutzer, passwort), Verknüpfungen werden aufgelöst
    * omniwrench.sdk.pick_credential(parent) -> Auswahldialog im eigenen Tool-GUI
"""

from __future__ import annotations

import secrets
import string
import time
import uuid
from dataclasses import asdict, dataclass, field

from .vault import Vault


@dataclass
class Credential:
    id: str
    name: str
    username: str
    password: str
    provider: str = "local"
    changed: int = field(default_factory=lambda: int(time.time()))

    @property
    def ref(self) -> str:
        """Verweis, der in Tool-Einstellungen gespeichert wird ("<anbieter>:<id>")."""
        return f"{self.provider}:{self.id}"


class CredentialProvider:
    """Schnittstelle für Quellen von Zugangsdaten."""

    id = "base"
    name = "Base"
    writable = False

    def list(self) -> list[Credential]:
        raise NotImplementedError

    def get(self, cred_id: str) -> Credential | None:
        return next((c for c in self.list() if c.id == cred_id), None)


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

    def list(self) -> list[Credential]:
        return sorted((Credential(**v) for v in self._load().values()), key=lambda c: c.name.lower())

    def get(self, cred_id: str) -> Credential | None:
        raw = self._load().get(cred_id)
        return Credential(**raw) if raw else None

    def add(self, name: str, username: str, password: str) -> Credential:
        cred = Credential(uuid.uuid4().hex[:12], name.strip(), username.strip(), password)
        data = self._load()
        data[cred.id] = asdict(cred)
        self._save(data)
        return cred

    def update(self, cred: Credential) -> None:
        cred.changed = int(time.time())
        data = self._load()
        data[cred.id] = asdict(cred)
        self._save(data)

    def delete(self, cred_id: str) -> None:
        data = self._load()
        data.pop(cred_id, None)
        self._save(data)


class CredentialManager:
    """Fasst alle Anbieter zusammen und löst Verweise auf."""

    def __init__(self, vault: Vault):
        self.local = LocalProvider(vault)
        self.providers: list[CredentialProvider] = [self.local]

    def all(self) -> list[Credential]:
        result: list[Credential] = []
        for provider in self.providers:
            try:
                result.extend(provider.list())
            except Exception:  # noqa: BLE001 - ein defekter Anbieter darf die Liste nicht blockieren
                continue
        return result

    def resolve(self, ref: str) -> Credential | None:
        provider_id, _, cred_id = (ref or "").partition(":")
        provider = next((p for p in self.providers if p.id == provider_id), None)
        return provider.get(cred_id) if provider else None


def generate_password(length: int = 20) -> str:
    """Zufallspasswort mit Groß-/Kleinbuchstaben, Ziffern und Sonderzeichen."""
    alphabet = string.ascii_letters + string.digits + "!#$%&*+-=?@_"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw)):
            return pw


_manager: CredentialManager | None = None


def init(vault: Vault) -> CredentialManager:
    global _manager
    _manager = CredentialManager(vault)
    return _manager


def manager() -> CredentialManager:
    if _manager is None:
        raise RuntimeError("Passwortmanager nicht initialisiert")
    return _manager

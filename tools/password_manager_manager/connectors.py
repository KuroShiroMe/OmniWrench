"""Konnektoren zu externen Passwortmanagern.

Die Typen (Felder, Skripte, Voraussetzungen) stehen in connector_types.json.
Jeder angelegte Konnektor wird als Anbieter (CredentialProvider) im Hauptprogramm
registriert - damit durchsucht der Auswahldialog "Aus Passwortmanager" auch ihn.

Gespeichert wird:
    Tool-Einstellung "connectors": [{id, type, name, enabled, save_auth, values: {nicht geheime Felder}}]
    Tresor (ctx.secrets) "conn:<id>": {geheime Felder}   - nur wenn save_auth
Geheime Felder ohne save_auth gelten nur für die laufende Sitzung.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from omniwrench.sdk import AuthenticationRequired, AuthField, Credential, CredentialProvider, ToolContext

TYPES_FILE = Path(__file__).with_name("connector_types.json")
PROVIDER_PREFIX = "pmm-"
SETTINGS_KEY = "connectors"

# Sitzungs-Speicher für nicht gespeicherte Anmeldedaten (nur im Speicher, pro Konnektor-ID)
_session_auth: dict[str, dict[str, str]] = {}


def load_types() -> dict[str, dict]:
    return json.loads(TYPES_FILE.read_text(encoding="utf-8"))["types"]


def text(value, language: str) -> str:
    """Mehrsprachige Angabe aus der JSON ({"en":…, "de":…} oder Text)."""
    if isinstance(value, dict):
        base = language.split("_")[0]
        return value.get(language) or value.get(base) or value.get("en") or next(iter(value.values()), "")
    return value or ""


def is_secret(f: dict) -> bool:
    return f.get("type") == "secret" or bool(f.get("secret"))


@dataclass
class ConnectorConfig:
    id: str
    type: str
    name: str
    enabled: bool = True
    save_auth: bool = True
    values: dict = field(default_factory=dict)

    @property
    def provider_id(self) -> str:
        return PROVIDER_PREFIX + self.id


class ConnectorStore:
    """Liest/schreibt die Konnektoren eines Benutzers."""

    def __init__(self, ctx: ToolContext):
        self.ctx = ctx
        self.types = load_types()

    def all(self) -> list[ConnectorConfig]:
        return [ConnectorConfig(**c) for c in self.ctx.settings.get(SETTINGS_KEY, []) or []
                if c.get("type") in self.types]

    def get(self, conn_id: str) -> ConnectorConfig | None:
        return next((c for c in self.all() if c.id == conn_id), None)

    def save(self, conn: ConnectorConfig, secrets: dict[str, str] | None = None) -> None:
        items = [c for c in self.all() if c.id != conn.id] + [conn]
        self.ctx.settings.set(SETTINGS_KEY, [c.__dict__ for c in items])
        if secrets is not None:
            self.set_secrets(conn, secrets)

    def delete(self, conn_id: str) -> None:
        self.ctx.settings.set(SETTINGS_KEY, [c.__dict__ for c in self.all() if c.id != conn_id])
        self.ctx.secrets.delete(f"conn:{conn_id}")
        _session_auth.pop(conn_id, None)

    def new(self, type_id: str, name: str) -> ConnectorConfig:
        return ConnectorConfig(uuid.uuid4().hex[:10], type_id, name)

    # Geheimnisse: Tresor (gespeichert) bzw. Sitzung
    def secrets(self, conn: ConnectorConfig) -> dict[str, str]:
        stored = (self.ctx.secrets.get(f"conn:{conn.id}") or {}) if conn.save_auth else {}
        return {**stored, **_session_auth.get(conn.id, {})}

    def set_secrets(self, conn: ConnectorConfig, values: dict[str, str], save: bool | None = None) -> None:
        save = conn.save_auth if save is None else save
        _session_auth[conn.id] = {**_session_auth.get(conn.id, {}), **values}
        if save:
            stored = self.ctx.secrets.get(f"conn:{conn.id}") or {}
            self.ctx.secrets.set(f"conn:{conn.id}", {**stored, **values})
        else:
            self.ctx.secrets.delete(f"conn:{conn.id}")

    def all_values(self, conn: ConnectorConfig) -> dict[str, str]:
        return {**conn.values, **self.secrets(conn)}


# ===================================================================== Anbieter
class ConnectorProvider(CredentialProvider):
    def __init__(self, conn: ConnectorConfig, store: ConnectorStore):
        self.conn = conn
        self.store = store
        self.spec = store.types[conn.type]
        self.id = conn.provider_id
        self.name = conn.name
        self.max_results = int(store.ctx.settings.get("max_results", 100) or 100)

    @property
    def values(self) -> dict[str, str]:
        return self.store.all_values(self.conn)

    def auth_fields(self) -> list[AuthField]:
        lang = self.store.ctx.language
        return [AuthField(f["key"], text(f["label"], lang), is_secret(f))
                for f in self.spec["fields"] if f.get("auth")]

    def set_auth(self, values: dict[str, str], save: bool) -> None:
        secret_keys = {f["key"] for f in self.spec["fields"] if is_secret(f)}
        secret_part = {k: v for k, v in values.items() if k in secret_keys}
        plain_part = {k: v for k, v in values.items() if k not in secret_keys}
        if plain_part:  # z. B. Benutzername: normale Konfiguration
            self.conn.values.update(plain_part)
        if save != self.conn.save_auth:
            self.conn.save_auth = save
        self.store.save(self.conn)
        self.store.set_secrets(self.conn, secret_part, save)
        self.on_auth_changed()

    def on_auth_changed(self) -> None:
        """Nach neuen Anmeldedaten (z. B. geöffnete Datenbank verwerfen)."""

    def _missing_auth(self) -> bool:
        vals = self.values
        return any(f.get("auth") and is_secret(f) and not vals.get(f["key"]) for f in self.spec["fields"]
                   if f.get("required", True))

    def test(self) -> str:
        """Verbindungstest: liefert eine kurze Erfolgsmeldung oder wirft eine Exception."""
        return str(len(self.search("")))


class PowerShellConnector(ConnectorProvider):
    """Konnektor, dessen Logik vollständig als PowerShell-Skripte in der JSON steht."""

    def _run(self, action: str, **extra):
        scripts = self.spec["scripts"]
        script = "\n".join(scripts.get("prologue", []) + scripts[action])
        payload = json.dumps({**self.values, "max": self.max_results, **extra})
        result = self.store.ctx.run_powershell(script, stdin=payload, timeout=120)
        if not result.ok:
            message = result.stderr or result.stdout or "PowerShell error"
            if any(re.search(p, message) for p in self.spec.get("auth_error_patterns", [])):
                raise AuthenticationRequired(self, message)
            raise RuntimeError(message.strip().splitlines()[0] if message.strip() else message)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def search(self, query: str) -> list[Credential]:
        rows = self._run("search", query=query) or []
        return [Credential(str(r.get("id")), r.get("name") or "", r.get("username") or "",
                           source=f"{self.name} · {r['detail']}" if r.get("detail") else self.name)
                for r in rows]

    def get_secret(self, cred_id: str) -> Credential | None:
        data = self._run("get", id=cred_id)
        if not data:
            return None
        return Credential(cred_id, cred_id.split("|")[-1], data.get("username") or "", data.get("password") or "")


class KeePassConnector(ConnectorProvider):
    """KeePass-Datenbank direkt über pykeepass (kein KeePass-Programm nötig)."""

    def __init__(self, *args):
        super().__init__(*args)
        self._db = None
        self._mtime = 0.0

    def on_auth_changed(self) -> None:
        self._db = None

    def close(self) -> None:
        self._db = None

    def _open(self):
        path = Path(self.values.get("database", ""))
        if not path.is_file():
            raise RuntimeError(self.store.ctx.tr("err.db_missing", path=path))
        mtime = path.stat().st_mtime
        if self._db is not None and mtime == self._mtime:
            return self._db
        from pykeepass import PyKeePass
        from pykeepass.exceptions import CredentialsError
        password = self.values.get("password") or None
        key_file = self.values.get("key_file") or None
        if not password and not key_file:
            raise AuthenticationRequired(self)
        try:
            self._db = PyKeePass(str(path), password=password, keyfile=key_file)
        except CredentialsError:
            raise AuthenticationRequired(self) from None
        self._mtime = mtime
        return self._db

    @staticmethod
    def _group_path(entry) -> str:
        try:
            return "/".join(g for g in entry.group.path if g)
        except Exception:  # noqa: BLE001
            return ""

    def search(self, query: str) -> list[Credential]:
        q = query.strip().lower()
        result = []
        for e in self._open().entries:
            hay = " ".join(filter(None, [e.title, e.username, e.url, e.notes])).lower()
            if q in hay:
                group = self._group_path(e)
                result.append(Credential(e.uuid.hex, e.title or "", e.username or "",
                                         source=f"{self.name} · {group}" if group else self.name))
                if len(result) >= self.max_results:
                    break
        return result

    def get_secret(self, cred_id: str) -> Credential | None:
        entry = self._open().find_entries(uuid=uuid.UUID(cred_id), first=True)
        if entry is None:
            return None
        return Credential(cred_id, entry.title or "", entry.username or "", entry.password or "")


IMPLEMENTATIONS = {"powershell": PowerShellConnector, "keepass": KeePassConnector}


def make_provider(conn: ConnectorConfig, store: ConnectorStore) -> ConnectorProvider:
    return IMPLEMENTATIONS[store.types[conn.type]["implementation"]](conn, store)


def register_all(ctx: ToolContext) -> None:
    """Startup-Hook: alle aktiven Konnektoren beim Hauptprogramm anmelden."""
    store = ConnectorStore(ctx)
    for conn in store.all():
        if conn.enabled:
            ctx.register_credential_provider(make_provider(conn, store))
        else:
            ctx.unregister_credential_provider(conn.provider_id)

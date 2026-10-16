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

import glob
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from omniwrench.sdk import AuthenticationRequired, AuthField, Credential, CredentialProvider, ToolContext

TYPES_FILE = Path(__file__).with_name("connector_types.json")
PROVIDER_PREFIX = "pmm-"
SETTINGS_KEY = "connectors"

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# Sitzungs-Speicher für nicht gespeicherte Anmeldedaten (nur im Speicher, pro Konnektor-ID)
_session_auth: dict[str, dict[str, str]] = {}
# Laufzeitzustand der Konnektoren (z. B. Bitwarden-Sitzungsschlüssel, Vault-Token) - nur im Speicher
_session_state: dict[str, dict] = {}


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


def defaults(spec: dict) -> dict:
    return {f["key"]: f["default"] for f in spec["fields"] if "default" in f}


def is_visible(f: dict, values: dict) -> bool:
    """show_if: {"auth_mode": "api_key"} oder {"auth_mode": ["userpass", "ldap"]} -> Feld nur bei passendem Wert."""
    return all(values.get(k, "") in v if isinstance(v, list) else values.get(k, "") == v
               for k, v in (f.get("show_if") or {}).items())


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
        _session_state.pop(conn_id, None)

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
        return {**defaults(self.types[conn.type]), **conn.values, **self.secrets(conn)}


# ===================================================================== Anbieter
class ConnectorProvider(CredentialProvider):
    def __init__(self, conn: ConnectorConfig, store: ConnectorStore):
        self.conn = conn
        self.store = store
        self.spec = store.types[conn.type]
        self.id = conn.provider_id
        self.name = conn.name
        self.max_results = int(store.ctx.settings.get("max_results", 100) or 100)

    values_override: dict | None = None   # Verbindungstest im Dialog: Werte nicht speichern

    @property
    def values(self) -> dict[str, str]:
        if self.values_override is not None:
            return {**defaults(self.spec), **self.values_override}
        return self.store.all_values(self.conn)

    def auth_fields(self) -> list[AuthField]:
        lang = self.store.ctx.language
        vals = self.values
        return [AuthField(f["key"], text(f["label"], lang), is_secret(f))
                for f in self.spec["fields"] if f.get("auth") and is_visible(f, vals)]

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
        self.state.clear()

    def close(self) -> None:
        self.state.clear()

    @property
    def state(self) -> dict:
        """Laufzeitzustand (Sitzungsschlüssel, Token) - nur im Speicher; beim Verbindungstest nur für diese Instanz."""
        if self.values_override is not None:
            return self.__dict__.setdefault("_test_state", {})
        return _session_state.setdefault(self.conn.id, {})

    def test(self) -> str:
        """Verbindungstest: liefert eine kurze Erfolgsmeldung oder wirft eine Exception."""
        return str(len(self.search("")))


class PowerShellConnector(ConnectorProvider):
    """Konnektor, dessen Logik vollständig als PowerShell-Skripte in der JSON steht."""

    def _run(self, action: str, **extra):
        scripts = self.spec["scripts"]
        script = "\n".join(scripts.get("prologue", []) + scripts[action])
        payload = json.dumps({**self.values, "max": self.max_results, **extra})
        shell = self.values.get("shell") or self.spec.get("shell", "powershell")
        result = self.store.ctx.run_powershell(script, stdin=payload, timeout=120, shell=shell)
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


def find_program(spec: dict, configured: str = "") -> str | None:
    """Pfad eines Kommandozeilenprogramms (requirements.program): Feld 'cli_path', PATH oder winget-Ordner.

    Nach einer winget-Installation kennt der laufende Prozess den neuen PATH noch nicht - daher
    werden auch die winget-Links und -Paketordner des Benutzers durchsucht.
    """
    if configured:
        return configured if Path(configured).is_file() else None
    program = spec.get("requirements", {}).get("program", {})
    command = program.get("command", "")
    if not command:
        return None
    found = shutil.which(command)
    if found or os.name != "nt":
        return found
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
    for candidate in [winget / "Links" / f"{command}.exe",
                      *map(Path, glob.glob(str(winget / "Packages" / "*" / f"{command}.exe")))]:
        if candidate.is_file():
            return str(candidate)
    return None


class CliConnector(ConnectorProvider):
    """Grundlage für Konnektoren, die ein Kommandozeilenprogramm (bw, op) aufrufen."""

    auth_error_patterns: list[str] = []

    def _program(self) -> str:
        exe = find_program(self.spec, self.values.get("cli_path", ""))
        if not exe:
            program = self.spec.get("requirements", {}).get("program", {})
            raise RuntimeError(self.store.ctx.tr("err.cli_missing", program=program.get("name", "?"),
                                                 url=program.get("url", "")))
        return exe

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        ca_file = self.values.get("ca_file", "")
        if ca_file:  # Firmen-Stammzertifikat (TLS-Inspection) für Node-basierte Programme
            env["NODE_EXTRA_CA_CERTS"] = ca_file
        return env

    def _cli(self, *args: str, env: dict[str, str] | None = None, timeout: float = 120) -> str:
        proc = subprocess.run([self._program(), *args], capture_output=True, timeout=timeout,
                              env=env or self._env(), stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            message = err or out or f"exit code {proc.returncode}"
            if any(re.search(p, message) for p in self.auth_error_patterns):
                raise AuthenticationRequired(self, message)
            raise RuntimeError(message.splitlines()[0])
        return out

    def _cli_json(self, *args: str, **kwargs):
        out = self._cli(*args, **kwargs)
        return json.loads(out) if out else None


class BitwardenConnector(CliConnector):
    """Bitwarden / Vaultwarden über die offizielle Bitwarden-CLI (bw).

    Jeder Konnektor nutzt einen eigenen CLI-Datenordner (BITWARDENCLI_APPDATA_DIR), damit Server und
    Anmeldung nicht mit einer eigenen bw-Nutzung kollidieren. Der Sitzungsschlüssel (BW_SESSION) liegt
    nur im Speicher; der Datenordner enthält nur den verschlüsselten Tresor-Cache der CLI.
    """

    auth_error_patterns = [r"(?i)master password", r"(?i)username or password", r"(?i)vault is locked",
                           r"(?i)client_?id", r"(?i)client_?secret", r"(?i)not logged in", r"(?i)two-step"]

    def _env(self) -> dict[str, str]:
        env = super()._env()
        data = self.store.ctx.data_dir / "bitwarden" / self.conn.id
        data.mkdir(parents=True, exist_ok=True)
        env["BITWARDENCLI_APPDATA_DIR"] = str(data)
        for key in ("BW_SESSION", "BW_CLIENTID", "BW_CLIENTSECRET", "BW_PASSWORD"):
            env.pop(key, None)
        return env

    def _session(self) -> str:
        if self.state.get("session"):
            return self.state["session"]
        v = self.values
        if not v.get("master_password"):
            raise AuthenticationRequired(self)
        status = self._cli_json("status") or {}
        server = (v.get("server") or "").strip().rstrip("/")
        current = (status.get("serverUrl") or "").rstrip("/")
        if server != current and (server or current):
            if status.get("status") != "unauthenticated":
                self._cli("logout")
            self._cli("config", "server", server or "https://vault.bitwarden.com")
            status["status"] = "unauthenticated"
        env = self._env()
        env["BW_PASSWORD"] = v["master_password"]
        if status.get("status") == "unauthenticated":
            login_env = dict(env)
            if v.get("auth_mode", "api_key") == "api_key":
                if not v.get("client_id") or not v.get("client_secret"):
                    raise AuthenticationRequired(self)
                login_env["BW_CLIENTID"] = v["client_id"]
                login_env["BW_CLIENTSECRET"] = v["client_secret"]
                self._cli("login", "--apikey", env=login_env)
            else:
                if not v.get("email"):
                    raise AuthenticationRequired(self)
                self._cli("login", v["email"], "--passwordenv", "BW_PASSWORD", env=login_env)
        session = self._cli("unlock", "--passwordenv", "BW_PASSWORD", "--raw", env=env)
        if not session:
            raise AuthenticationRequired(self)
        self.state["session"] = session
        self._cli("sync", "--session", session)  # Cache der CLI aktualisieren (einmal pro Sitzung)
        return session

    def _call(self, *args: str):
        try:
            return self._cli_json(*args, "--session", self._session())
        except AuthenticationRequired:
            if not self.state.pop("session", None):
                raise
            return self._cli_json(*args, "--session", self._session())  # Sitzung abgelaufen -> neu entsperren

    def search(self, query: str) -> list[Credential]:
        args = ["list", "items"] + (["--search", query] if query.strip() else [])
        result = []
        for item in self._call(*args) or []:
            login = item.get("login") or {}
            if item.get("type") != 1:  # nur Anmeldungen
                continue
            uri = next((u.get("uri") for u in login.get("uris") or [] if u.get("uri")), "")
            result.append(Credential(item["id"], item.get("name") or "", login.get("username") or "",
                                     source=f"{self.name} · {uri}" if uri else self.name))
            if len(result) >= self.max_results:
                break
        return result

    def get_secret(self, cred_id: str) -> Credential | None:
        item = self._call("get", "item", cred_id)
        if not item:
            return None
        login = item.get("login") or {}
        return Credential(cred_id, item.get("name") or "", login.get("username") or "", login.get("password") or "")


class OnePasswordConnector(CliConnector):
    """1Password über die offizielle 1Password-CLI (op): Dienstkonto-Token oder Desktop-App-Integration."""

    auth_error_patterns = [r"(?i)service account", r"(?i)token", r"(?i)unauthori[sz]ed", r"(?i)authenticat"]
    CATEGORIES = "Login,Password,Server,Database,API Credential"

    def _env(self) -> dict[str, str]:
        env = super()._env()
        env.pop("OP_SERVICE_ACCOUNT_TOKEN", None)
        if self.values.get("auth_mode", "service_account") == "service_account":
            token = self.values.get("token", "")
            if not token:
                raise AuthenticationRequired(self)
            env["OP_SERVICE_ACCOUNT_TOKEN"] = token
        return env

    def _op(self, *args: str):
        extra = ["--format", "json"]
        account = self.values.get("account", "")
        if account and self.values.get("auth_mode") == "desktop":
            extra += ["--account", account]
        try:
            return self._cli_json(*args, *extra)
        except AuthenticationRequired as exc:
            if self.values.get("auth_mode") == "desktop":  # Anmeldung erfolgt in der 1Password-App
                raise RuntimeError(self.store.ctx.tr("err.op_desktop", message=str(exc))) from None
            raise

    def _vaults(self) -> list[str]:
        vault = self.values.get("vault", "").strip()
        if vault:
            return [vault]
        return [v["id"] for v in self._op("vault", "list") or []]

    def search(self, query: str) -> list[Credential]:
        q = query.strip().lower()
        result = []
        for vault in self._vaults():
            for item in self._op("item", "list", "--vault", vault, "--categories", self.CATEGORIES) or []:
                urls = [u.get("href", "") for u in item.get("urls") or []]
                user = item.get("additional_information") or ""
                hay = " ".join([item.get("title") or "", user, *urls]).lower()
                if q not in hay:
                    continue
                vault_info = item.get("vault") or {}
                detail = " · ".join(filter(None, [vault_info.get("name"), urls[0] if urls else ""]))
                result.append(Credential(f"{vault_info.get('id') or vault}|{item['id']}", item.get("title") or "",
                                         user, source=f"{self.name} · {detail}" if detail else self.name))
                if len(result) >= self.max_results:
                    return result
        return result

    def get_secret(self, cred_id: str) -> Credential | None:
        vault, _, item_id = cred_id.rpartition("|")
        args = ["item", "get", item_id] + (["--vault", vault] if vault else [])
        item = self._op(*args)
        if not item:
            return None
        fields = item.get("fields") or []

        def pick(purpose: str, ids: tuple[str, ...]) -> str:
            for f in fields:
                if f.get("purpose") == purpose and f.get("value"):
                    return str(f["value"])
            for f in fields:
                if (f.get("id") in ids or (f.get("label") or "").lower() in ids) and f.get("value"):
                    return str(f["value"])
            return ""

        return Credential(cred_id, item.get("title") or "", pick("USERNAME", ("username", "user", "benutzername")),
                          pick("PASSWORD", ("password", "credential", "passwort")))


class HashiCorpVaultConnector(ConnectorProvider):
    """HashiCorp Vault / OpenBao: KV-Secrets-Engine (Version 1 oder 2) über die HTTP-API.

    Suche = Namenssuche über die Pfade unterhalb des Basispfads (LIST, rekursiv, begrenzt).
    Anmeldung per Token, userpass, LDAP oder AppRole; das Login-Token liegt nur im Speicher.
    """

    MAX_LIST_CALLS = 300

    def _addr(self) -> str:
        return (self.values.get("address") or "").strip().rstrip("/")

    def _request(self, method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
        from omniwrench.core.net import _SSL, USER_AGENT
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if token:
            headers["X-Vault-Token"] = token
        if self.values.get("namespace"):
            headers["X-Vault-Namespace"] = self.values["namespace"].strip("/")
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self._addr() + "/v1/" + path.lstrip("/"), data=data, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                errors = json.loads(exc.read() or b"{}").get("errors") or []
            except ValueError:
                errors = []
            exc.vault_errors = errors  # type: ignore[attr-defined]
            raise
        return json.loads(raw) if raw else {}

    def _error(self, exc: urllib.error.HTTPError) -> RuntimeError:
        message = "; ".join(getattr(exc, "vault_errors", []) or []) or exc.reason
        return RuntimeError(self.store.ctx.tr("err.vault_http", status=exc.code, message=message))

    def _login(self) -> str:
        v = self.values
        mode = v.get("auth_mode", "token")
        if mode == "token":
            token = v.get("token", "")
            if not token:
                raise AuthenticationRequired(self)
            try:
                self._request("GET", "auth/token/lookup-self", token=token)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise AuthenticationRequired(self, self._error(exc).args[0]) from None
                raise self._error(exc) from None
            return token
        mount = (v.get("auth_mount") or mode).strip("/")
        if mode == "approle":
            if not v.get("role_id") or not v.get("secret_id"):
                raise AuthenticationRequired(self)
            path, body = f"auth/{mount}/login", {"role_id": v["role_id"], "secret_id": v["secret_id"]}
        else:  # userpass, ldap
            if not v.get("username") or not v.get("password"):
                raise AuthenticationRequired(self)
            user = urllib.parse.quote(v["username"], safe="")
            path, body = f"auth/{mount}/login/{user}", {"password": v["password"]}
        try:
            data = self._request("POST", path, body)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403):
                raise AuthenticationRequired(self, self._error(exc).args[0]) from None
            raise self._error(exc) from None
        token = (data.get("auth") or {}).get("client_token")
        if not token:
            raise AuthenticationRequired(self)
        return token

    def _token(self) -> str:
        if not self.state.get("token"):
            self.state["token"] = self._login()
        return self.state["token"]

    def _call(self, method: str, path: str) -> dict | None:
        """Aufruf mit Token; abgelaufenes Login-Token wird einmal erneuert. 404 -> None."""
        for attempt in (1, 2):
            try:
                return self._request(method, path, token=self._token())
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return None
                if exc.code == 403 and attempt == 1:  # Token abgelaufen/widerrufen? -> neu anmelden/prüfen
                    self.state.pop("token", None)
                    continue
                raise self._error(exc) from None
        return None

    def _kv2(self) -> bool:
        return str(self.values.get("kv_version", "2")) != "1"

    def _mount(self) -> str:
        return (self.values.get("mount") or "secret").strip("/")

    def _list(self, folder: str) -> list[str]:
        sub = "metadata/" if self._kv2() else ""
        path = f"{self._mount()}/{sub}{urllib.parse.quote(folder)}?list=true"
        try:
            data = self._call("GET", path)
        except RuntimeError:
            if folder.strip("/") == (self.values.get("path") or "").strip("/"):
                raise  # Basispfad nicht lesbar -> Fehler anzeigen
            return []  # Unterordner ohne Berechtigung überspringen
        return ((data or {}).get("data") or {}).get("keys") or []

    def search(self, query: str) -> list[Credential]:
        q = query.strip().lower()
        base = (self.values.get("path") or "").strip("/")
        queue = [base + "/" if base else ""]
        result: list[Credential] = []
        calls = 0
        while queue and calls < self.MAX_LIST_CALLS and len(result) < self.max_results:
            folder = queue.pop(0)
            calls += 1
            for key in self._list(folder):
                full = folder + key
                if key.endswith("/"):
                    queue.append(full)
                elif q in full.lower():
                    shown = full[len(base) + 1:] if base else full
                    result.append(Credential(full, key, "", source=f"{self.name} · {self._mount()}/{shown}"))
                    if len(result) >= self.max_results:
                        break
        return result

    def get_secret(self, cred_id: str) -> Credential | None:
        sub = "data/" if self._kv2() else ""
        data = self._call("GET", f"{self._mount()}/{sub}{urllib.parse.quote(cred_id)}")
        if not data:
            return None
        values = (data.get("data") or {})
        if self._kv2():
            values = values.get("data") or {}
        values = {str(k): "" if v is None else str(v) for k, v in values.items()}
        lower = {k.lower(): v for k, v in values.items()}

        def pick(configured: str, fallbacks: tuple[str, ...]) -> str:
            for key in (configured.lower(), *fallbacks):
                if key and key in lower:
                    return lower[key]
            return ""

        user = pick(self.values.get("username_key", ""), ("username", "user", "login"))
        password = pick(self.values.get("password_key", ""), ("password", "pass", "secret", "value"))
        if not password and len(values) == 1:  # einzelner Wert -> als Passwort verwenden
            password = next(iter(values.values()))
        return Credential(cred_id, cred_id.rsplit("/", 1)[-1], user, password)


IMPLEMENTATIONS = {"powershell": PowerShellConnector, "keepass": KeePassConnector, "bitwarden": BitwardenConnector,
                   "onepassword": OnePasswordConnector, "hashicorp_vault": HashiCorpVaultConnector}


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

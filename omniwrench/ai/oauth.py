"""Anmeldung per Browser: Loopback-Server auf 127.0.0.1 + PKCE (RFC 7636/8252).

Abläufe:
    chatgpt      "Sign in with ChatGPT" (dynamischer Client, Zugriff über das ChatGPT-Abo)
    openrouter   OpenRouter OAuth PKCE, liefert einen API-Schlüssel
    entra        Microsoft Entra ID (öffentlicher Client, delegierte Rechte) für M365 Copilot
    custom       eigenes OAuth 2.0 (Client-ID, Autorisierungs-/Token-URL, Scopes), z. B. Firmen-Bots

Alle Funktionen blockieren bis zur Rückkehr aus dem Browser und laufen deshalb im Hintergrund.
"""

from __future__ import annotations

import base64
import hashlib
import html
import http.server
import secrets
import threading
import time
import urllib.parse
import uuid
import webbrowser
from typing import Callable

from omniwrench.core.i18n import tr

from . import http as aihttp
from . import providers
from .connections import Connection, ConnectionStore
from .http import AIError, Cancelled

CHATGPT_AUTHORIZE = "https://auth.openai.com/api/accounts/authorize"
CHATGPT_TOKEN = "https://auth.openai.com/api/accounts/oauth/token"
CHATGPT_SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
CHATGPT_RESOURCE = "https://api.openai.com/v1"
CHATGPT_DYNAMIC_CLIENT = "dynamic_agent_client"

OPENROUTER_AUTH = "https://openrouter.ai/auth"
OPENROUTER_KEYS = "https://openrouter.ai/api/v1/auth/keys"

ENTRA_DEFAULT_CLIENT = "14d82eec-204b-4c2f-b7e8-296a70dab67e"   # Microsoft Graph Command Line Tools
ENTRA_DEFAULT_TENANT = "organizations"
ENTRA_COPILOT_SCOPES = ("Sites.Read.All Mail.Read People.Read.All OnlineMeetingTranscript.Read.All "
                        "Chat.Read ChannelMessage.Read.All ExternalItem.Read.All offline_access")

LOGIN_TIMEOUT = 300
HOST_ID_KEY = "ai_host_id"

_refresh_lock = threading.Lock()


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != self.server.callback_path:
            self.send_response(404)
            self.end_headers()
            return
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        ok = "error" not in params
        title = tr("ai.oauth.done_title") if ok else tr("ai.oauth.failed_title")
        text = tr("ai.oauth.done_text") if ok else html.escape(params.get("error_description", params["error"]))
        body = (f"<!doctype html><meta charset='utf-8'><title>OmniWrench</title>"
                f"<body style='font-family:Segoe UI,sans-serif;background:#16181d;color:#e6e8ec;"
                f"display:flex;align-items:center;justify-content:center;height:90vh'>"
                f"<div style='text-align:center'><h2>{html.escape(title)}</h2><p>{text}</p></div>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.server.result = params

    def log_message(self, *args):
        pass


class LoopbackServer:
    """Wartet auf genau einen Rücksprung des Browsers an http://127.0.0.1:<port><path>."""

    def __init__(self, path: str = "/callback", port: int = 0, host_name: str = "127.0.0.1"):
        self.httpd = http.server.HTTPServer(("127.0.0.1", port), _Handler)
        self.httpd.callback_path = path
        self.httpd.result = None
        self.httpd.timeout = 0.5
        self.redirect_uri = f"http://{host_name}:{self.httpd.server_port}{path}"

    def wait(self, stop: threading.Event | None = None, timeout: float = LOGIN_TIMEOUT) -> dict:
        end = time.monotonic() + timeout
        try:
            while self.httpd.result is None:
                if stop is not None and stop.is_set():
                    raise Cancelled()
                if time.monotonic() > end:
                    raise AIError(tr("ai.oauth.timeout"), "auth", code="timeout")
                self.httpd.handle_request()
            return self.httpd.result
        finally:
            self.httpd.server_close()


def _check(params: dict, state: str) -> str:
    if "error" in params:
        raise AIError(params.get("error_description") or params["error"], "auth", code=params["error"])
    if state and params.get("state") != state:
        raise AIError(tr("ai.oauth.state_mismatch"), "auth", code="state")
    code = params.get("code", "")
    if not code:
        raise AIError(tr("ai.oauth.no_code"), "auth", code="no_code")
    return code


def _open(url: str, open_url: Callable[[str], None] | None) -> None:
    (open_url or webbrowser.open)(url)


def _store_tokens(store: ConnectionStore, conn_id: str, tok: dict, **extra) -> None:
    data = store.secrets(conn_id)
    data["access_token"] = tok.get("access_token", "")
    if tok.get("refresh_token"):
        data["refresh_token"] = tok["refresh_token"]
    data["expires_at"] = int(time.time()) + int(tok.get("expires_in") or 3600) - 60
    if tok.get("id_token"):
        data["id_token"] = tok["id_token"]
        account = _id_token_account(tok["id_token"])
        if account:
            data["account"] = account
    data.update({k: v for k, v in extra.items() if v})
    store.set_secrets(conn_id, data)


def _id_token_account(id_token: str) -> str:
    try:
        import json
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return claims.get("email") or claims.get("preferred_username") or claims.get("name") or ""
    except Exception:
        return ""


# ------------------------------------------------------------------- ChatGPT
def host_id(settings) -> str:
    value = settings.get(HOST_ID_KEY, "")
    if not value:
        value = str(uuid.uuid4())
        settings.set(HOST_ID_KEY, value)
    return value


def login_chatgpt(store: ConnectionStore, conn: Connection, stop: threading.Event | None = None,
                  open_url: Callable[[str], None] | None = None) -> None:
    secrets_ = store.secrets(conn.id)
    client_id = secrets_.get("client_id") or CHATGPT_DYNAMIC_CLIENT
    server = LoopbackServer("/auth/callback")
    verifier, challenge = _pkce()
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    params = {
        "client_id": client_id,
        "ext_agent_host_id": host_id(store.settings),
        "response_type": "code",
        "redirect_uri": server.redirect_uri,
        "scope": CHATGPT_SCOPES,
        "resource": CHATGPT_RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if client_id == CHATGPT_DYNAMIC_CLIENT:
        params["agent_name_hint"] = "OmniWrench"
    elif secrets_.get("account"):
        params["login_hint"] = secrets_["account"]
    _open(CHATGPT_AUTHORIZE + "?" + urllib.parse.urlencode(params), open_url)
    result = server.wait(stop)
    code = _check(result, state)
    client_id = result.get("client_id") or client_id
    tok = aihttp.json_request("POST", CHATGPT_TOKEN, form={
        "grant_type": "authorization_code", "client_id": client_id, "code": code,
        "code_verifier": verifier, "redirect_uri": server.redirect_uri, "resource": CHATGPT_RESOURCE})
    _store_tokens(store, conn.id, tok, client_id=client_id)


# ---------------------------------------------------------------- OpenRouter
def login_openrouter(store: ConnectionStore, conn: Connection, stop: threading.Event | None = None,
                     open_url: Callable[[str], None] | None = None) -> None:
    server = LoopbackServer("/callback")
    verifier, challenge = _pkce()
    _open(OPENROUTER_AUTH + "?" + urllib.parse.urlencode({
        "callback_url": server.redirect_uri, "code_challenge": challenge,
        "code_challenge_method": "S256"}), open_url)
    code = _check(server.wait(stop), "")
    data = aihttp.json_request("POST", OPENROUTER_KEYS, body={
        "code": code, "code_verifier": verifier, "code_challenge_method": "S256"})
    key = data.get("key")
    if not key:
        raise AIError(tr("ai.oauth.no_code"), "auth")
    store.set_secrets(conn.id, {"api_key": key})


# ------------------------------------------------------- Entra / eigenes OAuth
def _endpoints(conn: Connection) -> tuple[str, str, str, str]:
    """(authorize, token, client_id, scopes) für Entra oder eigenes OAuth."""
    if conn.auth == providers.AUTH_ENTRA:
        tenant = (conn.entra or {}).get("tenant") or ENTRA_DEFAULT_TENANT
        client = (conn.entra or {}).get("client_id") or ENTRA_DEFAULT_CLIENT
        base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
        return base + "/authorize", base + "/token", client, ENTRA_COPILOT_SCOPES
    o = conn.oauth or {}
    if not (o.get("auth_url") and o.get("token_url") and o.get("client_id")):
        raise AIError(tr("ai.oauth.incomplete"), "auth", code="incomplete")
    return o["auth_url"], o["token_url"], o["client_id"], o.get("scopes", "")


def login_generic(store: ConnectionStore, conn: Connection, stop: threading.Event | None = None,
                  open_url: Callable[[str], None] | None = None) -> None:
    auth_url, token_url, client_id, scopes = _endpoints(conn)
    entra = conn.auth == providers.AUTH_ENTRA
    server = LoopbackServer("/" if entra else "/callback", host_name="localhost" if entra else "127.0.0.1")
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(24)
    params = {"client_id": client_id, "response_type": "code", "redirect_uri": server.redirect_uri,
              "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    if scopes:
        params["scope"] = scopes
    if entra:
        params["prompt"] = "select_account"
    sep = "&" if "?" in auth_url else "?"
    _open(auth_url + sep + urllib.parse.urlencode(params), open_url)
    code = _check(server.wait(stop), state)
    form = {"grant_type": "authorization_code", "client_id": client_id, "code": code,
            "code_verifier": verifier, "redirect_uri": server.redirect_uri}
    if scopes:
        form["scope"] = scopes
    secret = store.secrets(conn.id).get("oauth_client_secret")
    if secret:
        form["client_secret"] = secret
    _store_tokens(store, conn.id, aihttp.json_request("POST", token_url, form=form))


def login(store: ConnectionStore, conn: Connection, stop: threading.Event | None = None,
          open_url: Callable[[str], None] | None = None) -> None:
    if conn.auth == providers.AUTH_CHATGPT:
        login_chatgpt(store, conn, stop, open_url)
    elif conn.auth == providers.AUTH_OPENROUTER:
        login_openrouter(store, conn, stop, open_url)
    elif conn.auth in (providers.AUTH_ENTRA, providers.AUTH_CUSTOM):
        login_generic(store, conn, stop, open_url)
    else:
        raise AIError(f"no browser login for {conn.auth}", "request")


def logout(store: ConnectionStore, conn: Connection) -> None:
    data = store.secrets(conn.id)
    # ChatGPT: ausgestellte Client-ID wiederverwenden; Client-Secret des eigenen OAuth behalten
    keep = {k: data[k] for k in ("client_id", "oauth_client_secret") if k in data}
    store.set_secrets(conn.id, keep)


# ------------------------------------------------------------------ Tokens
def access_token(store: ConnectionStore, conn: Connection) -> str:
    """Gültiges Zugriffstoken, bei Bedarf erneuert (Refresh-Token rotiert bei ChatGPT)."""
    with _refresh_lock:
        data = store.secrets(conn.id)
        token = data.get("access_token", "")
        if token and int(data.get("expires_at", 0)) > time.time():
            return token
        refresh = data.get("refresh_token")
        if not refresh:
            raise AIError(tr("ai.error.signed_out"), "auth", code="signed_out")
        if conn.auth == providers.AUTH_CHATGPT:
            url = CHATGPT_TOKEN
            form = {"grant_type": "refresh_token", "client_id": data.get("client_id", ""),
                    "refresh_token": refresh, "resource": CHATGPT_RESOURCE}
        else:
            _, url, client_id, scopes = _endpoints(conn)
            form = {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh}
            if scopes:
                form["scope"] = scopes
            secret = store.secrets(conn.id).get("oauth_client_secret")
            if secret:
                form["client_secret"] = secret
        try:
            tok = aihttp.json_request("POST", url, form=form)
        except AIError as err:
            if err.status in (400, 401):
                logout(store, conn)
                raise AIError(tr("ai.error.signed_out"), "auth", code="signed_out") from None
            raise
        _store_tokens(store, conn.id, tok)
        return tok.get("access_token", "")

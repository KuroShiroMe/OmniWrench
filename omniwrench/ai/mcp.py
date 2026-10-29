"""MCP-Client (Model Context Protocol): Werkzeuge fremder MCP-Server für die Assistenten nutzbar machen.

Unterstützt die aktuelle Fassung 2026-07-28 (ohne Sitzung, Version in jedem Request unter _meta) und die
älteren Fassungen mit initialize-Handshake (2025-11-25 … 2025-03-26), wie es die Spezifikation für
„dual-era“-Clients beschreibt:
    stdio: zuerst server/discover; bei einem unbekannten Fehler oder Zeitüberschreitung -> initialize.
    HTTP:  zuerst ein moderner Request; 400/404/405 ohne bekannten modernen Fehler -> initialize.
Genutzt werden nur Werkzeuge (tools/list, tools/call). Rückfragen des Servers (elicitation, sampling)
werden abgelehnt. Qt-frei; die Oberfläche steht in tools/gadgetron/mcptab.py.

Server-Eintrag (Tool-Einstellung "mcp_servers"):
    {"id", "name", "transport": "stdio"|"http", "command", "args": [..], "env": {..}, "cwd",
     "url", "headers": {..}, "enabled": true, "trusted": false, "disabled_tools": [..]}
Token für HTTP liegt im Tresor des Tools (secret_key(id)) und geht als "Authorization: Bearer …" mit.
"""

from __future__ import annotations

import base64
import itertools
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from omniwrench import APP_NAME, __version__

log = logging.getLogger(__name__)

MODERN_VERSION = "2026-07-28"
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
SUPPORTED = (MODERN_VERSION, *LEGACY_VERSIONS)
# Fehlercodes, an denen man einen modernen Server erkennt (dann kein Rückfall auf initialize)
UNSUPPORTED_VERSION, HEADER_MISMATCH, MISSING_CAPABILITY = -32022, -32020, -32021
MODERN_ERRORS = {UNSUPPORTED_VERSION, HEADER_MISMATCH, MISSING_CAPABILITY}
TIMEOUT = 60.0
PROBE_TIMEOUT = 8.0
MAX_TOOLS = 200
NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")
CLIENT_INFO = {"name": APP_NAME, "version": __version__}


class MCPError(Exception):
    def __init__(self, message: str, code: int = 0, data: Any = None, status: int = 0):
        super().__init__(message)
        self.code = code
        self.data = data
        self.status = status


def secret_key(server_id: str) -> str:
    return f"mcp:{server_id}"


def new_server(name: str, transport: str = "stdio") -> dict:
    import secrets
    return {"id": secrets.token_hex(4), "name": name, "transport": transport, "command": "", "args": [],
            "env": {}, "cwd": "", "url": "", "headers": {}, "enabled": True, "trusted": False,
            "disabled_tools": []}


def split_args(text: str) -> list[str]:
    """Argumentzeile wie in einer Shell aufteilen (Anführungszeichen erlaubt)."""
    try:
        return shlex.split(text, posix=os.name != "nt") if text.strip() else []
    except ValueError:
        return text.split()


def slug(text: str, limit: int = 20) -> str:
    s = NAME_RE.sub("_", text.strip().lower()).strip("_")
    return (s or "server")[:limit]


def function_name(server: dict, tool: str) -> str:
    """Eindeutiger Funktionsname für den Assistenten: mcp_<server>_<werkzeug>, höchstens 64 Zeichen."""
    base = f"mcp_{slug(server.get('name') or server.get('id', ''))}_"
    name = NAME_RE.sub("_", tool)
    return (base + name)[:64]


def is_read_only(tool: dict, trusted: bool) -> bool:
    """Werkzeug nur lesend? Hinweise des Servers zählen nur bei vertrauenswürdigen Servern (Spezifikation)."""
    return bool(trusted and (tool.get("annotations") or {}).get("readOnlyHint"))


def clean_schema(schema: Any) -> dict:
    """inputSchema für die Sprachmodell-Anbieter: ohne $schema/$id/x-mcp-header, immer ein Objekt."""
    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k not in ("$schema", "$id", "x-mcp-header")}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node
    out = strip(schema) if isinstance(schema, dict) else {}
    if out.get("type") != "object":
        out = {"type": "object", "properties": {}}
    out.setdefault("properties", {})
    return out


def result_text(result: dict) -> str:
    """tools/call-Ergebnis -> Text für den Assistenten."""
    parts = []
    for c in result.get("content") or []:
        kind = c.get("type")
        if kind == "text":
            parts.append(c.get("text", ""))
        elif kind in ("image", "audio"):
            size = len(c.get("data") or "") * 3 // 4
            parts.append(f"[{kind} {c.get('mimeType', '')}, {size} bytes]")
        elif kind == "resource":
            r = c.get("resource") or {}
            parts.append(f"[resource {r.get('uri', '')}]\n{r.get('text', '')}" if r.get("text")
                         else f"[resource {r.get('uri', '')} {r.get('mimeType', '')}]")
        elif kind == "resource_link":
            parts.append(f"[link {c.get('name', '')}: {c.get('uri', '')}]")
    if "structuredContent" in result and not any(parts):
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False, indent=1))
    text = "\n".join(p for p in parts if p) or "(no content)"
    return ("Error: " + text) if result.get("isError") else text


def _meta(version: str) -> dict:
    return {"io.modelcontextprotocol/protocolVersion": version,
            "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
            "io.modelcontextprotocol/clientCapabilities": {}}


def _header_value(value: str) -> str:
    """Wert für Mcp-Name / Mcp-Param-*: reines ASCII so, sonst Base64-Sentinel."""
    safe = all(0x20 <= ord(ch) <= 0x7E for ch in value) and value == value.strip()
    if safe and not (value.startswith("=?base64?") and value.endswith("?=")):
        return value
    return "=?base64?" + base64.b64encode(value.encode("utf-8")).decode() + "?="


def param_headers(schema: dict, args: dict) -> dict:
    """x-mcp-header: Werte statisch erreichbarer Eigenschaften als Mcp-Param-<Name>."""
    out: dict[str, str] = {}

    def walk(node: dict, values: Any):
        for key, sub in (node.get("properties") or {}).items():
            if not isinstance(sub, dict) or not isinstance(values, dict) or values.get(key) is None:
                continue
            v = values[key]
            name = sub.get("x-mcp-header")
            if isinstance(name, str) and name and isinstance(v, (str, int, bool)) and not isinstance(v, float):
                out[f"Mcp-Param-{name}"] = _header_value(("true" if v else "false") if isinstance(v, bool)
                                                         else str(v))
            if sub.get("properties"):
                walk(sub, v)
    walk(schema or {}, args or {})
    return out


def valid_header_schema(schema: dict) -> bool:
    """Prüft die x-mcp-header-Regeln; ungültige Werkzeuge muss ein HTTP-Client weglassen."""
    seen: set[str] = set()
    token = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")

    def bad_anywhere(node: Any, allowed: bool) -> bool:
        if isinstance(node, dict):
            if "x-mcp-header" in node and not allowed:
                return True
            return any(bad_anywhere(v, False) for k, v in node.items() if k != "properties")
        if isinstance(node, list):
            return any(bad_anywhere(v, False) for v in node)
        return False

    def walk(node: dict) -> bool:
        for sub in (node.get("properties") or {}).values():
            if not isinstance(sub, dict):
                continue
            name = sub.get("x-mcp-header")
            if name is not None:
                if not isinstance(name, str) or not token.match(name) or name.lower() in seen \
                        or sub.get("type") not in ("string", "integer", "boolean"):
                    return False
                seen.add(name.lower())
            if any(bad_anywhere(v, False) for k, v in sub.items() if k not in ("properties", "x-mcp-header")):
                return False
            if not walk(sub):
                return False
        return True
    return walk(schema or {})


# ------------------------------------------------------------------ Transporte
class StdioTransport:
    """Startet den Server als Prozess; eine JSON-RPC-Nachricht je Zeile auf stdin/stdout."""

    def __init__(self, command: str, args: list[str], env: dict | None = None, cwd: str = ""):
        full_env = dict(os.environ)
        full_env.update({str(k): str(v) for k, v in (env or {}).items()})
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        try:
            self.proc = subprocess.Popen([command, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, cwd=cwd or None, env=full_env,
                                         creationflags=flags)
        except OSError as err:
            raise MCPError(f"Cannot start {command}: {err}") from None
        self._pending: dict[Any, dict] = {}
        self._events: dict[Any, threading.Event] = {}
        self._lock = threading.Lock()
        self._write = threading.Lock()
        self.stderr = ""
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read(self) -> None:
        for raw in self.proc.stdout:
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if "method" in msg:
                if "id" in msg:         # Anfrage des Servers (alte Fassungen): nur ping beantworten
                    if msg["method"] == "ping":
                        self._send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
                    else:
                        self._send({"jsonrpc": "2.0", "id": msg["id"],
                                    "error": {"code": -32601, "message": "Not supported by this client"}})
                continue
            with self._lock:
                ev = self._events.get(msg.get("id"))
                if ev is not None:
                    self._pending[msg.get("id")] = msg
                    ev.set()
        with self._lock:                 # Prozess beendet: alle Wartenden wecken
            for ev in self._events.values():
                ev.set()

    def _read_err(self) -> None:
        for raw in self.proc.stderr:
            self.stderr = (self.stderr + raw.decode("utf-8", "replace"))[-4000:]

    def _send(self, msg: dict) -> None:
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write:
            try:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
            except (OSError, ValueError):
                code = self.proc.poll()
                raise MCPError(f"Server process ended (exit code {code}). {self.stderr[-500:]}".strip()) from None

    def request(self, msg: dict, timeout: float, stop: threading.Event | None, headers: dict | None = None) -> dict:
        ev = threading.Event()
        with self._lock:
            self._events[msg["id"]] = ev
        try:
            self._send(msg)
            waited = 0.0
            while not ev.wait(0.2):
                waited += 0.2
                if stop is not None and stop.is_set():
                    self.notify({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                 "params": {"requestId": msg["id"], "reason": "cancelled by user"}})
                    raise MCPError("cancelled")
                if waited >= timeout:
                    raise MCPError(f"Timeout after {int(timeout)} s", status=-1)
            with self._lock:
                resp = self._pending.pop(msg["id"], None)
            if resp is None:
                raise MCPError(f"Server process ended. {self.stderr[-500:]}".strip())
            return resp
        finally:
            with self._lock:
                self._events.pop(msg["id"], None)

    def notify(self, msg: dict, headers: dict | None = None) -> None:
        try:
            self._send(msg)
        except MCPError:
            pass

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                self.proc.kill()
            except OSError:
                pass


class HttpTransport:
    """Streamable HTTP: jede Nachricht ein POST; Antwort als JSON oder SSE-Strom."""

    def __init__(self, url: str, headers: dict | None = None):
        self.url = url
        self.headers = dict(headers or {})
        self.session = ""               # nur alte Fassungen (Mcp-Session-Id)

    def _open(self, body: dict, extra: dict, timeout: float):
        from omniwrench.core.net import _SSL, USER_AGENT
        h = {"User-Agent": USER_AGENT, "Content-Type": "application/json",
             "Accept": "application/json, text/event-stream", **self.headers, **extra}
        if self.session:
            h["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), headers=h, method="POST")
        host = (urllib.parse.urlparse(self.url).hostname or "").lower()
        if self.url.startswith("https:"):
            return urllib.request.urlopen(req, timeout=timeout, context=_SSL)
        if host in ("localhost", "::1") or host.startswith("127."):
            return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)
        return urllib.request.urlopen(req, timeout=timeout)

    def request(self, msg: dict, timeout: float, stop: threading.Event | None, headers: dict | None = None) -> dict:
        try:
            resp = self._open(msg, headers or {}, timeout)
        except urllib.error.HTTPError as err:
            raw = err.read() or b""
            try:
                data = json.loads(raw)
            except ValueError:
                data = None
            if isinstance(data, dict) and isinstance(data.get("error"), dict):
                data.setdefault("id", msg.get("id"))
                data["_status"] = err.code
                return data
            raise MCPError(f"HTTP {err.code}: {raw[:300].decode('utf-8', 'replace')}".strip(),
                           status=err.code) from None
        except (urllib.error.URLError, OSError) as err:
            raise MCPError(str(getattr(err, "reason", err)), status=-1) from None
        with resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session = sid
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "text/event-stream" in ctype:
                return self._from_sse(resp, msg.get("id"), stop)
            raw = resp.read()
        try:
            return json.loads(raw) if raw else {"id": msg.get("id"), "result": {}}
        except ValueError:
            raise MCPError("Invalid JSON from server: " + raw[:200].decode("utf-8", "replace")) from None

    @staticmethod
    def _from_sse(resp, want_id, stop) -> dict:
        data: list[str] = []
        for raw in resp:
            if stop is not None and stop.is_set():
                raise MCPError("cancelled")    # Strom schließen = Abbruch (moderne Fassung)
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
                continue
            if line or not data:
                continue
            try:
                msg = json.loads("\n".join(data))
            except ValueError:
                msg = None
            data = []
            if isinstance(msg, dict) and msg.get("id") == want_id and ("result" in msg or "error" in msg):
                return msg
        if data:
            try:
                msg = json.loads("\n".join(data))
                if isinstance(msg, dict) and msg.get("id") == want_id:
                    return msg
            except ValueError:
                pass
        raise MCPError("Stream ended without a response")

    def notify(self, msg: dict, headers: dict | None = None) -> None:
        try:
            self._open(msg, headers or {}, 15).close()
        except (urllib.error.URLError, OSError):
            pass

    def close(self) -> None:
        if self.session:                  # alte Fassungen: Sitzung beenden
            try:
                req = urllib.request.Request(self.url, method="DELETE", headers={**self.headers,
                                                                                 "Mcp-Session-Id": self.session})
                urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=5).close()
            except (urllib.error.URLError, OSError, ValueError):
                pass


# ------------------------------------------------------------------ Client
class Client:
    """Verbindung zu einem MCP-Server. connect() ermittelt die Fassung, tools() listet die Werkzeuge."""

    def __init__(self, server: dict, token: str = ""):
        self.server = server
        self.token = token
        self.transport: StdioTransport | HttpTransport | None = None
        self.version = ""
        self.modern = True
        self.info: dict = {}
        self.instructions = ""
        self._ids = itertools.count(1)
        self._schemas: dict[str, dict] = {}

    @property
    def is_http(self) -> bool:
        return self.server.get("transport") == "http"

    def connect(self, stop: threading.Event | None = None) -> None:
        s = self.server
        if self.is_http:
            headers = {str(k): str(v) for k, v in (s.get("headers") or {}).items()}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            if not s.get("url"):
                raise MCPError("URL missing")
            self.transport = HttpTransport(s["url"], headers)
        else:
            if not s.get("command"):
                raise MCPError("Command missing")
            self.transport = StdioTransport(s["command"], list(s.get("args") or []), s.get("env") or {},
                                            s.get("cwd") or "")
        try:
            self._negotiate(stop)
        except Exception:
            self.close()
            raise

    def _negotiate(self, stop) -> None:
        self.version, self.modern = MODERN_VERSION, True
        for _attempt in range(2):
            try:
                resp = self._raw("server/discover", {}, PROBE_TIMEOUT, stop)
            except MCPError as err:
                if err.status == -1 and self.is_http:
                    raise                            # Netzwerkfehler: kein Rückfall
                if err.status in (-1, 0) or err.status in (400, 404, 405):
                    break                            # stdio: Zeitüberschreitung / HTTP ohne JSON -> alt
                raise
            err = resp.get("error")
            if not err:
                res = resp.get("result") or {}
                self.info = (res.get("_meta") or {}).get("io.modelcontextprotocol/serverInfo") or {}
                self.instructions = res.get("instructions") or ""
                versions = res.get("supportedVersions") or [MODERN_VERSION]
                if MODERN_VERSION in versions:
                    return
                if any(v in LEGACY_VERSIONS for v in versions):
                    break
                raise MCPError(f"No common protocol version (server: {', '.join(versions)})")
            code = err.get("code")
            if code == UNSUPPORTED_VERSION:
                offered = [str(v) for v in (err.get("data") or {}).get("supported") or []]
                if MODERN_VERSION in offered:
                    continue
                if any(v in LEGACY_VERSIONS for v in offered):
                    break
                raise MCPError(f"No common protocol version (server: {', '.join(offered)})", code)
            if code in MODERN_ERRORS or (code == -32601 and resp.get("_status") == 404):
                raise MCPError(err.get("message") or "Server error", code)
            break                                    # unbekannter Fehler -> alter Server
        self._initialize(stop)

    def _initialize(self, stop) -> None:
        self.modern = False
        resp = self._raw("initialize", {"protocolVersion": LEGACY_VERSIONS[0], "capabilities": {},
                                        "clientInfo": CLIENT_INFO}, TIMEOUT, stop, legacy=True)
        if resp.get("error"):
            raise MCPError(resp["error"].get("message") or "initialize failed", resp["error"].get("code", 0))
        res = resp.get("result") or {}
        version = res.get("protocolVersion") or LEGACY_VERSIONS[0]
        if version not in LEGACY_VERSIONS and version != "2024-11-05":
            raise MCPError(f"Unsupported protocol version {version}")
        self.version = version
        self.info = res.get("serverInfo") or {}
        self.instructions = res.get("instructions") or ""
        headers = {"MCP-Protocol-Version": version} if self.is_http else {}
        self.transport.notify({"jsonrpc": "2.0", "method": "notifications/initialized"}, headers)

    def _raw(self, method: str, params: dict, timeout: float, stop, legacy: bool = False,
             extra_headers: dict | None = None) -> dict:
        if self.transport is None:
            raise MCPError("not connected")
        params = dict(params)
        headers: dict[str, str] = {}
        if not legacy and self.modern:
            params["_meta"] = {**(params.get("_meta") or {}), **_meta(self.version)}
            if self.is_http:
                headers = {"MCP-Protocol-Version": self.version, "Mcp-Method": method}
                name = params.get("name") or params.get("uri")
                if method in ("tools/call", "resources/read", "prompts/get") and name:
                    headers["Mcp-Name"] = _header_value(str(name))
        elif self.is_http and self.version and method != "initialize":
            headers = {"MCP-Protocol-Version": self.version}
        headers.update(extra_headers or {})
        msg = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}
        return self.transport.request(msg, timeout, stop, headers)

    def call(self, method: str, params: dict | None = None, timeout: float = TIMEOUT, stop=None,
             extra_headers: dict | None = None) -> dict:
        resp = self._raw(method, params or {}, timeout, stop, extra_headers=extra_headers)
        err = resp.get("error")
        if err:
            raise MCPError(err.get("message") or f"Error {err.get('code')}", err.get("code", 0), err.get("data"))
        return resp.get("result") or {}

    def tools(self, stop=None) -> list[dict]:
        out, cursor = [], None
        for _page in range(20):
            res = self.call("tools/list", {"cursor": cursor} if cursor else {}, stop=stop)
            for t in res.get("tools") or []:
                if not isinstance(t, dict) or not t.get("name"):
                    continue
                if self.is_http and not valid_header_schema(t.get("inputSchema") or {}):
                    log.warning("MCP: Werkzeug %s ausgelassen (ungültiges x-mcp-header)", t.get("name"))
                    continue
                out.append(t)
            cursor = res.get("nextCursor")
            if not cursor or len(out) >= MAX_TOOLS:
                break
        self._schemas = {t["name"]: t.get("inputSchema") or {} for t in out}
        return out[:MAX_TOOLS]

    def call_tool(self, name: str, arguments: dict, stop=None, timeout: float = 300) -> dict:
        params: dict = {"name": name, "arguments": arguments or {}}
        extra = param_headers(self._schemas.get(name) or {}, arguments) if self.is_http and self.modern else {}
        res = self.call("tools/call", params, timeout, stop, extra)
        if res.get("resultType") == "input_required":
            # Rückfragen (Formulare, Sampling) unterstützt OmniWrench nicht: alle ablehnen, einmal neu senden
            params["inputResponses"] = {k: {"action": "decline"} for k in (res.get("inputRequests") or {})}
            if res.get("requestState"):
                params["requestState"] = res["requestState"]
            res = self.call("tools/call", params, timeout, stop, extra)
            if res.get("resultType") == "input_required":
                return {"content": [{"type": "text", "text": "The server needs interactive input, which "
                                     "OmniWrench does not support."}], "isError": True}
        return res

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()
            self.transport = None

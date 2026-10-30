"""OmniWrench als MCP-Server: andere KI-Programme (Claude Desktop, VS Code, Cursor …) nutzen die Funktionen,
die auch die eingebauten Assistenten haben – mit denselben Zugriffsstufen (Seite „KI-Zugriff“, Ausnahme
für den Assistenten "mcp-server"), Bestätigung bei Änderungen und Verfremdung.

Transport: Streamable HTTP auf 127.0.0.1 (nur dieser Rechner), Endpunkt /mcp, Pflicht-Token
("Authorization: Bearer …"). Spricht die Fassung 2026-07-28 (ohne Sitzung) und für ältere Clients den
initialize-Handshake (2025-11-25 … 2025-03-26).
Für Clients, die nur stdio können: "OmniWrench --mcp-stdio" (bzw. python main.py --mcp-stdio) leitet stdin/stdout
an den laufenden Server weiter; Port und Token stehen in CONFIG_DIR/mcp_server.json.
Qt-frei; Start/Stopp und Oberfläche im Tool Gadgetron (tools/gadgetron/mcptab.py).
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from omniwrench import APP_NAME, __version__

from . import functions
from .mcp import LEGACY_VERSIONS, MODERN_VERSION

log = logging.getLogger(__name__)

CONN_ID = "mcp-server"            # Ausnahmen auf der Seite „KI-Zugriff“ gelten unter diesem Namen
DEFAULT_PORT = 47821
SERVER_VERSIONS = [MODERN_VERSION, *LEGACY_VERSIONS]
INSTRUCTIONS = (f"{APP_NAME} is an admin toolbox for Windows clients and Linux. These tools read (and, after the "
                "user confirms in the program, change) data of the program and its connected systems. Values like "
                "IP-1 or HOST-2 are placeholders for hidden real data; pass them back unchanged.")


def info_file() -> Path:
    from omniwrench.core.paths import CONFIG_DIR
    return CONFIG_DIR / "mcp_server.json"


def write_info(port: int, token: str) -> None:
    path = info_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"port": port, "token": token, "pid": os.getpid()}), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def clear_info() -> None:
    try:
        info_file().unlink()
    except OSError:
        pass


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _decode_header(value: str) -> str:
    if value.startswith("=?base64?") and value.endswith("?="):
        try:
            return base64.b64decode(value[9:-2]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return "\0invalid"
    return value


# ------------------------------------------------------------------ Funktionen bereitstellen
class FunctionHost:
    """Welche Funktionen der Server anbietet und wie ein Aufruf läuft (Stufen, Bestätigung, Verfremdung)."""

    def __init__(self, settings, confirm: Callable[[functions.Function, dict], bool] | None = None,
                 in_gui: Callable[[Callable[[], Any]], Any] | None = None, window=None,
                 on_call: Callable[[str, bool], None] | None = None):
        self.settings = settings
        self.confirm = confirm or (lambda fn, args: False)
        self.in_gui = in_gui or (lambda fn: fn())
        self.window = window
        self.on_call = on_call or (lambda name, ok: None)
        self.pseudo_state: dict = {}      # gleiche Platzhalter, solange der Server läuft

    def level_for(self, source: str) -> int:
        from . import access
        return access.level(self.settings, source, CONN_ID)

    def functions(self) -> list[functions.Function]:
        # Werkzeuge fremder MCP-Server nicht weiterreichen (keine Schleifen, keine fremden Rechte)
        fns = [f for f in functions.available(self.level_for) if not f.name.startswith("mcp_")]
        return sorted(fns, key=lambda f: f.name)

    def _pseudo(self, source: str):
        from . import access
        from .pseudo import Pseudonymizer
        return Pseudonymizer(self.pseudo_state, access.pseudo_kinds(self.settings),
                             enabled=access.pseudo_enabled(self.settings, source))

    def call(self, name: str, args: dict, stop: threading.Event) -> tuple[str, bool]:
        fn = next((f for f in self.functions() if f.name == name), None)
        if fn is None:
            raise KeyError(name)
        p = self._pseudo(fn.source)
        args = json.loads(p.decode(json.dumps(args or {}, ensure_ascii=False)))
        if (fn.confirm or fn.level >= functions.LEVEL_CHANGE) and not self.confirm(fn, args):
            self.on_call(name, False)
            return "The user declined this action in OmniWrench.", False
        ctx = functions.CallContext(window=self.window, level=self.level_for(fn.source), in_gui=self.in_gui,
                                    stop=stop)
        try:
            value = fn.handler(args, ctx)
        except Exception as err:  # noqa: BLE001 - Fehler geht als Text an den Client
            self.on_call(name, False)
            return f"Error: {err}", False
        self.on_call(name, True)
        return functions.format_result(p.encode_value(value)), True

    def schema(self, fn: functions.Function) -> dict:
        change = fn.level >= functions.LEVEL_CHANGE
        params = dict(fn.parameters or {"type": "object"})
        params.setdefault("type", "object")
        return {"name": fn.name, "description": fn.description, "inputSchema": params,
                "annotations": {"readOnlyHint": not change, "destructiveHint": change, "openWorldHint": False}}


# ------------------------------------------------------------------ JSON-RPC
class Core:
    """Beantwortet eine JSON-RPC-Nachricht (beide Fassungen)."""

    def __init__(self, host: FunctionHost):
        self.host = host

    @staticmethod
    def error(mid, code: int, message: str, data: Any = None) -> dict:
        e = {"code": code, "message": message}
        if data is not None:
            e["data"] = data
        return {"jsonrpc": "2.0", "id": mid, "error": e}

    def handle(self, msg: Any, stop: threading.Event | None = None) -> dict | None:
        stop = stop or threading.Event()
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method", ""), str):
            return self.error(None, -32600, "Invalid request")
        method, mid = msg.get("method"), msg.get("id")
        if method is None:
            return None                                # Antwort eines Clients – gibt es hier nicht
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if "id" not in msg:
            return None                                # Benachrichtigung (initialized, cancelled …)
        version = ((params.get("_meta") or {}).get("io.modelcontextprotocol/protocolVersion")
                   if isinstance(params.get("_meta"), dict) else None)
        modern = version is not None and method != "initialize"
        if modern and version != MODERN_VERSION:
            return self.error(mid, -32022, "Unsupported protocol version",
                              {"supported": SERVER_VERSIONS, "requested": version})

        def ok(result: dict) -> dict:
            if modern:
                result = {"resultType": "complete", **result}
            return {"jsonrpc": "2.0", "id": mid, "result": result}

        server_info = {"name": APP_NAME, "version": __version__}
        if method == "initialize":
            requested = params.get("protocolVersion")
            chosen = requested if requested in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
            return ok({"protocolVersion": chosen, "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": server_info, "instructions": INSTRUCTIONS})
        if method == "server/discover":
            return ok({"supportedVersions": SERVER_VERSIONS, "capabilities": {"tools": {}},
                       "_meta": {"io.modelcontextprotocol/serverInfo": server_info},
                       "instructions": INSTRUCTIONS})
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": [self.host.schema(f) for f in self.host.functions()]})
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            try:
                text, success = self.host.call(str(name), args, stop)
            except KeyError:
                return self.error(mid, -32602, f"Unknown tool: {name}")
            return ok({"content": [{"type": "text", "text": text}], "isError": not success})
        return self.error(mid, -32601, f"Method not found: {method}")


# ------------------------------------------------------------------ HTTP
class _Handler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}-MCP/{__version__}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: D401 - leise
        log.debug("MCP-Server: " + fmt, *args)

    def _send(self, status: int, body: dict | None = None, headers: dict | None = None) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def do_GET(self):  # noqa: N802 - keine Ereignisströme
        self._send(405, None, {"Allow": "POST"})

    def do_DELETE(self):  # noqa: N802
        self._send(405, None, {"Allow": "POST"})

    def _allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if origin:
            from urllib.parse import urlparse
            if (urlparse(origin).hostname or "") not in ("localhost", "127.0.0.1", "::1"):
                self._send(403, Core.error(None, -32600, "Origin not allowed"))
                return False
        token = self.server.mcp.token
        auth = self.headers.get("Authorization") or ""
        given = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if not token or not hmac.compare_digest(given.encode(), token.encode()):
            self._send(401, Core.error(None, -32600, "Missing or wrong token"),
                       {"WWW-Authenticate": 'Bearer realm="OmniWrench"'})
            return False
        return True

    def do_POST(self):  # noqa: N802
        srv = self.server.mcp
        if self.path.split("?")[0].rstrip("/") != "/mcp":
            self._send(404, Core.error(None, -32601, "Use the endpoint /mcp"))
            return
        if not self._allowed():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            msg = json.loads(self.rfile.read(min(length, 10_000_000)) or b"null")
        except (ValueError, OSError):
            self._send(400, Core.error(None, -32700, "Parse error"))
            return
        if isinstance(msg, list):
            self._send(400, Core.error(None, -32600, "Batches are not supported"))
            return
        if isinstance(msg, dict) and "id" not in msg:
            self._send(202)
            return
        params = msg.get("params") if isinstance(msg, dict) and isinstance(msg.get("params"), dict) else {}
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        version = meta.get("io.modelcontextprotocol/protocolVersion")
        mid = msg.get("id") if isinstance(msg, dict) else None
        method = msg.get("method") if isinstance(msg, dict) else None
        if version is not None and method != "initialize":
            problem = self._header_problem(version, method, params)
            if problem:
                code = -32022 if problem == "version" else -32020
                body = (Core.error(mid, code, "Unsupported protocol version",
                                   {"supported": SERVER_VERSIONS, "requested": version}) if problem == "version"
                        else Core.error(mid, code, f"Header mismatch: {problem}"))
                self._send(400, body)
                return
        stop = threading.Event()
        resp = srv.core.handle(msg, stop)
        headers = {}
        if method == "initialize" and resp and "result" in resp:
            headers["Mcp-Session-Id"] = secrets.token_hex(16)
        if resp is None:
            self._send(202)
            return
        status = 200
        if version is not None and "error" in resp and resp["error"]["code"] == -32601:
            status = 404
        self._send(status, resp, headers)

    def _header_problem(self, version: str, method, params: dict) -> str:
        hv = self.headers.get("MCP-Protocol-Version")
        if hv is None:
            return "MCP-Protocol-Version missing"
        if hv != version:
            return "MCP-Protocol-Version does not match _meta"
        if version != MODERN_VERSION:
            return "version"
        if self.headers.get("Mcp-Method") != method:
            return "Mcp-Method missing or does not match"
        if method in ("tools/call", "resources/read", "prompts/get"):
            name = self.headers.get("Mcp-Name")
            if name is None or _decode_header(name) != str(params.get("name") or params.get("uri") or ""):
                return "Mcp-Name missing or does not match"
        return ""


class Server:
    """HTTP-Server im Hintergrund-Thread. start() wirft OSError, wenn der Port belegt ist."""

    def __init__(self, host: FunctionHost, port: int = DEFAULT_PORT, token: str = ""):
        self.core = Core(host)
        self.port = port
        self.token = token or new_token()
        self._httpd: ThreadingHTTPServer | None = None
        self.started = 0.0

    @property
    def running(self) -> bool:
        return self._httpd is not None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/mcp"

    def start(self) -> None:
        if self._httpd is not None:
            return
        httpd = ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)
        httpd.daemon_threads = True
        httpd.mcp = self
        self.port = httpd.server_address[1]
        self._httpd = httpd
        self.started = time.time()
        threading.Thread(target=httpd.serve_forever, name="mcp-server", daemon=True).start()
        write_info(self.port, self.token)

    def stop(self) -> None:
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
            clear_info()


# ------------------------------------------------------------------ stdio-Brücke
def stdio_bridge(stdin=None, stdout=None) -> int:
    """Leitet JSON-RPC-Zeilen von stdin an den laufenden Server weiter (für Clients, die nur stdio können)."""
    import urllib.error
    import urllib.request
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def write(msg: dict) -> None:
        stdout.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        stdout.flush()

    session = ""
    for raw in stdin:
        if not raw.strip():
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            write(Core.error(None, -32700, "Parse error"))
            continue
        mid = msg.get("id") if isinstance(msg, dict) else None
        try:
            info = json.loads(info_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            if mid is not None:
                write(Core.error(mid, -32603, f"{APP_NAME} is not running or its MCP server is off. Start "
                                              f"{APP_NAME}, open the tool Gadgetron and switch on the MCP server."))
            continue
        params = msg.get("params") if isinstance(msg, dict) and isinstance(msg.get("params"), dict) else {}
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "Authorization": f"Bearer {info.get('token', '')}"}
        version = meta.get("io.modelcontextprotocol/protocolVersion")
        if version:
            headers["MCP-Protocol-Version"] = str(version)
            headers["Mcp-Method"] = str(msg.get("method"))
            name = params.get("name") or params.get("uri")
            if name is not None:
                from .mcp import _header_value
                headers["Mcp-Name"] = _header_value(str(name))
        if session:
            headers["Mcp-Session-Id"] = session
        req = urllib.request.Request(f"http://127.0.0.1:{info.get('port')}/mcp",
                                     data=json.dumps(msg).encode("utf-8"), headers=headers, method="POST")
        try:
            with opener.open(req, timeout=600) as resp:
                session = resp.headers.get("Mcp-Session-Id") or session
                body = resp.read()
        except urllib.error.HTTPError as err:
            body = err.read()
        except (urllib.error.URLError, OSError) as err:
            if mid is not None:
                write(Core.error(mid, -32603, f"{APP_NAME} is not reachable: {getattr(err, 'reason', err)}"))
            continue
        if mid is None or not body:
            continue
        try:
            write(json.loads(body))
        except ValueError:
            write(Core.error(mid, -32603, "Invalid answer from OmniWrench"))
    return 0

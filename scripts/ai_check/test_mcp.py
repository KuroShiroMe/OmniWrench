"""MCP prüfen: Client (stdio/HTTP, neue und alte Fassung), Server (HTTP, Token, Header, Stufen, Verfremdung),
stdio-Brücke und Gadgetron (MCP).

    python scripts/ai_check/test_mcp.py [--shots ORDNER]
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import render_screenshots as rs  # noqa: E402  (Temp-Home, offscreen, pump)

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from omniwrench.ai import functions, mcp  # noqa: E402
from omniwrench.ai import mcp_server as mcps  # noqa: E402
from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.settings import AppSettings  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402

OK = 0

FAKE_STDIO = r'''
import json, sys
mode = sys.argv[1]
TOOLS = [
    {"name": "echo", "title": "Echo", "description": "Echo a text",
     "inputSchema": {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
                     "properties": {"text": {"type": "string"}}, "required": ["text"]},
     "annotations": {"readOnlyHint": True}},
    {"name": "delete all!", "description": "Deletes everything", "inputSchema": {"type": "object"}},
]
inited = False
def send(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
for line in sys.stdin:
    m = json.loads(line); mid = m.get("id"); meth = m.get("method"); p = m.get("params") or {}
    if mid is None:
        continue
    ver = (p.get("_meta") or {}).get("io.modelcontextprotocol/protocolVersion")
    res = lambda r: send({"jsonrpc": "2.0", "id": mid, "result": r})
    err = lambda c, t, d=None: send({"jsonrpc": "2.0", "id": mid, "error": {"code": c, "message": t, "data": d}})
    if mode == "silent" and meth == "server/discover":
        continue
    if mode in ("legacy", "silent"):
        if meth == "initialize":
            inited = True
            res({"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "L"}})
            continue
        if meth == "server/discover":
            err(-32601, "Method not found"); continue
        if not inited:
            err(-32002, "not initialized"); continue
    else:
        if meth == "initialize":
            err(-32601, "Method not found"); continue
        if ver != "2026-07-28":
            err(-32022, "Unsupported protocol version", {"supported": ["2026-07-28"], "requested": ver}); continue
        if meth == "server/discover":
            res({"resultType": "complete", "supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}},
                 "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "Fake", "version": "1"}},
                 "instructions": "Fake server"})
            continue
    if meth == "tools/list":
        if p.get("cursor"):
            res({"tools": TOOLS[1:]})
        else:
            res({"tools": TOOLS[:1], "nextCursor": "2"})
    elif meth == "tools/call":
        a = p.get("arguments") or {}
        if p["name"] == "echo":
            if a.get("ask") and "inputResponses" not in p:
                res({"resultType": "input_required", "inputRequests": {"q": {"method": "elicitation/create"}},
                     "requestState": "st"})
            elif a.get("ask"):
                res({"content": [{"type": "text", "text": "declined:" + p["inputResponses"]["q"]["action"]
                                  + ":" + p.get("requestState", "")}]})
            else:
                res({"content": [{"type": "text", "text": "echo: " + a.get("text", "")}]})
        else:
            res({"content": [{"type": "text", "text": "deleted"},
                             {"type": "image", "data": "AAAA", "mimeType": "image/png"}], "isError": False})
    else:
        err(-32601, "Method not found")
'''


def check(cond, text):
    global OK
    if not cond:
        raise AssertionError(text)
    OK += 1


def wait(cond, seconds=20.0):
    n = 0
    while not cond() and n < seconds * 10:
        rs.pump(0.1)
        n += 1
    return cond()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def legacy_http_server() -> str:
    """Alter Streamable-HTTP-Server (2025-06-18): Sitzung über Mcp-Session-Id, Antwort als SSE."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):  # noqa: N802
            msg = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            sid = self.headers.get("Mcp-Session-Id")
            if "id" not in msg:
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if msg["method"] == "initialize":
                result, headers = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                                   "serverInfo": {"name": "LegacyHTTP"}}, {"Mcp-Session-Id": "sess-1"}
            elif sid != "sess-1":
                body = json.dumps({"jsonrpc": "2.0", "id": None,
                                   "error": {"code": -32000, "message": "Bad Request: No valid session ID"}}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            elif msg["method"] == "tools/list":
                result, headers = {"tools": [{"name": "who", "inputSchema": {"type": "object"}}]}, {}
            else:
                result, headers = {"content": [{"type": "text", "text": "legacy-ok"}]}, {}
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b": ping\n\n")
            self.wfile.write(f"data: {json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': result})}\n\n"
                             .encode())
            self.close_connection = True

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/mcp"


def post(url, body, headers) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else {}


def test_pure() -> None:
    check(mcp.function_name({"name": "Mein Server"}, "delete all!") == "mcp_mein_server_delete_all_", "Funktionsname")
    check(len(mcp.function_name({"name": "x" * 50}, "y" * 80)) == 64, "Name höchstens 64")
    check(mcp.split_args('-y "C:\\Program Files\\x" a') [1].endswith("x"), "Argumente mit Anführungszeichen")
    check(mcp._header_value("abc") == "abc" and mcp._header_value("Grüße").startswith("=?base64?"), "Header-Wert")
    schema = {"type": "object", "properties": {"region": {"type": "string", "x-mcp-header": "Region"},
                                               "n": {"type": "object", "properties": {
                                                   "id": {"type": "integer", "x-mcp-header": "Id"}}}}}
    check(mcp.valid_header_schema(schema), "x-mcp-header gültig")
    check(mcp.param_headers(schema, {"region": "eu", "n": {"id": 4}}) == {"Mcp-Param-Region": "eu",
                                                                          "Mcp-Param-Id": "4"}, "Param-Header")
    bad = {"type": "object", "properties": {"l": {"type": "array", "items": {"type": "string",
                                                                              "x-mcp-header": "L"}}}}
    check(not mcp.valid_header_schema(bad), "x-mcp-header in items ungültig")
    check(not mcp.valid_header_schema({"type": "object", "properties": {"f": {"type": "number",
                                                                              "x-mcp-header": "F"}}}),
          "number nicht erlaubt")
    clean = mcp.clean_schema({"$schema": "x", "type": "object", "properties": {"a": {"x-mcp-header": "A",
                                                                                     "type": "string"}}})
    check("$schema" not in clean and "x-mcp-header" not in clean["properties"]["a"], "Schema bereinigt")
    check(mcp.clean_schema(None) == {"type": "object", "properties": {}}, "leeres Schema")
    check(mcp.is_read_only({"annotations": {"readOnlyHint": True}}, True), "vertraut + lesend")
    check(not mcp.is_read_only({"annotations": {"readOnlyHint": True}}, False), "nicht vertraut = ändernd")
    r = mcp.result_text({"content": [{"type": "text", "text": "a"}, {"type": "image", "data": "AAAA",
                                                                     "mimeType": "image/png"},
                                     {"type": "resource_link", "uri": "file:///x", "name": "x"}]})
    check("a" in r and "[image image/png, 3 bytes]" in r and "file:///x" in r, "Ergebnistext")
    check(mcp.result_text({"content": [], "structuredContent": {"k": 1}, "isError": True}).startswith("Error:"),
          "Fehlerergebnis")


def test_stdio(script: Path) -> None:
    for mode, modern in (("modern", True), ("legacy", False), ("silent", False)):
        c = mcp.Client({"transport": "stdio", "command": sys.executable, "args": ["-I", str(script), mode]})
        c.connect()
        check(c.modern is modern, f"stdio {mode}: Fassung erkannt")
        tools = c.tools()
        check([t["name"] for t in tools] == ["echo", "delete all!"], f"stdio {mode}: Seiten zusammengeführt")
        check(mcp.result_text(c.call_tool("echo", {"text": "hi"})) == "echo: hi", f"stdio {mode}: Aufruf")
        if modern:
            check(c.instructions == "Fake server" and c.version == mcp.MODERN_VERSION, "Discover-Daten")
            check(mcp.result_text(c.call_tool("echo", {"ask": True})) == "declined:decline:st",
                  "Rückfrage abgelehnt und neu gesendet")
        c.close()
    c = mcp.Client({"transport": "stdio", "command": sys.executable + "-gibtsnicht", "args": []})
    try:
        c.connect()
        check(False, "fehlender Befehl")
    except mcp.MCPError:
        check(True, "fehlender Befehl meldet Fehler")


def test_server_http(settings) -> None:
    seen = {}

    def read_fn(args, ctx):
        seen["read"] = args
        return {"host": "srv01.corp.example", "ip": "10.1.2.3", "note": "ok"}

    def change_fn(args, ctx):
        seen["change"] = args
        return "changed"
    functions.register(functions.Function("t_read", "Read test", read_fn, level=functions.LEVEL_READ,
                                          parameters={"type": "object", "properties": {"host": {"type": "string"}}}))
    functions.register(functions.Function("t_change", "Change test", change_fn, level=functions.LEVEL_CHANGE))
    functions.register(functions.Function("mcp_other_x", "foreign", lambda a, c: "x", level=1))
    answers = []
    host = mcps.FunctionHost(settings, confirm=lambda fn, args: answers.pop(0) if answers else False)
    names = [f.name for f in host.functions()]
    check("t_read" not in names, "Stufe 1: Lesen nicht angeboten")
    acc = dict(settings.get("ai_access") or {})
    acc["exceptions"] = {mcps.CONN_ID: 4}
    settings.set("ai_access", acc)
    names = [f.name for f in host.functions()]
    check("t_read" in names and "t_change" in names and "mcp_other_x" not in names,
          "Ausnahme MCP-Server: Stufe 4, keine fremden MCP-Werkzeuge")
    srv = mcps.Server(host, free_port(), "geheim")
    srv.start()
    check(json.loads(mcps.info_file().read_text())["port"] == srv.port, "Infodatei geschrieben")
    url = srv.url

    c = mcp.Client({"transport": "http", "url": url}, "geheim")
    c.connect()
    check(c.modern and c.info.get("name") == "OmniWrench", "Client <-> eigener Server: moderne Fassung")
    tools = {t["name"]: t for t in c.tools()}
    check(tools["t_read"]["annotations"]["readOnlyHint"] and not tools["t_change"]["annotations"]["readOnlyHint"],
          "Annotationen lesend/ändernd")
    out = mcp.result_text(c.call_tool("t_read", {}))
    check("srv01" not in out and "10.1.2.3" not in out, "Ergebnis verfremdet")
    data = json.loads(out)
    mcp.result_text(c.call_tool("t_read", {"host": data["host"]}))
    check(seen["read"]["host"] == "srv01.corp.example", "Platzhalter zurückübersetzt")
    answers.append(False)
    r = c.call_tool("t_change", {})
    check(r.get("isError") and "declined" in mcp.result_text(r) and "change" not in seen, "Änderung abgelehnt")
    answers.append(True)
    check(mcp.result_text(c.call_tool("t_change", {})) == "changed", "Änderung bestätigt")
    try:
        c.call_tool("gibts_nicht", {})
        check(False, "unbekanntes Werkzeug")
    except mcp.MCPError as e:
        check(e.code == -32602, "unbekanntes Werkzeug -32602")
    c.close()

    meta = {"io.modelcontextprotocol/protocolVersion": mcp.MODERN_VERSION}
    base = {"Authorization": "Bearer geheim"}
    st, body = post(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta}}, {})
    check(st == 401, "ohne Token 401")
    st, body = post(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta}},
                    {**base, "Origin": "https://evil.example"})
    check(st == 403, "fremder Origin 403")
    st, body = post(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta}}, base)
    check(st == 400 and body["error"]["code"] == -32020, "fehlende Header -32020")
    st, body = post(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"_meta": meta,
                                                                                       "name": "t_read"}},
                    {**base, "MCP-Protocol-Version": mcp.MODERN_VERSION, "Mcp-Method": "tools/call",
                     "Mcp-Name": "t_change"})
    check(st == 400 and body["error"]["code"] == -32020, "Mcp-Name passt nicht")
    old = {"io.modelcontextprotocol/protocolVersion": "2099-01-01"}
    st, body = post(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": old}},
                    {**base, "MCP-Protocol-Version": "2099-01-01", "Mcp-Method": "tools/list"})
    check(st == 400 and body["error"]["code"] == -32022 and mcp.MODERN_VERSION in body["error"]["data"]["supported"],
          "unbekannte Fassung -32022")
    st, body = post(url, {"jsonrpc": "2.0", "id": 1, "method": "nope", "params": {"_meta": meta}},
                    {**base, "MCP-Protocol-Version": mcp.MODERN_VERSION, "Mcp-Method": "nope"})
    check(st == 404 and body["error"]["code"] == -32601, "unbekannte Methode 404")
    st, body = post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {}}}, base)
    check(st == 200 and body["result"]["protocolVersion"] == "2025-06-18", "alter Client: initialize")
    st, body = post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {**base, "MCP-Protocol-Version": "2025-06-18"})
    check(st == 200 and "resultType" not in body["result"] and body["result"]["tools"], "alter Client: tools/list")
    st, _ = post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, base)
    check(st == 202, "Benachrichtigung 202")
    req = urllib.request.Request(url, headers=base)
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=5)
        check(False, "GET")
    except urllib.error.HTTPError as e:
        check(e.code == 405, "GET 405")

    # stdio-Brücke als eigener Prozess (wie Claude Desktop sie startet)
    env = dict(os.environ)
    proc = subprocess.run([sys.executable, str(ROOT / "main.py"), "--mcp-stdio"], env=env, timeout=60,
                          input=(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "server/discover",
                                             "params": {"_meta": {**meta, "io.modelcontextprotocol/clientInfo": {}}}})
                                 + "\n" + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                                      "params": {"_meta": meta, "name": "t_read",
                                                                 "arguments": {}}}) + "\n").encode(),
                          capture_output=True)
    lines = [json.loads(x) for x in proc.stdout.decode().splitlines() if x.strip()]
    check(len(lines) == 2 and lines[0]["result"]["supportedVersions"][0] == mcp.MODERN_VERSION,
          "Brücke: discover " + proc.stderr.decode()[-300:])
    check("ok" in lines[1]["result"]["content"][0]["text"], "Brücke: Werkzeugaufruf")
    bridge_client = mcp.Client({"transport": "stdio", "command": sys.executable,
                                "args": [str(ROOT / "main.py"), "--mcp-stdio"]})
    bridge_client.connect()
    check(bridge_client.modern and any(t["name"] == "t_read" for t in bridge_client.tools()),
          "Client über die Brücke")
    bridge_client.close()
    srv.stop()
    check(not mcps.info_file().exists(), "Infodatei entfernt")
    proc = subprocess.run([sys.executable, str(ROOT / "main.py"), "--mcp-stdio"], timeout=60, capture_output=True,
                          input=(json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/list"}) + "\n").encode())
    check("not running" in proc.stdout.decode(), "Brücke ohne Server: verständlicher Fehler")
    for n in ("t_read", "t_change", "mcp_other_x"):
        functions.unregister(n)

    legacy = mcp.Client({"transport": "http", "url": legacy_http_server()})
    legacy.connect()
    check(not legacy.modern and legacy.version == "2025-06-18", "alter HTTP-Server erkannt")
    check([t["name"] for t in legacy.tools()] == ["who"], "alter HTTP-Server: Werkzeuge (SSE, Sitzung)")
    check(mcp.result_text(legacy.call_tool("who", {})) == "legacy-ok", "alter HTTP-Server: Aufruf")
    legacy.close()


def main() -> int:
    shots = None
    if "--shots" in sys.argv:
        shots = Path(sys.argv[sys.argv.index("--shots") + 1])
        shots.mkdir(parents=True, exist_ok=True)
    paths.ensure_dirs()
    mcp.PROBE_TIMEOUT = 1.5
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    from omniwrench.app import apply_language
    from omniwrench.ui import theme
    apply_language(app, "de")
    theme.apply_theme(app, "dark")
    vault = Vault(paths.VAULT_FILE)
    vault.create(password="mcp-check")
    credentials.init(vault)
    settings = AppSettings()
    settings.set("check_updates_on_start", False)
    settings.set("repositories", [])
    work = Path(tempfile.mkdtemp(prefix="mcp_check_"))
    script = work / "fake_mcp.py"
    script.write_text(FAKE_STDIO, encoding="utf-8")

    test_pure()
    test_stdio(script)
    test_server_http(settings)

    # --- Gadgetron --------------------------------------------------------------------------------------
    manager = ToolManager(vault)
    import aikit
    tid = aikit.install(manager, "gadgetron")["gadgetron"]
    from omniwrench.ui.main_window import MainWindow
    win = MainWindow(settings, vault, manager)
    win.resize(1500, 900)
    win.show()
    rs.pump(0.5)
    tool = aikit.open_tool(win, tid, rs.pump)
    tab = tool.page
    check(tid == "ai.gadgetron" and tab.isVisible(), "Gadgetron geöffnet")
    server = dict(mcp.new_server("Fake"), command=sys.executable, args=["-I", str(script), "modern"])
    tab.save_servers([server])
    tab.connect_server(server)
    check(wait(lambda: (tab.status.get(server["id"]) or {}).get("state") == "ok"), "Fake-Server verbunden")
    fn = functions.get("mcp_fake_echo")
    check(fn is not None and fn.level == functions.LEVEL_CHANGE and fn.source == tid, "nicht vertraut: Stufe 4")
    check(fn.handler({"text": "x"}, functions.CallContext()) == "echo: x", "Werkzeug über Funktion")
    check(fn.summary({"text": "x"})["code"].strip().startswith("{"), "Bestätigung zeigt Argumente")
    server["trusted"] = True
    tab.save_servers([server])
    tab.connect_server(server)
    check(wait(lambda: functions.get("mcp_fake_echo") is not None
               and functions.get("mcp_fake_echo").level == functions.LEVEL_READ), "vertraut + lesend: Stufe 3")
    check(functions.get("mcp_fake_delete_all_").level == functions.LEVEL_CHANGE, "ohne Hinweis: Stufe 4")
    import omniwrench.ui.ai_panel as ap
    orig_exec = QDialog.exec
    QDialog.exec = lambda self: QDialog.DialogCode.Accepted
    tab.table.selectRow(0)
    tools_dlg = sys.modules[type(tab).__module__].ToolsDialog
    orig_disabled = tools_dlg.disabled
    tools_dlg.disabled = lambda self: ["delete all!"]
    tab.show_tools()
    tools_dlg.disabled = orig_disabled
    check(functions.get("mcp_fake_delete_all_") is None and functions.get("mcp_fake_echo") is not None,
          "Werkzeug abgewählt")
    check(tab.servers()[0]["disabled_tools"] == ["delete all!"], "Abwahl gespeichert")
    bad = dict(mcp.new_server("Kaputt"), command=sys.executable, args=["-c", "import sys; sys.exit(3)"])
    tab.save_servers(tab.servers() + [bad])
    tab.connect_server(bad)
    check(wait(lambda: (tab.status.get(bad["id"]) or {}).get("state") == "error"), "kaputter Server: Fehler")
    tab.render()
    check("⚠" in tab.table.item(1, 2).text(), "Fehler in der Tabelle")

    # Server über den Reiter
    tab.port.setValue(free_port())
    confirmed = []
    ap.ConfirmDialog.exec = lambda self: (confirmed.append(1), QDialog.DialogCode.Accepted)[1]
    tab.on.setChecked(True)
    check(tab.server is not None and tab.server.running and type(tab)._owner is tab, "Server läuft")
    check("127.0.0.1" in tab.server_status.text(), "Status zeigt Adresse")
    cfg = json.loads(sys.modules[type(tab).__module__].client_config("stdio", tab.server.url, "t"))
    check(cfg["mcpServers"]["omniwrench"]["args"][-1] == "--mcp-stdio", "Einrichtung stdio")
    tab._copy_config("vscode")
    check(json.loads(QApplication.clipboard().text())["servers"]["omniwrench"]["type"] == "http",
          "Einrichtung VS Code kopiert")
    c = mcp.Client({"transport": "http", "url": tab.server.url}, tab.server.token)
    c.connect()
    names = [t["name"] for t in c.tools()]
    check(names and not any(n.startswith("mcp_") for n in names), "Server reicht MCP-Werkzeuge nicht weiter")
    c.close()
    acc = dict(settings.get("ai_access") or {})
    if shots:
        win.grab().save(str(shots / "gadgetron.png"))
    QDialog.exec = orig_exec
    win.close_tool(next(n for n, o in win.open_tools.items() if o.tool_id == tid))
    rs.pump(0.3)
    check(type(tab)._owner is None and not mcps.info_file().exists(), "Server beim Schließen gestoppt")
    check(functions.get("mcp_fake_echo") is None, "Werkzeuge beim Schließen entfernt")
    settings.set("ai_access", acc)
    print(f"OK: {OK} Prüfungen")
    return 0


if __name__ == "__main__":
    sys.exit(main())

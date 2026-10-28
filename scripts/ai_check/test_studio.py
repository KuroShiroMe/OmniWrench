"""Clank – KI-Studio ohne echten Anbieter prüfen (Fake-Server mit vorgegebenen Funktionsaufrufen).

    python scripts/ai_check/test_studio.py [--shots ORDNER]

Hauptfenster mit dem Tool, Arbeitsbereich aus einem Temp-Ordner (mit Git, falls vorhanden), Projekte und Chats,
Funktionen studio_* über den Chat (Lesen ab Stufe 3, Schreiben/Befehl mit Bestätigung), Sperre ohne Freigabe,
Pfade außerhalb des Arbeitsbereichs, Online-URLs erkennen. --shots speichert Bildschirmfotos.
"""

from __future__ import annotations

import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import render_screenshots as rs  # noqa: E402  (Temp-Home, offscreen, pump)

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from omniwrench.ai import access, functions  # noqa: E402
from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.manifest import ToolManifest  # noqa: E402
from omniwrench.core.settings import AppSettings  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402

OK = 0
SCRIPT: list[dict] = []      # nächste Funktionsaufrufe des Fake-Assistenten
SEEN: list[dict] = []        # empfangene Anfragen


def check(cond, text):
    global OK
    if not cond:
        raise AssertionError(text)
    OK += 1


def fake_server() -> str:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802
            body = json.dumps({"data": [{"id": "fake"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            SEEN.append(body)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            last = body["messages"][-1]
            if last["role"] != "tool" and SCRIPT:
                call = SCRIPT.pop(0)
                chunks = [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c" + str(len(SEEN)),
                                                                  "function": {"name": call["name"],
                                                                               "arguments": json.dumps(call["args"])}}]}}]}]
            else:
                chunks = [{"choices": [{"delta": {"content": "Fertig."}}]}]
            for c in chunks:
                self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.close_connection = True

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/v1"


def tool_results() -> list[str]:
    out = []
    for m in SEEN[-1]["messages"]:
        if m["role"] == "tool":
            out.append(m["content"])
    return out


def ask(win, panel, text: str, calls: list[dict]) -> list[str]:
    SCRIPT[:] = calls
    SEEN.clear()
    panel.input.setPlainText(text)
    panel.send()
    rs.pump(0.2)
    end = 0
    while panel._running and end < 300:
        rs.pump(0.1)
        end += 1
    check(not panel._running, f"Antwort auf {text!r}")
    return tool_results()


def main() -> int:
    shots = None
    if "--shots" in sys.argv:
        shots = Path(sys.argv[sys.argv.index("--shots") + 1])
        shots.mkdir(parents=True, exist_ok=True)
    paths.ensure_dirs()
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    from omniwrench.app import apply_language
    from omniwrench.ui import ai_panel, theme
    apply_language(app, "de")
    theme.apply_theme(app, "dark")
    vault = Vault(paths.VAULT_FILE)
    vault.create(password="studio-check")
    credentials.init(vault)
    settings = AppSettings()
    settings.set("check_updates_on_start", False)
    settings.set("repositories", [])
    settings.set("ai_storage_mode", "central")
    settings.set("ai_storage_root", tempfile.mkdtemp(prefix="studio_data_"))
    manager = ToolManager(vault)
    source = ROOT / "tools" / "clank"
    manifest = ToolManifest.load(source)
    shutil.copytree(source, paths.TOOLS_DIR / manifest.id, ignore=shutil.ignore_patterns("__pycache__", "*.png"))
    manager.refresh()
    tid = manifest.id

    # Arbeitsbereich: Ordner mit Dateien (Git, wenn vorhanden)
    work = Path(tempfile.mkdtemp(prefix="studio_ws_"))
    (work / "scripts").mkdir()
    (work / "scripts" / "cleanup.ps1").write_text("# Aufräumen\nGet-ChildItem $env:TEMP | Remove-Item -WhatIf\n",
                                                  encoding="utf-8")
    (work / "README.md").write_text("# Demo\nServer dc01.corp.example (10.1.2.3)\n", encoding="utf-8")
    has_git = shutil.which("git") is not None
    if has_git:
        for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "Test"],
                    ["add", "."], ["commit", "-qm", "Start"]):
            subprocess.run(["git", "-C", str(work), *cmd], check=True, capture_output=True)

    from omniwrench.ai.connections import Connection, ConnectionStore
    store = ConnectionStore(settings, vault)
    store.save(Connection(id="fake", name="Testbot", provider="ollama", base_url=fake_server(), model="fake",
                          auth="none"))
    from omniwrench.ui.main_window import MainWindow
    win = MainWindow(settings, vault, manager)
    win.resize(1500, 900)
    win.show()
    rs.pump(0.5)
    win.open_tool(tid)
    rs.pump(0.5)
    entry = next(o for o in win.open_tools.values() if o.tool_id == tid)
    tool = entry.instance
    panel = tool.panel
    check(panel.embedded and not panel.hist_btn.isVisible(), "Chat eingebettet ohne eigenen Verlauf")
    check({"studio_list", "studio_read", "studio_write_file", "studio_run_command"} <= {f.name for f in functions.all_functions()},
          "Funktionen registriert")

    # Projekt mit Arbeitsbereich
    from omniwrench.ai.storage import Storage
    st = Storage(settings, vault)
    project = {"name": "Skripte", "instructions": "Nur PowerShell.", "workspace": []}
    st.save_project(project)
    tool.chats.reload()
    tool.set_project(project["id"])
    check(tool.project["id"] == project["id"] and tool.roots == [], "Projekt gewählt, leerer Arbeitsbereich")
    from importlib import import_module
    wsm = import_module(type(tool).__module__.rsplit(".", 1)[0] + ".workspace")
    tool.roots.append(wsm.new_root("git" if has_git else "folder", "demo", str(work)))
    tool.save_roots()
    check(st.load_project(project["id"])["workspace"][0]["name"] == "demo", "Arbeitsbereich im Projekt gespeichert")
    check(tool.ws_panel.level_hint.isVisibleTo(tool.ws_panel), "Hinweis: Stufe zu niedrig")
    check(access.level(settings, tid) == 1, "Standardstufe 1")

    # Stufe 1: Studio-Funktionen nicht angeboten
    ask(win, panel, "Was liegt im Arbeitsbereich?", [])
    offered = {t["function"]["name"] for t in SEEN[-1].get("tools") or []}
    check("studio_read" not in offered and "studio_workspace" not in offered, "ohne Freigabe keine Studio-Funktionen")
    check("demo" in SEEN[-1]["messages"][0]["content"], "Systemtext nennt den Arbeitsbereich")

    # Stufe 4 für das Tool (wie auf der Seite KI-Zugriff)
    cfg = settings.get("ai_access_tools") or {}
    cfg[tid] = {"level": 4, "pseudo": None, "exceptions": {}}
    settings.set("ai_access_tools", cfg)
    tool._update_level()
    check(not tool.ws_panel.level_hint.isVisibleTo(tool.ws_panel), "Hinweis weg ab Stufe 3")
    res = ask(win, panel, "Liste die Skripte", [{"name": "studio_list", "args": {"path": "demo", "depth": 2}}])
    check(res and "demo/scripts/cleanup.ps1" in res[-1], f"studio_list {res}")
    res = ask(win, panel, "Lies die README", [{"name": "studio_read", "args": {"path": "demo/README.md"}}])
    check(res and "NET1.3" in res[-1] and "10.1.2.3" not in res[-1] and "HOST-1" in res[-1], f"Datei verfremdet gesendet {res}")
    res = ask(win, panel, "Suche Remove-Item", [{"name": "studio_search", "args": {"query": "remove-item"}}])
    check(res and "cleanup.ps1" in res[-1], "Suche")
    res = ask(win, panel, "Ausbruch", [{"name": "studio_read", "args": {"path": "demo/../../etc/passwd"}}])
    check(res and "outside the workspace" in res[-1], f"Pfad außerhalb abgelehnt {res}")

    # Schreiben mit Bestätigung (abgelehnt, dann erlaubt)
    seen_dialogs = []

    def fake_exec(answer):
        def run(self):
            seen_dialogs.append(self)
            if shots:
                self.grab().save(str(shots / f"confirm_{len(seen_dialogs)}.png"))
            return QDialog.DialogCode.Accepted if answer else QDialog.DialogCode.Rejected
        return run
    ai_panel.ConfirmDialog.exec = fake_exec(False)
    new = "# Aufräumen (nur Vorschau)\nGet-ChildItem $env:TEMP | Remove-Item -WhatIf -Recurse\n"
    write = {"name": "studio_write_file", "args": {"path": "demo/scripts/cleanup.ps1", "content": new,
                                                   "explanation": "Unterordner mit -Recurse einbeziehen."}}
    res = ask(win, panel, "Ändere das Skript", [write])
    check(seen_dialogs and "declined" in res[-1], f"abgelehnt {res[-1]}")
    check("-Recurse" not in (work / "scripts" / "cleanup.ps1").read_text(encoding="utf-8"), "Datei unverändert")
    ai_panel.ConfirmDialog.exec = fake_exec(True)
    res = ask(win, panel, "Ändere das Skript", [write])
    check("-Recurse" in (work / "scripts" / "cleanup.ps1").read_text(encoding="utf-8"), f"Datei geschrieben {res}")
    if has_git:
        res = ask(win, panel, "Git-Status", [{"name": "studio_git", "args": {"action": "status", "path": "demo"}}])
        check("cleanup.ps1" in res[-1], f"Git-Status {res[-1]}")
    cmd = "echo studio-ok" if sys.platform != "win32" else "Write-Output studio-ok"
    res = ask(win, panel, "Befehl", [{"name": "studio_run_command",
                                      "args": {"command": cmd, "explanation": "Test", "folder": "demo"}}])
    check("studio-ok" in res[-1], f"Befehl ausgeführt {res[-1]}")
    check(tool.viewer.isVisible() and "studio-ok" in tool.viewer.text.toPlainText(), "Ausgabe in der Ansicht")
    if shots:
        win.grab().save(str(shots / "studio.png"))
    tool.side.setCurrentIndex(1)
    top = tool.ws_panel.tree.topLevelItem(0)
    top.setExpanded(True)
    rs.pump(0.2)
    check(top.childCount() >= 2, "Baum des Arbeitsbereichs")
    tool.show_file("demo/scripts/cleanup.ps1")
    check("-Recurse" in tool.viewer.text.toPlainText(), "Dateiansicht")
    if shots:
        win.grab().save(str(shots / "studio_ws.png"))
    tool.side.setCurrentIndex(0)
    # Chat liegt im Projekt
    threads = st.list_threads(project["id"])
    check(threads, "Chats im Projekt gespeichert")
    tool.chats.reload()
    tool.open_thread(threads[-1]["id"], project["id"])
    check(panel.thread["id"] == threads[-1]["id"], "Chat aus der Seitenleiste geöffnet")
    # Online-URLs
    rm = import_module(type(tool).__module__.rsplit(".", 1)[0] + ".remote")
    check(rm.parse_url("https://github.com/KuroShiroMe/OmniWrench.git")["repo"] == "OmniWrench", "GitHub-URL")
    g = rm.parse_url("https://gitlab.example.com/infra/team/scripts/-/tree/main")
    check(g["provider"] == "gitlab" and g["owner"] == "infra/team" and g["repo"] == "scripts", f"GitLab-URL {g}")
    a = rm.parse_url("https://dev.azure.com/contoso/Ops/_git/tools")
    check(a["provider"] == "azure" and a["project"] == "Ops" and a["repo"] == "tools", "Azure-URL")
    # Schließen entfernt die Funktionen
    win.close_tool(next(n for n, o in win.open_tools.items() if o.tool_id == tid))
    rs.pump(0.3)
    check(not [f for f in functions.all_functions() if f.name.startswith("studio_")], "Funktionen entfernt")
    print(f"OK: {OK} Prüfungen")
    return 0


if __name__ == "__main__":
    sys.exit(main())

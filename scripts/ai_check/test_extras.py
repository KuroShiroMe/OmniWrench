"""Clank-Extras prüfen: Vorlagen, Dokumente, Bildschirmfoto, Zeitpläne (Fake-Assistent).

    python scripts/ai_check/test_extras.py [--shots ORDNER]
"""

from __future__ import annotations

import datetime as dt
import http.server
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import render_screenshots as rs  # noqa: E402  (Temp-Home, offscreen, pump)

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.settings import AppSettings  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402

OK = 0
SEEN: list[dict] = []
REPLY = {"text": "# Drucker einrichten\n\n1. Treiber installieren\n2. Testseite drucken"}


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
            text = REPLY["text"]
            for part in (text[:7], text[7:]):
                self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': part}}]})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.close_connection = True

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/v1"


def rs_pattern(pix: QPixmap) -> QPixmap:
    """Bild mit Inhalt (nicht einfarbig)."""
    out = QPixmap(pix)
    p = QPainter(out)
    p.fillRect(0, 0, 50, 50, QColor("white"))
    p.end()
    return out


def wait(cond, seconds=20.0):
    n = 0
    while not cond() and n < seconds * 10:
        rs.pump(0.1)
        n += 1
    return cond()


def test_schedule_logic(sm) -> None:
    mon = dt.datetime(2026, 11, 2, 7, 0)       # Montag
    j = sm.new_job("Bericht", "Fasse zusammen", "daily", "08:00")
    check(dt.datetime.fromtimestamp(sm.next_run(j, mon)) == dt.datetime(2026, 11, 2, 8, 0), "täglich heute 8:00")
    check(dt.datetime.fromtimestamp(sm.next_run(j, mon.replace(hour=9))) == dt.datetime(2026, 11, 3, 8, 0),
          "täglich morgen")
    j.update(kind="weekly", weekdays=[4], time="17:30")
    check(dt.datetime.fromtimestamp(sm.next_run(j, mon)) == dt.datetime(2026, 11, 6, 17, 30), "wöchentlich Freitag")
    j.update(kind="once", date="2026-11-01")
    check(sm.next_run(j, mon) is None, "einmalig vorbei")
    j.update(kind="interval", hours=4, last_run=mon.timestamp())
    check(dt.datetime.fromtimestamp(sm.next_run(j, mon)) == dt.datetime(2026, 11, 2, 11, 0), "alle 4 h")
    missed = dict(sm.new_job("x", "y"), next_run=mon.timestamp() - 3600, catch_up=False)
    check(sm.plan(missed, mon.timestamp(), opened=True)["next_run"] > mon.timestamp(), "verpasst ohne Nachholen")
    missed["catch_up"] = True
    p = sm.plan(missed, mon.timestamp(), opened=True)
    check(p in sm.due([p], mon.timestamp()), "verpasst mit Nachholen fällig")
    once = dict(sm.new_job("o", "p", "once"), date="2026-11-02", time="08:00")
    after = sm.after_run(once, mon.timestamp(), "ok", "t1")
    check(not after["enabled"] and after["last_thread"] == "t1", "einmalig danach aus")
    check(sm.describe(dict(j, kind="weekly", weekdays=[0, 4], time="08:00"), lambda k, **kw: k + str(kw)),
          "Beschreibung")


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
    from omniwrench.ui import theme
    apply_language(app, "de")
    theme.apply_theme(app, "dark")
    vault = Vault(paths.VAULT_FILE)
    vault.create(password="extras-check")
    credentials.init(vault)
    settings = AppSettings()
    settings.set("check_updates_on_start", False)
    settings.set("repositories", [])
    settings.set("ai_storage_mode", "central")
    data_root = Path(tempfile.mkdtemp(prefix="extras_data_"))
    settings.set("ai_storage_root", str(data_root))
    manager = ToolManager(vault)
    import aikit
    ids = aikit.install(manager, "clank", "infobot", "orvus")
    tid = ids["clank"]
    from omniwrench.ai.connections import Connection, ConnectionStore
    store = ConnectionStore(settings, vault)
    store.save(Connection(id="bot", name="Testbot", provider="ollama", base_url=fake_server(), model="f",
                          auth="none"))
    from omniwrench.ui.main_window import MainWindow
    win = MainWindow(settings, vault, manager)
    win.resize(1500, 900)
    win.show()
    rs.pump(0.5)
    win.open_tool(tid)
    rs.pump(0.5)
    tool = next(o for o in win.open_tools.values() if o.tool_id == tid).instance
    pkg = type(tool).__module__.rsplit(".", 1)[0]
    tm, shot_mod = (sys.modules[pkg + n] for n in (".templates", ".screenshot"))
    check(not hasattr(tool, "modes") and tool.context.manifest.version >= "1.1.0", "Clank ohne Reiter (nur Chat)")

    # Vorlagen
    check(tm.placeholders("A {{Skript}} B {{ Server }} {{Skript}}") == ["Skript", "Server"], "Platzhalter")
    check(tm.fill("x {{Skript}} y", {"Skript": "Get-Date"}) == "x Get-Date y", "Füllen")
    panel = tool.templates
    check(panel.list.count() == len(tm.BUILTIN) and "{{Skript}}" in panel.list.item(0).data(Qt.ItemDataRole.UserRole)["text"],
          "mitgelieferte Vorlagen")
    tm.FillDialog.exec = lambda self: (self.fields["Skript"].setPlainText("Get-Service | Stop-Service"),
                                       QDialog.DialogCode.Accepted)[-1]
    panel.apply(panel.list.item(0).data(Qt.ItemDataRole.UserRole))
    check("Get-Service | Stop-Service" in tool.panel.input.toPlainText() and "{{" not in tool.panel.input.toPlainText(),
          "Vorlage im Eingabefeld")
    tm.TemplateDialog.exec = lambda self: (self.name.setText("Eigene"), self.text.setPlainText("Hallo {{Name}}"),
                                           QDialog.DialogCode.Accepted)[-1]
    panel.new()
    check(panel.list.count() == len(tm.BUILTIN) + 1 and tool.context.settings.get("templates")[0]["name"] == "Eigene",
          "eigene Vorlage gespeichert")
    tool.panel.input.clear()

    # Dokumente
    docs = aikit.open_tool(win, ids["infobot"], rs.pump).page
    check(docs.stack.currentIndex() == 1 and docs.conn_box.count() == 1, "Dokumente bereit")
    SEEN.clear()
    docs.editor.setPlainText("Server 10.1.2.3 im Büro")
    check(docs.ask(False, "Anleitung Drucker", "guide", use_existing=True), "Schreiben gestartet")
    check(wait(lambda: not docs.running), "Dokument fertig")
    check(docs.editor.toPlainText().startswith("# Drucker einrichten"), f"Text im Editor {docs.editor.toPlainText()!r}")
    sent = json.dumps(SEEN[-1])
    check("10.1.2.3" not in sent and "NET1.3" in sent, "Entwurf verfremdet gesendet")
    check(docs.path is not None and docs.path.exists() and docs.path.parent.name == "Documents", "als Markdown gespeichert")
    check(not SEEN[-1].get("tools"), "keine Funktionen")
    # Überarbeiten der Markierung
    REPLY["text"] = "2. Testseite drucken und prüfen"
    cur = docs.editor.textCursor()
    start = docs.editor.toPlainText().index("2. Testseite")
    cur.setPosition(start)
    cur.setPosition(len(docs.editor.toPlainText()), cur.MoveMode.KeepAnchor)
    docs.editor.setTextCursor(cur)
    check(docs.ask(True, "genauer"), "Überarbeiten gestartet")
    check(wait(lambda: not docs.running), "Überarbeitung fertig")
    text = docs.editor.toPlainText()
    check("1. Treiber installieren" in text and "und prüfen" in text, f"nur Markierung ersetzt {text!r}")
    out = Path(tempfile.mkdtemp(prefix="extras_export_"))
    for fmt in ("html", "pdf", "odt"):
        target = docs.export(fmt, str(out / f"doc.{fmt}"))
        check(target and Path(target).stat().st_size > 100, f"Export {fmt}")
    check(b"%PDF" in (out / "doc.pdf").read_bytes()[:8], "PDF gültig")
    if shots:
        win.grab().save(str(shots / "infobot.png"))
    docs.to_chat()
    rs.pump(0.2)
    check(win.ai_panel.attachments and win.ai_panel.attachments[-1]["kind"] == "text", "Dokument an die Chatleiste")
    win.ai_panel.attachments = []
    aikit.open_tool(win, tid, rs.pump)

    # Bildschirmfoto: Speichern + Bereichsauswahl (offscreen ist der Bildschirm leer)
    pix = QPixmap(400, 300)
    pix.fill(QColor("#336699"))
    blank = QPixmap(50, 50)
    blank.fill(QColor("black"))
    check(shot_mod.is_blank(blank) and not shot_mod.is_blank(rs_pattern(pix)), "leeres Bild erkannt")
    shooter = shot_mod.Screenshot(None, tool.storage, tool.tr)
    saved = shooter.save(pix)
    check(saved.exists() and json.loads(Path(str(saved) + ".json").read_text(encoding="utf-8"))["screenshot"],
          "Bildschirmfoto gespeichert")
    picker = shot_mod.RegionPicker(pix, "hint")
    got = []
    picker.picked.connect(got.append)
    for kind, pos in ((QMouseEvent.Type.MouseButtonPress, QPointF(10, 10)),
                      (QMouseEvent.Type.MouseMove, QPointF(110, 60)),
                      (QMouseEvent.Type.MouseButtonRelease, QPointF(110, 60))):
        ev = QMouseEvent(kind, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        {QMouseEvent.Type.MouseButtonPress: picker.mousePressEvent, QMouseEvent.Type.MouseMove: picker.mouseMoveEvent,
         QMouseEvent.Type.MouseButtonRelease: picker.mouseReleaseEvent}[kind](ev)
    check(got and got[0] is not None and got[0].width() == 100 and got[0].height() == 50, "Bereich gewählt")
    tool.image_to_chat(str(saved))
    check(tool.panel.attachments and tool.panel.attachments[-1]["kind"] == "image", "Bild im Chat")

    # Zeitpläne
    orvus = aikit.open_tool(win, ids["orvus"], rs.pump)
    sm = sys.modules[type(orvus).__module__.rsplit(".", 1)[0] + ".schedule"]
    test_schedule_logic(sm)
    plans = orvus.page
    job = sm.new_job("DHCP-Bericht", "Fasse die DHCP-Befunde zusammen.")
    plans.save_jobs([sm.plan(job, __import__("time").time())])
    plans.table.selectRow(0)
    REPLY["text"] = "Keine Befunde."
    SEEN.clear()
    plans.run_now()
    check(wait(lambda: not plans._busy), "Zeitplan gelaufen")
    j = plans.jobs()[0]
    check(j["last_status"] == "ok" and j["last_thread"], f"Status {j['last_status']}")
    th = orvus.services.storage.load_thread(j["last_thread"])
    check(th and th["messages"][-1]["content"] == "Keine Befunde." and th["title"].startswith("⏰"), "Chat gespeichert")
    check("nobody is watching" in SEEN[-1]["messages"][0]["content"], "Systemtext für geplante Läufe")
    plans.open_result()
    rs.pump(0.2)
    check(win.ai_panel.thread and win.ai_panel.thread["id"] == j["last_thread"], "Ergebnis in der Chatleiste geöffnet")
    # fälliger Lauf über tick()
    plans.save_jobs([dict(j, next_run=1, enabled=True)])
    sm.ScheduleTab._owner = None
    plans.tick()
    check(wait(lambda: not plans._busy) and plans.jobs()[0]["last_run"] > j["last_run"], "fälliger Lauf über tick")
    if shots:
        win.grab().save(str(shots / "orvus.png"))
        aikit.open_tool(win, tid, rs.pump)
        tool.side.setCurrentIndex(2)
        rs.pump(0.2)
        win.grab().save(str(shots / "clank_templates.png"))
    for t in ids.values():
        aikit.close_tool(win, t, rs.pump)
    check(sm.ScheduleTab._owner is None, "Zeitpläne beim Schließen freigegeben")
    print(f"OK: {OK} Prüfungen")
    return 0


if __name__ == "__main__":
    sys.exit(main())

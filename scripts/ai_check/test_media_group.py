"""Clank: Bilder und Gruppenchat ohne echte Anbieter prüfen (Fake-Server für alle Bild-Schnittstellen).

    python scripts/ai_check/test_media_group.py [--shots ORDNER]

Bild-Schnittstellen (OpenAI-kompatibel inkl. Vorlagebild, Gemini, Black Forest Labs, fal.ai, Replicate,
Stability, Ideogram, MiniMax) mit Schlüssel-Kopfzeilen und Abfragen; Speichern mit JSON-Beschreibung;
Gruppen-Ablauf mit allen Bremsen; Reiter „Bilder“ und „Gruppenchat“ im Hauptfenster.
"""

from __future__ import annotations

import base64
import http.server
import json
import shutil
import struct
import sys
import tempfile
import threading
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import render_screenshots as rs  # noqa: E402  (Temp-Home, offscreen, pump)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.manifest import ToolManifest  # noqa: E402
from omniwrench.core.settings import AppSettings  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402

OK = 0
SEEN: list[tuple[str, str, dict, bytes]] = []    # (Methode, Pfad, Kopfzeilen, Inhalt)
CHAT_MODE = {"agree": False}


def check(cond, text):
    global OK
    if not cond:
        raise AssertionError(text)
    OK += 1


def png(w: int = 4, h: int = 3) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x80\x40\xc0" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG = png()
B64 = base64.b64encode(PNG).decode()


def fake_server() -> str:
    polls = {"bfl": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, data, ctype="application/json", status=200):
            body = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def base(self) -> str:
            return f"http://127.0.0.1:{self.server.server_port}"

        def do_GET(self):  # noqa: N802
            p = self.path
            SEEN.append(("GET", p, dict(self.headers), b""))
            if p.startswith("/files/"):
                return self._send(PNG, "image/png")
            if p.startswith("/bfl/poll"):
                polls["bfl"] += 1
                if polls["bfl"] < 2:
                    return self._send({"status": "Pending"})
                return self._send({"status": "Ready", "result": {"sample": self.base() + "/files/bfl.png"}})
            if p == "/fal/status":
                return self._send({"status": "COMPLETED"})
            if p == "/fal/result":
                return self._send({"images": [{"url": self.base() + "/files/fal.png"}]})
            if p == "/rep/pred":
                return self._send({"status": "succeeded", "output": [self.base() + "/files/rep.png"]})
            return self._send({"data": [{"id": "fake"}]})

        def do_POST(self):  # noqa: N802
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            p = self.path
            SEEN.append(("POST", p, dict(self.headers), raw))
            body = {}
            if (self.headers.get("Content-Type") or "").startswith("application/json"):
                body = json.loads(raw or b"{}")
            if p.endswith("/images/generations"):
                return self._send({"data": [{"b64_json": B64, "revised_prompt": "rev"}] * int(body.get("n", 1))})
            if p.endswith("/images/edits"):
                return self._send({"data": [{"b64_json": B64}]})
            if ":generateContent" in p:
                return self._send({"candidates": [{"content": {"parts": [
                    {"text": "hier"}, {"inlineData": {"mimeType": "image/png", "data": B64}}]}}]})
            if p.startswith("/bfl/"):
                return self._send({"id": "j1", "polling_url": self.base() + "/bfl/poll"})
            if p.startswith("/fal/"):
                return self._send({"request_id": "r1", "status_url": self.base() + "/fal/status",
                                   "response_url": self.base() + "/fal/result"})
            if p.startswith("/rep/"):
                return self._send({"status": "starting", "urls": {"get": self.base() + "/rep/pred"}})
            if p.startswith("/stab/"):
                return self._send(PNG, "image/png")
            if p.startswith("/ideo/"):
                return self._send({"data": [{"url": self.base() + "/files/ideo.png"}]})
            if p.startswith("/mm/"):
                return self._send({"data": {"image_base64": [B64]}, "base_resp": {"status_code": 0}})
            if p.endswith("/chat/completions"):
                system = body["messages"][0]["content"]
                name = system.split('"')[1]
                n = sum(1 for m in body["messages"] if m["role"] == "assistant")
                text = f"Beitrag {n + 1} von {name}: Punkt {len(body['messages'])} zu NET1.3."
                if "summarize" in system.lower() or "Summarize" in system:
                    text = "Zusammenfassung: alles klar."
                elif CHAT_MODE["agree"]:
                    text += " [DONE]"
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for part in (text[:10], text[10:]):
                    self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': part}}]})}\n\n".encode())
                usage = {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
                self.wfile.write(f"data: {json.dumps(usage)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.close_connection = True
                return None
            return self._send({"error": "unknown"}, status=404)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}"


def last_post(prefix: str):
    return next(s for s in reversed(SEEN) if s[0] == "POST" and s[1].startswith(prefix))


def test_media(store, base: str, storage) -> None:
    from omniwrench.ai import media
    from omniwrench.ai.connections import Connection
    cases = [  # (Anbieter, Basis, Modell, Pfadanfang, Schlüssel-Kopfzeile)
        ("xai", base + "/v1", "grok-imagine-image", "/v1/images/generations", ("Authorization", "Bearer k-xai")),
        ("gemini", base + "/v1beta/openai", "gemini-nano-banana-2.1", "/v1beta/models/gemini-nano-banana-2.1",
         ("x-goog-api-key", "k-gemini")),
        ("bfl", base + "/bfl", "flux-2-pro", "/bfl/flux-2-pro", ("x-key", "k-bfl")),
        ("fal", base + "/fal", "fal-ai/flux-2-pro", "/fal/fal-ai/flux-2-pro", ("Authorization", "Key k-fal")),
        ("replicate", base + "/rep", "black-forest-labs/flux-2-pro", "/rep/models/black-forest-labs",
         ("Authorization", "Bearer k-replicate")),
        ("stability", base + "/stab", "core", "/stab/stable-image/generate/core", ("Authorization", "Bearer k-stability")),
        ("ideogram", base + "/ideo", "V_3_TURBO", "/ideo/ideogram-v3/generate", ("Api-Key", "k-ideogram")),
        ("minimax", base + "/mm", "image-01", "/mm/image_generation", ("Authorization", "Bearer k-minimax")),
    ]
    for provider, url, model, path, (hname, hval) in cases:
        conn = Connection(id="m-" + provider, name=provider, provider=provider, base_url=url, model="x")
        store.save(conn)
        store.set_secrets(conn.id, {"api_key": "k-" + provider})
        check(media.supports(conn, "image"), f"{provider}: Bilder unterstützt")
        items = media.generate_image(store, conn, media.Request("Ein Serverraum bei Nacht", model, "16:9", 1))
        check(items and items[0].data == PNG and items[0].mime == "image/png", f"{provider}: Bild erhalten")
        sent = last_post(path)
        headers = {k.lower(): v for k, v in sent[2].items()}
        check(headers.get(hname.lower()) == hval, f"{provider}: Kopfzeile {hname} {headers}")
        if provider == "gemini":
            body = json.loads(sent[3])
            check(body["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9", "Gemini: Format")
        if provider == "stability":
            check(b'name="aspect_ratio"' in sent[3] and b"16:9" in sent[3], "Stability: Multipart")
        if provider == "ideogram":
            check(b"TURBO" in sent[3] and b"16x9" in sent[3], "Ideogram: Turbo + Format")
        if provider == "bfl":
            body = json.loads(sent[3])
            check(body["width"] == 1344 and body["height"] == 768, "BFL: Pixel aus Format")
    # OpenAI-kompatibel mit Anzahl und Vorlagebild
    xai = store.get("m-xai")
    items = media.generate_image(store, xai, media.Request("Logo", "grok-imagine-image", "1:1", 3))
    check(len(items) == 3 and items[0].meta.get("revised_prompt") == "rev", "Anzahl 3 + umformuliert")
    items = media.generate_image(store, xai, media.Request("Logo", "m", "1:1", 1,
                                                           references=[{"mime": "image/png", "data": PNG}]))
    sent = last_post("/v1/images/edits")
    check(b'name="image[]"' in sent[3] and PNG in sent[3], "Vorlagebild als Multipart")
    # Speichern
    path = media.save(storage, "image", items[0], {"prompt": "Logo für die IT", "model": "m"})
    check(path.exists() and path.suffix == ".png" and path.read_bytes() == PNG, "Bild gespeichert")
    meta = media.read_meta(path)
    check(meta["prompt"] == "Logo für die IT" and meta["kind"] == "image", "JSON-Beschreibung")
    check(path in media.list_files(storage, "image"), "Liste der Bilder")
    # Ohne Bild-Schnittstelle
    c = Connection(id="m-anth", name="Claude", provider="anthropic")
    check(not media.supports(c, "image"), "Anthropic ohne Bilder")


def test_group_engine(group) -> None:
    """Bremsen des Ablaufs mit einer Fake-Chatfunktion."""
    parts = [group.new_participant("a", "Alpha", "Pro"), group.new_participant("b", "Beta", "Contra")]

    def run(opts, reply, pause=lambda r: True, pending=None):
        thread = group.new_thread("Sollen wir umstellen?", parts, opts)
        calls = []

        def chat_fn(p, system, msgs, on_text, stop):
            calls.append((p["name"], system, msgs))
            text = reply(p, len(calls), system)
            for i in range(0, len(text), 50):
                on_text(text[i:i + 50])
                if stop.is_set():
                    from omniwrench.ai.http import Cancelled
                    raise Cancelled()
            return {"text": text, "usage": {"input": 100, "output": 50}}
        hooks = group.GroupHooks(pause=pause, pending_user=pending or (lambda: []))
        reason = group.GroupRun(thread, chat_fn, hooks, threading.Event()).run()
        return reason, thread, calls

    words = ("Backup", "Patchen", "Firewall", "Monitoring", "Rollen", "Schulung", "Inventar", "Lizenzen",
             "Netzplan", "Notfall", "Zertifikate", "Protokolle")

    def uniq(p, n, s):
        return f"{p['name']} zu Punkt {n}: " + " ".join(words[(n * k) % len(words)] for k in range(1, 12))
    reason, t, calls = run({"rounds": 2, "summary": False, "stop_on_agree": False}, uniq)
    check(reason == "rounds" and len(calls) == 4, f"2 Runden x 2 ({reason}, {len(calls)})")
    check("\n\n[Alpha]: " in calls[1][2][-1]["content"] and calls[2][2][-1]["role"] == "user",
          "Verlauf aus Sicht des Teilnehmers")
    check(any(m["role"] == "assistant" for m in calls[2][2]), "eigene Beiträge als assistant")
    check("Pro" in calls[0][1] and "Beta" in calls[0][1], "Systemtext mit Rolle und anderen")
    reason, t, calls = run({"rounds": 10, "max_messages": 3, "summary": True}, uniq)
    check(reason == "max_messages" and sum(1 for m in t["messages"] if m["role"] == "assistant") == 4,
          "Bremse Beiträge + Zusammenfassung")
    check(t["messages"][-1].get("summary") and "Summarize" in calls[-1][1], "Zusammenfassung am Ende")
    reason, t, _ = run({"rounds": 5, "summary": False},
                       lambda p, n, s: f"Einverstanden, Variante B {p['name']}. [DONE]")
    check(reason == "agree" and len([m for m in t["messages"] if m.get("agree")]) == 2, "Einigkeit")
    check(all("[DONE]" not in m.get("content", "") for m in t["messages"]), "Marke entfernt")
    reason, t, _ = run({"rounds": 5, "summary": False, "stop_on_agree": False},
                       lambda p, n, s: "Ich wiederhole immer denselben Satz zur Umstellung der Clients auf das neue System.")
    check(reason == "repeat", f"Wiederholung ({reason})")
    reason, t, _ = run({"rounds": 1, "max_chars": 200, "summary": False}, lambda p, n, s: "x" * 2000)
    cut = [m for m in t["messages"] if m.get("cut")]
    check(len(cut) == 2 and len(cut[0]["content"]) <= 245, "Länge gekürzt")
    reason, t, _ = run({"rounds": 10, "token_budget": 1000, "summary": False, "stop_on_agree": False}, uniq)
    check(reason == "token_budget", f"Token-Budget ({reason})")
    paused = []
    reason, t, _ = run({"rounds": 3, "pause_each_round": True, "summary": False}, uniq,
                       pause=lambda r: paused.append(r) or r < 2)
    check(paused == [1, 2] and reason == "stopped", f"Pause nach Runden {paused} {reason}")
    queue = [["Bitte auch Kosten beachten."]]
    reason, t, calls = run({"rounds": 1, "summary": False}, uniq, pending=lambda: queue.pop() if queue else [])
    check(t["messages"][1]["role"] == "user" and "Kosten" in calls[0][2][-1]["content"], "Einwurf vor Beitrag")
    clock = iter([0, 0, 0, 700, 700, 700, 700])
    thread = group.new_thread("Zeit", parts, {"time_limit": 10, "summary": False})
    hooks = group.GroupHooks(clock=lambda: next(clock, 9999))
    r = group.GroupRun(thread, lambda p, s, m, o, st: {"text": "a" + p["id"]}, hooks, threading.Event()).run()
    check(r == "time_limit", f"Zeitlimit ({r})")
    o = group.options({"rounds": 999, "mode": "nonsense", "pause_each_round": 1})
    check(o["rounds"] == 30 and o["mode"] == "discussion" and o["pause_each_round"] is True, "Optionen begrenzt")


def wait(cond, seconds=20.0):
    n = 0
    while not cond() and n < seconds * 10:
        rs.pump(0.1)
        n += 1
    return cond()


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
    vault.create(password="media-check")
    credentials.init(vault)
    settings = AppSettings()
    settings.set("check_updates_on_start", False)
    settings.set("repositories", [])
    settings.set("ai_storage_mode", "central")
    settings.set("ai_storage_root", tempfile.mkdtemp(prefix="media_data_"))
    manager = ToolManager(vault)
    source = ROOT / "tools" / "clank"
    manifest = ToolManifest.load(source)
    shutil.copytree(source, paths.TOOLS_DIR / manifest.id, ignore=shutil.ignore_patterns("__pycache__", "*.png"))
    manager.refresh()
    tid = manifest.id

    from omniwrench.ai.connections import Connection, ConnectionStore
    from omniwrench.ai.storage import Storage
    store = ConnectionStore(settings, vault)
    storage = Storage(settings, vault)
    base = fake_server()
    test_media(store, base, storage)
    sys.path.insert(0, str(source.parent))
    import clank.group as group  # noqa: E402
    test_group_engine(group)

    # Oberfläche: nur Chat-Bots + ein Bildanbieter
    for c in store.list():
        if c.id != "m-xai":
            store.remove(c.id)
    store.save(Connection(id="bot1", name="Bot Eins", provider="ollama", base_url=base + "/v1", model="f",
                          auth="none"))
    store.save(Connection(id="bot2", name="Bot Zwei", provider="ollama", base_url=base + "/v1", model="f",
                          auth="none"))
    from omniwrench.ui.main_window import MainWindow
    win = MainWindow(settings, vault, manager)
    win.resize(1500, 900)
    win.show()
    rs.pump(0.5)
    win.open_tool(tid)
    rs.pump(0.5)
    tool = next(o for o in win.open_tools.values() if o.tool_id == tid).instance
    check(tool.modes.count() >= 5, "Reiter Chat, Bilder, Musik, Video, Gruppenchat")

    # Bilder
    tool.modes.setCurrentWidget(tool.images)
    rs.pump(0.2)
    img = tool.images
    check(img.stack.currentIndex() == 1 and img.conn_box.count() == 1, "Bildanbieter in der Auswahl")
    check(img.model_box.currentText() == "grok-imagine-image", "Modelle aus dem Katalog")
    img.prompt.setPlainText("Ein Schraubenschlüssel im Weltall, Comicstil")
    img.count.setValue(2)
    check(img.generate(), "Erzeugen gestartet")
    check(wait(lambda: not img.running), "Bild fertig")
    check(img.gallery.count() >= 3, f"Galerie ({img.gallery.count()})")
    img.gallery.setCurrentRow(0)
    rs.pump(0.2)
    check("Schraubenschlüssel" in img.meta.text(), "Vorschau mit Beschreibung")
    if shots:
        win.grab().save(str(shots / "clank_images.png"))
    first = img._path(img.gallery.item(0))
    tool.image_to_chat(str(first))
    check(tool.modes.currentIndex() == 0 and tool.panel.attachments and
          tool.panel.attachments[-1]["kind"] == "image", "Bild an den Chat angehängt")
    store.remove("m-xai")
    img.refresh()
    check(img.stack.currentIndex() == 0, "ohne Bildanbieter: Hinweis-Seite")

    # Gruppenchat
    tool.modes.setCurrentWidget(tool.group)
    rs.pump(0.2)
    g = tool.group
    check(g.stack.currentIndex() == 1 and g.table.rowCount() == 2, "zwei Teilnehmer vorbelegt")
    g.table.cellWidget(0, 2).setText("Sicherheit")
    g.topic.setPlainText("Wie sichern wir den Server 10.1.2.3 ab?")
    g.spins["rounds"].setValue(2)
    g.checks["stop_on_agree"].setChecked(False)
    SEEN.clear()
    check(g.start(), "Gruppenchat gestartet")
    g.input.setText("Bitte auch an Backups denken.")
    g.interject()
    check(wait(lambda: not g.running, 30), "Gruppenchat beendet")
    msgs = g.thread["messages"]
    spoken = [m for m in msgs if m["role"] == "assistant"]
    check(len(spoken) == 5 and spoken[-1].get("summary"), f"4 Beiträge + Zusammenfassung ({len(spoken)})")
    check(any(m["role"] == "user" and "Backups" in m["content"] for m in msgs), "Einwurf im Verlauf")
    chats = [json.loads(s[3]) for s in SEEN if s[1].endswith("/chat/completions")]
    check(chats and all("10.1.2.3" not in json.dumps(c) for c in chats), "Adresse verfremdet gesendet")
    check(any("10.1.2.3" in m.get("content", "") for m in spoken), "Antwort zurückübersetzt")
    check(not chats[0].get("tools"), "keine Funktionen im Gruppenchat")
    check(g.history.count() == 1 and g.store.load(g.thread["id"]), "Gruppenchat gespeichert")
    check("Sicherheit" in g.thread["participants"][0]["role"], "Rolle gespeichert")
    if shots:
        win.grab().save(str(shots / "clank_group.png"))
        g.new_group()
        rs.pump(0.2)
        win.grab().save(str(shots / "clank_group_setup.png"))
    win.close_tool(next(n for n, o in win.open_tools.items() if o.tool_id == tid))
    rs.pump(0.3)
    print(f"OK: {OK} Prüfungen")
    return 0


if __name__ == "__main__":
    sys.exit(main())

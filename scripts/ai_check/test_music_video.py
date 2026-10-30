"""Groovitron (Musik) und Vidcomic (Video): Anbieter-Schnittstellen und Oberfläche ohne echte Anbieter.

    python scripts/ai_check/test_music_video.py [--shots ORDNER]

Musik: Gemini Lyria, ElevenLabs, MiniMax, Stability, Mureka, fal.ai, Replicate. Video: Gemini Omni Flash
(Interactions + Datei-Download), xAI, MiniMax, Runway, Luma, Seedance, fal.ai, Replicate. Danach die Reiter
„Musik“/„Video“ im Hauptfenster: ohne ffmpeg ausgegraut, mit ffmpeg erzeugen, Vorschaubild, Kürzen, Musik
unterlegen, GIF. Braucht ffmpeg im PATH (CI installiert es); ohne ffmpeg nur die Schnittstellen.
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

from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox  # noqa: E402

from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.settings import AppSettings  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402

OK = 0
SEEN: list[tuple[str, str, dict, bytes]] = []
FFMPEG = shutil.which("ffmpeg") or ""
WORK = Path(tempfile.mkdtemp(prefix="mv_check_"))
MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def check(cond, text):
    global OK
    if not cond:
        raise AssertionError(text)
    OK += 1


def make_samples() -> None:
    """Echte kleine Dateien, damit ffmpeg damit arbeiten kann."""
    global MP3, MP4
    if not FFMPEG:
        return
    mp3, mp4 = WORK / "s.mp3", WORK / "s.mp4"
    run = lambda args: subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],  # noqa: E731
                                      check=True, capture_output=True)
    run(["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "libmp3lame", str(mp3)])
    run(["-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=2", "-f", "lavfi", "-i",
         "sine=frequency=220:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
         str(mp4)])
    MP3, MP4 = mp3.read_bytes(), mp4.read_bytes()


def fake_server() -> str:
    polls: dict[str, int] = {}

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

        def pending(self, key: str) -> bool:
            polls[key] = polls.get(key, 0) + 1
            return polls[key] < 2

        def do_GET(self):  # noqa: N802
            p = self.path
            SEEN.append(("GET", p, dict(self.headers), b""))
            b = self.base()
            if p == "/files/a.mp3":
                return self._send(MP3, "audio/mpeg")
            if p == "/files/v.mp4":
                return self._send(MP4, "video/mp4")
            if p.startswith(("/mu/v1/song/query/", "/mu/v1/instrumental/query/")):
                return self._send({"status": "running"} if self.pending("mu") else
                                  {"status": "succeeded", "choices": [{"url": b + "/files/a.mp3"}]})
            if p == "/fal/status":
                return self._send({"status": "COMPLETED"})
            if p == "/fal/result-audio":
                return self._send({"audio": {"url": b + "/files/a.mp3"}})
            if p == "/fal/result-video":
                return self._send({"video": {"url": b + "/files/v.mp4"}})
            if p == "/rep/pred-audio":
                return self._send({"status": "succeeded", "output": b + "/files/a.mp3"})
            if p == "/rep/pred-video":
                return self._send({"status": "succeeded", "output": b + "/files/v.mp4"})
            if p.startswith("/gem/v1beta/files/vid1:download"):
                return self._send(MP4, "video/mp4")
            if p.startswith("/gem/v1beta/files/vid1"):
                return self._send({"state": "PROCESSING"} if self.pending("gem") else {"state": "ACTIVE"})
            if p.startswith("/xai/v1/videos/"):
                return self._send({"status": "pending"} if self.pending("xai") else
                                  {"status": "done", "video": {"url": b + "/files/v.mp4"}})
            if p.startswith("/mm/v1/query/video_generation"):
                return self._send({"status": "Processing"} if self.pending("mm") else
                                  {"status": "Success", "file_id": "f1"})
            if p.startswith("/mm/v1/files/retrieve"):
                return self._send({"file": {"download_url": b + "/files/v.mp4"}})
            if p.startswith("/rw/v1/tasks/"):
                return self._send({"status": "RUNNING"} if self.pending("rw") else
                                  {"status": "SUCCEEDED", "output": [b + "/files/v.mp4"]})
            if p.startswith("/luma/generations/"):
                return self._send({"state": "dreaming"} if self.pending("luma") else
                                  {"state": "completed", "assets": {"video": b + "/files/v.mp4"}})
            if p.startswith("/sd/api/v3/contents/generations/tasks/"):
                return self._send({"status": "running"} if self.pending("sd") else
                                  {"status": "succeeded", "content": {"video_url": b + "/files/v.mp4"}})
            return self._send({"error": "unknown " + p}, status=404)

        def do_POST(self):  # noqa: N802
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            p = self.path
            SEEN.append(("POST", p, dict(self.headers), raw))
            b = self.base()
            import base64
            if ":generateContent" in p:
                return self._send({"candidates": [{"content": {"parts": [
                    {"text": "[Verse] Server laufen"},
                    {"inlineData": {"mimeType": "audio/mpeg", "data": base64.b64encode(MP3).decode()}}]}}]})
            if p.startswith("/el/v1/music"):
                return self._send(MP3, "audio/mpeg")
            if p.startswith("/mm/v1/music_generation"):
                return self._send({"data": {"audio": MP3.hex()}, "base_resp": {"status_code": 0}})
            if p.startswith("/stab/"):
                return self._send(MP3, "audio/mpeg")
            if p.startswith("/mu/v1/"):
                return self._send({"id": "t1", "status": "preparing"})
            if p.startswith("/fal/"):
                kind = "video" if "video" in p else "audio"
                return self._send({"request_id": "r1", "status_url": b + "/fal/status",
                                   "response_url": b + "/fal/result-" + kind})
            if p.startswith("/rep/"):
                kind = "video" if "video" in p else "audio"
                return self._send({"status": "starting", "urls": {"get": b + "/rep/pred-" + kind}})
            if p.startswith("/gem/v1beta/interactions"):
                return self._send({"id": "i1", "steps": [{"type": "model_output", "content": [
                    {"type": "video", "mime_type": "video/mp4", "uri": b + "/gem/v1beta/files/vid1"}]}]})
            if p.startswith("/xai/v1/videos/generations"):
                return self._send({"request_id": "x1"})
            if p.startswith("/mm/v1/video_generation"):
                return self._send({"task_id": "m1", "base_resp": {"status_code": 0}})
            if p.startswith("/rw/v1/"):
                return self._send({"id": "w1"})
            if p.startswith("/luma/generations"):
                return self._send({"id": "l1", "state": "queued"})
            if p.startswith("/sd/api/v3/contents/generations/tasks"):
                return self._send({"id": "s1"})
            return self._send({"error": "unknown " + p}, status=404)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}"


def last_post(prefix: str):
    return next(s for s in reversed(SEEN) if s[0] == "POST" and s[1].startswith(prefix))


def test_apis(store, base: str) -> None:
    from omniwrench.ai import media
    from omniwrench.ai.connections import Connection
    music = [  # (Anbieter, Basis, Modell, Pfad, Kopfzeile)
        ("gemini", "/gem/v1beta/openai", "lyria-3.5", "/gem/v1beta/models/lyria-3.5", ("x-goog-api-key", "k")),
        ("elevenlabs", "/el/v1", "music_v1", "/el/v1/music", ("xi-api-key", "k")),
        ("minimax", "/mm/v1", "music-2.6", "/mm/v1/music_generation", ("Authorization", "Bearer k")),
        ("stability", "/stab/v2beta", "stable-audio-2.5", "/stab/v2beta/audio/stable-audio-2/text-to-audio",
         ("Authorization", "Bearer k")),
        ("mureka", "/mu/v1", "auto", "/mu/v1/song/generate", ("Authorization", "Bearer k")),
        ("fal", "/fal", "fal-ai/elevenlabs/music", "/fal/fal-ai/elevenlabs/music", ("Authorization", "Key k")),
        ("replicate", "/rep", "minimax/music-2.6", "/rep/models/minimax/music-2.6", ("Authorization", "Bearer k")),
    ]
    for provider, url, model, path, (hname, hval) in music:
        conn = Connection(id="mu-" + provider, name=provider, provider=provider, base_url=base + url)
        store.save(conn)
        store.set_secrets(conn.id, {"api_key": "k"})
        check(media.supports(conn, "music"), f"{provider}: Musik unterstützt")
        req = media.Request("Lo-Fi für die Hotline", model, duration=30, lyrics="[Verse] Server laufen")
        items = media.generate(store, conn, "music", req)
        check(items and items[0].data == MP3 and items[0].mime == "audio/mpeg", f"{provider}: Musik erhalten")
        headers = {k.lower(): v for k, v in last_post(path)[2].items()}
        check(headers.get(hname.lower()) == hval, f"{provider}: Kopfzeile {hname}")
    body = json.loads(last_post("/el/v1/music")[3])
    check(body["music_length_ms"] == 30000 and "Server laufen" in body["prompt"], "ElevenLabs: Länge + Text")
    body = json.loads(last_post("/mm/v1/music_generation")[3])
    check(body["lyrics"].startswith("[Verse]") and body["audio_setting"]["format"] == "mp3", "MiniMax: Liedtext")
    gem = media.generate(store, store.get("mu-gemini"), "music", media.Request("x", "lyria-3.5"))
    check("Server laufen" in gem[0].meta.get("lyrics", ""), "Lyria: Liedtext aus der Antwort")
    mureka = media.generate(store, store.get("mu-mureka"), "music",
                            media.Request("x", "auto", instrumental=True))
    check(mureka and last_post("/mu/v1/")[1] == "/mu/v1/instrumental/generate", "Mureka: instrumental")

    video = [
        ("gemini", "/gem/v1beta/openai", "gemini-omni-1.1-flash", "/gem/v1beta/interactions", ("x-goog-api-key", "k")),
        ("xai", "/xai/v1", "grok-imagine-video-1.5", "/xai/v1/videos/generations", ("Authorization", "Bearer k")),
        ("minimax", "/mm/v1", "MiniMax-Hailuo-2.3", "/mm/v1/video_generation", ("Authorization", "Bearer k")),
        ("runway", "/rw/v1", "gen4.5", "/rw/v1/text_to_video", ("X-Runway-Version", "2024-11-06")),
        ("luma", "/luma", "ray-2", "/luma/generations", ("Authorization", "Bearer k")),
        ("seedance", "/sd/api/v3", "seedance-2-0-pro", "/sd/api/v3/contents/generations/tasks",
         ("Authorization", "Bearer k")),
        ("fal", "/fal", "fal-ai/kling-video/v3/pro/text-to-video", "/fal/fal-ai/kling-video",
         ("Authorization", "Key k")),
        ("replicate", "/rep", "wan-video/wan-2.5-t2v", "/rep/models/wan-video", ("Authorization", "Bearer k")),
    ]
    for provider, url, model, path, (hname, hval) in video:
        conn = Connection(id="vi-" + provider, name=provider, provider=provider, base_url=base + url)
        store.save(conn)
        store.set_secrets(conn.id, {"api_key": "k"})
        check(media.supports(conn, "video"), f"{provider}: Video unterstützt")
        req = media.Request("Rechenzentrum im Morgenlicht", model, aspect="9:16", duration=8, resolution="720p")
        items = media.generate(store, conn, "video", req)
        check(items and items[0].data == MP4 and items[0].mime == "video/mp4", f"{provider}: Video erhalten")
        headers = {k.lower(): v for k, v in last_post(path)[2].items()}
        check(headers.get(hname.lower()) == hval, f"{provider}: Kopfzeile {hname}")
    body = json.loads(last_post("/gem/v1beta/interactions")[3])
    check(body["response_format"]["aspect_ratio"] == "9:16" and body["model"] == "gemini-omni-1.1-flash",
          "Omni: Format")
    body = json.loads(last_post("/rw/v1/text_to_video")[3])
    check(body["ratio"] == "720:1280" and body["promptText"].startswith("Rechenzentrum"), "Runway: Verhältnis")
    body = json.loads(last_post("/sd/api/v3/")[3])
    check("--ratio 9:16" in body["content"][0]["text"], "Seedance: Parameter im Text")
    body = json.loads(last_post("/mm/v1/video_generation")[3])
    check(body["resolution"] == "768P" and body["duration"] == 10, "MiniMax: Auflösung/Dauer")
    check(not media.supports(Connection(id="k", name="k", provider="kling"), "video"), "Kling direkt nicht")
    # Abbrechen während der Abfrage
    stop = threading.Event()
    stop.set()
    from omniwrench.ai.http import Cancelled
    try:
        media.generate(store, store.get("vi-luma"), "video", media.Request("x", "ray-2"), stop)
        check(False, "Abbruch")
    except Cancelled:
        check(True, "Abbruch")


def wait(cond, seconds=30.0):
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
    make_samples()
    paths.ensure_dirs()
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    from omniwrench.app import apply_language
    from omniwrench.ui import theme
    apply_language(app, "de")
    theme.apply_theme(app, "dark")
    vault = Vault(paths.VAULT_FILE)
    vault.create(password="mv-check")
    credentials.init(vault)
    settings = AppSettings()
    settings.set("check_updates_on_start", False)
    settings.set("repositories", [])
    settings.set("ai_storage_mode", "central")
    settings.set("ai_storage_root", tempfile.mkdtemp(prefix="mv_data_"))
    manager = ToolManager(vault)
    import aikit
    ids = aikit.install(manager, "groovitron", "vidcomic")

    from omniwrench.ai.connections import ConnectionStore
    store = ConnectionStore(settings, vault)
    base = fake_server()
    test_apis(store, base)
    if not FFMPEG:
        print(f"OK: {OK} Prüfungen (ohne ffmpeg: Oberfläche übersprungen)")
        return 0

    for c in store.list():
        if c.id not in ("mu-elevenlabs", "vi-xai"):
            store.remove(c.id)
    from omniwrench.ui.main_window import MainWindow
    win = MainWindow(settings, vault, manager)
    win.resize(1500, 900)
    win.show()
    rs.pump(0.5)
    tool = aikit.open_tool(win, ids["groovitron"], rs.pump)
    from omniwrench.ai import ffmpeg as ff
    from omniwrench.ui import ai_media as mtab

    # ohne ffmpeg: ausgegraut
    real_which = shutil.which
    shutil.which = lambda name, *a, **k: None if name in ("ffmpeg", "ffprobe") else real_which(name, *a, **k)
    tool.page.refresh()
    rs.pump(0.2)
    check(tool.page.stack.currentIndex() == 0 and "ffmpeg" in tool.page.ff_page.label.text(), "ohne ffmpeg: Hinweis")
    if shots:
        win.grab().save(str(shots / "clank_no_ffmpeg.png"))
    shutil.which = real_which
    settings_tool = tool.context.settings
    settings_tool.set("ffmpeg_path", FFMPEG)
    tool.page.ff_page.changed.emit()
    rs.pump(0.2)
    check(tool.page.stack.currentIndex() == 2, "mit ffmpeg: Musik bereit")

    # Musik erzeugen und zu MP3 / kürzen
    mt = tool.page
    mt.prompt.setPlainText("Ruhiger Beat für die Hotline")
    mt.duration.setValue(20)
    check(mt.generate(), "Musik gestartet")
    check(wait(lambda: not mt.running), "Musik fertig")
    check(mt.files.count() == 1 and mt._current is not None, f"Musikliste ({mt.status.text()})")
    track = mt._current
    mtab.TrimDialog.exec = lambda self: (self.start.setValue(0.5), self.end.setValue(1.5),
                                         QDialog.DialogCode.Accepted)[-1]
    mt.trim()
    check(wait(lambda: mt.files.count() == 2), "gekürztes Stück")
    trimmed = Path(mt._current)
    check(0.8 < ff.duration(FFMPEG, trimmed) < 1.3, f"Länge nach Kürzen {ff.duration(FFMPEG, trimmed)}")

    # Video erzeugen, Vorschaubild, Musik unterlegen, GIF
    vtool = aikit.open_tool(win, ids["vidcomic"], rs.pump)
    vtool.context.settings.set("ffmpeg_path", FFMPEG)
    vt = vtool.page
    vt.refresh()
    rs.pump(0.2)
    check(vt.stack.currentIndex() == 2 and vt.model_box.currentText() == "grok-imagine-video-1.5", "Video bereit")
    vt.prompt.setPlainText("Ein Schraubenschlüssel dreht sich")
    check(vt.generate(), "Video gestartet")
    check(wait(lambda: not vt.running), "Video fertig")
    check(vt.files.count() == 1, f"Videoliste ({vt.status.text()})")
    clip = Path(vt._current)
    check(clip.with_name(clip.name + ".poster.png").exists(), "Vorschaubild")
    QInputDialog.getItem = staticmethod(lambda *a, **k: (track.name, True))
    vt.add_music()
    check(wait(lambda: vt.files.count() == 2), "Video mit Musik")
    check(json.loads(Path(str(vt._current) + ".json").read_text(encoding="utf-8"))["edit"] == "music",
          "Beschreibung der Bearbeitung")
    vt._select(vt.files.item(vt.files.count() - 1))
    vt.to_gif()
    from omniwrench.ai import media
    from omniwrench.ai.storage import Storage
    gifs = lambda: [p for p in media.list_files(Storage(settings, vault), "image") if p.suffix == ".gif"]  # noqa: E731
    check(wait(lambda: bool(gifs())), "GIF in den Bildern")
    if shots:
        vt.files.setCurrentRow(0)
        rs.pump(0.3)
        win.grab().save(str(shots / "vidcomic.png"))
        aikit.open_tool(win, ids["groovitron"], rs.pump)
        win.grab().save(str(shots / "groovitron.png"))
    for tid in ids.values():
        aikit.close_tool(win, tid, rs.pump)
    print(f"OK: {OK} Prüfungen")
    return 0


if __name__ == "__main__":
    sys.exit(main())

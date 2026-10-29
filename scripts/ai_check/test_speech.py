"""Sprache prüfen: Transkription/Vorlesen (Fake-Anbieter), Sprechererkennung, Mitschrift-Reiter mit Einwilligung,
Profilen und Zusammenfassung, Sprachassistent (Knopf „Sprechen“, Weckwort-Ablauf mit Fake-Erkennung).

    python scripts/ai_check/test_speech.py [--shots ORDNER]
"""

from __future__ import annotations

import base64
import http.server
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import render_screenshots as rs  # noqa: E402  (Temp-Home, offscreen, pump)

import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox  # noqa: E402

from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.settings import AppSettings  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402

OK = 0
POSTS: list[tuple[str, bytes, dict]] = []
MP3 = b"ID3\x04fake-mp3"
CHAT = {"text": "Zusammenfassung: Server-Umzug am Freitag beschlossen."}
RATE = 16000


def check(cond, text):
    global OK
    if not cond:
        raise AssertionError(text)
    OK += 1


def wait(cond, seconds=30.0):
    n = 0
    while not cond() and n < seconds * 10:
        rs.pump(0.1)
        n += 1
    return cond()


def voice(f0, formants, secs=3.0, seed=0):
    """Synthetische „Stimme“: Obertöne mit eigener Klangfarbe, mit Pausen."""
    r = np.random.default_rng(seed)
    t = np.arange(int(RATE * secs)) / RATE
    f = f0 * (1 + 0.03 * np.sin(2 * np.pi * 3 * t + seed))
    ph = 2 * np.pi * np.cumsum(f) / RATE
    x = sum((1 / k) * np.sin(k * ph) * sum(np.exp(-((k * f0 - F) / 120) ** 2) for F in formants)
            for k in range(1, 40))
    return (x / np.abs(x).max() * 0.3 + 0.002 * r.standard_normal(len(t))).astype("float32")


ALICE = (110, [700, 1200, 2600])
BOB = (210, [400, 2200, 3000])


def silence(secs):
    return np.zeros(int(RATE * secs), dtype="float32")


def fake_server() -> str:
    state = {"aai": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, data, status=200):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path.startswith("/aai/v2/transcript/"):
                state["aai"] += 1
                if state["aai"] < 2:
                    self._json({"status": "processing"})
                else:
                    self._json({"status": "completed", "utterances": [
                        {"speaker": "A", "start": 0, "end": 1200, "text": "Erster Satz."},
                        {"speaker": "B", "start": 1300, "end": 2500, "text": "Zweiter Satz."}]})
                return
            self._json({"data": [{"id": "fake"}]})

        def do_POST(self):  # noqa: N802
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            POSTS.append((self.path, raw, dict(self.headers)))
            p = self.path
            if p == "/oa/v1/audio/transcriptions":
                if b"gpt-4o-transcribe-diarize" in raw:
                    known = b"known_speaker_names[]" in raw
                    self._json({"segments": [
                        {"speaker": "Alice" if known else "A", "start": 0.0, "end": 1.4, "text": "Guten Morgen."},
                        {"speaker": "B", "start": 1.5, "end": 3.0, "text": "Hallo zusammen."}]})
                else:
                    self._json({"text": "Wie spät ist es?"})
            elif p == "/oa/v1/audio/speech":
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.end_headers()
                self.wfile.write(MP3)
            elif p == "/el/v1/speech-to-text":
                self._json({"text": "Hallo du", "words": [
                    {"text": "Hallo", "type": "word", "start": 0.0, "end": 0.4, "speaker_id": "speaker_0"},
                    {"text": " ", "type": "spacing", "speaker_id": "speaker_0"},
                    {"text": "Welt.", "type": "word", "start": 0.5, "end": 0.9, "speaker_id": "speaker_0"},
                    {"text": " ", "type": "spacing", "speaker_id": "speaker_1"},
                    {"text": "Ja.", "type": "word", "start": 1.2, "end": 1.4, "speaker_id": "speaker_1"}]})
            elif p.startswith("/el/v1/text-to-speech/"):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(MP3)
            elif p.startswith("/dg/v1/listen"):
                # Sprecherwechsel in der Mitte jedes Abschnitts: Deepgram nummeriert je Anfrage neu
                self._json({"results": {"utterances": [
                    {"speaker": 0, "start": 0.0, "end": 2.9, "transcript": "Teil eins."},
                    {"speaker": 1, "start": 3.0, "end": 6.0, "transcript": "Teil zwei."}]}})
            elif p.startswith("/gem/v1beta/models/") and p.endswith(":generateContent"):
                if "-tts" in p:
                    pcm = base64.b64encode(b"\x00\x01" * 2400).decode()
                    self._json({"candidates": [{"content": {"parts": [{"inlineData": {
                        "mimeType": "audio/L16;codec=pcm;rate=24000", "data": pcm}}]}}]})
                else:
                    self._json({"candidates": [{"content": {"parts": [
                        {"text": "Speaker 1: Hallo zusammen.\nSpeaker 2: Guten Tag.\nwie geht es?"}]}}]})
            elif p == "/aai/v2/upload":
                self._json({"upload_url": "https://cdn.example/x"})
            elif p == "/aai/v2/transcript":
                self._json({"id": "t1", "status": "queued"})
            elif p == "/chat/v1/chat/completions":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                text = CHAT["text"]
                for part in (text[:9], text[9:]):
                    self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': part}}]})}\n\n"
                                     .encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.close_connection = True
            else:
                self._json({"error": {"message": "unknown " + p}}, 404)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}"


class FakeSource:
    """Spielt fertige Samples in 100-ms-Blöcken ab, danach Stille."""

    def __init__(self, kind, samples):
        self.kind = kind
        self.samples = samples
        self.error = ""

    def run(self, feed, stop):
        pos = 0
        while not stop.is_set():
            block = self.samples[pos:pos + 1600]
            if len(block) < 1600:
                block = np.zeros(1600, dtype="float32")
            feed(block)
            pos += 1600
            time.sleep(0.002)


def test_core(store, base, sp, au, storage) -> None:
    from omniwrench.ai import speech
    from omniwrench.ai.connections import Connection
    wav = speech.wav_bytes(voice(*ALICE, secs=1.0))
    check(wav[:4] == b"RIFF" and len(wav) > 30000, "WAV erzeugt")
    conns = {}
    for cid, provider, url in (("oa", "openai", "/oa/v1"), ("el", "elevenlabs", "/el/v1"),
                               ("dg", "deepgram", "/dg/v1"), ("aai", "assemblyai", "/aai/v2")):
        c = Connection(id=cid, name=provider, provider=provider, base_url=base + url, auth="api_key")
        store.save(c)
        store.set_secrets(cid, {"api_key": "k"})
        conns[cid] = store.get(cid)
    check({c.id for c in speech.stt_connections(store)} >= {"oa", "el", "dg", "aai"}, "STT-Verbindungen")
    check({c.id for c in speech.tts_connections(store)} >= {"oa", "el"}, "TTS-Verbindungen")
    check(speech.stt_models(conns["oa"])[0] == "gpt-transcribe", "OpenAI: gpt-transcribe zuerst")
    check(speech.tts_models(conns["el"])[0] == "eleven_v4_turbo", "ElevenLabs: v4 turbo")
    segs = speech.transcribe(store, conns["oa"], wav, "gpt-transcribe", ["de", "en"])
    check(segs[0].text == "Wie spät ist es?", "OpenAI Text")
    body = POSTS[-1][1]
    check(body.count(b"languages[]") == 2 and b"name=\"language\"" not in body, "languages[] statt language")
    segs = speech.transcribe(store, conns["oa"], wav, "gpt-4o-transcribe-diarize", [], [("Alice", wav)])
    check(segs[0].speaker == "Alice" and segs[0].known and not segs[1].known, "Diarize mit bekannter Stimme")
    check(b"data:audio/wav;base64," in POSTS[-1][1] and b"diarized_json" in POSTS[-1][1], "Stimmprobe gesendet")
    segs = speech.transcribe(store, conns["el"], wav)
    check([(s.speaker, s.text) for s in segs] == [("speaker_0", "Hallo Welt."), ("speaker_1", "Ja.")],
          "ElevenLabs Wörter gruppiert")
    check({k.lower(): v for k, v in POSTS[-1][2].items()}.get("xi-api-key") == "k", "ElevenLabs Schlüssel")
    segs = speech.transcribe(store, conns["dg"], wav, "", ["de"])
    check(len(segs) == 2 and segs[1].speaker == "1", "Deepgram Äußerungen")
    check("diarize_model=latest" in POSTS[-1][0] and "language=de" in POSTS[-1][0], "Deepgram Parameter")
    check({k.lower(): v for k, v in POSTS[-1][2].items()}.get("authorization") == "Token k", "Deepgram Token")
    segs = speech.transcribe(store, conns["aai"], wav)
    check([s.speaker for s in segs] == ["A", "B"] and segs[1].start == 1.3, "AssemblyAI mit Abfragen")
    sent = json.loads(next(b for p, b, h in reversed(POSTS) if p == "/aai/v2/transcript"))
    check(sent["speech_models"][0] == "universal-3-pro" and sent["speaker_labels"], "AssemblyAI speech_models")
    data, mime = speech.synthesize(store, conns["oa"], "Hallo")
    check(data == MP3 and mime == "audio/mpeg", "OpenAI Vorlesen")
    data, _ = speech.synthesize(store, conns["el"], "Hallo", "", "voice123")
    check(data == MP3 and "/text-to-speech/voice123" in POSTS[-1][0], "ElevenLabs Vorlesen")
    md = speech.transcript_markdown({"title": "T", "created": 0, "duration": 65, "consent": {"at": 1},
                                     "speakers": {"S1": {"name": "Alice"}}, "summary": "Kurz.",
                                     "segments": [{"t": 3, "speaker": "S1", "text": "Hallo"}]})
    check("**[00:00:03] Alice:** Hallo" in md and "Kurz." in md and "00:01:05" in md, "Markdown")

    # Sprechererkennung
    a1, a2 = sp.embedding(voice(*ALICE, seed=1)), sp.embedding(voice(115, ALICE[1], seed=2))
    b1 = sp.embedding(voice(*BOB, seed=3))
    check(sp.similarity(a1, a2) > sp.THRESHOLD > sp.similarity(a1, b1), "Stimmen unterscheidbar")
    check(sp.embedding(silence(2)) is None and sp.embedding(voice(*ALICE, secs=0.2)) is None, "zu leise/kurz")
    sess = sp.SessionSpeakers([], "Sprecher {n}")
    s1, s2, s3 = sess.assign(a1), sess.assign(b1), sess.assign(a2)
    check(s1 == s3 != s2 and sess.speakers[s2]["name"] == "Sprecher 2", "Zuordnung in der Mitschrift")
    profiles = sp.ProfileStore(storage)
    prof = profiles.upsert("Alice", a1, b"RIFFdata")
    check(profiles.base.with_suffix(".owai").exists() and not profiles.base.with_suffix(".json").exists(),
          "Profile immer verschlüsselt")
    check(profiles.load()[0]["name"] == "Alice" and profiles.samples(profiles.load())[0] == ("Alice", b"RIFFdata"),
          "Profil geladen")
    sess = sp.SessionSpeakers(profiles.load(), "Sprecher {n}")
    check(sess.speakers[sess.assign(a2)]["name"] == "Alice", "Profil erkennt Stimme wieder")
    profiles.delete(prof["id"])
    check(profiles.load() == [], "Profil gelöscht")

    # Abschnitte
    chunks = []
    ch = au.Chunker(lambda s, t: chunks.append((len(s) / RATE, t)))
    ch.feed(np.concatenate([silence(1), voice(*ALICE, 2.5), silence(1.5), voice(*BOB, 2.0), silence(1.5)]))
    check(len(chunks) == 2 and 0.6 < chunks[0][1] < 1.0 and chunks[1][1] > 3.5, f"zwei Abschnitte {chunks}")
    ch.feed(np.concatenate([voice(*ALICE, 0.15), silence(3)]))
    check(len(chunks) == 2, "Klick ignoriert")
    long = []
    au.Chunker(lambda s, t: long.append(len(s) / RATE)).feed(voice(*ALICE, 30))
    check(long and long[0] <= au.MAX_CHUNK + 0.1, "lange Rede geteilt")


def test_more_speech(store, base) -> None:
    """Gemini (Erkennung + Vorlesen), Groq Whisper, Mistral Voxtral, Piper-Adressen."""
    from omniwrench.ai import speech
    from omniwrench.ai.connections import Connection
    for cid, provider, url in (("gem", "gemini", "/gem/v1beta/openai"), ("gq", "groq", "/oa/v1"),
                               ("mi", "mistral", "/oa/v1")):
        store.save(Connection(id=cid, name=provider, provider=provider, base_url=base + url, auth="api_key"))
        store.set_secrets(cid, {"api_key": "k"})
    gem, gq, mi = store.get("gem"), store.get("gq"), store.get("mi")
    stt = {c.id for c in speech.stt_connections(store)}
    tts = {c.id for c in speech.tts_connections(store)}
    check({"gem", "gq", "mi"} <= stt and "gem" in tts and not {"gq", "mi"} & tts, f"Gemini/Groq/Mistral STT, TTS {tts}")
    check(speech.stt_models(gq)[0] == "whisper-large-v3-turbo" and speech.stt_models(mi) == ["voxtral-mini-latest"],
          "Groq Whisper, Mistral Voxtral")
    check(all("tts" not in m for m in speech.stt_models(gem)) and all("tts" in m for m in speech.tts_models(gem)),
          "Gemini Modelle getrennt")
    check(len(speech.voices(gem)) == 30 and "Kore" in speech.voices(gem), "30 Gemini-Stimmen")
    wav = speech.wav_bytes(voice(*ALICE, secs=0.5))
    segs = speech.transcribe(store, gem, wav, "", ["de"])
    check([(s.speaker, s.text) for s in segs] == [("1", "Hallo zusammen."), ("2", "Guten Tag. wie geht es?")],
          f"Gemini Erkennung mit Sprechern {[(s.speaker, s.text) for s in segs]}")
    path, raw, headers = POSTS[-1]
    check(path.startswith("/gem/v1beta/models/gemini-3.8-flash:") and b"audio/wav" in raw and
          {k.lower(): v for k, v in headers.items()}.get("x-goog-api-key") == "k", "Gemini: Audio + Schlüssel nativ")
    data, mime = speech.synthesize(store, gem, "Hallo", "", "Puck")
    check(mime == "audio/wav" and data[:4] == b"RIFF" and b"Puck" in POSTS[-1][1], "Gemini Vorlesen als WAV")
    speech.transcribe(store, mi, wav, "voxtral-mini-latest", ["de"])
    check(b"response_format" not in POSTS[-1][1] and b"voxtral" in POSTS[-1][1], "Voxtral ohne response_format")
    from omniwrench.ai import local_speech as ls
    check(ls.piper_url("de_DE-thorsten-medium", ".onnx").endswith(
        "/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx"), "Piper-Adresse")
    check(ls.piper_url("de_DE-eva_k-x_low", ".onnx.json").endswith("/de/de_DE/eva_k/x_low/de_DE-eva_k-x_low.onnx.json"),
          "Piper-Adresse mit x_low")


def main() -> int:
    shots = None
    if "--shots" in sys.argv:
        shots = Path(sys.argv[sys.argv.index("--shots") + 1])
        shots.mkdir(parents=True, exist_ok=True)
    paths.ensure_dirs()
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    from omniwrench.app import apply_language
    from omniwrench.ui import theme
    apply_language(app, "de")
    theme.apply_theme(app, "dark")
    vault = Vault(paths.VAULT_FILE)
    vault.create(password="speech-check")
    credentials.init(vault)
    settings = AppSettings()
    settings.set("check_updates_on_start", False)
    settings.set("repositories", [])
    settings.set("ai_storage_mode", "central")
    settings.set("ai_storage_root", str(Path(tempfile.mkdtemp(prefix="speech_data_"))))
    base = fake_server()
    from omniwrench.ai.connections import Connection, ConnectionStore
    from omniwrench.ai.storage import Storage
    store = ConnectionStore(settings, vault)
    store.save(Connection(id="bot", name="Testbot", provider="ollama", base_url=base + "/chat/v1", model="f",
                          auth="none"))
    manager = ToolManager(vault)
    import aikit
    ids = aikit.install(manager, "kreeli", "mr_zurkon")
    from omniwrench.ui.main_window import MainWindow
    win = MainWindow(settings, vault, manager)
    win.resize(1500, 900)
    win.show()
    rs.pump(0.5)
    from omniwrench.ai import audio as au
    real_missing = au.missing
    au.missing = lambda packages=au.PACKAGES: [p for p in real_missing(packages) if p != "soundcard"]
    tool = aikit.open_tool(win, ids["kreeli"], rs.pump)
    pkg = type(tool).__module__.rsplit(".", 1)[0]
    sp, ts = (sys.modules[pkg + n] for n in (".speakers", ".transcript"))
    test_core(store, base, sp, au, Storage(settings, vault))
    test_more_speech(store, base)

    # --- Kreeli – Transkription ---------------------------------------------------------------------
    tab = tool.page
    tab.refresh()
    rs.pump(0.3)
    check(tab.stack.currentIndex() == 2, "Mitschrift bereit (Anbieter vorhanden)")
    # Sprecherprofile: Hinweis beim Start, verstecktes „immer aktiv“ nach 10x Umschalten
    notice = {"result": QDialog.DialogCode.Rejected, "shown": 0}

    def notice_exec(_dlg):
        notice["shown"] += 1
        return notice["result"]
    ts.ProfileNotice.exec = notice_exec
    tab.settings.set("ts_profiles_always", False)
    dlg = ts.ConsentDialog(tab.tr_, "OA", True, tab.settings, tab)
    check(not dlg.profiles.isChecked() and not dlg.always.isVisibleTo(dlg), "Profile aus, Zusatzhaken versteckt")
    dlg.agree.setChecked(True)
    dlg.profiles.click()
    dlg.accept()
    check(notice["shown"] == 1 and not dlg.profiles.isChecked() and dlg.result() != QDialog.DialogCode.Accepted,
          "Profilhinweis abgelehnt -> kein Start, Haken weg")
    notice["result"] = QDialog.DialogCode.Accepted
    dlg.profiles.click()
    dlg.accept()
    check(notice["shown"] == 2 and dlg.result() == QDialog.DialogCode.Accepted, "Profilhinweis bestätigt -> Start")
    dlg = ts.ConsentDialog(tab.tr_, "OA", True, tab.settings, tab)
    for _ in range(9):
        dlg.profiles.click()
    check(not dlg.always.isVisibleTo(dlg), "9x umschalten reicht nicht")
    dlg.profiles.click()
    check(dlg.always.isVisibleTo(dlg), "10x umschalten zeigt „immer aktiv“")
    dlg.always.setChecked(True)
    check(tab.settings.get("ts_profiles_always") is True and dlg.profiles.isChecked(), "immer aktiv gespeichert")
    dlg = ts.ConsentDialog(tab.tr_, "OA", True, tab.settings, tab)
    check(dlg.profiles.isChecked() and dlg.always.isVisibleTo(dlg) and dlg.always.isChecked(), "beim nächsten Mal vorbelegt")
    dlg.agree.setChecked(True)
    dlg.accept()
    check(notice["shown"] == 2 and dlg.result() == QDialog.DialogCode.Accepted, "ohne Profilhinweis gestartet")
    dlg.always.setChecked(False)
    check(tab.settings.get("ts_profiles_always") is False, "immer aktiv wieder aus")
    tab.conn.setCurrentIndex(tab.conn.findData("oa"))
    tab.model.setCurrentIndex(tab.model.findData("gpt-4o-transcribe-diarize"))
    tab.sum_conn.setCurrentIndex(tab.sum_conn.findData("bot"))
    meeting = np.concatenate([silence(0.5), voice(*ALICE, 3.0, 5), silence(1.2), voice(*BOB, 3.0, 6), silence(1.5)])
    tab.make_sources = lambda: [FakeSource("system", meeting)]
    consent = {"agree": False, "profiles": True}

    def consent_exec(dlg):
        dlg.agree.setChecked(consent["agree"])
        dlg.profiles.setChecked(consent["profiles"])
        check(not dlg.start.isEnabled() if not consent["agree"] else dlg.start.isEnabled(),
              "Start nur mit Einwilligung")
        return QDialog.DialogCode.Accepted if consent["agree"] else QDialog.DialogCode.Rejected
    ts.ConsentDialog.exec = consent_exec
    tab.start()
    check(tab.recorder is None and tab.data is None, "ohne Einwilligung keine Aufnahme")
    consent["agree"] = True
    tab.start()
    check(tab.recorder is not None and tab.banner.isVisibleTo(tab), "Aufnahme läuft mit Hinweisbalken")
    check(tab.data["consent"]["at"] > 0 and tab.data["consent"]["profiles"], "Einwilligung gespeichert")
    check(wait(lambda: len(tab.data["segments"]) >= 4), "Abschnitte transkribiert")
    if shots:
        rs.pump(0.3)
        win.grab().save(str(shots / "kreeli.png"))
    tab.stop()
    check(wait(lambda: tab.worker is None) and wait(lambda: not tab._summarizing and tab.data.get("summary")),
          "beendet und automatisch zusammengefasst")
    check("Server-Umzug" in tab.data["summary"], "Zusammenfassung übernommen")
    names = {s["name"] for s in tab.data["speakers"].values()}
    check(len(tab.data["speakers"]) == 2 and "Sprecher 1" in names, f"zwei Sprecher {names}")
    saved = tab.services.storage.load_transcript(tab.data["id"])
    check(saved and saved["segments"] and all("embedding" not in s for s in saved["speakers"].values())
          and all("audio" not in s for s in saved["segments"]), "gespeichert ohne Stimmmerkmale")
    check((tab.services.storage.transcript_dir(tab.data["id"]) / "transcript.owai").exists(),
          "Mitschrift verschlüsselt")
    # Sprecher umbenennen und als Profil speichern
    first = next(sid for sid, s in tab.data["speakers"].items() if s["name"] == "Sprecher 1")
    tab.spk_table.selectRow(list(tab.data["speakers"]).index(first))
    QInputDialog.getText = staticmethod(lambda *a, **k: ("Alice", True))
    tab.save_profile()
    profiles = tab.profiles.load()
    check(profiles and profiles[0]["name"] == "Alice" and profiles[0].get("sample"), "Profil aus Mitschrift")
    check(tab.data["speakers"][first]["name"] == "Alice", "Sprecher heißt jetzt Alice")
    tab.reload()
    check(tab.history.count() == 1, "Mitschrift in der Liste")
    tab.to_chat()
    check(win.ai_panel.attachments and "Alice" in win.ai_panel.attachments[-1]["text"], "Mitschrift in die Chatleiste")
    win.ai_panel.attachments = []
    aikit.open_tool(win, ids["kreeli"], rs.pump)

    # Zweite Aufnahme: Deepgram (anonyme Sprecher) – Profil benennt die Stimme
    tab.conn.setCurrentIndex(tab.conn.findData("dg"))
    tab.auto_sum.setChecked(False)
    tab.make_sources = lambda: [FakeSource("system", meeting)]
    tab.start()
    check(wait(lambda: len(tab.data["segments"]) >= 2), "zweite Aufnahme transkribiert")
    tab.stop()
    check(wait(lambda: tab.worker is None), "zweite beendet")
    names = [s["name"] for s in tab.data["speakers"].values()]
    check("Alice" in names, f"Profil erkennt Alice wieder {names}")
    # Mikrofon = eigener Name
    tab.own.setText("Stef")
    tab.make_sources = lambda: [FakeSource("mic", meeting)]
    tab.start()
    check(wait(lambda: len(tab.data["segments"]) >= 2), "Mikrofon transkribiert")
    tab.stop()
    wait(lambda: tab.worker is None)
    check({s["name"] for s in tab.data["speakers"].values()} == {"Stef"}, "Mikrofon = eigener Name")
    tab.delete(tab.data["id"])
    check(tab.history.count() == 2, "Mitschrift gelöscht")

    # --- Mr. Zurkon – Sprachassistent ---------------------------------------------------------------
    zurkon = aikit.open_tool(win, ids["mr_zurkon"], rs.pump)
    va = sys.modules[type(zurkon).__module__.rsplit(".", 1)[0] + ".voice"]
    v = zurkon.page
    v.refresh()
    rs.pump(0.3)
    check(v.stack.currentIndex() == 1, "Sprachassistent bereit")
    check(v.panel is not win.ai_panel and v.panel.embedded, "eigener eingebetteter Chat")
    check(v.name.text() == "Zurkon" and va.wake_phrases("", "")[0] == "hey Zurkon", "Weckwort „Hey Zurkon“")
    check(not v.form.isRowVisible(v.engine_row) if v.wake_available() else v.form.isRowVisible(v.engine_row),
          "Hinweis zur Weckwort-Erkennung nur ohne Einrichtung")
    check(va.matches("hey klang wie spät", ["hey clank"]) and va.matches("Hey, Clank!", ["hey clank"])
          and not va.matches("heute klappt es", ["hey clank"]), "Weckwort unscharf")
    check(va.speakable("# Titel\n\n**Fett** und `code`\n```\nx\n```\n- Punkt", 500, "(Code im Chat)") ==
          "Titel Fett und code (Code im Chat) Punkt", "Vorlesetext ohne Markdown")
    check(len(va.speakable("Satz eins. " * 200, 100)) <= 102, "Vorlesetext gekürzt")
    v.stt.setCurrentIndex(v.stt.findData("oa"))
    v.tts.setCurrentIndex(v.tts.findData(va.SYSTEM_VOICE))
    v.panel.bot.setCurrentIndex(v.panel.bot.findData("bot"))
    question = np.concatenate([silence(0.3), voice(*ALICE, 1.5, 9), silence(2.0)])
    v.make_source = lambda: FakeSource("mic", question)
    CHAT["text"] = "Es ist **zehn** Uhr."
    v.talk()
    check(v.state == "command", "Knopf Sprechen: hört zu")
    check(wait(lambda: "Wie spät ist es?" in v.log.toPlainText()), "Frage erkannt")
    check(wait(lambda: v.state in ("followup", "off", "wake") and "zehn" in v.log.toPlainText()), "Antwort gelesen")
    msgs = v.panel.thread["messages"]
    check(msgs[0]["content"] == "Wie spät ist es?" and "zehn" in msgs[-1]["content"], "Frage und Antwort im Chat")
    sys_prompt = next(json.loads(b) for p, b, h in reversed(POSTS) if p == "/chat/v1/chat/completions")
    check("read aloud" in json.dumps(sys_prompt), "Hinweis für Sprachausgabe im Systemtext")
    v.off()
    check(v.state == "off" and v.mic is None, "ausgeschaltet")

    # Weckwort-Ablauf mit Fake-Erkennung (Vosk wird im Test nicht geladen)
    class FakeDetector:
        heard = ""

        def feed(self, samples):
            return "hey zurkon" if float(np.abs(samples).max()) > 0.1 else ""

        def reset(self):
            pass

        def transcribe(self, samples):
            return "offline frage"
    v.wake_available = lambda: True
    va.WakeDetector = lambda path, phrases: FakeDetector()
    wake_then_question = np.concatenate([silence(0.3), voice(*BOB, 0.3, 1), silence(0.5),
                                         voice(*ALICE, 1.5, 2), silence(2.5)])
    v.make_source = lambda: FakeSource("mic", wake_then_question)
    v.stt.setCurrentIndex(v.stt.findData(va.OFFLINE))
    v.tts.setCurrentIndex(v.tts.findData("oa"))
    v.followup.setChecked(False)
    CHAT["text"] = "Offline beantwortet."
    v.on_btn.setChecked(True)
    check(v.state in ("wake", "command"), "wartet auf Weckwort")
    check(wait(lambda: "offline frage" in v.log.toPlainText()), "Weckwort -> Frage offline erkannt")
    check(wait(lambda: "Offline beantwortet" in v.log.toPlainText()), "Antwort")
    check(wait(lambda: any(p == "/oa/v1/audio/speech" for p, b, h in POSTS)), "Vorlesen über Anbieter")
    check(wait(lambda: v.state == "wake", 20), "danach wieder Weckwort")
    v.off()
    rs.pump(0.3)
    # Sprache frei wählbar, Offline-Optionen, Stimmen je Anbieter
    v.refresh()
    check(v.stt.findData(va.WHISPER) >= 0 and v.tts.findData(va.PIPER) >= 0, "Whisper lokal und Piper wählbar")
    v.stt.setCurrentIndex(v.stt.findData(va.WHISPER))
    check(v.stt_model.count() == 4 and v.stt_model.currentData() == "small", "Whisper-Größen, small vorgewählt")
    check(not v.local_btn.isHidden() and "faster-whisper" in v.local_info.text(), "Einrichten-Hinweis für Whisper")
    v.tts.setCurrentIndex(v.tts.findData("gem"))
    check(v.voice.count() == 30 and v.voice.isEditable(), "Gemini-Stimmen in der Auswahl")
    v.voice.setCurrentIndex(v.voice.findData("Puck"))
    v.lang_box.setCurrentIndex(v.lang_box.findData("fr"))
    check(v._lang() == "fr", "andere Sprache als Programmsprache")
    v.tts.setCurrentIndex(v.tts.findData(va.PIPER))
    names = [v.voice.itemData(i) for i in range(v.voice.count())]
    check(names and all(n.startswith("fr_") for n in names), f"Piper-Stimmen der gewählten Sprache {names[:3]}")
    v.lang_box.setCurrentIndex(0)
    v._save_settings()
    check((zurkon.context.settings.get("va_voices") or {}).get(va.PIPER, "").startswith(zurkon.context.settings.get(
        "va_lang") or "de"), "Stimme je Ausgabe gemerkt")
    v.tts.setCurrentIndex(v.tts.findData("gem"))
    check(v.voice.currentData() == "Puck", "Gemini-Stimme wiederhergestellt")

    # Einstellungen › KI-Funktionen: Standard je Funktion
    from omniwrench.ai import defaults
    from omniwrench.ui.ai_defaults import DefaultsPage
    ov = DefaultsPage(settings, vault)
    labels = [ov.table.item(i, 0).text() for i in range(ov.table.rowCount())]
    check(len(labels) == len(defaults.FUNCTIONS) and "Chat" in labels[0], f"Übersicht: alle Funktionen {labels[:2]}")
    row = defaults.FUNCTIONS.index("va_tts")
    box = ov.combos[row]
    box.setCurrentIndex(box.findData("oa"))
    ov._chosen(row)
    v.refresh()
    check(defaults.get(settings, "va_tts") == "oa" and v.tts.currentData() == "oa", "Einstellung stellt das Tool um")
    row = defaults.FUNCTIONS.index("ts_stt")
    check(ov.combos[row].findData(va.WHISPER) >= 0, "Transkription: Whisper lokal in der Übersicht")
    from omniwrench.ai import scan
    store.settings.set(scan.SETTINGS_KEY, {"oa": {"ts": 1, "kinds": {"tts": {"status": "ok"}},
                                                  "account": {"balance": 4.5, "currency": "USD"}, "limits": {}}})
    ov.refresh()
    row = defaults.FUNCTIONS.index("va_tts")
    check("4.5" in ov.table.item(row, 3).text() and "✔" in ov.table.item(row, 2).text(),
          f"Prüfergebnis und Guthaben angezeigt ({ov.table.item(row, 3).text()})")
    # Wiedergabe auf dem aktuellen Gerät, Systemstimme je Ansage neu
    from omniwrench.ui import ai_kit
    check(ai_kit.output_device(settings) is not None, "Ausgabegerät ermittelt")
    if shots:
        ov.resize(1100, 600)
        ov.grab().save(str(shots / "ai_defaults.png"))
        v.setup.head.setChecked(True)
        v.stt.setCurrentIndex(v.stt.findData(va.WHISPER))
        rs.pump(0.3)
        win.grab().save(str(shots / "mr_zurkon.png"))
    for t in ids.values():
        aikit.close_tool(win, t, rs.pump)
    check(v.state == "off", "beim Schließen ausgeschaltet")
    print(f"OK: {OK} Prüfungen")
    return 0


if __name__ == "__main__":
    sys.exit(main())

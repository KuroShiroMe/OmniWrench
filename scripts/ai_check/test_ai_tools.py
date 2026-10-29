"""KI-Tools rund um die Aufteilung von Clank prüfen (ohne echte Anbieter und ohne Netz).

    python scripts/ai_check/test_ai_tools.py [--shots ORDNER]

Ollama einrichten (Fake-Dienst: Version, Modelle, Laden mit Fortschritt, Löschen; Dialog), Installation der KI-Tools
mit Opt-out-Auswahl und gemeinsamem Paketordner (pip ohne --upgrade, PYTHONPATH), Übernahme alter Clank-Einstellungen,
Kategorie „KI-Tools“, Fortschrittsbalken im Installationsfenster, alle KI-Tools öffnen und schließen.
"""

from __future__ import annotations

import http.server
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import render_screenshots as rs  # noqa: E402  (Temp-Home, offscreen, pump)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.settings import AppSettings  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402

OK = 0
AI_TOOLS = ("clank", "pixelizer", "groovitron", "vidcomic", "qforce", "infobot", "orvus", "kreeli", "mr_zurkon",
            "gadgetron")
MODELS = [{"name": "llama3.2:3b", "size": 2_000_000_000}]
PULLS: list[str] = []


def check(cond, text):
    global OK
    if not cond:
        raise AssertionError(text)
    OK += 1


def fake_ollama() -> str:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, data, code=200):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/api/version":
                self._json({"version": "0.13.0"})
            elif self.path == "/api/tags":
                self._json({"models": MODELS})
            else:
                self._json({}, 404)

        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path != "/api/pull":
                self._json({}, 404)
                return
            PULLS.append(body["model"])
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            if body["model"] == "kaputt":
                self.wfile.write(b'{"error": "pull model manifest: file does not exist"}\n')
                return
            for done in (0, 50, 100):
                self.wfile.write(json.dumps({"status": "pulling abc", "total": 100, "completed": done}).encode() + b"\n")
            self.wfile.write(b'{"status": "success"}\n')
            MODELS.append({"name": body["model"], "size": 5_200_000_000})

        def do_DELETE(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            MODELS[:] = [m for m in MODELS if m["name"] != body.get("model")]
            self._json({})

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/v1"


def test_ollama(base: str, shots) -> None:
    from omniwrench.ai import ollama
    check(ollama.root_url(base) == base[:-3] and ollama.is_local(base), "Adresse ohne /v1, lokal")
    check(ollama.version(base) == "0.13.0" and ollama.version("http://127.0.0.1:9/v1") == "", "Version / nicht erreichbar")
    lines = []
    ollama.pull("qwen3:8b", base, lines.append)
    check(any("50 %" in x for x in lines) and lines[-1] == "success", f"Laden mit Prozent {lines}")
    check([m["name"] for m in ollama.models(base)] == ["llama3.2:3b", "qwen3:8b"], "Modellliste")
    try:
        ollama.pull("kaputt", base)
        check(False, "Fehler beim Laden gemeldet")
    except RuntimeError as err:
        check("does not exist" in str(err), "Fehler beim Laden gemeldet")
    ollama.delete("qwen3:8b", base)
    check([m["name"] for m in ollama.models(base)] == ["llama3.2:3b"], "Modell gelöscht")
    from omniwrench.ui.ai_ollama import OllamaDialog
    dlg = OllamaDialog(base)
    check("0.13.0" in dlg.state.text() and dlg.models() == ["llama3.2:3b"], "Dialog: läuft, Modelle")
    check(not dlg.install_btn.isVisibleTo(dlg) and dlg.pull_btn.isEnabled(), "Dialog: Laden möglich")
    dlg.pick.setCurrentIndex(1)
    dlg.pull()
    check(PULLS[-1] == "qwen3:8b" and "qwen3:8b" in dlg.models(), "Dialog: Modell geladen")
    if shots:
        dlg.resize(700, 520)
        dlg.grab().save(str(shots / "ollama.png"))
    stopped = OllamaDialog("http://127.0.0.1:9/v1")
    check("✔" not in stopped.state.text() and not stopped.pull_btn.isEnabled(), "Dialog: Dienst aus")


def test_install(manager, settings) -> None:
    from omniwrench import sdk
    from omniwrench.ai import audio
    calls = []

    def fake_install(packages, progress=None, tool_dir=None):
        calls.append(list(packages))
        if progress:
            progress("Collecting " + packages[0])
        return ""
    real_install, real_missing = audio.install_packages, audio.missing
    audio.install_packages = fake_install
    audio.missing = lambda packages=audio.PACKAGES: [p for p in packages if p not in ("numpy",)]
    asked = []
    sdk.set_install_chooser(lambda title, text, options: (asked.append(options), [o[0] for o in options
                                                                                   if o[0] != "whisper"])[1])
    import omniwrench.ai.local_speech as ls
    real_vosk = ls.vosk_download
    ls.vosk_download = lambda data, lang, progress=None: progress and progress("50 %")
    ls.piper_voices = lambda data, lang: [("de_DE-thorsten-medium", 63)]
    ls.piper_download = lambda data, voice, progress=None: None
    try:
        log = []
        manager.install_dir(ROOT / "tools" / "mr_zurkon", log.append)
    finally:
        audio.install_packages, audio.missing, ls.vosk_download = real_install, real_missing, real_vosk
        sdk.set_install_chooser(None)
    check(asked and [o[0] for o in asked[0]] == ["wake", "whisper", "piper"] and all(o[2] for o in asked[0]),
          "Opt-out-Auswahl: Weckwort, Whisper, Piper vorbelegt")
    flat = [p for c in calls for p in c]
    check("vosk" in flat and "piper" in flat and "faster_whisper" not in flat and "numpy" not in flat,
          f"nur gewählte und fehlende Pakete {calls}")
    check(manager.tools["ai.mr-zurkon"].manifest.category == "ai", "Kategorie ai")
    from omniwrench.core import categories
    check("ai" in categories.AREAS, "Bereich KI-Tools")
    # pip-Aufruf: kein --upgrade, Ziel im PYTHONPATH (sonst WinError 5 bei geladenem numpy)
    import subprocess
    seen = {}

    class FakePopen:
        def __init__(self, cmd, **kw):
            seen.update(cmd=cmd, env=kw.get("env", {}))
            self.stdout = iter(["Successfully installed x\n"])
            self.returncode = 0

        def wait(self):
            return 0
    real_popen = subprocess.Popen
    subprocess.Popen = FakePopen
    try:
        check(audio.install_packages(["vosk"]) == "", "pip-Aufruf")
    finally:
        subprocess.Popen = real_popen
    check("--upgrade" not in seen["cmd"] and str(audio.lib_dir()) in seen["cmd"] and
          str(audio.lib_dir()) in seen["env"].get("PYTHONPATH", ""), "pip ohne --upgrade, Ziel im PYTHONPATH")


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
    vault.create(password="ai-tools-check")
    credentials.init(vault)
    settings = AppSettings()
    settings.set("check_updates_on_start", False)
    settings.set("repositories", [])
    base = fake_ollama()
    test_ollama(base, shots)

    # Alte Clank-Einstellungen (bis 1.0.2), die die neuen Tools übernehmen
    from omniwrench.core.jsonio import write_json
    from omniwrench.sdk import SecretStore
    write_json(paths.TOOL_SETTINGS_DIR / "ai.clank.json", {
        "schedules": [{"id": "j1", "name": "Alt"}], "image_connection": "img1", "image_models": {"img1": "m"},
        "va_name": "Clank", "va_lang": "fr", "mcp_servers": [{"id": "s1", "name": "Alt"}], "workspace": []})
    SecretStore("ai.clank", vault).set("mcp_server_token", "tok")
    SecretStore("ai.clank", vault).set("mcp:s1", "srv")

    manager = ToolManager(vault)
    test_install(manager, settings)
    import aikit
    ids = aikit.install(manager, *AI_TOOLS)
    from omniwrench.ui.main_window import MainWindow
    win = MainWindow(settings, vault, manager)
    win.resize(1400, 900)
    win.show()
    rs.pump(0.5)
    for name, tid in ids.items():
        tool = aikit.open_tool(win, tid, rs.pump)
        check(tool.root is not None and tool.root.isVisible(), f"{name} geöffnet")
        check(manager.tools[tid].manifest.category == "ai", f"{name} in KI-Tools")
    orvus = aikit.open_tool(win, ids["orvus"], rs.pump)
    jobs = orvus.context.settings.get("schedules") or []
    check(len(jobs) == 1 and jobs[0]["name"] == "Alt", f"Zeitpläne aus Clank übernommen {jobs}")
    from omniwrench.ai import defaults
    check(defaults.get(settings, "image") == "img1", "Bildanbieter aus Clank als Standard")
    zurkon = aikit.open_tool(win, ids["mr_zurkon"], rs.pump)
    check(zurkon.context.settings.get("va_lang") == "fr" and zurkon.context.settings.get("va_name") == "Clank",
          "Sprachassistent-Einstellungen übernommen")
    gad = aikit.open_tool(win, ids["gadgetron"], rs.pump)
    check(gad.context.secrets.get("mcp_server_token") == "tok" and gad.context.secrets.get("mcp:s1") == "srv",
          "MCP-Token aus dem Tresor übernommen")
    if shots:
        win.grab().save(str(shots / "ai_tools_home.png"))
    for tid in ids.values():
        aikit.close_tool(win, tid, rs.pump)
    check(not win.open_tools or all(o.tool_id not in ids.values() for o in win.open_tools.values()), "alle geschlossen")

    # Installationsfenster: „NN %“ stellt den Balken und ersetzt die vorige Zeile
    from omniwrench.ui.widgets import TaskDialog
    dlg = TaskDialog(None, "Test", lambda progress: None)
    dlg._append("Lade …")
    dlg._append("10 %")
    dlg._append("60 %")
    check(dlg.bar.maximum() == 100 and dlg.bar.value() == 60, "Balken folgt den Prozenten")
    check(dlg.log.toPlainText().count("%") == 1, f"Prozentzeile ersetzt {dlg.log.toPlainText()!r}")
    print(f"OK: {OK} Prüfungen")
    return 0


if __name__ == "__main__":
    sys.exit(main())

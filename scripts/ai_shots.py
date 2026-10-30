"""Gemeinsamer Aufbau für die Screenshots der KI-Tools (Clank, Pixelizer, Q-Force, Gadgetron …).

Die KI-Tools brauchen das Hauptfenster (KI-Dienste, Chatleiste); open_tool() baut deshalb ein MainWindow mit einer
Verbindung zu einem lokalen Fake-Server, der vorbereitete Antworten streamt, und legt Beispielbilder ab.
Aufruf aus screenshots/render.py eines Tools: sys.path enthält scripts/ (scripts/render_screenshots.py).
"""

from __future__ import annotations

import http.server
import json
import math
import os
import threading
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QRadialGradient

QUESTION = "Which DHCP scopes are almost full, and what should I do about them?"
ANSWER = """Two scopes are above 90 % usage on **dhcp01.contoso.example**:

| Scope | Name | Usage | Free |
|---|---|---|---|
| 10.20.30.0/24 | Office 2nd floor | 96 % | 9 |
| 10.20.40.0/24 | Wi-Fi guests | 92 % | 19 |

**Recommendations**

1. *Office 2nd floor*: shorten the lease time from 8 days to 1 day – 31 leases belong to devices not seen for over a week.
2. *Wi-Fi guests*: extend the pool to 10.20.40.10–10.20.41.250 (/23) or reduce the lease time to 4 hours.
3. Check the failover partner **dhcp02** afterwards – both scopes are replicated in load-balance mode.

Should I prepare the lease time change for the first scope? It needs your confirmation before anything is saved."""

GROUP = [
    ("Planner", "#8b5cf6", "Start with a pilot group of 50 clients in IT and Sales. Feature updates via Intune rings, "
     "legacy line-of-business apps tested in a VM first."),
    ("Security", "#22c55e", "Agree on the pilot. Before the first ring: BitLocker escrow check, LAPS v2 on all devices "
     "and a rollback image. ✓"),
    ("Helpdesk", "#f59e0b", "Add a short user guide and a 2-week freeze for the hotline. Printers on floor 2 need the "
     "new universal driver."),
]

IMAGES = [
    ("Abstract network map, violet and teal, glowing nodes", ("#1e1b4b", "#8b5cf6", "#2dd4bf")),
    ("Server room at dusk, soft neon light, isometric", ("#0f172a", "#f472b6", "#38bdf8")),
    ("Friendly robot mascot holding a wrench, flat style", ("#1f2937", "#f59e0b", "#a78bfa")),
    ("Data center aisle, cold blue light, wide angle", ("#082f49", "#22d3ee", "#e0f2fe")),
    ("Calm sunrise over a city made of circuit boards", ("#3b0764", "#fb923c", "#fde68a")),
    ("Shield icon made of light particles, dark background", ("#020617", "#4ade80", "#a3e635")),
]


def _server() -> str:
    state = {"n": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802
            body = json.dumps({"data": [{"id": "llama4"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            state["n"] += 1
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for i in range(0, len(ANSWER), 40):
                chunk = {"choices": [{"delta": {"content": ANSWER[i:i + 40]}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.close_connection = True

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/v1"


def _art(path, colors, seed: int) -> None:
    """Abstraktes Beispielbild (statt eines echten KI-Bildes)."""
    img = QImage(768, 768, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QLinearGradient(0, 0, 768, 768)
    bg.setColorAt(0, QColor(colors[0]))
    bg.setColorAt(1, QColor(colors[0]).darker(160))
    p.fillRect(img.rect(), bg)
    for i in range(14):
        a = seed * 1.7 + i * 0.9
        x, y = 384 + math.cos(a) * (120 + i * 16), 384 + math.sin(a * 1.3) * (110 + i * 14)
        r = 40 + (i * 37 + seed * 11) % 120
        g = QRadialGradient(QPointF(x, y), r)
        c = QColor(colors[1 + i % 2])
        c.setAlpha(170)
        g.setColorAt(0, c)
        c.setAlpha(0)
        g.setColorAt(1, c)
        p.setBrush(g)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
    p.end()
    img.save(str(path), "PNG")


def open_tool(shot):
    """Hauptfenster mit Fake-Assistent und Beispielbildern; öffnet shot.tool_id. Gibt (Fenster, Tool) zurück."""
    from omniwrench.ai.connections import Connection, ConnectionStore
    from omniwrench.ai.storage import Storage
    from omniwrench.core import paths
    from omniwrench.core.settings import AppSettings
    from omniwrench.ui.main_window import MainWindow

    settings = AppSettings()
    settings.set("check_updates_on_start", False)
    settings.set("repositories", [])
    settings.set("ai_storage_mode", "central")      # Beispieldaten im Temp-Home, nicht in „Dokumente“
    settings.set("ai_storage_root", str(paths.LOCAL_DIR / f"ai-shots-{shot.tool_id}"))
    vault = shot.manager.vault
    store = ConnectionStore(settings, vault)
    store.save(Connection(id="local", name="Llama 4 (local)", provider="ollama", base_url=_server(),
                          model="llama4", auth="none"))
    store.save(Connection(id="img", name="OpenAI", provider="openai", model="gpt-5", auth="api_key"))
    settings.set("ai_primary", "local")
    storage = Storage(settings, vault)
    for i, (prompt, colors) in enumerate(IMAGES):
        target = storage.media_target("images", " ".join(prompt.split()[:6]), ".png")
        _art(target, colors, i)
        created = int(time.time()) - i * 600
        target.with_suffix(".png.json").write_text(json.dumps(
            {"format": 1, "kind": "image", "file": target.name, "created": created,
             "prompt": prompt, "connection": "OpenAI", "model": "gpt-image-2", "aspect": "1:1"}), encoding="utf-8")
        os.utime(target, (created, created))           # Galerie sortiert nach Änderungszeit

    win = MainWindow(settings, vault, shot.manager)
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    win.resize(1280, 860)
    win.show()
    shot.wait(0.5)
    win.open_tool(shot.tool_id)
    shot.wait(0.5)
    tool = next(o for o in win.open_tools.values() if o.tool_id == shot.tool_id).instance
    extra = win.size() - tool.root.size()              # Tool-Bereich auf Screenshot-Größe bringen
    win.resize(1280 + extra.width(), 800 + extra.height())
    shot.wait(0.3)
    shot.widgets.append(win)
    return win, tool

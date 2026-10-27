"""Rendert die Screenshots der Tools für Store und Home.

    python scripts/render_screenshots.py                  # alle Tools mit screenshots/render.py
    python scripts/render_screenshots.py tools/netprobe   # nur dieses Tool
    python scripts/render_screenshots.py --lang de        # Oberflächensprache der Bilder (Standard: en)

Jedes Tool beschreibt seine Bilder selbst:

* tool.json  "screenshots": [{"file": "screenshots/overview.png", "caption": "…"}, …]
  Der erste Eintrag ist der Hauptscreenshot (Karte im Store/Home), danach je Funktion einer.
* screenshots/render.py  mit  def render(shot): …  - baut die Oberfläche mit Beispieldaten auf
  und speichert jedes Bild mit shot.save("<name>") (Name = Dateiname ohne .png aus tool.json).

Läuft ohne Bildschirm (Qt offscreen, echte Schriften über fontconfig) in einem leeren Temp-Ordner
(OMNIWRENCH_HOME): Das Tool wird dort nur abgelegt, nicht installiert - Windows-Tools lassen sich so
auch unter Linux rendern, solange render.py ein Fake-Backend benutzt. Danach scripts/build_store.py.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1280, 800  # 16:10, wie die Vorschau in Store und Home

_home = tempfile.TemporaryDirectory(prefix="omniwrench_shots_")
os.environ["OMNIWRENCH_HOME"] = _home.name  # vor dem Import von omniwrench (paths.py)
_screen = Path(_home.name) / "screen.json"
_screen.write_text(json.dumps({"screens": [{"name": "shots", "x": 0, "y": 0, "width": 3840, "height": 2160,
                                            "logicalDpi": 96, "dpr": 1}]}), encoding="utf-8")
os.environ.setdefault("QT_QPA_PLATFORM", f"offscreen:configfile={_screen.as_posix()}")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QEventLoop, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.manifest import ToolManifest  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402
from omniwrench.ui import theme  # noqa: E402

log = logging.getLogger("render_screenshots")


def pump(seconds: float = 0.2) -> None:
    end = time.monotonic() + seconds
    while True:
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if time.monotonic() >= end:
            return
        time.sleep(0.01)


class Shot:
    """Wird an render(shot) übergeben."""

    def __init__(self, manager: ToolManager, tool_id: str, source: Path, lang: str):
        self.manager = manager
        self.tool_id = tool_id
        self.source = source            # Tool-Ordner im Repository (dort landen die Bilder)
        self.lang = lang
        self.saved: list[str] = []
        self.instances = []
        self.widgets: list[QWidget] = []

    @property
    def tool(self):
        return self.manager.get(self.tool_id)

    @property
    def settings(self):
        """Einstellungen des Tools (vor create() setzen, z. B. Beispielwerte)."""
        return self.tool.settings

    def module(self, name: str):
        """Modul aus dem Tool-Paket, z. B. shot.module("backend")."""
        return self.manager._import_module(self.tool, name)

    def create(self, width: int = WIDTH, height: int = HEIGHT):
        """Neue Tool-Instanz mit Oberfläche in Screenshot-Größe -> (instance, widget)."""
        instance = self.manager.create_instance(self.tool_id, notify=lambda _m: None)
        widget = instance.create_widget(None)
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        widget.resize(width, height)
        widget.show()
        self.instances.append(instance)
        self.widgets.append(widget)
        self.wait(0.3)
        return instance, widget

    def wait(self, seconds: float = 0.2) -> None:
        pump(seconds)

    def wait_until(self, condition, timeout: float = 15, what: str = "Bedingung") -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return
            pump(0.05)
        raise TimeoutError(f"Zeitüberschreitung: {what}")

    def save(self, name: str, widget: QWidget | None = None) -> Path:
        """Speichert widget (Standard: zuletzt erzeugte Oberfläche) als screenshots/<name>.png."""
        widget = widget or self.widgets[-1]
        self.wait(0.15)
        target = self.source / "screenshots" / f"{name}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        widget.grab().save(str(target), "PNG", 9)
        self.saved.append(f"screenshots/{name}.png")
        print(f"    {target.relative_to(ROOT) if ROOT in target.parents else target}", flush=True)
        return target

    def save_dialog(self, name: str, dialog: QWidget, base: QWidget | None = None) -> Path:
        """Dialog mittig über der Oberfläche (abgedunkelt, mit Titelleiste) als ein Bild speichern."""
        base = base or self.widgets[-1]
        dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        dialog.show()
        self.wait(0.3)
        image = base.grab()
        dlg = dialog.grab()
        bar = 34
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(image.rect(), QColor(0, 0, 0, 120))
        x = (image.width() - dlg.width()) // 2
        y = max(10, (image.height() - dlg.height() - bar) // 2)
        frame = QRect(x, y, dlg.width(), dlg.height() + bar)
        for i in range(12, 0, -2):  # weicher Schatten
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 14))
            p.drawRoundedRect(frame.adjusted(-i, -i + 4, i, i + 4), 10 + i, 10 + i)
        c = theme.current
        p.setBrush(QColor(c["surface2"]))
        p.setPen(QColor(c["border"]))
        p.drawRoundedRect(frame, 8, 8)
        p.setPen(QColor(c["text"]))
        p.drawText(QRect(x + 14, y, dlg.width() - 28, bar), Qt.AlignmentFlag.AlignVCenter, dialog.windowTitle())
        p.drawPixmap(x, y + bar, dlg)
        p.end()
        dialog.hide()
        target = self.source / "screenshots" / f"{name}.png"
        image.save(str(target), "PNG", 9)
        self.saved.append(f"screenshots/{name}.png")
        print(f"    {target.relative_to(ROOT) if ROOT in target.parents else target}", flush=True)
        return target

    def close(self) -> None:
        for instance in self.instances:
            try:
                instance.shutdown()
            except Exception:  # noqa: BLE001
                log.warning("shutdown %s:\n%s", self.tool_id, traceback.format_exc())
        for w in self.widgets:
            w.hide()
            w.deleteLater()
        pump(0.1)


def render_tool(manager: ToolManager, source: Path, lang: str) -> list[str]:
    """Rendert ein Tool; Rückgabe: Probleme."""
    manifest = ToolManifest.load(source)
    script = source / "screenshots" / "render.py"
    if not script.is_file():
        return [f"{manifest.id}: screenshots/render.py fehlt"]
    print(f"  {manifest.id} {manifest.version}", flush=True)
    target = paths.TOOLS_DIR / manifest.id
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=lambda d, names: [
        n for n in names if n in ("__pycache__", "_lib") or n.endswith(".pyc")
        or (Path(d).name == "screenshots" and n.endswith(".png"))])
    lib = source / "_lib"  # pip-Pakete einer lokalen Installation mitbenutzen, falls vorhanden
    if lib.is_dir():
        sys.path.insert(0, str(lib))
    manager.refresh()
    shot = Shot(manager, manifest.id, source, lang)
    try:
        module = manager._import_module(manager.get(manifest.id), "screenshots.render")
        module.render(shot)
    except Exception:  # noqa: BLE001
        return [f"{manifest.id}: render.py fehlgeschlagen:\n{traceback.format_exc()}"]
    finally:
        shot.close()
    wanted = [s["file"] for s in manifest.screenshot_list]
    problems = [f"{manifest.id}: {f} steht in tool.json, wurde aber nicht gerendert" for f in wanted
                if f not in shot.saved]
    problems += [f"{manifest.id}: {f} gerendert, fehlt aber in tool.json" for f in shot.saved if f not in wanted]
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tools", nargs="*", type=Path, help="Tool-Ordner (Standard: alle in tools/)")
    ap.add_argument("--lang", default="en", help="Sprache der Oberfläche in den Bildern (Standard: en)")
    ap.add_argument("--theme", default="dark", choices=("dark", "light"))
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(name)s: %(message)s")
    paths.ensure_dirs()
    QMessageBox.exec = lambda self: QMessageBox.StandardButton.Ok  # keine blockierenden Dialoge
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    from omniwrench.app import apply_language
    from omniwrench.core.settings import AppSettings
    AppSettings().set("language", args.lang)
    apply_language(app, args.lang)
    theme.apply_theme(app, args.theme)

    vault = Vault(paths.VAULT_FILE)
    vault.create(password="render-screenshots")
    credentials.init(vault)
    manager = ToolManager(vault)

    sources = [p.resolve() for p in args.tools] or sorted(
        p for p in (ROOT / "tools").iterdir() if (p / "screenshots" / "render.py").is_file())
    problems: list[str] = []
    for source in sources:
        problems += render_tool(manager, source, args.lang)
    for p in problems:
        print(p, file=sys.stderr)
    print("Screenshots fertig" if not problems else f"{len(problems)} Problem(e)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

"""Starttest ohne Benutzereingaben (für CI und lokal).

    python scripts/smoke_test.py               # Fenster unsichtbar (QT_QPA_PLATFORM=offscreen)
    python scripts/smoke_test.py --visible     # mit echten Fenstern (Windows-Desktop)

Ablauf in einem leeren Temp-Ordner (OMNIWRENCH_HOME): Tresor anlegen, alle Tools ohne
System-Voraussetzungen aus dem lokalen Store (store/index.json) installieren, dann für jede
Sprache das Hauptfenster aufbauen, Store-Tab und alle Tools öffnen, Fenstergrößen durchspielen
und wieder schließen. Jede Fehlermeldung (QMessageBox, Log-Eintrag ab ERROR, unbehandelte
Ausnahme) lässt den Test fehlschlagen. Tools mit Windows-Funktionen/PS-Modulen/winget (z. B. RSAT)
werden nur geprüft, nicht installiert, damit keine System-Änderungen passieren.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_REQS = ("windows_capabilities", "windows_features", "powershell_modules", "winget")

if "--visible" not in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_home = tempfile.TemporaryDirectory(prefix="omniwrench_smoke_")
os.environ["OMNIWRENCH_HOME"] = _home.name  # vor dem Import von omniwrench (paths.py liest es beim Import)
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from omniwrench import __version__  # noqa: E402
from omniwrench.core import credentials, i18n, paths  # noqa: E402
from omniwrench.core.manifest import validate_package  # noqa: E402
from omniwrench.core.settings import AppSettings  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402

errors: list[str] = []


class _ErrorCollector(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        errors.append(f"Log {record.levelname} {record.name}: {self.format(record)}")


def _message_box(kind: str, default):
    def show(parent, title, text, *args, **kwargs):
        errors.append(f"QMessageBox.{kind}: {title}: {text}")
        return default
    return staticmethod(show)


def _excepthook(exc_type, exc, tb) -> None:
    errors.append("Unbehandelte Ausnahme:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))


def pump(seconds: float = 0.3) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        time.sleep(0.01)


def wait_for(condition, timeout: float, what: str) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return
        pump(0.05)
    errors.append(f"Zeitüberschreitung: {what}")


def step(text: str) -> None:
    print(f"[smoke] {text}", flush=True)


def main() -> int:
    paths.ensure_dirs()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    collector = _ErrorCollector(logging.ERROR)
    logging.getLogger().addHandler(collector)
    sys.excepthook = _excepthook
    QMessageBox.critical = _message_box("critical", QMessageBox.StandardButton.Ok)
    QMessageBox.warning = _message_box("warning", QMessageBox.StandardButton.Ok)
    QMessageBox.question = _message_box("question", QMessageBox.StandardButton.No)

    step(f"OmniWrench {__version__}, Python {sys.version.split()[0]}, OMNIWRENCH_HOME={_home.name}")
    settings = AppSettings()
    settings.set("check_updates_on_start", False)
    settings.set("repositories", [{"name": "Local", "url": str(ROOT / "store" / "index.json"), "enabled": True}])

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    from omniwrench.app import apply_language
    from omniwrench.ui import theme
    apply_language(app, "de")
    theme.apply_theme(app, "dark")

    vault = Vault(paths.VAULT_FILE)
    vault.create(password="smoke-test-passwort")
    credentials.init(vault)
    manager = ToolManager(vault)
    from omniwrench.ui.credentials import install_auth_handler
    install_auth_handler()

    # Tools aus dem lokalen Store installieren (prüft auch ZIPs und sha256)
    index = json.loads((ROOT / "store" / "index.json").read_text(encoding="utf-8"))
    sources = {validate_package(p).id: p for p in (ROOT / "tools").iterdir() if (p / "tool.json").is_file()}
    for entry in index["tools"]:
        reqs = entry.get("requirements") or {}
        if any(reqs.get(k) for k in SYSTEM_REQS):
            step(f"{entry['id']}: nur Paketprüfung (System-Voraussetzungen werden nicht installiert)")
            validate_package(sources[entry["id"]])
            continue
        step(f"{entry['id']} {entry['version']}: installieren")
        try:
            manager.install_zip(ROOT / "store" / entry["download_url"], lambda m: None, entry["sha256"])
        except Exception:  # noqa: BLE001
            errors.append(f"Installation {entry['id']} fehlgeschlagen:\n{traceback.format_exc()}")
    manager.run_hooks("startup")
    for tool_id, tool in manager.tools.items():
        if tool.error:
            errors.append(f"{tool_id} defekt: {tool.error}")

    from omniwrench.ui.main_window import MainWindow
    languages = sorted(i18n.load_locales(i18n.APP_LOCALES_DIR))
    for code in languages:
        step(f"Hauptfenster in Sprache {code}")
        settings.set("language", code)
        apply_language(app, code)
        manager.refresh()
        window = MainWindow(settings, vault, manager)
        window.show()
        pump()
        window.show_store()
        wait_for(lambda: window.catalog is not None, 30, f"Store-Katalog ({code})")
        for tool_id in sorted(manager.tools):
            before = len(window.open_tools)
            window.open_tool(tool_id)
            pump(0.2)
            if len(window.open_tools) <= before and not manager.tools[tool_id].manifest.single_instance:
                errors.append(f"{tool_id} ließ sich nicht öffnen ({code})")
        for width in (900, 1400, 2560):
            window.resize(width, 800)
            pump(0.1)
        window.show_home()
        window.close()
        window.deleteLater()
        pump()

    vault.lock()
    app.quit()
    if errors:
        print("\nStarttest FEHLGESCHLAGEN:", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)
        return 1
    step(f"OK: {len(manager.tools)} Tools, {len(languages)} Sprachen")
    return 0


if __name__ == "__main__":
    code = main()
    logging.shutdown()  # Logdateien schließen, sonst kann Windows den Temp-Ordner nicht löschen
    try:
        _home.cleanup()
    except OSError:
        pass
    sys.exit(code)

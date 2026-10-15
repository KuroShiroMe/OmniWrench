"""Programmstart: Logging, Sprache, Theme, Anmeldung, Hauptfenster."""

from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback

from PySide6.QtCore import QLibraryInfo, Qt, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from admintools import APP_ID, APP_NAME, __version__
from admintools.core import i18n, net, paths
from admintools.core.i18n import tr
from admintools.core.settings import AppSettings
from admintools.core.tool_manager import ToolManager
from admintools.core.vault import Vault

_qt_translator: QTranslator | None = None


def _setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        paths.LOG_DIR / "admintools.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if not getattr(sys, "frozen", False):
        root.addHandler(logging.StreamHandler())


def _excepthook(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    logging.getLogger("admintools").error("Unbehandelter Fehler:\n%s", text)
    if QApplication.instance():
        QMessageBox.critical(None, APP_NAME, tr("app.unexpected_error", error=exc))


def apply_language(app: QApplication, code: str) -> None:
    """Setzt die Programmsprache und lädt passende Qt-Standardtexte (Ja/Nein, Abbrechen …)."""
    global _qt_translator
    i18n.set_language(code)
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    qt_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for lang in i18n.app_chain():  # Dialekte nutzen die Qt-Texte ihrer Basissprache
        translator = QTranslator(app)
        if translator.load(f"qtbase_{lang.split('_')[0]}", qt_dir):
            app.installTranslator(translator)
            _qt_translator = translator
            break


def main() -> int:
    paths.ensure_dirs()
    _setup_logging()
    sys.excepthook = _excepthook
    logging.getLogger("admintools").info("%s %s startet", APP_NAME, __version__)

    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)  # eigenes Taskleisten-Icon

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    # Beenden steuert das Hauptfenster selbst (sonst würde der UI-Neuaufbau das Programm beenden)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(paths.RESOURCES_DIR / "app.svg")))

    from admintools.ui import theme  # nach QApplication importieren
    from admintools.ui.login_dialog import LoginDialog

    settings = AppSettings()
    apply_language(app, settings.get("language", ""))
    theme.apply_theme(app, settings.get("theme", "dark"))

    vault = Vault(paths.VAULT_FILE)
    if not LoginDialog(vault).exec():
        return 0
    net.github_token = vault.get("app:github_token") or None

    from admintools.ui.main_window import MainWindow

    manager = ToolManager(vault)
    windows: list[MainWindow] = []

    def open_window(restart: bool = False) -> None:
        if windows:
            old = windows.pop()
            old.deleteLater()
        if restart:
            apply_language(app, settings.get("language", ""))
            manager.refresh()  # übersetzte Tool-Namen neu einlesen
        window = MainWindow(settings, vault, manager, force_restore=restart)
        window.restartRequested.connect(lambda: open_window(restart=True))
        windows.append(window)
        window.show()

    open_window()
    return app.exec()

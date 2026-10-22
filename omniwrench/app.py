"""Programmstart: Logging, Sprache, Theme, Anmeldung, Hauptfenster."""

from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback

from PySide6.QtCore import QLibraryInfo, Qt, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from omniwrench import APP_ID, APP_MUTEX, APP_NAME, __version__
from omniwrench.core import credentials, i18n, net, paths
from omniwrench.core.i18n import tr
from omniwrench.core.settings import AppSettings
from omniwrench.core.tool_manager import ToolManager
from omniwrench.core.vault import Vault

_qt_translator: QTranslator | None = None
_app_mutex = None


def _setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        paths.LOG_DIR / "omniwrench.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if not getattr(sys, "frozen", False):
        root.addHandler(logging.StreamHandler())


def _excepthook(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    logging.getLogger("omniwrench").error("Unbehandelter Fehler:\n%s", text)
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
    log = logging.getLogger("omniwrench")
    log.info("%s %s startet (%s, Programm: %s, Daten: %s)", APP_NAME, __version__, paths.INSTALL_KIND,
             paths.APP_DIR, paths.CONFIG_DIR)
    for line in paths.MIGRATION_LOG:
        log.info(line)

    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)  # eigenes Taskleisten-Icon
        # Das Installationsprogramm wartet, solange dieser Mutex existiert (Update, Deinstallation)
        global _app_mutex
        _app_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, APP_MUTEX)

    settings = AppSettings()
    from omniwrench.ui import scaling  # importiert nur Qt-Module, erzeugt noch keine QApplication
    scaling.apply_scale_factor(settings.get("ui_scale", 1.0))  # muss vor QApplication(...) passieren

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setDesktopFileName("omniwrench")  # Linux: Symbol/Gruppierung über omniwrench.desktop
    # Beenden steuert das Hauptfenster selbst (sonst würde der UI-Neuaufbau das Programm beenden)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(paths.RESOURCES_DIR / "app.svg")))

    from omniwrench.ui import theme  # nach QApplication importieren
    from omniwrench.ui.login_dialog import LoginDialog

    apply_language(app, settings.get("language", ""))
    theme.apply_theme(app, settings.get("theme", "dark"))

    vault = Vault(paths.VAULT_FILE)
    if not LoginDialog(vault).exec():
        return 0
    net.github_token = vault.get("app:github_token") or None
    credentials.init(vault)

    from omniwrench.ui.main_window import MainWindow

    manager = ToolManager(vault)
    from omniwrench.ui.credentials import install_auth_handler
    install_auth_handler()            # Rückfrage, wenn ein Passwortmanager neue Zugangsdaten braucht
    manager.run_hooks("startup")      # z. B. Konnektoren des Password Manager Manager registrieren
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

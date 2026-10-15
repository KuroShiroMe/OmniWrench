"""Hauptfenster: Seitenleiste + frei anordenbare Tabs (Qt Advanced Docking System)."""

from __future__ import annotations

import base64
import logging
import os
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import PySide6QtAds as ads
from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QVBoxLayout,
    QWidget,
)

from omniwrench import APP_NAME, GITHUB_REPO, VENDOR, __version__
from omniwrench.core import app_updater, repository
from omniwrench.core.i18n import tr
from omniwrench.core.jsonio import read_json, write_json
from omniwrench.core.paths import APP_DIR, LAYOUT_FILE, LOG_DIR, RESOURCES_DIR
from omniwrench.core.repository import Catalog, CatalogEntry
from omniwrench.core.settings import AppSettings
from omniwrench.core.tool_manager import ToolManager
from omniwrench.core.vault import Vault
from omniwrench.sdk import ToolBase

from . import theme
from .home_page import HomePage
from .login_dialog import LoginDialog
from .settings_dialogs import AppSettingsDialog, ToolSettingsDialog
from .sidebar import Sidebar
from .store_page import StorePage
from .widgets import TaskDialog, tool_icon
from .workers import run_async

log = logging.getLogger(__name__)
CF = ads.CDockManager.eConfigFlag
DWF = ads.CDockWidget.DockWidgetFeature


@dataclass
class OpenTool:
    tool_id: str
    instance: ToolBase
    dock: ads.CDockWidget
    listeners: list[Callable] = field(default_factory=list)


class _ActivityFilter(QObject):
    """Startet den Auto-Sperre-Timer bei Benutzeraktivität neu."""

    def __init__(self, timer: QTimer):
        super().__init__()
        self.timer = timer

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.Wheel) \
                and self.timer.interval() > 0:
            self.timer.start()
        return False


class MainWindow(QMainWindow):
    catalogChanged = Signal()
    # Oberfläche neu aufbauen (z. B. nach Sprachwechsel) - wird in app.py behandelt
    restartRequested = Signal()

    def __init__(self, settings: AppSettings, vault: Vault, manager: ToolManager, force_restore: bool = False):
        super().__init__()
        self.settings = settings
        self.vault = vault
        self.manager = manager
        self.catalog: Catalog | None = None
        self.tool_updates: dict[str, CatalogEntry] = {}
        self.app_release: app_updater.AppRelease | None = None
        self.open_tools: dict[str, OpenTool] = {}
        self._locked = False
        self._force_quit = False
        self._restarting = False

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setWindowIcon(QIcon(str(RESOURCES_DIR / "app.svg")))
        self.resize(1400, 860)

        self._build_dock_manager()
        self._build_menus()
        self._build_statusbar()
        self._setup_auto_lock()
        if settings.get("restore_layout", True) or force_restore:
            self._restore_layout()

        if not force_restore:
            QTimer.singleShot(300, lambda: self.check_updates(manual=False))

    # ================================================================ Aufbau
    def _build_dock_manager(self) -> None:
        for flag, on in (
            (CF.OpaqueSplitterResize, True), (CF.FocusHighlighting, True), (CF.AllTabsHaveCloseButton, True),
            (CF.DockAreaHasCloseButton, False), (CF.DockAreaHasTabsMenuButton, True),
            (CF.MiddleMouseButtonClosesTab, True), (CF.EqualSplitOnInsertion, True), (CF.AlwaysShowTabs, True),
            (CF.FloatingContainerHasWidgetTitle, True), (CF.FloatingContainerHasWidgetIcon, True),
            (CF.DockAreaHideDisabledButtons, True),
        ):
            ads.CDockManager.setConfigFlag(flag, on)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        dock_host = QWidget()
        host_lay = QVBoxLayout(dock_host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        self.dm = ads.CDockManager(dock_host)
        self._ads_base_style = self.dm.styleSheet()
        self.dm.setStyleSheet(self._ads_base_style + theme.ads_stylesheet())
        host_lay.addWidget(self.dm)
        self.setCentralWidget(splitter)

        # Home (immer geöffnet)
        self.home_dock = ads.CDockWidget(self.dm, tr("nav.home"))
        self.home_dock.setObjectName("home")
        self.home_dock.setWidget(HomePage(self))
        self.home_dock.setIcon(QIcon(str(RESOURCES_DIR / "app.svg")))
        self.home_dock.setFeature(DWF.DockWidgetClosable, False)
        self.home_area = self.dm.addDockWidget(ads.CenterDockWidgetArea, self.home_dock)

        # Store (bei Bedarf eingeblendet)
        self.store_page = StorePage(self)
        self.store_dock = ads.CDockWidget(self.dm, tr("nav.store"))
        self.store_dock.setObjectName("store")
        self.store_dock.setWidget(self.store_page)
        self.dm.addDockWidgetTabToArea(self.store_dock, self.home_area)
        self.store_dock.toggleView(False)
        self.home_dock.setAsCurrentTab()

        self.sidebar = Sidebar(self)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(dock_host)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([250, 1150])

    def _build_menus(self) -> None:
        mb = self.menuBar()

        m = mb.addMenu(tr("menu.file"))
        m.addAction(tr("menu.install_zip"), self.install_from_zip)
        m.addAction(tr("menu.install_folder"), self.install_from_folder)
        m.addSeparator()
        m.addAction(tr("menu.lock"), QKeySequence("Ctrl+L"), self.lock)
        m.addAction(tr("menu.quit"), QKeySequence("Ctrl+Q"), self.close)

        m = mb.addMenu(tr("menu.view"))
        self.act_sidebar = QAction(tr("menu.sidebar"), self, checkable=True, checked=True)
        self.act_sidebar.setShortcut("Ctrl+B")
        self.act_sidebar.toggled.connect(self.sidebar.setVisible)
        m.addAction(self.act_sidebar)
        m.addAction(tr("nav.home"), QKeySequence("Ctrl+H"), self.show_home)
        m.addAction(tr("nav.store"), QKeySequence("Ctrl+Shift+S"), self.show_store)
        m.addSeparator()
        m.addAction(tr("menu.reset_layout"), self.reset_layout)

        m = mb.addMenu(tr("menu.extras"))
        m.addAction(tr("menu.check_updates"), lambda: self.check_updates(manual=True))
        m.addAction(tr("menu.settings"), QKeySequence("Ctrl+,"), self.open_app_settings)

        m = mb.addMenu(tr("menu.help"))
        m.addAction(tr("menu.dev_docs"), lambda: self._open_path(APP_DIR / "docs" / "TOOL_ENTWICKLUNG.md"))
        m.addAction(tr("menu.log_folder"), lambda: self._open_path(LOG_DIR))
        m.addSeparator()
        m.addAction(tr("menu.about"), self._about)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.update_btn = QPushButton()
        self.update_btn.setFlat(True)
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.hide()
        self.update_btn.clicked.connect(self._update_button_clicked)
        sb.addPermanentWidget(self.update_btn)

    def notify(self, message: str, timeout: int = 6000) -> None:
        self.statusBar().showMessage(message, timeout)

    # ========================================================= Navigation
    def show_home(self) -> None:
        self.home_dock.toggleView(True)
        self.home_dock.setAsCurrentTab()
        self.home_dock.raise_()

    def show_store(self) -> None:
        if self.store_dock.isClosed():
            area = self._target_area()
            if area is not None and self.store_dock.dockAreaWidget() is not area:
                self.dm.addDockWidgetTabToArea(self.store_dock, area)
            self.store_dock.toggleView(True)
        self.store_dock.setAsCurrentTab()
        self.store_dock.raise_()
        if self.catalog is None:
            self.reload_catalog()

    def _target_area(self):
        """Bereich, in dem neue Tabs geöffnet werden: zuletzt fokussierter Bereich, sonst Home."""
        focused = self.dm.focusedDockWidget()
        for dock in (focused, self.home_dock):
            if dock is not None and not dock.isClosed() and dock.dockAreaWidget() is not None:
                return dock.dockAreaWidget()
        return None

    # =========================================================== Tools
    def _free_dock_name(self, tool_id: str) -> str:
        n = 1
        while f"tool:{tool_id}:{n}" in self.open_tools:
            n += 1
        return f"tool:{tool_id}:{n}"

    def _create_tool_widget(self, tool_id: str) -> tuple[ToolBase, QWidget] | None:
        tool = self.manager.get(tool_id)
        try:
            instance = self.manager.create_instance(
                tool_id, notify=self.notify, open_settings=lambda: self.open_tool_settings(tool_id))
            return instance, instance.create_widget(None)
        except Exception as exc:  # noqa: BLE001
            log.error("Tool %s konnte nicht gestartet werden:\n%s", tool_id, traceback.format_exc())
            QMessageBox.critical(self, tr("tool.start_error_title"),
                                 tr("tool.start_error", name=tool.manifest.display_name, error=exc))
            return None

    def _register_instance(self, name: str, tool_id: str, instance: ToolBase, dock: ads.CDockWidget) -> None:
        tool = self.manager.get(tool_id)
        entry = OpenTool(tool_id, instance, dock)
        cb = instance.on_settings_changed
        tool.settings.on_change(cb)
        entry.listeners.append(cb)
        self.open_tools[name] = entry

    def open_tool(self, tool_id: str, dock_name: str | None = None, focus: bool = True) -> None:
        tool = self.manager.get(tool_id)
        if tool is None:
            return
        if tool.manifest.single_instance:
            existing = [o for o in self.open_tools.values() if o.tool_id == tool_id]
            if existing:
                existing[0].dock.setAsCurrentTab()
                existing[0].dock.raise_()
                return
        name = dock_name or self._free_dock_name(tool_id)
        created = self._create_tool_widget(tool_id)
        if created is None:
            return
        instance, widget = created

        same = sum(1 for o in self.open_tools.values() if o.tool_id == tool_id)
        title = tool.manifest.display_name + (f" ({same + 1})" if same else "")
        dock = ads.CDockWidget(self.dm, title)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setIcon(tool_icon(tool.manifest, tool.path, 16))
        dock.setTabToolTip(f"{tool.manifest.display_name} {tool.manifest.version}")
        dock.setFeature(DWF.DockWidgetDeleteOnClose, True)
        dock.setFeature(DWF.CustomCloseHandling, True)
        dock.closeRequested.connect(lambda n=name: self.close_tool(n))

        area = self._target_area()
        if area is not None:
            self.dm.addDockWidgetTabToArea(dock, area)
        else:
            self.dm.addDockWidget(ads.CenterDockWidgetArea, dock)

        self._register_instance(name, tool_id, instance, dock)
        if focus:
            dock.setAsCurrentTab()
            dock.raise_()

    def reload_tool_tabs(self, tool_id: str) -> None:
        """Baut alle offenen Tabs eines Tools mit neuer Instanz neu auf (z. B. nach Sprachwechsel)."""
        for name, entry in [(n, o) for n, o in self.open_tools.items() if o.tool_id == tool_id]:
            if not entry.instance.can_close():
                continue
            self._shutdown_instance(entry)
            del self.open_tools[name]
            created = self._create_tool_widget(tool_id)
            if created is None:
                entry.dock.closeDockWidget()
                continue
            instance, widget = created
            old = entry.dock.takeWidget()
            entry.dock.setWidget(widget)
            if old is not None:
                old.deleteLater()
            self._register_instance(name, tool_id, instance, entry.dock)

    def close_tool(self, name: str, force: bool = False) -> bool:
        entry = self.open_tools.get(name)
        if entry is None:
            return True
        if not force:
            try:
                if not entry.instance.can_close():
                    return False
            except Exception:  # noqa: BLE001
                log.exception("can_close() fehlgeschlagen")
        self._shutdown_instance(entry)
        del self.open_tools[name]
        entry.dock.closeDockWidget()
        return True

    def _shutdown_instance(self, entry: OpenTool) -> None:
        try:
            entry.instance.shutdown()
        except Exception:  # noqa: BLE001
            log.exception("shutdown() von %s fehlgeschlagen", entry.tool_id)
        tool = self.manager.get(entry.tool_id)
        if tool:
            for cb in entry.listeners:
                tool.settings.remove_listener(cb)

    def close_tool_instances(self, tool_id: str) -> bool:
        names = [n for n, o in self.open_tools.items() if o.tool_id == tool_id]
        return all(self.close_tool(n) for n in names)

    def show_tool_menu(self, tool_id: str, global_pos) -> None:
        tool = self.manager.get(tool_id)
        if tool is None:
            return
        menu = QMenu(self)
        act_open = menu.addAction(tr("common.open"), lambda: self.open_tool(tool_id))
        font = QFont(act_open.font())
        font.setBold(True)
        act_open.setFont(font)
        menu.addAction(tr("toolmenu.settings"), lambda: self.open_tool_settings(tool_id))
        upd = self.tool_updates.get(tool_id)
        act_upd = menu.addAction(tr("toolmenu.update_to", version=upd.manifest.version) if upd
                                 else tr("toolmenu.update"), lambda: self.install_entry(upd))
        act_upd.setEnabled(upd is not None)
        menu.addSeparator()
        menu.addAction(tr("toolmenu.check"), lambda: self.check_tool(tool_id))
        menu.addAction(tr("toolmenu.repair"), lambda: self.repair_tool(tool_id))
        menu.addAction(tr("toolmenu.open_folder"), lambda: self._open_path(tool.path))
        menu.addSeparator()
        menu.addAction(tr("toolmenu.uninstall"), lambda: self.uninstall_tool(tool_id))
        menu.exec(global_pos)

    def open_tool_settings(self, tool_id: str) -> None:
        tool = self.manager.get(tool_id)
        if tool is None:
            return
        dlg = ToolSettingsDialog(tool, self)
        if dlg.exec() and dlg.language_changed:
            self.reload_tool_tabs(tool_id)

    # ===================================================== Installation
    def install_entry(self, entry: CatalogEntry | None) -> None:
        if entry is None:
            return
        tool_id = entry.manifest.id
        name = entry.manifest.display_name
        if any(o.tool_id == tool_id for o in self.open_tools.values()):
            if QMessageBox.question(self, tr("install.tool_open_title"), tr("install.tool_open", name=name)) \
                    != QMessageBox.StandardButton.Yes:
                return
            if not self.close_tool_instances(tool_id):
                return
        reqs = entry.manifest.requirements.summary()
        if reqs and not self.manager.get(tool_id):
            if QMessageBox.question(self, tr("install.requirements_title"),
                                    tr("install.requirements", name=name, items="\n- ".join(reqs))) \
                    != QMessageBox.StandardButton.Yes:
                return
        key = "install.updating" if self.manager.get(tool_id) else "install.installing"
        TaskDialog(self, tr(key, name=name),
                   lambda progress: repository.install_from_catalog(entry, self.manager, progress),
                   on_success=lambda _: self._after_install()).exec()

    def _after_install(self) -> None:
        if self.catalog:
            self.tool_updates = repository.available_updates(self.catalog, self.manager)
        self.catalogChanged.emit()
        self._update_status_button()

    def install_from_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("install.choose_zip"), "", tr("install.zip_filter") + " (*.zip)")
        if path:
            TaskDialog(self, tr("install.from_file"),
                       lambda progress: self.manager.install_zip(Path(path), progress),
                       on_success=lambda _: self._after_install()).exec()

    def install_from_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("install.choose_folder"))
        if path:
            TaskDialog(self, tr("install.from_folder"),
                       lambda progress: self.manager.install_dir(Path(path), progress),
                       on_success=lambda _: self._after_install()).exec()

    def uninstall_tool(self, tool_id: str) -> None:
        tool = self.manager.get(tool_id)
        if tool is None:
            return
        name = tool.manifest.display_name
        box = QMessageBox(QMessageBox.Icon.Question, tr("uninstall.title"), tr("uninstall.confirm", name=name),
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        chk = QCheckBox(tr("uninstall.remove_data"))
        box.setCheckBox(chk)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        if not self.close_tool_instances(tool_id):
            return
        remove = chk.isChecked()
        TaskDialog(self, tr("uninstall.running", name=name),
                   lambda progress: self.manager.uninstall(tool_id, remove, progress),
                   on_success=lambda _: self._after_install()).exec()

    def check_tool(self, tool_id: str) -> None:
        tool = self.manager.get(tool_id)
        title = tr("check.title")

        def done(missing):
            if missing:
                QMessageBox.warning(self, title, tr("check.missing", items="\n- ".join(missing)))
            else:
                QMessageBox.information(self, title, tr("check.ok", name=tool.manifest.display_name))

        self.notify(tr("check.running"))
        run_async(lambda: self.manager.check_tool(tool_id), done, lambda err: QMessageBox.warning(self, title, err))

    def repair_tool(self, tool_id: str) -> None:
        tool = self.manager.get(tool_id)
        TaskDialog(self, tr("repair.running", name=tool.manifest.display_name),
                   lambda progress: self.manager.repair(tool_id, progress)).exec()

    # ========================================================== Updates
    def reload_catalog(self, on_done: Callable[[], None] | None = None) -> None:
        self.store_page.set_loading(True)
        repos = list(self.settings.get("repositories", []))

        def loaded(catalog: Catalog):
            self.catalog = catalog
            self.tool_updates = repository.available_updates(catalog, self.manager)
            self.catalogChanged.emit()
            self._update_status_button()
            if on_done:
                on_done()

        run_async(lambda: repository.load_catalog(repos), loaded,
                  lambda err: (self.store_page.set_loading(False), self.notify(tr("store.error", error=err))))

    def check_updates(self, manual: bool) -> None:
        if not manual and not self.settings.get("check_updates_on_start", True):
            return
        self.notify(tr("updates.searching"))

        def tools_done():
            if manual:
                n = len(self.tool_updates)
                self.notify(tr("updates.tools_available", count=n) if n else tr("updates.tools_current"))

        self.reload_catalog(on_done=tools_done)
        repo = self.settings.get("app_update_repo", "")
        if not repo:
            if manual:
                self.notify(tr("updates.no_repo"))
            return
        prerelease = self.settings.get("include_prereleases", False)

        def app_done(release):
            self.app_release = release
            self._update_status_button()
            if manual and release is None:
                QMessageBox.information(self, tr("updates.title"),
                                        tr("updates.app_current", app=APP_NAME, version=__version__))

        run_async(lambda: app_updater.check_for_update(repo, prerelease), app_done,
                  lambda err: manual and QMessageBox.warning(self, tr("updates.title"),
                                                             tr("updates.check_failed", error=err)))

    def _update_status_button(self) -> None:
        parts = []
        if self.app_release:
            parts.append(f"{APP_NAME} {self.app_release.version}")
        if self.tool_updates:
            parts.append(tr("updates.tool_count", count=len(self.tool_updates)))
        self.update_btn.setText("⬆  " + tr("updates.available", items=", ".join(parts)) if parts else "")
        self.update_btn.setStyleSheet(f"color: {theme.current['warning']}; font-weight: 600; border: none;")
        self.update_btn.setVisible(bool(parts))

    def _update_button_clicked(self) -> None:
        if self.app_release:
            self._offer_app_update()
        elif self.tool_updates:
            self.show_store()
            self.store_page.select_updates()

    def _offer_app_update(self) -> None:
        rel = self.app_release
        box = QMessageBox(self)
        box.setWindowTitle(tr("updates.app_title"))
        box.setText(tr("updates.app_available", app=APP_NAME, version=rel.version, installed=__version__))
        box.setDetailedText(rel.notes or tr("updates.no_notes"))
        install = box.addButton(tr("updates.install_now"), QMessageBox.ButtonRole.AcceptRole) if rel.asset_url else None
        web = box.addButton(tr("updates.open_release"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(tr("updates.later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is web:
            QDesktopServices.openUrl(QUrl(rel.html_url))
        elif install is not None and box.clickedButton() is install:
            def task(progress):
                progress(tr("updates.downloading", app=APP_NAME, version=rel.version))
                path = app_updater.download_update(rel)
                progress(tr("updates.restarting"))
                return path

            dlg = TaskDialog(self, tr("updates.app_title"), task)
            dlg.exec()
            if dlg.success and dlg.result_value:
                app_updater.apply_update(dlg.result_value)
                self._force_quit = True
                self.close()

    # ======================================================== Sperren
    def _setup_auto_lock(self) -> None:
        self.lock_timer = QTimer(self)
        self.lock_timer.setSingleShot(True)
        self.lock_timer.timeout.connect(self.lock)
        self._activity = _ActivityFilter(self.lock_timer)
        QApplication.instance().installEventFilter(self._activity)
        self._apply_auto_lock()

    def _apply_auto_lock(self) -> None:
        minutes = int(self.settings.get("auto_lock_minutes", 0) or 0)
        self.lock_timer.setInterval(minutes * 60_000)
        if minutes:
            self.lock_timer.start()
        else:
            self.lock_timer.stop()

    def lock(self) -> None:
        if self._locked:
            return
        self._locked = True
        self.lock_timer.stop()
        self.vault.lock()
        floating = list(self.dm.floatingWidgets())
        for w in floating:
            w.hide()
        self.hide()
        dlg = LoginDialog(self.vault, locked=True)
        if dlg.exec():
            self._locked = False
            self.show()
            for w in floating:
                w.show()
            self._apply_auto_lock()
        else:
            self._locked = False
            self._force_quit = True
            self.close()

    # ======================================================= Einstellungen
    def open_app_settings(self) -> None:
        old_repos = self.settings.get("repositories")
        dlg = AppSettingsDialog(self.settings, self.vault, self)
        if not dlg.exec():
            return
        theme.apply_theme(QApplication.instance(), self.settings.get("theme", "dark"))
        self.dm.setStyleSheet(self._ads_base_style + theme.ads_stylesheet())
        self._apply_auto_lock()
        if dlg.language_changed:
            # Oberfläche in der neuen Sprache neu aufbauen (Layout und offene Tabs bleiben erhalten)
            self.restart_ui()
            return
        self.catalogChanged.emit()
        if self.settings.get("repositories") != old_repos:
            self.reload_catalog()

    def restart_ui(self) -> None:
        self._restarting = True
        if self.close():
            self.restartRequested.emit()
        else:
            self._restarting = False

    # ========================================================= Layout
    def _restore_layout(self) -> None:
        data = read_json(LAYOUT_FILE, default=None)
        if not data:
            return
        try:
            if data.get("geometry"):
                self.restoreGeometry(base64.b64decode(data["geometry"]))
            self.act_sidebar.setChecked(data.get("sidebar", True))
            for t in data.get("tools", []):
                if self.manager.get(t["tool_id"]):
                    self.open_tool(t["tool_id"], dock_name=t["name"], focus=False)
            if data.get("state"):
                self.dm.restoreState(base64.b64decode(data["state"]))
            self.home_dock.toggleView(True)  # Home immer sichtbar
        except Exception:  # noqa: BLE001
            log.exception("Layout konnte nicht wiederhergestellt werden")

    def _save_layout(self) -> None:
        write_json(LAYOUT_FILE, {
            "geometry": base64.b64encode(bytes(self.saveGeometry())).decode(),
            "state": base64.b64encode(bytes(self.dm.saveState())).decode(),
            "sidebar": self.act_sidebar.isChecked(),
            "tools": [{"name": n, "tool_id": o.tool_id} for n, o in self.open_tools.items()],
        })

    def reset_layout(self) -> None:
        for dock in [self.home_dock, self.store_dock] + [o.dock for o in self.open_tools.values()]:
            if dock.isFloating() or dock.dockAreaWidget() is not self.home_area:
                self.dm.addDockWidgetTabToArea(dock, self.home_area)
        self.show_home()

    # ========================================================== Sonstiges
    def _open_path(self, path: Path) -> None:
        if path.exists():
            os.startfile(str(path))  # noqa: S606 - Windows Explorer / Standardprogramm
        else:
            QMessageBox.information(self, APP_NAME, tr("common.not_found", path=path))

    def _about(self) -> None:
        QMessageBox.about(self, tr("about.title", app=APP_NAME),
                          f"<h3>{APP_NAME} {__version__}</h3><p>{tr('about.text')}</p>"
                          f"<p>{tr('about.installed', count=len(self.manager.tools))}</p>"
                          f"<p>© {VENDOR} · <a href='https://github.com/{GITHUB_REPO}'>github.com/{GITHUB_REPO}</a></p>")

    def closeEvent(self, event):  # noqa: N802
        if not self._force_quit:
            for o in self.open_tools.values():
                try:
                    if not o.instance.can_close():
                        event.ignore()
                        return
                except Exception:  # noqa: BLE001
                    log.exception("can_close() fehlgeschlagen")
        if self.settings.get("restore_layout", True) or self._restarting:
            try:
                self._save_layout()
            except Exception:  # noqa: BLE001
                log.exception("Layout konnte nicht gespeichert werden")
        for o in list(self.open_tools.values()):
            self._shutdown_instance(o)
        self.open_tools.clear()
        QApplication.instance().removeEventFilter(self._activity)
        self.lock_timer.stop()
        for w in list(self.dm.floatingWidgets()):
            w.close()
        event.accept()
        if not self._restarting:
            QApplication.instance().quit()

    def sizeHint(self):  # noqa: N802
        return QSize(1400, 860)

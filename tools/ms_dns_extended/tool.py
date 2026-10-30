"""MS DNS Extended Management – Verwaltung von Microsoft-DNS-Servern mit Prüfung, Serververgleich und Aufräum-Vorschau.

Aufbau wie MS DHCP Extended Management (bewusst eigenständig, keine gemeinsamen Module):
* Anmeldeseite (Server, Anmeldedaten) -> Hauptbereich mit eigenem Dock-Manager (QtAds): feste Seiten Übersicht,
  Server, Suche, Vergleich, Prüfung, Ereignisprotokoll; dazu je Zone ein Tab.
* Alle Serverzugriffe laufen über service.DnsService im Hintergrund (runner.Runner); Dialoge und Rückfragen laufen
  zwischen den Schritten im GUI-Thread. Prüfung, Ereignisprotokoll und Auto-Refresh laufen ohne Runner (run_async),
  damit die Oberfläche bedienbar bleibt.
"""

from __future__ import annotations

import datetime
import html
import os
import time
from concurrent.futures import ThreadPoolExecutor

import PySide6QtAds as ads
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QSplitter, QStackedWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from omniwrench.sdk import CredentialField, ToolBase, run_async
from omniwrench.ui import theme
from omniwrench.ui.widgets import make_button

from . import dialogs as dlg
from . import ui_base
from .ai import DnsAI
from . import dnsutil as du
from . import eventlog
from . import favorites as fv
from . import ping as pinger
from .backend import WmiBackend
from .page_zone import ZoneTab
from .pages import CheckPage, ComparePage, EventsPage, OverviewPage, SearchPage, ServerPage
from .runner import Job, Runner
from .service import DnsService, UserError
from .ui_base import FilterState, Markers, bold_label, choose, confirm, error, help_icon, info, short_list, text_dialog, warn

WIKI = "https://github.com/KuroShiroMe/OmniWrench/wiki/Tool-MS-DNS-Extended-Management"
MAX_SERVERS = 12
REFRESH_MINUTES = (0, 1, 2, 5, 10, 15, 30)
PAGES = ("overview", "server", "search", "compare", "check", "events")


class _Bridge(QObject):
    """Log und Fortschritt kommen aus Hintergrund-Threads (ToolBase ist kein QObject)."""
    log = Signal(str, bool)
    progress = Signal(str, int, int)
    scan_progress = Signal(str, int, int)


class MsDnsExtended(ToolBase):
    backend_factory = None     # für Tests/Screenshots: Ersatz für das WMI-Backend

    # --- Aufbau --------------------------------------------------------------------------------------
    def create_widget(self, parent=None) -> QWidget:
        tr = self.tr = self.context.tr
        self.settings = self.context.settings
        self.bridge = _Bridge()
        self.bridge.log.connect(self._append_log)
        self.bridge.progress.connect(self._progress)
        factory = type(self).backend_factory
        self.backend = factory() if factory else WmiBackend()
        self.svc = DnsService(self.backend, tr, lambda t, e=False: self.bridge.log.emit(t, e),
                              lambda t, i=0, n=0: self.bridge.progress.emit(t, i, n))
        self.flt = FilterState(self.settings)
        self.runner = Runner()
        self.runner.busy_changed.connect(self._busy)
        self.runner.status.connect(lambda t: self._progress(t, 0, 0) if t != "busy" else None)
        self.runner.failed.connect(self._failed)
        self.queue: list = []
        self._login_fav: dict | None = None   # Favorit der laufenden Anmeldung (weitere Server, DHCP-Abgleich)
        self.tabs: dict[tuple[str, str], tuple[ZoneTab, ads.CDockWidget]] = {}
        self._markers: dict[int, Markers] = {}
        self.scans: dict[str, dict] = {}
        self.dhcp_leases: list[dict] | None = None
        self._scan_gen = 0
        self._poll_gen = 0
        self._poll_busy = False
        self._ev_since: dict[str, str] = {}
        self._repl_busy: set[tuple[str, str]] = set()
        self._closed = False      # nach shutdown(): späte Rückrufe (Timer, Hintergrund) nichts mehr anfassen lassen

        self.root = QWidget(parent)
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_login())
        self.stack.addWidget(self._build_main())
        self.stack.addWidget(self._build_loading())
        lay.addWidget(self._build_status())
        self.refresh_timer = QTimer(self.root)
        self.refresh_timer.timeout.connect(self._poll_tick)
        self._shortcut = QShortcut(QKeySequence("Ctrl+W"), self.root)
        self._shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._shortcut.activated.connect(self._close_current)
        self.bridge.scan_progress.connect(self.check_page.scan_progress)
        self.ai = DnsAI(self)
        ui_base.set_ask_hook(self.context)
        return self.root

    def _card(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 24, 24, 24)
        card = QFrame()
        card.setObjectName("dnscard")
        card.setMaximumWidth(720)
        card.setStyleSheet(f"QFrame#dnscard {{ border:1px solid {theme.current['border']}; border-radius:8px;"
                           f" background:{theme.current['surface']}; }}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(10)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(card, 10)
        h.addStretch(1)
        outer.addStretch(1)
        outer.addLayout(h)
        outer.addStretch(2)
        return page, cl

    def _build_loading(self) -> QWidget:
        page, cl = self._card()
        self.load_title = bold_label("")
        f = self.load_title.font()
        f.setPointSizeF(f.pointSizeF() * 1.3)
        self.load_title.setFont(f)
        cl.addWidget(self.load_title)
        self.load_bar = QProgressBar()
        self.load_bar.setRange(0, 0)
        self.load_bar.setTextVisible(False)
        self.load_bar.setMaximumHeight(10)
        cl.addWidget(self.load_bar)
        self.load_steps = QLabel("")
        self.load_steps.setTextFormat(Qt.TextFormat.RichText)
        self.load_steps.setWordWrap(True)
        self.load_steps.setStyleSheet(f"color:{theme.current['muted']};")
        cl.addWidget(self.load_steps)
        self._steps: list[str] = []
        return page

    def _step(self, text: str, is_error: bool = False) -> None:
        if self.stack.currentIndex() != 2:
            return
        color = theme.current["danger"] if is_error else theme.current["muted"]
        self._steps.append(f"<span style='color:{color}'>{html.escape(text)}</span>")
        self._steps = self._steps[-8:]
        self.load_steps.setText("<br>".join(self._steps))

    def _build_login(self) -> QWidget:
        tr = self.tr
        page, cl = self._card()
        th = QHBoxLayout()
        title = bold_label(tr("login.title"))
        f = title.font()
        f.setPointSizeF(f.pointSizeF() * 1.4)
        title.setFont(f)
        th.addWidget(title)
        th.addWidget(help_icon(tr("login.intro") + "\n\n" + tr("login.requirements")))
        th.addStretch(1)
        cl.addLayout(th)
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self.favs = fv.FavoriteStore(self.settings, self.context.secrets)
        self.fav_panel = fv.FavoritesPanel(tr, self.favs, self.fav_capture, [
            {"key": "auto_discover", "label": tr("login.auto_discover"), "type": "check", "default": True},
            {"key": "auto_scan", "label": tr("login.auto_scan"), "type": "check", "default": True},
            {"key": "servers", "label": tr("fav.extra_servers"), "type": "list", "placeholder": tr("fav.extra_servers_ph")},
            {"key": "dhcp_server", "label": tr("fav.dhcp_server")}], self.fav_cred_items)
        self.fav_panel.applied.connect(self.fav_apply)
        self.fav_panel.activated.connect(self.fav_activated)
        grid.addWidget(QLabel(tr("login.server")), 0, 0)
        self.server = QComboBox()
        self.server.setEditable(True)
        self.server.addItems(self.settings.get("servers") or [])
        self.server.setEditText(self.settings.get("last_server") or "")
        self.server.lineEdit().setPlaceholderText(tr("login.server_ph"))
        self.server.lineEdit().returnPressed.connect(self._login_clicked)
        self.server.editTextChanged.connect(self.fav_panel.server_edited)
        srow = QHBoxLayout()
        srow.setSpacing(2)
        srow.addWidget(self.server, 1)
        srow.addWidget(self.fav_panel.star_button())
        grid.addLayout(srow, 0, 1)
        grid.addWidget(QLabel(tr("login.auth")), 1, 0, Qt.AlignmentFlag.AlignTop)
        modes = QVBoxLayout()
        self.mode_group = QButtonGroup(page)
        who = os.environ.get("USERDOMAIN", "") + ("\\" if os.environ.get("USERDOMAIN") else "") + os.environ.get("USERNAME", "")
        self.m_sso = QRadioButton(tr("login.mode_sso", user=who or "–"))
        self.m_vault = QRadioButton(tr("login.mode_vault"))
        self.m_manual = QRadioButton(tr("login.mode_manual"))
        for i, b in enumerate((self.m_sso, self.m_vault, self.m_manual)):
            self.mode_group.addButton(b, i)
            modes.addWidget(b)
            if i == 1:
                self.cred_field = CredentialField(settings=self.settings, key="credential")
                modes.addWidget(self.cred_field)
            if i == 2:
                row = QHBoxLayout()
                self.user = QLineEdit(self.settings.get("last_user") or "")
                self.user.setPlaceholderText(tr("login.user_ph"))
                self.password = QLineEdit()
                self.password.setEchoMode(QLineEdit.EchoMode.Password)
                self.password.setPlaceholderText(tr("login.password"))
                self.password.returnPressed.connect(self._login_clicked)
                row.addWidget(self.user)
                row.addWidget(self.password)
                modes.addLayout(row)
        mode = self.settings.get("login_mode") or "sso"
        {"sso": self.m_sso, "vault": self.m_vault, "manual": self.m_manual}.get(mode, self.m_sso).setChecked(True)
        self.mode_group.idToggled.connect(lambda *_: self._mode_changed())
        grid.addLayout(modes, 1, 1)
        self.ai_row = fv.AIAccessRow(self.context)
        if self.ai_row.available:
            from omniwrench.core.i18n import tr as app_tr
            grid.addWidget(QLabel(app_tr("ai.tab_access")), 2, 0)
            grid.addWidget(self.ai_row, 2, 1)
        cl.addLayout(grid)
        self.auto_discover = QCheckBox(tr("login.auto_discover"))
        self.auto_discover.setChecked(bool(self.settings.get("auto_discover", True)))
        self.auto_scan = QCheckBox(tr("login.auto_scan"))
        self.auto_scan.setChecked(bool(self.settings.get("auto_scan", True)))
        for box, tip in ((self.auto_discover, "login.auto_discover_hint"), (self.auto_scan, "login.auto_scan_hint")):
            r = QHBoxLayout()
            r.addWidget(box)
            r.addWidget(help_icon(tr(tip)))
            r.addStretch(1)
            cl.addLayout(r)
        row = QHBoxLayout()
        self.login_btn = make_button(tr("login.connect"), primary=True, on_click=self._login_clicked)
        row.addWidget(self.login_btn)
        self.login_status = QLabel("")
        self.login_status.setWordWrap(True)
        row.addWidget(self.login_status, 1)
        cl.addLayout(row)
        self._mode_changed()
        self.fav_panel.restore()
        outer = QWidget()
        ol = QHBoxLayout(outer)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(0)
        ol.addWidget(self.fav_panel)
        ol.addWidget(page, 1)
        return outer

    def _mode_changed(self) -> None:
        self.cred_field.setEnabled(self.m_vault.isChecked())
        self.user.setEnabled(self.m_manual.isChecked())
        self.password.setEnabled(self.m_manual.isChecked())

    # --- Favoriten -----------------------------------------------------------------------------------
    def fav_capture(self) -> dict:
        """Anmeldemaske als Favorit. Ein eingegebenes Kennwort wird nur im Tresor gespeichert (Anmeldeart "stored")."""
        login: dict = {"mode": "sso"}
        out = {"server": self.server.currentText().strip(), "login": login, "options": {
            "auto_discover": self.auto_discover.isChecked(), "auto_scan": self.auto_scan.isChecked()},
            "ai": self.ai_row.value()}
        if self.m_vault.isChecked():
            login.update(mode="vault", cred=fv.cred_key(self.cred_field.selected_item()))
        elif self.m_manual.isChecked():
            login.update(mode="stored" if self.password.text() else "manual", user=self.user.text().strip())
            if self.password.text():
                out["password"] = self.password.text()
        return out

    def fav_cred_items(self) -> list[dict]:
        return self.cred_field.value()["items"]

    def fav_apply(self, fav: dict | None) -> None:
        if not fav:
            return
        login, opts = fav.get("login") or {}, fav.get("options") or {}
        self.server.setEditText(fav.get("server", ""))
        mode = login.get("mode", "sso")
        {"vault": self.m_vault, "manual": self.m_manual, "stored": self.m_manual}.get(mode, self.m_sso).setChecked(True)
        self.login_status.setText("")
        self.password.clear()
        if mode in ("manual", "stored"):
            self.user.setText(login.get("user", ""))
            pw = self.favs.password(fav["id"]) if mode == "stored" else None
            if pw is not None:
                self.password.setText(pw)
            else:
                if mode == "stored":
                    self.login_status.setText(self.tr("fav.pw_missing"))
                self.password.setFocus()
        elif mode == "vault":
            items = self.cred_field.value()["items"]
            key = login.get("cred") or {}
            idx = fv.match_cred(items, key)
            if idx < 0 and key.get("ref"):          # Eintrag aus dem Passwortmanager: Verweis in die Liste übernehmen
                items.append(dict(key))
                idx = len(items) - 1
                self.settings.set("credential", {"items": items, "selected": idx})
                self.cred_field.set_value({"items": items, "selected": idx})
            if idx >= 0:
                self.cred_field.combo.setCurrentIndex(idx)
            else:
                self.login_status.setText(self.tr("fav.cred_missing"))
        for key, box in (("auto_discover", self.auto_discover), ("auto_scan", self.auto_scan)):
            if key in opts:
                box.setChecked(bool(opts[key]))
        self.ai_row.set_value(fav.get("ai"))

    def fav_activated(self, fav: dict) -> None:
        """Doppelklick in der Favoritenliste: Maske ist gefüllt, direkt anmelden."""
        self._login_clicked()

    def _build_main(self) -> QWidget:
        tr = self.tr
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 6, 8, 0)
        lay.setSpacing(6)
        top = QHBoxLayout()
        self.conn_info = QLabel("")
        self.conn_info.setTextFormat(Qt.TextFormat.RichText)
        top.addWidget(self.conn_info, 1)
        top.addWidget(QLabel(tr("main.auto_refresh")))
        self.refresh_combo = QComboBox()
        for m in REFRESH_MINUTES:
            self.refresh_combo.addItem(tr("main.refresh_off") if not m else tr("main.refresh_min", n=m), m)
        self.refresh_combo.setToolTip(tr("main.auto_refresh_tip"))
        self.refresh_combo.setCurrentIndex(max(0, self.refresh_combo.findData(self._refresh_minutes())))
        self.refresh_combo.currentIndexChanged.connect(
            lambda _i: (self.settings.set("auto_refresh", self.refresh_combo.currentData()), self._apply_refresh_timer()))
        top.addWidget(self.refresh_combo)
        self.logout_btn = make_button(tr("main.logout"), on_click=lambda: self.run(self.logout_flow()))
        top.addWidget(self.logout_btn)
        help_btn = QToolButton()
        help_btn.setText("?")
        help_btn.setToolTip(tr("main.help"))
        help_btn.clicked.connect(lambda: text_dialog(self.root, tr("main.help"), tr("help.text"), tr("ui.close")))
        top.addWidget(help_btn)
        lay.addLayout(top)
        split = QSplitter(Qt.Orientation.Vertical)
        host = QWidget()
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)
        ads.CDockManager.setConfigFlag(ads.CDockManager.eConfigFlag.AllTabsHaveCloseButton, True)
        ads.CDockManager.setConfigFlag(ads.CDockManager.eConfigFlag.AlwaysShowTabs, True)
        self.dm = ads.CDockManager(host)
        hl.addWidget(self.dm)
        self.overview = OverviewPage(self)
        self.server_page = ServerPage(self)
        self.search_page = SearchPage(self)
        self.compare_page = ComparePage(self)
        self.check_page = CheckPage(self)
        self.events_page = EventsPage(self)
        self.fixed_docks: dict[str, ads.CDockWidget] = {}
        self.area = None
        for key, w in zip(PAGES, (self.overview, self.server_page, self.search_page, self.compare_page,
                                  self.check_page, self.events_page)):
            d = ads.CDockWidget(self.dm, tr("page." + key))
            d.setObjectName(f"dns_{key}")
            d.setWidget(w)
            d.setFeature(ads.CDockWidget.DockWidgetFeature.DockWidgetClosable, False)
            if self.area is None:
                self.area = self.dm.addDockWidget(ads.CenterDockWidgetArea, d)
            else:
                self.dm.addDockWidgetTabToArea(d, self.area)
            self.fixed_docks[key] = d
        self.fixed_docks["events"].visibilityChanged.connect(lambda vis: self.events_page.on_shown() if vis else None)
        self.fixed_docks["compare"].visibilityChanged.connect(lambda vis: self.compare_page.refresh() if vis else None)
        self.fixed_docks["overview"].setAsCurrentTab()
        split.addWidget(host)
        logw = QWidget()
        ll = QVBoxLayout(logw)
        ll.setContentsMargins(0, 0, 0, 0)
        lh = QHBoxLayout()
        lh.addWidget(bold_label(tr("main.log")))
        lh.addStretch(1)
        clr = QToolButton()
        clr.setText(tr("main.log_clear"))
        clr.clicked.connect(lambda: self.log_view.clear())
        lh.addWidget(clr)
        ll.addLayout(lh)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        ll.addWidget(self.log_view)
        split.addWidget(logw)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 1)
        split.setSizes([640, 140])
        lay.addWidget(split, 1)
        self.main_area = host
        return page

    def _build_status(self) -> QWidget:
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 3, 8, 3)
        self.status = QLabel(self.tr("status.ready"))
        self.status.setStyleSheet(f"color:{theme.current['muted']};")
        lay.addWidget(self.status, 1)
        self.pbar = QProgressBar()
        self.pbar.setMaximumWidth(220)
        self.pbar.setMaximumHeight(14)
        self.pbar.setTextVisible(False)
        self.pbar.hide()
        lay.addWidget(self.pbar)
        self.cancel_btn = QPushButton(self.tr("ui.cancel"))
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        lay.addWidget(self.cancel_btn)
        return bar

    # --- Ablaufsteuerung ----------------------------------------------------------------------------
    def run(self, gen) -> bool:
        if gen is None:
            return False
        if self.runner.active:
            self.queue.append(gen)
            return True
        return self.runner.start(gen, self._next)

    def job_flow(self, fn, status: str = ""):
        res = yield Job(fn, status)
        return res

    def simple_flow(self, fn, status: str = ""):
        yield Job(fn, status)

    def atomic(self, title: str, flow):
        """Ablauf als Transaktion: Tritt ein Fehler auf, werden alle Änderungen bis dahin zurückgenommen."""
        svc = self.svc
        tx, outer = svc.tx_begin(title)
        try:
            result = yield from flow
        except GeneratorExit:
            svc._tx = outer
            if tx.undo:
                self.queue.insert(0, self._rollback_flow(tx))
            raise
        except Exception as e:  # noqa: BLE001 - jeder Fehler löst die Rücknahme aus
            svc._tx = None
            err = yield Job(lambda exc=e: svc.tx_fail(exc, tx, outer), self.tr("status.rollback"))
            raise err from None
        svc.tx_commit(tx, outer)
        return result

    def _rollback_flow(self, tx):
        fails = yield Job(lambda: self.svc.tx_rollback(tx), self.tr("status.rollback"))
        warn(self.root, self.tr("tx.title"), self.svc.tx_message_cancel(tx, fails))

    def _next(self) -> None:
        if self.queue and not self.runner.active:
            self.runner.start(self.queue.pop(0), self._next)
        elif not self.runner.active:
            self._progress(self.tr("status.ready"), 0, 0)

    def _busy(self, busy: bool, cancellable: bool) -> None:
        if self._closed:
            return
        self.main_area.setEnabled(not busy)
        self.logout_btn.setEnabled(not busy)
        self.login_btn.setEnabled(not busy)
        self.pbar.setVisible(busy)
        if busy:
            self.pbar.setRange(0, 0)
        self.cancel_btn.setVisible(busy and cancellable)
        self.cancel_btn.setEnabled(True)
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        else:
            while QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()

    def _cancel(self) -> None:
        self.svc.cancel.set()
        self.cancel_btn.setEnabled(False)
        self._progress(self.tr("status.cancelling"), 0, 0)

    def _progress(self, text: str, i: int, n: int) -> None:
        if self._closed:
            return
        if text:
            self.status.setText(text)
        if n:
            self.pbar.setRange(0, n)
            self.pbar.setValue(i)

    def _append_log(self, text: str, is_error: bool) -> None:
        if self._closed:
            return
        self._step(text, is_error)
        stamp = time.strftime("%H:%M:%S")
        color = theme.current["danger"] if is_error else theme.current["text"]
        body = html.escape(text).replace("\n", "<br>&nbsp;&nbsp;")
        self.log_view.appendHtml(f"<span style='color:{theme.current['muted']}'>{stamp}</span> "
                                 f"<span style='color:{color}'>{body}</span>")

    def _failed(self, text: str, details: str = "") -> None:
        self._append_log(text, True)
        self.login_status.setText("")
        if self.stack.currentIndex() == 2:
            self.stack.setCurrentIndex(0)
        self.show_error(self.tr("ui.error"), text, details)

    def show_error(self, title: str, text: str, details: str = "", warning: bool = False) -> None:
        """Meldung mit „Detailansicht“ (Kopf: Tool, Version, Zeit, Meldung; darunter die technischen Zeilen)."""
        tr = self.tr
        if details:
            head = [f"{self.context.manifest.display_name} {self.context.manifest.version}",
                    time.strftime("%Y-%m-%d %H:%M:%S"), "", tr("err.details_hint"), "", text, "", "-" * 60]
            details = "\n".join(head) + "\n" + details
        error(self.root, title, text, details, tr("ui.details"), tr("ui.details_title"),
              tr("ui.close"), tr("ui.copy_all"), QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Critical)

    def notify(self, text: str) -> None:
        self.svc.log(text)
        self.context.notify(text)

    # --- Anmeldung -----------------------------------------------------------------------------------
    def _login_clicked(self) -> None:
        if self.runner.active:
            return
        server = self.server.currentText().strip()
        if not server:
            warn(self.root, self.tr("login.title"), self.tr("login.err_server"))
            return
        fav = self.fav_panel.current()
        self._login_fav = fav if fav and fav["server"].lower() == server.lower() else None
        if self.m_vault.isChecked():
            self.login_status.setText(self.tr("login.cred_loading"))
            self.cred_field.resolve_async(lambda cred: self.run(self.login_flow(server, cred, True)))
        elif self.m_manual.isChecked():
            if not self.user.text().strip():
                warn(self.root, self.tr("login.title"), self.tr("login.err_user"))
                return
            self.run(self.login_flow(server, (self.user.text().strip(), self.password.text()), False))
        else:
            self.run(self.login_flow(server, None, False))

    def remember_server(self, server: str) -> None:
        lst = [s for s in (self.settings.get("servers") or []) if s.lower() != server.lower()]
        lst.insert(0, server)
        self.settings.set("servers", lst[:15])

    def login_flow(self, server: str, cred, from_vault: bool):
        tr, svc = self.tr, self.svc
        if from_vault and not cred:
            self.login_status.setText(tr("login.no_cred"))
            return
        user, pw = cred if cred else ("", "")
        mode = "vault" if from_vault else "manual" if cred else "sso"
        self.settings.set("login_mode", mode)
        if mode == "manual":
            self.settings.set("last_user", user)
        self.settings.set("auto_discover", self.auto_discover.isChecked())
        self.settings.set("auto_scan", self.auto_scan.isChecked())
        self.login_status.setText("")
        self.load_title.setText(tr("login.connecting", server=server))
        self._steps = []
        self.load_steps.setText("")
        self.stack.setCurrentIndex(2)
        hello = yield Job(svc.hello, tr("status.starting"))
        if not hello.get("wmi"):
            raise UserError(svc.host_text(hello.get("error") or "@ERR:no_pywin32:"))
        svc.reset()
        yield Job(lambda: svc.connect(server, user, pw), tr("status.connecting", server=server))
        self.password.clear()
        self.remember_server(server)
        self.settings.set("last_server", server)
        yield Job(svc.load_all, tr("status.loading_server", server=server))
        if self.auto_discover.isChecked():
            yield from self.discover_connect_flow(silent=True)
        if self._login_fav:
            yield from self.fav_login_flow(self._login_fav)
        self.login_status.setText("")
        self.scans = {}
        self.refresh_pages()
        self.stack.setCurrentIndex(1)
        self.fixed_docks["overview"].setAsCurrentTab()
        now = eventlog.iso_utc(datetime.datetime.now() - datetime.timedelta(minutes=2))
        self._ev_since = {s: now for s in svc.servers}
        self._apply_refresh_timer()
        self.ai_row.apply()
        if self.auto_scan.isChecked():
            self.start_scan()

    def discover_connect_flow(self, silent: bool):
        """Weitere DNS-Server (DCs der Domäne) mit denselben Anmeldedaten verbinden."""
        tr, svc = self.tr, self.svc
        found = yield Job(svc.discover_servers, tr("status.discover"))
        found = found[: max(0, MAX_SERVERS - len(svc.servers))]
        if not found:
            if not silent:
                info(self.root, tr("cmp.discover"), tr("cmp.discover_none"))
            return
        if not silent and not confirm(self.root, tr("cmp.discover"), tr("cmp.discover_q", list=short_list(found))):
            return
        ok = yield from self.connect_servers_flow(found, tr("status.discover_connect", n=len(found)))
        if ok:
            svc.log(tr("log.discover_ok", n=len(ok), list=", ".join(ok)))
        self.refresh_pages()

    def fav_login_flow(self, fav: dict):
        """Nach der Anmeldung über einen Favoriten: weitere Server verbinden, DHCP-Server für den Abgleich setzen."""
        tr, svc = self.tr, self.svc
        opts = fav.get("options") or {}
        more = []
        for s in opts.get("servers") or []:
            n = du.norm(str(s))
            if n and n not in svc.servers and n not in more:
                more.append(n)
        more = more[: max(0, MAX_SERVERS - len(svc.servers))]
        if more:
            ok = yield from self.connect_servers_flow(more, tr("status.fav_connect", n=len(more)))
            if ok:
                svc.log(tr("log.fav_connected", n=len(ok), list=", ".join(ok)))
        dhcp = du.norm(str(opts.get("dhcp_server") or ""))
        if dhcp:
            svc.dhcp_server = dhcp
            svc.dhcp_user, svc.dhcp_secret = svc.user, svc.secrets.get(svc.primary, "")
            svc.log(tr("log.fav_dhcp", server=dhcp))

    def connect_servers_flow(self, servers: list[str], status: str):
        """Server parallel mit der Anmeldung des ersten Servers verbinden; Fehler nur ins Protokoll. Liefert die verbundenen."""
        tr, svc = self.tr, self.svc
        user, pw = svc.user, svc.secrets.get(svc.primary, "")

        def work():
            ok, bad = [], []

            def one(s):
                try:
                    svc.add_server(s, user, pw)
                    return s, None
                except UserError as e:
                    return s, str(e)
            with ThreadPoolExecutor(max_workers=6, thread_name_prefix="dnsconn") as ex:
                for s, err in ex.map(one, servers):
                    (bad if err else ok).append((s, err))
            return ok, bad
        ok, bad = yield Job(work, status)
        for s, err in bad:
            svc.log(tr("log.discover_failed", server=s, error=err))
        return [s for s, _e in ok]

    def discover_flow(self):
        yield from self.discover_connect_flow(silent=False)

    def logout_flow(self):
        tr = self.tr
        open_tabs = len(self.tabs)
        if open_tabs and not confirm(self.root, tr("main.logout"), tr("main.logout_q", n=open_tabs)):
            return
        self.refresh_timer.stop()
        self._scan_gen += 1
        self.svc.scan_cancel.set()
        for key in list(self.tabs):
            self._close_tab(key)
        yield Job(self.svc.logout, tr("status.logout"))
        self.ai_row.clear()
        self.scans = {}
        self.dhcp_leases = None
        self.stack.setCurrentIndex(0)

    def add_server_flow(self):
        tr, svc = self.tr, self.svc
        sugg = yield Job(svc.discover_servers, tr("status.discover"))
        v = dlg.add_server_dialog(self.root, tr, sugg, svc.user)
        if not v:
            return
        server = du.norm(v["server"])
        if server in svc.servers:
            info(self.root, tr("srv.add_title"), tr("srv.add_exists", server=server))
            return
        if v["mode"] == "other":
            user, pw = v["user"], v["password"]
        else:
            user, pw = svc.user, svc.secrets.get(svc.primary, "")
        yield Job(lambda: svc.add_server(server, user, pw), tr("status.connecting", server=server))
        self._ev_since[server] = eventlog.iso_utc(datetime.datetime.now() - datetime.timedelta(minutes=2))
        self.refresh_pages()

    def remove_server(self, server: str) -> None:
        tr = self.tr
        if server == self.svc.primary:
            return
        if not confirm(self.root, tr("ov.remove_server"), tr("srv.remove_q", server=server)):
            return
        for key in [k for k in self.tabs if k[0] == server]:
            self._close_tab(key)
        self.svc.remove_server(server)
        self.scans.pop(server, None)
        self.refresh_pages()

    # --- Seiten --------------------------------------------------------------------------------------
    def refresh_pages(self) -> None:
        svc = self.svc
        names = list(svc.servers)
        more = f" (+{len(names) - 1})" if len(names) > 1 else ""
        self.conn_info.setText(self.tr("main.connected", server=html.escape(svc.primary) + more,
                                       user=html.escape(svc.user or self.tr("login.current"))))
        for p in (self.overview, self.server_page, self.search_page, self.events_page):
            p.refresh()
        self.compare_page.refresh()
        self.check_page.refresh_dhcp()
        for (s, z), (tab, dock) in list(self.tabs.items()):
            if z not in svc.zones.get(s, {}):
                continue
            tab.set_data()

    def show_page(self, name: str) -> None:
        d = self.fixed_docks.get(name)
        if d is not None:
            d.setAsCurrentTab()

    def wiki_url(self, anchor: str = "") -> str:
        return WIKI + (f"#{anchor.lower()}" if anchor else "")

    def markers_for(self, tab) -> Markers:
        m = self._markers.get(id(tab))
        if m is None:
            m = Markers(self.tr, self.flt, lambda key, t=tab: t.marker_clicked(key))
            self._markers[id(tab)] = m
        return m

    def scan_result(self, server: str) -> dict | None:
        return self.scans.get(server)

    def dhcp_by_ip(self) -> dict[str, dict] | None:
        if self.dhcp_leases is None:
            return None
        return {x["ip"]: x for x in self.dhcp_leases if x.get("state") == 1 or x.get("kind") == "reservation"}

    # --- Zonen-Tabs ----------------------------------------------------------------------------------
    def open_zone(self, server: str, zone: str, select_key: str | None = None, show_findings: bool = False) -> None:
        key = (server, zone)
        if key in self.tabs:
            tab, dock = self.tabs[key]
            dock.setAsCurrentTab()
            if select_key:
                tab.select_key(select_key)
            elif show_findings:
                tab.show_findings()
            return
        self.run(self._open_zone_flow(server, zone, select_key, show_findings))

    def _open_zone_flow(self, server, zone, select_key, show_findings):
        tr, svc = self.tr, self.svc
        if svc.records(server, zone) is None:
            recs = yield Job(lambda: svc.load_zone(server, zone), tr("status.loading_zone", zone=zone))
        else:
            recs = svc.records(server, zone)
        rel = svc.related_zones(server, zone, recs)
        if rel:
            yield Job(lambda: svc.load_many(server, rel), tr("status.loading_related", n=len(rel)))
        tab = ZoneTab(self, server, zone)
        title = zone if server == svc.primary else f"{zone} @ {server.split('.')[0]}"
        dock = ads.CDockWidget(self.dm, title)
        dock.setObjectName(f"dnszone_{server}_{zone}")
        dock.setWidget(tab)
        dock.setFeature(ads.CDockWidget.DockWidgetFeature.DockWidgetDeleteOnClose, True)
        dock.closeRequested.connect(lambda k=(server, zone): self._forget_tab(k))
        self.dm.addDockWidgetTabToArea(dock, self.area)
        self.tabs[(server, zone)] = (tab, dock)
        tab.set_data()
        dock.setAsCurrentTab()
        if select_key:
            tab.select_key(select_key)
        elif show_findings:
            tab.show_findings()

    def _forget_tab(self, key) -> None:
        tab_dock = self.tabs.pop(key, None)
        if tab_dock:
            self._markers.pop(id(tab_dock[0]), None)

    def _close_tab(self, key) -> None:
        tab_dock = self.tabs.pop(key, None)
        if tab_dock:
            self._markers.pop(id(tab_dock[0]), None)
            tab_dock[1].closeDockWidget()

    def _close_current(self) -> None:
        for key, (tab, dock) in list(self.tabs.items()):
            if dock.isCurrentTab() and dock.isVisible():
                self._close_tab(key)
                return

    def zone_changed(self, server: str, zone: str) -> None:
        t = self.tabs.get((server, zone))
        if t:
            t[0].set_data()
        self.overview.refresh()

    def reload_zone_flow(self, server: str, zone: str):
        tr, svc = self.tr, self.svc
        before = list(svc.records(server, zone) or [])
        yield Job(lambda: (svc.load_zones(server), svc.load_zone(server, zone)), tr("status.loading_zone", zone=zone))
        diff = svc.diff_zone(before, svc.records(server, zone) or [])
        if diff and before:
            svc.log(tr("log.reload_diff", zone=zone, n=len(diff)) + "\n" + "\n".join(diff[:20]))
        self.zone_changed(server, zone)

    def reload_server_flow(self, server: str):
        tr, svc = self.tr, self.svc
        open_zones = [z for (s, z) in self.tabs if s == server]

        def work():
            svc.refresh_info(server)
            svc.load_zones(server)
            for (s, z) in [k for k in svc.cache if k[0] == server]:
                if z not in svc.zones.get(server, {}):
                    svc.cache.pop((s, z), None)
            for z in open_zones:
                if z in svc.zones.get(server, {}):
                    svc.load_zone(server, z)
        yield Job(work, tr("status.loading_server", server=server))
        for z in open_zones:
            if z not in svc.zones.get(server, {}):
                self._close_tab((server, z))
                svc.log(tr("log.zone_gone", zone=z, server=server), True)
        self.refresh_pages()

    def load_all_zones_flow(self, server: str, then=None):
        tr, svc = self.tr, self.svc
        todo = [n for n, z in svc.zones.get(server, {}).items() if (server, n) not in svc.cache
                and z["type"] in (du.ZONE_PRIMARY, du.ZONE_SECONDARY)]
        if todo:
            res = yield Job(lambda: svc.load_many(server, todo), tr("status.loading_related", n=len(todo)))
            bad = [z for z, r in res.items() if isinstance(r, UserError)]
            if bad:
                svc.log(tr("log.zones_failed", list=", ".join(bad)), True)
        self.overview.refresh()
        if then:
            then()

    # --- Schreiben mit Konfliktprüfung -------------------------------------------------------------
    def write_flow(self, server: str, zone: str, touched: list[du.Rec], new: list[du.Rec], title: str, fn,
                   extra_zones=()):
        """Vor dem Schreiben prüfen, ob andere die betroffenen Zonen geändert haben; dann als Transaktion
        schreiben. fn läuft im Hintergrund und nutzt die svc-Methoden (die ihre Rücknahme selbst ablegen)."""
        tr, svc = self.tr, self.svc
        zones = [zone] + [z for z in extra_zones if z != zone]
        loaded = {z: (svc.cache.get((server, z)) or {}).get("loaded") for z in zones}

        def guard():
            out = []
            for z in zones:
                out += svc.guard(server, z, [r for r in touched if r.zone == z], [r for r in new if r.zone == z])
            return out
        lines = yield Job(guard, tr("status.checking"))
        if lines:
            since = min((t for t in loaded.values() if t), default=du.now_utc() - datetime.timedelta(hours=1))
            who = yield Job(lambda: svc.who_changed(server, zone, since), tr("status.checking"))
            text = tr("conflict.text", list=short_list(lines, 10))
            if who:
                text += "\n\n" + tr("conflict.who", list=short_list(who, 6))
            for z in zones:
                self.zone_changed(server, z)
            choice = choose(self.root, tr("conflict.title"), text,
                            [("reload", tr("conflict.reload")), ("anyway", tr("conflict.anyway")),
                             ("cancel", tr("ui.cancel"))], default="reload")
            if choice != "anyway":
                return
        try:
            yield from self.atomic(title, self.job_flow(fn, tr("status.saving")))
        except GeneratorExit:
            # Abbruch: atomic stellt die Rücknahme an den Anfang der Warteschlange, danach neu laden
            self.queue.append(self._after_write_flow(server, zones, False))
            raise
        except Exception:
            yield from self._after_write_flow(server, zones, False)
            raise
        yield from self._after_write_flow(server, zones, True)
        for z in zones:
            own = {r.key for r in svc.records(server, z) or []}
            present = {r.key for r in new if r.zone == z and r.key in own}
            absent = {r.key for r in touched if r.zone == z and r.key not in own}
            if present or absent:
                self.repl_watch(server, z, present, absent)

    def _after_write_flow(self, server: str, zones: list[str], ok: bool):
        """Erfolg: eigene Änderung ist im Zwischenspeicher, nur die neue Seriennummer merken.
        Fehler/Abbruch: die Rücknahme hat am Server zurückgeschrieben -> Zonen neu laden."""
        svc = self.svc

        def work():
            for z in zones:
                c = svc.cache.get((server, z))
                if c is not None:
                    try:
                        if ok:
                            c["serial"] = svc.zone_serial(server, z)
                        else:
                            svc.load_zone(server, z)
                    except UserError:
                        pass
        yield Job(work, self.tr("status.saving") if ok else self.tr("status.loading"))
        for z in zones:
            self.zone_changed(server, z)
        self.search_page.run() if self.search_page.grid.rows else None

    def delete_records_flow(self, server: str, recs: list[du.Rec], after=None):
        tr, svc = self.tr, self.svc
        if not confirm(self.root, tr("zt.delete"), tr("del.records_q", n=len(recs), list=short_list(
                [f"{r.zone}: {r.node} {r.type} {r.value}" for r in recs], 12))):
            return
        zones = sorted({r.zone for r in recs})

        def write():
            for r in recs:
                svc.delete_record(server, r)
        yield from self.write_flow(server, zones[0], recs, [], tr("tx.delete", n=len(recs)), write, extra_zones=zones[1:])
        if after:
            after()

    def zone_action_flow(self, server: str, zone: str, action: str):
        tr, svc = self.tr, self.svc
        yield Job(lambda: svc.zone_action(server, zone, action), tr(f"zact.{action}"))
        yield from self.reload_zone_flow(server, zone)

    # --- Replikation ---------------------------------------------------------------------------------
    REPL_DELAYS = (15, 45, 90, 180, 300)   # Sekunden nach einer eigenen Änderung bis zur nächsten Nachprüfung

    def repl_check(self, server: str, zone: str, then=None) -> bool:
        """Replikationsstand im Hintergrund prüfen (ohne Runner, blockiert die Oberfläche nicht).
        False = läuft schon / nichts zu prüfen (then wird dann nicht aufgerufen)."""
        svc = self.svc
        key = (server, zone)
        if self._closed or key in self._repl_busy or server not in svc.servers:
            return False
        if not svc.repl_peers(server, zone) and not svc._unconnected_secondaries(server, zone):
            svc.repl.pop(key, None)
            t = self.tabs.get(key)
            if t:
                t[0].set_repl(None)
            return False
        self._repl_busy.add(key)
        t = self.tabs.get(key)
        if t:
            t[0].repl_busy(True)

        def done(st):
            self._repl_busy.discard(key)
            if self._closed:
                return
            t = self.tabs.get(key)
            if t:
                t[0].set_repl(st)
            for p in st["peers"]:
                pt = self.tabs.get((p, zone))
                if pt:
                    pt[0].set_data()
            if then:
                then(st)

        def failed(text):
            self._repl_busy.discard(key)
            if self._closed:
                return
            t = self.tabs.get(key)
            if t:
                t[0].repl_busy(False)
            svc.log(text.splitlines()[0] if text else "?", True)
        run_async(lambda: svc.repl_status(server, zone), done, failed)
        return True

    def repl_watch(self, server: str, zone: str, present: set[str], absent: set[str]) -> None:
        """Nach einer eigenen Änderung nachprüfen, bis sie auf allen verbundenen Partnern angekommen ist
        (Ergebnis ins Protokoll)."""
        svc, tr = self.svc, self.tr
        if not svc.repl_peers(server, zone):
            return
        t0 = time.monotonic()
        state = {"i": 0}

        def tick():
            if self._closed or server not in svc.servers:
                return
            if self.runner.active or QApplication.activeModalWidget() is not None \
                    or not self.repl_check(server, zone, then=check):
                QTimer.singleShot(5000, self.root, tick)

        def check(st):
            pend = svc.repl_pending(st, present, absent)
            sec = int(time.monotonic() - t0)
            if not pend:
                svc.log(tr("log.repl_arrived", zone=zone, n=len(st["peers"]), sec=sec))
                return
            state["i"] += 1
            if state["i"] < len(self.REPL_DELAYS):
                QTimer.singleShot((self.REPL_DELAYS[state["i"]] - self.REPL_DELAYS[state["i"] - 1]) * 1000, self.root, tick)
            else:
                svc.log(tr("log.repl_pending", zone=zone, list=", ".join(pend), min=max(1, sec // 60)), True)
        QTimer.singleShot(self.REPL_DELAYS[0] * 1000, self.root, tick)

    def replicate_flow(self, server: str, zone: str):
        tr, svc = self.tr, self.svc
        res = yield Job(lambda: svc.replicate(server, zone), tr("status.replicating", zone=zone))
        text = "\n".join("• " + x for x in res["done"])
        if res["warnings"]:
            self.show_error(tr("repl.title"), text + "\n\n" + "\n\n".join(res["warnings"]),
                            "\n".join(res["details"]), warning=True)
        else:
            info(self.root, tr("repl.title"), text + "\n\n" + tr("repl.recheck_hint"))
        self.repl_check(server, zone)
        # Übertragung/UpdateFromDS laufen im DNS-Dienst nach; später noch einmal nachsehen
        QTimer.singleShot(15000, self.root, lambda: self.repl_check(server, zone))

    def new_zone_flow(self, server: str):
        tr, svc = self.tr, self.svc
        info_ = svc.servers.get(server, {})
        v = dlg.ZoneDialog.ask(self.root, tr, bool(info_.get("ds")))
        if not v:
            return
        if v["name"] in svc.zones.get(server, {}):
            warn(self.root, tr("zone.new_title"), tr("zone.exists", zone=v["name"]))
            return

        def write():
            svc.create_zone(server, v["name"], v["type"], v["ds"], v["file"], v["masters"], v["admin"])
            if v.get("updates") is not None and v["name"] in svc.zones.get(server, {}):
                svc.set_zone(server, v["name"], {"allow_update": v["updates"]})
        yield from self.atomic(tr("tx.zone_create", zone=v["name"]), self.job_flow(write, tr("status.saving")))
        self.refresh_pages()
        self.open_zone(server, v["name"])

    def delete_zone_flow(self, server: str, zone: str):
        tr, svc = self.tr, self.svc
        z = svc.zones.get(server, {}).get(zone, {})
        text = tr("zone.delete_q", zone=zone, server=server)
        if z.get("ds"):
            text += "\n\n" + tr("zone.delete_ad")
        if not dlg.delete_word_dialog(self.root, tr("ov.delete_zone"), text, tr("del.word")):
            return
        yield Job(lambda: svc.delete_zone(server, zone), tr("status.saving"))
        self._close_tab((server, zone))
        self.refresh_pages()

    # --- DHCP-Abgleich -------------------------------------------------------------------------------
    def dhcp_setup_flow(self):
        tr, svc = self.tr, self.svc
        v = dlg.dhcp_dialog(self.root, tr, svc.dhcp_server or self.settings.get("dhcp_server") or "", svc.user)
        if not v:
            return
        svc.dhcp_server = du.norm(v["server"])
        if v["mode"] == "other":
            svc.dhcp_user, svc.dhcp_secret = v["user"], v["password"]
        else:
            svc.dhcp_user, svc.dhcp_secret = svc.user, svc.secrets.get(svc.primary, "")
        self.settings.set("dhcp_server", svc.dhcp_server)
        res = yield Job(lambda: svc.dhcp_compare(svc.primary), tr("status.dhcp", server=svc.dhcp_server))
        self.dhcp_leases = res["leases"]
        self.check_page.refresh_dhcp()
        for tab, _d in self.tabs.values():
            tab.fill_scavenge()
        info(self.root, tr("dhcp.title"), tr("dhcp.loaded", n=len(res["leases"]), f=len(res["findings"])))

    # --- Prüfung (im Hintergrund) -------------------------------------------------------------------
    def start_scan(self) -> None:
        tr, svc = self.tr, self.svc
        server = self.overview.current_server() or svc.primary
        if not server:
            return
        self._scan_gen += 1
        gen = self._scan_gen
        probe = self.check_page.probe.isChecked()
        dhcp = self.check_page.with_dhcp.isChecked() and bool(svc.dhcp_server)
        t0 = time.monotonic()
        self.check_page.scan_started()

        def work():
            res = svc.scan(server, probe, dhcp=dhcp,
                           progress=lambda t, i=0, n=0: self.bridge.scan_progress.emit(t, i, n))
            if dhcp:
                try:
                    res["leases"] = svc.dhcp_compare(server)["leases"]
                except UserError:
                    pass
            return res

        def done(res):
            if gen != self._scan_gen:
                return
            res["time"] = time.strftime("%H:%M")
            res["seconds"] = int(time.monotonic() - t0)
            self.scans[server] = res
            if res.get("leases") is not None:
                self.dhcp_leases = res["leases"]
            self.check_page.scan_stopped()
            self.check_page.set_scan(res)
            self.overview.refresh()
            for (s, z), (tab, _d) in self.tabs.items():
                if s == server:
                    tab.recheck()
            svc.log(tr("log.scan_done", server=server, n=len(res["findings"]), sec=res["seconds"]))

        def failed(text):
            if gen != self._scan_gen:
                return
            self.check_page.scan_stopped(tr("chk.failed") + " " + (text.splitlines()[0] if text else ""))
            svc.log(text, True)
        run_async(work, done, failed)

    def ping_many(self, ips: list[str], cb) -> None:
        self._progress(self.tr("sc.pinging", n=len(ips)), 0, 0)
        run_async(lambda: pinger.ping_many(ips),
                  lambda res: None if self._closed else (cb(res), self._progress(self.tr("status.ready"), 0, 0)),
                  lambda text: self.svc.log(text, True))

    # --- Änderungen anderer (Auto-Refresh) ----------------------------------------------------------
    def _refresh_minutes(self) -> int:
        try:
            return int(self.settings.get("auto_refresh", 5))
        except (TypeError, ValueError):
            return 5

    def _apply_refresh_timer(self) -> None:
        m = self._refresh_minutes()
        if m and self.stack.currentIndex() == 1:
            self.refresh_timer.start(m * 60 * 1000)
        else:
            self.refresh_timer.stop()

    def _poll_tick(self) -> None:
        """Zonenliste und offene Zonen prüfen (Seriennummer); geänderte neu laden, "wer" aus dem Protokoll."""
        if self._poll_busy or self.runner.active or QApplication.activeModalWidget() is not None:
            return
        svc = self.svc
        open_zones = list(self.tabs)
        servers = list(svc.servers)
        since = dict(self._ev_since)
        self._poll_busy = True
        self._poll_gen += 1
        gen = self._poll_gen

        def work():
            changed, events = [], {}
            for s in servers:
                try:
                    svc.load_zones(s)
                except UserError:
                    continue
            for s, z in open_zones:
                try:
                    if svc.zone_changed(s, z):
                        before = list(svc.records(s, z) or [])
                        svc.load_zone(s, z)
                        changed.append((s, z, svc.diff_zone(before, svc.records(s, z) or [])))
                except UserError:
                    continue
            if changed:
                for s in {c[0] for c in changed}:
                    events[s] = svc.change_events(s, since.get(s) or eventlog.iso_utc(
                        datetime.datetime.now() - datetime.timedelta(minutes=10)), None, 100)
            return changed, events

        def done(res):
            self._poll_busy = False
            if gen != self._poll_gen:
                return
            changed, events = res
            now = eventlog.iso_utc(datetime.datetime.now())
            for s in servers:
                self._ev_since[s] = now
            for s, z, diff in changed:
                who = sorted({e.get("user") for e in events.get(s, []) if e.get("zone") in (z, "") and e.get("user")})
                svc.log(self.tr("log.changed_by_others", zone=z, n=len(diff), who=", ".join(who) or "?")
                        + ("\n" + "\n".join(diff[:10]) if diff else ""))
            self.refresh_pages()

        def failed(_text):
            self._poll_busy = False
        run_async(work, done, failed)

    # --- Lebenszyklus --------------------------------------------------------------------------------
    def can_close(self) -> bool:
        return not self.runner.active

    def shutdown(self) -> None:
        self._closed = True
        ai_row = getattr(self, "ai_row", None)
        if ai_row is not None:
            ai_row.clear()
        self.refresh_timer.stop()
        self._scan_gen += 1
        self._poll_gen += 1
        self.svc.scan_cancel.set()
        try:
            self.backend.close()
        except Exception:  # noqa: BLE001 - beim Schließen nur aufräumen
            pass

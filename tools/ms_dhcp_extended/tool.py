"""MS DHCP Extended Management – Verwaltung von Microsoft-DHCP-Servern (IPv4 und IPv6) mit Prüfung, Failover und Replikation.

Aufbau:
* Anmeldeseite (Server, Anmeldedaten, Partner) -> Hauptbereich mit eigenem Dock-Manager (QtAds):
  feste Seiten Übersicht, Server-Optionen, Failover, Definitionen, Prüfung; dazu je Scope ein Tab
  und Entwürfe für neue Scopes.
* Umschalter IPv4/IPv6 oben: Übersicht, Server-Optionen und Definitionen zeigen die gewählte Familie,
  DHCPv6-Scopes öffnen als page_scope6.ScopeTab6; Failover nur IPv4, Prüfung und Ereignisprotokoll beide.
* Alle Serverzugriffe laufen über service.DhcpService im Hintergrund (runner.Runner); Dialoge und
  Rückfragen laufen zwischen den Schritten im GUI-Thread.
"""

from __future__ import annotations

import datetime
import html
import json
import os
import time

import PySide6QtAds as ads
from PySide6.QtCore import QMimeData, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QSplitter, QStackedWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from omniwrench.sdk import CredentialField, ToolBase
from omniwrench.ui import theme
from omniwrench.ui.widgets import make_button

from . import checks as ck
from . import dialogs as dlg
from . import eventlog
from . import ip6calc as ip6
from .page_draft import DraftTab
from .page_events import EventsPage
from .page_scope import ScopeTab
from .page_scope6 import ScopeTab6
from .pages import CheckPage, DefsPage, FailoverPage, OverviewPage, ServerOptionsPage
from .backend import ApiBackend
from .runner import Job, Runner
from .scanner import Scanner
from .service import DhcpService, ReplicationError, UserError
from .ui_base import FilterState, bold_label, confirm, error, help_icon, info, level_icon, short_list, text_dialog, warn

MIME = "application/x-omniwrench-ms-dhcp-extended+json"
MAX_SERVERS = 15
REFRESH_MINUTES = (0, 1, 2, 5, 10, 15, 30)


class _Bridge(QObject):
    """Log und Fortschritt kommen aus Hintergrund-Threads (ToolBase ist kein QObject)."""
    log = Signal(str, bool)
    progress = Signal(str, int, int)


class MsDhcpExtended(ToolBase):
    backend_factory = None     # für Tests/Screenshots: Ersatz für das DHCP-API-Backend

    # --- Aufbau --------------------------------------------------------------------------------------
    def create_widget(self, parent=None) -> QWidget:
        tr = self.tr = self.context.tr
        self.settings = self.context.settings
        self.bridge = _Bridge()
        self.bridge.log.connect(self._append_log)
        self.bridge.progress.connect(self._progress)
        self.backend = self._new_backend()
        self.svc = DhcpService(self.backend, tr, lambda t, e=False: self.bridge.log.emit(t, e),
                               lambda t, i=0, n=0: self.bridge.progress.emit(t, i, n))
        self.flt = FilterState(self.settings)
        self.runner = Runner()
        self.runner.busy_changed.connect(self._busy)
        self.runner.status.connect(lambda t: self._progress(t, 0, 0) if t != "busy" else None)
        self.runner.failed.connect(self._failed)
        self.scanner = Scanner(self._new_backend, lambda: self.svc, lambda t, e=False: self.bridge.log.emit(t, e))
        self.queue: list = []
        self.tabs: dict[QWidget, ads.CDockWidget] = {}
        self.scan: dict | None = None
        self._classes: dict[bool, tuple[list[str], list[str]]] = {}     # v6? -> (Hersteller-, Benutzerklassen)
        self.family = 6 if self.settings.get("family") == 6 else 4
        self._dock_seq = 0
        self._ev_since = ""             # Ereignisprotokoll: bis hierhin gelesen (UTC)
        self._ev_seen: set[int] = set()  # schon gemeldete Ereignisse (EventRecordID)
        self._poll_error = ""

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
        cp = self.check_page
        self.scanner.running_changed.connect(lambda on: None if on else cp.scan_stopped())
        self.scanner.progress.connect(cp.scan_progress)
        self.scanner.scope_done.connect(cp.scope_done)
        self.scanner.finished.connect(self._scan_finished)
        self.scanner.failed.connect(self._scan_failed)
        return self.root

    def _new_backend(self):
        factory = type(self).backend_factory
        return factory() if factory else ApiBackend()

    def _card(self) -> tuple[QWidget, QVBoxLayout, QFrame]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 24, 24, 24)
        card = QFrame()
        card.setObjectName("skcard")
        card.setMaximumWidth(720)
        card.setStyleSheet(f"QFrame#skcard {{ border:1px solid {theme.current['border']}; border-radius:8px;"
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
        return page, cl, card

    def _build_loading(self) -> QWidget:
        """Während der Anmeldung nur Fortschritt; bei einem Fehler geht es zurück zur Anmeldemaske."""
        page, cl, _card = self._card()
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
        page, cl, card = self._card()
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
        grid.addWidget(QLabel(tr("login.server")), 0, 0)
        self.server = QComboBox()
        self.server.setEditable(True)
        self.server.addItems(self.settings.get("servers") or [])
        self.server.setEditText(self.settings.get("last_server") or "")
        self.server.lineEdit().setPlaceholderText(tr("login.server_ph"))
        self.server.lineEdit().returnPressed.connect(self._login_clicked)
        grid.addWidget(self.server, 0, 1)
        self.ad_btn = make_button(tr("login.from_ad"), on_click=lambda: self.run(self.ad_flow()))
        grid.addWidget(self.ad_btn, 0, 2)
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
        grid.addLayout(modes, 1, 1, 1, 2)
        cl.addLayout(grid)
        self.auto_partner = QCheckBox(tr("login.auto_partner"))
        self.auto_partner.setChecked(bool(self.settings.get("auto_partner", True)))
        self.auto_scan = QCheckBox(tr("login.auto_scan"))
        self.auto_scan.setChecked(bool(self.settings.get("auto_scan", True)))
        for box, tip in ((self.auto_partner, "login.auto_partner_hint"), (self.auto_scan, "login.auto_scan_hint")):
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
        return page

    def _mode_changed(self) -> None:
        self.cred_field.setEnabled(self.m_vault.isChecked())
        self.user.setEnabled(self.m_manual.isChecked())
        self.password.setEnabled(self.m_manual.isChecked())

    def _build_main(self) -> QWidget:
        tr = self.tr
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 6, 8, 0)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(self._build_family_switch())
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
        self.auto_repl = QCheckBox(tr("main.auto_replicate"))
        self.auto_repl.setToolTip(tr("main.auto_replicate_tip"))
        self.auto_repl.setChecked(bool(self.settings.get("auto_replicate", True)))
        self.auto_repl.toggled.connect(lambda on: self.settings.set("auto_replicate", on))
        top.addWidget(self.auto_repl)
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
        self.overview.action.connect(self._ov_action)
        self.srv_opts = ServerOptionsPage(self)
        self.fo_page = FailoverPage(self)
        self.defs_page = DefsPage(self)
        self.check_page = CheckPage(self)
        self.events_page = EventsPage(self)
        self.fixed_docks = []
        self.area = None
        for key, w in (("overview", self.overview), ("server_options", self.srv_opts), ("failover", self.fo_page),
                       ("defs", self.defs_page), ("check", self.check_page), ("events", self.events_page)):
            d = ads.CDockWidget(self.dm, tr("page." + key))
            d.setObjectName(f"sk_{key}")
            d.setWidget(w)
            d.setFeature(ads.CDockWidget.DockWidgetFeature.DockWidgetClosable, False)
            if self.area is None:
                self.area = self.dm.addDockWidget(ads.CenterDockWidgetArea, d)
            else:
                self.dm.addDockWidgetTabToArea(d, self.area)
            self.fixed_docks.append(d)
        self.fixed_docks[5].visibilityChanged.connect(lambda vis: self.events_page.on_shown() if vis else None)
        self.fixed_docks[0].setAsCurrentTab()
        self.apply_expert_mode()
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

    def _build_family_switch(self) -> QWidget:
        """IPv4 | IPv6 als Segmentschaltfläche: bestimmt Übersicht, Server-Optionen und Definitionen."""
        c = theme.current
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(0)
        self.family_group = QButtonGroup(w)
        for i, fam in enumerate((4, 6)):
            b = QPushButton(f"IPv{fam}")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(self.tr("main.family_tip"))
            rad = "border-top-left-radius:5px; border-bottom-left-radius:5px;" if i == 0 else \
                "border-top-right-radius:5px; border-bottom-right-radius:5px; border-left:none;"
            b.setStyleSheet(f"QPushButton {{ padding:3px 14px; border:1px solid {c['border']}; border-radius:0; {rad}"
                            f" background:{c['surface']}; color:{c['text']}; font-weight:600; }}"
                            f" QPushButton:checked {{ background:{c['accent']}; border-color:{c['accent']}; color:white; }}")
            self.family_group.addButton(b, fam)
            lay.addWidget(b)
        self.family_group.button(self.family).setChecked(True)
        self.family_group.idClicked.connect(self.set_family)
        return w

    def set_family(self, fam: int) -> None:
        if fam not in (4, 6) or fam == self.family:
            return
        self.family = fam
        self.settings.set("family", fam)
        self.family_group.button(fam).setChecked(True)
        self.overview.set_data(self.svc, self.scan)
        self.srv_opts.current = None
        self.srv_opts.refresh()
        self.defs_page.refresh()
        self.defs_page.apply_rights()
        self.update_conn_info()

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

    def atomic(self, title: str, flow):
        """Führt einen Ablauf (Generator mit Jobs) als Transaktion aus: Tritt ein Fehler auf, werden alle
        Änderungen, die der Ablauf bis dahin am Server und am Partner gemacht hat, zurückgenommen."""
        svc = self.svc
        tx, outer = svc.tx_begin(title)
        try:
            result = yield from flow
        except GeneratorExit:
            svc._tx = outer
            if tx.undo:     # abgebrochen: Rücknahme als eigener Ablauf nachholen
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
        self.main_area.setEnabled(not busy)
        self.logout_btn.setEnabled(not busy)
        self.login_btn.setEnabled(not busy)
        self.ad_btn.setEnabled(not busy)
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
        if text:
            self.status.setText(text)
        if n:
            self.pbar.setRange(0, n)
            self.pbar.setValue(i)

    def _append_log(self, text: str, is_error: bool) -> None:
        self._step(text, is_error)
        stamp = time.strftime("%H:%M:%S")
        color = theme.current["danger"] if is_error else theme.current["text"]
        body = html.escape(text).replace("\n", "<br>&nbsp;&nbsp;")
        self.log_view.appendHtml(f"<span style='color:{theme.current['muted']}'>{stamp}</span> "
                                 f"<span style='color:{color}'>{body}</span>")

    def _failed(self, text: str) -> None:
        self._append_log(text, True)
        self.login_status.setText("")
        if self.stack.currentIndex() == 2:      # Anmeldung fehlgeschlagen -> zurück zur Anmeldemaske
            self.stack.setCurrentIndex(0)
        error(self.root, self.tr("ui.error"), text)

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
        self.settings.set("auto_partner", self.auto_partner.isChecked())
        self.settings.set("auto_scan", self.auto_scan.isChecked())
        self.login_status.setText("")
        self.load_title.setText(tr("login.connecting", server=server))
        self._steps = []
        self.load_steps.setText("")
        self.stack.setCurrentIndex(2)
        hello = yield Job(svc.hello, tr("status.starting_host"))
        if not (hello or {}).get("dhcp"):
            raise UserError(tr("err.no_module"))
        yield Job(lambda: svc.connect(server, user, pw), tr("status.connecting", server=server))
        self.password.clear()
        self.remember_server(server)
        self.settings.set("last_server", server)
        yield Job(svc.load_all, tr("status.loading_server", server=server))
        svc.partner_mode = "Lazy"
        if self.auto_partner.isChecked():
            svc.partner_mode = "Auto"
            yield from self.partner_login_flow()
            # Sicht der direkt erreichbaren Partner gleich mitladen (schnell); netsh-Partner erst bei Bedarf
            yield from self.load_peer_flow([pn for pn in svc.partners() if svc.partner_via.get(pn) == "Cim"], refresh=False)
        self.login_status.setText("")
        self._classes = {}
        self.scan = None
        self.check_page.scan = None
        self.refresh_pages()
        self.stack.setCurrentIndex(1)
        self.fixed_docks[0].setAsCurrentTab()
        self._ev_since = eventlog.iso_utc(datetime.datetime.now() - datetime.timedelta(minutes=2))
        self._ev_seen = set()
        self._poll_error = ""
        self._apply_refresh_timer()
        if self.auto_scan.isChecked():
            self.start_scan()

    def partner_login_flow(self):
        tr, svc = self.tr, self.svc
        for pn in svc.partners():
            user, pw = None, ""
            while True:
                try:
                    yield Job(lambda: svc.connect_partner(pn, user, pw), tr("status.partner", partner=pn))
                    break
                except UserError as e:
                    choice = dlg.partner_login_dialog(self.root, tr, pn, str(e))
                    if choice == "retry":
                        continue
                    if choice == "other":
                        c = dlg.credentials_dialog(self.root, tr, pn, svc.partner_user.get(pn, svc.user))
                        if c:
                            user, pw = c
                            continue
                        break
                    if choice == "primary":
                        svc.partner_mode = "Off"
                        svc.log(tr("log.primary_only"), True)
                        return
                    break

    def ad_flow(self):
        tr = self.tr
        items = yield Job(self.svc.dhcp_in_dc, tr("status.ad"))
        if not items:
            info(self.root, tr("login.from_ad"), tr("login.ad_none"))
            return
        cur = self.server.currentText()
        names = sorted({i["name"] for i in items if i.get("name")}, key=str.lower)
        self.server.clear()
        self.server.addItems(names)
        self.server.setEditText(cur or names[0])
        self.server.showPopup()
        self.svc.log(tr("log.ad_found", n=len(names)))

    def logout_flow(self):
        tr = self.tr
        dirty = [w for w in self.tabs if isinstance(w, ScopeTab) and w.is_dirty()]
        if dirty and not confirm(self.root, tr("main.logout"), tr("main.confirm_logout", list=short_list([w.sid for w in dirty])) ):
            return
        self.refresh_timer.stop()
        for w in list(self.tabs):
            self.close_tab(w, force=True)
        self.scanner.reset()
        yield Job(self.svc.disconnect, tr("status.disconnecting"))
        self.defs_page.lock()
        self.srv_opts.current = None
        self.events_page.reset()
        self.stack.setCurrentIndex(0)

    def remember_server(self, server: str) -> None:
        lst = [s for s in (self.settings.get("servers") or []) if s.lower() != server.lower()]
        lst.insert(0, server)
        self.settings.set("servers", lst[:MAX_SERVERS])
        cur = self.server.currentText()
        self.server.clear()
        self.server.addItems(lst[:MAX_SERVERS])
        self.server.setEditText(cur)

    def known_servers(self) -> list[str]:
        out = []
        for s in list(self.settings.get("servers") or []) + self.svc.partners():
            if s and s.lower() not in (x.lower() for x in out):
                out.append(s)
        return out

    # --- Hauptbereich -------------------------------------------------------------------------------
    def refresh_pages(self) -> None:
        self.overview.set_data(self.svc, self.scan)
        self.fo_page.refresh()
        self.defs_page.refresh()
        self.srv_opts.refresh()
        self.events_page.refresh()
        self.apply_expert_mode()
        self.apply_rights()

    def apply_rights(self) -> None:
        """Oberfläche an die Rechte anpassen: ohne Schreibrecht nur Ansicht (Schaltflächen ausgeblendet)."""
        svc = self.svc
        self.overview.apply_rights(svc.can_write(None))
        self.fo_page.apply_rights()
        self.srv_opts.apply_rights()
        self.defs_page.apply_rights()
        for w in self.tabs:
            if isinstance(w, ScopeTab):
                w.apply_rights()
        self.auto_repl.setVisible(svc.can_write(None) and bool(svc.partners()))
        self.update_conn_info()

    def apply_expert_mode(self) -> None:
        """Die Seite Definitionen gibt es nur im Expertenmodus (Einstellungen)."""
        on = bool(self.settings.get("expert_mode", False))
        d = self.fixed_docks[3]
        if d.isClosed() == on:
            d.toggleView(on)
        if not on:
            self.defs_page.lock()

    def load_peer_flow(self, partners: list[str], refresh: bool = True):
        """Sicht der Partner laden (Failover-Beziehungen, Scopes, Server-Optionen)."""
        for pn in partners:
            if self.svc.partner_mode == "Off":
                break
            yield Job(lambda pn=pn: self.svc.load_peer(pn), self.tr("status.peer", partner=pn))
        if refresh:
            self.fo_page.refresh()
            self.srv_opts.refresh()
            self.apply_rights()

    def update_conn_info(self) -> None:
        tr, svc = self.tr, self.svc
        parts = [f"<b>{html.escape(svc.server or '')}</b>", html.escape(svc.user or tr("ui.sso")),
                 html.escape(tr("conn.protocol", proto=svc.protocol or "–"))]
        if not svc.can_write(None):
            parts.append(f"<b>{html.escape(tr('conn.read_only_long'))}</b>")
        warn_state = svc.partner_mode == "Off" or bool(svc.partner_fail) or bool(svc.netsh_fail) or not svc.can_write(None)
        for pn in svc.partners():
            parts.append(html.escape(f"{tr('conn.partner')} {pn}: {svc.partner_state(pn)}"))
        if svc.partner_mode == "Off":
            parts.append(html.escape(tr("conn.primary_only")))
        if self.family == 6 and svc.v6_error:
            parts.append(html.escape(tr("conn.v6_error")))
            warn_state = True
        color = theme.current["warning"] if warn_state else theme.current["text"]
        self.conn_info.setText(f"<span style='color:{color}'>" + " · ".join(parts) + "</span>")

    def checker(self) -> ck.Checker:
        return self.svc.checker()

    # --- Prüfung im Hintergrund ----------------------------------------------------------------------
    def start_scan(self) -> None:
        cp = self.check_page
        if self.scanner.running or not self.svc.server:
            return
        cp.scan_started()
        if not self.scanner.start(cp.with_leases.isChecked(), cp.with_partner.isChecked(), cp.with_dns.isChecked()):
            cp.scan_stopped()

    def _scan_finished(self, scan: dict) -> None:
        self.set_scan(scan)
        key = "log.scan_cancelled" if scan.get("partial") else "log.scan_done"
        self.svc.log(self.tr(key, n=len(scan["scopes"]), sec=scan["seconds"]))

    def _scan_failed(self, text: str) -> None:
        self.check_page.scan_failed(text)
        self.svc.log(self.tr("log.scan_failed", error=text), True)

    def set_scan(self, scan: dict) -> None:
        self.scan = scan
        if not scan.get("partial") and "partner_diffs" in scan:
            self.svc.partner_diffs = dict(scan["partner_diffs"])
            for w in list(self.tabs):
                if isinstance(w, ScopeTab):
                    w.recheck()
        self.check_page.set_scan(scan)
        self.overview.set_data(self.svc, scan)
        self.fo_page.refresh()
        self.update_conn_info()

    def reload_all_flow(self):
        yield Job(self.svc.load_all, self.tr("status.loading_server", server=self.svc.server))
        self._classes = {}
        self.refresh_pages()

    def refresh_overview_rows(self):
        yield Job(self.svc.load_overview, self.tr("status.loading"))
        self.overview.set_data(self.svc, self.scan)
        self.fo_page.refresh()
        self.update_conn_info()

    def _ov_action(self, a: str) -> None:
        g = self.overview.grid
        ids = [r["id"] for r in g.selected_rows()]
        if a in ("New", "Duplicate", "Activate", "Deactivate", "Remove") and not self.svc.can_write(None):
            return
        if a == "Refresh":
            self.run(self.reload_all_flow())
        elif a == "New":
            self.open_draft(None, v6=self.family == 6)
        elif a == "Edit":
            for sid in ids[:10]:
                self.open_scope(sid)
        elif a == "Duplicate" and ids:
            self.open_draft(ids[0])
        elif a in ("Activate", "Deactivate") and ids:
            self.run(self.state_flow(ids, a == "Activate"))
        elif a == "Remove" and ids:
            self.run(self.remove_scopes_flow(ids))

    def state_flow(self, ids: list[str], active: bool):
        tr, svc = self.tr, self.svc
        state = "Active" if active else "InActive"
        ids = [i for i in ids if (svc.scope_row(i) or {}).get("state") != state]
        if not ids:
            return
        if not confirm(self.root, tr("ov.activate" if active else "ov.deactivate"),
                       tr("ov.confirm_state", state=tr("state." + state), list=short_list(ids))):
            return

        def write():    # alle oder keiner
            for sid in ids:
                setter = svc.scope6_set if ip6.is_v6_scope(sid) else svc.scope_set
                yield Job(lambda sid=sid, setter=setter: setter(sid, State=state), tr("status.saving"))
        yield from self.atomic(tr("tx.scope_state", state=tr("state." + state)), write())
        for sid in ids:
            svc.log(tr("log.scope_state", id=sid, state=tr("state." + state)))
            tab = self.scope_tab(sid)
            yield from self.after_change(sid, tab)
            if tab is not None:
                yield from tab.load_flow(leases=False)
        yield from self.refresh_overview_rows()

    def remove_scopes_flow(self, ids: list[str]):
        tr, svc = self.tr, self.svc
        fo = [i for i in ids if i in svc.scope_fo]
        text = tr("ov.confirm_remove", list=short_list(ids))
        if fo:
            text += "\n\n" + tr("ov.confirm_remove_fo", list=short_list(fo))
        word = tr("ov.delete_word")
        if not dlg.confirm_typed(self.root, tr, tr("ov.remove"), text, word):
            return
        errs = []
        for sid in ids:
            rel = svc.scope_fo.get(sid)

            def write(sid=sid, rel=rel):
                # je Scope eine Transaktion: scheitert das Löschen, kommt er zurück in die Beziehung und zum Partner
                if rel:
                    yield Job(lambda: svc.remove_fo_scopes(rel, [sid]), tr("status.fo_remove", id=sid))
                if ip6.is_v6_scope(sid):
                    yield Job(lambda: svc.scope6_remove(sid), tr("status.removing", id=sid))
                else:
                    yield Job(lambda: svc.scope_remove(sid), tr("status.removing", id=sid))
            try:
                yield from self.atomic(tr("tx.scope_remove", id=sid), write())
                svc.log(tr("log.scope_removed", id=sid))
                tab = self.scope_tab(sid)
                if tab is not None:
                    self.close_tab(tab, force=True)
            except UserError as e:
                errs.append(f"{sid}: {e}")
        if errs:
            warn(self.root, tr("ov.remove"), short_list(errs, 12))
        yield Job(svc.load_failovers, tr("status.loading"))
        yield from self.refresh_overview_rows()

    # --- Tabs ----------------------------------------------------------------------------------------
    def scope_tab(self, sid: str) -> ScopeTab | None:
        return next((w for w in self.tabs if isinstance(w, ScopeTab) and w.sid == sid), None)

    def _add_dock(self, w: QWidget, title: str) -> ads.CDockWidget:
        self._dock_seq += 1
        d = ads.CDockWidget(self.dm, title)
        d.setObjectName(f"sk_tab_{self._dock_seq}")
        d.setWidget(w)
        d.setFeature(ads.CDockWidget.DockWidgetFeature.DockWidgetDeleteOnClose, True)
        d.setFeature(ads.CDockWidget.DockWidgetFeature.CustomCloseHandling, True)
        d.closeRequested.connect(lambda w=w: self.close_tab(w))
        self.dm.addDockWidgetTabToArea(d, self.area)
        self.tabs[w] = d
        w.dock = d
        d.setAsCurrentTab()
        d.raise_()
        return d

    def open_scope(self, sid: str, show_findings: bool = False) -> None:
        tab = self.scope_tab(sid)
        if tab is None:
            tab = ScopeTab6(self, sid) if ip6.is_v6_scope(sid) else ScopeTab(self, sid)
            self._add_dock(tab, sid)
            self.run(tab.load_flow(leases=True))
        else:
            self.tabs[tab].setAsCurrentTab()
            self.tabs[tab].raise_()
        if show_findings:
            tab.select_page("Findings")

    def open_draft(self, source: str | None, v6: bool = False) -> None:
        if v6 or ip6.is_v6_scope(source):
            self.run(self.new_scope6_flow(source))
            return
        d = DraftTab(self, source)
        self._add_dock(d, self.tr("draft.tab_dup", id=source) if source else self.tr("draft.tab_new"))
        self.run(d.init_flow())

    def new_scope6_flow(self, source: str | None):
        """Neuer DHCPv6-Scope bzw. Kopie: ein Dialog statt Entwurf (kein Pool, kein Failover). Optionen und
        Ausschlüsse der Quelle werden auf den neuen Präfix umgerechnet; alles oder nichts."""
        tr, svc = self.tr, self.svc
        src = svc.scope_row(source) if source else None
        data = None
        if src:
            data = yield Job(lambda: svc.get_scope(source, False), tr("status.loading_scope", id=source))
        res = dlg.scope6_dialog(self.root, tr, {s["id"] for s in svc.scopes6}, (data or {}).get("scope"))
        if not res:
            return
        pfx = res["prefix"]

        def work():
            sid = svc.scope6_add(pfx, res["name"], res["desc"], res["pref"], res["lease_pref"], res["lease_valid"], False)
            if data and res.get("copy_exclusions"):
                for x in data["exclusions"]:
                    svc.excl6_add(sid, *ip6.convert_values([x["start"], x["end"]], source, sid))
            if data and res.get("copy_options"):
                for o in data["options"]:
                    svc.opt_set(sid, int(o["id"]), ip6.convert_values(o["values"], source, sid), o.get("vendor") or "",
                                o.get("user") or "")
            if res["active"]:
                svc.scope6_set(sid, State="Active")
        yield Job(lambda: svc.atomic(tr("tx.scope6_add", id=pfx), work), tr("status.saving"))
        svc.log(tr("log.scope6_created", id=pfx, name=res["name"]))
        yield from self.refresh_overview_rows()
        self.open_scope(pfx)

    def close_tab(self, w: QWidget, force: bool = False) -> None:
        d = self.tabs.get(w)
        if d is None:
            return
        if not force and not w.can_close():
            return
        self.tabs.pop(w, None)
        try:
            self.ctl_disconnect(w)
        except Exception:  # noqa: BLE001
            pass
        d.closeDockWidget()

    def ctl_disconnect(self, w: QWidget) -> None:
        for name in ("_refresh_marks",):
            fn = getattr(w, name, None)
            if fn:
                try:
                    self.flt.changed.disconnect(fn)
                except (RuntimeError, TypeError):
                    pass

    def _close_current(self) -> None:
        for w, d in list(self.tabs.items()):
            if d.isCurrentTab() and (d.isAncestorOf(QApplication.focusWidget()) if QApplication.focusWidget() else True):
                self.close_tab(w)
                return

    def update_tab(self, w: QWidget, lvl: str | None) -> None:
        d = self.tabs.get(w)
        if d is None:
            return
        d.setIcon(level_icon(lvl) if lvl else level_icon(None))
        if isinstance(w, ScopeTab):
            title = (ip6.fmt_net(w.sid, w.plen) if isinstance(w, ScopeTab6) else w.sid) + (" *" if w.is_dirty() else "") \
                + (" ⟳" if w.unreplicated else "")
            d.setWindowTitle(title)

    # --- Gemeinsame Abläufe --------------------------------------------------------------------------
    def after_change(self, sid: str, tab=None):
        """Nach einer Änderung: bei Failover sofort replizieren (Auto-Replikation) oder als offen markieren."""
        tr, svc = self.tr, self.svc
        rel = svc.scope_fo.get(sid)
        if not rel:
            return
        if self.auto_repl.isChecked() and svc.partner_mode != "Off":
            try:
                yield Job(lambda: svc.replicate([sid]), tr("status.replicating", id=sid, partner=rel["partner"]))
                if tab is not None:
                    tab.set_unreplicated(False)
            except UserError as e:
                if tab is not None:
                    tab.set_unreplicated(True)
                warn(self.root, tr("scope.replicate"), str(e))
            self.update_conn_info()
        else:
            svc.log(tr("log.repl_pending", id=sid, partner=rel["partner"]))
            if tab is not None:
                tab.set_unreplicated(True)

    # --- Änderungen anderer: Auto-Refresh ---------------------------------------------------------------
    def _refresh_minutes(self) -> int:
        try:
            m = int(self.settings.get("auto_refresh", 5))
        except (TypeError, ValueError):
            m = 5
        return m if m in REFRESH_MINUTES else 5

    def _apply_refresh_timer(self) -> None:
        self.refresh_timer.stop()
        m = self._refresh_minutes()
        if m and self.svc.server and self.stack.currentIndex() == 1:
            self.refresh_timer.start(m * 60_000)

    def _poll_tick(self) -> None:
        # nur, wenn gerade nichts läuft und kein Dialog offen ist - sonst beim nächsten Mal
        if self.stack.currentIndex() != 1 or self.runner.active or self.queue or QApplication.activeModalWidget():
            return
        self.run(self.poll_flow())

    def poll_flow(self):
        """Hintergrundprüfung (Oberfläche bleibt bedienbar): neue Änderungen laut Ereignisprotokoll melden, offene
        Scopes, Übersicht, Failover, Server-Optionen und Definitionen neu laden, wenn sich etwas geändert hat."""
        tr, svc = self.tr, self.svc
        try:
            since = self._ev_since
            stamp = eventlog.iso_utc(datetime.datetime.now() - datetime.timedelta(minutes=2))
            events = yield Job(lambda: svc.change_events(since), quiet=True)
            self._ev_since = stamp
            new = [ev for ev in events if ev.get("record") not in self._ev_seen]
            self.events_page.add_events(new)
            for ev in reversed(new):
                self._ev_seen.add(ev.get("record"))
                svc.log(tr("log.changed_by", time=(ev.get("time") or "")[:16], user=ev.get("user") or "?",
                           text=ev.get("text") or f"#{ev.get('id')}"))
            for tab in [w for w in list(self.tabs) if isinstance(w, ScopeTab) and w.data]:
                try:
                    fresh = yield Job(lambda sid=tab.sid: svc.get_scope(sid, False), quiet=True)
                except UserError as e:
                    if tab in self.tabs:
                        tab._show_banner(tr("conf.banner_error", error=str(e)), False)
                    continue
                if tab in self.tabs:
                    diffs = tab.apply_remote(fresh, new)
                    if diffs:
                        svc.log(tr("log.remote_changed", id=tab.sid, list="; ".join(diffs[:6])), tab.is_dirty())
            sig = self._server_sig()
            yield Job(svc.load_overview, quiet=True)
            yield Job(svc.load_failovers, quiet=True)
            yield Job(svc.load_server_options, quiet=True)
            yield Job(svc.load_defs, quiet=True)
            self.overview.set_data(svc, self.scan)
            if self._server_sig() != sig:
                self.fo_page.refresh()
                self.srv_opts.refresh()
                self.defs_page.refresh()
                for w in self.tabs:
                    if isinstance(w, ScopeTab) and w.data:
                        w._fill_failover()
            self.update_conn_info()
            self._poll_error = ""
        except UserError as e:     # z. B. Server kurz nicht erreichbar: nur einmal melden, nächste Runde versucht es neu
            if str(e) != self._poll_error:
                self._poll_error = str(e)
                svc.log(tr("log.poll_failed", error=str(e)), True)

    def _server_sig(self) -> str:
        svc = self.svc
        return json.dumps([svc.failovers, svc.server_option_rows, sorted(map(str, svc.defs.items())), svc.server_option_rows6,
                           sorted(map(str, svc.defs6.items()))], sort_keys=True, default=str)

    def _mark_replicated(self, ok: list[str], failed: list[str]) -> None:
        for sid in ok:
            t = self.scope_tab(sid)
            if t is not None:
                t.set_unreplicated(False)
        for sid in failed:
            t = self.scope_tab(sid)
            if t is not None:
                t.set_unreplicated(True)

    def replicate_ids_flow(self, ids: list[str]):
        tr, svc = self.tr, self.svc
        if not confirm(self.root, tr("fo.replicate"), tr("fo.confirm_replicate_ids", list=short_list(ids))):
            return
        try:
            ok = yield Job(lambda: svc.replicate(ids), tr("status.replicating_n", n=len(ids)))
            self._mark_replicated(ok, [])
            self.notify(tr("log.repl_ok_n", n=len(ok)))
        except ReplicationError as e:
            self._mark_replicated(e.ok, [i for i in ids if i not in e.ok])
            warn(self.root, tr("fo.replicate"), str(e))
        self.update_conn_info()

    def replicate_rel_flow(self, rel: dict):
        tr, svc = self.tr, self.svc
        if not confirm(self.root, tr("fo.replicate"), tr("fo.confirm_replicate", name=rel["name"], partner=rel["partner"],
                                                         n=len(rel["scopes"]))):
            return
        try:
            ok = yield Job(lambda: svc.replicate_relationship(rel["name"]), tr("status.replicating_rel", name=rel["name"]))
            self._mark_replicated(ok, [])
            self.notify(tr("log.repl_ok_n", n=len(ok)))
        except ReplicationError as e:
            self._mark_replicated(e.ok, [i for i in rel["scopes"] if i not in e.ok])
            warn(self.root, tr("fo.replicate"), str(e))
        self.update_conn_info()

    def load_classes(self, v6: bool = False):
        if v6 not in self._classes:
            try:
                cls = yield Job(lambda: self.svc.classes(v6=v6), self.tr("status.loading"))
            except UserError:
                cls = []
            vendors = sorted(c["name"] for c in cls if c["type"].lower() == "vendor")
            users = sorted(c["name"] for c in cls if c["type"].lower() == "user")
            self._classes[v6] = (vendors, users)
        return self._classes[v6]

    def new_definition_flow(self, preset: dict):
        tr, svc = self.tr, self.svc
        preset = dict(preset or {})
        v6 = bool(preset.pop("v6", False))
        vendors, _users = yield from self.load_classes(v6)
        with_partner = bool(svc.partners()) and svc.partner_mode != "Off" and not v6
        d = dlg.definition_dialog(self.root, tr, None, vendors, with_partner, preset or None, v6=v6)
        if not d:
            return False
        if svc.opt_def(d["id"], d["vendor"], v6):
            warn(self.root, tr("def.new"), tr("def.err_exists", tag=f"{d['id']:03d}"))
            return False

        def work():
            # Definition lokal und beim Partner - scheitert der Partner, wird auch die lokale wieder entfernt
            svc.def_add(d, v6=v6)
            for pn in (svc.partners() if d.get("partner") else []):
                try:
                    svc.copy_def_to_partner(d, pn)
                except UserError as e:
                    raise UserError(tr("err.def_partner", tag=f"{d['id']:03d}", partner=pn, error=str(e))) from None
        try:
            yield Job(lambda: svc.atomic(tr("tx.def_add", tag=f"{d['id']:03d}"), work), tr("status.saving"))
        finally:
            yield Job(svc.load_defs, tr("status.loading"))
        svc.log(tr("log.def_created", tag=f"{d['id']:03d}", name=d["name"]))
        self.defs_page.refresh()
        return True

    # --- Zwischenablage ------------------------------------------------------------------------------
    def clip_set(self, kind: str, items: list[dict], sid: str, mask: str, text: str) -> None:
        fam = 6 if ip6.is_v6_scope(sid) or (not sid and self.family == 6) else 4
        payload = {"App": "OmniWrench.MsDhcpExtended", "Kind": kind, "Server": self.svc.server, "SourceScopeId": sid,
                   "SourceMask": mask, "Family": fam, "Items": items}
        md = QMimeData()
        md.setData(MIME, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        md.setText(text)
        QApplication.clipboard().setMimeData(md)
        self._progress(self.tr("clip.copied", n=len(items), kind=self.tr("clip.kind." + kind)), 0, 0)

    def clip_get(self) -> dict | None:
        md = QApplication.clipboard().mimeData()
        if md is None or not md.hasFormat(MIME):
            return None
        try:
            data = json.loads(bytes(md.data(MIME)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) and data.get("App") == "OmniWrench.MsDhcpExtended" else None

    # --- Lebenszyklus ------------------------------------------------------------------------------
    def on_settings_changed(self, changed_keys: set[str]) -> None:
        if "credential" in changed_keys:
            self.cred_field.set_value(self.settings.get("credential"))
        if "auto_replicate" in changed_keys:
            self.auto_repl.setChecked(bool(self.settings.get("auto_replicate", True)))
        if "auto_partner" in changed_keys:
            self.auto_partner.setChecked(bool(self.settings.get("auto_partner", True)))
        if "auto_scan" in changed_keys:
            self.auto_scan.setChecked(bool(self.settings.get("auto_scan", True)))
        if "expert_mode" in changed_keys:
            self.apply_expert_mode()
        if "auto_refresh" in changed_keys:
            self.refresh_combo.blockSignals(True)
            self.refresh_combo.setCurrentIndex(max(0, self.refresh_combo.findData(self._refresh_minutes())))
            self.refresh_combo.blockSignals(False)
            self._apply_refresh_timer()

    def can_close(self) -> bool:
        dirty = [w for w in getattr(self, "tabs", {}) if isinstance(w, ScopeTab) and w.is_dirty()]
        if dirty:
            return confirm(self.root, self.tr("ui.close"), self.tr("main.confirm_logout", list=short_list([w.sid for w in dirty])))
        return True

    def shutdown(self) -> None:
        scanner = getattr(self, "scanner", None)
        if scanner is not None:
            scanner.reset()
        runner = getattr(self, "runner", None)
        if runner is not None:
            runner.abort()
        backend = getattr(self, "backend", None)
        if backend is not None and hasattr(backend, "close"):
            backend.close()

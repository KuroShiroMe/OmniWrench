"""NetProbe – umfassendes Netzwerk-Testtool.

Oben eine Eingabe (IP, DNS-Name, Netz oder Bereich), darunter die Zielliste mit Fortschritt.
Ein Klick auf ein Ziel öffnet innerhalb des Tools einen frei anordenbaren Tab (QtAds) mit den
Ergebnissen je Kategorie. Es werden nur die Kategorien angezeigt, zu denen Tests gelaufen sind.
"""

from __future__ import annotations

import PySide6QtAds as ads
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QProgressBar, QPushButton, QSplitter, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.sdk import ToolBase, run_async
from omniwrench.ui.widgets import library_icon, make_button

from .engine import DONE, ERROR, NO_ANSWER, RUNNING, STOPPED, Engine, TargetResult
from .localnet import VendorDB
from .options_dialog import OptionsDialog
from .portinfo import library_ports
from .render import LEVEL_COLOR, Renderer
from . import findings as fx
from .targets import TargetError, parse

STATUS_COLOR = {RUNNING: "#3b82f6", DONE: "#10b981", NO_ANSWER: "#6b7280", ERROR: "#ef4444", STOPPED: "#f59e0b"}


class _Bridge(QObject):
    """Signale für den Übergang vom Engine-Thread in den GUI-Thread (ToolBase ist kein QObject)."""
    updated = Signal(object)
    finished = Signal()


class NetProbe(ToolBase):
    def create_widget(self, parent=None) -> QWidget:
        tr = self.context.tr
        self.renderer = Renderer(tr, self.context.language)
        self._bridge = _Bridge()
        self.engine: Engine | None = None
        self.result_docks: dict[str, ads.CDockWidget] = {}
        self.row_for: dict[str, int] = {}
        self._dock_seq = 0

        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        # Eingabezeile
        top = QHBoxLayout()
        self.input = QLineEdit(self.context.settings.get("last_target", ""))
        self.input.setPlaceholderText(tr("ui.placeholder"))
        self.input.setFont(QFont("Consolas", 11))
        self.input.returnPressed.connect(self._start)
        self.start_btn = make_button(tr("ui.start"), primary=True, on_click=self._start)
        self.start_btn.setIcon(library_icon("play", 16, "#ffffff"))
        self.stop_btn = make_button(tr("ui.stop"), danger=True, on_click=self._stop)
        self.stop_btn.setEnabled(False)
        self.options_btn = make_button(tr("ui.options"), on_click=self._options)
        self.options_btn.setIcon(library_icon("sliders-horizontal", 16))
        top.addWidget(QLabel(tr("ui.target")))
        top.addWidget(self.input, 1)
        top.addWidget(self.options_btn)
        top.addWidget(self.start_btn)
        top.addWidget(self.stop_btn)
        outer.addLayout(top)

        self.error = QLabel()
        self.error.setStyleSheet("color:#ef4444")
        self.error.setWordWrap(True)
        self.error.hide()
        outer.addWidget(self.error)

        # Links die Zielliste, rechts der Ergebnisbereich (eigenes Docking im Tool)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.list = QTreeWidget()
        self.list.setColumnCount(3)
        self.list.setHeaderLabels([tr("list.target"), tr("list.status"), tr("list.progress")])
        self.list.setRootIsDecorated(False)
        self.list.setAlternatingRowColors(True)
        self.list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.list.itemActivated.connect(self._open_result)
        self.list.itemClicked.connect(self._open_result)
        lv.addWidget(self.list, 1)
        self.summary = QLabel("")
        self.summary.setStyleSheet("color:#9ca3af;")
        lv.addWidget(self.summary)
        splitter.addWidget(left)

        # eigener Dock-Manager (stört das Haupttool nicht)
        host = QWidget()
        host_lay = QVBoxLayout(host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        ads.CDockManager.setConfigFlag(ads.CDockManager.eConfigFlag.AllTabsHaveCloseButton, True)
        ads.CDockManager.setConfigFlag(ads.CDockManager.eConfigFlag.AlwaysShowTabs, True)
        self.dm = ads.CDockManager(host)
        host_lay.addWidget(self.dm)
        self.placeholder = QLabel(tr("ui.hint_click"))
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("color:#6b7280;")
        ph_dock = ads.CDockWidget(self.dm, tr("ui.results"))
        ph_dock.setWidget(self.placeholder)
        ph_dock.setFeature(ads.CDockWidget.DockWidgetFeature.DockWidgetClosable, False)
        self._result_area = self.dm.addDockWidget(ads.CenterDockWidgetArea, ph_dock)
        self._ph_dock = ph_dock
        splitter.addWidget(host)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 720])
        outer.addWidget(splitter, 1)

        self._bridge.updated.connect(self._apply_update)
        self._bridge.finished.connect(self._on_finished)
        self._results: list[TargetResult] = []
        return root

    # ------------------------------------------------------------ Steuerung
    def _options(self) -> None:
        current = self.context.settings.get("options", {})
        dlg = OptionsDialog(current if isinstance(current, dict) else {}, self.context.tr, self.input.window())
        if dlg.exec():
            self.context.settings.set("options", dlg.result())

    def _start(self) -> None:
        if self.engine and self.engine.running:
            return
        text = self.input.text().strip()
        max_hosts = 4096
        try:
            targets = parse(text, max_hosts)
        except TargetError as exc:
            self._show_error(exc)
            return
        self.error.hide()
        self.context.settings.set("last_target", text)
        options = self.context.settings.get("options", {})
        options = options if isinstance(options, dict) else {}

        # alte Ergebnisse schließen
        for dock in list(self.result_docks.values()):
            dock.closeDockWidget()
        self.result_docks.clear()
        self.row_for.clear()
        self.list.clear()

        vendors = VendorDB(self.context.data_dir, options.get("oui_download", True))
        self.engine = Engine(options, library_ports(), vendors,
                             on_update=lambda r: self._bridge.updated.emit(r),
                             on_finished=lambda: self._bridge.finished.emit())
        self._results = self.engine.start(targets)
        for i, res in enumerate(self._results):
            self.row_for[id(res)] = i
            item = QTreeWidgetItem([res.label, self.context.tr("status.pending"), ""])
            item.setFont(0, QFont("Consolas", 10))
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            self.list.addTopLevelItem(item)
        self.list.resizeColumnToContents(1)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.summary.setText(self.context.tr("ui.running", count=len(self._results)))
        if len(self._results) == 1:
            self.list.setCurrentItem(self.list.topLevelItem(0))

    def _stop(self) -> None:
        if self.engine:
            self.engine.stop()
        self.stop_btn.setEnabled(False)

    def _show_error(self, exc: TargetError) -> None:
        msg = str(exc)
        if msg.startswith("limit:"):
            text = self.context.tr("err.too_many", limit=msg.split(":")[1])
        elif msg.startswith("invalid:"):
            text = self.context.tr("err.invalid", value=msg.split(":", 1)[1])
        else:
            text = self.context.tr("err.empty")
        self.error.setText(text)
        self.error.show()

    # ------------------------------------------------------------ Aktualisierung
    def _apply_update(self, res: TargetResult) -> None:
        row = self.row_for.get(id(res))
        if row is None:
            return
        item = self.list.topLevelItem(row)
        if item is None:
            return
        item.setText(1, self.context.tr("status." + res.status))
        color = STATUS_COLOR.get(res.status)
        if color:
            item.setForeground(1, QColor(color))
        if res.total:
            pct = int(100 * res.done / res.total)
            step = self.context.tr("test." + res.step) if res.step else ""
            item.setText(2, f"{pct}%  {step}".strip())
        if res.findings:
            errors = sum(1 for f in res.findings if f.level == fx.ERROR)
            warns = sum(1 for f in res.findings if f.level == fx.WARN)
            if errors or warns:
                item.setText(0, f"{res.label}   ⚠{errors + warns}")
        # offenen Ergebnis-Tab aktualisieren
        dock = self.result_docks.get(id(res))
        if dock is not None and res.status in (DONE, NO_ANSWER, ERROR, STOPPED):
            self._fill_result(dock, res)

    def _on_finished(self) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        done = sum(1 for r in self._results if r.status == DONE)
        issues = sum(1 for r in self._results for f in r.findings if f.level in (fx.ERROR, fx.WARN))
        self.summary.setText(self.context.tr("ui.done", done=done, total=len(self._results), issues=issues))

    # ------------------------------------------------------------ Ergebnis-Tabs
    def _open_result(self, item: QTreeWidgetItem) -> None:
        row = item.data(0, Qt.ItemDataRole.UserRole)
        if row is None or row >= len(self._results):
            return
        res = self._results[row]
        dock = self.result_docks.get(id(res))
        if dock is not None:
            dock.setAsCurrentTab()
            dock.raise_()
            return
        self._dock_seq += 1
        dock = ads.CDockWidget(self.dm, res.label)
        dock.setObjectName(f"np_result_{self._dock_seq}")
        dock.setFeature(ads.CDockWidget.DockWidgetFeature.DockWidgetDeleteOnClose, True)
        dock.setFeature(ads.CDockWidget.DockWidgetFeature.CustomCloseHandling, False)
        self.result_docks[id(res)] = dock
        dock.closed.connect(lambda rid=id(res): self.result_docks.pop(rid, None))
        self._fill_result(dock, res)
        self.dm.addDockWidgetTabToArea(dock, self._result_area)
        if self._ph_dock is not None:
            self._ph_dock.toggleView(False)
        dock.setAsCurrentTab()
        dock.raise_()

    def _fill_result(self, dock: ads.CDockWidget, res: TargetResult) -> None:
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        for cat in self.renderer.category_order(res):
            widget = self.renderer.widget_for(cat, res)
            title = self.context.tr("cat." + cat)
            if cat == "findings":
                n = sum(1 for f in res.findings if f.level in (fx.ERROR, fx.WARN))
                if n:
                    title += f" ({n})"
            tabs.addTab(widget, title.replace("&", "&&"))  # & nicht als Tastenkürzel deuten
        old = dock.takeWidget()
        if old is not None:
            old.deleteLater()
        dock.setWidget(tabs)
        dock.setWindowTitle(res.label)

    # ------------------------------------------------------------ Abschluss
    def can_close(self) -> bool:
        return True

    def shutdown(self) -> None:
        if self.engine:
            self.engine.stop()

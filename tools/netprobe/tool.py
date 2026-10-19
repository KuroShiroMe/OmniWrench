"""NetProbe – umfassendes Netzwerk-Testtool.

Oben eine Eingabe (IP, DNS-Name, Netz oder Bereich) samt Testprofil-Auswahl, darunter die dauerhafte
Zielliste. Netze erscheinen als aufklappbare Gruppe mit Fortschritt (x/y Hosts). Ergebnisse jedes Ziels
werden erneut getestet statt doppelt angelegt. Ein Klick auf ein Ziel öffnet innerhalb des Tools einen
frei anordenbaren Tab (QtAds) mit den Ergebnissen je Kategorie – nur Kategorien mit Tests werden gezeigt.
Kontextmenü und Buttons bieten Wiederholen, Löschen und PDF-Export.
"""

from __future__ import annotations

import PySide6QtAds as ads
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, QSplitter, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.sdk import ToolBase
from omniwrench.ui.widgets import library_icon, make_button

from . import findings as fx
from . import pdfreport
from .engine import DONE, ERROR, NO_ANSWER, RUNNING, STOPPED, TEMPLATE_IDS, Engine, TargetResult, template_options
from .localnet import VendorDB
from .options_dialog import OptionsDialog
from .portinfo import library_ports
from .render import Renderer
from .targets import TargetError, parse

STATUS_COLOR = {RUNNING: "#3b82f6", DONE: "#10b981", NO_ANSWER: "#6b7280", ERROR: "#ef4444", STOPPED: "#f59e0b"}
ENDED = (DONE, NO_ANSWER, ERROR, STOPPED)
MAX_HOSTS = 4096


class _Bridge(QObject):
    """Signale für den Übergang vom Engine-Thread in den GUI-Thread (ToolBase ist kein QObject)."""
    updated = Signal(object)
    finished = Signal(object)


class NetProbe(ToolBase):
    def create_widget(self, parent=None) -> QWidget:
        tr = self.context.tr
        self.renderer = Renderer(tr, self.context.language)
        self.engines: set[Engine] = set()
        self.res_for_addr: dict[str, TargetResult] = {}
        self.item_for_addr: dict[str, QTreeWidgetItem] = {}
        self.group_items: dict[str, QTreeWidgetItem] = {}
        self.dock_for_addr: dict[str, ads.CDockWidget] = {}
        self._dock_seq = 0

        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        # Eingabezeile mit Testprofil-Dropdown
        top = QHBoxLayout()
        self.input = QLineEdit(self.context.settings.get("last_target", ""))
        self.input.setPlaceholderText(tr("ui.placeholder"))
        self.input.setFont(QFont("Consolas", 11))
        self.input.returnPressed.connect(self._start)
        self.template = QComboBox()
        for key in TEMPLATE_IDS:
            self.template.addItem(tr("template." + key), key)
        self.template.setToolTip(tr("ui.template_hint"))
        saved_tpl = self.context.settings.get("template", "standard")
        self.template.setCurrentIndex(max(0, self.template.findData(saved_tpl)))
        self.template.currentIndexChanged.connect(
            lambda: self.context.settings.set("template", self.template.currentData()))
        self.start_btn = make_button(tr("ui.start"), primary=True, on_click=self._start)
        self.start_btn.setIcon(library_icon("play", 16, "#ffffff"))
        self.stop_btn = make_button(tr("ui.stop"), danger=True, on_click=self._stop)
        self.stop_btn.setEnabled(False)
        self.options_btn = make_button(tr("ui.options"), on_click=self._options)
        self.options_btn.setIcon(library_icon("sliders-horizontal", 16))
        top.addWidget(QLabel(tr("ui.target")))
        top.addWidget(self.input, 1)
        top.addWidget(self.template)
        top.addWidget(self.options_btn)
        top.addWidget(self.start_btn)
        top.addWidget(self.stop_btn)
        outer.addLayout(top)

        self.error = QLabel()
        self.error.setStyleSheet("color:#ef4444")
        self.error.setWordWrap(True)
        self.error.hide()
        outer.addWidget(self.error)

        # Links die Zielliste (dauerhaft), rechts der Ergebnisbereich (eigenes Docking im Tool)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.repeat_btn = make_button(tr("ui.repeat"), on_click=self._repeat_selected)
        self.repeat_btn.setIcon(library_icon("refresh-cw", 15))
        self.delete_btn = make_button(tr("ui.delete"), on_click=self._delete_selected)
        self.delete_btn.setIcon(library_icon("trash-2", 15))
        self.export_btn = make_button(tr("ui.export"), on_click=self._export_selected)
        self.export_btn.setIcon(library_icon("file-down", 15))
        self.clear_btn = make_button(tr("ui.clear_all"), on_click=self._clear_all)
        for b in (self.repeat_btn, self.delete_btn, self.export_btn):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(self.clear_btn)
        lv.addLayout(bar)

        self.list = QTreeWidget()
        self.list.setColumnCount(3)
        self.list.setHeaderLabels([tr("list.target"), tr("list.status"), tr("list.progress")])
        self.list.setAlternatingRowColors(True)
        self.list.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.list.itemActivated.connect(self._open_result)
        self.list.itemClicked.connect(self._open_result)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
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
        splitter.setSizes([380, 720])
        outer.addWidget(splitter, 1)

        self._bridge = _Bridge()
        self._bridge.updated.connect(self._apply_update)
        self._bridge.finished.connect(self._on_finished)
        self._update_controls()
        return root

    # ------------------------------------------------------------ Optionen/Steuerung
    def _options(self) -> None:
        current = self.context.settings.get("options", {})
        dlg = OptionsDialog(current if isinstance(current, dict) else {}, self.context.tr, self.input.window())
        if dlg.exec():
            self.context.settings.set("options", dlg.result())

    def _run_options(self) -> dict:
        template = self.template.currentData()
        saved = self.context.settings.get("options", {})
        saved = saved if isinstance(saved, dict) else {}
        return template_options(template, saved)

    def _start(self) -> None:
        text = self.input.text().strip()
        try:
            targets = parse(text, MAX_HOSTS)
        except TargetError as exc:
            self._show_error(exc)
            return
        self.error.hide()
        self.context.settings.set("last_target", text)
        self._run_targets(targets)

    def _run_targets(self, targets: list) -> None:
        if not targets:
            return
        options = self._run_options()
        vendors = VendorDB(self.context.data_dir, options.get("oui_download", True))
        engine = Engine(options, library_ports(), vendors,
                        on_update=lambda r: self._bridge.updated.emit(r),
                        on_finished=lambda: None)
        engine.on_finished = lambda e=engine: self._bridge.finished.emit(e)
        results = engine.start(targets)
        self.engines.add(engine)
        last_host = None
        for res in results:
            self._bind_result(res)
            if not res.target.group:
                last_host = res
        self._update_controls()
        if last_host is not None and len(results) == 1:
            self.list.setCurrentItem(self.item_for_addr.get(last_host.target.address))

    def _stop(self) -> None:
        for engine in list(self.engines):
            engine.stop()
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

    # ------------------------------------------------------------ Zielliste
    def _bind_result(self, res: TargetResult) -> None:
        """Legt einen Zieleintrag an oder verwendet den vorhandenen erneut (Wiederholung)."""
        tr = self.context.tr
        addr = res.target.address
        parent = None
        if res.target.group:
            parent = self.group_items.get(res.target.group)
            if parent is None:
                parent = QTreeWidgetItem([res.target.group, "", ""])
                parent.setData(0, Qt.ItemDataRole.UserRole, ("group", res.target.group))
                font = parent.font(0)
                font.setBold(True)
                parent.setFont(0, font)
                self.list.addTopLevelItem(parent)
                parent.setExpanded(True)
                self.group_items[res.target.group] = parent

        item = self.item_for_addr.get(addr)
        if item is None:
            item = QTreeWidgetItem([res.label, tr("status.pending"), ""])
            item.setFont(0, QFont("Consolas", 10))
            item.setData(0, Qt.ItemDataRole.UserRole, ("host", addr))
            if parent is not None:
                parent.addChild(item)
            else:
                self.list.addTopLevelItem(item)
            self.item_for_addr[addr] = item
        else:
            item.setText(0, res.label)
            item.setText(1, tr("status.pending"))
            item.setText(2, "")
            item.setForeground(1, QBrush())
        self.res_for_addr[addr] = res
        dock = self.dock_for_addr.get(addr)
        if dock is not None:
            self._fill_result(dock, res)
        self._update_group(res.target.group)

    def _apply_update(self, res: TargetResult) -> None:
        addr = res.target.address
        if self.res_for_addr.get(addr) is not res:
            return  # veraltetes Update – Eintrag wurde zwischenzeitlich neu getestet
        item = self.item_for_addr.get(addr)
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
        label = res.label
        if res.findings:
            issues = sum(1 for f in res.findings if f.level in (fx.ERROR, fx.WARN))
            if issues:
                label = f"{res.label}   ⚠{issues}"
        item.setText(0, label)
        dock = self.dock_for_addr.get(addr)
        if dock is not None and res.status in ENDED:
            self._fill_result(dock, res)
        self._update_group(res.target.group)

    def _update_group(self, group: str) -> None:
        if not group:
            return
        parent = self.group_items.get(group)
        if parent is None:
            return
        total = parent.childCount()
        done = alive = 0
        for i in range(total):
            child = parent.child(i)
            data = child.data(0, Qt.ItemDataRole.UserRole)
            res = self.res_for_addr.get(data[1]) if data else None
            if res and res.status in ENDED:
                done += 1
                if res.status == DONE:
                    alive += 1
        parent.setText(1, self.context.tr("list.hosts", done=done, total=total, alive=alive))
        parent.setText(2, f"{int(100 * done / total)}%" if total else "")

    def _on_finished(self, engine: Engine) -> None:
        self.engines.discard(engine)
        self._update_controls()

    def _update_controls(self) -> None:
        running = bool(self.engines)
        self.stop_btn.setEnabled(running)
        hosts = [r for r in self.res_for_addr.values()]
        done = sum(1 for r in hosts if r.status == DONE)
        issues = sum(1 for r in hosts for f in r.findings if f.level in (fx.ERROR, fx.WARN))
        if running:
            self.summary.setText(self.context.tr("ui.running", count=len(hosts)))
        elif hosts:
            self.summary.setText(self.context.tr("ui.done", done=done, total=len(hosts), issues=issues))
        else:
            self.summary.setText("")

    # ------------------------------------------------------------ Auswahl-Aktionen
    def _selected_hosts(self) -> list[TargetResult]:
        """Alle über die Auswahl erreichten Host-Ergebnisse (Gruppen schließen ihre Kinder ein)."""
        out: list[TargetResult] = []
        seen: set[str] = set()

        def add(addr: str) -> None:
            if addr not in seen and addr in self.res_for_addr:
                seen.add(addr)
                out.append(self.res_for_addr[addr])

        for item in self.list.selectedItems():
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if not data:
                continue
            if data[0] == "host":
                add(data[1])
            elif data[0] == "group":
                for i in range(item.childCount()):
                    cd = item.child(i).data(0, Qt.ItemDataRole.UserRole)
                    if cd:
                        add(cd[1])
        return out

    def _repeat_selected(self) -> None:
        results = self._selected_hosts()
        if results:
            self._run_targets([r.target for r in results])

    def _delete_selected(self) -> None:
        items = list(self.list.selectedItems())
        groups_touched: set[str] = set()
        for item in items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if not data:
                continue
            if data[0] == "group":
                for i in range(item.childCount()):
                    cd = item.child(i).data(0, Qt.ItemDataRole.UserRole)
                    if cd:
                        self._remove_host(cd[1])
                self._drop_group(data[1])
            elif data[0] == "host":
                self._remove_host(data[1])
                if item.parent() is not None:
                    groups_touched.add(item.parent().data(0, Qt.ItemDataRole.UserRole)[1])
        for group in groups_touched:
            parent = self.group_items.get(group)
            if parent is not None and parent.childCount() == 0:
                self._drop_group(group)
        self._update_controls()

    def _remove_host(self, addr: str) -> None:
        dock = self.dock_for_addr.pop(addr, None)
        if dock is not None:
            dock.closeDockWidget()
        item = self.item_for_addr.pop(addr, None)
        if item is not None:
            parent = item.parent()
            if parent is not None:
                parent.removeChild(item)
            else:
                idx = self.list.indexOfTopLevelItem(item)
                if idx >= 0:
                    self.list.takeTopLevelItem(idx)
        self.res_for_addr.pop(addr, None)

    def _drop_group(self, group: str) -> None:
        parent = self.group_items.pop(group, None)
        if parent is not None:
            idx = self.list.indexOfTopLevelItem(parent)
            if idx >= 0:
                self.list.takeTopLevelItem(idx)

    def _clear_all(self) -> None:
        for engine in list(self.engines):
            engine.stop()
        for dock in list(self.dock_for_addr.values()):
            dock.closeDockWidget()
        self.dock_for_addr.clear()
        self.res_for_addr.clear()
        self.item_for_addr.clear()
        self.group_items.clear()
        self.list.clear()
        self._update_controls()

    def _export_selected(self) -> None:
        results = [r for r in self._selected_hosts() if r.status in ENDED and r.raw]
        if not results:
            results = [r for r in self.res_for_addr.values() if r.status in ENDED and r.raw]
        if not results:
            self.error.setText(self.context.tr("err.nothing_export"))
            self.error.show()
            return
        default = results[0].label.replace("/", "_") if len(results) == 1 else "netprobe"
        path, _ = QFileDialog.getSaveFileName(self.input.window(), self.context.tr("ui.export"),
                                              f"{default}.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            pdfreport.export_pdf(path, results, self.context.tr, self.context.language)
        except Exception as exc:  # noqa: BLE001 - Fehler dem Nutzer zeigen statt stiller Abbruch
            QMessageBox.warning(self.input.window(), self.context.tr("ui.export"),
                                self.context.tr("err.export_failed", error=str(exc)))
            return
        self.context.notify(self.context.tr("ui.export_done", path=path))

    def _context_menu(self, pos) -> None:
        if not self.list.selectedItems():
            item = self.list.itemAt(pos)
            if item is not None:
                item.setSelected(True)
        if not self.list.selectedItems():
            return
        menu = QMenu(self.list)
        acts = [("refresh-cw", "ui.repeat", self._repeat_selected),
                ("file-down", "ui.export", self._export_selected),
                ("trash-2", "ui.delete", self._delete_selected)]
        for icon, key, slot in acts:
            act = QAction(library_icon(icon, 15), self.context.tr(key), menu)
            act.triggered.connect(slot)
            menu.addAction(act)
        menu.addSeparator()
        clear = QAction(self.context.tr("ui.clear_all"), menu)
        clear.triggered.connect(self._clear_all)
        menu.addAction(clear)
        menu.exec(self.list.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------ Ergebnis-Tabs
    def _open_result(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != "host":
            return
        res = self.res_for_addr.get(data[1])
        if res is None:
            return
        dock = self.dock_for_addr.get(data[1])
        if dock is not None:
            dock.setAsCurrentTab()
            dock.raise_()
            return
        self._dock_seq += 1
        dock = ads.CDockWidget(self.dm, res.label)
        dock.setObjectName(f"np_result_{self._dock_seq}")
        dock.setFeature(ads.CDockWidget.DockWidgetFeature.DockWidgetDeleteOnClose, True)
        dock.setFeature(ads.CDockWidget.DockWidgetFeature.CustomCloseHandling, False)
        self.dock_for_addr[data[1]] = dock
        dock.closed.connect(lambda a=data[1]: self.dock_for_addr.pop(a, None))
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
        for engine in list(self.engines):
            engine.stop()

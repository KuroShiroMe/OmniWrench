"""Einstellungen › KI-Assistenten › Funktionen: Standard-Assistent je Funktion, was er darf (letzte Prüfung) und wie
viel Volumen er meldet, dazu das Audio-Ausgabegerät der KI-Tools.

Die Auswahl landet in "ai_defaults" (omniwrench.ai.defaults); die KI-Tools übernehmen sie beim nächsten Öffnen bzw.
Aktualisieren. Prüfen nutzt die Fähigkeitsprüfung (omniwrench.ai.scan); die Tabelle zeigt den letzten Stand ohne
neue Abfrage.
"""

from __future__ import annotations

import time

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from omniwrench.ai import defaults, scan
from omniwrench.ai.connections import ConnectionStore
from omniwrench.core.i18n import tr

from . import theme
from .ai_kit import OUTPUT_KEY, audio_outputs
from .widgets import label, make_button
from .workers import run_async

LOCAL_LABEL = {defaults.WHISPER: "ai.kit.whisper", defaults.VOSK: "ai.kit.vosk",
               defaults.SYSTEM_VOICE: "ai.kit.system_voice", defaults.PIPER: "ai.kit.piper"}


class DefaultsPage(QWidget):
    COLS = ("function", "assistant", "status", "volume", "requires")

    def __init__(self, settings, vault, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.store = ConnectionStore(settings, vault)
        self._busy = False
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr("ai.def.title"), "CardTitle"))
        lay.addWidget(label(tr("ai.def.intro"), "Muted", wrap=True))
        self.table = QTableWidget(len(defaults.FUNCTIONS), len(self.COLS))
        self.table.setHorizontalHeaderLabels([tr(f"ai.def.col.{c}") for c in self.COLS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        head.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 230)
        self.table.setColumnWidth(3, 260)
        self.combos: list[QComboBox] = []
        for i, fn in enumerate(defaults.FUNCTIONS):
            self.table.setItem(i, 0, QTableWidgetItem(tr(f"ai.def.fn.{fn}")))
            box = QComboBox()
            box.activated.connect(lambda _idx, r=i: self._chosen(r))
            self.table.setCellWidget(i, 1, box)
            self.combos.append(box)
        lay.addWidget(self.table, 1)
        btns = QHBoxLayout()
        self.check_one = make_button("🔍 " + tr("ai.def.check_selected"), on_click=self.check_selected)
        btns.addWidget(self.check_one)
        self.check_all = make_button("🔍 " + tr("ai.def.check_all"), on_click=self.check_everything)
        btns.addWidget(self.check_all)
        btns.addWidget(make_button(tr("ai.def.details"), on_click=self.show_details))
        btns.addStretch()
        lay.addLayout(btns)
        out = QHBoxLayout()
        out.addWidget(QLabel(tr("ai.def.output")))
        self.output = QComboBox()
        self.output.addItem(tr("ai.def.output_default"), "")
        for did, name in audio_outputs():
            self.output.addItem(name, did)
        self.output.setCurrentIndex(max(0, self.output.findData(settings.get(OUTPUT_KEY) or "")))
        self.output.currentIndexChanged.connect(lambda *_: settings.set(OUTPUT_KEY, self.output.currentData() or ""))
        out.addWidget(self.output, 1)
        lay.addLayout(out)
        self.status = label("", "Muted", wrap=True)
        lay.addWidget(self.status)
        lay.addWidget(label(tr("ai.def.hint"), "Muted", wrap=True))
        self.refresh()

    # --- Anzeige -------------------------------------------------------------------------------------
    def refresh(self) -> None:
        for i, fn in enumerate(defaults.FUNCTIONS):
            box = self.combos[i]
            keep = defaults.get(self.settings, fn) or (self.store.primary_id() if defaults.KIND[fn] == "chat" else "")
            box.blockSignals(True)
            box.clear()
            for c in defaults.candidates(self.store, fn):
                box.addItem(c.name, c.id)
            for opt in defaults.LOCAL.get(fn, ()):
                box.addItem("💻 " + tr(LOCAL_LABEL[opt]), opt)
            if not box.count():
                box.addItem(tr("ai.def.none"), "")
            box.setCurrentIndex(max(0, box.findData(keep)))
            box.setEnabled(box.count() > 1 or bool(box.currentData()))
            box.blockSignals(False)
            self._show_row(i)
        self.table.resizeRowsToContents()

    def _show_row(self, i: int) -> None:
        from .ai_scan import status_text, volume_text
        fn, cid = defaults.FUNCTIONS[i], self.combos[i].currentData() or ""
        kind = defaults.KIND[fn]
        conn = self.store.get(cid) if cid and cid not in LOCAL_LABEL else None
        c = theme.current
        status, volume, req, color = "", "", "", c["muted"]
        if cid in LOCAL_LABEL:
            status, color, volume = "✔ " + tr("ai.def.local_ok"), c["success"], tr("ai.def.local_free")
        elif conn is not None:
            last = scan.last(self.settings, conn.id)
            k = (last or {}).get("kinds", {}).get(kind) if last else None
            if k:
                status = status_text(k.get("status", "unknown"))
                color = {"ok": c["success"], "missing": c["danger"], "error": c["danger"]}.get(k.get("status"),
                                                                                             c["muted"])
                if k.get("requires"):
                    req = tr(f"ai.req.{k['requires']}")
            else:
                status = tr("ai.def.not_checked")
            if last:
                volume = (volume_text(last) or tr("ai.def.no_volume")) + " · " + \
                    time.strftime("%d.%m. %H:%M", time.localtime(last.get("ts", 0)))
            if not req and conn.info is not None:
                spec = ((conn.info.media or {}).get(kind) or {}) if kind in ("image", "music", "video") else {}
                code = spec.get("requires") or conn.info.requirement(conn.auth)
                req = tr(f"ai.req.{code}") if code else ""
        for col, text in ((2, status), (3, volume), (4, req)):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            if col == 2:
                item.setForeground(QBrush(QColor(color)))
            self.table.setItem(i, col, item)

    def _chosen(self, i: int) -> None:
        fn, cid = defaults.FUNCTIONS[i], self.combos[i].currentData() or ""
        if not cid:
            return
        defaults.set(self.settings, fn, cid)
        self._show_row(i)
        self.status.setText(tr("ai.def.saved", function=tr(f"ai.def.fn.{fn}"), name=self.combos[i].currentText()))

    # --- Prüfen --------------------------------------------------------------------------------------
    def _selected_conn(self):
        i = self.table.currentRow()
        cid = self.combos[i].currentData() or "" if i >= 0 else ""
        return self.store.get(cid) if cid and cid not in LOCAL_LABEL else None

    def show_details(self) -> None:
        conn = self._selected_conn()
        if conn is None:
            self.status.setText(tr("ai.def.select_first"))
            return
        from .ai_scan import ScanDialog
        ScanDialog(self.store, conn, self, run=False).exec()
        self.refresh()

    def check_selected(self) -> None:
        conn = self._selected_conn()
        if conn is None:
            self.status.setText(tr("ai.def.select_first"))
            return
        self._check([conn])

    def check_everything(self) -> None:
        seen, conns = set(), []
        for box in self.combos:
            for j in range(box.count()):
                cid = box.itemData(j) or ""
                c = self.store.get(cid) if cid and cid not in LOCAL_LABEL else None
                if c is not None and c.id not in seen:
                    seen.add(c.id)
                    conns.append(c)
        self._check(conns)

    def _check(self, conns: list) -> None:
        if self._busy or not conns:
            return
        self._busy = True
        store = self.store
        for b in (self.check_one, self.check_all):
            b.setEnabled(False)

        def work(progress):
            errors = []
            for c in conns:
                progress(tr("ai.scan.running", name=c.name))
                try:
                    scan.scan(store, c)
                except Exception as err:  # noqa: BLE001 - nächste Verbindung trotzdem prüfen
                    errors.append(f"{c.name}: {err}")
            return errors

        def done(errors):
            self._end_check()
            self.status.setText(("⚠ " + "; ".join(errors)) if errors else tr("ai.def.checked", count=len(conns)))

        def failed(text):
            self._end_check()
            self.status.setText("⚠ " + text.splitlines()[0])
        run_async(work, done, failed, self.status.setText)

    def _end_check(self) -> None:
        self._busy = False
        for b in (self.check_one, self.check_all):
            b.setEnabled(True)
        self.refresh()

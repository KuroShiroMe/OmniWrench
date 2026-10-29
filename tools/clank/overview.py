"""Reiter „KI-Übersicht“: Standard-Assistent je Funktion, was er darf (Prüfung) und wie viel Volumen er meldet.

Die Auswahl schreibt dieselben Tool-Einstellungen wie die einzelnen Reiter (image_connection, va_stt …) und stellt
den Reiter gleich mit um. Prüfen nutzt die Fähigkeitsprüfung des Hauptprogramms (omniwrench.ai.scan); das Ergebnis
bleibt gespeichert, die Tabelle zeigt den letzten Stand ohne neue Abfrage.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from omniwrench.sdk import run_async

from . import local_speech as ls

VOSK = "__vosk__"
SYSTEM_VOICE = "__system__"
LOCAL = {ls.WHISPER: "va.whisper", VOSK: "va.offline", SYSTEM_VOICE: "va.system_voice", ls.PIPER: "va.piper"}


@dataclass
class Row:
    key: str                     # Tool-Einstellung
    label: str                   # Sprachschlüssel der Funktion
    kind: str                    # Art in der Prüfung (chat, image, music, video, stt, tts)
    candidates: Callable         # (store) -> [Connection]
    local: tuple = ()            # Offline-Optionen
    tab: str = ""                # Attribut des Reiters im Studio
    combo: str = ""              # Attribut der Auswahl im Reiter


def _alive(conns) -> list:
    return [c for c in conns if not (c.info and c.info.removed)]


def rows() -> list[Row]:
    from omniwrench.ai import media, speech
    chat = lambda s: _alive(s.chat_connections())                       # noqa: E731
    return [
        Row("chat_connection", "ov.chat", "chat", chat, tab="panel", combo="bot"),
        Row("image_connection", "ov.image", "image", lambda s: _alive(media.connections_for(s, "image")),
            tab="images", combo="conn_box"),
        Row("music_connection", "ov.music", "music", lambda s: _alive(media.connections_for(s, "music")),
            tab="music", combo="conn_box"),
        Row("video_connection", "ov.video", "video", lambda s: _alive(media.connections_for(s, "video")),
            tab="video", combo="conn_box"),
        Row("doc_connection", "ov.docs", "chat", chat, tab="docs", combo="conn_box"),
        Row("ts_connection", "ov.ts", "stt", lambda s: _alive(speech.stt_connections(s)), (ls.WHISPER,),
            tab="transcript", combo="conn"),
        Row("ts_summary_connection", "ov.ts_summary", "chat", chat, tab="transcript", combo="sum_conn"),
        Row("va_stt", "ov.va_stt", "stt", lambda s: _alive(speech.stt_connections(s)), (ls.WHISPER, VOSK),
            tab="voice", combo="stt"),
        Row("va_tts", "ov.va_tts", "tts", lambda s: _alive(speech.tts_connections(s)), (SYSTEM_VOICE, ls.PIPER),
            tab="voice", combo="tts"),
    ]


class OverviewTab(QWidget):
    COLS = ("function", "assistant", "status", "volume", "requires")

    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.services = studio.services
        self.tr_ = tr = studio.tr
        self.settings = studio.context.settings
        self.rows = rows()
        self._busy = False
        lay = QVBoxLayout(self)
        intro = QLabel(tr("ov.intro"))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.table = QTableWidget(len(self.rows), len(self.COLS))
        self.table.setHorizontalHeaderLabels([tr(f"ov.col.{c}") for c in self.COLS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        head.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 240)
        self.table.setColumnWidth(3, 300)
        self.combos: list[QComboBox] = []
        for i, row in enumerate(self.rows):
            self.table.setItem(i, 0, QTableWidgetItem(tr(row.label)))
            box = QComboBox()
            box.activated.connect(lambda _idx, r=i: self._chosen(r))
            self.table.setCellWidget(i, 1, box)
            self.combos.append(box)
        lay.addWidget(self.table, 1)
        btns = QHBoxLayout()
        self.check_one = QPushButton("🔍 " + tr("ov.check_selected"))
        self.check_one.clicked.connect(self.check_selected)
        btns.addWidget(self.check_one)
        self.check_all = QPushButton("🔍 " + tr("ov.check_all"))
        self.check_all.clicked.connect(self.check_everything)
        btns.addWidget(self.check_all)
        self.details = QPushButton(tr("ov.details"))
        self.details.clicked.connect(self.show_details)
        btns.addWidget(self.details)
        btns.addStretch()
        opts = QPushButton(tr("ui.open_ai_options"))
        opts.clicked.connect(self.services.open_options)
        btns.addWidget(opts)
        lay.addLayout(btns)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        hint = QLabel(tr("ov.hint"))
        hint.setWordWrap(True)
        hint.setEnabled(False)
        lay.addWidget(hint)

    # --- Anzeige -------------------------------------------------------------------------------------
    def refresh(self) -> None:
        store = self.services.connections
        tr = self.tr_
        for i, row in enumerate(self.rows):
            box = self.combos[i]
            keep = self.settings.get(row.key) or ""
            if not keep and row.kind == "chat":
                keep = store.primary_id()
            box.blockSignals(True)
            box.clear()
            for c in row.candidates(store):
                box.addItem(c.name, c.id)
            for opt in row.local:
                box.addItem("💻 " + tr(LOCAL[opt]), opt)
            if not box.count():
                box.addItem(tr("ov.none"), "")
            idx = box.findData(keep)
            box.setCurrentIndex(max(0, idx))
            box.setEnabled(bool(box.currentData()) or box.count() > 1)
            box.blockSignals(False)
            self._show_row(i)
        self.table.resizeRowsToContents()

    def _show_row(self, i: int) -> None:
        from omniwrench.ai import scan
        from omniwrench.ui import theme
        from omniwrench.ui.ai_scan import status_text, volume_text
        tr = self.tr_
        row, cid = self.rows[i], self.combos[i].currentData() or ""
        conn = self.services.connections.get(cid) if cid and cid not in LOCAL else None
        status, volume, req, color = "", "", "", theme.current["muted"]
        if cid in LOCAL:
            status, color = "✔ " + tr("ov.local_ok"), theme.current["success"]
            volume = tr("ov.local_free")
        elif conn is not None:
            last = scan.last(self.services.settings, conn.id)
            kind = (last or {}).get("kinds", {}).get(row.kind) if last else None
            if kind:
                status = status_text(kind.get("status", "unknown"))
                color = {"ok": theme.current["success"], "missing": theme.current["danger"],
                         "error": theme.current["danger"]}.get(kind.get("status"), theme.current["muted"])
                if kind.get("requires"):
                    req = tr_app(f"ai.req.{kind['requires']}")
            else:
                status = tr("ov.not_checked")
            if last:
                volume = volume_text(last) or tr("ov.no_volume")
                volume += " · " + time.strftime("%d.%m. %H:%M", time.localtime(last.get("ts", 0)))
            if not req and conn.info is not None:
                spec = ((conn.info.media or {}).get(row.kind) or {}) if row.kind in ("image", "music", "video") \
                    else {}
                code = spec.get("requires") or conn.info.requirement(conn.auth)
                req = tr_app(f"ai.req.{code}") if code else ""
        for col, text in ((2, status), (3, volume), (4, req)):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            if col == 2:
                item.setForeground(QBrush(QColor(color)))
            self.table.setItem(i, col, item)

    # --- Auswahl -------------------------------------------------------------------------------------
    def _chosen(self, i: int) -> None:
        row, cid = self.rows[i], self.combos[i].currentData() or ""
        if not cid:
            return
        self.settings.set(row.key, cid)
        apply_to_tab(self.studio, row, cid)
        self._show_row(i)
        self.status.setText(self.tr_("ov.saved", function=self.tr_(row.label), name=self.combos[i].currentText()))

    # --- Prüfen --------------------------------------------------------------------------------------
    def _selected_conn(self):
        i = self.table.currentRow()
        if i < 0:
            return None
        cid = self.combos[i].currentData() or ""
        return self.services.connections.get(cid) if cid and cid not in LOCAL else None

    def show_details(self) -> None:
        conn = self._selected_conn()
        if conn is None:
            self.status.setText(self.tr_("ov.select_first"))
            return
        from omniwrench.ui.ai_scan import ScanDialog
        ScanDialog(self.services.connections, conn, self, run=False).exec()
        self.refresh()

    def check_selected(self) -> None:
        conn = self._selected_conn()
        if conn is None:
            self.status.setText(self.tr_("ov.select_first"))
            return
        self._check([conn])

    def check_everything(self) -> None:
        seen, conns = set(), []
        for box in self.combos:
            for j in range(box.count()):
                cid = box.itemData(j) or ""
                c = self.services.connections.get(cid) if cid and cid not in LOCAL else None
                if c is not None and c.id not in seen:
                    seen.add(c.id)
                    conns.append(c)
        self._check(conns)

    def _check(self, conns: list) -> None:
        from omniwrench.ai import scan
        if self._busy or not conns:
            return
        self._busy = True
        tr = self.tr_
        store = self.services.connections
        for b in (self.check_one, self.check_all):
            b.setEnabled(False)

        def work(progress):
            errors = []
            for c in conns:
                progress(tr("ov.checking", name=c.name))
                try:
                    scan.scan(store, c)
                except Exception as err:  # noqa: BLE001 - nächste Verbindung trotzdem prüfen
                    errors.append(f"{c.name}: {err}")
            return errors

        def done(errors):
            self._end_check()
            self.status.setText(("⚠ " + "; ".join(errors)) if errors else tr("ov.checked", count=len(conns)))

        def failed(text):
            self._end_check()
            self.status.setText("⚠ " + text.splitlines()[0])
        run_async(work, done, failed, self.status.setText)

    def _end_check(self) -> None:
        self._busy = False
        for b in (self.check_one, self.check_all):
            b.setEnabled(True)
        self.refresh()


def tr_app(key: str) -> str:
    from omniwrench.core.i18n import tr
    return tr(key)


def apply_to_tab(studio, row: Row, cid: str) -> None:
    """Gewählten Standard im Reiter einstellen (wenn der Reiter seine Auswahl schon gefüllt hat)."""
    tab = getattr(studio, row.tab, None)
    box = getattr(tab, row.combo, None) if tab is not None else None
    if box is None:
        return
    idx = box.findData(cid)
    if idx < 0 or idx == box.currentIndex():
        return
    if row.tab == "panel":
        box.setCurrentIndex(idx)
        tab._bot_changed(idx)
    else:
        box.setCurrentIndex(idx)


def apply_defaults(studio) -> None:
    """Beim Start: gespeicherten Standard-Chat-Assistenten in den Chat übernehmen."""
    cid = studio.context.settings.get("chat_connection") or ""
    if cid:
        apply_to_tab(studio, rows()[0], cid)

"""Einstellungen › KI-Assistenten › Ollama: Ollama installieren, starten und Modelle laden (omniwrench.ai.ollama).

Geöffnet aus dem Verbindungsdialog des Anbieters Ollama. Downloads laufen im Fortschrittsfenster (ai_kit).
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from omniwrench.ai import ollama
from omniwrench.core.i18n import tr

from .ai_kit import ProgressDialog
from .widgets import label, make_button


class OllamaDialog(QDialog):
    def __init__(self, base_url: str = "", parent=None):
        super().__init__(parent)
        self.base_url = base_url or ollama.DEFAULT_URL
        self.setWindowTitle(tr("ai.ollama.title"))
        self.setMinimumWidth(640)
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr("ai.ollama.intro"), "Muted", wrap=True))
        self.state = label("", wrap=True)
        lay.addWidget(self.state)
        row = QHBoxLayout()
        self.install_btn = make_button("⬇ " + tr("ai.ollama.install"), primary=True, on_click=self.install)
        row.addWidget(self.install_btn)
        self.start_btn = make_button("▶ " + tr("ai.ollama.start"), on_click=self.start)
        row.addWidget(self.start_btn)
        row.addStretch()
        lay.addLayout(row)
        self.linux = QLineEdit(ollama.LINUX_COMMAND)
        self.linux.setReadOnly(True)
        lrow = QHBoxLayout()
        lrow.addWidget(self.linux, 1)
        self.copy_btn = make_button("⧉ " + tr("ai.ollama.copy"), on_click=lambda: (
            QGuiApplication.clipboard().setText(ollama.LINUX_COMMAND), self.status.setText(tr("ai.ollama.copied"))))
        lrow.addWidget(self.copy_btn)
        lay.addLayout(lrow)

        lay.addWidget(label(tr("ai.ollama.models"), "CardTitle"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("ai.ollama.col_model"), tr("ai.ollama.col_size")])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(140)
        lay.addWidget(self.table, 1)
        prow = QHBoxLayout()
        self.pick = QComboBox()
        self.pick.setEditable(True)
        self.pick.setMaxVisibleItems(20)
        self.ram = ollama.total_ram_gb()
        self._fill_pick(set())
        self.pick.lineEdit().setPlaceholderText(tr("ai.ollama.other"))
        prow.addWidget(self.pick, 1)
        self.pull_btn = make_button("⬇ " + tr("ai.ollama.pull"), on_click=self.pull)
        prow.addWidget(self.pull_btn)
        self.del_btn = make_button(tr("ai.ollama.delete"), on_click=self.delete)
        prow.addWidget(self.del_btn)
        lay.addLayout(prow)
        lay.addWidget(label(tr("ai.ollama.hint"), "Muted", wrap=True))
        lib = QLabel(f'<a href="{ollama.LIBRARY_URL}">{tr("ai.ollama.library")}</a>')
        lib.setOpenExternalLinks(True)
        lay.addWidget(lib)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.refresh()

    # --- Anzeige -------------------------------------------------------------------------------------
    def refresh(self) -> None:
        local = ollama.is_local(self.base_url)
        exe = ollama.executable() if local else "remote"
        ver = ollama.version(self.base_url)
        if ver:
            text = "✔ " + tr("ai.ollama.running", version=ver, url=ollama.root_url(self.base_url))
        elif exe:
            text = tr("ai.ollama.stopped")
        else:
            text = tr("ai.ollama.missing")
        self.state.setText(text)
        self.install_btn.setVisible(local and not exe and not ver and os.name == "nt")
        self.linux.setVisible(local and not exe and not ver and os.name != "nt")
        self.copy_btn.setVisible(self.linux.isVisibleTo(self))
        self.start_btn.setVisible(local and bool(exe) and not ver)
        for b in (self.pull_btn, self.del_btn, self.pick):
            b.setEnabled(bool(ver))
        self.table.setRowCount(0)
        if not ver:
            return
        try:
            found = ollama.models(self.base_url)
        except (OSError, ValueError) as err:
            self.status.setText("⚠ " + str(err))
            return
        self._fill_pick({m["name"] for m in found})
        for m in found:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(m["name"]))
            self.table.setItem(r, 1, QTableWidgetItem(f"{m['size'] / 1e9:.1f} GB"))

    def _fill_pick(self, installed: set[str]) -> None:
        """Empfehlungen (★) zuerst, dann nach Größe; ✔ = schon geladen, ⚠ = größer als der Arbeitsspeicher."""
        typed = self.pick.currentText()
        keep = typed if typed and typed != self.pick.itemText(self.pick.currentIndex()) else ""
        self.pick.blockSignals(True)
        self.pick.clear()
        rows = list(ollama.RECOMMENDED[:ollama.TOP]) + sorted(ollama.RECOMMENDED[ollama.TOP:], key=lambda m: m[1])
        for i, (name, gb, key) in enumerate(rows):
            if i == ollama.TOP:
                self.pick.insertSeparator(self.pick.count())
            mark = "★ " if i < ollama.TOP else ""
            if name in installed or f"{name}:latest" in installed:
                mark = "✔ " + mark
            text = f"{mark}{name} · ~{gb:g} GB · {tr(f'ai.ollama.rec.{key}')}"
            self.pick.addItem(text, name)
            if self.ram and gb > self.ram * 0.85:
                self.pick.setItemData(self.pick.count() - 1, tr("ai.ollama.too_big", ram=round(self.ram)),
                                      Qt.ItemDataRole.ToolTipRole)
                self.pick.setItemText(self.pick.count() - 1, "⚠ " + text)
        if keep:
            self.pick.setEditText(keep)
        self.pick.blockSignals(False)

    def models(self) -> list[str]:
        return [self.table.item(r, 0).text() for r in range(self.table.rowCount())]

    # --- Aktionen ------------------------------------------------------------------------------------
    def install(self) -> None:
        if QMessageBox.question(self, tr("ai.ollama.install"), tr("ai.ollama.install_q")) \
                != QMessageBox.StandardButton.Yes:
            return

        def work(progress):
            ollama.install_windows(progress)
            progress(tr("ai.ollama.starting"))
            return ollama.start(self.base_url, wait=40)
        dlg = ProgressDialog(tr("ai.ollama.install"), work, self)
        dlg.exec()
        self.status.setText(("⚠ " + dlg.error) if dlg.error else tr("ai.ollama.installed"))
        self.refresh()

    def start(self) -> None:
        dlg = ProgressDialog(tr("ai.ollama.start"), lambda progress: ollama.start(self.base_url), self)
        dlg.exec()
        if not dlg.result:
            self.status.setText("⚠ " + (dlg.error or tr("ai.ollama.no_start")))
        self.refresh()

    def _chosen(self) -> str:
        text = self.pick.currentText().strip()
        data = self.pick.currentData()
        if data and self.pick.itemText(self.pick.currentIndex()) == text:
            return data
        return text.lstrip("⚠✔★ ").split(" ")[0]

    def pull(self) -> None:
        name = self._chosen()
        if not name:
            return
        dlg = ProgressDialog(tr("ai.ollama.pulling", model=name),
                             lambda progress: ollama.pull(name, self.base_url, progress), self)
        dlg.exec()
        self.status.setText(("⚠ " + dlg.error) if dlg.error else tr("ai.ollama.pulled", model=name))
        self.refresh()

    def delete(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        name = self.table.item(r, 0).text()
        if QMessageBox.question(self, tr("ai.ollama.delete"), tr("ai.ollama.delete_q", model=name)) \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            ollama.delete(name, self.base_url)
        except OSError as err:
            self.status.setText("⚠ " + str(err))
        self.refresh()

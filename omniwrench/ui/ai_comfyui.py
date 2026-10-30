"""Einstellungen › KI-Assistenten › ComfyUI: ComfyUI installieren, starten und die Modelle für Bilder, Musik und
Video laden (omniwrench.ai.comfyui).

Geöffnet aus dem Verbindungsdialog des Anbieters ComfyUI. Downloads laufen im Fortschrittsfenster (ai_kit).
"""

from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from omniwrench.ai import comfyui
from omniwrench.core.i18n import tr

from .ai_kit import ProgressDialog
from .widgets import label, make_button

ICONS = {"image": "🖼", "music": "🎵", "video": "🎬"}


class ComfyDialog(QDialog):
    def __init__(self, base_url: str = "", settings=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.base_url = base_url or comfyui.DEFAULT_URL
        self.server = ""
        self.setWindowTitle(tr("ai.comfy.title"))
        self.setMinimumWidth(680)
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr("ai.comfy.intro"), "Muted", wrap=True))
        self.state = label("", wrap=True)
        lay.addWidget(self.state)
        row = QHBoxLayout()
        self.install_btn = make_button("⬇ " + tr("ai.comfy.install"), primary=True, on_click=self.install)
        row.addWidget(self.install_btn)
        self.start_btn = make_button("▶ " + tr("ai.comfy.start"), on_click=self.start)
        row.addWidget(self.start_btn)
        row.addWidget(make_button("↻ " + tr("ai.comfy.recheck"), on_click=self.refresh))
        row.addStretch()
        lay.addLayout(row)
        self.linux_label = label(tr("ai.comfy.linux"), "Muted")
        lay.addWidget(self.linux_label)
        lrow = QHBoxLayout()
        self.linux = QLineEdit(comfyui.LINUX_COMMAND)
        self.linux.setReadOnly(True)
        lrow.addWidget(self.linux, 1)
        self.copy_btn = make_button("⧉ " + tr("ai.ollama.copy"), on_click=lambda: (
            QGuiApplication.clipboard().setText(comfyui.LINUX_COMMAND), self.status.setText(tr("ai.ollama.copied"))))
        lrow.addWidget(self.copy_btn)
        lay.addLayout(lrow)

        lay.addWidget(label(tr("ai.comfy.models"), "CardTitle"))
        frow = QHBoxLayout()
        frow.addWidget(QLabel(tr("ai.comfy.folder")))
        self.folder = QLineEdit(str((settings.get("ai_comfy_models") if settings else "") or ""))
        self.folder.setPlaceholderText("…/ComfyUI/models")
        self.folder.editingFinished.connect(self._folder_changed)
        frow.addWidget(self.folder, 1)
        frow.addWidget(make_button("…", on_click=self._browse))
        lay.addLayout(frow)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("ai.comfy.col_model"), tr("ai.ollama.col_size"), ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(170)
        lay.addWidget(self.table, 1)
        brow = QHBoxLayout()
        self.dl_btn = make_button("⬇ " + tr("ai.comfy.download"), on_click=self.download)
        brow.addWidget(self.dl_btn)
        brow.addStretch()
        lay.addLayout(brow)
        lay.addWidget(label(tr("ai.comfy.hint"), "Muted", wrap=True))
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.refresh()

    # --- Anzeige -------------------------------------------------------------------------------------
    def refresh(self) -> None:
        local = comfyui.is_local(self.base_url)
        self.server = comfyui.find_server(self.base_url) if local else (
            comfyui.root_url(self.base_url) if comfyui.version(self.base_url) else "")
        exe = comfyui.executable() if local else ""
        if self.server:
            ver = comfyui.version(self.server)
            self.state.setText("✔ " + tr("ai.comfy.running", version=ver, url=self.server))
            if not self.folder.text().strip():
                self.folder.setText(comfyui.guess_models_dir(self.server))
                self._folder_changed()
        else:
            self.state.setText(tr("ai.comfy.stopped") if exe else tr("ai.comfy.missing"))
        self.install_btn.setVisible(local and not exe and not self.server and os.name == "nt")
        linux = local and not exe and not self.server and os.name != "nt"
        for w in (self.linux_label, self.linux, self.copy_btn):
            w.setVisible(linux)
        self.start_btn.setVisible(local and bool(exe) and not self.server)
        self._fill()

    def _fill(self) -> None:
        keep = self.table.currentRow()
        self.table.setRowCount(0)
        folder = self.folder.text().strip()
        for name, preset in comfyui.PRESETS.items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            item = QTableWidgetItem(f"{ICONS[preset['kind']]} {name} · {tr(f'ai.comfy.desc.{name}')}")
            item.setData(256, name)
            self.table.setItem(r, 0, item)
            self.table.setItem(r, 1, QTableWidgetItem(f"{comfyui.size_gb(name):g} GB"))
            missing = comfyui.missing_files(name, self.server, folder)
            self.table.setItem(r, 2, QTableWidgetItem("✔" if not missing else "—"))
        self.table.resizeColumnToContents(1)
        self.table.resizeColumnToContents(2)
        self.table.selectRow(keep if 0 <= keep < self.table.rowCount() else 0)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("ai.comfy.folder"), self.folder.text())
        if path:
            self.folder.setText(path)
            self._folder_changed()

    def _folder_changed(self) -> None:
        if self.settings is not None:
            self.settings.set("ai_comfy_models", self.folder.text().strip())
        self._fill()

    def chosen(self) -> str:
        r = self.table.currentRow()
        return self.table.item(r, 0).data(256) if r >= 0 else ""

    # --- Aktionen ------------------------------------------------------------------------------------
    def install(self) -> None:
        if QMessageBox.question(self, tr("ai.comfy.install"), tr("ai.comfy.install_q")) \
                != QMessageBox.StandardButton.Yes:
            return
        dlg = ProgressDialog(tr("ai.comfy.install"), comfyui.install_windows, self)
        dlg.exec()
        if dlg.error:
            self.status.setText("⚠ " + dlg.error)
        elif dlg.result is False:                        # kein winget: Download-Seite
            QDesktopServices.openUrl(QUrl(comfyui.DOWNLOAD_PAGE))
            self.status.setText(tr("ai.comfy.manual"))
        else:
            self.status.setText(tr("ai.comfy.first_start"))
        self.refresh()

    def start(self) -> None:
        dlg = ProgressDialog(tr("ai.comfy.start"), lambda progress: comfyui.start(self.base_url), self)
        dlg.exec()
        if not dlg.result:
            self.status.setText("⚠ " + (dlg.error or tr("ai.comfy.no_start")))
        self.refresh()

    def download(self) -> None:
        name = self.chosen()
        folder = self.folder.text().strip()
        if not name:
            return
        if not folder:
            self.status.setText(tr("ai.comfy.need_folder"))
            return
        missing = comfyui.missing_files(name, "", folder)
        if not missing:
            self.status.setText(tr("ai.comfy.done"))
            return
        gb = round(sum(f[3] for f in missing), 1)
        if QMessageBox.question(self, tr("ai.comfy.download"), tr("ai.comfy.download_q", model=name, size=f"{gb:g}",
                                                                  folder=folder)) != QMessageBox.StandardButton.Yes:
            return
        dlg = ProgressDialog(tr("ai.comfy.download") + " – " + name,
                             lambda progress: comfyui.download(name, folder, self.server, progress), self)
        dlg.exec()
        self.status.setText(("⚠ " + dlg.error) if dlg.error else tr("ai.comfy.done"))
        self.refresh()

    def url(self) -> str:
        """Adresse des gefundenen ComfyUI (für die Verbindung), sonst die bisherige."""
        return self.server or self.base_url

"""Pixelizer – Bilder: Bilder mit den verbundenen Bild-Anbietern erzeugen, Galerie aus der Datenablage.

Die Anbieter-Schnittstellen stehen im Hauptprogramm (omniwrench.ai.media). Bilder landen unverschlüsselt
als PNG/JPG mit JSON-Beschreibung im Bilder-Ordner der KI-Datenablage.
"""

from __future__ import annotations

import mimetypes
import threading
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QStackedWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from omniwrench.sdk import run_async
from omniwrench.ui.ai_kit import NoBotPage

MAX_REFS = 4
THUMB = 150


def _thumb(path: Path, size: int = THUMB) -> QIcon:
    img = QImage(str(path))
    if img.isNull():
        return QIcon()
    return QIcon(QPixmap.fromImage(img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)))


class ImagesTab(QWidget):
    to_chat = Signal(str)        # Pfad eines Bildes, das an den Chat angehängt werden soll

    def __init__(self, studio):
        super().__init__()
        from omniwrench.ai import media
        self.media = media
        self.studio = studio
        self.services = studio.services
        tr = self.tr_ = studio.tr
        self.refs: list[dict] = []
        self._stop: threading.Event | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.empty = NoBotPage(tr("img.no_bot"), tr("ui.open_ai_options"), self.services.open_options)
        self.stack.addWidget(self.empty)

        page = QWidget()
        self.stack.addWidget(page)
        lay = QHBoxLayout(page)
        split = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(split)

        # --- links: Auftrag
        form_w = QWidget()
        fl = QVBoxLayout(form_w)
        fl.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.conn_box = QComboBox()
        self.conn_box.currentIndexChanged.connect(self._conn_changed)
        form.addRow(tr("img.connection"), self.conn_box)
        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        form.addRow(tr("img.model"), self.model_box)
        self.aspect = QComboBox()
        for a in media.ASPECTS:
            self.aspect.addItem(tr("img.aspect." + a.replace(":", "_")), a)
        form.addRow(tr("img.aspect"), self.aspect)
        self.count = QSpinBox()
        self.count.setRange(1, 4)
        form.addRow(tr("img.count"), self.count)
        fl.addLayout(form)
        fl.addWidget(QLabel(tr("img.prompt")))
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText(tr("img.prompt_hint"))
        fl.addWidget(self.prompt, 2)
        fl.addWidget(QLabel(tr("img.negative")))
        self.negative = QPlainTextEdit()
        self.negative.setPlaceholderText(tr("img.negative_hint"))
        self.negative.setMaximumHeight(60)
        fl.addWidget(self.negative)
        ref_row = QHBoxLayout()
        self.ref_btn = QPushButton("🖼 " + tr("img.add_ref"))
        self.ref_btn.clicked.connect(self.add_reference_dialog)
        ref_row.addWidget(self.ref_btn)
        self.ref_label = QLabel()
        self.ref_label.setWordWrap(True)
        ref_row.addWidget(self.ref_label, 1)
        self.ref_clear = QToolButton(text="✕")
        self.ref_clear.setToolTip(tr("img.clear_refs"))
        self.ref_clear.clicked.connect(self.clear_references)
        ref_row.addWidget(self.ref_clear)
        fl.addLayout(ref_row)
        go_row = QHBoxLayout()
        self.go = QPushButton("✦ " + tr("img.generate"))
        self.go.setDefault(True)
        self.go.clicked.connect(self._go_or_stop)
        go_row.addWidget(self.go)
        go_row.addStretch()
        fl.addLayout(go_row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        fl.addWidget(self.status)
        hint = QLabel(tr("img.cost_hint"))
        hint.setWordWrap(True)
        hint.setEnabled(False)
        fl.addWidget(hint)
        split.addWidget(form_w)

        # --- Mitte: Galerie
        self.gallery = QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setIconSize(QSize(THUMB, THUMB))
        self.gallery.setGridSize(QSize(THUMB + 16, THUMB + 16))
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.gallery.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.gallery.customContextMenuRequested.connect(self._menu)
        self.gallery.currentItemChanged.connect(lambda cur, _prev: self._preview(cur))
        self.gallery.itemDoubleClicked.connect(lambda it: self._open(self._path(it)))
        split.addWidget(self.gallery)

        # --- rechts: Vorschau
        prev_w = QWidget()
        pl = QVBoxLayout(prev_w)
        pl.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel(tr("img.select"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(240, 240)
        pl.addWidget(self.preview, 1)
        self.meta = QLabel()
        self.meta.setWordWrap(True)
        self.meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pl.addWidget(self.meta)
        split.addWidget(prev_w)
        split.setSizes([320, 520, 360])
        self._current: Path | None = None
        self._update_refs()

    # --- Verbindungen ---------------------------------------------------------------------------------
    def refresh(self) -> None:
        store = self.services.connections
        conns = self.media.connections_for(store, "image")
        keep = self.services.default("image") or self.conn_box.currentData()
        self.conn_box.blockSignals(True)
        self.conn_box.clear()
        for c in conns:
            self.conn_box.addItem(c.name, c.id)
        idx = self.conn_box.findData(keep)
        self.conn_box.setCurrentIndex(max(0, idx))
        self.conn_box.blockSignals(False)
        self.stack.setCurrentIndex(1 if conns else 0)
        if conns:
            self._conn_changed()
        self.reload_gallery()

    def connection(self):
        cid = self.conn_box.currentData()
        return self.services.connections.get(cid) if cid else None

    def _conn_changed(self, *_):
        conn = self.connection()
        if conn is None:
            return
        self.services.set_default("image", conn.id)
        last = (self.studio.context.settings.get("image_models") or {}).get(conn.id, "")
        self.model_box.clear()
        for m in self.media.models(conn, "image"):
            self.model_box.addItem(m)
        if last:
            self.model_box.setCurrentText(last)
        self._update_refs()

    # --- Referenzbilder -------------------------------------------------------------------------------
    def add_reference_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, self.tr_("img.add_ref"), "",
                                                self.tr_("img.image_filter") + " (*.png *.jpg *.jpeg *.webp)")
        for f in files:
            self.add_reference(Path(f))

    def add_reference(self, path: Path) -> None:
        if len(self.refs) >= MAX_REFS:
            self.status.setText(self.tr_("img.too_many_refs", n=MAX_REFS))
            return
        try:
            data = path.read_bytes()
        except OSError as e:
            QMessageBox.warning(self, self.tr_("img.add_ref"), str(e))
            return
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        self.refs.append({"name": path.name, "mime": mime, "data": data})
        self._update_refs()

    def clear_references(self) -> None:
        self.refs = []
        self._update_refs()

    def _update_refs(self) -> None:
        conn = self.connection()
        ok = conn is not None and self.media.accepts_references(conn)
        self.ref_btn.setEnabled(ok)
        self.ref_btn.setToolTip("" if ok else self.tr_("img.no_refs"))
        names = ", ".join(r["name"] for r in self.refs)
        self.ref_label.setText(names if ok or not names else names + " · " + self.tr_("img.no_refs"))
        self.ref_clear.setVisible(bool(self.refs))

    # --- Erzeugen ------------------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._stop is not None

    def _go_or_stop(self) -> None:
        if self.running:
            self.stop()
        else:
            self.generate()

    def generate(self) -> bool:
        conn = self.connection()
        prompt = self.prompt.toPlainText().strip()
        if conn is None or not prompt:
            self.status.setText(self.tr_("img.need_prompt") if conn else self.tr_("img.no_bot"))
            return False
        media = self.media
        model = self.model_box.currentText().strip()
        models = dict(self.studio.context.settings.get("image_models") or {})
        models[conn.id] = model
        self.studio.context.settings.set("image_models", models)
        refs = [{"mime": r["mime"], "data": r["data"]} for r in self.refs] \
            if media.accepts_references(conn) else []
        req = media.Request(prompt=prompt, model=model, aspect=self.aspect.currentData(),
                            count=self.count.value(), references=refs,
                            negative=self.negative.toPlainText().strip())
        stop = self._stop = threading.Event()
        self.go.setText("■ " + self.tr_("img.stop"))
        self.status.setText(self.tr_("img.working", name=conn.name))
        store = self.services.connections
        storage = self.services.storage
        meta = {"prompt": prompt, "negative": req.negative, "model": model, "aspect": req.aspect,
                "connection": conn.id, "connection_name": conn.name, "provider": conn.provider,
                "references": [r["name"] for r in self.refs] if refs else []}

        def task(progress):
            from omniwrench.ai import chat
            from omniwrench.ai.http import Cancelled
            try:
                items = media.generate_image(store, conn, req, stop, progress)
                if stop.is_set():
                    return ("stopped", None)
                return ("ok", [str(media.save(storage, "image", m, dict(meta))) for m in items])
            except Cancelled:
                return ("stopped", None)
            except Exception as err:  # noqa: BLE001 - als Text anzeigen
                return ("error", chat.error_text(err))

        run_async(task, lambda res: self._done(stop, res), lambda text: self._done(stop, ("error", text)),
                  lambda state: self._progress(stop, state))
        return True

    def _progress(self, stop, state: str) -> None:
        if stop is self._stop and state:
            self.status.setText(self.tr_("img.waiting", state=state))

    def _done(self, stop, res) -> None:
        if stop is not self._stop:
            return
        self._stop = None
        self.go.setText("✦ " + self.tr_("img.generate"))
        kind, value = res
        if kind == "ok":
            self.status.setText(self.tr_("img.done", n=len(value)))
            self.reload_gallery(select=value[0] if value else "")
        elif kind == "stopped":
            self.status.setText(self.tr_("img.stopped"))
        else:
            self.status.setText("⚠ " + str(value))

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
            self._stop = None
            self.go.setText("✦ " + self.tr_("img.generate"))
            self.status.setText(self.tr_("img.stopped"))

    # --- Galerie -------------------------------------------------------------------------------------
    def reload_gallery(self, select: str = "") -> None:
        self.gallery.clear()
        for path in self.media.list_files(self.services.storage, "image"):
            item = QListWidgetItem(_thumb(path), "")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(self.media.read_meta(path).get("prompt", path.name))
            self.gallery.addItem(item)
            if select and str(path) == select:
                self.gallery.setCurrentItem(item)
        if not select and self.gallery.count() and self._current is None:
            self._preview(None)

    def _path(self, item) -> Path | None:
        return Path(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _selected(self) -> list[Path]:
        return [self._path(i) for i in self.gallery.selectedItems()]

    def _preview(self, item) -> None:
        path = self._path(item)
        self._current = path
        if path is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(self.tr_("img.select"))
            self.meta.setText("")
            return
        pix = QPixmap(str(path))
        if not pix.isNull():
            pix = pix.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pix)
        m = self.media.read_meta(path)
        lines = []
        if m.get("prompt"):
            lines.append(m["prompt"])
        info = " · ".join(x for x in (m.get("connection_name"), m.get("model"), m.get("aspect")) if x)
        if info:
            lines.append(info)
        if m.get("revised_prompt"):
            lines.append(self.tr_("img.revised", text=m["revised_prompt"]))
        lines.append(path.name)
        self.meta.setText("\n\n".join(lines))

    def _menu(self, pos) -> None:
        paths = self._selected()
        if not paths:
            return
        tr = self.tr_
        menu = QMenu(self)
        first = paths[0]
        menu.addAction(tr("img.open"), lambda: self._open(first))
        menu.addAction(tr("img.reveal"), lambda: self._open(first.parent))
        menu.addAction(tr("img.copy"), lambda: QGuiApplication.clipboard().setImage(QImage(str(first))))
        menu.addSeparator()
        menu.addAction(tr("img.reuse"), lambda: self.reuse(first))
        menu.addAction(tr("img.as_ref"), lambda: [self.add_reference(p) for p in paths])
        menu.addAction(tr("img.to_chat"), lambda: [self.to_chat.emit(str(p)) for p in paths])
        menu.addSeparator()
        menu.addAction(tr("img.delete"), lambda: self.delete(paths))
        menu.exec(self.gallery.viewport().mapToGlobal(pos))

    def _open(self, path: Path | None) -> None:
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def reuse(self, path: Path) -> None:
        m = self.media.read_meta(path)
        self.prompt.setPlainText(m.get("prompt", ""))
        self.negative.setPlainText(m.get("negative", ""))
        idx = self.conn_box.findData(m.get("connection", ""))
        if idx >= 0:
            self.conn_box.setCurrentIndex(idx)
        if m.get("model"):
            self.model_box.setCurrentText(m["model"])
        a = self.aspect.findData(m.get("aspect", ""))
        if a >= 0:
            self.aspect.setCurrentIndex(a)

    def delete(self, paths: list[Path]) -> None:
        if QMessageBox.question(self, self.tr_("img.delete"), self.tr_("img.delete_q", n=len(paths))) \
                != QMessageBox.StandardButton.Yes:
            return
        for p in paths:
            for f in (p, p.with_suffix(p.suffix + ".json")):
                try:
                    f.unlink()
                except OSError:
                    pass
        self._current = None
        self.reload_gallery()
        self._preview(None)


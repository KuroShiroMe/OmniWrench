"""Reiter „Dokumente“: Anleitungen, Berichte, Konzepte … mit dem Assistenten schreiben und exportieren.

Dokumente sind Markdown-Dateien im Dokumente-Ordner der KI-Datenablage (unverschlüsselt, zum Weitergeben).
Export als HTML, PDF und ODT (über Qt, ohne Zusatzpakete). Was an den Assistenten geht, wird nach der
Einstellung „KI-Zugriff“ des Tools verfremdet.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QTextDocument, QTextDocumentWriter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QStackedWidget,
    QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

from omniwrench.sdk import run_async

from .images import NoBotPage

DOC_TYPES = ("guide", "report", "concept", "minutes", "email", "free")


def ask_once(services, tool_id: str, conn, system: str, text: str, on_text, stop: threading.Event):
    """Eine Frage ohne Funktionen. Gibt (Antwort, decode) zurück; on_text bekommt verfremdeten Teiltext."""
    from omniwrench.ai import access, adapters
    from omniwrench.ai.pseudo import Pseudonymizer
    pseudo = Pseudonymizer({}, access.pseudo_kinds(services.settings),
                           enabled=access.pseudo_enabled(services.settings, tool_id))
    adapter = adapters.for_connection(services.connections, conn)
    result = adapter.chat(system, [{"role": "user", "content": pseudo.encode(text)}], [],
                          lambda kind, data: on_text(data, pseudo.decode) if kind == "text" else None, stop, {})
    return pseudo.decode(result.get("text") or ""), pseudo.decode


def safe_name(title: str) -> str:
    name = re.sub(r"[^\w\-. ]+", "_", title).strip(" ._")[:80]
    return name or time.strftime("Dokument %Y-%m-%d %H%M")


class WriteDialog(QDialog):
    def __init__(self, tr, revise: bool, has_text: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("doc.revise") if revise else tr("doc.write"))
        self.resize(560, 320)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        if not revise:
            for k in DOC_TYPES:
                self.kind.addItem(tr("doc.type." + k), k)
            form.addRow(tr("doc.type"), self.kind)
        lay.addLayout(form)
        lay.addWidget(QLabel(tr("doc.revise_what") if revise else tr("doc.write_what")))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText(tr("doc.revise_hint") if revise else tr("doc.write_hint"))
        lay.addWidget(self.text, 1)
        self.use_text = QCheckBox(tr("doc.use_existing"))
        self.use_text.setChecked(has_text)
        self.use_text.setVisible(not revise and has_text)
        lay.addWidget(self.use_text)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)


class _Bridge(QObject):
    text = Signal(str)
    done = Signal(object)


class DocumentsTab(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.services = studio.services
        tr = self.tr_ = studio.tr
        self.path: Path | None = None
        self._stop: threading.Event | None = None
        self._buffer = ""
        self._decode = lambda t: t
        self._target: tuple[int, int] | None = None     # Bereich, der ersetzt wird (Überarbeiten)
        self.bridge = _Bridge()
        self.bridge.text.connect(self._on_text)
        self.bridge.done.connect(self._on_done)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.stack.addWidget(NoBotPage(tr("grp.no_bot"), tr("ui.open_ai_options"), self.services.open_options))
        page = QWidget()
        self.stack.addWidget(page)
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(split)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        new = QPushButton("＋ " + tr("doc.new"))
        new.clicked.connect(self.new_doc)
        sl.addWidget(new)
        self.list = QListWidget()
        self.list.itemClicked.connect(lambda it: self.open_doc(Path(it.data(Qt.ItemDataRole.UserRole))))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        sl.addWidget(self.list, 1)
        split.addWidget(side)

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.title = QLineEdit()
        self.title.setPlaceholderText(tr("doc.title"))
        bar.addWidget(self.title, 2)
        self.conn_box = QComboBox()
        bar.addWidget(self.conn_box, 1)
        self.write_btn = QPushButton("✦ " + tr("doc.write"))
        self.write_btn.clicked.connect(lambda: self.ask(False))
        bar.addWidget(self.write_btn)
        self.revise_btn = QPushButton("✎ " + tr("doc.revise"))
        self.revise_btn.clicked.connect(lambda: self.ask(True))
        bar.addWidget(self.revise_btn)
        save = QPushButton(tr("doc.save"))
        save.clicked.connect(self.save)
        bar.addWidget(save)
        export = QToolButton(text=tr("doc.export") + " ▾")
        export.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(export)
        for fmt in ("html", "pdf", "odt"):
            menu.addAction(fmt.upper(), lambda f=fmt: self.export(f))
        menu.addAction(tr("doc.to_chat"), self.to_chat)
        export.setMenu(menu)
        bar.addWidget(export)
        ml.addLayout(bar)
        edit_split = QSplitter(Qt.Orientation.Horizontal)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(tr("doc.editor_hint"))
        self.editor.textChanged.connect(lambda: self._preview_timer.start())
        edit_split.addWidget(self.editor)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        edit_split.addWidget(self.preview)
        ml.addWidget(edit_split, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        ml.addWidget(self.status)
        split.addWidget(main)
        split.setSizes([220, 980])
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(lambda: self.preview.setMarkdown(self.editor.toPlainText()))

    # --- Verwaltung ----------------------------------------------------------------------------------
    def folder(self) -> Path:
        return self.services.storage.ensure("documents")

    def refresh(self) -> None:
        conns = [c for c in self.services.connections.chat_connections() if not (c.info and c.info.removed)]
        keep = self.conn_box.currentData() or self.studio.context.settings.get("doc_connection") or \
            self.services.connections.primary_id()
        self.conn_box.clear()
        for c in conns:
            self.conn_box.addItem(c.name, c.id)
        self.conn_box.setCurrentIndex(max(0, self.conn_box.findData(keep)))
        self.stack.setCurrentIndex(1 if conns else 0)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        try:
            files = sorted(self.folder().glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            files = []
        for p in files:
            item = QListWidgetItem(p.stem)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.list.addItem(item)
            if self.path is not None and p == self.path:
                item.setSelected(True)

    def new_doc(self) -> None:
        if self.running:
            return
        self._autosave()
        self.path = None
        self.title.clear()
        self.editor.clear()
        self.status.setText("")

    def open_doc(self, path: Path) -> None:
        if self.running or path == self.path:
            return
        self._autosave()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            self.status.setText("⚠ " + str(e))
            return
        self.path = path
        self.title.setText(path.stem)
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self.status.setText("")

    def _autosave(self) -> None:
        if self.editor.document().isModified() and self.editor.toPlainText().strip():
            self.save()

    def save(self) -> Path | None:
        text = self.editor.toPlainText()
        title = self.title.text().strip() or (text.strip().splitlines()[0].lstrip("# ").strip() if text.strip() else "")
        target = self.folder() / (safe_name(title) + ".md")
        if self.path is not None and self.path != target and target.exists():
            target = self.path       # Name belegt: unter altem Namen speichern
        try:
            target.write_text(text, encoding="utf-8")
            if self.path is not None and self.path != target and self.path.exists():
                self.path.unlink()
        except OSError as e:
            self.status.setText("⚠ " + str(e))
            return None
        self.path = target
        self.title.setText(target.stem)
        self.editor.document().setModified(False)
        self.status.setText(self.tr_("doc.saved", name=target.name))
        self.reload()
        return target

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        tr = self.tr_
        menu = QMenu(self)
        menu.addAction(tr("img.reveal"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))))
        menu.addAction(tr("img.delete"), lambda: self.delete(path))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def delete(self, path: Path) -> None:
        if QMessageBox.question(self, self.tr_("img.delete"), self.tr_("media.delete_q", name=path.name)) \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            path.unlink()
        except OSError:
            pass
        if path == self.path:
            self.path = None
            self.editor.clear()
            self.title.clear()
        self.reload()

    # --- Assistent -----------------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._stop is not None

    def ask(self, revise: bool, request: str = "", kind: str = "free", use_existing: bool | None = None) -> bool:
        if self.running:
            self.stop()
            return False
        tr = self.tr_
        cursor = self.editor.textCursor()
        whole = self.editor.toPlainText()
        if not request:
            dlg = WriteDialog(tr, revise, bool(whole.strip()), self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return False
            request = dlg.text.toPlainText().strip()
            kind = dlg.kind.currentData() or "free"
            use_existing = dlg.use_text.isChecked()
        if not request:
            return False
        conn = self.services.connections.get(self.conn_box.currentData() or "")
        if conn is None:
            return False
        self.studio.context.settings.set("doc_connection", conn.id)
        system = ("You write documents for system administrators inside OmniWrench. Write in the user's language, "
                  "formally and neutrally, as clean Markdown with headings, lists and code blocks where useful. "
                  "Answer with the document text only, without any introduction or closing remarks.")
        if revise:
            if cursor.hasSelection():
                self._target = (cursor.selectionStart(), cursor.selectionEnd())
                part = cursor.selectedText().replace(" ", "\n")
            else:
                self._target = (0, len(whole))
                part = whole
            text = f"Revise the following text. Instruction: {request}\n\n---\n{part}"
        else:
            self._target = (0, len(whole)) if use_existing or not whole.strip() else (len(whole), len(whole))
            text = f"Document type: {tr('doc.type.' + kind)}\nTask: {request}"
            if use_existing and whole.strip():
                text += f"\n\nUse and extend this existing draft:\n---\n{whole}"
        stop = self._stop = threading.Event()
        self._buffer = ""
        self._backup = whole
        self.write_btn.setText("■ " + tr("img.stop"))
        self.revise_btn.setEnabled(False)
        self.editor.setReadOnly(True)
        self.status.setText(tr("doc.working", name=conn.name))
        b = self.bridge
        tool_id = self.studio.context.manifest.id

        def on_text(delta, decode):
            if not stop.is_set():
                self._decode = decode
                b.text.emit(delta)

        def task():
            from omniwrench.ai import chat
            try:
                answer, _dec = ask_once(self.services, tool_id, conn, system, text, on_text, stop)
                b.done.emit(("ok", answer, stop))
            except Exception as err:  # noqa: BLE001 - als Text anzeigen
                b.done.emit(("error", chat.error_text(err), stop))

        run_async(task)
        return True

    def _replace(self, new: str) -> None:
        start, end = self._target or (0, 0)
        base = self._backup
        self.editor.blockSignals(True)
        self.editor.setPlainText(base[:start] + new + base[end:])
        self.editor.blockSignals(False)
        self._preview_timer.start()

    def _on_text(self, delta: str) -> None:
        if not self.running:
            return
        self._buffer += delta
        self._replace(self._decode(self._buffer))

    def _on_done(self, res) -> None:
        kind, value, stop = res
        if stop is not self._stop:
            return
        self._finish()
        if kind == "ok":
            answer = value.strip()
            if answer.startswith("```") and answer.endswith("```"):
                answer = answer.strip("`").split("\n", 1)[-1].rsplit("\n", 1)[0]
            self._replace(answer + ("\n" if self._target and self._target[1] < len(self._backup) else ""))
            self.editor.document().setModified(True)
            if not self.title.text().strip():
                first = next((ln for ln in answer.splitlines() if ln.strip()), "")
                self.title.setText(first.lstrip("# ").strip()[:80])
            self.save()
        else:
            self._replace(self._backup[self._target[0]:self._target[1]] if self._target else "")
            self.status.setText("⚠ " + str(value))

    def _finish(self) -> None:
        self._stop = None
        self.write_btn.setText("✦ " + self.tr_("doc.write"))
        self.revise_btn.setEnabled(True)
        self.editor.setReadOnly(False)

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
            self._finish()
            self.status.setText(self.tr_("img.stopped"))

    # --- Export --------------------------------------------------------------------------------------
    def _document(self) -> QTextDocument:
        doc = QTextDocument()
        doc.setMarkdown(self.editor.toPlainText())
        return doc

    def export(self, fmt: str, target: str = "") -> str:
        src = self.save() if self.editor.toPlainText().strip() else None
        if src is None:
            return ""
        if not target:
            target, _ = QFileDialog.getSaveFileName(self, self.tr_("doc.export"), str(src.with_suffix("." + fmt)),
                                                    f"{fmt.upper()} (*.{fmt})")
            if not target:
                return ""
        doc = self._document()
        try:
            if fmt == "html":
                Path(target).write_text(doc.toHtml(), encoding="utf-8")
            elif fmt == "odt":
                writer = QTextDocumentWriter(target, b"odf")
                if not writer.write(doc):
                    raise OSError("ODT")
            else:
                from PySide6.QtPrintSupport import QPrinter
                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(target)
                doc.print_(printer)
        except Exception as e:  # noqa: BLE001
            self.status.setText("⚠ " + str(e))
            return ""
        self.status.setText(self.tr_("doc.exported", name=Path(target).name))
        return target

    def to_chat(self) -> None:
        if self.editor.toPlainText().strip():
            self.studio.panel.add_text_attachment((self.title.text().strip() or "Dokument") + ".md",
                                                  self.editor.toPlainText()[:100_000])
            self.studio.modes.setCurrentIndex(0)
            self.studio.panel.focus_input()

    def shutdown(self) -> None:
        self.stop()
        self._autosave()

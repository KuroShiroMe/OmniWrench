"""Vorlagen für wiederkehrende Fragen (Seitenleiste „Vorlagen“ im Chat).

Mitgelieferte Vorlagen stehen in den Sprachdateien (tpl.<id>.name/.text), eigene in der Tool-Einstellung
"templates": [{"id", "name", "text"}]. Platzhalter {{Name}} fragt ein Dialog beim Verwenden ab.
"""

from __future__ import annotations

import re
import secrets

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

BUILTIN = ("explain_script", "review_script", "write_ps", "analyze_log", "error_msg", "user_mail", "change_log",
           "runbook")
PLACEHOLDER = re.compile(r"\{\{\s*([^{}]{1,40}?)\s*\}\}")


def placeholders(text: str) -> list[str]:
    seen: list[str] = []
    for m in PLACEHOLDER.finditer(text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def fill(text: str, values: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1).strip(), m.group(0)), text)


def all_templates(tr, settings) -> list[dict]:
    out = [{"id": b, "name": tr(f"tpl.{b}.name"), "text": tr(f"tpl.{b}.text"), "builtin": True} for b in BUILTIN]
    for t in settings.get("templates") or []:
        if isinstance(t, dict) and t.get("text"):
            out.append({"id": t.get("id") or secrets.token_hex(3), "name": t.get("name") or "?",
                        "text": t["text"], "builtin": False})
    return out


class TemplateDialog(QDialog):
    def __init__(self, tr, template: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("tpl.edit") if template else tr("tpl.new"))
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit((template or {}).get("name", ""))
        form.addRow(tr("tpl.name"), self.name)
        lay.addLayout(form)
        hint = QLabel(tr("tpl.placeholder_hint"))
        hint.setWordWrap(True)
        hint.setEnabled(False)
        lay.addWidget(hint)
        self.text = QPlainTextEdit((template or {}).get("text", ""))
        lay.addWidget(self.text, 1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._ok)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _ok(self) -> None:
        if self.name.text().strip() and self.text.toPlainText().strip():
            self.accept()


class FillDialog(QDialog):
    """Fragt die Platzhalter einer Vorlage ab."""

    def __init__(self, tr, template: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(template["name"])
        self.resize(560, 300)
        self.template = template
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.fields: dict[str, QPlainTextEdit] = {}
        for name in placeholders(template["text"]):
            edit = QPlainTextEdit()
            edit.setMinimumHeight(70)
            form.addRow(name + ":", edit)
            self.fields[name] = edit
        lay.addLayout(form, 1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def text(self) -> str:
        return fill(self.template["text"], {k: e.toPlainText().strip() for k, e in self.fields.items()})


class TemplatesPanel(QWidget):
    use = Signal(str)            # fertiger Text für die Eingabe des Chats

    def __init__(self, tr, settings):
        super().__init__()
        self.tr_ = tr
        self.settings = settings
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        add = QPushButton("＋ " + tr("tpl.new"))
        add.clicked.connect(self.new)
        row.addWidget(add)
        row.addStretch()
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda it: self.apply(it.data(Qt.ItemDataRole.UserRole)))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list, 1)
        hint = QLabel(tr("tpl.hint"))
        hint.setWordWrap(True)
        hint.setEnabled(False)
        lay.addWidget(hint)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        for t in all_templates(self.tr_, self.settings):
            item = QListWidgetItem(("📌 " if t["builtin"] else "✎ ") + t["name"])
            item.setData(Qt.ItemDataRole.UserRole, t)
            item.setToolTip(t["text"][:400])
            self.list.addItem(item)

    def apply(self, t: dict) -> None:
        if placeholders(t["text"]):
            dlg = FillDialog(self.tr_, t, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            self.use.emit(dlg.text())
        else:
            self.use.emit(t["text"])

    def _own(self) -> list[dict]:
        return [dict(t) for t in self.settings.get("templates") or [] if isinstance(t, dict)]

    def new(self, base: dict | None = None) -> None:
        dlg = TemplateDialog(self.tr_, base, self)
        if base:
            dlg.setWindowTitle(self.tr_("tpl.new"))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        own = self._own()
        own.append({"id": secrets.token_hex(3), "name": dlg.name.text().strip(), "text": dlg.text.toPlainText()})
        self.settings.set("templates", own)
        self.reload()

    def edit(self, t: dict) -> None:
        dlg = TemplateDialog(self.tr_, t, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        own = self._own()
        for o in own:
            if o.get("id") == t["id"]:
                o.update(name=dlg.name.text().strip(), text=dlg.text.toPlainText())
        self.settings.set("templates", own)
        self.reload()

    def delete(self, t: dict) -> None:
        if QMessageBox.question(self, self.tr_("tpl.delete"), self.tr_("tpl.delete_q", name=t["name"])) \
                != QMessageBox.StandardButton.Yes:
            return
        self.settings.set("templates", [o for o in self._own() if o.get("id") != t["id"]])
        self.reload()

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        t = item.data(Qt.ItemDataRole.UserRole)
        tr = self.tr_
        menu = QMenu(self)
        menu.addAction(tr("tpl.use"), lambda: self.apply(t))
        menu.addAction(tr("tpl.copy"), lambda: self.new({"name": t["name"] + " (2)", "text": t["text"]}))
        if not t["builtin"]:
            menu.addAction(tr("tpl.edit"), lambda: self.edit(t))
            menu.addAction(tr("tpl.delete"), lambda: self.delete(t))
        menu.exec(self.list.viewport().mapToGlobal(pos))

"""Oberfläche des Passwortmanagers.

* PasswordManagerWidget  - Verwaltung (Tab in den Einstellungen, eigener Dialog über Extras)
* CredentialPickerDialog - Auswahl eines Eintrags ("Aus Passwortmanager")
* CredentialField        - Eingabefeld Benutzer + Passwort + Button zum Übernehmen aus dem Manager.
                           Wird in Tool-Einstellungen vom Typ "credential" verwendet und steht
                           Tool-Entwicklern über omniwrench.sdk zur Verfügung.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.core import credentials
from omniwrench.core.credentials import Credential
from omniwrench.core.i18n import tr

from .widgets import label, library_icon, make_button

CLIPBOARD_CLEAR_SECONDS = 30


def copy_secret(text: str, notify=None) -> None:
    """Kopiert in die Zwischenablage und leert sie nach 30 s wieder (falls unverändert)."""
    clipboard = QApplication.clipboard()
    clipboard.setText(text)
    QTimer.singleShot(CLIPBOARD_CLEAR_SECONDS * 1000,
                      lambda: clipboard.text() == text and clipboard.clear())
    if notify:
        notify(tr("pwm.copied", seconds=CLIPBOARD_CLEAR_SECONDS))


class PasswordEdit(QWidget):
    """Passwortfeld mit Anzeigen-Knopf und optionalem Generator."""

    textEdited = Signal(str)

    def __init__(self, text: str = "", placeholder: str = "", generator: bool = False, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.edit = QLineEdit(text)
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText(placeholder or tr("settings.password_placeholder"))
        self.edit.textEdited.connect(self.textEdited)
        lay.addWidget(self.edit, 1)
        eye = make_button("")
        eye.setIcon(library_icon("eye", 16))
        eye.setCheckable(True)
        eye.setFixedWidth(34)
        eye.setToolTip(tr("settings.show_password"))
        eye.toggled.connect(lambda on: self.edit.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        lay.addWidget(eye)
        if generator:
            gen = make_button("")
            gen.setIcon(library_icon("dices", 16))
            gen.setFixedWidth(34)
            gen.setToolTip(tr("pwm.generate"))
            gen.clicked.connect(self._generate)
            lay.addWidget(gen)

    def _generate(self) -> None:
        self.edit.setText(credentials.generate_password())
        self.edit.setEchoMode(QLineEdit.EchoMode.Normal)
        self.textEdited.emit(self.edit.text())

    def text(self) -> str:
        return self.edit.text()

    def setText(self, text: str) -> None:  # noqa: N802
        self.edit.setText(text)


class CredentialEditDialog(QDialog):
    def __init__(self, parent=None, cred: Credential | None = None, username: str = "", password: str = ""):
        super().__init__(parent)
        self.cred = cred
        self.setWindowTitle(tr("pwm.edit_title") if cred else tr("pwm.new_title"))
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(cred.name if cred else "")
        self.name.setPlaceholderText(tr("pwm.name_placeholder"))
        self.user = QLineEdit(cred.username if cred else username)
        self.user.setPlaceholderText(tr("settings.username_placeholder"))
        self.pw = PasswordEdit(cred.password if cred else password, generator=True)
        form.addRow(tr("pwm.name"), self.name)
        form.addRow(tr("pwm.username"), self.user)
        form.addRow(tr("pwm.password"), self.pw)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _save(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, self.windowTitle(), tr("pwm.name_required"))
            return
        local = credentials.manager().local
        if self.cred:
            self.cred.name, self.cred.username, self.cred.password = \
                self.name.text().strip(), self.user.text().strip(), self.pw.text()
            local.update(self.cred)
        else:
            self.cred = local.add(self.name.text(), self.user.text(), self.pw.text())
        self.accept()


class PasswordManagerWidget(QWidget):
    """Liste aller Einträge mit Neu/Bearbeiten/Löschen/Kopieren."""

    def __init__(self, parent=None, notify=None):
        super().__init__(parent)
        self.notify = notify
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(label(tr("pwm.hint"), "Muted", wrap=True))
        self.search = QLineEdit(placeholderText="🔍  " + tr("pwm.search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        lay.addWidget(self.search)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("pwm.name"), tr("pwm.username")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda *_: self._edit())
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(make_button(tr("common.add"), primary=True, on_click=self._add))
        row.addWidget(make_button(tr("pwm.edit"), on_click=self._edit))
        row.addWidget(make_button(tr("common.remove"), danger=True, on_click=self._delete))
        row.addStretch()
        row.addWidget(make_button(tr("pwm.copy_user"), on_click=lambda: self._copy("username")))
        row.addWidget(make_button(tr("pwm.copy_password"), on_click=lambda: self._copy("password")))
        lay.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        q = self.search.text().strip().lower()
        items = [c for c in credentials.manager().local.list() if q in (c.name + " " + c.username).lower()]
        self.table.setRowCount(len(items))
        for r, c in enumerate(items):
            name = QTableWidgetItem(c.name)
            name.setData(Qt.ItemDataRole.UserRole, c.id)
            name.setIcon(library_icon("key-round", 16))
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, QTableWidgetItem(c.username))

    def _selected(self) -> Credential | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        return credentials.manager().local.get(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))

    def _add(self) -> None:
        if CredentialEditDialog(self).exec():
            self.refresh()

    def _edit(self) -> None:
        cred = self._selected()
        if cred and CredentialEditDialog(self, cred).exec():
            self.refresh()

    def _delete(self) -> None:
        cred = self._selected()
        if cred and QMessageBox.question(self, tr("common.remove"), tr("pwm.delete_confirm", name=cred.name)) \
                == QMessageBox.StandardButton.Yes:
            credentials.manager().local.delete(cred.id)
            self.refresh()

    def _copy(self, attr: str) -> None:
        cred = self._selected()
        if cred:
            copy_secret(getattr(cred, attr), self.notify)


class PasswordManagerDialog(QDialog):
    def __init__(self, parent=None, notify=None):
        super().__init__(parent)
        self.setWindowTitle(tr("pwm.title"))
        self.resize(640, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(PasswordManagerWidget(self, notify), 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


class CredentialPickerDialog(QDialog):
    """Auswahl eines Eintrags aus allen Anbietern; "Neu …" legt direkt einen an."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected: Credential | None = None
        self.setWindowTitle(tr("pwm.pick_title"))
        self.resize(520, 400)
        lay = QVBoxLayout(self)
        self.search = QLineEdit(placeholderText="🔍  " + tr("pwm.search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        lay.addWidget(self.search)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("pwm.name"), tr("pwm.username")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda *_: self._accept())
        lay.addWidget(self.table, 1)
        self.empty = label(tr("pwm.empty"), "Muted", wrap=True)
        lay.addWidget(self.empty)
        row = QHBoxLayout()
        row.addWidget(make_button(tr("pwm.new"), on_click=self._new))
        row.addStretch()
        row.addWidget(make_button(tr("pwm.use"), primary=True, on_click=self._accept))
        cancel = make_button(tr("pwm.cancel"), on_click=self.reject)
        row.addWidget(cancel)
        lay.addLayout(row)
        self._items: list[Credential] = []
        self.refresh()
        self.search.setFocus()

    def refresh(self) -> None:
        q = self.search.text().strip().lower()
        self._items = [c for c in credentials.manager().all() if q in (c.name + " " + c.username).lower()]
        self.table.setRowCount(len(self._items))
        for r, c in enumerate(self._items):
            name = QTableWidgetItem(c.name)
            name.setIcon(library_icon("key-round", 16))
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, QTableWidgetItem(c.username))
        if self._items:
            self.table.selectRow(0)
        self.empty.setVisible(not credentials.manager().all())

    def _new(self) -> None:
        dlg = CredentialEditDialog(self)
        if dlg.exec():
            self.selected = dlg.cred
            self.accept()

    def _accept(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._items):
            self.selected = self._items[row]
            self.accept()


def pick_credential(parent: QWidget | None = None) -> Credential | None:
    """Öffnet den Auswahldialog und liefert den gewählten Eintrag (oder None)."""
    dlg = CredentialPickerDialog(parent)
    return dlg.selected if dlg.exec() else None


class CredentialField(QWidget):
    """Benutzer + Passwort mit Button "Aus Passwortmanager".

    Wird ein Eintrag übernommen, bleibt er verknüpft: Ändert sich das Passwort im Manager,
    gilt automatisch das neue. Tippt man selbst etwas, wird die Verknüpfung gelöst.

    value() -> {"username": …, "password": …}  bzw. zusätzlich {"ref": "local:<id>"} bei Verknüpfung
    """

    changed = Signal()

    def __init__(self, value: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.user = QLineEdit()
        self.user.setPlaceholderText(tr("settings.username_placeholder"))
        self.user.textEdited.connect(self._unlink)
        row.addWidget(self.user, 1)
        self.pick_btn = make_button("", on_click=self._pick)
        self.pick_btn.setIcon(library_icon("key-round", 16))
        self.pick_btn.setToolTip(tr("pwm.pick_button"))
        self.pick_btn.setFixedWidth(34)
        row.addWidget(self.pick_btn)
        lay.addLayout(row)
        self.pw = PasswordEdit()
        self.pw.textEdited.connect(self._unlink)
        lay.addWidget(self.pw)
        self.link_label = label("", "Muted")
        self.link_label.hide()
        lay.addWidget(self.link_label)
        self._ref = ""
        self.set_value(value or {})

    def set_value(self, value: dict) -> None:
        self._ref = value.get("ref", "")
        cred = credentials.manager().resolve(self._ref) if self._ref else None
        if self._ref and cred is None:
            self._ref = ""  # Eintrag wurde im Manager gelöscht
        self.user.setText(cred.username if cred else value.get("username", ""))
        self.pw.setText(cred.password if cred else value.get("password", ""))
        self._show_link(cred)

    def value(self) -> dict:
        result = {"username": self.user.text(), "password": self.pw.text()}
        if self._ref:
            result["ref"] = self._ref
        return result

    def _show_link(self, cred: Credential | None) -> None:
        self.link_label.setVisible(cred is not None)
        if cred:
            self.link_label.setText("🔗 " + tr("pwm.linked", name=cred.name))

    def _pick(self) -> None:
        cred = pick_credential(self)
        if cred:
            self._ref = cred.ref
            self.user.setText(cred.username)
            self.pw.setText(cred.password)
            self._show_link(cred)
            self.changed.emit()

    def _unlink(self, *_):
        if self._ref:
            self._ref = ""
            self._show_link(None)
        self.changed.emit()

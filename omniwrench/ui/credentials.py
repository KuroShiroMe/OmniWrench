"""Oberfläche des Passwortmanagers.

* PasswordManagerWidget  - Verwaltung des eingebauten Managers (Einstellungen, Extras)
* CredentialPickerDialog - Volltextsuche über alle verbundenen Manager
* CredentialField        - mehrere hinterlegte Zugangsdaten mit Auswahlliste; gespeichert werden
                           nur Verweise, Passwörter werden erst beim Gebrauch abgerufen.
                           Wird in Tool-Einstellungen vom Typ "credential" verwendet und steht
                           Tool-Entwicklern über omniwrench.sdk.CredentialField zur Verfügung.
* ProviderLoginDialog    - Rückfrage, wenn ein Manager (neue) Zugangsdaten braucht
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView,
    QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.core import credentials
from omniwrench.core.credentials import Credential, CredentialProvider
from omniwrench.core.i18n import tr

from .widgets import label, library_icon, make_button
from .workers import run_async

CLIPBOARD_CLEAR_SECONDS = 30
SEARCH_DELAY_MS = 300


def copy_secret(text: str, notify=None) -> None:
    """Kopiert in die Zwischenablage und leert sie nach 30 s wieder (falls unverändert)."""
    clipboard = QApplication.clipboard()
    clipboard.setText(text)
    QTimer.singleShot(CLIPBOARD_CLEAR_SECONDS * 1000,
                      lambda: clipboard.text() == text and clipboard.clear())
    if notify:
        notify(tr("pwm.copied", seconds=CLIPBOARD_CLEAR_SECONDS))


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().hide()
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    return table


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


# ============================================================ Eingebauter Manager
class CredentialEditDialog(QDialog):
    """Eintrag im eingebauten Manager anlegen/bearbeiten. store=False: nur Werte abfragen."""

    def __init__(self, parent=None, cred: Credential | None = None, store: bool = True, offer_store: bool = False):
        super().__init__(parent)
        self.cred = cred
        self.store = store
        self.setWindowTitle(tr("pwm.edit_title") if cred else tr("pwm.new_title"))
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(cred.name if cred else "")
        self.name.setPlaceholderText(tr("pwm.name_placeholder"))
        self.user = QLineEdit(cred.username if cred else "")
        self.user.setPlaceholderText(tr("settings.username_placeholder"))
        self.pw = PasswordEdit(cred.password if cred else "", generator=True)
        form.addRow(tr("pwm.name"), self.name)
        form.addRow(tr("pwm.username"), self.user)
        form.addRow(tr("pwm.password"), self.pw)
        lay.addLayout(form)
        self.store_check = QCheckBox(tr("pwm.also_store"))
        self.store_check.setVisible(offer_store)
        lay.addWidget(self.store_check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _save(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, self.windowTitle(), tr("pwm.name_required"))
            return
        local = credentials.manager().local
        if self.store or self.store_check.isChecked():
            if self.cred:
                self.cred.name, self.cred.username, self.cred.password = \
                    self.name.text().strip(), self.user.text().strip(), self.pw.text()
                local.update(self.cred)
            else:
                self.cred = local.add(self.name.text(), self.user.text(), self.pw.text())
        else:
            self.cred = Credential("", self.name.text().strip(), self.user.text().strip(), self.pw.text(), provider="")
        self.accept()


class PasswordManagerWidget(QWidget):
    """Liste des eingebauten Managers mit Neu/Bearbeiten/Löschen/Kopieren."""

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
        self.table = _table([tr("pwm.name"), tr("pwm.username")])
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
        items = credentials.manager().local.search(self.search.text())
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


# ================================================== Anmeldung an einem Manager
class ProviderLoginDialog(QDialog):
    """Fragt nach den Zugangsdaten eines Managers - statt einer Fehlermeldung."""

    def __init__(self, provider: CredentialProvider, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.setWindowTitle(tr("pwm.login_title", name=provider.name))
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr("pwm.login_text", name=provider.name), wrap=True))
        form = QFormLayout()
        self.inputs: dict[str, QWidget] = {}
        for f in provider.auth_fields():
            w = PasswordEdit() if f.secret else QLineEdit()
            self.inputs[f.key] = w
            form.addRow(f.label, w)
        lay.addLayout(form)
        self.save = QCheckBox(tr("pwm.login_save"))
        self.save.setChecked(True)
        lay.addWidget(self.save)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _ok(self) -> None:
        values = {k: w.text() for k, w in self.inputs.items()}
        self.provider.set_auth(values, self.save.isChecked())
        self.accept()


def ask_provider_login(provider: CredentialProvider) -> bool:
    if not provider.auth_fields():
        return False
    return bool(ProviderLoginDialog(provider, QApplication.activeWindow()).exec())


def install_auth_handler() -> None:
    credentials.manager().auth_handler = ask_provider_login


# ============================================================ Auswahl
class CredentialPickerDialog(QDialog):
    """Volltextsuche über alle Manager; "Neu …" legt direkt einen Eintrag im eingebauten an."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected: Credential | None = None
        self.setWindowTitle(tr("pwm.pick_title"))
        self.resize(640, 420)
        lay = QVBoxLayout(self)
        self.search = QLineEdit(placeholderText="🔍  " + tr("pwm.search_all"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: self._timer.start())
        lay.addWidget(self.search)
        self.table = _table([tr("pwm.name"), tr("pwm.username"), tr("pwm.source")])
        self.table.doubleClicked.connect(lambda *_: self._accept())
        lay.addWidget(self.table, 1)
        self.status = label("", "Muted", wrap=True)
        self.status.linkActivated.connect(self._login)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        row.addWidget(make_button(tr("pwm.new"), on_click=self._new))
        row.addStretch()
        row.addWidget(make_button(tr("pwm.use"), primary=True, on_click=self._accept))
        row.addWidget(make_button(tr("pwm.cancel"), on_click=self.reject))
        lay.addLayout(row)
        self._items: list[Credential] = []
        self._auth_needed: list[CredentialProvider] = []
        self._generation = 0
        self._timer = QTimer(self, singleShot=True, interval=SEARCH_DELAY_MS)
        self._timer.timeout.connect(self.refresh)
        self.refresh()
        self.search.setFocus()

    def refresh(self) -> None:
        self._generation += 1
        gen, query = self._generation, self.search.text()
        manager = credentials.manager()
        # Eingebauter Manager sofort, externe im Hintergrund (können langsam sein)
        local = manager.search(query, [manager.local])
        self._show(local.items, local, final=len(manager.providers) == 1)
        external = [p for p in manager.providers if p is not manager.local]
        if external:
            self.status.setText(tr("pwm.searching"))
            run_async(lambda: manager.search(query, external),
                      lambda res: gen == self._generation and self._show(local.items + res.items, res, final=True),
                      lambda err: self.status.setText(tr("common.error_short", error=err)))

    def _show(self, items: list[Credential], result, final: bool) -> None:
        self._items = items
        self.table.setRowCount(len(items))
        for r, c in enumerate(items):
            name = QTableWidgetItem(c.name)
            name.setIcon(library_icon("key-round", 16))
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, QTableWidgetItem(c.username))
            self.table.setItem(r, 2, QTableWidgetItem(c.source))
        if items and self.table.currentRow() < 0:
            self.table.selectRow(0)
        if not final:
            return
        self._auth_needed = result.auth_needed
        notes = [f"<a href='{i}'>{tr('pwm.login_link', name=p.name)}</a>" for i, p in enumerate(result.auth_needed)]
        notes += [f"⚠ {name}: {err[:120]}" for name, err in result.errors.items()]
        if not items and not notes:
            notes.append(tr("pwm.empty") if not self.search.text() else tr("common.no_results"))
        self.status.setText(" · ".join(notes))

    def _login(self, index: str) -> None:
        provider = self._auth_needed[int(index)]
        if ask_provider_login(provider):
            self.refresh()

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
    """Öffnet den Auswahldialog und liefert den gewählten Eintrag (Passwort ggf. noch nicht abgerufen)."""
    dlg = CredentialPickerDialog(parent)
    return dlg.selected if dlg.exec() else None


# ============================================================ Feld
class CredentialField(QWidget):
    """Mehrere hinterlegte Zugangsdaten mit Auswahlliste.

    [ Domänen-Admin Contoso — CONTOSO\\admin  ▼ ] [🔑] [+] [🗑]
      Quelle: Netwrix Password Secure

    * 🔑 übernimmt einen Eintrag aus einem Manager (gespeichert wird nur der Verweis)
    * +  legt Zugangsdaten manuell an (optional auch im eingebauten Manager)
    * Die Liste und die Auswahl werden gespeichert, Passwörter externer Manager nie.
    """

    changed = Signal()

    def __init__(self, value: dict | None = None, parent: QWidget | None = None, settings=None, key: str = ""):
        super().__init__(parent)
        self._settings, self._key = settings, key
        if settings is not None and key and value is None:
            value = settings.get(key)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(220)
        self.combo.currentIndexChanged.connect(self._selection_changed)
        row.addWidget(self.combo, 1)
        for icon, tip, slot in (("key-round", tr("pwm.pick_button"), self._pick),
                                ("plus", tr("pwm.add_manual"), self._add_manual),
                                ("trash-2", tr("pwm.remove_entry"), self._remove)):
            btn = make_button("", on_click=slot)
            btn.setIcon(library_icon(icon, 16))
            btn.setToolTip(tip)
            btn.setFixedWidth(34)
            row.addWidget(btn)
        lay.addLayout(row)
        self.info = label("", "Muted")
        lay.addWidget(self.info)
        self._items: list[dict] = []
        self.set_value(value)

    # ------------------------------------------------------------- Werte
    def set_value(self, value: dict | None) -> None:
        norm = credentials.normalize_value(value)
        self._items = norm["items"]
        self._fill(norm["selected"])

    def value(self) -> dict:
        return {"items": [dict(i) for i in self._items], "selected": max(self.combo.currentIndex(), 0)}

    def selected_item(self) -> dict | None:
        idx = self.combo.currentIndex()
        return self._items[idx] if 0 <= idx < len(self._items) else None

    def resolve(self) -> tuple[str, str] | None:
        """(Benutzer, Passwort) des gewählten Eintrags - externe Manager werden erst hier abgefragt."""
        item = self.selected_item()
        return credentials.resolve_item(item) if item else None

    # ------------------------------------------------------------- intern
    def _fill(self, selected: int) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        for item in self._items:
            text = item.get("name") or item.get("username") or "?"
            if item.get("username") and item.get("username") != text:
                text += f"  —  {item['username']}"
            self.combo.addItem(library_icon("key-round" if item.get("ref") else "pencil", 16), text)
        if not self._items:
            self.combo.addItem(tr("pwm.none_selected"))
            self.combo.setEnabled(False)
        else:
            self.combo.setEnabled(True)
            self.combo.setCurrentIndex(min(selected, len(self._items) - 1))
        self.combo.blockSignals(False)
        self._update_info()

    def _update_info(self) -> None:
        item = self.selected_item()
        if not item:
            self.info.setText("")
        elif item.get("ref"):
            provider = credentials.manager().provider(item["ref"].partition(":")[0])
            self.info.setText("🔗 " + tr("pwm.from_source", source=provider.name if provider else item["ref"]))
        else:
            self.info.setText("✎ " + tr("pwm.manual_entry"))

    def _selection_changed(self, _index: int) -> None:
        self._update_info()
        self._emit()

    def _emit(self) -> None:
        if self._settings is not None and self._key:
            self._settings.update({self._key: self.value()})
        self.changed.emit()

    def _append(self, item: dict) -> None:
        # gleicher Verweis nicht doppelt
        for i, existing in enumerate(self._items):
            if item.get("ref") and existing.get("ref") == item["ref"]:
                self._fill(i)
                self._emit()
                return
        self._items.append(item)
        self._fill(len(self._items) - 1)
        self._emit()

    def _pick(self) -> None:
        cred = pick_credential(self)
        if cred:
            self._append({"name": cred.name, "username": cred.username, "ref": cred.ref})

    def _add_manual(self) -> None:
        dlg = CredentialEditDialog(self, store=False, offer_store=True)
        if not dlg.exec():
            return
        c = dlg.cred
        if c.provider:  # wurde im eingebauten Manager gespeichert -> Verweis
            self._append({"name": c.name, "username": c.username, "ref": c.ref})
        else:
            self._append({"name": c.name, "username": c.username, "password": c.password})

    def _remove(self) -> None:
        idx = self.combo.currentIndex()
        if 0 <= idx < len(self._items):
            del self._items[idx]
            self._fill(max(idx - 1, 0))
            self._emit()

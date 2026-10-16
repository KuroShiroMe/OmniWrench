"""OmniVault: eingebauter Passwortmanager + Konnektoren zu externen Managern."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.core import credentials as core_credentials
from omniwrench.sdk import ToolBase, run_async
# Erstanbieter-Tool: nutzt Bausteine des Hauptprogramms direkt
from omniwrench.ui.credentials import PasswordEdit, PasswordManagerWidget, ask_provider_login, copy_secret
from omniwrench.ui.widgets import clear_layout, library_icon

from .connectors import ConnectorConfig, ConnectorStore, defaults, is_secret, is_visible, make_provider, register_all, text

ROLE_KIND = Qt.ItemDataRole.UserRole
ROLE_ID = Qt.ItemDataRole.UserRole + 1


class FieldInput:
    """Eingabefeld für eine Felddefinition aus connector_types.json."""

    def __init__(self, f: dict, value, lang: str, on_change):
        self.f = f
        placeholder = text(f.get("placeholder"), lang)
        kind = f.get("type", "string")
        if is_secret(f):
            self.widget = PasswordEdit(str(value or ""), placeholder)
            self.get = self.widget.text
        elif kind == "choice":
            self.widget = QComboBox()
            for opt in f.get("options", []):
                self.widget.addItem(text(opt.get("label"), lang) or str(opt["value"]), opt["value"])
            self.widget.setCurrentIndex(max(self.widget.findData(value), 0))
            self.widget.currentIndexChanged.connect(on_change)
            self.get = lambda: self.widget.currentData() or ""
        elif kind == "bool":
            self.widget = QCheckBox()
            self.widget.setChecked(bool(value))
            self.widget.toggled.connect(on_change)
            self.get = lambda: "1" if self.widget.isChecked() else ""
        elif kind in ("path_file", "path_dir"):
            self.widget = QWidget()
            h = QHBoxLayout(self.widget)
            h.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(str(value or ""))
            edit.setPlaceholderText(placeholder)
            btn = QPushButton()
            btn.setIcon(library_icon("folder-open", 16))
            btn.setFixedWidth(34)

            def browse():
                if kind == "path_dir":
                    path = QFileDialog.getExistingDirectory(self.widget, text(f["label"], lang), edit.text())
                else:
                    path, _ = QFileDialog.getOpenFileName(self.widget, text(f["label"], lang), edit.text())
                if path:
                    edit.setText(path)

            btn.clicked.connect(browse)
            h.addWidget(edit, 1)
            h.addWidget(btn)
            self.get = edit.text
        else:
            self.widget = QLineEdit(str(value or ""))
            self.widget.setPlaceholderText(placeholder)
            self.get = self.widget.text


class ConnectorDialog(QDialog):
    """Konnektor anlegen/bearbeiten. Die Art des Managers wird oben gewählt, die Felder
    passen sich an (Definitionen aus connector_types.json)."""

    def __init__(self, tool: "OmniVault", conn: ConnectorConfig | None):
        super().__init__(tool.root)
        self.tool = tool
        self.ctx = tool.context
        self.is_new = conn is None
        types = tool.store.types
        self.conn = conn or tool.store.new(next(iter(types)), "")
        tr = self.ctx.tr
        self.setWindowTitle(tr("dlg.title_new") if self.is_new else tr("dlg.title_edit"))
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)

        top = QFormLayout()
        self.type_combo = QComboBox()
        for type_id, spec in types.items():
            self.type_combo.addItem(library_icon(spec.get("icon", "plug"), 16), spec["name"], type_id)
        self.type_combo.setCurrentIndex(max(self.type_combo.findData(self.conn.type), 0))
        self.type_combo.setEnabled(self.is_new)  # Art eines bestehenden Konnektors bleibt fest
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        top.addRow(tr("dlg.type"), self.type_combo)
        self.name = QLineEdit(self.conn.name)
        self.name.setPlaceholderText(tr("dlg.name_placeholder"))
        top.addRow(tr("dlg.name"), self.name)
        self.enabled = QCheckBox(tr("dlg.enabled"))
        self.enabled.setChecked(self.conn.enabled)
        top.addRow("", self.enabled)
        lay.addLayout(top)

        self.desc = QLabel(wordWrap=True)
        self.desc.setObjectName("Muted")
        self.desc.setOpenExternalLinks(True)
        lay.addWidget(self.desc)

        self.fields_box = QWidget()
        self.form = QFormLayout(self.fields_box)
        self.form.setContentsMargins(0, 4, 0, 4)
        lay.addWidget(self.fields_box)

        self.save_auth = QCheckBox(tr("dlg.save_auth"))
        self.save_auth.setChecked(self.conn.save_auth)
        lay.addWidget(self.save_auth)
        hint = QLabel(tr("dlg.save_auth_hint"), wordWrap=True)
        hint.setObjectName("Muted")
        lay.addWidget(hint)

        self.status = QLabel(wordWrap=True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        test = QPushButton(tr("dlg.test"))
        test.clicked.connect(self._test)
        row.addWidget(test)
        row.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        lay.addLayout(row)

        self.inputs: dict[str, FieldInput] = {}
        self._values = tool.store.all_values(self.conn) if not self.is_new else {}
        self._build_fields()

    # ------------------------------------------------------------ Felder
    @property
    def spec(self) -> dict:
        return self.tool.store.types[self.type_combo.currentData()]

    def _current_values(self) -> dict:
        vals = {**defaults(self.spec), **self._values}
        vals.update({k: inp.get() for k, inp in self.inputs.items()})
        return vals

    def _build_fields(self) -> None:
        lang = self.ctx.language
        spec = self.spec
        desc = text(spec.get("description"), lang)
        if spec.get("docs"):
            desc += f" <a href='{spec['docs']}'>{self.ctx.tr('dlg.docs')}</a>"
        self.desc.setText(desc)
        values = self._current_values()
        while self.form.rowCount():
            self.form.removeRow(0)
        self.inputs = {}
        for f in spec["fields"]:
            inp = FieldInput(f, values.get(f["key"], ""), lang, self._refresh_visibility)
            self.inputs[f["key"]] = inp
            caption = ("🔑 " if f.get("auth") else "") + text(f["label"], lang) + (" *" if f.get("required") else "")
            self.form.addRow(caption, inp.widget)
        self._refresh_visibility()

    def _refresh_visibility(self, *_args) -> None:
        values = self._current_values()
        for key, inp in self.inputs.items():
            self.form.setRowVisible(inp.widget, is_visible(inp.f, values))

    def _type_changed(self) -> None:
        old_default = self.tool.store.types.get(self.conn.type, {}).get("name", "")
        if not self.name.text().strip() or self.name.text() == old_default:
            self.name.setText("")
        self.conn.type = self.type_combo.currentData()
        self._values = {}
        self._build_fields()
        self.status.setText("")

    def _missing_required(self) -> list[str]:
        values = self._current_values()
        return [text(f["label"], self.ctx.language) for f in self.spec["fields"]
                if f.get("required") and is_visible(f, values) and not str(values.get(f["key"], "")).strip()]

    # ------------------------------------------------------------ Aktionen
    def _collect(self) -> tuple[ConnectorConfig, dict[str, str]]:
        spec = self.spec
        conn = ConnectorConfig(self.conn.id, self.type_combo.currentData(), self.name.text().strip() or spec["name"],
                               self.enabled.isChecked(), self.save_auth.isChecked(), {})
        secrets = {}
        for f in spec["fields"]:
            (secrets if is_secret(f) else conn.values)[f["key"]] = self.inputs[f["key"]].get()
        return conn, secrets

    def _apply(self) -> ConnectorConfig:
        conn, secrets = self._collect()
        self.tool.store.save(conn)
        self.tool.store.set_secrets(conn, secrets, conn.save_auth)
        return conn

    def _ensure_modules(self) -> bool:
        """Fehlende PowerShell-Module (z. B. SecretManagement) zur Installation anbieten."""
        modules = self.spec.get("requirements", {}).get("powershell_modules", [])
        missing = [m for m in modules
                   if self.ctx.run_powershell(f"if (Get-Module -ListAvailable -Name '{m}') {{ 'ok' }}").stdout.strip() != "ok"]
        if not missing:
            return True
        if QMessageBox.question(self, self.windowTitle(), self.ctx.tr("dlg.install_modules", modules=", ".join(missing))) \
                != QMessageBox.StandardButton.Yes:
            return False
        self.status.setText(self.ctx.tr("dlg.installing"))
        QApplication.processEvents()
        for m in missing:
            res = self.ctx.run_powershell(
                "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;"
                f"Install-Module -Name '{m}' -Scope CurrentUser -Force -AllowClobber", timeout=900)
            if not res.ok:
                self.status.setText("❌ " + (res.stderr or res.stdout)[:300])
                return False
        self.status.setText("✅ " + self.ctx.tr("dlg.installed", modules=", ".join(missing)))
        return True

    def _test(self) -> None:
        missing = self._missing_required()
        if missing:
            self.status.setText("⚠ " + self.ctx.tr("dlg.missing", fields=", ".join(missing)))
            return
        if not self._ensure_modules():
            return
        conn, secrets = self._collect()
        provider = make_provider(conn, self.tool.store)
        provider.values_override = {**conn.values, **secrets}
        self.status.setText(self.ctx.tr("dlg.testing"))
        tr = self.ctx.tr

        def run():
            try:
                return provider.test()
            except core_credentials.AuthenticationRequired:
                raise RuntimeError(tr("dlg.test_auth")) from None

        run_async(run, lambda count: self.status.setText("✅ " + tr("dlg.test_ok", count=count)),
                  lambda err: self.status.setText("❌ " + err))

    def _save(self) -> None:
        missing = self._missing_required()
        if missing:
            QMessageBox.warning(self, self.windowTitle(), self.ctx.tr("dlg.missing", fields=", ".join(missing)))
            return
        if not self._ensure_modules():
            return
        self.conn = self._apply()
        self.accept()


class OmniVault(ToolBase):
    def create_widget(self, parent=None) -> QWidget:
        tr = self.context.tr
        self.store = ConnectorStore(self.context)
        self.root = QWidget(parent)
        outer = QHBoxLayout(self.root)
        outer.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        # ---- links: Quellen
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 12, 6, 12)
        title = QLabel(tr("ui.sources").upper())
        title.setObjectName("SectionTitle")
        ll.addWidget(title)
        self.sources = QListWidget()
        self.sources.currentItemChanged.connect(lambda *_: self._source_changed())
        self.sources.itemDoubleClicked.connect(lambda *_: self._edit())
        ll.addWidget(self.sources, 1)
        row = QHBoxLayout()
        add = QPushButton(tr("ui.add_connector"))
        add.setIcon(library_icon("plus", 16))
        add.clicked.connect(self._add)
        row.addWidget(add)
        self.edit_btn = QPushButton(tr("ui.edit"))
        self.edit_btn.clicked.connect(self._edit)
        row.addWidget(self.edit_btn)
        self.del_btn = QPushButton(tr("ui.remove"))
        self.del_btn.clicked.connect(self._remove)
        row.addWidget(self.del_btn)
        ll.addLayout(row)
        splitter.addWidget(left)

        # ---- rechts: eingebauter Manager oder Suche
        self.stack = QStackedWidget()
        local_page = QWidget()
        lp = QVBoxLayout(local_page)
        lp.setContentsMargins(12, 12, 12, 12)
        lp.addWidget(PasswordManagerWidget(local_page, self.context.notify))
        self.stack.addWidget(local_page)

        search_page = QWidget()
        sp = QVBoxLayout(search_page)
        sp.setContentsMargins(12, 12, 12, 12)
        self.search_title = QLabel()
        self.search_title.setObjectName("CardTitle")
        sp.addWidget(self.search_title)
        self.query = QLineEdit(placeholderText="🔍  " + tr("ui.search"))
        self.query.setClearButtonEnabled(True)
        self._timer = QTimer(self.root, singleShot=True, interval=400)
        self._timer.timeout.connect(self._search)
        self.query.textChanged.connect(lambda: self._timer.start())
        self.query.returnPressed.connect(self._search)
        sp.addWidget(self.query)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("ui.col_name"), tr("ui.col_user"), tr("ui.col_source")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        sp.addWidget(self.table, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("Muted")
        self.status.linkActivated.connect(self._login)
        sp.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch()
        for key, attr in (("ui.copy_user", "username"), ("ui.copy_password", "password")):
            b = QPushButton(tr(key))
            b.clicked.connect(lambda _=False, a=attr: self._copy(a))
            actions.addWidget(b)
        sp.addLayout(actions)
        self.stack.addWidget(search_page)
        splitter.addWidget(self.stack)
        splitter.setSizes([280, 720])

        self._items: list[core_credentials.Credential] = []
        self._auth_needed: list = []
        self._generation = 0
        self._fill_sources()
        return self.root

    # ------------------------------------------------------------ Quellen
    def _fill_sources(self, select: tuple[str, str] | None = None) -> None:
        tr = self.context.tr
        self.sources.blockSignals(True)
        self.sources.clear()
        entries = [("all", "", tr("ui.search_all"), "search"),
                   ("local", "", tr("ui.local"), "lock-keyhole")]
        for conn in self.store.all():
            icon = self.store.types[conn.type].get("icon", "plug")
            label = conn.name + ("" if conn.enabled else f"  ({tr('ui.disabled')})")
            entries.append(("conn", conn.id, label, icon))
        for kind, cid, label, icon in entries:
            item = QListWidgetItem(library_icon(icon, 18), label)
            item.setData(ROLE_KIND, kind)
            item.setData(ROLE_ID, cid)
            self.sources.addItem(item)
        self.sources.blockSignals(False)
        target = 1
        if select:
            for i in range(self.sources.count()):
                it = self.sources.item(i)
                if (it.data(ROLE_KIND), it.data(ROLE_ID)) == select:
                    target = i
        self.sources.setCurrentRow(target)
        self._source_changed()

    def _current(self) -> tuple[str, str]:
        item = self.sources.currentItem()
        return (item.data(ROLE_KIND), item.data(ROLE_ID)) if item else ("local", "")

    def _source_changed(self) -> None:
        kind, cid = self._current()
        self.edit_btn.setEnabled(kind == "conn")
        self.del_btn.setEnabled(kind == "conn")
        if kind == "local":
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)
        conn = self.store.get(cid) if kind == "conn" else None
        self.search_title.setText(conn.name if conn else self.context.tr("ui.search_all"))
        self.table.setRowCount(0)
        self._search()

    def _providers(self):
        manager = core_credentials.manager()
        kind, cid = self._current()
        if kind == "conn":
            conn = self.store.get(cid)
            if conn and not conn.enabled:
                return [make_provider(conn, self.store)]  # deaktiviert: trotzdem hier durchsuchbar
            p = manager.provider(conn.provider_id) if conn else None
            return [p] if p else []
        return list(manager.providers)

    def _add(self) -> None:
        dlg = ConnectorDialog(self, None)
        if dlg.exec():
            self._after_change(dlg.conn)

    def _edit(self) -> None:
        kind, cid = self._current()
        conn = self.store.get(cid) if kind == "conn" else None
        if conn and ConnectorDialog(self, conn).exec():
            self._after_change(self.store.get(cid))

    def _remove(self) -> None:
        kind, cid = self._current()
        conn = self.store.get(cid) if kind == "conn" else None
        if conn and QMessageBox.question(self.root, self.context.tr("ui.remove"),
                                         self.context.tr("ui.remove_confirm", name=conn.name)) \
                == QMessageBox.StandardButton.Yes:
            self.store.delete(conn.id)
            self.context.unregister_credential_provider(conn.provider_id)
            self._fill_sources()

    def _after_change(self, conn: ConnectorConfig) -> None:
        register_all(self.context)   # beim Hauptprogramm neu anmelden (ersetzt alte Instanz)
        self._fill_sources(select=("conn", conn.id))

    # ------------------------------------------------------------ Suche
    def _search(self) -> None:
        if self.stack.currentIndex() != 1:
            return
        self._generation += 1
        gen, query, providers = self._generation, self.query.text(), self._providers()
        self.status.setText(self.context.tr("ui.searching"))
        run_async(lambda: core_credentials.manager().search(query, providers),
                  lambda res: gen == self._generation and self._show(res),
                  lambda err: self.status.setText("❌ " + err))

    def _show(self, res) -> None:
        tr = self.context.tr
        self._items = res.items
        self._auth_needed = res.auth_needed
        self.table.setRowCount(len(res.items))
        for r, c in enumerate(res.items):
            name = QTableWidgetItem(c.name)
            name.setIcon(library_icon("key-round", 16))
            self.table.setItem(r, 0, name)
            self.table.setItem(r, 1, QTableWidgetItem(c.username))
            self.table.setItem(r, 2, QTableWidgetItem(c.source))
        notes = [tr("ui.results", count=len(res.items))]
        notes += [f"<a href='{i}'>{tr('ui.login_link', name=p.name)}</a>" for i, p in enumerate(res.auth_needed)]
        notes += [f"⚠ {name}: {err[:160]}" for name, err in res.errors.items()]
        self.status.setText(" · ".join(notes))

    def _login(self, index: str) -> None:
        if ask_provider_login(self._auth_needed[int(index)]):
            self._search()

    def _copy(self, attr: str) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._items)):
            return
        item = self._items[row]
        if attr == "username":
            copy_secret(item.username, self.context.notify)
            return
        cred = core_credentials.manager().resolve(item.ref)  # fragt bei Bedarf nach Anmeldedaten
        if cred:
            copy_secret(cred.password, self.context.notify)

    def on_settings_changed(self, changed_keys: set[str]) -> None:
        if "max_results" in changed_keys:
            register_all(self.context)

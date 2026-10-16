"""Password Manager Manager: eingebauter Passwortmanager + Konnektoren zu externen Managern."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QSplitter, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.core import credentials as core_credentials
from omniwrench.sdk import ToolBase, run_async
# Erstanbieter-Tool: nutzt Bausteine des Hauptprogramms direkt
from omniwrench.ui.credentials import PasswordEdit, PasswordManagerWidget, ask_provider_login, copy_secret
from omniwrench.ui.widgets import library_icon

from .connectors import ConnectorConfig, ConnectorStore, is_secret, make_provider, register_all, text

ROLE_KIND = Qt.ItemDataRole.UserRole
ROLE_ID = Qt.ItemDataRole.UserRole + 1


class ConnectorDialog(QDialog):
    """Konnektor anlegen/bearbeiten - Felder kommen aus connector_types.json."""

    def __init__(self, tool: "PasswordManagerManager", conn: ConnectorConfig, is_new: bool):
        super().__init__(tool.root)
        self.tool, self.conn = tool, conn
        ctx = tool.context
        tr, lang = ctx.tr, ctx.language
        spec = tool.store.types[conn.type]
        self.spec = spec
        self.setWindowTitle(tr("dlg.title_new" if is_new else "dlg.title_edit", type=spec["name"]))
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        desc = QLabel(text(spec.get("description"), lang))
        desc.setWordWrap(True)
        desc.setObjectName("Muted")
        lay.addWidget(desc)
        if spec.get("verified") is False:
            warn = QLabel("⚠ " + tr("dlg.unverified"))
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #f59e0b")
            lay.addWidget(warn)

        form = QFormLayout()
        self.name = QLineEdit(conn.name)
        form.addRow(tr("dlg.name"), self.name)
        self.enabled = QCheckBox(tr("dlg.enabled"))
        self.enabled.setChecked(conn.enabled)
        form.addRow("", self.enabled)

        values = tool.store.all_values(conn)
        self.inputs: dict[str, QWidget] = {}
        for f in spec["fields"]:
            w = self._make_input(f, values.get(f["key"], ""), lang)
            self.inputs[f["key"]] = w
            caption = text(f["label"], lang) + (" *" if f.get("required") else "")
            form.addRow(("🔑 " if f.get("auth") else "") + caption, w)
        lay.addLayout(form)

        self.save_auth = QCheckBox(tr("dlg.save_auth"))
        self.save_auth.setChecked(conn.save_auth)
        self.save_auth.setToolTip(tr("dlg.save_auth_hint"))
        lay.addWidget(self.save_auth)
        hint = QLabel(tr("dlg.save_auth_hint"))
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        lay.addWidget(hint)

        self.status = QLabel()
        self.status.setWordWrap(True)
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

    def _make_input(self, f: dict, value, lang: str) -> QWidget:
        placeholder = text(f.get("placeholder"), lang)
        if is_secret(f):
            w = PasswordEdit(str(value or ""), placeholder)
            return w
        if f.get("type") in ("path_file", "path_dir"):
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(str(value or ""))
            edit.setPlaceholderText(placeholder)
            btn = QPushButton("…")
            btn.setFixedWidth(34)

            def browse():
                if f["type"] == "path_dir":
                    path = QFileDialog.getExistingDirectory(box, text(f["label"], lang), edit.text())
                else:
                    path, _ = QFileDialog.getOpenFileName(box, text(f["label"], lang), edit.text())
                if path:
                    edit.setText(path)

            btn.clicked.connect(browse)
            h.addWidget(edit, 1)
            h.addWidget(btn)
            box.text = edit.text
            return box
        if f.get("type") == "bool":
            w = QCheckBox()
            w.setChecked(bool(value))
            w.text = lambda w=w: "1" if w.isChecked() else ""
            return w
        w = QLineEdit(str(value or ""))
        w.setPlaceholderText(placeholder)
        return w

    def _collect(self) -> tuple[ConnectorConfig, dict[str, str]]:
        conn = ConnectorConfig(self.conn.id, self.conn.type, self.name.text().strip() or self.spec["name"],
                               self.enabled.isChecked(), self.save_auth.isChecked(), {})
        secrets = {}
        for f in self.spec["fields"]:
            val = self.inputs[f["key"]].text()
            (secrets if is_secret(f) else conn.values)[f["key"]] = val
        return conn, secrets

    def _missing_required(self) -> list[str]:
        lang = self.tool.context.language
        return [text(f["label"], lang) for f in self.spec["fields"]
                if f.get("required") and not self.inputs[f["key"]].text().strip()]

    def _apply(self) -> ConnectorConfig:
        conn, secrets = self._collect()
        self.tool.store.save(conn)
        self.tool.store.set_secrets(conn, secrets, conn.save_auth)
        return conn

    def _ensure_modules(self) -> bool:
        """Fehlende PowerShell-Module (z. B. SecretManagement) anbieten zu installieren."""
        ctx = self.tool.context
        modules = self.spec.get("requirements", {}).get("powershell_modules", [])
        missing = [m for m in modules
                   if ctx.run_powershell(f"if (Get-Module -ListAvailable -Name '{m}') {{ 'ok' }}").stdout.strip() != "ok"]
        if not missing:
            return True
        if QMessageBox.question(self, self.windowTitle(), ctx.tr("dlg.install_modules", modules=", ".join(missing))) \
                != QMessageBox.StandardButton.Yes:
            return False
        self.status.setText(ctx.tr("dlg.installing"))
        QApplication.processEvents()
        for m in missing:
            res = ctx.run_powershell(
                "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;"
                f"Install-Module -Name '{m}' -Scope CurrentUser -Force -AllowClobber", timeout=900)
            if not res.ok:
                self.status.setText("❌ " + (res.stderr or res.stdout)[:300])
                return False
        self.status.setText("✅ " + ctx.tr("dlg.installed", modules=", ".join(missing)))
        return True

    def _test(self) -> None:
        missing = self._missing_required()
        if missing:
            self.status.setText("⚠ " + self.tool.context.tr("dlg.missing", fields=", ".join(missing)))
            return
        if not self._ensure_modules():
            return
        conn = self._apply()
        provider = make_provider(conn, self.tool.store)
        self.status.setText(self.tool.context.tr("dlg.testing"))
        tr = self.tool.context.tr

        def failed(err: str):
            self.status.setText("❌ " + err)

        def done(count):
            self.status.setText("✅ " + tr("dlg.test_ok", count=count))

        def run():
            try:
                return provider.test()
            except core_credentials.AuthenticationRequired:
                raise RuntimeError(tr("dlg.test_auth")) from None

        run_async(run, done, failed)

    def _save(self) -> None:
        missing = self._missing_required()
        if missing:
            QMessageBox.warning(self, self.windowTitle(), self.tool.context.tr("dlg.missing", fields=", ".join(missing)))
            return
        if not self._ensure_modules():
            return
        self.conn = self._apply()
        self.accept()


class PasswordManagerManager(ToolBase):
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
        add.clicked.connect(lambda: self._add_menu(add))
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

    def _add_menu(self, button: QPushButton) -> None:
        menu = QMenu(self.root)
        for type_id, spec in self.store.types.items():
            menu.addAction(library_icon(spec.get("icon", "plug"), 16), spec["name"],
                           lambda t=type_id: self._add(t))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _add(self, type_id: str) -> None:
        conn = self.store.new(type_id, self.store.types[type_id]["name"])
        dlg = ConnectorDialog(self, conn, is_new=True)
        if dlg.exec():
            self._after_change(dlg.conn)
        else:
            self.store.delete(conn.id)  # beim Testen evtl. schon angelegt
            self._fill_sources()

    def _edit(self) -> None:
        kind, cid = self._current()
        conn = self.store.get(cid) if kind == "conn" else None
        if conn and ConnectorDialog(self, conn, is_new=False).exec():
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

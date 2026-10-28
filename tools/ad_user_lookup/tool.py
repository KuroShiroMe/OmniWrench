"""Active-Directory-Benutzersuche über das PowerShell-Modul ActiveDirectory."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.sdk import CredentialField, ToolBase, run_async

COLUMNS = ["SamAccountName", "Name", "Enabled", "LockedOut", "LastLogonDate", "mail"]

# Parameter kommen als JSON über stdin - so landen Passwörter nie in der Kommandozeile.
SEARCH_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Import-Module ActiveDirectory
$p = [Console]::In.ReadToEnd() | ConvertFrom-Json
$adParams = @{
    Filter = "SamAccountName -like '*$($p.q)*' -or Name -like '*$($p.q)*' -or mail -like '*$($p.q)*'"
    Properties = @('Enabled','LockedOut','LastLogonDate','mail','Department','Title','MemberOf','whenCreated','PasswordLastSet')
    ResultSetSize = [int]$p.max
}
if ($p.server) { $adParams.Server = $p.server }
if ($p.base) { $adParams.SearchBase = $p.base }
if ($p.user) {
    $sec = ConvertTo-SecureString $p.password -AsPlainText -Force
    $adParams.Credential = New-Object System.Management.Automation.PSCredential($p.user, $sec)
}
$users = Get-ADUser @adParams | ForEach-Object {
    [pscustomobject]@{
        SamAccountName = $_.SamAccountName; Name = $_.Name; Enabled = $_.Enabled; LockedOut = $_.LockedOut
        LastLogonDate = if ($_.LastLogonDate) { $_.LastLogonDate.ToString('yyyy-MM-dd HH:mm') } else { '' }
        mail = $_.mail; Department = $_.Department; Title = $_.Title; DistinguishedName = $_.DistinguishedName
        whenCreated = $_.whenCreated.ToString('yyyy-MM-dd')
        PasswordLastSet = if ($_.PasswordLastSet) { $_.PasswordLastSet.ToString('yyyy-MM-dd HH:mm') } else { '' }
        MemberOf = @($_.MemberOf | ForEach-Object { ($_ -split ',')[0] -replace '^CN=' })
    }
}
ConvertTo-Json -InputObject @($users) -Depth 3 -Compress
"""


class AdUserLookup(ToolBase):
    def create_widget(self, parent=None) -> QWidget:
        tr = self.context.tr
        root = QWidget(parent)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(16, 16, 16, 16)

        row = QHBoxLayout()
        self.query = QLineEdit(placeholderText=tr("ui.search_placeholder"))
        self.query.returnPressed.connect(self._search)
        row.addWidget(self.query, 1)
        self.btn = QPushButton(tr("ui.search"))
        self.btn.clicked.connect(self._search)
        row.addWidget(self.btn)
        settings_btn = QPushButton("⚙")
        settings_btn.setToolTip(tr("ui.settings"))
        settings_btn.clicked.connect(self.context.open_settings)
        row.addWidget(settings_btn)
        lay.addLayout(row)

        # Anmeldedaten: Auswahlliste aus dem Passwortmanager (gespeichert werden nur Verweise,
        # das Passwort wird erst beim Suchen abgerufen - einmal pro Sitzung)
        cred_row = QHBoxLayout()
        self.use_cred = QCheckBox(tr("ui.use_credential"))
        self.use_cred.setChecked(bool(self.context.settings.get("use_credential")))
        self.use_cred.toggled.connect(self._toggle_credential)
        cred_row.addWidget(self.use_cred)
        self.cred_field = CredentialField(settings=self.context.settings, key="credential")
        self.cred_field.setEnabled(self.use_cred.isChecked())
        cred_row.addWidget(self.cred_field, 1)
        lay.addLayout(cred_row)

        self.status = QLabel()
        lay.addWidget(self.status)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(f"col.{c}") for c in COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._show_details)
        splitter.addWidget(self.table)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        splitter.addWidget(self.details)
        splitter.setSizes([400, 200])
        lay.addWidget(splitter, 1)
        self._users: list[dict] = []
        if hasattr(self.context, "add_ask_action"):     # KI-Assistent (ab OmniWrench 0.9.0)
            self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.table.customContextMenuRequested.connect(self._context_menu)
            from omniwrench.sdk import AI_READ
            self.context.ai_function(
                "ad_user_results", "AD user lookup: users found by the last search in the tool (account, name, "
                "state, last logon, mail, department, groups).", self._ai_results, level=AI_READ)
        return root

    def _selected_users(self) -> list[dict]:
        rows = sorted({i.data(Qt.ItemDataRole.UserRole) for i in self.table.selectedItems()})
        return [self._users[r] for r in rows if r is not None and 0 <= r < len(self._users)]

    def _context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        if not self._selected_users():
            return
        menu = QMenu(self.table)
        self.context.add_ask_action(menu, lambda: json.dumps(self._selected_users(), ensure_ascii=False, indent=1))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _ai_results(self, args, call):
        return call.in_gui(lambda: {"query": self.query.text().strip(), "total": len(self._users),
                                    "users": self._users[:200]})

    def _toggle_credential(self, on: bool) -> None:
        self.context.settings.set("use_credential", on)
        self.cred_field.setEnabled(on)

    def on_settings_changed(self, changed_keys: set[str]) -> None:
        if "credential" in changed_keys:
            self.cred_field.set_value(self.context.settings.get("credential"))
        if "use_credential" in changed_keys:
            self.use_cred.setChecked(bool(self.context.settings.get("use_credential")))

    def _search(self) -> None:
        q = self.query.text().strip().replace("'", "''")
        if not q:
            return
        s = self.context.settings
        params = {"q": q, "max": s.get("max_results", 200), "server": s.get("server"), "base": s.get("search_base")}
        self.btn.setEnabled(False)
        self.status.setText(self.context.tr("ui.searching"))
        if s.get("use_credential"):
            # Passwortmanager können Sekunden brauchen -> Abruf im Hintergrund
            self.cred_field.resolve_async(lambda cred: self._run_search(params, cred))
        else:
            self._run_search(params)

    def _run_search(self, params: dict, cred: tuple[str, str] | None = None) -> None:
        if self.context.settings.get("use_credential"):
            if not cred:
                self.btn.setEnabled(True)
                self.status.setText(self.context.tr("ui.no_credential"))
                return
            params["user"], params["password"] = cred
        run_async(lambda: self.context.run_powershell_json(SEARCH_SCRIPT, stdin=json.dumps(params), timeout=120),
                  self._show_results, self._failed)

    def _show_results(self, users) -> None:
        tr = self.context.tr
        self.btn.setEnabled(True)
        self._users = users or []
        self.status.setText(tr("ui.found", count=len(self._users)))
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._users))
        for r, u in enumerate(self._users):
            for c, key in enumerate(COLUMNS):
                value = u.get(key)
                text = (tr("ui.yes") if value else tr("ui.no")) if isinstance(value, bool) else str(value or "")
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, r)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)

    def _failed(self, error: str) -> None:
        self.btn.setEnabled(True)
        first_line = error.splitlines()[0] if error else ""
        self.status.setText(self.context.tr("ui.error", error=first_line))
        self.details.setPlainText(error)

    def _show_details(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        u = self._users[items[0].data(Qt.ItemDataRole.UserRole)]
        lines = [f"{k}: {v}" for k, v in u.items() if k != "MemberOf"]
        lines.append("\n" + self.context.tr("ui.groups") + ":\n  " + "\n  ".join(sorted(u.get("MemberOf") or [])))
        self.details.setPlainText("\n".join(lines))

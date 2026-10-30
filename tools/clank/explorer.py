"""Seitenleiste „Arbeitsbereich“: freigegebene Ordner und Repositories als Baum (lokal und online)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMenu, QMessageBox, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.sdk import run_async
from omniwrench.ui.widgets import make_button

from . import remote as rm
from . import workspace as wsm

ROLE = Qt.ItemDataRole.UserRole
ICONS = {"folder": "📁", "git": "🌿", "remote": "☁"}


class RemoteDialog(QDialog):
    """Online-Repository hinzufügen: URL, Token (optional), Zweig; wahlweise lokal klonen."""

    def __init__(self, tr, token_lookup, clone_dir: str, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.setWindowTitle(tr("ws.remote_title"))
        self.resize(560, 300)
        self._token_lookup = token_lookup
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("ws.remote_intro")))
        form = QFormLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://github.com/owner/repo")
        self.url.textChanged.connect(self._url_changed)
        form.addRow(tr("ws.remote_url"), self.url)
        self.provider = QLabel("–")
        form.addRow(tr("ws.remote_provider"), self.provider)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText(tr("ws.remote_token_ph"))
        form.addRow(tr("ws.remote_token"), self.token)
        self.branch = QLineEdit()
        self.branch.setPlaceholderText(tr("ws.remote_branch_ph"))
        form.addRow(tr("ws.remote_branch"), self.branch)
        self.clone = QCheckBox(tr("ws.remote_clone"))
        form.addRow("", self.clone)
        row = QHBoxLayout()
        self.target = QLineEdit(clone_dir)
        pick = QToolButton(text="…")
        pick.clicked.connect(self._pick)
        row.addWidget(self.target, 1)
        row.addWidget(pick)
        self.target_row = QWidget()
        self.target_row.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        form.addRow(tr("ws.remote_target"), self.target_row)
        self.clone.toggled.connect(self.target_row.setEnabled)
        self.target_row.setEnabled(False)
        lay.addLayout(form)
        lay.addWidget(QLabel(tr("ws.remote_hint")), 0)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.info: dict | None = None

    def _url_changed(self, text: str) -> None:
        try:
            self.info = rm.parse_url(text)
            self.provider.setText(self.tr(f"ws.provider.{self.info['provider']}") + f"  ·  {self.info['host']}")
            if not self.token.text():
                self.token.setText(self._token_lookup(self.info) or "")
        except wsm.WorkspaceError:
            self.info = None
            self.provider.setText("–")

    def _pick(self) -> None:
        d = QFileDialog.getExistingDirectory(self, self.tr("ws.remote_target"), self.target.text())
        if d:
            self.target.setText(d)

    def _ok(self) -> None:
        if self.info is None:
            QMessageBox.warning(self, self.windowTitle(), self.tr("ws.remote_bad_url"))
            return
        self.accept()


class WorkspacePanel(QWidget):
    open_file = Signal(str)          # Pfad relativ zum Arbeitsbereich
    changed = Signal()               # Einträge geändert (Tool speichert)
    open_access = Signal()           # Seite „KI-Zugriff“ des Tools öffnen

    def __init__(self, tool, parent=None):
        super().__init__(parent)
        self.tool = tool
        tr = self.tr = tool.context.tr
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.scope = QLabel("")
        self.scope.setObjectName("Muted")
        self.scope.setWordWrap(True)
        lay.addWidget(self.scope)
        self.level_hint = QWidget()
        hl = QHBoxLayout(self.level_hint)
        hl.setContentsMargins(0, 0, 0, 0)
        txt = QLabel(tr("ws.level_hint"))
        txt.setWordWrap(True)
        txt.setStyleSheet("color: #f59e0b;")
        hl.addWidget(txt, 1)
        hl.addWidget(make_button(tr("ws.level_open"), on_click=self.open_access.emit))
        lay.addWidget(self.level_hint)
        row = QHBoxLayout()
        self.add_btn = QToolButton(text="＋ " + tr("ws.add"))
        self.add_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        m = QMenu(self.add_btn)
        m.addAction("📁 " + tr("ws.add_folder"), self.add_folder)
        m.addAction("☁ " + tr("ws.add_remote"), self.add_remote)
        self.add_btn.setMenu(m)
        row.addWidget(self.add_btn)
        row.addStretch()
        self.refresh_btn = QToolButton(text="⟳")
        self.refresh_btn.setToolTip(tr("ws.refresh"))
        self.refresh_btn.clicked.connect(self.reload)
        row.addWidget(self.refresh_btn)
        lay.addLayout(row)
        self.filter = QLineEdit(placeholderText="🔍  " + tr("ws.filter"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemExpanded.connect(self._expand)
        self.tree.itemDoubleClicked.connect(self._activated)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.tree, 1)
        self.empty = QLabel(tr("ws.empty"))
        self.empty.setWordWrap(True)
        self.empty.setObjectName("Muted")
        lay.addWidget(self.empty)

    # --- Anzeige -------------------------------------------------------------------------------------
    def set_scope(self, text: str) -> None:
        self.scope.setText(text)

    def update_level(self, level: int) -> None:
        self.level_hint.setVisible(bool(self.tool.roots) and level < 3)

    def reload(self) -> None:
        self.tree.clear()
        for r in self.tool.roots:
            it = QTreeWidgetItem([f"{ICONS.get(r['kind'], '📁')} {r['name']}" + (" 🔒" if r.get("readonly") else "")])
            it.setData(0, ROLE, ("root", r["id"], ""))
            tip = r.get("path") or (r.get("remote") or {}).get("url", "")
            it.setToolTip(0, tip)
            it.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            self.tree.addTopLevelItem(it)
        self.empty.setVisible(not self.tool.roots)
        self.tree.setVisible(bool(self.tool.roots))
        self.filter.setVisible(bool(self.tool.roots))

    def _root(self, rid: str) -> dict | None:
        return next((r for r in self.tool.roots if r["id"] == rid), None)

    def _expand(self, item: QTreeWidgetItem) -> None:
        kind, rid, sub = item.data(0, ROLE)
        if item.childCount() or kind == "file":
            return
        root = self._root(rid)
        if root is None:
            return
        if root["kind"] == "remote":
            loading = QTreeWidgetItem([self.tr("ws.loading")])
            item.addChild(loading)

            def done(entries, item=item):
                item.takeChildren()
                self._fill(item, rid, sub, entries)

            def failed(text, item=item):
                item.takeChildren()
                item.addChild(QTreeWidgetItem(["⚠ " + text.splitlines()[0]]))
            run_async(lambda: self.tool.remote_for(root).list_dir(sub, 1), done, failed)
            return
        base = Path(root["path"]) / sub if sub else Path(root["path"])
        try:
            entries = sorted(base.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError as e:
            item.addChild(QTreeWidgetItem(["⚠ " + str(e)]))
            return
        rows = []
        for e in entries[:wsm.MAX_LIST]:
            if e.is_dir() and e.name in wsm.SKIP_DIRS:
                continue
            rows.append({"path": (f"{sub}/{e.name}" if sub else e.name), "type": "dir" if e.is_dir() else "file"})
        self._fill(item, rid, sub, rows)

    def _fill(self, item: QTreeWidgetItem, rid: str, sub: str, entries: list[dict]) -> None:
        for e in entries:
            name = e["path"].rsplit("/", 1)[-1]
            child = QTreeWidgetItem([("📁 " if e["type"] == "dir" else "📄 ") + name])
            child.setData(0, ROLE, ("dir" if e["type"] == "dir" else "file", rid, e["path"]))
            if e["type"] == "dir":
                child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            item.addChild(child)
        if not entries:
            empty = QTreeWidgetItem([self.tr("ws.folder_empty")])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            item.addChild(empty)
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self.filter.text().strip().lower()

        def visit(it: QTreeWidgetItem) -> bool:
            shown = False
            for i in range(it.childCount()):
                shown = visit(it.child(i)) or shown
            own = not needle or needle in it.text(0).lower()
            it.setHidden(not (own or shown))
            return own or shown
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            visit(top)
            top.setHidden(False)

    def _rel(self, item: QTreeWidgetItem) -> str:
        kind, rid, sub = item.data(0, ROLE)
        root = self._root(rid)
        return f"{root['name']}/{sub}".rstrip("/") if root else ""

    def _activated(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, ROLE)
        if data and data[0] == "file":
            self.open_file.emit(self._rel(item))

    def _menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        data = item.data(0, ROLE) if item else None
        if not data:
            return
        tr = self.tr
        m = QMenu(self)
        kind, rid, sub = data
        root = self._root(rid)
        if kind == "file":
            m.addAction(tr("ws.open"), lambda: self.open_file.emit(self._rel(item)))
            m.addAction(tr("ws.attach"), lambda: self.tool.attach_file(self._rel(item)))
        if root and root["kind"] != "remote":
            m.addAction(tr("ws.reveal"), lambda: self.tool.reveal(self._rel(item)))
        if kind == "root" and root:
            m.addSeparator()
            act = m.addAction(tr("ws.readonly"))
            act.setCheckable(True)
            act.setChecked(bool(root.get("readonly")))
            act.toggled.connect(lambda on: self._set_readonly(rid, on))
            m.addAction(tr("ws.rename"), lambda: self._rename(rid))
            m.addAction(tr("ws.remove"), lambda: self._remove(rid))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # --- Ändern --------------------------------------------------------------------------------------
    def add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, self.tr("ws.add_folder"))
        if not d:
            return
        path = Path(d)
        kind = "git" if wsm.is_git_dir(path) else "folder"
        roots = self.tool.roots
        roots.append(wsm.new_root(kind, wsm.unique_name(roots, path.name or str(path)), str(path)))
        self.changed.emit()

    def add_remote(self) -> None:
        tool, tr = self.tool, self.tr
        dlg = RemoteDialog(tr, tool.token_for, tool.clone_dir(), self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.info is None:
            return
        info, token, branch = dlg.info, dlg.token.text().strip(), dlg.branch.text().strip()
        if token:
            tool.save_token(info, token)
        roots = tool.roots
        if dlg.clone.isChecked():
            target = Path(dlg.target.text().strip() or tool.clone_dir()) / info["repo"]

            def done(_res):
                roots.append(wsm.new_root("git", wsm.unique_name(roots, info["repo"]), str(target)))
                tool.notify(tr("ws.cloned", path=str(target)))
                self.changed.emit()

            def failed(text):
                QMessageBox.warning(self, tr("ws.remote_title"), text)
            tool.notify(tr("ws.cloning", url=info["url"]))
            run_async(lambda: rm.clone(info, token, target, branch), done, failed)
            return
        roots.append(wsm.new_root("remote", wsm.unique_name(roots, info["repo"]), "",
                                  {**info, "branch": branch}, readonly=True))
        self.changed.emit()

    def _set_readonly(self, rid: str, on: bool) -> None:
        root = self._root(rid)
        if root and root["kind"] != "remote":
            root["readonly"] = on
            self.changed.emit()

    def _rename(self, rid: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        root = self._root(rid)
        if not root:
            return
        name, ok = QInputDialog.getText(self, self.tr("ws.rename"), self.tr("ws.name"), text=root["name"])
        name = name.strip().replace("/", "-")
        if ok and name and name != root["name"]:
            others = [r for r in self.tool.roots if r["id"] != rid]
            root["name"] = wsm.unique_name(others, name)
            self.changed.emit()

    def _remove(self, rid: str) -> None:
        root = self._root(rid)
        if root and QMessageBox.question(self, self.tr("ws.remove"), self.tr("ws.remove_q", name=root["name"])) \
                == QMessageBox.StandardButton.Yes:
            self.tool.roots[:] = [r for r in self.tool.roots if r["id"] != rid]
            self.changed.emit()

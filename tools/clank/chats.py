"""Seitenleiste „Chats“: Projekte mit ihren Chats und Chats ohne Projekt (Daten aus der KI-Datenablage)."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QMenu, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

ROLE = Qt.ItemDataRole.UserRole


class ChatList(QWidget):
    open_thread = Signal(str, str)      # (Chat-ID, Projekt-ID)
    new_chat = Signal(str)              # Projekt-ID ("" = ohne Projekt)
    new_project = Signal()
    select_project = Signal(str)
    edit_project = Signal(str)
    delete_project = Signal(str)
    rename_thread = Signal(str, str)
    delete_thread = Signal(str, str)
    reveal = Signal(str, str)           # (Chat-ID | "", Projekt-ID)

    def __init__(self, tr, storage, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.storage = storage
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        row = QHBoxLayout()
        b1 = QToolButton(text="＋ " + tr("chats.new_chat"))
        b1.clicked.connect(lambda: self.new_chat.emit(self.current_project()))
        b2 = QToolButton(text="📁 " + tr("chats.new_project"))
        b2.clicked.connect(self.new_project.emit)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch()
        lay.addLayout(row)
        self.search = QLineEdit(placeholderText="🔍  " + tr("chats.search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.reload)
        lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemExpanded.connect(lambda it: self._expanded.add(it.data(0, ROLE)[1]))
        self.tree.itemCollapsed.connect(lambda it: self._expanded.discard(it.data(0, ROLE)[1]))
        lay.addWidget(self.tree, 1)
        self._project = ""
        self._thread = ""
        self._expanded: set[str] = {""}

    def current_project(self) -> str:
        return self._project

    def mark(self, thread_id: str, project: str) -> None:
        self._thread, self._project = thread_id or "", project or ""
        self._expanded.add(self._project)
        self.reload()

    def reload(self) -> None:
        needle = self.search.text().strip().lower()
        self.tree.clear()
        groups = [("", self.tr("chats.no_project"), None)]
        groups += [(p["id"], p.get("name") or p["id"], p) for p in self.storage.list_projects()]
        for pid, name, proj in groups:
            top = QTreeWidgetItem([("📁 " if pid else "💬 ") + name + (" 🔒" if proj and proj.get("locked") else "")])
            top.setData(0, ROLE, ("project", pid))
            f = top.font(0)
            f.setBold(pid == self._project)
            top.setFont(0, f)
            if proj and proj.get("workspace"):
                top.setToolTip(0, self.tr("chats.project_ws", n=len(proj["workspace"])))
            self.tree.addTopLevelItem(top)
            threads = self.storage.list_threads(pid)
            shown = 0
            for t in threads:
                title = t.get("title") or self.tr("chats.untitled")
                if needle and needle not in title.lower():
                    continue
                when = time.strftime("%d.%m. %H:%M", time.localtime(t.get("updated") or 0))
                it = QTreeWidgetItem([f"{'🔒 ' if t.get('locked') else ''}{title}"])
                it.setToolTip(0, f"{title}\n{when} · {t.get('connection_name') or ''}")
                it.setData(0, ROLE, ("thread", t["id"], pid))
                if t["id"] == self._thread:
                    it.setSelected(True)
                    fi = it.font(0)
                    fi.setBold(True)
                    it.setFont(0, fi)
                top.addChild(it)
                shown += 1
            if needle and not shown and needle not in name.lower():
                top.setHidden(True)
            top.setExpanded(pid in self._expanded or bool(needle))

    def _clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, ROLE)
        if not data:
            return
        if data[0] == "thread":
            self.open_thread.emit(data[1], data[2])
        else:
            self.select_project.emit(data[1])

    def _menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        data = item.data(0, ROLE) if item else None
        if not data:
            return
        tr = self.tr
        m = QMenu(self)
        if data[0] == "thread":
            tid, pid = data[1], data[2]
            m.addAction(tr("chats.open"), lambda: self.open_thread.emit(tid, pid))
            m.addAction(tr("chats.rename"), lambda: self.rename_thread.emit(tid, pid))
            m.addAction(tr("chats.reveal"), lambda: self.reveal.emit(tid, pid))
            m.addSeparator()
            m.addAction(tr("chats.delete"), lambda: self.delete_thread.emit(tid, pid))
        else:
            pid = data[1]
            m.addAction(tr("chats.new_chat"), lambda: self.new_chat.emit(pid))
            if pid:
                m.addAction(tr("chats.edit_project"), lambda: self.edit_project.emit(pid))
                m.addAction(tr("chats.reveal"), lambda: self.reveal.emit("", pid))
                m.addSeparator()
                m.addAction(tr("chats.delete_project"), lambda: self.delete_project.emit(pid))
        m.exec(self.tree.viewport().mapToGlobal(pos))

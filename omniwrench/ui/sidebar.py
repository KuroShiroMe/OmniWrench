"""Seitenleiste mit Navigation und Liste der installierten Tools (nach Kategorien)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from omniwrench.core.i18n import tr

from .widgets import label, make_button, tool_icon

if TYPE_CHECKING:
    from .main_window import MainWindow

CATEGORY_ROLE = Qt.ItemDataRole.UserRole + 1


class Sidebar(QWidget):
    def __init__(self, host: "MainWindow"):
        super().__init__()
        self.host = host
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(200)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 10, 10)
        lay.setSpacing(6)

        nav = QWidget()
        nav.setObjectName("SidebarNav")
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(0, 0, 0, 0)
        nav_lay.setSpacing(2)
        nav_lay.addWidget(make_button("🏠   " + tr("nav.home"), on_click=lambda: host.show_home()))
        nav_lay.addWidget(make_button("🛒   " + tr("nav.store"), on_click=host.show_store))
        lay.addWidget(nav)

        lay.addSpacing(8)
        lay.addWidget(label(tr("sidebar.installed").upper(), "SectionTitle"))
        self.search = QLineEdit(placeholderText=tr("sidebar.filter"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        lay.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.setExpandsOnDoubleClick(False)  # Doppelklick auf Kategorie = Filter auf Home
        self.tree.itemDoubleClicked.connect(self._activated)
        self.tree.itemActivated.connect(self._activated)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        lay.addWidget(self.tree, 1)

        self._last_activation = None
        host.manager.toolsChanged.connect(self.refresh)
        host.catalogChanged.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.tree.clear()
        query = self.search.text().strip().lower()
        nodes: dict[tuple, QTreeWidgetItem] = {}
        for tool in sorted(self.host.manager.tools.values(), key=lambda t: t.manifest.display_name.lower()):
            m = tool.manifest
            if query and query not in (m.display_name + "/".join(m.category_path) + " ".join(m.tags)).lower():
                continue
            parent = None
            path = m.category_path
            for depth in range(1, len(path) + 1):
                key = tuple(path[:depth])
                if key not in nodes:
                    node = QTreeWidgetItem([key[-1]])
                    node.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    font = node.font(0)
                    font.setBold(True)
                    node.setFont(0, font)
                    node.setData(0, CATEGORY_ROLE, key)
                    node.setToolTip(0, f"{key[-1]}\n{tr('sidebar.category_hint')}")
                    (parent.addChild(node) if parent else self.tree.addTopLevelItem(node))
                    nodes[key] = node
                parent = nodes[key]
            name = m.display_name + ("  ⬆" if tool.id in self.host.tool_updates else "")
            item = QTreeWidgetItem([name])
            item.setIcon(0, tool_icon(m, tool.path, 18))
            item.setData(0, Qt.ItemDataRole.UserRole, tool.id)
            item.setToolTip(0, f"{m.display_name} {m.version}\n{m.display_description}")
            parent.addChild(item)
        self.tree.expandAll()

    def _activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        # itemDoubleClicked und itemActivated feuern beide - nur einmal reagieren
        if self._last_activation is item:
            return
        self._last_activation = item
        QTimer.singleShot(0, lambda: setattr(self, "_last_activation", None))
        if tool_id := item.data(0, Qt.ItemDataRole.UserRole):
            self.host.open_tool(tool_id)
        elif category := item.data(0, CATEGORY_ROLE):
            self.host.show_home(category_filter=tuple(category))

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item and (tool_id := item.data(0, Qt.ItemDataRole.UserRole)):
            self.host.show_tool_menu(tool_id, self.tree.viewport().mapToGlobal(pos))

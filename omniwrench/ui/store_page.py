"""Store-Tab: Tools aus den konfigurierten Repositories durchsuchen und installieren.

Gleicher Aufbau wie die Vollansicht im Home-Tab: Karten mit Symbol, Titel, Screenshots,
Kurzbeschreibung und einem Button; ein Klick zeigt rechts alle Details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLineEdit, QScrollArea, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.core.i18n import tr

from .tool_views import DetailsPanel, ToolCard, ToolItem, side_width
from .widgets import ColumnFlowLayout, ResponsiveRow, clear_layout, label, make_button

if TYPE_CHECKING:
    from .main_window import MainWindow

FILTER_ALL = "__all__"
FILTER_UPDATES = "__updates__"
FILTER_INSTALLED = "__installed__"


class StorePage(QWidget):
    def __init__(self, host: "MainWindow"):
        super().__init__()
        self.host = host
        self.selected: str | None = None
        self.cards: dict[str, ToolCard] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(12)

        titles = QVBoxLayout()
        titles.addWidget(label(tr("nav.store"), "PageTitle"))
        self.status = label(tr("store.loading"), "PageSubtitle", wrap=True)
        titles.addWidget(self.status)
        controls = QHBoxLayout()
        self.search = QLineEdit(placeholderText="🔍  " + tr("store.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(150)
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self._render)
        controls.addWidget(self.search, 1)
        self.update_all_btn = make_button(tr("updates.update_all"), primary=True, on_click=host.update_all_tools)
        self.update_all_btn.hide()
        controls.addWidget(self.update_all_btn)
        self.refresh_btn = make_button(tr("store.refresh"), on_click=host.reload_catalog)
        controls.addWidget(self.refresh_btn)
        root.addWidget(ResponsiveRow(titles, controls))

        self.splitter = splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(150)
        self.tree.currentItemChanged.connect(lambda *_: self._render())
        splitter.addWidget(self.tree)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        scroll.setWidget(content)
        outer = QVBoxLayout(content)
        outer.setContentsMargins(12, 0, 4, 0)
        # Karten in Spalten: schmale Fenster untereinander, große Monitore mehrere nebeneinander
        holder = QWidget()
        self.list = ColumnFlowLayout(holder, min_width=280, spacing=14)
        outer.addWidget(holder)
        self.empty = label(tr("store.empty"), "Muted")
        self.empty.hide()
        outer.addWidget(self.empty)
        outer.addStretch()
        scroll.setMinimumWidth(320)  # mindestens eine Karte; sonst drückt der Splitter die Karten zusammen
        splitter.addWidget(scroll)
        self.details = DetailsPanel(host, self.search)
        self.details.closed.connect(self.clear_selection)
        self.details.hide()
        splitter.addWidget(self.details)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 800, 0])
        root.addWidget(splitter, 1)

        host.catalogChanged.connect(self.refresh)
        host.manager.toolsChanged.connect(self._render)
        self.refresh()

    def set_loading(self, loading: bool) -> None:
        self.refresh_btn.setEnabled(not loading)
        if loading:
            self.status.setText(tr("store.loading"))

    def select_updates(self) -> None:
        self.tree.setCurrentItem(self.tree.topLevelItem(1))

    # ------------------------------------------------------------ Auswahl
    def select_tool(self, tool_id: str) -> None:
        catalog = self.host.catalog
        entry = catalog.entries.get(tool_id) if catalog else None
        if entry is None:
            return self.clear_selection()
        self.selected = tool_id
        for tid, card in self.cards.items():
            card.set_selected(tid == tool_id)
        self.details.show_item(ToolItem.for_store(entry, self.host))
        if self.details.isHidden():
            self.details.show()
            self._fit_tree()
            sizes = self.splitter.sizes()
            whole = max(sum(sizes), 800)
            side = side_width(whole)
            tree = max(150, min(sizes[0], whole - side - 320)) if self.tree.isVisible() else 0
            self.splitter.setSizes([tree, whole - tree - side, side])

    def clear_selection(self) -> None:
        self.selected = None
        for card in self.cards.values():
            card.set_selected(False)
        self.details.hide()
        self._fit_tree()

    def _fit_tree(self) -> None:
        # Schmales Fenster mit offenen Details: Kategorienbaum ausblenden statt die Karten zu quetschen
        narrow = self.width() < 150 + 320 + side_width(self.width()) + 40
        self.tree.setVisible(self.details.isHidden() or not narrow)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_tree()

    def _open(self, tool_id: str) -> None:
        if self.host.manager.get(tool_id):
            self.host.open_tool(tool_id)

    def refresh(self) -> None:
        catalog = self.host.catalog
        if catalog is None:
            return
        selected = self.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) if self.tree.currentItem() else FILTER_ALL
        self.tree.blockSignals(True)
        self.tree.clear()
        n_upd = len(self.host.tool_updates)
        self.update_all_btn.setText(tr("updates.update_all_count", count=n_upd))
        self.update_all_btn.setVisible(n_upd > 0)
        for text, key in ((tr("store.filter_all"), FILTER_ALL),
                          (tr("store.filter_updates", count=n_upd), FILTER_UPDATES),
                          (tr("store.filter_installed"), FILTER_INSTALLED)):
            item = QTreeWidgetItem([text])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            self.tree.addTopLevelItem(item)
        cat_root = QTreeWidgetItem([tr("store.categories")])
        cat_root.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.tree.addTopLevelItem(cat_root)
        nodes: dict[tuple, QTreeWidgetItem] = {}
        paths = sorted({tuple(e.manifest.category_path) for e in catalog.entries.values()})
        for path in paths:
            for depth in range(1, len(path) + 1):
                key = tuple(path[:depth])
                if key in nodes:
                    continue
                parent = nodes.get(key[:-1], cat_root)
                node = QTreeWidgetItem(parent, [key[-1]])
                node.setData(0, Qt.ItemDataRole.UserRole, "/".join(key))
                nodes[key] = node
        self.tree.expandAll()
        restore = next((self.tree.topLevelItem(i) for i in range(3)
                        if self.tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole) == selected), None)
        restore = restore or next((n for n in nodes.values() if n.data(0, Qt.ItemDataRole.UserRole) == selected),
                                  self.tree.topLevelItem(0))
        self.tree.setCurrentItem(restore)
        self.tree.blockSignals(False)

        status = tr("store.status", tools=len(catalog.entries),
                    repos=len(self.host.settings.get("repositories", [])))
        if catalog.errors:
            status += "  ·  ⚠ " + "; ".join(catalog.errors)
        self.status.setText(status)
        self.set_loading(False)
        self._render()

    def _render(self) -> None:
        clear_layout(self.list)
        catalog = self.host.catalog
        if catalog is None:
            return
        key = self.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) if self.tree.currentItem() else FILTER_ALL
        entries = sorted(catalog.entries.values(), key=lambda e: e.manifest.display_name.lower())
        if key == FILTER_UPDATES:
            entries = [e for e in entries if e.manifest.id in self.host.tool_updates]
        elif key == FILTER_INSTALLED:
            entries = [e for e in entries if self.host.manager.get(e.manifest.id)]
        elif key and key != FILTER_ALL:
            entries = [e for e in entries if ("/".join(e.manifest.category_path) + "/").startswith(key + "/")]
        query = self.search.text().strip().lower()
        if query:
            entries = [e for e in entries if query in ToolItem.for_store(e, self.host).search_text()]
        self.cards = {}
        for e in entries:
            card = ToolCard(ToolItem.for_store(e, self.host), self.host, self.select_tool, self._open,
                            self.host.show_tool_menu)
            card.set_selected(e.manifest.id == self.selected)
            self.cards[e.manifest.id] = card
            self.list.addWidget(card)
        self.empty.setVisible(not entries)
        # Detail-Leiste nach Installation/Update/Katalogwechsel neu aufbauen
        if self.selected and self.selected in catalog.entries:
            self.details.show_item(ToolItem.for_store(catalog.entries[self.selected], self.host))
        elif self.selected:
            self.clear_selection()

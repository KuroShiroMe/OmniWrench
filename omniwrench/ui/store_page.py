"""Store-Tab: Tools aus den konfigurierten Repositories durchsuchen und installieren."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import unquote

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLineEdit, QScrollArea, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.core import system
from omniwrench.core.i18n import tr
from omniwrench.core.repository import CatalogEntry
from omniwrench.core.versioning import is_newer

from .widgets import ColumnFlowLayout, ResponsiveRow, breakable, clear_layout, label, make_button, tag_links, tool_icon

if TYPE_CHECKING:
    from .main_window import MainWindow

FILTER_ALL = "__all__"
FILTER_UPDATES = "__updates__"
FILTER_INSTALLED = "__installed__"


def _search_text(entry: CatalogEntry) -> str:
    m = entry.manifest
    return (m.display_name + m.display_description + "/".join(m.category_path) + " ".join(m.tags)).lower()


class StoreCard(QFrame):
    def __init__(self, entry: CatalogEntry, host: "MainWindow"):
        super().__init__()
        self.setObjectName("ToolCard")
        m = entry.manifest
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        lay = QHBoxLayout()
        lay.setSpacing(14)

        icon = label("")
        icon.setPixmap(tool_icon(m, None, 52).pixmap(52, 52))
        lay.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(4)
        info.addWidget(label(m.display_name, "StoreCardTitle"))
        meta = f"v{m.version} · {' › '.join(m.category_path)}"
        if m.author:
            meta += f" · {m.author}"
        meta += " · " + tr("store.source", name=entry.repo_name)
        info.addWidget(label(meta, "CardMeta", wrap=True))
        info.addWidget(label(m.display_long_description, "CardDesc", wrap=True))
        if m.tags:  # Klick auf ein Tag sucht danach
            tags = label(tr("store.tags", items=tag_links(m.tags)), "CardMeta", wrap=True)
            tags.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            tags.linkActivated.connect(lambda tag: host.store_page.search.setText(unquote(tag)))
            info.addWidget(tags)
        reqs = m.requirements.summary()
        if reqs:
            info.addWidget(label(breakable(tr("store.requirements", items=", ".join(reqs))), "CardMeta", wrap=True))
        lay.addLayout(info, 1)

        installed = host.manager.get(m.id)
        col = QVBoxLayout()
        if installed is None and not system.supports_platform(m.platforms):
            # Tool für ein anderes Betriebssystem (z. B. nur Windows): anzeigen, aber nicht installierbar
            platforms = ", ".join(system.platform_name(p) for p in m.platforms)
            col.addWidget(label(tr("store.platform_only", platforms=platforms), "CardMeta"),
                          alignment=Qt.AlignmentFlag.AlignRight)
            btn = None
        elif installed is None:
            btn = make_button(tr("store.install"), primary=True, on_click=lambda: host.install_entry(entry))
        elif is_newer(m.version, installed.manifest.version):
            col.addWidget(label(tr("store.installed_version", version=installed.manifest.version), "CardMeta"),
                          alignment=Qt.AlignmentFlag.AlignRight)
            btn = make_button(tr("store.update_to", version=m.version), primary=True,
                              on_click=lambda: host.install_entry(entry))
        else:
            btn = make_button(tr("common.open"), on_click=lambda: host.open_tool(m.id))
            col.addWidget(label(tr("store.installed"), "BadgeOk"), alignment=Qt.AlignmentFlag.AlignRight)
        if btn is not None:
            btn.setMinimumWidth(130)
            col.addWidget(btn)
        col.addStretch()
        # Schmale Karte: Status und Button rutschen unter die Beschreibung
        outer.addWidget(ResponsiveRow(lay, col, left_width=300, align=Qt.AlignmentFlag.AlignTop))
        outer.addStretch()  # Karten einer Zeile sind gleich hoch - Inhalt bleibt oben


class StorePage(QWidget):
    def __init__(self, host: "MainWindow"):
        super().__init__()
        self.host = host
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

        splitter = QSplitter()
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
        self.list = ColumnFlowLayout(holder, min_width=520, spacing=10)
        outer.addWidget(holder)
        self.empty = label(tr("store.empty"), "Muted")
        self.empty.hide()
        outer.addWidget(self.empty)
        outer.addStretch()
        splitter.addWidget(scroll)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 800])
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
            entries = [e for e in entries if query in _search_text(e)]
        for e in entries:
            self.list.addWidget(StoreCard(e, self.host))
        self.empty.setVisible(not entries)

"""Store-Tab: Tools aus den konfigurierten Repositories durchsuchen und installieren."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLineEdit, QScrollArea, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.core.i18n import tr
from omniwrench.core.repository import CatalogEntry
from omniwrench.core.versioning import is_newer

from .widgets import clear_layout, label, make_button, tool_icon

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
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)

        icon = label("")
        icon.setPixmap(tool_icon(m, None, 52).pixmap(52, 52))
        lay.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(4)
        info.addWidget(label(m.display_name, "CardTitle"))
        meta = f"v{m.version} · {' › '.join(m.category_path)}"
        if m.author:
            meta += f" · {m.author}"
        meta += " · " + tr("store.source", name=entry.repo_name)
        info.addWidget(label(meta, "CardMeta", wrap=True))
        info.addWidget(label(m.display_long_description, "CardDesc", wrap=True))
        reqs = m.requirements.summary()
        if reqs:
            info.addWidget(label(tr("store.requirements", items=", ".join(reqs)), "CardMeta", wrap=True))
        lay.addLayout(info, 1)

        installed = host.manager.get(m.id)
        col = QVBoxLayout()
        if installed is None:
            btn = make_button(tr("store.install"), primary=True, on_click=lambda: host.install_entry(entry))
        elif is_newer(m.version, installed.manifest.version):
            col.addWidget(label(tr("store.installed_version", version=installed.manifest.version), "CardMeta"),
                          alignment=Qt.AlignmentFlag.AlignRight)
            btn = make_button(tr("store.update_to", version=m.version), primary=True,
                              on_click=lambda: host.install_entry(entry))
        else:
            btn = make_button(tr("common.open"), on_click=lambda: host.open_tool(m.id))
            col.addWidget(label(tr("store.installed"), "BadgeOk"), alignment=Qt.AlignmentFlag.AlignRight)
        btn.setMinimumWidth(130)
        col.addWidget(btn)
        col.addStretch()
        lay.addLayout(col)


class StorePage(QWidget):
    def __init__(self, host: "MainWindow"):
        super().__init__()
        self.host = host
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label(tr("nav.store"), "PageTitle"))
        self.status = label(tr("store.loading"), "PageSubtitle", wrap=True)
        titles.addWidget(self.status)
        header.addLayout(titles, 1)
        self.search = QLineEdit(placeholderText="🔍  " + tr("store.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(140)
        self.search.setMaximumWidth(280)
        self.search.textChanged.connect(self._render)
        header.addWidget(self.search, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.refresh_btn = make_button(tr("store.refresh"), on_click=host.reload_catalog)
        header.addWidget(self.refresh_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

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
        self.list = QVBoxLayout(content)
        self.list.setContentsMargins(12, 0, 4, 0)
        self.list.setSpacing(10)
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
        if not entries:
            self.list.addWidget(label(tr("store.empty"), "Muted"))
        self.list.addStretch()

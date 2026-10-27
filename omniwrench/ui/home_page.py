"""Home-Tab: installierte Tools, gruppiert nach Kategorie, in wählbarer Ansicht.

Ansichten (Einstellung "home_view"): Vollansicht (Karten mit Screenshots wie im Store),
große Symbole, kleine Symbole und Liste mit Details. Ein Klick zeigt rechts die Detail-Leiste,
ein Doppelklick startet das Tool, ein Rechtsklick öffnet das Kontextmenü.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFrame, QHBoxLayout, QHeaderView, QLineEdit, QMenu, QScrollArea, QSplitter,
    QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.core.i18n import tr
from omniwrench.core.system import is_windows_server

from .tool_views import DetailsPanel, Selectable, ToolCard, ToolItem, repolish, side_width
from .widgets import ColumnFlowLayout, FitLabel, FlowLayout, ResponsiveRow, clear_layout, label, library_icon, make_button

if TYPE_CHECKING:
    from .main_window import MainWindow

VIEWS = ("full", "large", "small", "list")
VIEW_ICONS = {"full": "gallery-vertical-end", "large": "grid-2x2", "small": "grid-3x3", "list": "layout-list"}


class ToolTile(Selectable, QFrame):
    """Große Symbole: Symbol mit Name darunter."""

    SIZE = QSize(128, 122)
    ICON = 56

    def __init__(self, item: ToolItem, page: "HomePage"):
        super().__init__()
        self.item = item
        self.activated_cb, self.opened_cb, self.menu_cb = page.select_tool, page.host.open_tool, page.host.show_tool_menu
        self.setObjectName("ToolTile")
        self.setFixedSize(self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(item.manifest.display_description)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 8)
        lay.setSpacing(6)
        icon = label("")
        icon.setPixmap(item.icon(self.ICON))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)
        lay.addWidget(FitLabel(item.manifest.display_name, max_pt=9.5, min_pt=7.5, single_min_pt=8.5), 1)

        if item.update is not None:  # kleiner Punkt oben rechts
            dot = label("", "UpdateDot", parent=self)
            dot.setFixedSize(10, 10)
            dot.move(self.SIZE.width() - 18, 8)
            dot.setToolTip(tr("home.update_badge", version=item.update.manifest.version))


class SmallTile(Selectable, QFrame):
    """Kleine Symbole: Symbol links, Name rechts daneben."""

    SIZE = QSize(210, 38)
    ICON = 24

    def __init__(self, item: ToolItem, page: "HomePage"):
        super().__init__()
        self.item = item
        self.activated_cb, self.opened_cb, self.menu_cb = page.select_tool, page.host.open_tool, page.host.show_tool_menu
        self.setObjectName("ToolTile")
        self.setFixedSize(self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(item.manifest.display_description)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(8)
        icon = label("")
        icon.setPixmap(item.icon(self.ICON))
        lay.addWidget(icon)
        name = label("", "TileName")
        name.setText(name.fontMetrics().elidedText(item.manifest.display_name, Qt.TextElideMode.ElideRight,
                                                   self.SIZE.width() - self.ICON - 40))
        lay.addWidget(name, 1)
        if item.update is not None:
            dot = label("", "UpdateDot")
            dot.setFixedSize(8, 8)
            dot.setToolTip(tr("home.update_badge", version=item.update.manifest.version))
            lay.addWidget(dot)


class ToolList(QTreeWidget):
    """Liste mit Details: eine Zeile je Tool, Spalten sortierbar."""

    COLUMNS = ("home.col_name", "details.version", "details.category", "home.col_status", "home.col_description")

    def __init__(self, page: "HomePage"):
        super().__init__()
        self.page = page
        self.setObjectName("ToolList")
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setIconSize(QSize(22, 22))
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHeaderLabels([tr(k) for k in self.COLUMNS])
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        header = self.header()
        header.setStretchLastSection(True)
        for col in range(len(self.COLUMNS) - 1):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemClicked.connect(lambda it, _c: page.select_tool(it.data(0, Qt.ItemDataRole.UserRole)))
        self.itemDoubleClicked.connect(lambda it, _c: page.host.open_tool(it.data(0, Qt.ItemDataRole.UserRole)))
        self.rows: dict[str, QTreeWidgetItem] = {}

    def add(self, item: ToolItem) -> None:
        m = item.manifest
        status = tr("home.update_badge", version=item.update.manifest.version) if item.update else ""
        row = QTreeWidgetItem([m.display_name, m.version, " › ".join(m.category_path), status,
                               m.display_description])
        row.setIcon(0, item.icon(22))
        row.setData(0, Qt.ItemDataRole.UserRole, m.id)
        row.setToolTip(4, m.display_description)
        self.addTopLevelItem(row)
        self.rows[m.id] = row

    def fit_height(self) -> None:
        """Keine eigene Bildlaufleiste: die Seite scrollt als Ganzes."""
        rows = self.topLevelItemCount()
        row_h = self.sizeHintForRow(0) if rows else 24
        self.setFixedHeight(self.header().sizeHint().height() + rows * row_h + 2 * self.frameWidth() + 2)

    def set_selected_id(self, tool_id: str | None) -> None:
        self.blockSignals(True)
        self.clearSelection()
        if tool_id in self.rows:
            self.rows[tool_id].setSelected(True)
        self.blockSignals(False)

    def _menu(self, pos) -> None:
        it = self.itemAt(pos)
        if it is not None:
            tool_id = it.data(0, Qt.ItemDataRole.UserRole)
            self.page.select_tool(tool_id)
            self.page.host.show_tool_menu(tool_id, self.viewport().mapToGlobal(pos))


class HomePage(QWidget):
    def __init__(self, host: "MainWindow"):
        super().__init__()
        self.host = host
        self.selected: str | None = None
        self.views: dict[str, Selectable] = {}
        self.tool_list: ToolList | None = None
        self.view = host.settings.get("home_view", "full")
        if self.view not in VIEWS:
            self.view = "full"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        root.addWidget(self.splitter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        scroll.setWidget(content)
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(32, 28, 32, 28)
        self.body.setSpacing(12)
        scroll.setMinimumWidth(360)  # mindestens eine Karte samt Rand
        self.splitter.addWidget(scroll)

        titles = QVBoxLayout()
        titles.addWidget(label(tr("home.title"), "PageTitle"))
        self.subtitle = label("", "PageSubtitle", wrap=True)
        titles.addWidget(self.subtitle)
        search_row, buttons = QHBoxLayout(), QHBoxLayout()
        self.search = QLineEdit(placeholderText="🔍  " + tr("home.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(150)
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self.refresh)
        search_row.addWidget(self.search)
        buttons.addWidget(self._view_switch())
        self.filter_btn = make_button(tr("home.filter"), on_click=self._show_filter_menu)
        self.filter_btn.setIcon(library_icon("list-filter", 16))
        buttons.addWidget(self.filter_btn)
        buttons.addWidget(make_button(tr("home.open_store"), primary=True, on_click=host.show_store))
        buttons.addStretch()
        controls = QHBoxLayout()
        controls.addWidget(ResponsiveRow(search_row, buttons))
        # Kopfzeile: bei wenig Platz rutschen Suche und Buttons unter den Titel (und notfalls untereinander)
        self.body.addWidget(ResponsiveRow(titles, controls))

        self.details = DetailsPanel(host, self.search)
        self.details.closed.connect(self.clear_selection)
        self.details.hide()
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 1)

        # OmniWrench ist für Windows-Clients gedacht; auf Servern fehlen z. B. RSAT-Capabilities
        if is_windows_server():
            self.body.addWidget(label(tr("home.server_notice"), "Notice", wrap=True))

        # Aktiver Kategorie-Filter als "Chip" mit Entfernen-Knopf
        self.category_filter: tuple[str, ...] = ()
        self.filter_chip = make_button("", on_click=lambda: self.set_category_filter(()))
        self.filter_chip.setObjectName("FilterChip")
        self.filter_chip.setToolTip(tr("home.filter_clear"))
        self.filter_chip.hide()
        self.body.addWidget(self.filter_chip, alignment=Qt.AlignmentFlag.AlignLeft)

        self.sections = QVBoxLayout()
        self.sections.setSpacing(8)
        self.body.addLayout(self.sections)
        self.body.addStretch()

        host.manager.toolsChanged.connect(self.refresh)
        host.catalogChanged.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------ Ansicht
    def _view_switch(self) -> QWidget:
        box = QFrame()
        box.setObjectName("Segmented")
        lay = QHBoxLayout(box)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self.view_group = QButtonGroup(self)
        self.view_buttons: dict[str, QToolButton] = {}
        for view in VIEWS:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setChecked(view == self.view)
            btn.setIcon(library_icon(VIEW_ICONS[view], 16))
            btn.setIconSize(QSize(16, 16))
            btn.setToolTip(tr(f"home.view_{view}"))
            btn.setAccessibleName(tr(f"home.view_{view}"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, v=view: self.set_view(v))
            self.view_group.addButton(btn)
            self.view_buttons[view] = btn
            lay.addWidget(btn)
        return box

    def set_view(self, view: str) -> None:
        if view not in VIEWS:
            return
        self.view_buttons[view].setChecked(True)
        if view != self.view:
            self.view = view
            self.host.settings.set("home_view", view)
            self.refresh()

    # ------------------------------------------------------------ Auswahl
    def select_tool(self, tool_id: str) -> None:
        tool = self.host.manager.get(tool_id)
        if tool is None:
            return self.clear_selection()
        self.selected = tool_id
        self._mark_selection()
        self.details.show_item(ToolItem.for_home(tool, self.host))
        if self.details.isHidden():
            self.details.show()
            total = max(self.splitter.width(), 900)
            side = side_width(total)
            self.splitter.setSizes([total - side, side])

    def clear_selection(self) -> None:
        self.selected = None
        self._mark_selection()
        self.details.hide()

    def _mark_selection(self) -> None:
        for tid, widget in self.views.items():
            widget.set_selected(tid == self.selected)
        if self.tool_list is not None:
            self.tool_list.set_selected_id(self.selected)

    # ------------------------------------------------------------ Filter
    def set_category_filter(self, path: tuple[str, ...] | list[str]) -> None:
        """Zeigt nur Tools dieser Kategorie; () = alle."""
        self.category_filter = tuple(path)
        if self.category_filter:
            self.filter_chip.setText(" › ".join(self.category_filter) + "   ✕")
            self.filter_chip.show()
        else:
            self.filter_chip.hide()
        self.filter_btn.setProperty("active", bool(self.category_filter))
        repolish(self.filter_btn)
        self.refresh()

    def _show_filter_menu(self) -> None:
        menu = QMenu(self)
        act = menu.addAction(tr("home.filter_all"), lambda: self.set_category_filter(()))
        act.setCheckable(True)
        act.setChecked(not self.category_filter)
        menu.addSeparator()
        paths: set[tuple[str, ...]] = set()
        for tool in self.host.manager.tools.values():
            path = tuple(tool.manifest.category_path)
            paths.update(path[:i] for i in range(1, len(path) + 1))
        for path in sorted(paths):
            count = sum(1 for t in self.host.manager.tools.values()
                        if tuple(t.manifest.category_path[:len(path)]) == path)
            text = "      " * (len(path) - 1) + f"{path[-1]}  ({count})"
            act = menu.addAction(text, lambda p=path: self.set_category_filter(p))
            act.setCheckable(True)
            act.setChecked(path == self.category_filter)
        menu.exec(self.filter_btn.mapToGlobal(self.filter_btn.rect().bottomLeft()))

    # ------------------------------------------------------------ Aufbau
    def refresh(self) -> None:
        clear_layout(self.sections)
        self.views = {}
        self.tool_list = None
        tools = list(self.host.manager.tools.values())
        updates = self.host.tool_updates
        n_upd = sum(1 for t in tools if t.id in updates)
        self.subtitle.setText(
            tr("home.subtitle", count=len(tools)) + (" · " + tr("home.subtitle_updates", count=n_upd) if n_upd else "")
        )

        if not tools:
            box = QVBoxLayout()
            box.addSpacing(40)
            box.addWidget(label(tr("home.empty_title"), "CardTitle"), alignment=Qt.AlignmentFlag.AlignCenter)
            box.addWidget(label(tr("home.empty_text"), "Muted"), alignment=Qt.AlignmentFlag.AlignCenter)
            self.sections.addLayout(box)
            self.clear_selection()
            return

        if self.category_filter:
            n = len(self.category_filter)
            tools = [t for t in tools if tuple(t.manifest.category_path[:n]) == self.category_filter]
        items = [ToolItem.for_home(t, self.host) for t in tools]
        query = self.search.text().strip().lower()
        if query:
            items = [i for i in items if query in i.search_text()]
        items.sort(key=lambda i: i.manifest.display_name.lower())

        if not items:
            self.sections.addWidget(label(tr("common.no_results"), "Muted"))
        elif self.view == "list":
            self.tool_list = ToolList(self)
            for item in items:
                self.tool_list.add(item)
            self.tool_list.fit_height()
            self.sections.addWidget(self.tool_list)
        else:
            groups: dict[str, list[ToolItem]] = {}
            for item in items:
                groups.setdefault(item.manifest.category_path[0], []).append(item)
            for category in sorted(groups):
                self.sections.addSpacing(10)
                self.sections.addWidget(label(category.upper(), "SectionTitle"))
                holder = QWidget()
                if self.view == "full":
                    flow = ColumnFlowLayout(holder, min_width=280, spacing=14)
                else:
                    flow = FlowLayout(holder, spacing=6 if self.view == "small" else 10)
                for item in groups[category]:
                    widget = self._tile(item)
                    self.views[item.id] = widget
                    flow.addWidget(widget)
                self.sections.addWidget(holder)
        if items:
            self.sections.addSpacing(6)
            self.sections.addWidget(label(tr("home.hint"), "Muted"))

        # Auswahl nach dem Neuaufbau beibehalten (z. B. nach Update, Ansichts- oder Sprachwechsel)
        if self.selected and (tool := self.host.manager.get(self.selected)):
            self._mark_selection()
            self.details.show_item(ToolItem.for_home(tool, self.host))
        else:
            self.clear_selection()

    def _tile(self, item: ToolItem) -> QWidget:
        if self.view == "full":
            return ToolCard(item, self.host, self.select_tool, self.host.open_tool, self.host.show_tool_menu)
        if self.view == "small":
            return SmallTile(item, self)
        return ToolTile(item, self)

"""Home-Tab: installierte Tools als kompakte Kacheln (Symbol + Name), gruppiert nach Kategorie.

Ein Klick zeigt rechts eine Detail-Leiste mit Beschreibung und Metadaten,
ein Doppelklick startet das Tool, ein Rechtsklick öffnet das Kontextmenü.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QHBoxLayout, QLineEdit, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from omniwrench.core.i18n import tr
from omniwrench.core.tool_manager import InstalledTool

from .widgets import FlowLayout, clear_layout, label, make_button, tool_icon

if TYPE_CHECKING:
    from .main_window import MainWindow


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ToolTile(QFrame):
    SIZE = QSize(128, 122)
    ICON = 56

    def __init__(self, tool: InstalledTool, page: "HomePage", has_update: bool):
        super().__init__()
        self.tool = tool
        self.page = page
        self.setObjectName("ToolTile")
        self.setFixedSize(self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tool.manifest.display_description)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 8)
        lay.setSpacing(6)
        icon = label("")
        icon.setPixmap(tool_icon(tool.manifest, tool.path, self.ICON).pixmap(self.ICON, self.ICON))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)
        name = label(tool.manifest.display_name, "TileName", wrap=True)
        name.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(name, 1)

        if has_update:  # kleiner Punkt oben rechts
            dot = label("", "UpdateDot", parent=self)
            dot.setFixedSize(10, 10)
            dot.move(self.SIZE.width() - 18, 8)
            dot.setToolTip(tr("home.update_badge", version=page.host.tool_updates[tool.id].manifest.version))

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        _repolish(self)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.page.select_tool(self.tool.id)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.page.host.open_tool(self.tool.id)

    def contextMenuEvent(self, event):  # noqa: N802
        self.page.host.show_tool_menu(self.tool.id, event.globalPos())


class DetailsPanel(QFrame):
    """Rechte Seitenleiste mit Beschreibung, Metadaten und Aktionen des gewählten Tools."""

    def __init__(self, page: "HomePage"):
        super().__init__()
        self.page = page
        self.host = page.host
        self.setObjectName("DetailsPanel")
        self.setMinimumWidth(280)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        self.content = QWidget()
        self.content.setObjectName("DetailsContent")
        scroll.setWidget(self.content)
        self.lay = QVBoxLayout(self.content)
        self.lay.setContentsMargins(20, 16, 20, 16)
        self.lay.setSpacing(10)

    def show_tool(self, tool: InstalledTool) -> None:
        clear_layout(self.lay)
        m = tool.manifest
        host = self.host

        top = QHBoxLayout()
        top.addStretch()
        close = make_button("✕", on_click=self.page.clear_selection)
        close.setObjectName("FlatButton")
        close.setToolTip(tr("details.close"))
        top.addWidget(close)
        self.lay.addLayout(top)

        icon = label("")
        icon.setPixmap(tool_icon(m, tool.path, 72).pixmap(72, 72))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(icon)
        title = label(m.display_name, "PageTitle", wrap=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(title)
        sub = label(f"v{m.version} · {' › '.join(m.category_path)}", "Muted", wrap=True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(sub)

        actions = QHBoxLayout()
        actions.addWidget(make_button(tr("common.open"), primary=True, on_click=lambda: host.open_tool(m.id)), 1)
        actions.addWidget(make_button(tr("toolmenu.settings"), on_click=lambda: host.open_tool_settings(m.id)), 1)
        self.lay.addLayout(actions)
        upd = host.tool_updates.get(m.id)
        if upd:
            self.lay.addWidget(make_button(tr("toolmenu.update_to", version=upd.manifest.version), primary=True,
                                           on_click=lambda: host.install_entry(upd)))

        self.lay.addSpacing(6)
        self.lay.addWidget(label(tr("details.description").upper(), "SectionTitle"))
        self.lay.addWidget(label(m.display_long_description or "–", wrap=True))

        self.lay.addSpacing(6)
        self.lay.addWidget(label(tr("details.info").upper(), "SectionTitle"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setVerticalSpacing(6)
        reqs = m.requirements.summary()
        rows = [
            (tr("details.version"), m.version),
            (tr("details.category"), " › ".join(m.category_path)),
            (tr("details.author"), m.author or "–"),
            (tr("details.id"), m.id),
            (tr("details.requirements"), "\n".join(reqs) if reqs else tr("details.none")),
        ]
        if m.homepage:
            rows.append((tr("details.homepage"), f"<a href='{m.homepage}'>{m.homepage}</a>"))
        for key, value in rows:
            val = label(value, wrap=True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            val.setOpenExternalLinks(True)
            form.addRow(label(key, "Muted"), val)
        self.lay.addLayout(form)

        self.lay.addStretch()
        bottom = QHBoxLayout()
        bottom.addWidget(make_button(tr("toolmenu.open_folder"), on_click=lambda: host.open_tool_folder(m.id)))
        bottom.addStretch()
        bottom.addWidget(make_button(tr("toolmenu.uninstall"), danger=True, on_click=lambda: host.uninstall_tool(m.id)))
        self.lay.addLayout(bottom)


class HomePage(QWidget):
    def __init__(self, host: "MainWindow"):
        super().__init__()
        self.host = host
        self.selected: str | None = None
        self.tiles: dict[str, ToolTile] = {}

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
        self.splitter.addWidget(scroll)

        self.details = DetailsPanel(self)
        self.details.hide()
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 1)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label(tr("home.title"), "PageTitle"))
        self.subtitle = label("", "PageSubtitle")
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)
        self.search = QLineEdit(placeholderText="🔍  " + tr("home.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(200)
        self.search.setMaximumWidth(280)
        self.search.textChanged.connect(self.refresh)
        header.addWidget(self.search, alignment=Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(make_button(tr("home.open_store"), primary=True, on_click=host.show_store),
                         alignment=Qt.AlignmentFlag.AlignVCenter)
        self.body.addLayout(header)

        self.sections = QVBoxLayout()
        self.sections.setSpacing(8)
        self.body.addLayout(self.sections)
        self.body.addStretch()

        host.manager.toolsChanged.connect(self.refresh)
        host.catalogChanged.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------ Auswahl
    def select_tool(self, tool_id: str) -> None:
        tool = self.host.manager.get(tool_id)
        if tool is None:
            return self.clear_selection()
        self.selected = tool_id
        for tid, tile in self.tiles.items():
            tile.set_selected(tid == tool_id)
        self.details.show_tool(tool)
        if self.details.isHidden():
            self.details.show()
            total = max(self.splitter.width(), 900)
            self.splitter.setSizes([total - 340, 340])

    def clear_selection(self) -> None:
        self.selected = None
        for tile in self.tiles.values():
            tile.set_selected(False)
        self.details.hide()

    # ------------------------------------------------------------ Aufbau
    def refresh(self) -> None:
        clear_layout(self.sections)
        self.tiles = {}
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

        query = self.search.text().strip().lower()
        if query:
            tools = [t for t in tools if query in (t.manifest.display_name + t.manifest.display_description
                                                   + "/".join(t.manifest.category_path)
                                                   + " ".join(t.manifest.tags)).lower()]
        groups: dict[str, list[InstalledTool]] = {}
        for t in sorted(tools, key=lambda t: t.manifest.display_name.lower()):
            groups.setdefault(t.manifest.category_path[0], []).append(t)

        for category in sorted(groups):
            self.sections.addSpacing(10)
            self.sections.addWidget(label(category.upper(), "SectionTitle"))
            holder = QWidget()
            flow = FlowLayout(holder, spacing=10)
            for t in groups[category]:
                tile = ToolTile(t, self, t.id in updates)
                self.tiles[t.id] = tile
                flow.addWidget(tile)
            self.sections.addWidget(holder)
        if not groups:
            self.sections.addWidget(label(tr("common.no_results"), "Muted"))
        else:
            self.sections.addSpacing(6)
            self.sections.addWidget(label(tr("home.hint"), "Muted"))

        # Auswahl nach dem Neuaufbau beibehalten (z. B. nach Update oder Sprachwechsel)
        if self.selected and self.host.manager.get(self.selected):
            if self.selected in self.tiles:
                self.tiles[self.selected].set_selected(True)
            self.details.show_tool(self.host.manager.get(self.selected))
        else:
            self.clear_selection()

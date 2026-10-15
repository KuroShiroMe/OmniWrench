"""Home-Tab: Übersicht der installierten Tools als Kacheln, gruppiert nach Kategorie."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from omniwrench.core.i18n import tr
from omniwrench.core.tool_manager import InstalledTool

from .widgets import FlowLayout, clear_layout, label, make_button, tool_icon

if TYPE_CHECKING:
    from .main_window import MainWindow


class ToolCard(QFrame):
    SIZE = QSize(280, 150)

    def __init__(self, tool: InstalledTool, host: "MainWindow", update_version: str | None):
        super().__init__()
        self.tool = tool
        self.host = host
        self.setObjectName("ToolCard")
        self.setFixedSize(self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        m = tool.manifest
        self.setToolTip(m.display_long_description)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(12)
        icon = label("")
        icon.setPixmap(tool_icon(m, tool.path, 44).pixmap(44, 44))
        head.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        name = label(m.display_name, "CardTitle")
        titles.addWidget(name)
        titles.addWidget(label(f"v{m.version} · {' › '.join(m.category_path)}", "CardMeta"))
        head.addLayout(titles, 1)
        lay.addLayout(head)

        desc = label(m.display_description, "CardDesc", wrap=True)
        desc.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(desc, 1)

        if update_version:
            badges = QHBoxLayout()
            badges.addWidget(label(tr("home.update_badge", version=update_version), "Badge"))
            badges.addStretch()
            lay.addLayout(badges)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.host.open_tool(self.tool.id)

    def contextMenuEvent(self, event):  # noqa: N802
        self.host.show_tool_menu(self.tool.id, event.globalPos())


class HomePage(QWidget):
    def __init__(self, host: "MainWindow"):
        super().__init__()
        self.host = host
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(32, 28, 32, 28)
        self.body.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label(tr("home.title"), "PageTitle"))
        self.subtitle = label("", "PageSubtitle")
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)
        self.search = QLineEdit(placeholderText="🔍  " + tr("home.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(140)
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

    def refresh(self) -> None:
        clear_layout(self.sections)
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
            flow = FlowLayout(holder)
            for t in groups[category]:
                upd = updates.get(t.id)
                flow.addWidget(ToolCard(t, self.host, upd.manifest.version if upd else None))
            self.sections.addWidget(holder)
        if not groups:
            self.sections.addWidget(label(tr("common.no_results"), "Muted"))

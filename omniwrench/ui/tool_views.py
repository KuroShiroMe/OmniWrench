"""Gemeinsame Bausteine für Home und Store.

* ToolItem      - ein Tool aus Sicht der Oberfläche (installiert und/oder im Store-Katalog)
* ToolCard      - Vollansicht: Symbol + Titel, Screenshot-Karussell, Kurzbeschreibung, ein Aktions-Button
* DetailsPanel  - rechte Leiste mit allen Metadaten, Screenshots und Aktionen
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable
from urllib.parse import unquote

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from omniwrench.core import system
from omniwrench.core.i18n import tr
from omniwrench.core.manifest import ToolManifest
from omniwrench.core.repository import CatalogEntry
from omniwrench.core.tool_manager import InstalledTool
from omniwrench.core.versioning import is_newer

from .screenshots import ScreenshotCarousel, ScreenshotViewer, ShotRef
from .widgets import ResponsiveRow, accent_color, breakable, clear_layout, label, make_button, tag_links, tool_icon

if TYPE_CHECKING:
    from .main_window import MainWindow


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


@dataclass
class ToolItem:
    manifest: ToolManifest                  # angezeigte Metadaten (Home: installiert, Store: Katalog)
    installed: InstalledTool | None = None
    entry: CatalogEntry | None = None       # Eintrag im Store-Katalog (falls geladen)
    update: CatalogEntry | None = None      # neuere Version im Store

    @property
    def id(self) -> str:
        return self.manifest.id

    @classmethod
    def for_home(cls, tool: InstalledTool, host: "MainWindow") -> "ToolItem":
        catalog = host.catalog.entries if host.catalog else {}
        return cls(tool.manifest, tool, catalog.get(tool.id), host.tool_updates.get(tool.id))

    @classmethod
    def for_store(cls, entry: CatalogEntry, host: "MainWindow") -> "ToolItem":
        installed = host.manager.get(entry.manifest.id)
        update = entry if installed and is_newer(entry.manifest.version, installed.manifest.version) else None
        return cls(entry.manifest, installed, entry, update)

    @property
    def runnable(self) -> bool:
        return self.installed is not None or system.supports_platform(self.manifest.platforms)

    def icon(self, size: int) -> QPixmap:
        path = self.installed.path if self.installed and self.manifest is self.installed.manifest else None
        return tool_icon(self.manifest, path, size).pixmap(size, size)

    def screenshots(self) -> list[ShotRef]:
        """Bilder aus dem Tool-Ordner (installiert), sonst aus dem Store-Katalog."""
        if self.installed is not None:
            m = self.installed.manifest
            local = [ShotRef(m.screenshot_caption(s), path=self.installed.path / s["file"])
                     for s in m.screenshot_list]
            if local and all(r.path.is_file() for r in local):
                return local
        if self.entry is not None:
            m = self.entry.manifest
            return [ShotRef(m.screenshot_caption(s), url=s["url"], sha256=s.get("sha256", ""))
                    for s in m.screenshot_list if s.get("url")]
        return []

    def search_text(self) -> str:
        m = self.manifest
        return (m.display_name + m.display_description + "/".join(m.category_path) + " ".join(m.tags)).lower()


def platform_text(manifest: ToolManifest) -> str:
    return ", ".join(system.platform_name(p) for p in manifest.platforms)


def primary_action(item: ToolItem, host: "MainWindow") -> QWidget:
    """Der eine Button einer Karte: Installieren, Update oder Öffnen (bzw. Hinweis auf das Betriebssystem)."""
    m = item.manifest
    if item.installed is None and not item.runnable:
        hint = label(tr("store.platform_only", platforms=platform_text(m)), "CardMeta", wrap=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return hint
    if item.installed is None:
        return make_button(tr("store.install"), primary=True, on_click=lambda: host.install_entry(item.entry))
    if item.update is not None:
        return make_button(tr("store.update_to", version=item.update.manifest.version), primary=True,
                           on_click=lambda: host.install_entry(item.update))
    return make_button(tr("common.open"), on_click=lambda: host.open_tool(item.id))


class Selectable:
    """Mixin für Elemente, die ein Tool darstellen (Karte, Kachel): Klick wählt, Doppelklick öffnet."""

    item: ToolItem
    activated_cb: Callable[[str], None]
    opened_cb: Callable[[str], None]
    menu_cb: Callable[[str, object], None] | None

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)  # type: ignore[attr-defined]
        repolish(self)  # type: ignore[arg-type]

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.activated_cb(self.item.id)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.opened_cb(self.item.id)

    def contextMenuEvent(self, event):  # noqa: N802
        if self.menu_cb is not None and self.item.installed is not None:
            self.menu_cb(self.item.id, event.globalPos())


class ToolCard(Selectable, QFrame):
    """Vollansicht eines Tools: Symbol und Titel, darunter Screenshots, Kurzbeschreibung und Aktion."""

    def __init__(self, item: ToolItem, host: "MainWindow", on_select: Callable[[str], None],
                 on_open: Callable[[str], None], on_menu: Callable[[str, object], None] | None = None):
        super().__init__()
        self.item = item
        self.activated_cb, self.opened_cb, self.menu_cb = on_select, on_open, on_menu
        self.setObjectName("ToolCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        m = item.manifest
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        icon = label("")
        icon.setPixmap(item.icon(36))
        head.addWidget(icon)
        title = label(m.display_name, "CardTitleLarge", wrap=True)
        head.addWidget(title, 1)
        if item.update is not None and item.installed is not None:  # kleiner Punkt wie bei den Kacheln
            dot = label("", "UpdateDot")
            dot.setFixedSize(10, 10)
            dot.setToolTip(tr("home.update_badge", version=item.update.manifest.version))
            head.addWidget(dot, alignment=Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)

        self.carousel = ScreenshotCarousel(item.screenshots(), item.icon(96), accent_color(m))
        self.carousel.clicked.connect(lambda: on_select(item.id))
        lay.addWidget(self.carousel)

        desc = label(m.display_description, "CardDesc", wrap=True)
        desc.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        lay.addWidget(desc)
        lay.addStretch()
        action = primary_action(item, host)
        if isinstance(action, QPushButton):
            action.setMinimumWidth(150)
            row = QHBoxLayout()
            row.addWidget(action)
            row.addStretch()
            lay.addLayout(row)
        else:
            lay.addWidget(action)


class DetailsPanel(QFrame):
    """Rechte Seitenleiste mit allen Metadaten, Screenshots und Aktionen des gewählten Tools."""

    closed = Signal()

    def __init__(self, host: "MainWindow", search: QLineEdit):
        super().__init__()
        self.host = host
        self.search = search  # Klick auf ein Tag sucht danach
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

    def show_item(self, item: ToolItem) -> None:
        clear_layout(self.lay)
        m = item.manifest
        host = self.host

        top = QHBoxLayout()
        icon = label("")
        icon.setPixmap(item.icon(48))
        top.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label(m.display_name, "DetailsTitle", wrap=True))
        titles.addWidget(label(f"v{m.version} · {' › '.join(m.category_path)}", "Muted", wrap=True))
        top.addLayout(titles, 1)
        close = make_button("✕", on_click=self.closed.emit)
        close.setObjectName("FlatButton")
        close.setToolTip(tr("details.close"))
        top.addWidget(close, alignment=Qt.AlignmentFlag.AlignTop)
        self.lay.addLayout(top)

        self._add_actions(item)

        shots = item.screenshots()
        carousel = ScreenshotCarousel(shots, item.icon(96), accent_color(m))
        caption = label("", "Muted", wrap=True)

        def sync(_i=0):
            shot = carousel.current()
            caption.setText(shot.caption if shot else "")
            caption.setVisible(bool(shot and shot.caption))

        carousel.indexChanged.connect(sync)
        if shots:
            carousel.clicked.connect(lambda: ScreenshotViewer(
                m.display_name, shots, carousel.index, self, item.icon(96), accent_color(m)).exec())
        self.lay.addSpacing(4)
        self.lay.addWidget(carousel)
        self.lay.addWidget(caption)
        sync()

        self.lay.addSpacing(6)
        self.lay.addWidget(label(tr("details.description").upper(), "SectionTitle"))
        self.lay.addWidget(label(m.display_long_description or "–", wrap=True))

        self.lay.addSpacing(6)
        self.lay.addWidget(label(tr("details.info").upper(), "SectionTitle"))
        self.lay.addLayout(self._info_form(item))

        self.lay.addStretch()
        if item.installed is not None:
            folder, uninstall = QHBoxLayout(), QHBoxLayout()
            folder.addWidget(make_button(tr("toolmenu.open_folder"), on_click=lambda: host.open_tool_folder(m.id)))
            folder.addStretch()
            uninstall.addWidget(make_button(tr("toolmenu.uninstall"), danger=True,
                                            on_click=lambda: host.uninstall_tool(m.id)))
            self.lay.addWidget(ResponsiveRow(folder, uninstall))  # schmale Leiste: Buttons untereinander

    def _add_actions(self, item: ToolItem) -> None:
        host, m = self.host, item.manifest
        if item.installed is None:
            if item.runnable:
                btn = make_button(tr("store.install"), primary=True, on_click=lambda: host.install_entry(item.entry))
                self.lay.addWidget(btn)
            else:
                self.lay.addWidget(label(tr("store.platform_only", platforms=platform_text(m)), "Notice", wrap=True))
            return
        actions = QHBoxLayout()
        actions.addWidget(make_button(tr("common.open"), primary=item.update is None,
                                      on_click=lambda: host.open_tool(m.id)), 1)
        actions.addWidget(make_button(tr("toolmenu.settings"), on_click=lambda: host.open_tool_settings(m.id)), 1)
        self.lay.addLayout(actions)
        if item.update is not None:
            self.lay.addWidget(make_button(tr("toolmenu.update_to", version=item.update.manifest.version),
                                           primary=True, on_click=lambda: host.install_entry(item.update)))

    def _info_form(self, item: ToolItem) -> QFormLayout:
        m = item.manifest
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setVerticalSpacing(6)
        reqs = m.requirements.summary()
        rows = [(tr("details.version"), m.version)]
        if item.installed is not None and item.installed.manifest.version != m.version:
            rows.append((tr("details.installed_version"), item.installed.manifest.version))
        elif item.update is not None and item.update.manifest.version != m.version:
            rows.append((tr("details.available_version"), item.update.manifest.version))
        rows += [
            (tr("details.category"), " › ".join(m.category_path)),
            (tr("details.platforms"), platform_text(m)),
            (tr("details.author"), m.author or "–"),
            (tr("details.id"), m.id),
            (tr("details.requirements"), breakable("\n".join(reqs)) if reqs else tr("details.none")),
        ]
        if item.entry is not None:
            rows.append((tr("details.source"), item.entry.repo_name))
        if m.homepage:
            url = html.escape(m.homepage, quote=True)
            rows.append((tr("details.homepage"), f"<a href='{url}'>{breakable(html.escape(m.homepage))}</a>"))
        for key, value in rows:
            val = label(value, wrap=True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            val.setOpenExternalLinks(True)
            form.addRow(label(key, "Muted"), val)
        if m.tags:
            tags = label(tag_links(m.tags), wrap=True)
            tags.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            tags.linkActivated.connect(lambda tag: self.search.setText(unquote(tag)))
            form.insertRow(2, label(tr("details.tags"), "Muted"), tags)
        return form


def side_width(total: int) -> int:
    """Breite der Detail-Leiste: wächst mit dem Fenster (klein 320, große Monitore bis 600)."""
    return int(min(max(total * 0.3, 320), 600))

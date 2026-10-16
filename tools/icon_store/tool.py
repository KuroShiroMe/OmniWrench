"""Icon Store: Symbole durchsuchen, ansehen und in verschiedenen Formaten/Größen speichern."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListView, QPushButton, QScrollArea, QSplitter, QStyle,
    QStyledItemDelegate, QVBoxLayout, QWidget,
)

from omniwrench.core import icons
from omniwrench.sdk import ToolBase

from . import export
from .export import Style

GRID_ICON = 40
PREVIEW = 160


class IconModel(QAbstractListModel):
    """Alle Symbole der Bibliothek; Vorschaubilder werden erst beim Anzeigen gerendert."""

    NAME = Qt.ItemDataRole.UserRole
    SEARCH = Qt.ItemDataRole.UserRole + 1
    CATEGORIES = Qt.ItemDataRole.UserRole + 2

    def __init__(self, color: str):
        super().__init__()
        self.names = list(icons.library_names())
        self.color = color
        self._cache: dict[str, QIcon] = {}
        self._search = {n: " ".join([n, n.replace("-", " "), *icons.library_info(n)["tags"]]).lower()
                        for n in self.names}

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.names)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        name = self.names[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return name
        if role == Qt.ItemDataRole.DecorationRole:
            if name not in self._cache:
                svg = export.build_svg(icons.library_svg(name), Style(color=self.color))
                self._cache[name] = QIcon(QPixmap.fromImage(export.render(svg, GRID_ICON * 2)))
            return self._cache[name]
        if role == Qt.ItemDataRole.ToolTipRole:
            return name + "\n" + ", ".join(icons.library_info(name)["tags"][:12])
        if role == self.NAME:
            return name
        if role == self.SEARCH:
            return self._search[name]
        if role == self.CATEGORIES:
            return icons.library_info(name)["categories"]
        return None


class IconDelegate(QStyledItemDelegate):
    """Rasterzelle: Symbol oben, Name darunter - bei Bedarf zweizeilig, Umbruch nach Bindestrich."""

    CELL = QSize(118, 100)

    def sizeHint(self, option, index):  # noqa: N802
        return self.CELL

    @staticmethod
    def _lines(name: str, fm: QFontMetrics, width: int) -> list[str]:
        if fm.horizontalAdvance(name) <= width:
            return [name]
        cuts = [i + 1 for i, ch in enumerate(name) if ch == "-"]
        fitting = [c for c in cuts if fm.horizontalAdvance(name[:c]) <= width]
        cut = fitting[-1] if fitting else (cuts[0] if cuts else len(name))
        first, rest = name[:cut], name[cut:]
        lines = [fm.elidedText(first, Qt.TextElideMode.ElideRight, width)]
        if rest:
            lines.append(fm.elidedText(rest, Qt.TextElideMode.ElideRight, width))
        return lines

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(3, 3, -3, -3)
        pal = option.palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            color = pal.color(QPalette.ColorRole.Highlight)
            color.setAlpha(110 if selected else 40)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 10, 10)
        icon: QIcon = index.data(Qt.ItemDataRole.DecorationRole)
        icon_rect = QRect(rect.center().x() - GRID_ICON // 2, rect.top() + 10, GRID_ICON, GRID_ICON)
        icon.paint(painter, icon_rect)
        font = QFont(option.font)
        font.setPointSizeF(8.5)
        painter.setFont(font)
        fm = QFontMetrics(font)
        painter.setPen(pal.color(QPalette.ColorRole.Text if selected else QPalette.ColorRole.PlaceholderText))
        y = icon_rect.bottom() + 6
        for line in self._lines(index.data(IconModel.NAME), fm, rect.width() - 8):
            painter.drawText(QRect(rect.left(), y, rect.width(), fm.height()), Qt.AlignmentFlag.AlignHCenter, line)
            y += fm.height()
        painter.restore()


class IconFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.query = ""
        self.category = ""

    def set_filter(self, query: str, category: str) -> None:
        self.query, self.category = query.strip().lower(), category
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):  # noqa: N802
        idx = self.sourceModel().index(row, 0, parent)
        if self.category and self.category not in idx.data(IconModel.CATEGORIES):
            return False
        return all(word in idx.data(IconModel.SEARCH) for word in self.query.split())


class ColorButton(QPushButton):
    def __init__(self, color: str, on_change):
        super().__init__()
        self.on_change = on_change
        self.setFixedWidth(64)
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, color: str) -> None:
        self.color = color
        self.setStyleSheet(f"background: {color}; border: 1px solid #555; border-radius: 6px; min-height: 22px;")
        self.setToolTip(color)

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self.color), self, options=QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self.set_color(c.name())
            self.on_change()


class IconStore(ToolBase):
    def create_widget(self, parent=None) -> QWidget:
        tr = self.context.tr
        s = self.context.settings
        self.root = QWidget(parent)
        outer = QVBoxLayout(self.root)
        outer.setContentsMargins(16, 14, 16, 12)

        # ---- Kopfzeile: Suche + Filter
        top = QHBoxLayout()
        title = QLabel(tr("tool.name"))
        title.setObjectName("PageTitle")
        top.addWidget(title)
        top.addStretch()
        self.search = QLineEdit(placeholderText="🔍  " + tr("ui.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(260)
        top.addWidget(self.search)
        self.source = QComboBox()
        self.source.addItem(f"Lucide {icons.library_version()}", "lucide")
        self.source.setToolTip(tr("ui.source"))
        top.addWidget(self.source)
        self.category = QComboBox()
        self.category.setMinimumWidth(200)
        top.addWidget(self.category)
        outer.addLayout(top)
        self.count = QLabel()
        self.count.setObjectName("Muted")
        outer.addWidget(self.count)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        # ---- Raster
        grid_color = "#e6e8ec" if self.root.palette().window().color().lightness() < 128 else "#1d2129"
        self.model = IconModel(grid_color)
        self.proxy = IconFilter()
        self.proxy.setSourceModel(self.model)
        self.view = QListView()
        self.view.setModel(self.proxy)
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setIconSize(QSize(GRID_ICON, GRID_ICON))
        self.view.setGridSize(IconDelegate.CELL)
        self.view.setItemDelegate(IconDelegate(self.view))
        self.view.setMouseTracking(True)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setUniformItemSizes(True)
        self.view.setWordWrap(True)
        self.view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.view.setSpacing(4)
        self.view.setObjectName("IconGrid")
        self.view.selectionModel().currentChanged.connect(lambda cur, _prev: self._select(cur))
        self.view.doubleClicked.connect(lambda *_: self._save())
        splitter.addWidget(self.view)

        # ---- Details
        splitter.addWidget(self._build_details())
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([780, 380])

        categories = icons.library_categories()
        counts: dict[str, int] = {}
        for n in self.model.names:
            for c in icons.library_info(n)["categories"]:
                counts[c] = counts.get(c, 0) + 1
        self.category.addItem(tr("ui.all_categories", count=len(self.model.names)), "")
        for cid, title_ in sorted(categories.items(), key=lambda kv: kv[1].lower()):
            self.category.addItem(f"{title_}  ({counts.get(cid, 0)})", cid)

        self._timer = QTimer(self.root, singleShot=True, interval=150)
        self._timer.timeout.connect(self._apply_filter)
        self.search.textChanged.connect(lambda: self._timer.start())
        self.category.currentIndexChanged.connect(self._apply_filter)
        self._apply_filter()
        self.view.setCurrentIndex(self.proxy.index(0, 0))
        self.search.setFocus()
        return self.root

    # ------------------------------------------------------------ Details
    def _build_details(self) -> QWidget:
        tr = self.context.tr
        s = self.context.settings
        panel = QFrame()
        panel.setObjectName("DetailsPanel")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(scroll)
        content = QWidget()
        content.setObjectName("DetailsContent")
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(PREVIEW + 24)
        self.preview.setObjectName("IconPreview")
        lay.addWidget(self.preview)
        self.name_label = QLabel()
        self.name_label.setObjectName("PageTitle")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.name_label)

        # Name für Tool-Entwickler
        dev = QLabel(tr("ui.dev_name").upper())
        dev.setObjectName("SectionTitle")
        lay.addWidget(dev)
        row = QHBoxLayout()
        self.dev_name = QLineEdit()
        self.dev_name.setReadOnly(True)
        row.addWidget(self.dev_name, 1)
        copy = QPushButton(tr("ui.copy"))
        copy.clicked.connect(lambda: self._copy_text(self.dev_name.text()))
        row.addWidget(copy)
        lay.addLayout(row)

        info = QLabel(tr("ui.info").upper())
        info.setObjectName("SectionTitle")
        lay.addWidget(info)
        self.info_form = QFormLayout()
        self.info_form.setVerticalSpacing(4)
        self.lbl_categories = QLabel(wordWrap=True)
        self.lbl_tags = QLabel(wordWrap=True)
        self.lbl_source = QLabel(wordWrap=True)
        self.lbl_source.setOpenExternalLinks(True)
        for key, w in (("ui.categories", self.lbl_categories), ("ui.tags", self.lbl_tags),
                       ("ui.source", self.lbl_source)):
            cap = QLabel(tr(key))
            cap.setObjectName("Muted")
            self.info_form.addRow(cap, w)
        lay.addLayout(self.info_form)

        # Darstellung
        style_title = QLabel(tr("ui.style").upper())
        style_title.setObjectName("SectionTitle")
        lay.addWidget(style_title)
        form = QFormLayout()
        self.color_btn = ColorButton(s.get("default_color") or "#1f2937", self._refresh_preview)
        form.addRow(tr("ui.color"), self.color_btn)
        self.stroke = QDoubleSpinBox()
        self.stroke.setRange(0.5, 4.0)
        self.stroke.setSingleStep(0.25)
        self.stroke.setValue(2.0)
        self.stroke.valueChanged.connect(self._refresh_preview)
        form.addRow(tr("ui.stroke"), self.stroke)
        bg_row = QHBoxLayout()
        self.bg = QComboBox()
        for key in ("none", "square", "circle"):
            self.bg.addItem(tr(f"ui.bg_{key}"), key)
        self.bg.currentIndexChanged.connect(self._bg_changed)
        bg_row.addWidget(self.bg, 1)
        self.bg_color = ColorButton("#3b82f6", self._refresh_preview)
        self.bg_color.setEnabled(False)
        bg_row.addWidget(self.bg_color)
        form.addRow(tr("ui.background"), bg_row)
        lay.addLayout(form)

        # Export
        exp_title = QLabel(tr("ui.export").upper())
        exp_title.setObjectName("SectionTitle")
        lay.addWidget(exp_title)
        eform = QFormLayout()
        self.fmt = QComboBox()
        for f in export.FORMATS:
            self.fmt.addItem(tr(f"fmt.{f}"), f)
        self.fmt.setCurrentIndex(max(self.fmt.findData(s.get("default_format") or "png"), 0))
        self.fmt.currentIndexChanged.connect(self._fmt_changed)
        eform.addRow(tr("ui.format"), self.fmt)
        sizes_box = QWidget()
        grid = QGridLayout(sizes_box)
        grid.setContentsMargins(0, 0, 0, 0)
        self.size_checks: dict[int, QCheckBox] = {}
        default_sizes = set(s.get("default_sizes") or [256])
        for i, size in enumerate(export.SIZES):
            cb = QCheckBox(f"{size}")
            cb.setChecked(size in default_sizes)
            self.size_checks[size] = cb
            grid.addWidget(cb, i // 4, i % 4)
        eform.addRow(tr("ui.sizes"), sizes_box)
        self.custom_size = QLineEdit()
        self.custom_size.setPlaceholderText(tr("ui.custom_size_hint"))
        eform.addRow(tr("ui.custom_size"), self.custom_size)
        lay.addLayout(eform)
        self.fmt_hint = QLabel(wordWrap=True)
        self.fmt_hint.setObjectName("Muted")
        lay.addWidget(self.fmt_hint)

        btns = QHBoxLayout()
        clip = QPushButton(tr("ui.copy_image"))
        clip.clicked.connect(self._copy_image)
        btns.addWidget(clip)
        save = QPushButton(tr("ui.save_as"))
        save.setProperty("primary", True)
        save.clicked.connect(self._save)
        btns.addWidget(save)
        lay.addLayout(btns)
        self.status = QLabel(wordWrap=True)
        self.status.setObjectName("Muted")
        lay.addWidget(self.status)
        lay.addStretch()
        self._fmt_changed()
        return panel

    # ------------------------------------------------------------ Logik
    def _apply_filter(self) -> None:
        self.proxy.set_filter(self.search.text(), self.category.currentData() or "")
        self.count.setText(self.context.tr("ui.count", shown=self.proxy.rowCount(), total=len(self.model.names)))
        if self.proxy.rowCount() and not self.view.currentIndex().isValid():
            self.view.setCurrentIndex(self.proxy.index(0, 0))

    def _current_name(self) -> str | None:
        idx = self.view.currentIndex()
        return idx.data(IconModel.NAME) if idx.isValid() else None

    def _select(self, index) -> None:
        if not index.isValid():
            return
        name = index.data(IconModel.NAME)
        info = icons.library_info(name)
        titles = icons.library_categories()
        self.name_label.setText(name)
        self.dev_name.setText(name)
        self.dev_name.setToolTip(f'"icon": "{name}"')
        self.lbl_categories.setText(", ".join(titles.get(c, c) for c in info["categories"]) or "–")
        self.lbl_tags.setText(", ".join(info["tags"]) or "–")
        meta = icons.library_meta()
        self.lbl_source.setText(f"<a href='https://lucide.dev/icons/{name}'>Lucide {icons.library_version()}</a> · "
                                f"{meta.get('license', 'ISC')} – {self.context.tr('ui.license_hint')}")
        self._refresh_preview()

    def _style(self) -> Style:
        return Style(color=self.color_btn.color, stroke=self.stroke.value(), background=self.bg.currentData(),
                     bg_color=self.bg_color.color)

    def _svg(self, name: str) -> bytes:
        return export.build_svg(icons.library_svg(name), self._style())

    def _refresh_preview(self) -> None:
        name = self._current_name()
        if not name:
            return
        pix = QPixmap.fromImage(export.render(self._svg(name), PREVIEW * 2))
        pix.setDevicePixelRatio(2)
        self.preview.setPixmap(pix)

    def _bg_changed(self) -> None:
        has_bg = self.bg.currentData() != "none"
        self.bg_color.setEnabled(has_bg)
        # Auf farbigem Hintergrund ist ein weißes Symbol meist gewünscht (und umgekehrt)
        default = self.context.settings.get("default_color") or "#1f2937"
        if has_bg and self.color_btn.color == default:
            self.color_btn.set_color("#ffffff")
        elif not has_bg and self.color_btn.color == "#ffffff":
            self.color_btn.set_color(default)
        self._refresh_preview()

    def _fmt_changed(self) -> None:
        fmt = self.fmt.currentData()
        self.fmt_hint.setText(self.context.tr(f"fmt.{fmt}_hint"))
        multi = fmt in ("png", "jpg", "ico")
        for cb in self.size_checks.values():
            cb.setEnabled(multi or fmt == "pdf")
        self.custom_size.setEnabled(fmt != "svg")

    def _sizes(self) -> list[int]:
        sizes = [s for s, cb in self.size_checks.items() if cb.isChecked()]
        for part in self.custom_size.text().replace(";", ",").split(","):
            if part.strip().isdigit() and 1 <= int(part) <= 4096:
                sizes.append(int(part))
        return sorted(set(sizes)) or [256]

    def _copy_text(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.status.setText(self.context.tr("ui.copied", text=text))

    def _copy_image(self) -> None:
        name = self._current_name()
        if name:
            size = max(self._sizes())
            QApplication.clipboard().setImage(export.render(self._svg(name), size))
            self.status.setText(self.context.tr("ui.image_copied", size=size))

    def _save(self) -> None:
        name = self._current_name()
        if not name:
            return
        fmt = self.fmt.currentData()
        start = Path(self.context.settings.get("export_dir") or Path.home() / "Pictures")
        path, _ = QFileDialog.getSaveFileName(self.root, self.context.tr("ui.save_as"),
                                              str(start / f"{name}.{fmt}"), f"{fmt.upper()} (*.{fmt})")
        if not path:
            return
        try:
            written = export.export(Path(path), fmt, self._svg(name), self._sizes())
        except Exception as exc:  # noqa: BLE001
            self.status.setText("❌ " + str(exc))
            return
        self.context.settings.set("export_dir", str(Path(path).parent))
        msg = self.context.tr("ui.saved", count=len(written), path=str(written[0].parent))
        self.status.setText("✅ " + msg)
        self.context.notify(msg)

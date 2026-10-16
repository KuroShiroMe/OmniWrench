"""IconForge: Symbole aus vielen freien Paketen durchsuchen, ansehen und exportieren."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListView, QPushButton, QScrollArea, QSizePolicy, QSplitter, QStyle,
    QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget,
)

from omniwrench.sdk import ToolBase
from omniwrench.ui.widgets import library_icon

from . import export
from .export import Style
from .packs import IconRef, PackStore, load_licenses
from .wizard import PackWizard

GRID_ICON = 40
PREVIEW = 160
ALL_PACKS = "__all__"
GREEN, RED = "#16a34a", "#dc2626"


class IconModel(QAbstractListModel):
    """Symbole der gewählten Pakete; Vorschaubilder werden erst beim Anzeigen gerendert."""

    REF = Qt.ItemDataRole.UserRole
    SEARCH = Qt.ItemDataRole.UserRole + 1
    CATEGORIES = Qt.ItemDataRole.UserRole + 2

    def __init__(self, store: PackStore, color: str):
        super().__init__()
        self.store = store
        self.color = color
        self.refs: list[IconRef] = []
        self._search: list[str] = []
        self._cache: dict[IconRef, QIcon] = {}

    def set_refs(self, refs: list[IconRef]) -> None:
        self.beginResetModel()
        self.refs = refs
        names = {p: d["name"].lower() for p, d in self.store.defs.items()}
        self._search = []
        for r in refs:
            info = self.store.info(r)
            self._search.append(" ".join([r.name, r.name.replace("-", " ").replace("_", " "), names[r.pack],
                                          *info.get("tags", [])]).lower())
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.refs)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        ref = self.refs[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return ref.name
        if role == Qt.ItemDataRole.DecorationRole:
            if ref not in self._cache:
                try:
                    svg = export.build_svg(self.store.svg(ref), Style(color=self.color))
                    self._cache[ref] = QIcon(export.render_pixmap(svg, GRID_ICON))
                except Exception:  # noqa: BLE001 - defekte SVG nicht anzeigen, Raster läuft weiter
                    self._cache[ref] = QIcon()
            return self._cache[ref]
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{ref.name}\n{self.store.defs[ref.pack]['name']} · {ref.variant}"
        if role == self.REF:
            return ref
        if role == self.SEARCH:
            return self._search[index.row()]
        if role == self.CATEGORIES:
            return self.store.info(ref).get("categories", [])
        return None


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


class IconDelegate(QStyledItemDelegate):
    """Rasterzelle: Symbol oben, Name darunter - bei Bedarf zweizeilig, Umbruch nach Bindestrich."""

    CELL = QSize(118, 100)

    def sizeHint(self, option, index):  # noqa: N802
        return self.CELL

    @staticmethod
    def _lines(name: str, fm: QFontMetrics, width: int) -> list[str]:
        if fm.horizontalAdvance(name) <= width:
            return [name]
        cuts = [i + 1 for i, ch in enumerate(name) if ch in "-_"]
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
        for line in self._lines(index.data(Qt.ItemDataRole.DisplayRole), fm, rect.width() - 8):
            painter.drawText(QRect(rect.left(), y, rect.width(), fm.height()), Qt.AlignmentFlag.AlignHCenter, line)
            y += fm.height()
        painter.restore()


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
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.set_color(c.name())
            self.on_change()


class HeaderBar(QWidget):
    """Kopfzeile, die bei wenig Platz umbricht, statt das Tool breiter zu machen.

    Breit: alles in einer Zeile. Mittel: Titel und Suche, darunter die Filter. Schmal: die Filter
    zusätzlich auf zwei Zeilen verteilt (filters, dann more).
    """

    SPACING = 8

    def __init__(self, title: QWidget, search: tuple[QWidget, int], filters: list[tuple[QWidget, int]],
                 more: list[tuple[QWidget, int]]):
        super().__init__()
        self._title, self._search, self._filters, self._more = title, search, filters, more
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self._rows = [QHBoxLayout() for _ in range(3)]
        for row in self._rows:
            row.setSpacing(self.SPACING)
            box.addLayout(row)
        self._mode = -1
        self._arrange(0)

    def _layouts(self, mode: int) -> list[list[tuple[QWidget, int]]]:
        head = [(self._title, 0), self._search]
        if mode == 0:
            return [head + self._filters + self._more]
        if mode == 1:
            return [head, self._filters + self._more]
        return [head, self._filters, self._more]

    @staticmethod
    def _width(w: QWidget) -> int:
        """Platzbedarf: dehnbare Felder (Suche) mit Mindestbreite, alle anderen mit Wunschbreite."""
        expanding = w.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
        return max(w.minimumWidth(), (w.minimumSizeHint() if expanding else w.sizeHint()).width())

    def _needed(self, mode: int) -> int:
        return max(sum(self._width(w) for w, _ in row) + self.SPACING * (len(row) - 1) for row in self._layouts(mode))

    def _arrange(self, mode: int) -> None:
        self._mode = mode
        for row in self._rows:
            while row.count():
                row.takeAt(0)
        for row, items in zip(self._rows, self._layouts(mode)):
            for i, (w, stretch) in enumerate(items):
                row.addWidget(w, stretch)
                if mode == 0 and i == 0:
                    row.addStretch()
        self.updateGeometry()

    def minimumSizeHint(self):  # noqa: N802 - schmalste Anordnung bestimmt die Mindestbreite des Tools
        return QSize(self._needed(2), super().minimumSizeHint().height())

    def resizeEvent(self, event):  # noqa: N802
        width = event.size().width()
        mode = next((m for m in (0, 1) if self._needed(m) <= width), 2)
        if mode != self._mode:
            self._arrange(mode)
        super().resizeEvent(event)


def _section(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("SectionTitle")
    return lbl


class IconForge(ToolBase):
    def create_widget(self, parent=None) -> QWidget:
        tr = self.context.tr
        self.store = PackStore(self.context.data_dir)
        self.licenses = load_licenses()
        self.root = QWidget(parent)
        outer = QVBoxLayout(self.root)
        outer.setContentsMargins(16, 14, 16, 12)

        # ---- Kopfzeile
        # Breiten in Zeichen statt Pixeln, damit die Leiste mit Schrift und Skalierung mitwächst
        char = self.root.fontMetrics().averageCharWidth()
        title = QLabel(tr("tool.name"))
        title.setObjectName("PageTitle")
        self.search = QLineEdit(placeholderText="🔍  " + tr("ui.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(char * 26)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pack = QComboBox()
        self.pack.setMinimumContentsLength(18)
        self.pack.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.pack.setToolTip(tr("ui.pack_hint"))
        self.get_packs = QToolButton()
        self.get_packs.setIcon(library_icon("download", 18))
        self.get_packs.setToolTip(tr("ui.pack_get"))
        side = self.pack.sizeHint().height()
        self.get_packs.setFixedSize(side, side)
        self.get_packs.setIconSize(QSize(side * 3 // 5, side * 3 // 5))
        self.get_packs.clicked.connect(self._open_wizard)
        self.variant = QComboBox()
        self.variant.setMinimumContentsLength(9)
        self.variant.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.category = QComboBox()
        self.category.setMinimumContentsLength(16)
        self.category.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        outer.addWidget(HeaderBar(title, (self.search, 2), [(self.pack, 1), (self.get_packs, 0), (self.variant, 0)],
                                  [(self.category, 1)]))
        self.count = QLabel()
        self.count.setObjectName("Muted")
        outer.addWidget(self.count)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        grid_color = "#e6e8ec" if self.root.palette().window().color().lightness() < 128 else "#1d2129"
        self.model = IconModel(self.store, grid_color)
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
        self.view.setObjectName("IconGrid")
        # mindestens eine ganze Spalte, sonst schrumpft bei schmalem Fenster das Raster statt der Detailleiste
        scrollbar = self.view.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        self.view.setMinimumWidth(IconDelegate.CELL.width() + scrollbar + 2 * self.view.frameWidth() + 4)
        self.view.selectionModel().currentChanged.connect(lambda cur, _prev: self._select(cur))
        self.view.doubleClicked.connect(lambda *_: self._save())
        splitter.addWidget(self.view)
        splitter.addWidget(self._build_details())
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([char * 100, char * 52])

        self._timer = QTimer(self.root, singleShot=True, interval=150)
        self._timer.timeout.connect(self._apply_filter)
        self.search.textChanged.connect(lambda: self._timer.start())
        self.category.currentIndexChanged.connect(self._apply_filter)
        self.pack.currentIndexChanged.connect(self._pack_changed)
        self.variant.currentIndexChanged.connect(self._load_items)
        self._fill_packs(select="lucide")
        self.search.setFocus()
        return self.root

    # ------------------------------------------------------------ Pakete
    def _fill_packs(self, select: str) -> None:
        """Nur verfügbare (eingebaute oder geladene) Bibliotheken; weitere kommen über den Download-Assistenten."""
        tr = self.context.tr
        self.pack.blockSignals(True)
        self.pack.clear()
        self.pack.addItem(tr("ui.pack_all"), ALL_PACKS)
        for pid, spec in sorted(self.store.defs.items(), key=lambda kv: (not kv[1].get("builtin"), kv[1]["name"].lower())):
            if self.store.is_available(pid):
                self.pack.addItem(spec["name"], pid)
        index = self.pack.findData(select)
        self.pack.setCurrentIndex(index if index >= 0 else max(self.pack.findData("lucide"), 0))
        self.pack.blockSignals(False)
        self._pack_changed()

    def _open_wizard(self) -> None:
        current = self.pack.currentData()
        wizard = PackWizard(self.store, self.licenses, self.context, self.root,
                            select=current if current not in (ALL_PACKS, "lucide") else None)
        wizard.packDownloaded.connect(lambda pid: self._fill_packs(select=pid))
        wizard.packRemoved.connect(lambda pid: self._fill_packs(select=self.pack.currentData()
                                                                if self.pack.currentData() != pid else "lucide"))
        wizard.exec()
        wizard.deleteLater()

    def _pack_changed(self) -> None:
        tr = self.context.tr
        pid = self.pack.currentData()
        self.variant.blockSignals(True)
        self.variant.clear()
        if pid == ALL_PACKS:
            self.variant.addItem(tr("ui.variant_all"), "")
            self.variant.setEnabled(False)
        else:
            spec = self.store.defs[pid]
            available = self.store.index(pid)["variants"]
            for vid, v in spec["variants"].items():
                if vid in available:
                    self.variant.addItem(v.get("label", vid), vid)
            self.variant.setEnabled(self.variant.count() > 1)
        self.variant.blockSignals(False)
        self._load_items()

    def _load_items(self) -> None:
        pid = self.pack.currentData()
        if pid == ALL_PACKS:
            refs = [r for p in self.store.defs if self.store.is_available(p) for r in self.store.items(p)]
        else:
            refs = self.store.items(pid, self.variant.currentData())
        self.model.set_refs(refs)
        # Kategorien der angezeigten Symbole
        tr = self.context.tr
        counts: dict[tuple[str, str], int] = {}
        for r in refs:
            for c in self.store.info(r).get("categories", []):
                key = (r.pack, c)
                counts[key] = counts.get(key, 0) + 1
        titles: dict[str, tuple[str, int]] = {}
        for (p, c), n in counts.items():
            title, prev = titles.get(c, (self.store.category_title(p, c), 0))
            titles[c] = (title, prev + n)
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem(tr("ui.all_categories", count=len(refs)), "")
        for cid, (title, n) in sorted(titles.items(), key=lambda kv: kv[1][0].lower()):
            self.category.addItem(f"{title}  ({n})", cid)
        self.category.setEnabled(bool(titles))
        self.category.blockSignals(False)
        self._apply_filter()
        self.view.setCurrentIndex(self.proxy.index(0, 0))

    # ------------------------------------------------------------ Details
    def _build_details(self) -> QWidget:
        """Rechte Leiste: oben Export (Format, Größen, Speichern), darunter Vorschau, Darstellung, Infos, Lizenz."""
        panel = QFrame()
        panel.setObjectName("DetailsPanel")
        panel.setMinimumWidth(self.root.fontMetrics().averageCharWidth() * 40)
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
        self._build_export(lay)
        lay.addSpacing(6)
        self._build_preview(lay)
        self._build_style(lay)
        self._build_info(lay)
        self._build_license(lay)
        lay.addStretch()
        self._fmt_changed()
        return panel

    def _build_export(self, lay: QVBoxLayout) -> None:
        tr = self.context.tr
        s = self.context.settings
        lay.addWidget(_section(tr("ui.export")))
        eform = QFormLayout()
        eform.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
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
        for i, size in enumerate(export.SIZES):
            cb = QCheckBox(f"{size}")
            cb.setChecked(size == 256)
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
        clip.setIcon(library_icon("clipboard-copy", 16))
        clip.clicked.connect(self._copy_image)
        btns.addWidget(clip, 1)
        save = QPushButton(tr("ui.save_as"))
        save.setIcon(library_icon("download", 16, "#ffffff"))
        save.setProperty("primary", True)
        save.clicked.connect(self._save)
        btns.addWidget(save, 1)
        lay.addLayout(btns)
        self.status = QLabel(wordWrap=True)
        self.status.setObjectName("Muted")
        self.status.hide()
        lay.addWidget(self.status)

    def _build_preview(self, lay: QVBoxLayout) -> None:
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(PREVIEW + 24)
        self.preview.setObjectName("IconPreview")
        lay.addWidget(self.preview)
        self.name_label = QLabel()
        self.name_label.setObjectName("PageTitle")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.name_label.setWordWrap(True)
        lay.addWidget(self.name_label)
        self.pack_label = QLabel(wordWrap=True)
        self.pack_label.setObjectName("Muted")
        self.pack_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pack_label.setOpenExternalLinks(True)
        lay.addWidget(self.pack_label)

    def _build_style(self, lay: QVBoxLayout) -> None:
        tr = self.context.tr
        lay.addWidget(_section(tr("ui.style")))
        sform = QFormLayout()
        self.color_btn = ColorButton(self.context.settings.get("default_color") or "#1f2937", self._refresh_preview)
        sform.addRow(tr("ui.color"), self.color_btn)
        self.stroke = QDoubleSpinBox()
        self.stroke.setRange(0.5, 4.0)
        self.stroke.setSingleStep(0.25)
        self.stroke.setValue(2.0)
        self.stroke.setToolTip(tr("ui.stroke_hint"))
        self.stroke.valueChanged.connect(self._refresh_preview)
        sform.addRow(tr("ui.stroke"), self.stroke)
        bg_row = QHBoxLayout()
        self.bg = QComboBox()
        for key in ("none", "square", "circle"):
            self.bg.addItem(tr(f"ui.bg_{key}"), key)
        self.bg.currentIndexChanged.connect(self._bg_changed)
        bg_row.addWidget(self.bg, 1)
        self.bg_color = ColorButton("#3b82f6", self._refresh_preview)
        self.bg_color.setEnabled(False)
        bg_row.addWidget(self.bg_color)
        sform.addRow(tr("ui.background"), bg_row)
        lay.addLayout(sform)

    def _build_info(self, lay: QVBoxLayout) -> None:
        tr = self.context.tr
        lay.addWidget(_section(tr("ui.info")))
        form = QFormLayout()
        form.setVerticalSpacing(4)
        self.lbl_categories = QLabel(wordWrap=True)
        self.lbl_tags = QLabel(wordWrap=True)
        for key, w in (("ui.categories", self.lbl_categories), ("ui.tags", self.lbl_tags)):
            cap = QLabel(tr(key))
            cap.setObjectName("Muted")
            form.addRow(cap, w)
        lay.addLayout(form)

    def _build_license(self, lay: QVBoxLayout) -> None:
        tr = self.context.tr
        lay.addWidget(_section(tr("ui.license")))
        self.lic_name = QLabel(wordWrap=True)
        self.lic_name.setOpenExternalLinks(True)
        lay.addWidget(self.lic_name)
        self.lic_summary = QLabel(wordWrap=True)
        self.lic_summary.setObjectName("Muted")
        lay.addWidget(self.lic_summary)
        self.perm_box = QWidget()
        self.perm_layout = QGridLayout(self.perm_box)
        self.perm_layout.setContentsMargins(0, 2, 0, 2)
        self.perm_layout.setHorizontalSpacing(8)
        self.perm_layout.setVerticalSpacing(3)
        lay.addWidget(self.perm_box)
        disclaimer = QLabel(tr("ui.license_disclaimer"), wordWrap=True)
        disclaimer.setObjectName("Muted")
        lay.addWidget(disclaimer)

    # ------------------------------------------------------------ Logik
    def _apply_filter(self) -> None:
        self.proxy.set_filter(self.search.text(), self.category.currentData() or "")
        self.count.setText(self.context.tr("ui.count", shown=self.proxy.rowCount(), total=self.model.rowCount()))
        if self.proxy.rowCount() and not self.view.currentIndex().isValid():
            self.view.setCurrentIndex(self.proxy.index(0, 0))

    def _current(self) -> IconRef | None:
        idx = self.view.currentIndex()
        return idx.data(IconModel.REF) if idx.isValid() else None

    def _select(self, index) -> None:
        if not index.isValid():
            return
        ref: IconRef = index.data(IconModel.REF)
        tr = self.context.tr
        spec = self.store.defs[ref.pack]
        info = self.store.info(ref)
        version = self.store.index(ref.pack).get("version", "")
        variant_label = spec["variants"].get(ref.variant, {}).get("label", ref.variant)
        self.name_label.setText(ref.name)
        self.pack_label.setText(f"<a href='{spec.get('homepage', '')}'>{spec['name']}</a> {version} · {variant_label}")
        self.lbl_categories.setText(", ".join(self.store.category_title(ref.pack, c)
                                              for c in info.get("categories", [])) or "–")
        tags = info.get("tags", [])
        self.lbl_tags.setText(", ".join(tags[:40]) + (" …" if len(tags) > 40 else "") or "–")
        self._show_license(ref)
        self._refresh_preview()

    def _show_license(self, ref: IconRef) -> None:
        tr = self.context.tr
        lang = self.context.language.split("_")[0]
        key = self.store.license_key(ref.pack)
        lic = self.licenses["licenses"].get(key, {})
        self.lic_name.setText(f"<b><a href='{lic.get('url', '')}'>{lic.get('name', key)}</a></b>  ({key})")
        summary = lic.get("summary", {})
        self.lic_summary.setText(summary.get(lang) or summary.get("en", ""))
        perms = dict(lic.get("permissions", {}))
        if self.store.is_brand(ref):
            perms["trademark_free"] = False
        while self.perm_layout.count():
            w = self.perm_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        row = 0
        for pkey in self.licenses["permission_order"]:
            if pkey not in perms:
                continue
            ok = perms[pkey]
            mark = QLabel("✔" if ok else "✘")
            mark.setStyleSheet(f"color: {GREEN if ok else RED}; font-weight: 700; font-size: 11pt;")
            self.perm_layout.addWidget(mark, row, 0, Qt.AlignmentFlag.AlignTop)
            text = QLabel(tr(f"perm.{pkey}"), wordWrap=True)
            self.perm_layout.addWidget(text, row, 1)
            row += 1
        self.perm_layout.setColumnStretch(1, 1)

    def _style(self) -> Style:
        return Style(color=self.color_btn.color, stroke=self.stroke.value(), background=self.bg.currentData(),
                     bg_color=self.bg_color.color)

    def _svg(self, ref: IconRef) -> bytes:
        return export.build_svg(self.store.svg(ref), self._style())

    def _refresh_preview(self) -> None:
        ref = self._current()
        if not ref:
            return
        self.preview.setPixmap(export.render_pixmap(self._svg(ref), PREVIEW))

    def _bg_changed(self) -> None:
        has_bg = self.bg.currentData() != "none"
        self.bg_color.setEnabled(has_bg)
        default = self.context.settings.get("default_color") or "#1f2937"
        if has_bg and self.color_btn.color == default:
            self.color_btn.set_color("#ffffff")
        elif not has_bg and self.color_btn.color == "#ffffff":
            self.color_btn.set_color(default)
        self._refresh_preview()

    def _fmt_changed(self) -> None:
        fmt = self.fmt.currentData()
        self.fmt_hint.setText(self.context.tr(f"fmt.{fmt}_hint"))
        for cb in self.size_checks.values():
            cb.setEnabled(fmt != "svg")
        self.custom_size.setEnabled(fmt != "svg")

    def _sizes(self) -> list[int]:
        sizes = [s for s, cb in self.size_checks.items() if cb.isChecked()]
        for part in self.custom_size.text().replace(";", ",").split(","):
            if part.strip().isdigit() and 1 <= int(part) <= 4096:
                sizes.append(int(part))
        return sorted(set(sizes)) or [256]

    def _set_status(self, text: str) -> None:
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def _copy_image(self) -> None:
        ref = self._current()
        if ref:
            size = max(self._sizes())
            QApplication.clipboard().setImage(export.render(self._svg(ref), size))
            self._set_status(self.context.tr("ui.image_copied", size=size))

    def _save(self) -> None:
        ref = self._current()
        if not ref:
            return
        fmt = self.fmt.currentData()
        start = Path(self.context.settings.get("export_dir") or Path.home() / "Pictures")
        path, _ = QFileDialog.getSaveFileName(self.root, self.context.tr("ui.save_as"),
                                              str(start / f"{ref.name}.{fmt}"), f"{fmt.upper()} (*.{fmt})")
        if not path:
            return
        try:
            written = export.export(Path(path), fmt, self._svg(ref), self._sizes())
        except Exception as exc:  # noqa: BLE001
            self._set_status("❌ " + str(exc))
            return
        self.context.settings.set("export_dir", str(Path(path).parent))
        msg = self.context.tr("ui.saved", count=len(written), path=str(written[0].parent))
        self._set_status("✅ " + msg)
        self.context.notify(msg)

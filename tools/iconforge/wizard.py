"""Download-Assistent: Symbol-Bibliothek auswählen, Vorschau mit Banner und Angaben ansehen, laden oder entfernen."""

from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QDateTime, QLocale, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from shiboken6 import isValid

from omniwrench.core import icons
from omniwrench.sdk import run_async

from . import export
from .export import Style
from .packs import PackStore, pack_color

# Platzhalter-Symbole (eingebautes Lucide), solange ein Paket noch nicht geladen ist
FALLBACK_ICONS = ["house", "star", "heart", "settings", "cloud", "mail", "user", "search", "camera", "bell", "folder",
                  "calendar", "map-pin", "shield", "zap", "music", "image", "globe", "lock", "message-circle"]


class HeroBanner(QWidget):
    """Dynamisch erzeugtes Banner: Farbverlauf in der Akzentfarbe des Pakets, darauf Beispielsymbole."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._color = QColor("#6366f1")
        self._seed = ""
        self._svgs: list[bytes] = []
        self._monogram = ""
        self._icon_cache: dict[tuple[int, int], QPixmap | None] = {}

    def sizeHint(self):  # noqa: N802
        size = super().sizeHint()
        size.setHeight(self.fontMetrics().height() * 9)
        return size

    def minimumSizeHint(self):  # noqa: N802
        return self.sizeHint()

    def set_pack(self, pack: str, name: str, color: str, svgs: list[bytes]) -> None:
        self._seed = pack
        self._color = QColor(color)
        self._monogram = "".join(w[0] for w in name.split()[:2]).upper()
        self._svgs = svgs or [s for s in (icons.library_svg(n) for n in FALLBACK_ICONS) if s]
        self._icon_cache = {}
        self.updateGeometry()
        self.update()

    def _icon(self, i: int, px: int) -> QPixmap | None:
        key = (i, px)
        cache = self._icon_cache
        if key not in cache:
            try:
                svg = export.build_svg(self._svgs[i], Style(color="#ffffff", stroke=1.75))
                pix = QPixmap.fromImage(export.render(svg, px * 2))
                pix.setDevicePixelRatio(2)
            except Exception:  # noqa: BLE001 - defektes Symbol einfach auslassen
                pix = None
            cache[key] = pix
        return cache[key]

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        radius = min(16.0, rect.height() / 8)
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip)

        base = self._color
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        hue, sat = base.hslHueF(), max(0.45, base.hslSaturationF())
        grad.setColorAt(0, QColor.fromHslF(hue, sat, 0.58))
        grad.setColorAt(0.5, QColor.fromHslF(hue, sat, 0.46))
        grad.setColorAt(1, QColor.fromHslF((hue - 0.09) % 1.0, sat, 0.34))
        p.fillRect(rect, grad)
        glow = QRadialGradient(QPointF(rect.width() * 0.85, 0), rect.height() * 1.1)
        glow.setColorAt(0, QColor(255, 255, 255, 40))
        glow.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(rect, glow)

        rng = random.Random(self._seed)
        h = rect.height()
        # Symbol-Raster, das nach links ausblendet
        cell = max(24, int(h / 3.2))
        icon_px = int(cell * 0.55)
        cols = int(rect.width() / cell) + 2
        rows = int(h / cell) + 2
        if self._svgs:
            for r in range(rows):
                for c in range(cols):
                    x = c * cell + (cell / 2 if r % 2 else 0) - cell / 2
                    y = r * cell - cell / 3
                    fade = max(0.0, min(1.0, (x / rect.width()) * 1.25 - 0.1))
                    if fade <= 0.05:
                        continue
                    pix = self._icon(rng.randrange(len(self._svgs)), icon_px)
                    if pix is None:
                        continue
                    p.setOpacity(0.10 + 0.30 * fade * rng.random())
                    p.drawPixmap(QPointF(x + (cell - icon_px) / 2, y + (cell - icon_px) / 2), pix)
        p.setOpacity(1.0)

        # Hervorgehobenes Symbol in einer Glas-Kachel
        tile = h * 0.52
        tile_rect = QRectF(h * 0.28, (h - tile) / 2, tile, tile)
        p.setPen(QColor(255, 255, 255, 110))
        p.setBrush(QColor(255, 255, 255, 46))
        p.drawRoundedRect(tile_rect, tile * 0.24, tile * 0.24)
        hero = self._icon(0, int(tile * 0.56)) if self._svgs else None
        if hero is not None:
            size = hero.width() / hero.devicePixelRatio()
            p.drawPixmap(QPointF(tile_rect.center().x() - size / 2, tile_rect.center().y() - size / 2), hero)
        elif self._monogram:
            font = QFont(self.font())
            font.setPixelSize(int(tile * 0.36))
            font.setWeight(QFont.Weight.Bold)
            p.setFont(font)
            p.setPen(QColor("#ffffff"))
            p.drawText(tile_rect, Qt.AlignmentFlag.AlignCenter, self._monogram)
        p.end()


class PackWizard(QDialog):
    """Assistent zum Herunterladen (und Entfernen) von Symbol-Bibliotheken."""

    packDownloaded = Signal(str)
    packRemoved = Signal(str)

    def __init__(self, store: PackStore, licenses: dict, context, parent=None, select: str | None = None):
        super().__init__(parent)
        self.store = store
        self.licenses = licenses
        self.context = context
        tr = context.tr
        self.locale = QLocale(context.language.split("_")[0])
        self._busy = False
        self.setWindowTitle(tr("wizard.title"))
        fm = self.fontMetrics()
        self.resize(fm.averageCharWidth() * 78, fm.height() * 34)
        self.setMinimumWidth(fm.averageCharWidth() * 56)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        intro = QLabel(tr("wizard.intro"), wordWrap=True)
        intro.setObjectName("Muted")
        lay.addWidget(intro)

        row = QHBoxLayout()
        cap = QLabel(tr("wizard.library"))
        row.addWidget(cap)
        self.combo = QComboBox()
        self.combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(30)
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(self.combo, 1)
        lay.addLayout(row)

        self.banner = HeroBanner()
        lay.addWidget(self.banner)
        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.subtitle = QLabel(wordWrap=True)
        self.subtitle.setObjectName("Muted")
        lay.addWidget(self.subtitle)

        form = QFormLayout()
        form.setVerticalSpacing(5)
        form.setHorizontalSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields: dict[str, QLabel] = {}
        for key in ("publisher", "version", "size", "files", "published", "styles", "license", "status", "source", "package"):
            caption = QLabel(tr(f"wizard.{key}"))
            caption.setObjectName("Muted")
            value = QLabel(wordWrap=True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            value.setOpenExternalLinks(True)
            form.addRow(caption, value)
            self.fields[key] = value
        lay.addLayout(form)
        lay.addStretch()

        self.progress = QLabel(wordWrap=True)
        self.progress.setObjectName("Muted")
        lay.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.remove_btn = QPushButton(tr("wizard.remove"))
        self.remove_btn.clicked.connect(self._remove)
        buttons.addWidget(self.remove_btn)
        buttons.addStretch()
        self.close_btn = QPushButton(tr("wizard.close"))
        self.close_btn.clicked.connect(self.reject)
        buttons.addWidget(self.close_btn)
        self.download_btn = QPushButton(tr("wizard.download"))
        self.download_btn.setProperty("primary", True)
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(self._download)
        buttons.addWidget(self.download_btn)
        lay.addLayout(buttons)

        packs = self.store.downloadable()
        pending = [p for p in packs if not self.store.is_available(p)]
        first = select if select in packs else (pending[0] if pending else packs[0])
        for pid in packs:
            self.combo.addItem(self._item_text(pid), pid)
        self.combo.setCurrentIndex(self.combo.findData(first))
        self.combo.currentIndexChanged.connect(self._show)
        self._show()
        self._load_summaries(packs)

    # ------------------------------------------------------------ Anzeige
    def _size(self, size: int) -> str:
        return self.locale.formattedDataSize(size, 1, QLocale.DataSizeFormat.DataSizeTraditionalFormat) if size else "…"

    def _item_text(self, pid: str) -> str:
        spec = self.store.defs[pid]
        mark = "✔  " if self.store.is_available(pid) else ""
        size = self._size(self.store.catalog(pid).get("size", 0))
        return f"{mark}{spec['name']}  ·  {size}  ·  {spec.get('publisher', '')}"

    def _refresh_items(self) -> None:
        for i in range(self.combo.count()):
            self.combo.setItemText(i, self._item_text(self.combo.itemData(i)))

    def _date(self, iso: str) -> str:
        if not iso:
            return "–"
        dt = QDateTime.fromString(iso.replace("Z", "+00:00")[:19], Qt.DateFormat.ISODate)
        return self.locale.toString(dt.date(), QLocale.FormatType.ShortFormat) if dt.isValid() else iso[:10]

    def _show(self) -> None:
        tr = self.context.tr
        pid = self.combo.currentData()
        spec = self.store.defs[pid]
        installed = self.store.is_available(pid)
        self.banner.set_pack(pid, spec["name"], pack_color(pid, spec), self.store.samples(pid, 24) if installed else [])
        self.title.setText(spec["name"])
        styles = [v.get("label", k) for k, v in spec["variants"].items()]
        self.subtitle.setText(tr("wizard.subtitle", count=len(styles)))
        lic = self.licenses["licenses"].get(spec["license"], {})
        homepage = spec.get("homepage", "")
        npm = f"https://www.npmjs.com/package/{spec['package']}"
        f = self.fields
        f["publisher"].setText(spec.get("publisher", "–"))
        f["styles"].setText(", ".join(styles))
        f["license"].setText(f"<a href='{lic.get('url', '')}'>{lic.get('name', spec['license'])}</a>")
        f["source"].setText(f"<a href='{homepage}'>{homepage}</a>" if homepage else "–")
        f["package"].setText(f"<a href='{npm}'>{spec['package']}</a>")
        if installed:
            idx = self.store.index(pid)
            total = sum(len(n) for n in idx["variants"].values())
            f["status"].setText("✔ " + tr("wizard.status_installed", version=idx.get("version", ""), count=total,
                                          size=self._size(self.store.disk_size(pid))))
        else:
            f["status"].setText(tr("wizard.status_missing"))
        self.download_btn.setText(tr("wizard.update" if installed else "wizard.download"))
        self.remove_btn.setVisible(installed)
        self._show_release(pid)
        if not self.store.catalog_fresh(pid, exact=True):
            self._fetch_release(pid)

    def _show_release(self, pid: str) -> None:
        info = self.store.catalog(pid)
        f = self.fields
        if not info:
            for key in ("version", "size", "files", "published"):
                f[key].setText("…")
            return
        f["version"].setText(info.get("version") or "–")
        f["size"].setText(self._size(info.get("size", 0)))
        f["files"].setText(self.locale.toString(int(info.get("files", 0))) if info.get("files") else "–")
        f["published"].setText(self._date(info.get("published", "")) if info.get("exact") else "…")

    # ------------------------------------------------------------ npm-Angaben
    def _load_summaries(self, packs: list[str]) -> None:
        missing = [p for p in packs if not self.store.catalog_fresh(p)]
        if not missing:
            return

        def work():
            with ThreadPoolExecutor(max_workers=6) as pool:
                for pid in missing:
                    pool.submit(self._safe, self.store.fetch_summary, pid)

        run_async(work, lambda _: self._summaries_loaded(), lambda _err: None)

    @staticmethod
    def _safe(fn, *args):
        try:
            return fn(*args)
        except Exception:  # noqa: BLE001 - einzelne Pakete ohne Angaben sind kein Fehler
            return None

    def _alive(self) -> bool:
        """Dialog noch offen? (Antworten aus dem Hintergrund können nach dem Schließen eintreffen.)"""
        return isValid(self) and self.isVisible()

    def _summaries_loaded(self) -> None:
        if self._alive():
            self._refresh_items()
            self._show_release(self.combo.currentData())

    def _fetch_release(self, pid: str) -> None:
        def done(_):
            if self._alive():
                self._refresh_items()
                if self.combo.currentData() == pid:
                    self._show_release(pid)

        def failed(err):
            if self._alive() and self.combo.currentData() == pid:
                self.progress.setText("❌ " + self.context.tr("wizard.info_failed", error=err))

        self.progress.clear()
        run_async(lambda: self.store.fetch_release(pid), done, failed)

    # ------------------------------------------------------------ Aktionen
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for w in (self.combo, self.download_btn, self.remove_btn, self.close_btn):
            w.setEnabled(not busy)

    def _download(self) -> None:
        tr = self.context.tr
        pid = self.combo.currentData()
        name = self.store.defs[pid]["name"]
        self._set_busy(True)
        self.progress.setText(tr("ui.pack_loading", name=name))

        def done(_):
            self._set_busy(False)
            self.context.notify(tr("ui.pack_loaded", name=name))
            self.packDownloaded.emit(pid)
            self.accept()

        def failed(err):
            self._set_busy(False)
            self.progress.setText("❌ " + tr("ui.pack_failed", name=name, error=err))

        run_async(lambda progress: self.store.download(pid, progress), done, failed,
                  lambda msg: self.progress.setText(tr("ui.pack_loading", name=msg)))

    def _remove(self) -> None:
        tr = self.context.tr
        pid = self.combo.currentData()
        name = self.store.defs[pid]["name"]
        answer = QMessageBox.question(self, tr("wizard.remove"), tr("wizard.remove_confirm", name=name))
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.remove(pid)
        self.packRemoved.emit(pid)
        self._refresh_items()
        self._show()
        self.progress.setText(tr("wizard.removed", name=name))

    def reject(self) -> None:
        if not self._busy:
            super().reject()


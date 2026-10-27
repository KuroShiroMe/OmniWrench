"""Screenshots der Tools: Laden (lokal oder aus dem Store, mit Cache), Karussell und Großansicht.

Quelle eines Bildes ist ein ShotRef: entweder eine Datei im Tool-Ordner (installiertes Tool) oder
eine URL aus dem Store-Katalog (mit sha256). Heruntergeladene Bilder landen in
<LOCAL_DIR>/cache/screenshots/<sha256>.png und werden danach ohne Netz angezeigt.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from omniwrench.core import net
from omniwrench.core.i18n import tr
from omniwrench.core.paths import CACHE_DIR

from . import theme
from .scaling import fit_to_screen
from .widgets import label, library_icon
from .workers import run_async

log = logging.getLogger(__name__)
SHOT_CACHE_DIR = CACHE_DIR / "screenshots"
ASPECT = 10 / 16  # Höhe zu Breite der Vorschau (Screenshots werden in 16:10 gerendert)


@dataclass(frozen=True)
class ShotRef:
    caption: str = ""
    path: Path | None = None   # Datei im Tool-Ordner
    url: str = ""              # Store-Katalog
    sha256: str = ""

    @property
    def key(self) -> str:
        return self.sha256 or str(self.path or self.url)


class _Loader(QObject):
    """Lädt Bilder einmal pro Sitzung und meldet fertige Bilder über ein Signal."""

    loaded = Signal(str)

    def __init__(self):
        super().__init__()
        self._images: dict[str, QImage] = {}
        self._pending: set[str] = set()
        self._failed: set[str] = set()

    def image(self, ref: ShotRef) -> QImage | None:
        """Bild sofort, falls schon geladen; sonst wird es im Hintergrund geholt (Signal loaded)."""
        key = ref.key
        if key in self._images:
            return self._images[key]
        if key in self._failed or key in self._pending:
            return None
        self._pending.add(key)
        run_async(lambda: _read(ref), lambda data: self._done(key, data))
        return None

    def failed(self, ref: ShotRef) -> bool:
        return ref.key in self._failed

    def _done(self, key: str, data: bytes | None) -> None:
        self._pending.discard(key)
        img = QImage()
        if not data or not img.loadFromData(data):
            self._failed.add(key)
        else:
            self._images[key] = img
        self.loaded.emit(key)


def _read(ref: ShotRef) -> bytes | None:
    """Läuft im Hintergrund. Fehler (offline, Datei fehlt) sind kein Fehlerfall - es bleibt der Platzhalter."""
    try:
        if ref.path is not None:
            return ref.path.read_bytes()
        cached = SHOT_CACHE_DIR / f"{ref.sha256}.img" if ref.sha256 else None
        if cached and cached.is_file():
            return cached.read_bytes()
        data = net.get_bytes(ref.url, timeout=20)
        if ref.sha256 and hashlib.sha256(data).hexdigest() != ref.sha256:
            raise ValueError("sha256")
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
        return data
    except Exception as exc:  # noqa: BLE001
        log.info("Screenshot nicht geladen (%s): %s", ref.path or ref.url, exc)
        return None


_loader: _Loader | None = None


def loader() -> _Loader:
    global _loader
    if _loader is None:
        _loader = _Loader()
    return _loader


class ScreenshotCarousel(QWidget):
    """Vorschau im Format 16:10 mit Pfeilen und Punkten zum Durchklicken.

    Ohne Screenshots erscheint ein Platzhalter mit dem Tool-Symbol in der Akzentfarbe.
    clicked: Klick auf das Bild (nicht auf die Pfeile).
    """

    clicked = Signal()
    indexChanged = Signal(int)

    def __init__(self, shots: list[ShotRef], placeholder: QPixmap | None = None, accent: str = "",
                 radius: float = 8, fit: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.shots = shots
        self.fit = fit  # True: ganzes Bild zeigen (Großansicht), sonst Fläche füllen
        self.index = 0
        self.placeholder = placeholder
        self.accent = QColor(accent or theme.current["accent"])
        self.radius = radius
        self.setObjectName("Screenshot")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self.setMinimumSize(160, 100)
        self._prev = self._arrow("chevron-left", -1)
        self._next = self._arrow("chevron-right", 1)
        loader().loaded.connect(self._on_loaded)
        self._update_tooltip()

    def _arrow(self, icon: str, step: int) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("ShotArrow")
        btn.setIcon(library_icon(icon, 18, "#ffffff"))
        btn.setIconSize(QSize(18, 18))
        btn.setFixedSize(30, 30)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tr("shots.next") if step > 0 else tr("shots.previous"))
        btn.clicked.connect(lambda: self.step(step))
        btn.setVisible(len(self.shots) > 1)
        return btn

    # ------------------------------------------------------------ Steuerung
    def step(self, delta: int) -> None:
        if self.shots:
            self.set_index((self.index + delta) % len(self.shots))

    def set_index(self, index: int) -> None:
        if self.shots and index != self.index:
            self.index = index % len(self.shots)
            self._update_tooltip()
            self.update()
            self.indexChanged.emit(self.index)

    def current(self) -> ShotRef | None:
        return self.shots[self.index] if self.shots else None

    def _update_tooltip(self) -> None:
        shot = self.current()
        if shot is None:
            self.setToolTip("")
            return
        text = shot.caption
        if len(self.shots) > 1:
            text = f"{self.index + 1}/{len(self.shots)}  {text}".strip()
        self.setToolTip(text)

    def _on_loaded(self, key: str) -> None:
        if any(s.key == key for s in self.shots):
            self.update()

    # ------------------------------------------------------------ Größe
    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return round(width * ASPECT)

    def sizeHint(self):  # noqa: N802
        return QSize(400, round(400 * ASPECT))

    def resizeEvent(self, event):  # noqa: N802
        y = (self.height() - self._prev.height()) // 2
        self._prev.move(8, y)
        self._next.move(self.width() - self._next.width() - 8, y)
        super().resizeEvent(event)

    # ------------------------------------------------------------ Maus/Tastatur
    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            # Punkte unten: direkt zu einem Bild springen
            hit = self._dot_at(event.position())
            if hit is not None:
                self.set_index(hit)
            else:
                self.clicked.emit()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):  # noqa: N802 - Rad scrollt die Seite, nicht die Bilder
        event.ignore()

    # ------------------------------------------------------------ Zeichnen
    def _dots(self) -> list[QRectF]:
        n = len(self.shots)
        if n < 2:
            return []
        d, gap = 7.0, 7.0
        total = n * d + (n - 1) * gap
        x0 = (self.width() - total) / 2
        y = self.height() - d - 10
        return [QRectF(x0 + i * (d + gap), y, d, d) for i in range(n)]

    def _dot_at(self, pos: QPointF) -> int | None:
        for i, r in enumerate(self._dots()):
            if r.adjusted(-5, -6, 5, 6).contains(pos):
                return i
        return None

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(rect, self.radius, self.radius)
        p.setClipPath(clip)
        shot = self.current()
        img = loader().image(shot) if shot else None
        if img is not None:
            p.fillRect(rect, QColor(theme.current["bg"]))
            # Bild füllt die Fläche (zentriert, Überstand abgeschnitten)
            fn = min if self.fit else max
            scale = fn(rect.width() / img.width(), rect.height() / img.height())
            w, h = img.width() * scale, img.height() * scale
            target = QRectF(rect.center().x() - w / 2, rect.top(), w, h) if h > rect.height() else \
                QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h)
            p.drawImage(target, img)
        else:
            self._paint_placeholder(p, rect, loading=shot is not None and not loader().failed(shot))
        dots = self._dots()
        if dots:
            for i, r in enumerate(dots):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 90))
                p.drawEllipse(r.adjusted(-1.5, -1.5, 1.5, 1.5))
                p.setBrush(QColor(255, 255, 255, 235 if i == self.index else 120))
                p.drawEllipse(r)
        p.setClipping(False)
        p.setPen(QColor(theme.current["border"]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, self.radius, self.radius)
        p.end()

    def _paint_placeholder(self, p: QPainter, rect: QRectF, loading: bool) -> None:
        base = QColor(theme.current["surface2"])
        tint = QColor(self.accent)
        tint.setAlpha(55)
        p.fillRect(rect, base)
        p.fillRect(rect, tint)
        if self.placeholder is not None and not self.placeholder.isNull():
            size = min(rect.height() * 0.42, 96)
            p.setOpacity(0.9)
            p.drawPixmap(QRectF(rect.center().x() - size / 2, rect.center().y() - size / 2, size, size),
                         self.placeholder, QRectF(self.placeholder.rect()))
            p.setOpacity(1)
        if loading:
            p.setPen(QColor(theme.current["muted"]))
            p.drawText(rect.adjusted(0, 0, 0, -8), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                       tr("shots.loading"))


class ScreenshotViewer(QDialog):
    """Großansicht der Screenshots mit Bildunterschrift; Pfeiltasten blättern."""

    def __init__(self, title: str, shots: list[ShotRef], index: int = 0, parent: QWidget | None = None,
                 placeholder: QPixmap | None = None, accent: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        fit_to_screen(self, 1180, 800)
        lay = QVBoxLayout(self)
        self.carousel = ScreenshotCarousel(shots, placeholder, accent, radius=6, fit=True)
        self.carousel.set_index(index)
        self.carousel.setCursor(Qt.CursorShape.ArrowCursor)
        lay.addWidget(self.carousel, 1)
        row = QHBoxLayout()
        self.caption: QLabel = label("", wrap=True)
        row.addWidget(self.caption, 1)
        self.counter = label("", "Muted")
        row.addWidget(self.counter)
        lay.addLayout(row)
        self.carousel.indexChanged.connect(lambda _i: self._sync())
        self._sync()

    def _sync(self) -> None:
        shot = self.carousel.current()
        self.caption.setText(shot.caption if shot else "")
        n = len(self.carousel.shots)
        self.counter.setText(f"{self.carousel.index + 1} / {n}" if n > 1 else "")

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.carousel.step(1 if event.key() == Qt.Key.Key_Right else -1)
        else:
            super().keyPressEvent(event)

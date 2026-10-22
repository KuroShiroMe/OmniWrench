"""Wiederverwendbare UI-Bausteine."""

from __future__ import annotations

import base64
import hashlib
import html
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from PySide6.QtCore import QByteArray, QPoint, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QBoxLayout, QCheckBox, QDialog, QHBoxLayout, QLabel, QLayout, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from omniwrench.core import icons
from omniwrench.core.i18n import tr
from omniwrench.core.manifest import ToolManifest

from . import theme
from .scaling import device_pixel_ratio, device_pixels, fit_to_screen
from .workers import run_async

_ICON_COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f97316", "#10b981", "#06b6d4", "#eab308", "#ef4444", "#6366f1"]


def accent_color(manifest: ToolManifest) -> str:
    """Akzentfarbe aus tool.json oder eine stabile Farbe passend zur Tool-ID."""
    return manifest.color or _ICON_COLORS[int(hashlib.md5(manifest.id.encode()).hexdigest(), 16) % len(_ICON_COLORS)]


def _render_svg(svg: bytes, painter: QPainter, rect: QRectF, color: str) -> None:
    # Lucide-Symbole zeichnen mit "currentColor" - hier durch die gewünschte Farbe ersetzen
    renderer = QSvgRenderer(QByteArray(svg.replace(b"currentColor", color.encode())))
    renderer.render(painter, rect)


def library_icon(name: str, size: int = 24, color: str | None = None) -> QIcon:
    """Einfarbiges Symbol aus der eingebauten Bibliothek (z. B. für Buttons und Menüs)."""
    svg = icons.library_svg(name)
    if svg is None:
        return QIcon()
    # In der Auflösung des schärfsten Bildschirms zeichnen (Windows-Skalierung x eigene Skalierung)
    ratio = device_pixel_ratio()
    s = device_pixels(size, ratio)
    pix = QPixmap(s, s)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _render_svg(svg, p, QRectF(0, 0, s, s), color or theme.current["text"])
    p.end()
    pix.setDevicePixelRatio(s / size)
    return QIcon(pix)


_icon_cache: dict[tuple, QIcon] = {}


def tool_icon(manifest: ToolManifest, tool_dir: Path | None = None, size: int = 48) -> QIcon:
    """Symbol eines Tools: eigene Bilddatei, Bibliotheks-Symbol, eigenes Kürzel oder Initialen."""
    spec = icons.resolve(manifest.icon, manifest.icon_text, manifest.display_name, tool_dir, manifest.icon_data)
    if spec.kind == "file":
        return QIcon(spec.value)
    if spec.kind == "data":
        pix = QPixmap()
        pix.loadFromData(base64.b64decode(spec.value))
        return QIcon(pix)

    color = accent_color(manifest)
    ratio = device_pixel_ratio()
    key = (spec, color, size, ratio)
    if key in _icon_cache:
        return _icon_cache[key]

    s = device_pixels(size, ratio)  # in Bildschirmauflösung zeichnen, damit es auch bei 300 % scharf bleibt
    pix = QPixmap(s, s)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, s, s, s * 0.22, s * 0.22)
    if spec.kind == "library":
        inset = s * 0.2
        _render_svg(icons.library_svg(spec.value), p, QRectF(inset, inset, s - 2 * inset, s - 2 * inset), "#ffffff")
    else:
        text = spec.value
        font = QFont("Segoe UI")
        font.setBold(True)
        # Schriftgröße so wählen, dass auch 3-4 Zeichen ins Quadrat passen
        font.setPixelSize(int(s * {1: 0.55, 2: 0.44, 3: 0.34}.get(len(text), 0.27)))
        p.setFont(font)
        p.setPen(QColor("white"))
        p.drawText(QRect(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    pix.setDevicePixelRatio(s / size)
    icon = QIcon(pix)
    _icon_cache[key] = icon
    return icon


class FitLabel(QWidget):
    """Text, der sich an die Breite anpasst.

    1. Einzeilig, Schrift wird dafür schrittweise bis single_min_pt verkleinert
    2. Erst dann zweizeilig (Umbruch an Leerzeichen oder nach Bindestrichen), möglichst
       gleich lange Zeilen, Schrift wieder ab max_pt bis min_pt
    3. Notfalls wird die zweite Zeile mit "…" gekürzt
    """

    def __init__(self, text: str, max_pt: float = 10.0, min_pt: float = 7.5, single_min_pt: float = 8.5,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._text = text
        self.max_pt = max_pt
        self.min_pt = min_pt
        self.single_min_pt = single_min_pt
        self._font = QFont(self.font())
        self._lines: list[str] = [text]
        self.setToolTip(text)

    def text(self) -> str:
        return self._text

    def _font_at(self, pt: float) -> QFont:
        f = QFont(self.font())
        f.setPointSizeF(pt)
        return f

    def _sizes(self, minimum: float) -> list[float]:
        sizes, pt = [], self.max_pt
        while pt >= minimum - 0.01:
            sizes.append(round(pt, 1))
            pt -= 0.5
        return sizes

    def _splits(self) -> list[tuple[str, str]]:
        """Mögliche Umbrüche: an Leerzeichen und direkt nach Bindestrichen."""
        text, result = self._text, []
        for i, ch in enumerate(text):
            if ch == " ":
                result.append((text[:i], text[i + 1:]))
            elif ch == "-" and 0 < i < len(text) - 1:
                result.append((text[:i + 1], text[i + 1:]))
        return [(a.strip(), b.strip()) for a, b in result if a.strip() and b.strip()]

    def _layout(self) -> None:
        width = max(self.width(), 10)
        words = self._text.split()
        for pt in self._sizes(self.single_min_pt):
            font = self._font_at(pt)
            if QFontMetrics(font).horizontalAdvance(self._text) <= width:
                self._font, self._lines = font, [self._text]
                return
        splits = self._splits()
        if splits:
            for pt in self._sizes(self.min_pt):
                font = self._font_at(pt)
                fm = QFontMetrics(font)
                best = min(splits, key=lambda s: max(fm.horizontalAdvance(s[0]), fm.horizontalAdvance(s[1])))
                if max(fm.horizontalAdvance(best[0]), fm.horizontalAdvance(best[1])) <= width:
                    self._font, self._lines = font, list(best)
                    return
        # Zu lang: kleinste Schrift, erste Zeile so voll wie möglich, Rest gekürzt
        font = self._font_at(self.min_pt)
        fm = QFontMetrics(font)
        first = words[0] if words else self._text
        for i in range(len(words), 0, -1):
            if fm.horizontalAdvance(" ".join(words[:i])) <= width:
                first = " ".join(words[:i])
                rest = " ".join(words[i:])
                break
        else:
            rest = " ".join(words[1:])
        lines = [fm.elidedText(first, Qt.TextElideMode.ElideRight, width)]
        if rest:
            lines.append(fm.elidedText(rest, Qt.TextElideMode.ElideRight, width))
        self._font, self._lines = font, lines

    def resizeEvent(self, event):  # noqa: N802
        self._layout()
        super().resizeEvent(event)

    def sizeHint(self):  # noqa: N802
        fm = QFontMetrics(self._font_at(self.max_pt))
        return QSize(100, fm.lineSpacing() * 2)

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setFont(self._font)
        p.setPen(self.palette().color(self.foregroundRole()))
        fm = QFontMetrics(self._font)
        y = 0
        for line in self._lines:
            p.drawText(QRect(0, y, self.width(), fm.lineSpacing()), Qt.AlignmentFlag.AlignHCenter, line)
            y += fm.lineSpacing()
        p.end()


_BREAK_AFTER = ".~\\/_:@"


def breakable(text: str) -> str:
    """Erlaubt Zeilenumbrüche in langen Bezeichnern (z. B. Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0),
    damit schmale Leisten nicht breiter werden als der Platz (unsichtbares Leerzeichen nach . ~ \\ / _ : @)."""
    out, run = [], 0
    for ch in text:
        out.append(ch)
        run = 0 if ch.isspace() else run + 1
        if ch in _BREAK_AFTER and run > 8:
            out.append("\u200b")
    return "".join(out)


def tag_links(tags: list[str]) -> str:
    """Tags als Links (Rich Text); linkActivated liefert das Tag URL-kodiert (urllib.parse.unquote)."""
    return " · ".join(f"<a href='{quote(t)}' style='text-decoration:none'>{html.escape(t).replace(' ', '&nbsp;')}</a>"
                      for t in tags)


def make_button(text: str, primary: bool = False, danger: bool = False, on_click: Callable | None = None) -> QPushButton:
    btn = QPushButton(text)
    if primary:
        btn.setProperty("primary", True)
    if danger:
        btn.setProperty("danger", True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def label(text: str, object_name: str = "", wrap: bool = False, parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    if object_name:
        lbl.setObjectName(object_name)
    lbl.setWordWrap(wrap)
    return lbl


class ResponsiveRow(QWidget):
    """Zwei Bereiche nebeneinander (z. B. Seitentitel links, Suche und Buttons rechts).

    Reicht die Breite nicht für beide, rutscht der rechte Bereich unter den linken -
    so passt die Kopfzeile auch in kleine Fenster, ohne Inhalte abzuschneiden.
    """

    def __init__(self, left: QLayout, right: QLayout, parent: QWidget | None = None, left_width: int = 0,
                 align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignVCenter):
        super().__init__(parent)
        self._align = align
        self._left_width = left_width  # Breite, ab der der linke Teil genug Platz hat (0 = seine Wunschbreite)
        self._left, self._right = QWidget(), QWidget()
        self._left.setLayout(left)
        self._right.setLayout(right)
        for part in (left, right):
            part.setContentsMargins(0, 0, 0, 0)
        self._box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.addWidget(self._left, 1)
        self._box.addWidget(self._right, 0, align)

    def _needed_width(self) -> int:
        left = self._left_width or self._left.sizeHint().width()
        return left + self._box.spacing() + self._right.sizeHint().width()

    def minimumSizeHint(self):  # noqa: N802 - erlaubt dem Elternlayout, schmaler zu werden als beide Teile
        hint = super().minimumSizeHint()
        width = max(self._left.minimumSizeHint().width(), self._right.minimumSizeHint().width())
        return QSize(width, hint.height())

    def resizeEvent(self, event):  # noqa: N802
        wide = event.size().width() >= self._needed_width()
        direction = QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom
        if self._box.direction() != direction:
            self._box.setDirection(direction)
            self._box.setAlignment(self._right, self._align if wide else Qt.AlignmentFlag.AlignLeft)
            self.updateGeometry()
        super().resizeEvent(event)


class FlowLayout(QLayout):
    """Layout, das Elemente zeilenweise umbricht (für die Kachelansicht)."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 14):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _do_layout(self, rect: QRect, test: bool) -> int:
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > rect.right() and line_height > 0:
                x = rect.x()
                y += line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if not test:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


class ColumnFlowLayout(QLayout):
    """Gleich breite Spalten, deren Anzahl sich nach der verfügbaren Breite richtet.

    Elemente sind mindestens `min_width` breit; ist Platz für mehr, kommen weitere Spalten
    hinzu (z. B. Store-Karten: auf kleinen Fenstern untereinander, auf großen Monitoren nebeneinander).
    Alle Elemente einer Zeile erhalten die Höhe des höchsten.
    """

    def __init__(self, parent: QWidget | None = None, min_width: int = 460, spacing: int = 10,
                 max_columns: int = 6):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.min_width = min_width
        self.max_columns = max_columns
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def columns(self, width: int) -> int:
        return max(1, min(self.max_columns, (width + self._spacing) // (self.min_width + self._spacing)))

    @staticmethod
    def _height(item, width: int) -> int:
        h = item.heightForWidth(width) if item.hasHeightForWidth() else -1
        return max(h, item.minimumSize().height()) if h > 0 else item.sizeHint().height()

    def _do_layout(self, rect: QRect, test: bool) -> int:
        items = [i for i in self._items if not (i.widget() and i.widget().isHidden())]
        if not items:
            return 0
        cols = self.columns(rect.width())
        col_w = (rect.width() - (cols - 1) * self._spacing) / cols
        y = rect.y()
        for start in range(0, len(items), cols):
            row = items[start:start + cols]
            height = max(self._height(i, int(col_w)) for i in row)
            if not test:
                for n, item in enumerate(row):
                    x = rect.x() + round(n * (col_w + self._spacing))
                    item.setGeometry(QRect(x, y, int(col_w), height))
            y += height + self._spacing
        return y - self._spacing - rect.y()


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if w := item.widget():
            w.hide()  # sofort unsichtbar - deleteLater greift erst im nächsten Event-Loop-Durchlauf
            w.deleteLater()
        elif child := item.layout():
            clear_layout(child)


class TaskDialog(QDialog):
    """Führt eine längere Aufgabe im Hintergrund aus und zeigt deren Protokoll."""

    def __init__(self, parent: QWidget | None, title: str, task: Callable[[Callable[[str], None]], object],
                 on_success: Callable[[object], None] | None = None, auto_close=None):
        """auto_close = (AppSettings, Schlüssel): zeigt den Haken "Dieses Fenster nach Abschluss schließen",
        merkt ihn in den Einstellungen und schließt das Fenster nach erfolgreichem Abschluss selbst."""
        super().__init__(parent)
        self.setWindowTitle(title)
        fit_to_screen(self, 620, 380)
        self.success = False
        self.result_value = None
        self._on_success = on_success

        lay = QVBoxLayout(self)
        self.title = label(title, "CardTitle")
        lay.addWidget(self.title)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        lay.addWidget(self.log, 1)
        row = QHBoxLayout()
        self.auto_close = None
        if auto_close is not None:
            settings, key = auto_close
            self.auto_close = QCheckBox(tr("task.close_when_done"))
            self.auto_close.setChecked(bool(settings.get(key, False)))
            self.auto_close.toggled.connect(lambda on: settings.set(key, on))
            row.addWidget(self.auto_close)
        row.addStretch()
        self.close_btn = make_button(tr("common.close"), on_click=self.accept)
        self.close_btn.setEnabled(False)
        row.addWidget(self.close_btn)
        lay.addLayout(row)

        run_async(task, on_done=self._done, on_error=self._failed, on_progress=self._append)

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text)

    def _done(self, result) -> None:
        self.success = True
        self.result_value = result
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.title.setText(tr("task.done", title=self.windowTitle()))
        self.close_btn.setEnabled(True)
        if self._on_success:
            self._on_success(result)
        if self.auto_close is not None and self.auto_close.isChecked():
            QTimer.singleShot(600, self.accept)  # kurz "abgeschlossen" zeigen; bei Fehlern bleibt es offen

    def _failed(self, error: str) -> None:
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.title.setText(tr("task.failed", title=self.windowTitle()))
        self.title.setStyleSheet(f"color: {theme.current['danger']}")
        self._append("\n" + tr("task.error", error=error))
        self.close_btn.setEnabled(True)

    def reject(self) -> None:  # Escape erst nach Abschluss erlauben
        if self.close_btn.isEnabled():
            super().reject()

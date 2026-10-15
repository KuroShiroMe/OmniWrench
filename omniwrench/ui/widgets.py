"""Wiederverwendbare UI-Bausteine."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLayout, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from omniwrench.core.i18n import tr
from omniwrench.core.manifest import ToolManifest

from . import theme
from .workers import run_async

_ICON_COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f97316", "#10b981", "#06b6d4", "#eab308", "#ef4444", "#6366f1"]


def tool_icon(manifest: ToolManifest, tool_dir: Path | None = None, size: int = 48) -> QIcon:
    """Icon aus dem Tool-Paket oder ein generiertes Icon mit Initialen."""
    if tool_dir and manifest.icon and (tool_dir / manifest.icon).exists():
        return QIcon(str(tool_dir / manifest.icon))
    color = manifest.color or _ICON_COLORS[int(hashlib.md5(manifest.id.encode()).hexdigest(), 16) % len(_ICON_COLORS)]
    words = [w for w in manifest.display_name.replace("-", " ").split() if w]
    initials = "".join(w[0] for w in words[:2]).upper() or "?"

    pix = QPixmap(size * 2, size * 2)  # doppelte Auflösung für HiDPI
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, size * 2, size * 2, size * 0.45, size * 0.45)
    font = QFont("Segoe UI", int(size * 0.62))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(QRect(0, 0, size * 2, size * 2), Qt.AlignmentFlag.AlignCenter, initials)
    p.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)


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


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if w := item.widget():
            w.deleteLater()
        elif child := item.layout():
            clear_layout(child)


class TaskDialog(QDialog):
    """Führt eine längere Aufgabe im Hintergrund aus und zeigt deren Protokoll."""

    def __init__(self, parent: QWidget | None, title: str, task: Callable[[Callable[[str], None]], object],
                 on_success: Callable[[object], None] | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 380)
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

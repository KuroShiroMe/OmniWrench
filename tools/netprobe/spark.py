"""Kleine Verlaufsgrafik (Antwortzeiten) ohne externe Abhängigkeiten."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .sdk_scale import ratio


class Sparkline(QWidget):
    def __init__(self, values: list[float], parent=None):
        super().__init__(parent)
        self._values = [v for v in values if v is not None]
        self.setMinimumHeight(46)
        self.setToolTip("min / max: "
                        + (f"{min(self._values):.1f} / {max(self._values):.1f} ms" if self._values else "–"))

    def paintEvent(self, _event):  # noqa: N802
        if len(self._values) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width() - 8, self.height() - 10
        lo, hi = min(self._values), max(self._values)
        span = hi - lo or 1
        pts = []
        for i, v in enumerate(self._values):
            x = 4 + i * w / (len(self._values) - 1)
            y = 5 + h * (1 - (v - lo) / span)
            pts.append(QPointF(x, y))
        p.setPen(QPen(QColor("#3b82f6"), max(1.0, 1.4 * ratio())))
        p.drawPolyline(QPolygonF(pts))
        p.setPen(QPen(QColor("#3b82f680")))
        avg_y = 5 + h * (1 - (sum(self._values) / len(self._values) - lo) / span)
        p.drawLine(4, int(avg_y), 4 + w, int(avg_y))
        p.end()

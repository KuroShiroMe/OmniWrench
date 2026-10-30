"""Bildschirmfoto für den Chat: ganzer Bildschirm oder Bereich, OmniWrench wird kurz ausgeblendet.

Das Bild landet im Bilder-Ordner der KI-Datenablage und wird an den Chat angehängt. Unter Wayland liefern
manche Desktops kein Bild (Qt darf dort nicht auf den Bildschirm zugreifen) – dann gibt es einen Hinweis.
"""

from __future__ import annotations

import json
import time

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


def grab_all() -> QPixmap:
    """Alle Bildschirme als ein Bild (virtueller Desktop)."""
    screens = QGuiApplication.screens()
    if not screens:
        return QPixmap()
    area = QRect()
    for s in screens:
        area = area.united(s.geometry())
    out = QPixmap(area.size())
    out.fill(QColor("black"))
    p = QPainter(out)
    for s in screens:
        shot = s.grabWindow(0)
        g = s.geometry()
        p.drawPixmap(g.topLeft() - area.topLeft(), shot.scaled(g.size()) if shot.size() != g.size() else shot)
    p.end()
    out.setDevicePixelRatio(1)
    return out


def is_blank(pix: QPixmap) -> bool:
    if pix.isNull():
        return True
    img = pix.toImage().scaled(16, 16)
    first = img.pixel(0, 0)
    return all(img.pixel(x, y) == first for x in range(16) for y in range(16))


class RegionPicker(QWidget):
    """Vollbild-Überlagerung mit dem Bildschirmfoto; Ziehen wählt einen Bereich, Esc bricht ab."""
    picked = Signal(object)        # QPixmap oder None

    def __init__(self, shot: QPixmap, hint: str):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.shot = shot
        self.hint = hint
        self.start: QPoint | None = None
        self.end: QPoint | None = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        area = QRect()
        for s in QGuiApplication.screens():
            area = area.united(s.geometry())
        self.setGeometry(area)

    def rect_sel(self) -> QRect:
        if self.start is None or self.end is None:
            return QRect()
        x, y = min(self.start.x(), self.end.x()), min(self.start.y(), self.end.y())
        return QRect(x, y, abs(self.end.x() - self.start.x()), abs(self.end.y() - self.start.y()))

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.shot)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        sel = self.rect_sel()
        if not sel.isEmpty():
            p.drawPixmap(sel, self.shot, sel)
            p.setPen(QPen(QColor("#8b5cf6"), 2))
            p.drawRect(sel)
        p.setPen(QColor("white"))
        p.drawText(self.rect().adjusted(0, 24, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   self.hint)

    def mousePressEvent(self, e):  # noqa: N802
        self.start = self.end = e.position().toPoint()
        self.update()

    def mouseMoveEvent(self, e):  # noqa: N802
        self.end = e.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, _e):  # noqa: N802
        sel = self.rect_sel()
        self.close()
        self.picked.emit(self.shot.copy(sel) if sel.width() > 4 and sel.height() > 4 else None)

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.close()
            self.picked.emit(None)


class Screenshot:
    """Ablauf: Fenster ausblenden -> warten -> fotografieren -> (Bereich wählen) -> speichern -> Rückruf."""

    def __init__(self, window, storage, tr):
        self.window = window
        self.storage = storage
        self.tr = tr
        self._picker = None

    def take(self, region: bool, done) -> None:
        win = self.window
        was_visible = win is not None and win.isVisible()
        if was_visible:
            win.hide()

        def shoot():
            shot = grab_all()
            if was_visible:
                win.show()
                win.raise_()
            if is_blank(shot):
                done(None, self.tr("shot.blank"))
                return
            if not region:
                done(self.save(shot), "")
                return
            self._picker = RegionPicker(shot, self.tr("shot.region_hint"))
            self._picker.picked.connect(lambda pix: done(self.save(pix), "") if pix is not None else done(None, ""))
            self._picker.showFullScreen()
        QTimer.singleShot(350 if was_visible else 0, shoot)

    def save(self, pix: QPixmap):
        path = self.storage.media_target("images", "Screenshot", ".png")
        pix.save(str(path), "PNG")
        meta = {"format": 1, "kind": "image", "file": path.name, "created": int(time.time()),
                "prompt": self.tr("shot.title"), "screenshot": True}
        path.with_name(path.name + ".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                                       encoding="utf-8")
        return path

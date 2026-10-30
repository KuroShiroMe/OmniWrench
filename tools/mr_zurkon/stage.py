"""Große Anzeige von Mr. Zurkon: Zustand (pulsierende Kugel mit Mikrofonpegel), Wetterkarte mit Animation
(Sonne, Wolken, Regen, Schnee, Gewitter) und Nachrichten mit Laufband. Alles selbst gezeichnet (QPainter)."""

from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QDate, QLocale, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

STATE_COLORS = {"off": "#64748b", "wake": "#38bdf8", "command": "#f43f5e", "thinking": "#a78bfa",
                "speaking": "#34d399", "followup": "#fb923c"}
SKY = {  # Art -> (oben, unten) bei Tag; nachts dunkler
    "clear": ("#2563eb", "#f59e0b"), "cloudy": ("#475569", "#94a3b8"), "fog": ("#64748b", "#cbd5e1"),
    "rain": ("#1e3a5f", "#475569"), "snow": ("#64748b", "#e2e8f0"), "storm": ("#111827", "#4c1d95"),
}


class Stage(QWidget):
    """mode: "state" | "weather" | "news"."""
    closed = Signal()

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.tr_ = tr
        self.setMinimumHeight(260)
        self.mode = "state"
        self.state = "off"
        self.state_text = ""
        self.caption = ""
        self.answer = ""
        self.level = 0.0
        self.data: dict = {}
        self._t0 = time.time()
        self._shown_at = 0.0
        self._particles: list[list[float]] = []
        self._links: list[tuple[QRectF, str]] = []
        self._ticker = 0.0
        self.setMouseTracking(True)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.update)

    # --- Steuerung -----------------------------------------------------------------------------------
    def showEvent(self, e):
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def set_state(self, state: str, text: str, caption: str = "") -> None:
        self.state, self.state_text, self.caption = state, text, caption

    def set_answer(self, text: str) -> None:
        self.answer = text

    def show_weather(self, data: dict) -> None:
        self.mode, self.data, self._shown_at = "weather", data, time.time()
        kind = (data.get("current") or {}).get("kind", "")
        n = {"rain": 120, "storm": 160, "snow": 90}.get(kind, 0)
        self._particles = [[random.random(), random.random(), 0.6 + random.random() * 0.8] for _ in range(n)]

    def show_news(self, data: dict) -> None:
        self.mode, self.data, self._shown_at, self._ticker = "news", data, time.time(), 0.0

    def show_state(self) -> None:
        self.mode = "state"

    # --- Maus ----------------------------------------------------------------------------------------
    def mousePressEvent(self, e):
        pos = e.position()
        if self.mode != "state" and QRectF(self.width() - 34, 8, 26, 26).contains(pos):
            self.show_state()
            self.closed.emit()
            return
        for rect, link in self._links:
            if rect.contains(pos) and link:
                QDesktopServices.openUrl(QUrl(link))
                return

    def mouseMoveEvent(self, e):
        pos = e.position()
        hand = any(r.contains(pos) and link for r, link in self._links) or \
            (self.mode != "state" and QRectF(self.width() - 34, 8, 26, 26).contains(pos))
        self.setCursor(Qt.CursorShape.PointingHandCursor if hand else Qt.CursorShape.ArrowCursor)

    # --- Zeichnen ------------------------------------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._links = []
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        p.setClipPath(path)
        if self.mode == "weather" and self.data:
            self._paint_weather(p, r)
        elif self.mode == "news" and self.data:
            self._paint_news(p, r)
        else:
            self._paint_state(p, r)
        if self.mode != "state":
            self._close_button(p)
        p.end()

    def _font(self, size: float, bold: bool = False) -> QFont:
        f = QFont(self.font())
        f.setPointSizeF(max(6.0, size))
        f.setBold(bold)
        return f

    def _close_button(self, p: QPainter) -> None:
        box = QRectF(self.width() - 34, 8, 26, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawEllipse(box)
        p.setPen(QPen(QColor("white"), 2))
        c = box.center()
        p.drawLine(QPointF(c.x() - 5, c.y() - 5), QPointF(c.x() + 5, c.y() + 5))
        p.drawLine(QPointF(c.x() + 5, c.y() - 5), QPointF(c.x() - 5, c.y() + 5))

    def _paint_state(self, p: QPainter, r: QRectF) -> None:
        t = time.time() - self._t0
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#0f172a"))
        g.setColorAt(1, QColor("#1e1b4b"))
        p.fillRect(r, g)
        color = QColor(STATE_COLORS.get(self.state, "#64748b"))
        has_answer = bool(self.answer) and self.state in ("off", "wake", "speaking", "followup")
        cy = r.top() + r.height() * (0.34 if has_answer else 0.42)
        cx = r.center().x()
        base = min(r.width(), r.height()) * (0.13 if has_answer else 0.17)
        pulse = {"thinking": 0.10 * math.sin(t * 5), "speaking": 0.08 * math.sin(t * 9)}.get(
            self.state, 0.04 * math.sin(t * 2))
        level = self.level_source() if callable(getattr(self, "level_source", None)) else self.level
        rad = base * (1 + pulse + min(0.6, level * 9))
        for i in range(3, 0, -1):                       # Ringe
            ring = QColor(color)
            ring.setAlpha(int(40 / i))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ring)
            p.drawEllipse(QPointF(cx, cy), rad * (1 + 0.35 * i), rad * (1 + 0.35 * i))
        grad = QRadialGradient(QPointF(cx - rad * 0.3, cy - rad * 0.3), rad * 1.4)
        grad.setColorAt(0, color.lighter(160))
        grad.setColorAt(1, color.darker(140))
        p.setBrush(grad)
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        if self.state == "thinking":                     # kreisende Punkte
            p.setBrush(QColor("white"))
            for i in range(3):
                a = t * 3 + i * 2.1
                p.drawEllipse(QPointF(cx + math.cos(a) * rad * 1.25, cy + math.sin(a) * rad * 1.25), 4, 4)
        p.setPen(QColor("#e2e8f0"))
        p.setFont(self._font(15, True))
        top = cy + rad * 1.6
        p.drawText(QRectF(r.left(), top, r.width(), 30), Qt.AlignmentFlag.AlignCenter, self.state_text)
        if self.caption:
            p.setPen(QColor("#94a3b8"))
            p.setFont(self._font(10))
            p.drawText(QRectF(r.left() + 20, top + 28, r.width() - 40, 22), Qt.AlignmentFlag.AlignCenter,
                       self.caption)
        if has_answer:
            p.setPen(QColor("#f8fafc"))
            p.setFont(self._font(12.5))
            box = QRectF(r.left() + 28, top + 54, r.width() - 56, r.bottom() - top - 64)
            p.drawText(box, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                       self.answer)

    # --- Wetter --------------------------------------------------------------------------------------
    def _paint_weather(self, p: QPainter, r: QRectF) -> None:
        t = time.time() - self._t0
        cur = self.data.get("current") or {}
        kind = cur.get("kind", "cloudy")
        top, bottom = SKY.get(kind, SKY["cloudy"])
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        day = cur.get("is_day", True)
        g.setColorAt(0, QColor(top) if day else QColor(top).darker(260))
        g.setColorAt(1, QColor(bottom) if day else QColor(bottom).darker(220))
        p.fillRect(r, g)
        self._weather_fx(p, r, kind, day, t)
        fade = min(1.0, (time.time() - self._shown_at) / 0.6)
        p.setOpacity(fade)
        left = r.left() + 28
        p.setPen(QColor("white"))
        p.setFont(self._font(13, True))
        place = self.data.get("place", "")
        sub = ", ".join(x for x in (self.data.get("region"), self.data.get("country")) if x)
        p.drawText(QRectF(left, r.top() + 18, r.width() - 80, 24), Qt.AlignmentFlag.AlignLeft, place)
        p.setFont(self._font(9))
        p.setPen(QColor(255, 255, 255, 190))
        p.drawText(QRectF(left, r.top() + 42, r.width() - 80, 18), Qt.AlignmentFlag.AlignLeft, sub)
        bob = 4 * math.sin(t * 1.6)
        p.setFont(self._font(min(64.0, r.height() * 0.16)))
        p.setPen(QColor("white"))
        p.drawText(QRectF(left - 6, r.top() + 64 + bob, 140, 110), Qt.AlignmentFlag.AlignLeft, cur.get("icon", ""))
        temp = cur.get("temperature")
        p.setFont(self._font(min(54.0, r.height() * 0.15), True))
        p.drawText(QRectF(left + 130, r.top() + 64, 260, 90), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{round(temp)}°" if isinstance(temp, (int, float)) else "–")
        p.setFont(self._font(12, True))
        p.drawText(QRectF(left + 130, r.top() + 150, r.width() - left - 160, 22), Qt.AlignmentFlag.AlignLeft,
                   str(cur.get("condition", "")).capitalize())
        tr = self.tr_
        details = []
        if isinstance(cur.get("feels_like"), (int, float)):
            details.append(tr("va.w.feels", value=round(cur["feels_like"])))
        if isinstance(cur.get("wind_kmh"), (int, float)):
            details.append(tr("va.w.wind", value=round(cur["wind_kmh"])))
        if isinstance(cur.get("humidity"), (int, float)):
            details.append(tr("va.w.humidity", value=round(cur["humidity"])))
        p.setFont(self._font(9.5))
        p.setPen(QColor(255, 255, 255, 210))
        p.drawText(QRectF(left + 130, r.top() + 172, r.width() - left - 160, 20), Qt.AlignmentFlag.AlignLeft,
                   "  ·  ".join(details))
        days = self.data.get("days") or []
        if days:
            n = len(days)
            h = min(118.0, r.height() * 0.32)
            y = r.bottom() - h - 16
            w = (r.width() - 56 - (n - 1) * 10) / n
            from omniwrench.core.i18n import current_language
            loc = QLocale(current_language() or QLocale().name())
            for i, d in enumerate(days):
                card = QRectF(left + i * (w + 10), y, w, h)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 46))
                p.drawRoundedRect(card, 12, 12)
                p.setPen(QColor("white"))
                p.setFont(self._font(9.5, True))
                date = QDate.fromString(d.get("date", ""), "yyyy-MM-dd")
                label = tr("va.w.today") if i == 0 else (loc.dayName(date.dayOfWeek(), QLocale.FormatType.ShortFormat)
                                                          if date.isValid() else d.get("date", ""))
                p.drawText(QRectF(card.left(), card.top() + 6, w, 18), Qt.AlignmentFlag.AlignCenter, label)
                p.setFont(self._font(min(22.0, h * 0.2)))
                p.drawText(QRectF(card.left(), card.top() + 24, w, h * 0.38), Qt.AlignmentFlag.AlignCenter,
                           d.get("icon", ""))
                p.setFont(self._font(10, True))
                mx, mn = d.get("max"), d.get("min")
                temps = f"{round(mx)}° / {round(mn)}°" if isinstance(mx, (int, float)) and isinstance(mn, (int, float)) \
                    else ""
                p.drawText(QRectF(card.left(), card.bottom() - 40, w, 18), Qt.AlignmentFlag.AlignCenter, temps)
                if isinstance(d.get("rain_chance"), (int, float)):
                    p.setFont(self._font(8.5))
                    p.setPen(QColor("#bae6fd"))
                    p.drawText(QRectF(card.left(), card.bottom() - 22, w, 16), Qt.AlignmentFlag.AlignCenter,
                               f"💧 {round(d['rain_chance'])} %")
        p.setOpacity(1.0)
        p.setPen(QColor(255, 255, 255, 140))
        p.setFont(self._font(7.5))
        p.drawText(QRectF(r.left(), r.bottom() - 14, r.width() - 14, 12), Qt.AlignmentFlag.AlignRight,
                   self.data.get("source", ""))

    def _weather_fx(self, p: QPainter, r: QRectF, kind: str, day: bool, t: float) -> None:
        if kind == "clear":
            cx, cy = r.right() - r.width() * 0.2, r.top() + r.height() * 0.28
            if day:
                p.save()
                p.translate(cx, cy)
                p.rotate(t * 12)
                p.setPen(QPen(QColor(255, 236, 160, 90), 6, cap=Qt.PenCapStyle.RoundCap))
                for i in range(12):
                    p.rotate(30)
                    p.drawLine(QPointF(70, 0), QPointF(100 + 8 * math.sin(t * 2 + i), 0))
                p.restore()
                glow = QRadialGradient(QPointF(cx, cy), 70)
                glow.setColorAt(0, QColor(255, 240, 180, 230))
                glow.setColorAt(1, QColor(255, 200, 80, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glow)
                p.drawEllipse(QPointF(cx, cy), 70, 70)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 200))
                rnd = random.Random(7)
                for _ in range(40):
                    a = 0.5 + 0.5 * math.sin(t * 2 + rnd.random() * 6)
                    p.setOpacity(0.3 + 0.7 * a)
                    p.drawEllipse(QPointF(r.left() + rnd.random() * r.width(), r.top() + rnd.random() * r.height() * 0.6),
                                  1.5, 1.5)
                p.setOpacity(1.0)
        if kind in ("cloudy", "rain", "storm", "snow", "fog"):
            rnd = random.Random(3)
            for i in range(5):
                speed = 6 + rnd.random() * 10
                x = (rnd.random() * r.width() + t * speed) % (r.width() + 260) - 130 + r.left()
                y = r.top() + 20 + rnd.random() * r.height() * 0.35
                self._cloud(p, x, y, 0.7 + rnd.random() * 0.8, 70 if kind != "fog" else 110)
        if kind in ("rain", "storm"):
            p.setPen(QPen(QColor(200, 225, 255, 150), 1.6))
            for part in self._particles:
                part[1] = (part[1] + 0.025 * part[2]) % 1.0
                x, y = r.left() + part[0] * r.width(), r.top() + part[1] * r.height()
                p.drawLine(QPointF(x, y), QPointF(x - 3, y + 12 * part[2]))
        if kind == "snow":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 220))
            for part in self._particles:
                part[1] = (part[1] + 0.004 * part[2]) % 1.0
                x = r.left() + (part[0] + 0.02 * math.sin(t + part[2] * 9)) * r.width()
                p.drawEllipse(QPointF(x, r.top() + part[1] * r.height()), 2.2 * part[2], 2.2 * part[2])
        if kind == "storm" and (t % 4.0) < 0.12:
            p.fillRect(r, QColor(255, 255, 255, 120))

    @staticmethod
    def _cloud(p: QPainter, x: float, y: float, scale: float, alpha: int) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, alpha))
        for dx, dy, rad in ((0, 0, 26), (28, -12, 32), (60, 0, 26), (30, 8, 28)):
            p.drawEllipse(QPointF(x + dx * scale, y + dy * scale), rad * scale, rad * scale)

    # --- Nachrichten ---------------------------------------------------------------------------------
    def _paint_news(self, p: QPainter, r: QRectF) -> None:
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#111827"))
        g.setColorAt(1, QColor("#7f1d1d"))
        p.fillRect(r, g)
        tr = self.tr_
        left = r.left() + 24
        p.setPen(QColor("#fca5a5"))
        p.setFont(self._font(9, True))
        p.drawText(QRectF(left, r.top() + 16, 200, 18), Qt.AlignmentFlag.AlignLeft, "● " + tr("va.n.live"))
        p.setPen(QColor("white"))
        p.setFont(self._font(15, True))
        topic = self.data.get("topic") or tr("va.n.headlines")
        p.drawText(QRectF(left, r.top() + 34, r.width() - 80, 28), Qt.AlignmentFlag.AlignLeft, topic)
        items = self.data.get("items") or []
        ticker_h = 34
        y = r.top() + 72
        avail = r.bottom() - ticker_h - 10
        since = time.time() - self._shown_at
        for i, it in enumerate(items):
            if y + 40 > avail:
                break
            appear = min(1.0, max(0.0, (since - i * 0.12) / 0.4))
            p.setOpacity(appear)
            row = QRectF(left - 8 + (1 - appear) * 30, y, r.width() - 48, 44)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 22))
            p.drawRoundedRect(row, 10, 10)
            p.setPen(QColor("white"))
            p.setFont(self._font(10.5, True))
            p.drawText(row.adjusted(12, 4, -12, -18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(it.get("title", ""), Qt.TextElideMode.ElideRight,
                                                  int(row.width() - 24)))
            p.setPen(QColor("#fecaca"))
            p.setFont(self._font(8.5))
            p.drawText(row.adjusted(12, 24, -12, -4), Qt.AlignmentFlag.AlignLeft,
                       " · ".join(x for x in (it.get("source"), it.get("time")) if x))
            self._links.append((row, it.get("link", "")))
            y += 52
        p.setOpacity(1.0)
        bar = QRectF(r.left(), r.bottom() - ticker_h, r.width(), ticker_h)
        p.fillRect(bar, QColor("#dc2626"))
        text = "   +++   ".join(it.get("title", "") for it in items) + "   +++   "
        p.setPen(QColor("white"))
        p.setFont(self._font(10.5, True))
        width = p.fontMetrics().horizontalAdvance(text) or 1
        self._ticker = (self._ticker + 1.6) % width
        x = bar.left() - self._ticker
        while x < bar.right():
            p.drawText(QRectF(x, bar.top(), width, ticker_h), Qt.AlignmentFlag.AlignVCenter, text)
            x += width

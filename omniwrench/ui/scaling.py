"""Skalierung der Oberfläche und bildschirmabhängige Größen.

Die Skalierung aus den Anzeigeeinstellungen wirkt über QT_SCALE_FACTOR - zusätzlich zur
Windows-Anzeigeskalierung - und muss deshalb vor dem Erzeugen der QApplication gesetzt werden.
Alle festen Größen im Code sind logische Pixel und wachsen damit automatisch mit.
"""

from __future__ import annotations

import math
import os
import sys

from PySide6.QtCore import QProcess, QRect, QSize
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

# Auswahl in den Anzeigeeinstellungen (Faktor 1.0 = Windows-Einstellung unverändert)
SCALE_CHOICES = (0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
_ENV = "QT_SCALE_FACTOR"
_MARK = "OMNIWRENCH_SCALE_FACTOR"  # merkt sich, dass QT_SCALE_FACTOR von uns stammt (Neustart erbt die Umgebung)


def normalize(value) -> float:
    try:
        factor = float(value)
    except (TypeError, ValueError):
        return 1.0
    return min(max(factor, SCALE_CHOICES[0]), SCALE_CHOICES[-1])


def apply_scale_factor(value) -> None:
    """Setzt den globalen Skalierungsfaktor. Nur vor QApplication(...) wirksam."""
    if os.environ.get(_MARK):  # Wert aus einem vorherigen Start (Neustart-Prozess) verwerfen
        os.environ.pop(_ENV, None)
        os.environ.pop(_MARK, None)
    elif _ENV in os.environ:
        return  # von außen gesetzt (z. B. zum Testen) - hat Vorrang
    factor = normalize(value)
    if abs(factor - 1.0) > 0.001:
        os.environ[_ENV] = f"{factor:g}"
        os.environ[_MARK] = "1"


def device_pixel_ratio() -> float:
    """Größtes Pixelverhältnis aller Bildschirme - Bilder in dieser Auflösung bleiben überall scharf."""
    app = QGuiApplication.instance()
    screens = app.screens() if app else []
    return max([s.devicePixelRatio() for s in screens] + [1.0])


def device_pixels(logical: int | float, ratio: float | None = None) -> int:
    """Benötigte echte Pixel für eine logische Größe."""
    return max(1, math.ceil(logical * (ratio or device_pixel_ratio())))


def _available(widget: QWidget | None = None) -> QRect:
    screen = None
    if widget is not None:
        screen = widget.screen()
        if parent := widget.parentWidget():
            screen = parent.screen() or screen
    screen = screen or QGuiApplication.primaryScreen()
    return screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)


def fit_size(width: int, height: int, widget: QWidget | None = None, fraction: float = 0.92) -> QSize:
    """Wunschgröße, höchstens `fraction` des freien Bildschirmbereichs."""
    area = _available(widget)
    return QSize(min(width, int(area.width() * fraction)), min(height, int(area.height() * fraction)))


def fit_to_screen(widget: QWidget, width: int, height: int, fraction: float = 0.92) -> None:
    """resize() für Dialoge: passt auch bei hoher Skalierung auf kleine Bildschirme."""
    widget.resize(fit_size(width, height, widget, fraction))


def fit_min_width(widget: QWidget, width: int, fraction: float = 0.95) -> None:
    """setMinimumWidth(), das nie breiter als der Bildschirm wird (z. B. 1366 px bei 200 % Skalierung)."""
    widget.setMinimumWidth(min(width, int(_available(widget).width() * fraction)))


def window_size(widget: QWidget | None = None) -> QSize:
    """Startgröße des Hauptfensters: ein großer Teil des Bildschirms, ohne ihn zu füllen."""
    area = _available(widget)
    w = min(max(int(area.width() * 0.8), 960), area.width())
    h = min(max(int(area.height() * 0.82), 640), area.height())
    return QSize(w, h)


def clamp(value: float, low: int, high: int) -> int:
    return int(min(max(value, low), high))


def restart_application() -> bool:
    """Startet OmniWrench als neuen Prozess (die Anmeldung erfolgt dort erneut)."""
    if getattr(sys, "frozen", False):
        program, args = sys.executable, sys.argv[1:]
    else:
        program, args = sys.executable, sys.argv
    result = QProcess.startDetached(program, args, os.getcwd())
    return bool(result[0] if isinstance(result, tuple) else result)

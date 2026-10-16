"""Aufbereitung und Export von Symbolen (SVG, PNG, ICO, PDF, JPG)."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPixmap
from PySide6.QtSvg import QSvgRenderer

FORMATS = ["svg", "png", "ico", "pdf", "jpg"]
SIZES = [16, 24, 32, 48, 64, 128, 256, 512]
ICO_MAX = 256


def screen_ratio() -> float:
    """Pixeldichte für Vorschaubilder: höchste aller Bildschirme, mindestens 2 (scharf auch bei 300 %)."""
    screens = QGuiApplication.screens()
    return max([2.0, *(s.devicePixelRatio() for s in screens)])


def render_pixmap(svg: bytes, size: int) -> QPixmap:
    """Vorschaubild in logischer Größe size, gerendert in Bildschirm-Pixeldichte."""
    ratio = screen_ratio()
    pix = QPixmap.fromImage(render(svg, round(size * ratio)))
    pix.setDevicePixelRatio(ratio)
    return pix


@dataclass
class Style:
    color: str = "#1f2937"
    stroke: float = 2.0
    background: str = "none"         # none | square | circle
    bg_color: str = "#3b82f6"
    padding: float = 0.18            # Anteil Rand, wenn ein Hintergrund gezeichnet wird


def _viewbox(attrs: str) -> tuple[float, float, float, float]:
    m = re.search(r'viewBox="([^"]+)"', attrs)
    if m:
        parts = [float(x) for x in re.split(r"[ ,]+", m.group(1).strip())[:4]]
        if len(parts) == 4:
            return tuple(parts)  # type: ignore[return-value]
    w = re.search(r'\bwidth="([\d.]+)', attrs)
    h = re.search(r'\bheight="([\d.]+)', attrs)
    return 0.0, 0.0, float(w.group(1)) if w else 24.0, float(h.group(1)) if h else 24.0


def build_svg(svg: bytes, style: Style) -> bytes:
    """Symbol einfärben, Strichstärke setzen und optional auf einen Hintergrund legen.

    Strich-Symbole (stroke=currentColor, z. B. Lucide/Tabler) und Flächen-Symbole
    (fill=currentColor oder ganz ohne Farbangabe, z. B. Material/Simple Icons) werden
    gleichermaßen unterstützt.
    """
    text = svg.decode("utf-8", errors="replace")
    text = re.sub(r"<!--.*?-->|<\?xml.*?\?>|<!DOCTYPE.*?>", "", text, flags=re.S).strip()
    root = re.search(r"<svg\b([^>]*)>", text, flags=re.S)
    if root is None:
        return svg
    attrs = root.group(1)
    if "currentColor" in text:
        text = text.replace("currentColor", style.color)
    else:
        colors = set(re.findall(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,8}|black|white)"', text))
        if len(colors) == 1:
            # Einfarbiges Symbol mit fest eingetragener Farbe -> umfärben
            only = colors.pop()
            text = re.sub(rf'((?:fill|stroke)=")({re.escape(only)})(")', rf"\g<1>{style.color}\g<3>", text)
        elif not colors and not re.search(r'\sfill="', attrs):
            # Ganz ohne Farbangabe (z. B. Material): Füllfarbe am Wurzelelement setzen (wird vererbt)
            new_attrs = attrs + f' fill="{style.color}"'
            text = text.replace(f"<svg{attrs}>", f"<svg{new_attrs}>", 1)
        # mehrfarbige Symbole behalten ihre Farben
    text = re.sub(r'stroke-width="[\d.]+"', f'stroke-width="{style.stroke:g}"', text, count=1)
    if style.background == "none":
        return text.encode("utf-8")

    attrs = re.search(r"<svg\b([^>]*)>", text, flags=re.S).group(1)
    inner = re.search(r"<svg\b[^>]*>(.*)</svg>", text, flags=re.S).group(1)
    keep = " ".join(re.findall(r'(?:fill|stroke|stroke-width|stroke-linecap|stroke-linejoin)="[^"]*"', attrs))
    x, y, w, h = _viewbox(attrs)
    size = max(w, h)
    scale = 1 - 2 * style.padding
    # Symbol zentriert und verkleinert in ein quadratisches Feld der Größe size legen
    tx = (size - w * scale) / 2 - x * scale
    ty = (size - h * scale) / 2 - y * scale
    shape = (f'<circle cx="{size / 2:g}" cy="{size / 2:g}" r="{size / 2:g}" fill="{style.bg_color}"/>'
             if style.background == "circle"
             else f'<rect width="{size:g}" height="{size:g}" rx="{size * 0.21:g}" fill="{style.bg_color}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size:g}" height="{size:g}" viewBox="0 0 {size:g} {size:g}">'
            f'{shape}<g transform="translate({tx:g} {ty:g}) scale({scale:g})" {keep}>{inner}</g></svg>').encode("utf-8")


def render(svg: bytes, size: int, background: str | None = None) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(background) if background else Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg)).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, svg: bytes, sizes: list[int]) -> None:
    """ICO mit mehreren Größen (PNG-komprimierte Einträge, ab Windows Vista unterstützt)."""
    sizes = sorted({min(s, ICO_MAX) for s in sizes}) or [256]
    images = [png_bytes(render(svg, s)) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, data = b"", b""
    for s, img in zip(sizes, images):
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(img), offset + len(data))
        data += img
    path.write_bytes(header + entries + data)


def write_pdf(path: Path, svg: bytes, size: int) -> None:
    """Vektor-PDF (gut für Visio, Word, Druck). size = Kantenlänge in Punkt."""
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QSizeF(size, size), QPageSize.Unit.Point))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
    writer.setResolution(72)
    painter = QPainter(writer)
    QSvgRenderer(QByteArray(svg)).render(painter, QRectF(0, 0, size, size))
    painter.end()


def export(path: Path, fmt: str, svg: bytes, sizes: list[int], jpg_background: str = "#ffffff") -> list[Path]:
    """Exportiert ein Symbol. Mehrere Größen bei PNG/JPG -> eine Datei je Größe (name_32.png …)."""
    sizes = sorted(set(sizes)) or [256]
    written: list[Path] = []
    if fmt == "svg":
        path.write_bytes(svg)
        written.append(path)
    elif fmt == "ico":
        write_ico(path, svg, sizes)
        written.append(path)
    elif fmt == "pdf":
        write_pdf(path, svg, sizes[-1])
        written.append(path)
    elif fmt in ("png", "jpg"):
        for s in sizes:
            target = path if len(sizes) == 1 else path.with_name(f"{path.stem}_{s}{path.suffix}")
            image = render(svg, s, jpg_background if fmt == "jpg" else None)
            if fmt == "jpg":
                image = image.convertToFormat(QImage.Format.Format_RGB32)
            image.save(str(target), fmt.upper(), 95 if fmt == "jpg" else -1)
            written.append(target)
    else:
        raise ValueError(fmt)
    return written

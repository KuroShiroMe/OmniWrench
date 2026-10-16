"""Aufbereitung und Export von Symbolen (SVG, PNG, ICO, PDF, JPG)."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtSvg import QSvgRenderer

FORMATS = ["svg", "png", "ico", "pdf", "jpg"]
SIZES = [16, 24, 32, 48, 64, 128, 256, 512]
ICO_MAX = 256


@dataclass
class Style:
    color: str = "#1f2937"
    stroke: float = 2.0
    background: str = "none"         # none | square | circle
    bg_color: str = "#3b82f6"
    padding: float = 0.18            # Anteil Rand, wenn ein Hintergrund gezeichnet wird


def build_svg(svg: bytes, style: Style) -> bytes:
    """Lucide-SVG (24x24, stroke=currentColor) mit Farbe, Strichstärke und Hintergrund."""
    text = svg.decode("utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()
    text = text.replace("currentColor", style.color)
    text = re.sub(r'stroke-width="[\d.]+"', f'stroke-width="{style.stroke:g}"', text, count=1)
    if style.background == "none":
        return text.encode("utf-8")
    inner = re.search(r"<svg[^>]*>(.*)</svg>", text, flags=re.S).group(1)
    attrs = re.search(r"<svg([^>]*)>", text, flags=re.S).group(1)
    keep = " ".join(re.findall(r'(?:fill|stroke|stroke-width|stroke-linecap|stroke-linejoin)="[^"]*"', attrs))
    scale = 1 - 2 * style.padding
    offset = 12 * (1 - scale)
    shape = (f'<circle cx="12" cy="12" r="12" fill="{style.bg_color}"/>' if style.background == "circle"
             else f'<rect width="24" height="24" rx="5" fill="{style.bg_color}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">{shape}'
            f'<g transform="translate({offset:g} {offset:g}) scale({scale:g})" {keep}>{inner}</g></svg>'
            ).encode("utf-8")


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

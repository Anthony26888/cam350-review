"""Write the picture of the Gerber viewer to a file.

The picture is written from the same paths the viewer draws, so that the
file shows exactly what the screen shows: the same layers, the same
colours and the same negative content, which removes the artwork it is
put on.

Three formats are supported:

* ``png`` is a picture, drawn the way the viewer draws it: every layer is
  rasterised on its own and the negative content is erased from it.
* ``pdf`` and ``svg`` are vector files.  A vector surface cannot erase,
  so the negative content is drawn with the colour of the background,
  which gives the same picture.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QMarginsF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPainterPath,
    QPdfWriter,
    QPen,
)
from PySide6.QtSvg import QSvgGenerator

from services.gerber.render.layer import LayerPaths

#: The formats that can be written.
FORMATS = ("png", "pdf", "svg")


@dataclass
class ExportLayer:
    """One layer of the picture that is written."""

    #: The geometry of the layer, in scene coordinates.
    paths: LayerPaths
    #: The colour the layer is drawn with.
    color: QColor = field(default_factory=lambda: QColor("#FFFFFF"))


def layers_bounds(layers: Sequence[ExportLayer]) -> QRectF:
    """The area that all the layers cover."""
    rect = QRectF()
    for layer in layers:
        bounds = layer.paths.bounds()
        if bounds.isEmpty():
            continue
        rect = rect.united(bounds)
    return rect


def export_layers(
    layers: Sequence[ExportLayer],
    path: str,
    fmt: str = "png",
    width_px: int = 1920,
    background: str = "#0B1220",
    margin_mm: float = 10.0,
) -> str:
    """Write the layers to a file and return the path that was written.

    ``width_px`` is the width of the picture in pixels for a picture, and
    the width of the drawing in points for a vector file.
    """
    fmt = (fmt or "png").lower().lstrip(".")
    if fmt not in FORMATS:
        raise ValueError("unknown export format %r" % fmt)
    if not layers:
        raise ValueError("nothing to export: no visible layer")
    rect = layers_bounds(layers)
    if rect.isEmpty() or rect.width() <= 0.0 or rect.height() <= 0.0:
        raise ValueError("nothing to export: no visible geometry")

    if fmt == "png":
        _write_png(layers, path, rect, width_px, background)
    elif fmt == "pdf":
        _write_pdf(layers, path, rect, width_px, background, margin_mm)
    else:
        _write_svg(layers, path, rect, width_px, background)
    return path


# ----------------------------------------------------------------------
# the picture
# ----------------------------------------------------------------------
def _paint_raster(painter: QPainter, layers: Sequence[ExportLayer],
                  rect: QRectF, scale: float, background: QColor) -> None:
    """Draw the layers the way the viewer draws them.

    Every layer is drawn on its own image, where the negative content can
    be erased from the artwork underneath it.
    """
    for layer in layers:
        image = QImage(painter.device().width(), painter.device().height(),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        buf = QPainter(image)
        buf.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        buf.scale(scale, scale)
        buf.translate(-rect.left(), -rect.top())
        _paint_layer(buf, layer, background, erase=True)
        buf.end()
        painter.drawImage(0, 0, image)


def _paint_vector(painter: QPainter, layers: Sequence[ExportLayer],
                  rect: QRectF, scale: float, background: QColor) -> None:
    """Draw the layers as vector shapes.

    A vector surface cannot erase, so the negative content is drawn with
    the colour of the background.
    """
    for layer in layers:
        _paint_layer(painter, layer, background, erase=False)


def _paint_layer(painter: QPainter, layer: ExportLayer, background: QColor,
                 erase: bool) -> None:
    """Draw one layer, in the order of the file.

    A negative object removes the artwork that was drawn before it, so the
    parts have to be drawn one after the other.  A surface that cannot
    erase gets the negative objects in the colour of the background, which
    gives the same picture.
    """
    paths = layer.paths
    colour = QColor(layer.color)
    colour.setAlpha(255)
    clear_colour = colour if erase else QColor(background)
    clear_colour.setAlpha(255)
    current_clear = None
    for op in paths.ops:
        if op.clear != current_clear:
            current_clear = op.clear
            if erase:
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_Clear
                    if op.clear else
                    QPainter.CompositionMode.CompositionMode_SourceOver)
            pen_colour = clear_colour if op.clear else colour
        else:
            pen_colour = clear_colour if op.clear else colour
        if op.fill:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(pen_colour))
        else:
            painter.setPen(QPen(pen_colour, op.width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(op.path)
        if erase:
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)


# ----------------------------------------------------------------------
# the files
# ----------------------------------------------------------------------
def _write_png(layers: Sequence[ExportLayer], path: str, rect: QRectF,
               width_px: int, background: str) -> None:
    """Write a picture."""
    width_px = max(64, int(width_px))
    scale = width_px / rect.width()
    height_px = max(1, int(round(rect.height() * scale)))
    image = QImage(width_px, height_px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(background))
    painter = QPainter(image)
    try:
        _paint_raster(painter, layers, rect, scale, QColor(background))
    finally:
        painter.end()
    if not image.save(path, "PNG"):
        raise IOError("could not write %s" % path)


def _write_pdf(layers: Sequence[ExportLayer], path: str, rect: QRectF,
               width_px: int, background: str, margin_mm: float) -> None:
    """Write a vector file with one page."""
    writer = QPdfWriter(path)
    writer.setResolution(1200)
    layout = QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                          QPageLayout.Orientation.Landscape,
                          QMarginsF(margin_mm, margin_mm, margin_mm, margin_mm),
                          QPageLayout.Unit.Millimeter)
    writer.setPageLayout(layout)
    writer.setTitle("Gerber")
    page = writer.pageLayout().paintRectPixels(writer.resolution())
    painter = QPainter(writer)
    try:
        painter.fillRect(page, QColor(background))
        scale = min(page.width() / rect.width(), page.height() / rect.height())
        painter.translate((page.width() - rect.width() * scale) / 2.0,
                          (page.height() - rect.height() * scale) / 2.0)
        painter.scale(scale, scale)
        painter.translate(-rect.left(), -rect.top())
        _paint_vector(painter, layers, rect, scale, QColor(background))
    finally:
        painter.end()


def _write_svg(layers: Sequence[ExportLayer], path: str, rect: QRectF,
               width_px: int, background: str) -> None:
    """Write a vector file."""
    width_px = max(64, int(width_px))
    scale = width_px / rect.width()
    height_px = max(1, int(round(rect.height() * scale)))
    generator = QSvgGenerator()
    generator.setFileName(path)
    generator.setSize(QSize(width_px, height_px))
    generator.setViewBox(QRectF(0, 0, width_px, height_px))
    generator.setTitle("Gerber")
    generator.setDescription("Gerber layers of the CAM350 Review")
    painter = QPainter(generator)
    try:
        painter.fillRect(QRectF(0, 0, width_px, height_px), QColor(background))
        painter.scale(scale, scale)
        painter.translate(-rect.left(), -rect.top())
        _paint_vector(painter, layers, rect, scale, QColor(background))
    finally:
        painter.end()

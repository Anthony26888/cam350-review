"""Tests for the layer compositing of the Gerber viewer.

A Gerber layer is drawn dark first and the negative content is then
erased from it.  These tests render a layer into an image and look at the
pixels, so they check the compositing itself and not only the geometry.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from services.gerber.gerber_render import FlashShape, LineShape, RenderData
from services.gerber.render.layer import LayerItem, build_layer_paths


def _render(paths, color="#FF0000", size=(200, 200), scale=10.0):
    """Render the layer and return the image.

    The origin of the scene is placed in the middle of the image, so the
    geometry around (0, 0) is what the test looks at.
    """
    image = QImage(size[0], size[1], QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(size[0] / 2.0, size[1] / 2.0)
    painter.scale(scale, scale)
    item = LayerItem(paths, QColor(color))
    item.paint(painter, None, None)
    painter.end()
    return image


class TestLayerPaths:
    def test_dark_and_clear_content_are_separated(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="circle", w=4.0, h=4.0,
                                       seq=0))
        data.flashes.append(FlashShape(cx=1.0, cy=0.0, kind="circle", w=2.0, h=2.0,
                                       negative=True, seq=1))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        assert paths.has_clear is True
        assert [op for op in paths.ops if op.fill and not op.clear]
        assert [op for op in paths.ops if op.fill and op.clear]

    def test_a_layer_without_negatives_needs_no_compositing(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="circle", w=4.0, h=4.0))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        assert paths.has_clear is False
        assert not [op for op in paths.ops if op.clear]

    def test_a_negative_stroke_is_kept_apart(self):
        data = RenderData()
        data.lines.append(LineShape(x1=-5.0, y1=0.0, x2=5.0, y2=0.0, width=1.0, seq=0))
        data.lines.append(LineShape(x1=-5.0, y1=2.0, x2=5.0, y2=2.0, width=1.0,
                                    negative=True, seq=1))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        assert paths.has_clear is True
        dark = [op for op in paths.ops if not op.fill and not op.clear]
        clear = [op for op in paths.ops if not op.fill and op.clear]
        assert len(dark) == 1
        assert len(clear) == 1


class TestOrder:
    def test_the_artwork_that_comes_after_a_negative_object_stays(self):
        # A copper layer holds a negative pour and the positive pads that
        # lie on it.  The pads come after the pour, so they have to stay.
        data = RenderData()
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="rect", w=10.0, h=10.0,
                                       seq=0))
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="circle", w=2.0, h=2.0,
                                       negative=True, seq=1))
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="circle", w=1.0, h=1.0,
                                       seq=2))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        image = _render(paths, size=(120, 120), scale=10.0)
        # The pad that comes after the negative object is still there.
        assert image.pixelColor(60, 60).alpha() > 0
        # The pour around the pad is gone: the negative object removed it.
        assert image.pixelColor(52, 60).alpha() == 0


class TestCompositing:
    def test_a_clear_object_erases_the_dark_artwork(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="circle", w=10.0, h=10.0,
                                       seq=0))
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="circle", w=4.0, h=4.0,
                                       negative=True, seq=1))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        image = _render(paths, size=(120, 120), scale=10.0)
        # The centre of the clear object must be empty.
        assert image.pixelColor(60, 60).alpha() == 0
        # The dark ring around it must be painted.
        assert image.pixelColor(60, 35).alpha() > 0

    def test_dark_artwork_is_painted(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="circle", w=10.0, h=10.0))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        image = _render(paths, size=(120, 120), scale=10.0)
        assert image.pixelColor(60, 60).alpha() > 0
        assert image.pixelColor(60, 60).red() > 200

    def test_a_negative_stroke_erases_what_is_under_it(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="rect", w=10.0, h=10.0,
                                       seq=0))
        data.lines.append(LineShape(x1=-6.0, y1=0.0, x2=6.0, y2=0.0, width=2.0,
                                    negative=True, seq=1))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        image = _render(paths, size=(140, 140), scale=10.0)
        # On the stroke the artwork is gone.
        assert image.pixelColor(70, 70).alpha() == 0
        # Away from the stroke it is still there.
        assert image.pixelColor(70, 45).alpha() > 0

    def test_a_layer_without_negatives_is_fully_painted(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="rect", w=10.0, h=10.0))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        image = _render(paths, size=(120, 120), scale=10.0)
        assert image.pixelColor(60, 60).alpha() > 0
        assert image.pixelColor(60, 70).alpha() > 0


class TestQualityPolicy:
    """The supersampled render has to look like the antialiased one."""

    def _alpha_difference(self, a, b) -> float:
        total = 0
        count = 0
        for y in range(0, a.height(), 2):
            for x in range(0, a.width(), 2):
                total += abs(a.pixelColor(x, y).alpha() - b.pixelColor(x, y).alpha())
                count += 1
        return total / max(1, count)

    def test_thin_strokes_use_antialiasing(self):
        data = RenderData()
        data.lines.append(LineShape(x1=-5.0, y1=0.0, x2=5.0, y2=0.0, width=0.05))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        item = LayerItem(paths, QColor(255, 0, 0))
        # 0.05 mm at 5 px/mm is a quarter of a pixel: antialiasing is cheap.
        assert item._quality(5.0) == (1, True)

    def test_wide_strokes_are_supersampled(self):
        data = RenderData()
        data.lines.append(LineShape(x1=-5.0, y1=0.0, x2=5.0, y2=0.0, width=0.4))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        item = LayerItem(paths, QColor(255, 0, 0))
        # 0.4 mm at 20 px/mm is eight pixels wide: the antialiased stroker
        # would cost far more than drawing it twice as big.
        assert item._quality(20.0) == (2, False)

    def test_the_supersampled_picture_matches_the_antialiased_one(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="circle", w=1.0, h=1.0))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        colour = QColor(255, 0, 0)
        rect = QRectF(-10.0, -10.0, 20.0, 20.0)

        reference = LayerItem(paths, colour)
        reference._quality = lambda scale: (1, True)  # noqa: SLF001 - test hook
        antialiased, _ = reference._render(rect, 20.0)  # noqa: SLF001

        item = LayerItem(paths, colour)
        supersampled, _ = item._render(rect, 20.0)  # noqa: SLF001

        assert self._alpha_difference(antialiased, supersampled) < 12.0

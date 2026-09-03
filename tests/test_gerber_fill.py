import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

from services.gerber.gerber_render import ApertureMacro, FlashShape
from ui.gerber_viewer import _build_fill_path


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _circle(cx, cy, diameter, negative=False):
    return FlashShape(cx, cy, "circle", diameter, 0.0, 0.0, None, negative=negative)


def _round_rect_macro_pad():
    macro = ApertureMacro(
        polygons=[[(1.0, 0.5), (1.0, -0.5), (-1.0, -0.5), (-1.0, 0.5)]],
        circles=[(0.8, 0.3, 0.3), (0.8, -0.3, 0.3), (-0.8, 0.3, 0.3), (-0.8, -0.3, 0.3)],
    )
    return FlashShape(0.0, 0.0, "macro", 0.0, 0.0, 0.0, None, macro=macro)


def _expanded_round_rect_pad():
    """A RoundRect pad as gerbonara expands it: separate rect + circle flashes.

    Matches the F_Paste D11 pad (4 edge rects + 4 corner circles), whose
    mixed windings previously produced a hollow ring under WindingFill.
    """
    r = 0.159
    half = r / 2.0
    w = 0.201
    return [
        FlashShape(9.845, 1.4005, "rect", r, r, 180.0),
        FlashShape(9.7655, 1.3, "rect", w, r, -90.0),
        FlashShape(9.845, 1.1995, "rect", r, r, 0.0),
        FlashShape(9.9245, 1.3, "rect", w, r, 90.0),
        FlashShape(9.9245, 1.4005, "circle", r, 0.0, 0.0),
        FlashShape(9.7655, 1.4005, "circle", r, 0.0, 0.0),
        FlashShape(9.7655, 1.1995, "circle", r, 0.0, 0.0),
        FlashShape(9.9245, 1.1995, "circle", r, 0.0, 0.0),
    ]


def _kicad_round_rect_macro_pad():
    """A KiCad roundrect pad macro: lower-left body rect + 4 corner circles +
    2 horizontal segments (the shape emitted by KiCad's aperture macro)."""
    macro = ApertureMacro(
        polygons=[[(-0.01555, -0.010017), (0.01555, -0.010017),
                   (0.01555, 0.010017), (-0.01555, 0.010017)]],
        circles=[(-0.010017, 0.010017, 0.005533),
                 (0.010017, 0.010017, 0.005533),
                 (-0.010017, -0.010017, 0.005533),
                 (0.010017, -0.010017, 0.005533)],
        segments=[(-0.010017, 0.010017, 0.010017, 0.010017, 0.011066),
                  (-0.010017, -0.010017, 0.010017, -0.010017, 0.011066)],
    )
    return FlashShape(0.0, 0.0, "macro", 0.0, 0.0, 0.0, None, macro=macro)


def _render_fill(flashes, size=400):
    path = _build_fill_path(flashes, False, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert path.fillRule() == Qt.WindingFill
    bb = path.boundingRect()
    img = QImage(size, size, QImage.Format_RGB32)
    img.fill(0)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(Qt.white)
    painter.scale(size / bb.width(), size / bb.height())
    painter.translate(-bb.x(), -bb.y())
    painter.drawPath(path)
    painter.end()
    return img, bb


def _is_filled(img, bb, size, x, y):
    px = int((x - bb.x()) * size / bb.width())
    py = int((-y - bb.y()) * size / bb.height())
    c = img.pixel(px, py)
    return ((c >> 16) & 255) + ((c >> 8) & 255) + (c & 255) > 600


def test_overlapping_circles_use_winding_fill(app):
    flashes = [_circle(0.0, 0.0, 2.0), _circle(1.5, 0.0, 2.0)]
    path = _build_fill_path(flashes, False, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert path.fillRule() == Qt.WindingFill
    assert not path.isEmpty()


def test_round_rect_macro_pad_uses_winding_fill(app):
    path = _build_fill_path([_round_rect_macro_pad()], False, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert path.fillRule() == Qt.WindingFill
    assert not path.isEmpty()


def test_negative_flash_keeps_winding_fill(app):
    flashes = [
        _circle(0.0, 0.0, 4.0),
        _circle(0.0, 0.0, 1.0, negative=True),
    ]
    path = _build_fill_path(flashes, False, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert path.fillRule() == Qt.WindingFill
    assert not path.isEmpty()


def test_expanded_round_rect_pad_renders_solid(app):
    """Expanded RoundRect pad must fill solid, not a hollow ring/cut-lines."""
    flashes = _expanded_round_rect_pad()
    img, bb = _render_fill(flashes)
    size = img.width()
    probes = [
        (9.845, 1.3),      # center
        (9.8, 1.25),       # mid-left
        (9.9, 1.35),       # mid-right
        (9.8, 1.35),       # upper-left
        (9.9, 1.25),       # lower-right
        (9.845, 1.38),     # top edge middle
        (9.845, 1.22),     # bottom edge middle
    ]
    assert all(_is_filled(img, bb, size, x, y) for x, y in probes)


def test_kicad_round_rect_pad_segments_fill_solid(app):
    """KiCad roundrect macro segments must fill the top/bottom edges, not
    leave concave cut-lines (previously the segment quad had zero area)."""
    img, bb = _render_fill([_kicad_round_rect_macro_pad()])
    size = img.width()
    probes = [
        (0.0, 0.0),           # center
        (0.0, 0.012),         # top edge middle (segment)
        (0.0, -0.012),        # bottom edge middle (segment)
        (0.0, 0.007),         # inside body rect, upper area
        (0.0, -0.007),        # inside body rect, lower area
        (0.013, 0.0),         # mid-right
        (-0.013, 0.0),        # mid-left
        (0.0135, 0.0135),     # corner (circle)
        (-0.0135, 0.0135),    # corner (circle)
        (0.0135, -0.0135),    # corner (circle)
        (-0.0135, -0.0135),   # corner (circle)
    ]
    assert all(_is_filled(img, bb, size, x, y) for x, y in probes)
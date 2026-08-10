import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QApplication

from services.gerber.gerber_render import ApertureMacro, FlashShape
from ui.gerber_viewer import _add_flash


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _points(path: QPainterPath):
    return [
        (path.elementAt(i).x, path.elementAt(i).y)
        for i in range(path.elementCount())
    ]


SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def _poly_flash() -> FlashShape:
    return FlashShape(0.0, 0.0, "polygon", 0.0, 0.0, 0.0, list(SQUARE))


def test_polygon_region_rotates_90(app):
    path = QPainterPath()
    _add_flash(path, _poly_flash(), mirror=False, angle=90.0)
    pts = _points(path)
    assert pts[0] == pytest.approx((0.0, 0.0))
    assert pts[1] == pytest.approx((0.0, -10.0))
    assert pts[2] == pytest.approx((-10.0, -10.0))
    assert pts[3] == pytest.approx((-10.0, 0.0))


def test_polygon_region_mirror_zero_center(app):
    path = QPainterPath()
    _add_flash(path, _poly_flash(), mirror=True, angle=0.0)
    pts = _points(path)
    assert pts[0] == pytest.approx((0.0, 0.0))
    assert pts[1] == pytest.approx((-10.0, 0.0))   # (10,0) mirrored about x=0
    assert pts[2] == pytest.approx((-10.0, -10.0))
    assert pts[3] == pytest.approx((0.0, -10.0))


def test_polygon_region_offset_shifts_points(app):
    path = QPainterPath()
    _add_flash(path, _poly_flash(), mirror=False, angle=0.0, off_x=2.0, off_y=-3.0)
    pts = _points(path)
    assert pts[0] == pytest.approx((2.0, 3.0))    # scene y negates (0-3)=3
    assert pts[1] == pytest.approx((12.0, 3.0))
    assert pts[3] == pytest.approx((2.0, -7.0))


def test_local_polygon_flash_keeps_position_after_rotation(app):
    fl = FlashShape(100.0, 200.0, "polygon", 0.0, 0.0, 0.0, list(SQUARE))
    path = QPainterPath()
    _add_flash(path, fl, mirror=False, angle=90.0)
    pts = _points(path)
    # center (100,200) rotated 90 -> (-200,100) gerber -> scene (-200,-100)
    assert pts[0] == pytest.approx((-200.0, -100.0))
    # local (10,0) rotated 90 -> (0,10); scene = gx+lx, -(gy+ly)
    assert pts[1] == pytest.approx((-200.0, -110.0))


def test_macro_polygon_rotates_90(app):
    macro = ApertureMacro(polygons=[list(SQUARE)])
    fl = FlashShape(0.0, 0.0, "macro", 0.0, 0.0, 0.0, macro=macro)
    path = QPainterPath()
    _add_flash(path, fl, mirror=False, angle=90.0)
    pts = _points(path)
    assert pts[0] == pytest.approx((0.0, 0.0))
    assert pts[1] == pytest.approx((0.0, -10.0))
    assert pts[2] == pytest.approx((-10.0, -10.0))
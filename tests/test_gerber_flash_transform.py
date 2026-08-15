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


def _corners(path: QPainterPath):
    return [
        (path.elementAt(i).x, path.elementAt(i).y)
        for i in range(path.elementCount())
        if path.elementAt(i).isLineTo() or path.elementAt(i).isMoveTo()
    ]


def _assert_corners(path: QPainterPath, expected):
    got = sorted((round(x, 6), round(y, 6)) for x, y in _corners(path))
    exp = sorted(expected)
    assert len(got) == len(exp)
    for g, e in zip(got, exp):
        assert g == pytest.approx(e, abs=1e-9)


SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def _poly_flash() -> FlashShape:
    return FlashShape(0.0, 0.0, "polygon", 0.0, 0.0, 0.0, list(SQUARE))


def test_polygon_region_rotates_90(app):
    path = QPainterPath()
    _add_flash(path, _poly_flash(), mirror=False, angle=90.0)
    _assert_corners(path, [(0.0, 0.0), (0.0, -10.0), (-10.0, -10.0), (-10.0, 0.0)])


def test_polygon_region_mirror_zero_center(app):
    path = QPainterPath()
    _add_flash(path, _poly_flash(), mirror=True, angle=0.0)
    _assert_corners(path, [(0.0, 0.0), (-10.0, 0.0), (-10.0, -10.0), (0.0, -10.0)])


def test_polygon_region_offset_shifts_points(app):
    path = QPainterPath()
    _add_flash(path, _poly_flash(), mirror=False, angle=0.0, off_x=2.0, off_y=-3.0)
    _assert_corners(path, [(2.0, 3.0), (12.0, 3.0), (12.0, -7.0), (2.0, -7.0)])


def test_local_polygon_flash_keeps_position_after_rotation(app):
    fl = FlashShape(100.0, 200.0, "polygon", 0.0, 0.0, 0.0, list(SQUARE))
    path = QPainterPath()
    _add_flash(path, fl, mirror=False, angle=90.0)
    # center (100,200) rotated 90 -> (-200,100) gerber -> scene (-200,-100);
    # local (10,0) rotated 90 -> (0,10); scene = gx+lx, -(gy+ly)
    _assert_corners(
        path,
        [(-200.0, -100.0), (-200.0, -110.0), (-210.0, -110.0), (-210.0, -100.0)],
    )


def test_macro_polygon_rotates_90(app):
    macro = ApertureMacro(polygons=[list(SQUARE)])
    fl = FlashShape(0.0, 0.0, "macro", 0.0, 0.0, 0.0, macro=macro)
    path = QPainterPath()
    _add_flash(path, fl, mirror=False, angle=90.0)
    _assert_corners(path, [(0.0, 0.0), (0.0, -10.0), (-10.0, -10.0), (-10.0, 0.0)])
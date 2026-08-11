import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from services.gerber.gerber_render import (
    ArcShape,
    RenderData,
    parse_render,
    _sample_arc,
)
from services.gerber.gerber_render_lib import parse_layer, parse_render_std
from ui.gerber_viewer import _append_arc_path

from PySide6.QtGui import QPainterPath


def test_circle_flash(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX44Y44*%\n%MOMM*%\n%ADD11C,2.000000*%\n"
        "D11*\nX100000Y200000D03*\n"
    )
    d = parse_render_std(str(p))
    assert len(d.flashes) == 1
    fl = d.flashes[0]
    assert fl.kind == "circle"
    assert fl.w == pytest.approx(2.0)
    assert fl.h == pytest.approx(2.0)
    assert fl.cx == pytest.approx(10.0)
    assert fl.cy == pytest.approx(20.0)
    assert fl.negative is False


def test_rect_flash(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX36Y36*%\n%MOIN*%\n%ADD12R,0.100000X0.050000*%\n"
        "D12*\nX393701Y787402D03*\n"
    )
    d = parse_render_std(str(p))
    assert len(d.flashes) == 1
    fl = d.flashes[0]
    assert fl.kind == "rect"
    assert fl.w == pytest.approx(2.54)  # 0.1 in
    assert fl.h == pytest.approx(1.27)  # 0.05 in
    # R aperture has no rotation parameter in the spec, so 0
    assert fl.rot == pytest.approx(0.0)
    assert fl.cx == pytest.approx(10.0)
    assert fl.cy == pytest.approx(20.0)


def test_arc_g02_becomes_arcshape(tmp_path):
    p = tmp_path / "f.gko"
    p.write_text(
        "%FSLAX44Y44*%\n%MOMM*%\n%ADD10C,0.100000*%\nD10*\n"
        "X0Y100000D02*\n"
        "G02X100000Y0I100000J0D01*\n"
    )
    d = parse_render_std(str(p))
    assert len(d.arcs) == 1
    ar = d.arcs[0]
    assert ar.x1 == pytest.approx(0.0)
    assert ar.y1 == pytest.approx(10.0)
    assert ar.x2 == pytest.approx(10.0)
    assert ar.y2 == pytest.approx(0.0)
    # center is absolute (start + I,J)
    assert ar.cx == pytest.approx(10.0)
    assert ar.cy == pytest.approx(10.0)
    assert ar.clockwise is True
    assert ar.width == pytest.approx(0.1)
    assert ar.negative is False


def test_region_polygon(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX36Y36*%\n%MOIN*%\n%ADD10R,0.010000X0.010000*%\n"
        "D10*\nG36*\n"
        "X0Y0D02*\nX393701Y0D01*\nX393701Y393701D01*\nX0Y393701D01*\nX0Y0D01*\n"
        "G37*\n"
    )
    d = parse_render_std(str(p))
    polys = [f for f in d.flashes if f.kind == "polygon" and f.pts]
    assert len(polys) == 1
    assert polys[0].pts[0] == pytest.approx((0.0, 0.0))
    assert polys[0].pts[2] == pytest.approx((10.0, 10.0))
    assert polys[0].negative is False


def test_negative_region_from_lpc(tmp_path):
    p = tmp_path / "f.gto"
    p.write_text(
        "%FSLAX44Y44*%\n%MOMM*%\n%LPC*%\n%ADD10C,1.000000*%\n"
        "D10*\nG36*\n"
        "X0Y0D02*\nX100000Y0D01*\nX100000Y100000D01*\nX0Y100000D01*\nX0Y0D01*\n"
        "G37*\n"
    )
    d = parse_render_std(str(p))
    polys = [f for f in d.flashes if f.kind == "polygon" and f.pts]
    assert len(polys) == 1
    assert polys[0].negative is True


def _midpoint(ar, n=100):
    path = QPainterPath()
    _append_arc_path(path, ar, False, 0.0, 0.0, 0.0, 0.0, 0.0)
    return path.pointAtPercent(0.5)


def test_arc_to_path_clockwise_midpoint():
    ar = ArcShape(x1=0.0, y1=10.0, x2=10.0, y2=0.0, cx=10.0, cy=10.0,
                  clockwise=True, width=0.1)
    expected = _sample_arc(0.0, 10.0, 10.0, 0.0, 10.0, 10.0, True, 100)[50]
    path = QPainterPath()
    _append_arc_path(path, ar, False, 0.0, 0.0, 0.0, 0.0, 0.0)
    mid = path.pointAtPercent(0.5)
    assert math.hypot(mid.x() - expected[0], mid.y() + expected[1]) < 0.5


def test_arc_to_path_counterclockwise_midpoint():
    ar = ArcShape(x1=0.0, y1=10.0, x2=-10.0, y2=0.0, cx=0.0, cy=0.0,
                  clockwise=False, width=0.1)
    expected = _sample_arc(0.0, 10.0, -10.0, 0.0, 0.0, 0.0, False, 100)[50]
    path = QPainterPath()
    _append_arc_path(path, ar, False, 0.0, 0.0, 0.0, 0.0, 0.0)
    mid = path.pointAtPercent(0.5)
    assert math.hypot(mid.x() - expected[0], mid.y() + expected[1]) < 0.5


def test_arc_full_circle_ellipse():
    ar = ArcShape(x1=10.0, y1=0.0, x2=10.0, y2=0.0, cx=5.0, cy=0.0,
                  clockwise=True, width=0.1)
    path = QPainterPath()
    _append_arc_path(path, ar, False, 0.0, 0.0, 0.0, 0.0, 0.0)
    r = path.boundingRect()
    assert r.width() == pytest.approx(10.0, abs=0.001)
    assert r.height() == pytest.approx(10.0, abs=0.001)


def test_parse_layer_falls_back_to_legacy(tmp_path):
    p = tmp_path / "garbage.gko"
    p.write_text("this is not a gerber file at all\n")
    d = parse_layer(str(p))
    assert isinstance(d, RenderData)


def test_legacy_parser_still_works(tmp_path):
    p = tmp_path / "f.gko"
    p.write_text(
        "%FSLAX44Y44*%\n%MOMM*%\n%ADD10C,0.100000*%\nD10*\n"
        "X0Y100000D02*\n"
        "G02X100000Y0I100000J0D01*\n"
    )
    d = parse_render(str(p))
    assert len(d.lines) > 2  # tessellated arc
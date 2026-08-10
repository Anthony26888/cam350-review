import math

import pytest

from services.gerber.gerber_render import (
    parse_render, _parse_macro, _polygon_verts,
)


def test_add_rect_aperture_inch_to_mm(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX36Y36*%\n%MOIN*%\n%ADD10R,0.100000X0.050000*%\n"
        "D10*\nX393701Y787402D03*\n"
    )
    d = parse_render(str(p))
    assert len(d.flashes) == 1
    fl = d.flashes[0]
    assert fl.kind == "rect"
    assert fl.w == pytest.approx(2.54)   # 0.1 in
    assert fl.h == pytest.approx(1.27)   # 0.05 in
    assert fl.cx == pytest.approx(10.0)
    assert fl.cy == pytest.approx(20.0)


def test_add_circle_aperture_mm(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX44Y44*%\n%MOMM*%\n%ADD11C,2.000000*%\n"
        "D11*\nX100000Y200000D03*\n"
    )
    d = parse_render(str(p))
    assert len(d.flashes) == 1
    fl = d.flashes[0]
    assert fl.kind == "circle"
    assert fl.w == pytest.approx(2.0)
    assert fl.cx == pytest.approx(10.0)
    assert fl.cy == pytest.approx(20.0)


def test_draw_segment_width(tmp_path):
    p = tmp_path / "f.gko"
    p.write_text(
        "%FSLAX36Y36*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
        "D10*\n"
        "X0Y0D02*\n"
        "X100000Y0D01*\n"
    )
    d = parse_render(str(p))
    assert len(d.lines) == 1
    ln = d.lines[0]
    assert ln.width == pytest.approx(0.254)  # 0.01 in
    assert (ln.x1, ln.y1) == (pytest.approx(0), pytest.approx(0))
    assert ln.x2 == pytest.approx(2.54)


def test_arc_g02_polyline(tmp_path):
    p = tmp_path / "f.gko"
    p.write_text(
        "%FSLAX44Y44*%\n%MOMM*%\n%ADD10C,0.100000*%\nD10*\n"
        "X0Y100000D02*\n"
        "G02X100000Y0I100000J0D01*\n"
    )
    d = parse_render(str(p))
    assert len(d.lines) > 2
    first = d.lines[0]
    last = d.lines[-1]
    assert math.hypot(first.x1, first.y1 - 10) < 0.5
    assert math.hypot(last.x2 - 10, last.y2) < 0.5
    # arc radius about 10mm (center at start + I,J = (10,10))
    r = math.hypot(first.x1 - 10, first.y1 - 10)
    assert abs(r - 10.0) < 0.5


def test_d02_move_breaks_draw(tmp_path):
    p = tmp_path / "f.gko"
    p.write_text(
        "%FSLAX44Y44*%\n%MOMM*%\n%ADD10C,0.100000*%\nD10*\n"
        "X0Y0D02*\nX100000Y0D01*\nX200000Y0D02*\nX200000Y100000D01*\n"
    )
    d = parse_render(str(p))
    assert len(d.lines) == 2
    assert d.lines[1].x1 == pytest.approx(20.0)
    assert d.lines[1].y1 == pytest.approx(0.0)
    assert d.lines[1].y2 == pytest.approx(10.0)


def test_macro_outline_polygon():
    macro = _parse_macro(
        "4,1,4,0.010000,0.010000,0.020000,0.020000,0.030000,0.010000,0.010000,0.010000",
        25.4,
    )
    assert len(macro.polygons) == 1
    pts = macro.polygons[0]
    assert len(pts) == 4
    assert pts[0] == pytest.approx((0.254, 0.254))


def test_macro_thermal_circle():
    macro = _parse_macro(
        "7,1,0.010000,0.010000,0.050000,0.030000,0.002000", 25.4,
    )
    assert len(macro.circles) == 1
    cx, cy, r = macro.circles[0]
    assert cx == pytest.approx(0.254)
    assert r == pytest.approx(0.025 * 25.4)


def test_macro_center_line_rect():
    macro = _parse_macro(
        "21,1,0.025600,0.026500,0,0,0.0", 25.4,
    )
    assert len(macro.polygons) == 1
    assert len(macro.polygons[0]) == 4
    half_w = 0.0256 / 2.0 * 25.4
    half_h = 0.0265 / 2.0 * 25.4
    xs = [p[0] for p in macro.polygons[0]]
    ys = [p[1] for p in macro.polygons[0]]
    assert max(xs) == pytest.approx(half_w)
    assert max(ys) == pytest.approx(half_h)
    assert min(xs) == pytest.approx(-half_w)
    assert min(ys) == pytest.approx(-half_h)


def test_macro_type1_circle():
    macro = _parse_macro("1,1,0.020000,0.001000,-0.002000", 25.4)
    assert len(macro.circles) == 1
    cx, cy, r = macro.circles[0]
    assert cx == pytest.approx(0.0254)
    assert cy == pytest.approx(-0.0508)
    assert r == pytest.approx(0.254)


def test_macro_roundedrect_altium_style():
    macro = _parse_macro(
        "21,1,0.0256,0.0265,0,0,180.0\n"
        "1,1,0.0090,-0.0083,0.0132\n"
        "1,1,0.0090,0.0083,0.0132\n"
        "1,1,0.0090,0.0083,-0.0132\n"
        "1,1,0.0090,-0.0083,-0.0132",
        25.4,
    )
    assert len(macro.polygons) == 1
    assert len(macro.polygons[0]) == 4
    assert len(macro.circles) == 4
    assert len(macro.segments) == 0
    for seg_len in [
        math.hypot(x2 - x1, y2 - y1)
        for x1, y1, x2, y2, _w in macro.segments
    ]:
        assert seg_len < 5.0


def test_macro_flash(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX36Y36*%\n%MOIN*%\n"
        "%AMA1*\n"
        "4,1,4,0.010000,0.005000,0.010000,-0.005000,-0.010000,-0.005000,-0.010000,0.005000*\n"
        "%\n"
        "%ADD20A1*%\n"
        "D20*\nX393701Y393701D03*\n"
    )
    d = parse_render(str(p))
    assert len(d.flashes) == 1
    fl = d.flashes[0]
    assert fl.kind == "macro"
    assert fl.macro is not None
    assert len(fl.macro.polygons) == 1
    assert fl.cx == pytest.approx(10.0)


def test_polygon_verts_rotation():
    pts = _polygon_verts(10.0, 4, 0.0)
    assert len(pts) == 4
    assert pts[0] == pytest.approx((5.0, 0.0))


def test_macro_multiline_polygon():
    macro = _parse_macro(
        "4,1,4,\n"
        "0.010000,0.010000,\n"
        "0.010000,-0.010000,\n"
        "-0.010000,-0.010000,\n"
        "-0.010000,0.010000,\n"
        "0.0000\n"
        "4,1,3,\n"
        "0.100000,0.100000,\n"
        "0.200000,0.100000,\n"
        "0.150000,0.200000,\n"
        "0.0000\n",
        25.4,
    )
    assert len(macro.polygons) == 2
    assert len(macro.polygons[0]) == 4
    assert macro.polygons[0][0] == pytest.approx((0.254, 0.254))
    assert len(macro.polygons[1]) == 3


def test_macro_multiline_flash(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX36Y36*%\n%MOIN*%\n"
        "%AMA1*\n"
        "4,1,4,\n"
        "0.010000,0.005000,\n"
        "0.010000,-0.005000,\n"
        "-0.010000,-0.005000,\n"
        "-0.010000,0.005000,\n"
        "0.0000\n"
        "%\n"
        "%ADD20A1*%\n"
        "D20*\nX393701Y393701D03*\n"
    )
    d = parse_render(str(p))
    assert len(d.flashes) == 1
    fl = d.flashes[0]
    assert fl.kind == "macro"
    assert fl.macro is not None
    assert len(fl.macro.polygons) == 1
    assert len(fl.macro.polygons[0]) == 4


def test_g36_g37_region_fill(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX36Y36*%\n%MOIN*%\n%ADD10R,0.010000X0.010000*%\n"
        "D10*\nG36*\n"
        "X0Y0D02*\nX393701Y0D01*\nX393701Y393701D01*\nX0Y393701D01*\nX0Y0D01*\n"
        "G37*\n"
    )
    d = parse_render(str(p))
    regions = [f for f in d.flashes if f.kind == "polygon" and f.pts]
    assert len(regions) == 1
    assert len(regions[0].pts) == 4
    assert regions[0].pts[0] == pytest.approx((0.0, 0.0))
    assert regions[0].pts[2] == pytest.approx((10.0, 10.0))
    # region boundaries must NOT be emitted as stroked lines
    assert len(d.lines) == 0


def test_g36_g37_region_thick_aperture_no_strokes(tmp_path):
    p = tmp_path / "f.gto"
    p.write_text(
        "%FSLAX44Y44*%\n%MOMM*%\n%ADD80C,2.000000*%\n"
        "D80*\nG36*\n"
        "X0Y0D02*\nX100000Y0D01*\nX100000Y200000D01*\nX0Y200000D01*\nX0Y0D01*\n"
        "G37*\n"
    )
    d = parse_render(str(p))
    assert [f for f in d.flashes if f.kind == "polygon" and f.pts]
    assert len(d.lines) == 0


def test_draw_outside_region_still_stroked(tmp_path):
    p = tmp_path / "f.gto"
    p.write_text(
        "%FSLAX36Y36*%\n%MOIN*%\n%ADD80C,0.010000*%\n"
        "D80*\nX0Y0D02*\nX100000Y0D01*\n"
    )
    d = parse_render(str(p))
    assert len(d.lines) == 1
    assert d.lines[0].width == pytest.approx(0.254)


def test_fs_trailing_suppression(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSTAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
        "D10*\nX01Y01D03*\n"
    )
    d = parse_render(str(p))
    assert len(d.flashes) == 1
    assert d.flashes[0].cx == pytest.approx(25.4)   # 1.0 in
    assert d.flashes[0].cy == pytest.approx(25.4)   # 1.0 in


def test_bare_d03_flashes_at_current_position(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX36Y36*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
        "D10*\nX393701Y787402D02*\nD03*\n"
    )
    d = parse_render(str(p))
    assert len(d.flashes) == 1
    fl = d.flashes[0]
    assert fl.kind == "circle"
    assert fl.cx == pytest.approx(10.0)
    assert fl.cy == pytest.approx(20.0)


def test_bare_d03_uses_active_aperture(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX36Y36*%\n%MOIN*%\n"
        "%ADD10C,0.010000*%\n%ADD11R,0.100000X0.050000*%\n"
        "D10*\nX0Y0D02*\nD03*\n"
        "D11*\nX393701Y787402D02*\nD03*\n"
    )
    d = parse_render(str(p))
    assert len(d.flashes) == 2
    assert d.flashes[0].kind == "circle"
    assert d.flashes[0].cx == pytest.approx(0.0)
    assert d.flashes[1].kind == "rect"
    assert d.flashes[1].w == pytest.approx(2.54)
    assert d.flashes[1].cx == pytest.approx(10.0)
    assert d.flashes[1].cy == pytest.approx(20.0)


def test_bare_d02_d01_no_geometry(tmp_path):
    p = tmp_path / "f.gtp"
    p.write_text(
        "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
        "D10*\nX0Y0D02*\nX100000D01*\nD02*\nD01*\n"
    )
    d = parse_render(str(p))
    assert len(d.flashes) == 0
    # only the explicit draw segment is kept
    assert len(d.lines) == 1

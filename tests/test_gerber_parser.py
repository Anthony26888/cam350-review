import pytest

from services.gerber.gerber_parser import parse_segments, parse_flashes


def test_parse_segments_square_mil(tmp_path):
    path = tmp_path / "outline.gko"
    path.write_text(
        "%FSLAX43Y43*%\n"
        "%MOIN*%\n"
        "X0Y0D02*\n"
        "X1000Y0D01*\n"
        "X1000Y1000D01*\n"
        "X0Y1000D01*\n"
        "X0Y0D01*\n",
        encoding="utf-8",
    )
    segs = parse_segments(str(path))
    assert len(segs) == 4
    mm = 25.4
    assert segs[0] == pytest.approx((0.0, 0.0, mm, 0.0))
    assert segs[1] == pytest.approx((mm, 0.0, mm, mm))
    assert segs[2] == pytest.approx((mm, mm, 0.0, mm))
    assert segs[3] == pytest.approx((0.0, mm, 0.0, 0.0))


def test_parse_segments_partial_coords(tmp_path):
    path = tmp_path / "seg.gko"
    path.write_text(
        "%FSLAX43Y43*%\n"
        "%MOIN*%\n"
        "X1000Y0D02*\n"
        "Y1000D01*\n",
        encoding="utf-8",
    )
    segs = parse_segments(str(path))
    assert len(segs) == 1
    assert segs[0] == pytest.approx((25.4, 0.0, 25.4, 25.4))


def test_parse_segments_mm_units(tmp_path):
    path = tmp_path / "seg.gko"
    path.write_text(
        "%FSLAX44Y44*%\n"
        "%MOMM*%\n"
        "X0Y0D02*\n"
        "X100000Y0D01*\n"
        "X100000Y100000D01*\n",
        encoding="utf-8",
    )
    segs = parse_segments(str(path))
    assert len(segs) == 2
    assert segs[0] == pytest.approx((0.0, 0.0, 10.0, 0.0))
    assert segs[1] == pytest.approx((10.0, 0.0, 10.0, 10.0))


def test_parse_segments_move_does_not_draw(tmp_path):
    path = tmp_path / "seg.gko"
    path.write_text(
        "%FSLAX43Y43*%\n"
        "%MOIN*%\n"
        "X0Y0D02*\n"
        "X500Y0D02*\n"
        "X500Y500D01*\n",
        encoding="utf-8",
    )
    segs = parse_segments(str(path))
    assert len(segs) == 1
    assert segs[0] == pytest.approx((12.7, 0.0, 12.7, 12.7))


def test_parse_segments_fsta_trailing_suppression(tmp_path):
    path = tmp_path / "outline.gko"
    path.write_text(
        "%FSTAX24Y24*%\n"
        "%MOIN*%\n"
        "X104686Y1543D02*\n"
        "X104686Y0643D01*\n"
        "X16495D01*\n",
        encoding="utf-8",
    )
    segs = parse_segments(str(path))
    assert len(segs) == 2
    mm = 25.4
    assert segs[0] == pytest.approx((10.4686 * mm, 15.43 * mm, 10.4686 * mm, 6.43 * mm))
    assert segs[1] == pytest.approx((10.4686 * mm, 6.43 * mm, 16.495 * mm, 6.43 * mm))


def test_parse_segments_arc_with_ij(tmp_path):
    path = tmp_path / "outline.gko"
    path.write_text(
        "%FSLAX44Y44*%\n"
        "%MOIN*%\n"
        "X0Y0D02*\n"
        "X1800000Y50000D01*\n"
        "X1800000Y50000I0J50000D01*\n",
        encoding="utf-8",
    )
    segs = parse_segments(str(path))
    assert len(segs) == 2
    assert segs[0] == pytest.approx((0.0, 0.0, 4572.0, 127.0))
    assert segs[1] == pytest.approx((4572.0, 127.0, 4572.0, 127.0))


def test_parse_gerber_points_arc_with_ij(tmp_path):
    path = tmp_path / "outline.gko"
    path.write_text(
        "%FSLAX44Y44*%\n"
        "%MOIN*%\n"
        "X0Y0D02*\n"
        "X1800000Y50000D01*\n"
        "X1800000Y50000I0J50000D01*\n",
        encoding="utf-8",
    )
    from services.gerber.gerber_parser import parse_gerber_points

    pts = parse_gerber_points(str(path), codes=("1", "2"))
    assert len(pts) == 3
    assert pts[1].x_mm == pytest.approx(4572.0)
    assert pts[1].y_mm == pytest.approx(127.0)
    assert pts[2].x_mm == pytest.approx(4572.0)
    assert pts[2].y_mm == pytest.approx(127.0)


def test_parse_flashes_fsta_trailing_suppression(tmp_path):
    path = tmp_path / "paste.gtp"
    path.write_text(
        "%FSTAX24Y24*%\n"
        "%MOIN*%\n"
        "%ADD11C,0.0118*%\n"
        "D11*\n"
        "X112496Y11605D03*\n"
        "X16495Y0643D03*\n",
        encoding="utf-8",
    )
    pts = parse_flashes(str(path))
    assert len(pts) == 2
    mm = 25.4
    assert pts[0].x_mm == pytest.approx(11.2496 * mm)
    assert pts[0].y_mm == pytest.approx(11.605 * mm)
    assert pts[1].x_mm == pytest.approx(16.495 * mm)
    assert pts[1].y_mm == pytest.approx(6.43 * mm)

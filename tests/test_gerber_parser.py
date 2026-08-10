import pytest

from services.gerber.gerber_parser import parse_segments


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

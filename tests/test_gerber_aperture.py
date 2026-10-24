"""The D code of the shape under the pointer, and the X2 attributes."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.gerber.aperture_picker import ApertureIndex  # noqa: E402
from services.gerber.gerber_render import (  # noqa: E402
    ApertureInfo, FlashShape, LineShape, RenderData,
)
from services.gerber.spec import parse_file  # noqa: E402
from services.gerber.spec.adapter import to_render_data  # noqa: E402


def _write(tmp_path, text, name="sample.gbr"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestX2Attributes:
    def test_a_file_attribute_belongs_to_the_file(self, tmp_path):
        path = _write(tmp_path,
                      "%FSLAX44Y44*%\n%MOIN*%\n"
                      "%TF.FileFunction,Copper,L1,Top*%\n"
                      "%ADD10C,0.2000*%\n"
                      "G54D10*\nX010000Y020000D03*\n")
        image = parse_file(path)
        assert image.attributes["FileFunction"] == "Copper,L1,Top"

    def test_an_aperture_attribute_belongs_to_the_aperture(self, tmp_path):
        path = _write(tmp_path,
                      "%FSLAX44Y44*%\n%MOIN*%\n"
                      "%TA.AperFunction,Conductor*%\n"
                      "%ADD10C,0.2000*%\n"
                      "G54D10*\nX010000Y020000D03*\n")
        image = parse_file(path)
        assert image.apertures[10].attributes["AperFunction"] == "Conductor"

    def test_an_object_attribute_belongs_to_the_next_object(self, tmp_path):
        path = _write(tmp_path,
                      "%FSLAX44Y44*%\n%MOIN*%\n"
                      "%ADD10C,0.2000*%\n"
                      "%TO.N,Net1*%\n"
                      "G54D10*\nX010000Y020000D03*\n"
                      "%TO.N,Net2*%\n"
                      "X020000Y030000D03*\n")
        image = parse_file(path)
        assert len(image.items) == 2
        assert image.items[0].attributes["N"] == "Net1"
        assert image.items[1].attributes["N"] == "Net2"

    def test_the_aperture_table_reaches_the_render_model(self, tmp_path):
        path = _write(tmp_path,
                      "%FSLAX44Y44*%\n%MOIN*%\n"
                      "%TA.AperFunction,Conductor*%\n"
                      "%ADD10C,0.2000*%\n"
                      "G54D10*\nX010000Y020000D03*\n")
        data = to_render_data(parse_file(path))
        assert 10 in data.apertures
        info = data.apertures[10]
        assert info.kind == "circle"
        assert info.params == (0.2,)
        assert info.attributes["AperFunction"] == "Conductor"
        assert info.describe() == "D10 C,0.2"

    def test_the_d_code_reaches_the_shapes(self, tmp_path):
        path = _write(tmp_path,
                      "%FSLAX44Y44*%\n%MOIN*%\n"
                      "%ADD10C,0.2000*%\n"
                      "%ADD11C,0.3000*%\n"
                      "G54D10*\nX010000Y020000D03*\n"
                      "G54D11*\nX020000Y030000D03*\n"
                      "G54D10*\nX030000Y040000D01*\n")
        data = to_render_data(parse_file(path))
        assert [f.dcode for f in data.flashes] == [10, 11]
        assert [ln.dcode for ln in data.lines] == [10]


class TestApertureIndex:
    def test_a_flash_under_the_point_is_found(self):
        data = RenderData(
            flashes=[FlashShape(cx=1.0, cy=2.0, kind="circle", w=0.2, h=0.2,
                                dcode=10)],
            apertures={10: ApertureInfo(10, "circle", (0.2,))},
        )
        index = ApertureIndex(data)
        picked = index.pick(1.0, 2.0)
        assert picked is not None
        assert picked.dcode == 10
        assert picked.kind == "flash"

    def test_a_point_far_away_finds_nothing(self):
        data = RenderData(
            flashes=[FlashShape(cx=1.0, cy=2.0, kind="circle", w=0.2, h=0.2)],
        )
        index = ApertureIndex(data)
        assert index.pick(40.0, 40.0) is None

    def test_a_stroke_under_the_point_is_found(self):
        data = RenderData(
            lines=[LineShape(x1=0.0, y1=0.0, x2=10.0, y2=0.0, width=0.2, dcode=7)],
        )
        index = ApertureIndex(data)
        picked = index.pick(5.0, 0.05)
        assert picked is not None
        assert picked.dcode == 7
        assert picked.kind == "stroke"

    def test_the_place_of_the_pointer_is_mapped_back_to_the_file(self):
        data = RenderData()
        index = ApertureIndex(data, mirror=False, angle=90.0, off_x=1.0, off_y=2.0)
        # A rotation of 90 degrees turns (x, y) into (-y, x); the inverse
        # turns it back.
        gx, gy = index.to_file(-3.0, 4.0)
        assert gx == pytest.approx(2.0, abs=1e-6)
        assert gy == pytest.approx(4.0, abs=1e-6)

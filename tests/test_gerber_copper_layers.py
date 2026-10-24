"""The layers of a copper file: the polygons, the order and the role."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.gerber.gerber_render import (  # noqa: E402
    FlashShape, LineShape, RenderData,
)
from services.gerber.layer_scan import (  # noqa: E402
    ROLE_COPPER, ROLE_SILK, role_from_extension, role_from_name,
)
from services.gerber.render.layer import (  # noqa: E402
    LayerItem, build_layer_paths,
)

#: A file with a region (G36) that does not start at the origin.
REGION = (
    "%FSLAX44Y44*%\n%MOMM*%\n"
    "%ADD10C,0.2*%\n"
    "G36*\n"
    "X010000Y020000D02*\n"
    "X050000Y020000D01*\n"
    "X050000Y060000D01*\n"
    "X010000Y060000D01*\n"
    "X010000Y020000D01*\n"
    "G37*\n"
    "M02*\n"
)


def _bbox_of(paths):
    box = paths.bounds()
    return (box.left(), box.top(), box.right(), box.bottom())


class TestPolygons:
    def test_a_region_is_drawn_where_the_file_says(self):
        # The region of the file lies between 1 and 5 mm, and between 2
        # and 6 mm.  It used to be moved by the place of its first point.
        from services.gerber.gerber_render_lib import load_layer

        import tempfile

        path = os.path.join(tempfile.gettempdir(), "region_test.gbr")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(REGION)
        data, _ = load_layer(path)
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        left, top, right, bottom = _bbox_of(paths)
        assert left == pytest.approx(1.0, abs=0.01)
        assert right == pytest.approx(5.0, abs=0.01)
        # The scene turns the y upside down.
        assert bottom == pytest.approx(-2.0, abs=0.01)
        assert top == pytest.approx(-6.0, abs=0.01)

    def test_a_polygon_with_a_place_is_drawn_in_its_place(self):
        # A polygon that is given relative to the place of the flash.
        data = RenderData()
        data.flashes.append(FlashShape(
            cx=100.0, cy=200.0, kind="polygon", w=0.0, h=0.0,
            pts=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
            pts_local=True, seq=0))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        left, top, right, bottom = _bbox_of(paths)
        assert left == pytest.approx(100.0, abs=0.01)
        assert right == pytest.approx(110.0, abs=0.01)
        assert bottom == pytest.approx(-200.0, abs=0.01)


class TestOrder:
    def test_a_negative_object_removes_only_what_was_drawn_before(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="rect", w=10.0, h=10.0,
                                       seq=0))
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="circle", w=2.0, h=2.0,
                                       negative=True, seq=1))
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="circle", w=1.0, h=1.0,
                                       seq=2))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        # The parts are in the order of the file.
        assert [op.clear for op in paths.ops] == [False, True, False]

    def test_a_negative_stroke_comes_after_the_artwork_it_removes(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=0.0, cy=0.0, kind="rect", w=10.0, h=10.0,
                                       seq=0))
        data.lines.append(LineShape(x1=-6.0, y1=0.0, x2=6.0, y2=0.0, width=2.0,
                                    negative=True, seq=1))
        paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
        assert paths.has_clear is True
        kinds = [(op.fill, op.clear) for op in paths.ops]
        assert kinds == [(True, False), (False, True)]


class TestRoles:
    def test_the_copper_layers_are_not_silkscreen(self):
        assert role_from_extension("board.gtl") == (ROLE_COPPER, "top")
        assert role_from_extension("board.gbl") == (ROLE_COPPER, "bottom")
        assert role_from_extension("board.gto") == (ROLE_SILK, "top")

    def test_the_names_of_a_job_are_used(self):
        assert role_from_name("gtl") == (ROLE_COPPER, "top")
        assert role_from_name("gbl") == (ROLE_COPPER, "bottom")
        assert role_from_name("gto") == (ROLE_SILK, "top")

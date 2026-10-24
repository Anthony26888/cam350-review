"""The strokes of a layer in flat arrays and as objects."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.gerber.gerber_render import (  # noqa: E402
    ArcShape, FlashShape, LineShape, RenderData,
)
from services.gerber.render.layer import build_layer_paths  # noqa: E402


def _layer() -> RenderData:
    data = RenderData()
    data.lines = [
        LineShape(0.0, 0.0, 10.0, 0.0, 0.2, False, 10),
        LineShape(10.0, 0.0, 10.0, 5.0, 0.2, False, 10),
        LineShape(0.0, 0.0, 4.0, 3.0, 0.4, False, 11),
        LineShape(4.0, 3.0, 8.0, 3.0, 0.4, True, 11),
    ]
    data.arcs = [
        ArcShape(0.0, 0.0, 4.0, 0.0, 2.0, 0.0, True, 0.3, False, 12),
    ]
    data.flashes = [
        FlashShape(cx=2.0, cy=2.0, kind="circle", w=1.0, h=1.0, dcode=13),
    ]
    data.runs = [(False, 3, 1, 1), (True, 1, 0, 0)]
    return data


class TestFlatStrokes:
    def test_the_objects_come_from_the_arrays(self):
        data = _layer()
        import numpy as np

        array = np.array([
            (0.0, 0.0, 10.0, 0.0, 0.2, 0.0, 10.0),
            (10.0, 0.0, 10.0, 5.0, 0.2, 0.0, 10.0),
            (0.0, 0.0, 4.0, 3.0, 0.4, 0.0, 11.0),
            (4.0, 3.0, 8.0, 3.0, 0.4, 1.0, 11.0),
        ], dtype=np.float64)
        data.set_stroke_array(array)
        lines = data.lines
        assert len(lines) == 4
        assert lines[0].x2 == pytest.approx(10.0)
        assert lines[3].negative is True
        assert lines[3].dcode == 11

    def test_the_number_of_strokes_does_not_need_the_objects(self):
        data = _layer()
        import numpy as np

        data.set_stroke_array(np.zeros((7, 7), dtype=np.float64))
        assert data.stroke_count == 7

    def test_the_area_comes_from_the_arrays(self):
        data = RenderData()
        import numpy as np

        data.set_stroke_array(np.array([
            (1.0, 2.0, 3.0, 4.0, 0.2, 0.0, 10.0),
            (-1.0, 0.0, 0.0, 8.0, 0.2, 0.0, 10.0),
        ], dtype=np.float64))
        assert data.bbox() == pytest.approx((-1.0, 0.0, 3.0, 8.0))


class TestTheSamePaths:
    def test_the_arrays_give_the_same_paths_as_the_objects(self):
        from services.gerber.spec.adapter import _stroke_array_of

        data = _layer()
        as_objects = build_layer_paths(data, 0.0, False, 0.0, 0.0, False,
                                       (0.0, 0.0))
        array = _stroke_array_of(data.lines)
        other = _layer()
        other.set_stroke_array(array)
        as_arrays = build_layer_paths(other, 0.0, False, 0.0, 0.0, False,
                                      (0.0, 0.0))

        assert len(as_objects.ops) == len(as_arrays.ops)
        for one, other_op in zip(as_objects.ops, as_arrays.ops):
            assert one.width == pytest.approx(other_op.width)
            assert one.clear == other_op.clear
            assert one.fill == other_op.fill
            assert one.tile == other_op.tile
            assert one.path.elementCount() == other_op.path.elementCount()

"""Tests for the alignment of a drill file to the board."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from services.gerber.drill_aligner import (
    align_drill,
    points_bbox,
    shift_render_data,
)
from services.gerber.gerber_render import FlashShape, LineShape, RenderData


class TestAlignDrill:
    def test_a_known_offset_is_found(self):
        pads = [(10.0, 10.0), (20.0, 10.0), (30.0, 10.0), (10.0, 20.0)]
        holes = [(x - 5.0, y - 3.0) for x, y in pads]
        bbox = points_bbox(pads)
        result = align_drill(holes, pads, board_bbox=bbox, distance_threshold=0.3)
        assert result.applied is True
        assert result.offset_x == pytest.approx(5.0, abs=0.05)
        assert result.offset_y == pytest.approx(3.0, abs=0.05)

    def test_the_outline_is_used_when_there_is_no_paste(self):
        holes = [(1.0, 1.0), (11.0, 1.0)]
        bbox = (0.0, 0.0, 20.0, 20.0)
        result = align_drill(holes, [], board_bbox=bbox)
        assert result.method == "outline"
        # The middle of the drill (6, 1) moves onto the middle of the
        # board (10, 10).
        assert result.offset_x == pytest.approx(4.0, abs=0.05)
        assert result.offset_y == pytest.approx(9.0, abs=0.05)

    def test_nothing_to_align(self):
        result = align_drill([], [], board_bbox=(0.0, 0.0, 10.0, 10.0))
        assert result.applied is False
        assert result.offset_x == 0.0 and result.offset_y == 0.0

    def test_the_summary_mentions_the_offset(self):
        pads = [(0.0, 0.0), (5.0, 0.0)]
        holes = [(-2.0, -1.0), (3.0, -1.0)]
        result = align_drill(holes, pads, board_bbox=points_bbox(pads),
                             distance_threshold=0.3)
        assert "offset" in result.summary()


class TestShiftRenderData:
    def test_flashed_shapes_are_moved(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=1.0, cy=2.0, kind="circle", w=1.0, h=1.0))
        shift_render_data(data, 10.0, -5.0)
        assert data.flashes[0].cx == pytest.approx(11.0)
        assert data.flashes[0].cy == pytest.approx(-3.0)

    def test_lines_and_arcs_are_moved(self):
        data = RenderData()
        data.lines.append(LineShape(x1=0.0, y1=0.0, x2=1.0, y2=1.0, width=0.1))
        shift_render_data(data, 2.0, 3.0)
        assert data.lines[0].x1 == pytest.approx(2.0)
        assert data.lines[0].y2 == pytest.approx(4.0)

    def test_a_zero_offset_changes_nothing(self):
        data = RenderData()
        data.flashes.append(FlashShape(cx=1.0, cy=2.0, kind="circle", w=1.0, h=1.0))
        shift_render_data(data, 0.0, 0.0)
        assert data.flashes[0].cx == pytest.approx(1.0)

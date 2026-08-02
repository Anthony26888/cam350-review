import pytest

from services.gerber.offset_applier import (
    ComponentTransform,
    rotate_point,
    step4_apply_offset,
    step6_rotate,
    step7_mirror_bottom,
    round_coord,
)


def test_round_coord():
    assert round_coord(1.2345678) == 1.2346
    assert round_coord(2.0) == 2.0


def test_rotate_point_90():
    x, y = rotate_point(10, 0, 90)
    assert abs(x - 0.0) < 1e-9
    assert abs(y - 10.0) < 1e-9


def test_step4_apply_offset_no_rotation():
    comp = ComponentTransform("C1", "Top", 10, 20, 0)
    step4_apply_offset(comp, 5, -5, 0)
    assert comp.new_x == 15
    assert comp.new_y == 15
    assert comp.new_rotation == 0


def test_step6_rotate_top_90():
    comp = ComponentTransform("C1", "Top", 10, 20, 0)
    step4_apply_offset(comp, 0, 0, 0)
    step6_rotate(comp, board_w=100, board_h=50, angle_deg=90)
    assert comp.new_x == 50 - 20
    assert comp.new_y == 10
    assert comp.new_rotation == 90


def test_step6_rotate_bottom_ignored_with_unknown_layer():
    comp = ComponentTransform("C1", "mid", 10, 20, 0)
    step4_apply_offset(comp, 0, 0, 0)
    step6_rotate(comp, board_w=100, board_h=50, angle_deg=90)
    assert comp.new_x == 10


def test_step7_mirror_bottom_only():
    comp = ComponentTransform("C1", "Bottom", 10, 20, 0)
    step4_apply_offset(comp, 0, 0, 0)
    step7_mirror_bottom(comp, ref_width=100)
    assert comp.new_x == 90

    top_comp = ComponentTransform("C2", "Top", 10, 20, 0)
    step4_apply_offset(top_comp, 0, 0, 0)
    step7_mirror_bottom(top_comp, ref_width=100)
    assert top_comp.new_x == 10

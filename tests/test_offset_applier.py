import pytest

from services.gerber.offset_applier import (
    ComponentTransform,
    apply_all_transforms,
    rotate_point,
    step4_apply_offset,
    step6_rotate,
    step7_mirror_bottom,
    round_coord,
    GKO_PRIORITY_TOL,
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


def test_step6_rotate_bottom_90_swap():
    comp = ComponentTransform("C1", "Bottom", 10, 20, 30)
    step4_apply_offset(comp, 0, 0, 0)
    step6_rotate(comp, board_w=100, board_h=50, angle_deg=90)
    assert comp.new_x == 20
    assert comp.new_y == 10
    assert comp.new_rotation == (30 - 90) % 360


def test_step6_rotate_top_90_formula():
    comp = ComponentTransform("C1", "Top", 10, 20, 30)
    step4_apply_offset(comp, 0, 0, 0)
    step6_rotate(comp, board_w=100, board_h=50, angle_deg=90)
    assert comp.new_x == 50 - 20
    assert comp.new_y == 10
    assert comp.new_rotation == 120


class _Inst:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.origin = (0.0, 0.0)
        self.k = 0


class _Result:
    offset_x = 0.0
    offset_y = 0.0
    rotation_angle = 0.0
    n_matched = 0
    n_total = 0
    median_residual = -1.0
    gko_priority = False


class _Panel:
    def __init__(self, w, h):
        self.panel_w = w
        self.panel_h = h
        self.panel_origin = (0.0, 0.0)
        self.kind = "single"
        self.is_panel = False
        self.instances = [_Inst(0.0, 0.0)]


def test_apply_all_transforms_bottom_90_ticked_swaps_xy():
    panel = _Panel(100.0, 50.0)
    panel.instances = [_Inst(100.0, 50.0)]
    comp = ComponentTransform("C1", "Bottom", 10, 20, 30)
    apply_all_transforms(
        [comp], panel, {0: _Result()},
        origin_mode="panel", rotation_angle=90,
        rot_layers={"top": True, "bottom": True},
    )
    assert comp.new_x == 20
    assert comp.new_y == 10


def test_apply_all_transforms_bottom_90_unticked_keeps_mirror():
    panel = _Panel(100.0, 50.0)
    panel.instances = [_Inst(100.0, 50.0)]
    comp = ComponentTransform("C1", "Bottom", 10, 20, 30)
    apply_all_transforms(
        [comp], panel, {0: _Result()},
        origin_mode="panel", rotation_angle=90,
        rot_layers={"top": True, "bottom": False},
    )
    assert comp.new_x == 50 - 10
    assert comp.new_y == 20


def test_apply_all_transforms_rotation_skipped_for_unticked_layer():
    panel = _Panel(100.0, 50.0)
    panel.instances = [_Inst(100.0, 50.0)]
    comp = ComponentTransform("C1", "Top", 10, 20, 30)
    apply_all_transforms(
        [comp], panel, {0: _Result()},
        origin_mode="panel", rotation_angle=90,
        rot_layers={"top": False, "bottom": False},
    )
    # no 90° rotation, offset is identity -> coords unchanged for top
    assert comp.new_x == 10
    assert comp.new_y == 20
    assert comp.new_rotation == 30


def test_gko_priority_keeps_original_coords_when_gtp_conflicts():
    panel = _Panel(100.0, 50.0)
    panel.panel_origin = (265.9024, 163.3220)
    panel.instances = [_Inst(100.0, 50.0)]
    panel.instances[0].origin = (265.9024, 163.3220)
    res = _Result()
    res.offset_x = 264.7572
    res.offset_y = 165.8620
    res.n_matched = 135
    res.n_total = 484
    res.median_residual = 0.3813606151728656
    comp = ComponentTransform("C1", "Top", 42.8357, 201.549, 0)
    apply_all_transforms([comp], panel, {0: res}, origin_mode="panel", rotation_angle=0)
    # offset lệch gốc GKO quá ngưỡng -> ưu tiên panel_origin -> new == orig
    assert res.gko_priority is True
    assert comp.new_x == pytest.approx(42.8357, abs=1e-4)
    assert comp.new_y == pytest.approx(201.549, abs=1e-4)


def test_gko_priority_ignored_when_pad_match_reliable():
    panel = _Panel(100.0, 50.0)
    panel.panel_origin = (265.9024, 163.3220)
    panel.instances = [_Inst(100.0, 50.0)]
    panel.instances[0].origin = (265.9024, 163.3220)
    res = _Result()
    res.offset_x = 264.7572
    res.offset_y = 165.8620
    res.n_matched = 480
    res.n_total = 484
    res.median_residual = 0.02
    comp = ComponentTransform("C1", "Top", 42.8357, 201.549, 0)
    apply_all_transforms([comp], panel, {0: res}, origin_mode="panel", rotation_angle=0)
    # khớp pad đáng tin cậy -> giữ offset ICP (không ghi đè)
    assert res.gko_priority is False
    assert comp.new_x == pytest.approx(42.8357 + 264.7572 - 265.9024, abs=1e-4)
    assert comp.new_y == pytest.approx(201.549 + 165.8620 - 163.3220, abs=1e-4)


def test_gko_priority_not_applied_when_offset_matches_gko():
    panel = _Panel(100.0, 50.0)
    panel.panel_origin = (265.9024, 163.3220)
    panel.instances = [_Inst(100.0, 50.0)]
    panel.instances[0].origin = (265.9024, 163.3220)
    res = _Result()
    res.offset_x = 265.9024 + 0.001
    res.offset_y = 163.3220 - 0.001
    res.n_matched = 10
    res.n_total = 484
    res.median_residual = 0.5
    comp = ComponentTransform("C1", "Top", 42.8357, 201.549, 0)
    apply_all_transforms([comp], panel, {0: res}, origin_mode="panel", rotation_angle=0)
    # lệch < GKO_PRIORITY_TOL -> không kích hoạt fallback
    assert res.gko_priority is False
    assert res.offset_x == 265.9024 + 0.001


def test_gko_priority_constant_value():
    assert GKO_PRIORITY_TOL == 0.01

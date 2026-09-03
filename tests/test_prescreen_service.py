import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from models.review import ReviewRecord
from services.prescreen import (
    KIND_DUP,
    KIND_OUT,
    KIND_PAD,
    KIND_ROT,
    PrescreenConfig,
    PrescreenIssue,
    compute_pad_stats,
    dismiss_key_for,
    run_prescreen,
    summarize,
)
from services.session_service import SessionService


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _rec(des, mpn="MPN", layer="Top", x=0.0, y=0.0, rot=0.0):
    return ReviewRecord(designator=des, mpn=mpn, layer=layer,
                        old_x=x, old_y=y, old_rotation=rot)


def test_dup_flags_later_record_within_tolerance():
    recs = [_rec("A", x=10.0, y=10.0), _rec("B", x=10.0, y=10.03)]
    issues = run_prescreen(recs)
    dup = [i for i in issues if i.kind == KIND_DUP]
    assert len(dup) == 1
    assert dup[0].index == 1
    assert dup[0].designator == "B"


def test_dup_respects_tolerance_boundary():
    recs = [_rec("A", x=10.0, y=10.0), _rec("B", x=10.0, y=10.06)]
    issues = run_prescreen(recs)
    assert all(i.kind != KIND_DUP for i in issues)


def test_rot_majority_outlier_flagged_small_group_skipped():
    recs = [
        _rec("U1", mpn="X", rot=0),
        _rec("U2", mpn="X", rot=0),
        _rec("U3", mpn="X", rot=0),
        _rec("U4", mpn="X", rot=180),
        _rec("R9", mpn="Solo", rot=137),  # group size 1 -> skipped
    ]
    issues = run_prescreen(recs)
    rot = [i for i in issues if i.kind == KIND_ROT]
    assert len(rot) == 1
    assert rot[0].index == 3
    assert "180" in rot[0].detail


def test_rot_90_degree_deviation_not_flagged_by_default():
    # Same MPN rotated 90 degrees apart is a legitimate assembly variant
    recs = [
        _rec("C1", mpn="P", rot=0),
        _rec("C2", mpn="P", rot=0),
        _rec("C3", mpn="P", rot=0),
        _rec("C4", mpn="P", rot=90),
    ]
    issues = run_prescreen(recs)
    assert all(i.kind != KIND_ROT for i in issues)
    # Boundary: dev exactly == rot_dev (strict >) is not flagged either
    recs2 = [_rec("D1", mpn="Q", rot=0), _rec("D2", mpn="Q", rot=0),
             _rec("D3", mpn="Q", rot=90)]
    assert all(i.kind != KIND_ROT for i in run_prescreen(recs2))


def test_pad_systemic_flags_once_when_median_exceeds():
    from services.prescreen import PrescreenConfig
    recs = [_rec("A", x=10.0, y=10.0)]
    issues = run_prescreen(recs, paste_top=[(100.0, 100.0)])
    pads = [i for i in issues if i.kind == KIND_PAD]
    assert len(pads) == 1
    assert pads[0].index == -1
    assert pads[0].designator == ""
    assert "median" in pads[0].detail


def test_pad_clean_when_median_within_tolerance():
    recs = [_rec("A", x=100.05, y=100.0)]
    issues = run_prescreen(recs, paste_top=[(100.0, 100.0)])
    assert all(i.kind != KIND_PAD for i in issues)


def test_pad_skipped_when_layer_missing_paste():
    bot = [_rec("B1", layer="Bottom", x=500.0, y=500.0)]
    assert run_prescreen(bot, paste_top=[(100.0, 100.0)]) == []
    st = compute_pad_stats(bot, paste_top=[(100.0, 100.0)])
    assert st["n"] == 0 and st["median_mm"] is None


def test_compute_pad_stats_values():
    recs = [_rec("A", x=0.0, y=0.0), _rec("B", x=4.0, y=0.0)]
    st = compute_pad_stats(recs, paste_top=[(0.0, 0.0), (8.0, 0.0)])
    assert st["n"] == 2
    assert st["median_mm"] == 2.0
    assert abs(st["p95_mm"] - 4.0) < 1e-9


def test_compute_pad_stats_coords_override():
    recs = [_rec("A", x=999.0, y=999.0)]
    st = compute_pad_stats(recs, coords=[(2.0, 0.0)],
                           paste_top=[(0.0, 0.0), (4.0, 0.0)])
    assert st["n"] == 1
    assert abs(st["median_mm"] - 2.0) < 1e-9


def test_out_uses_margin():
    recs = [_rec("J1", x=52.0, y=20.0), _rec("J2", x=50.7, y=20.0)]
    issues = run_prescreen(recs, outline_bbox=(0.0, 0.0, 50.0, 40.0))
    out = [i for i in issues if i.kind == KIND_OUT]
    assert [i.designator for i in out] == ["J1"]


def test_dismissed_keys_filtered():
    recs = [_rec("A", x=10.0, y=10.0), _rec("B", x=10.0, y=10.01)]
    first = run_prescreen(recs)
    keys = {dismiss_key_for(i.kind, recs[i.index]) for i in first if i.kind == KIND_DUP}
    again = run_prescreen(recs, dismissed=frozenset(keys))
    assert all(i.kind != KIND_DUP for i in again)


def test_summarize_counts_per_category():
    recs = [
        _rec("A", x=10.0, y=10.0),
        _rec("B", x=10.0, y=10.01),
        _rec("J1", x=52.0, y=20.0),
    ]
    issues = run_prescreen(recs, outline_bbox=(0.0, 0.0, 50.0, 40.0))
    counts = summarize(issues)
    assert counts[KIND_DUP] == 1
    assert counts[KIND_OUT] == 1
    assert counts["TOTAL"] == 2


def test_disabled_or_empty_returns_nothing():
    assert run_prescreen([], outline_bbox=(0, 0, 1, 1)) == []
    cfg = PrescreenConfig(enabled=False)
    assert run_prescreen([_rec("A")], cfg=cfg) == []


def test_session_roundtrip_prescreen_dismissed(tmp_path):
    path = str(tmp_path / "s.cam350review")
    SessionService.save(path, [_rec("A")], prescreen_dismissed=[
        f"{KIND_ROT}:C1:1.000:2.000",
    ])
    data = SessionService.load(path)
    assert data.prescreen_dismissed == [f"{KIND_ROT}:C1:1.000:2.000"]


def test_coords_override_fixes_panel_shift_false_out():
    # Raw pickplace around (100, 50); gerber outline sits near origin.
    # After panel-mode alignment the record frame is shifted by -panel_origin,
    # so checking raw records against the raw outline flags everything.
    recs = [_rec("A", x=100.0, y=50.0), _rec("B", x=101.0, y=51.5)]
    bbox = (0.0, 0.0, 5.0, 5.0)
    assert all(i.kind == KIND_OUT for i in run_prescreen(recs, outline_bbox=bbox))
    coords = [(0.05, 0.02), (1.03, 1.48)]  # orig + align offset (gerber frame)
    issues = run_prescreen(recs, outline_bbox=bbox, coords=coords)
    assert all(i.kind != KIND_OUT for i in issues)


def test_coords_override_pad_against_raw_paste():
    from services.prescreen import PrescreenConfig
    recs = [_rec("C1", x=200.0, y=150.0)]
    coords = [(0.40, 0.00)]
    cfg = PrescreenConfig(pad_median_tol=0.3)
    pad = [i for i in run_prescreen(recs, paste_top=[(0.0, 0.0)],
                                    coords=coords, cfg=cfg)
           if i.kind == KIND_PAD]
    assert len(pad) == 1 and pad[0].index == -1
    ok = run_prescreen(recs, paste_top=[(0.4, 0.0)], coords=coords, cfg=cfg)
    assert all(i.kind != KIND_PAD for i in ok)


def test_rots_override_keeps_majority_detection():
    recs = [
        _rec("U1", mpn="X", rot=0),
        _rec("U2", mpn="X", rot=0),
        _rec("U3", mpn="X", rot=0),
        _rec("U4", mpn="X", rot=180),
    ]
    rots = [(r.old_rotation + 90) % 360 for r in recs]  # uniform board rotation
    issues = run_prescreen(recs, rots=rots)
    rot = [i for i in issues if i.kind == KIND_ROT]
    assert len(rot) == 1
    assert rot[0].index == 3


def _fake_panel(origin=(0.0, 0.0), w=50.0, h=40.0):
    import types
    return types.SimpleNamespace(
        panel_origin=origin, panel_w=w, panel_h=h,
        is_panel=False, count=1,
        instances=[types.SimpleNamespace(origin=origin, w=w, h=h, k=0)],
    )


def test_transform_points_panel_translate():
    from services.prescreen import transform_points_through_align
    panel = _fake_panel(origin=(10.0, 10.0))
    out = transform_points_through_align(
        [(25.0, 22.0)], "top", panel_info=panel,
        origin_mode="panel", rotation_angle=0,
        rot_layers={"top": True, "bottom": False},
    )
    assert out == [(15.0, 12.0)]


def test_transform_points_rotate90_top_layer():
    from services.prescreen import transform_points_through_align
    panel = _fake_panel(w=50.0, h=40.0)
    # step6 top 90°: x' = board_h - y ; y' = x   (after step4b with origin 0)
    out = transform_points_through_align(
        [(5.0, 2.0)], "top", panel_info=panel,
        origin_mode="panel", rotation_angle=90,
        rot_layers={"top": True, "bottom": False},
    )
    assert out == [(40.0 - 2.0, 5.0)]


def test_transform_points_mirror_bottom():
    from services.prescreen import transform_points_through_align
    panel = _fake_panel(w=50.0, h=40.0)
    out = transform_points_through_align(
        [(5.0, 2.0)], "bottom", panel_info=panel,
        origin_mode="panel", rotation_angle=0,
        rot_layers={"top": True, "bottom": False},
    )
    assert out == [(50.0 - 5.0, 2.0)]


def test_transform_points_without_panel_returns_input():
    from services.prescreen import transform_points_through_align
    pts = [(1.0, 2.0), (3.5, -4.0)]
    assert transform_points_through_align(pts, "top", panel_info=None) == pts


def test_config_legacy_rot_dev_45_migrates_to_90():
    from models.config import PrescreenConfig
    cfg = PrescreenConfig.from_dict({"rot_dev": 45.0})
    assert cfg.rot_dev == 90.0
    fresh = PrescreenConfig.from_dict({})
    assert fresh.rot_dev == 90.0
    custom = PrescreenConfig.from_dict({"rot_dev": 30.0})
    assert custom.rot_dev == 30.0

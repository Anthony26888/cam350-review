import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from services.gerber.origin_aligner import AlignResult
from services.gerber.panel_detector import BoardInstance, PanelInfo
from services.prescreen import (
    KIND_ROT,
    PrescreenIssue,
    pack_prescreen_ctx,
    unpack_prescreen_ctx,
)
from services.session_service import SessionService


def _live_ctx():
    panel = PanelInfo(
        kind="B",
        instances=[
            BoardInstance(origin=(0.0, 0.0), w=50.0, h=40.0, sub_name="S1", k=0),
            BoardInstance(origin=(0.0, 45.0), w=50.0, h=40.0, sub_name="S2", k=1),
        ],
        panel_origin=(2.5, 3.5),
        panel_w=52.0,
        panel_h=88.0,
        sub_block_names=["S1", "S2"],
        dx_mm=5.0,
        dy_mm=5.0,
        nx=1,
        ny=2,
    )
    return {
        "align_results": {
            0: {"top": AlignResult(offset_x=264.7, offset_y=165.8, rotation_angle=0.0,
                                   n_matched=100, n_total=484,
                                   median_residual=0.31, gko_priority=True)},
            1: {"bottom": AlignResult(offset_x=10.0, offset_y=20.0)},
        },
        "panel_info": panel,
        "origin_mode": "panel",
        "rotation_angle": 90,
        "rot_layers": {"top": True, "bottom": False},
    }


def test_align_result_roundtrip():
    res = AlignResult(offset_x=1.5, offset_y=-2.5, rotation_angle=90.0,
                      n_matched=3, n_total=4, median_residual=0.25,
                      gko_priority=True)
    assert AlignResult.from_dict(res.to_dict()).__dict__ == res.__dict__


def test_board_instance_roundtrip():
    inst = BoardInstance(origin=(1.25, 2.5), w=30.0, h=20.0, sub_name="X", k=2)
    back = BoardInstance.from_dict(inst.to_dict())
    assert back.origin == inst.origin and back.w == inst.w
    assert back.h == inst.h and back.k == inst.k and back.sub_name == "X"


def test_panel_info_roundtrip():
    ctx = _live_ctx()
    panel = ctx["panel_info"]
    back = PanelInfo.from_dict(panel.to_dict())
    assert back.kind == panel.kind
    assert back.count == panel.count == 2
    assert back.is_panel is True
    assert back.panel_origin == panel.panel_origin
    assert back.panel_w == panel.panel_w and back.panel_h == panel.panel_h
    assert [i.k for i in back.instances] == [0, 1]
    assert back.instances[1].sub_name == "S2"


def test_pack_produces_json_safe_dict():
    packed = pack_prescreen_ctx(_live_ctx())
    assert packed is not None
    json.dumps(packed)  # must not raise


def test_pack_unpack_roundtrip_restores_live_objects():
    ctx = _live_ctx()
    back = unpack_prescreen_ctx(pack_prescreen_ctx(ctx))
    assert back["origin_mode"] == "panel"
    assert back["rotation_angle"] == 90
    assert back["rot_layers"] == {"top": True, "bottom": False}
    # int instance keys restored
    assert set(back["align_results"].keys()) == {0, 1}
    top = back["align_results"][0]["top"]
    assert isinstance(top, AlignResult)
    assert top.offset_x == pytest.approx(264.7)
    assert top.gko_priority is True
    panel = back["panel_info"]
    assert isinstance(panel, PanelInfo)
    assert panel.count == 2 and panel.instances[0].k == 0
    # usable by the transform pipeline attributes
    assert panel.instances[1].origin[1] == pytest.approx(45.0)


def test_pack_unpack_none_and_empty():
    assert pack_prescreen_ctx(None) is None
    assert pack_prescreen_ctx({}) is None
    assert unpack_prescreen_ctx(None) is None
    assert unpack_prescreen_ctx({}) is None


def test_session_roundtrip_with_prescreen_ctx(tmp_path):
    path = str(tmp_path / "s.cam350review")
    packed = pack_prescreen_ctx(_live_ctx())
    SessionService.save(path, [], prescreen_dismissed=[f"{KIND_ROT}:C1:1.000:2.000"],
                        prescreen_ctx=packed)
    data = SessionService.load(path)
    assert data.prescreen_dismissed == [f"{KIND_ROT}:C1:1.000:2.000"]
    back = unpack_prescreen_ctx(data.prescreen_ctx)
    assert back["rotation_angle"] == 90
    assert back["panel_info"].count == 2


def test_session_old_file_without_ctx_loads(tmp_path):
    path = str(tmp_path / "old.cam350review")
    SessionService.save(path, [])
    data = SessionService.load(path)
    assert data.prescreen_ctx is None

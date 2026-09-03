import os
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from models.pickplace import PickPlaceData
from models.review import ReviewRecord
from services.prescreen import PrescreenIssue, summarize
from ui.origin_align_wizard import OriginAlignWizard


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _wizard(app):
    return OriginAlignWizard(
        PickPlaceData(headers=[], file_path=""),
        records=[],
        apply_callback=lambda *a: None,
        parent=None,
    )


def test_prescreen_step_summary_and_result(app):
    w = _wizard(app)
    assert w._step_index == 0

    w._show_step(5)
    assert "6/7" in w._lbl_title.text()
    assert w._btn_run_prescreen is not None
    assert w.get_prescreen_result() is None

    issues = [
        PrescreenIssue(kind="ROT", index=0, designator="U1", x=1.0, y=2.0),
        PrescreenIssue(kind="ROT", index=1, designator="U2", x=1.5, y=2.5),
        PrescreenIssue(kind="DUP", index=3, designator="R9", x=8.0, y=8.0),
    ]
    w._on_prescreen_finished(issues)
    text = w._prescreen_summary.text()
    assert "ROT : 2" in text
    assert "DUP : 1" in text
    assert "PAD : 0" in text
    assert "OUT : 0" in text
    counts = summarize(issues)
    assert counts["TOTAL"] == 3
    assert w.get_prescreen_result() == issues
    assert w._btn_next.isEnabled()

    # clean run flips to success message
    w._on_prescreen_finished([])
    assert "✅" in w._prescreen_summary.text()


def test_prescreen_legend_lists_all_kinds(app):
    w = _wizard(app)
    w._show_step(5)
    from PySide6.QtWidgets import QLabel
    joined = "\n".join(lb.text() for lb in w.findChildren(QLabel))
    assert "ROT" in joined and "PAD" in joined and "DUP" in joined and "OUT" in joined


def test_prescreen_gerber_points_share_final_record_frame(app):
    """Pickplace offset from gerber origin -> after the SAME align pipeline,
    records and transformed gerber points must land on identical coords."""
    import types

    from services.prescreen import (
        KIND_PAD,
        assign_instance_by_y,
        run_prescreen,
        transform_points_through_align,
    )

    panel_origin = (10.0, 10.0)
    panel_info = types.SimpleNamespace(
        panel_origin=panel_origin, panel_w=50.0, panel_h=40.0,
        is_panel=False, count=1,
        instances=[types.SimpleNamespace(origin=panel_origin, w=50.0, h=40.0, k=0)],
    )
    # alignment solved offset (-10, -10): pickplace(30,30) -> gerber pad(20,20)
    res = types.SimpleNamespace(offset_x=-10.0, offset_y=-10.0,
                                rotation_angle=0.0, n_total=1)
    align_results = {0: {"top": res}}

    rec = ReviewRecord(designator="C1", layer="Top",
                       old_x=30.0, old_y=30.0, old_rotation=0.0)
    rec.new_x, rec.new_y = 20.0 - panel_origin[0], 20.0 - panel_origin[1]  # step4+4b

    pts = transform_points_through_align(
        [(20.0, 20.0)], "top", align_results=align_results,
        panel_info=panel_info, origin_mode="panel",
        rotation_angle=0, rot_layers={"top": True, "bottom": False},
        instance_ks=[assign_instance_by_y(20.0, panel_info)],
    )
    assert pts == [(10.0, 10.0)]
    issues = run_prescreen([rec], paste_top=pts, outline_bbox=(0.0, 0.0, 5.0, 4.0),
                           coords=[(rec.new_x, rec.new_y)], rots=[0.0])
    assert all(i.kind != KIND_PAD for i in issues)


def test_prescreen_worker_run_end_to_end(app, tmp_path):
    from services.prescreen import PrescreenConfig
    from ui.origin_align_wizard import PrescreenWorker

    gko = tmp_path / "o.gko"
    gko.write_text(
        "%MOMM*%\n"
        "%FSLAX44Y44*%\n"
        "X0Y0D02*\n"
        "X50000Y0D01*\n"
        "X50000Y40000D01*\n"
        "X0Y40000D01*\n"
        "X0Y0D01*\n",
        encoding="ascii",
    )
    gtp = tmp_path / "p.gtp"
    gtp.write_text(
        "%MOMM*%\n"
        "%FSLAX44Y44*%\n"
        "X10000Y10000D03*\n"
        "X30000Y30000D03*\n",
        encoding="ascii",
    )

    import types as _t
    panel_origin = (0.0, 0.0)
    panel_info = _t.SimpleNamespace(
        panel_origin=panel_origin, panel_w=50.0, panel_h=40.0,
        is_panel=False, count=1,
        instances=[_t.SimpleNamespace(origin=panel_origin, w=50.0, h=40.0, k=0)],
    )
    ctx = {
        "align_results": {0: {"top": _t.SimpleNamespace(
            offset_x=0.0, offset_y=0.0, rotation_angle=0.0, n_total=2)}},
        "panel_info": panel_info,
        "origin_mode": "panel",
        "rotation_angle": 0,
        "rot_layers": {"top": True, "bottom": False},
    }
    recs = [
        ReviewRecord(designator="C1", layer="Top", old_x=1.0, old_y=1.0),
        ReviewRecord(designator="C2", layer="Top", old_x=6.0, old_y=6.0),  # OUT
    ]
    stats_got = []
    got = []
    w = PrescreenWorker(str(gko), str(gtp), "", recs,
                        PrescreenConfig(), {}, ctx=ctx)
    w.stats_ready.connect(stats_got.append)
    w.finished.connect(got.append)
    w.failed.connect(lambda m: got.append(_t.SimpleNamespace(error=m)))
    w.run()
    issues = got[0]
    kinds_by_des = {}
    for iss in issues:
        kinds_by_des.setdefault(iss.designator, []).append(iss.kind)
    assert "OUT" not in kinds_by_des.get("C1", [])
    assert "PAD" not in kinds_by_des.get("C1", [])
    assert "OUT" in kinds_by_des.get("C2", [])
    # per-component PAD no longer exists; board-level only (index == -1)
    assert all(i.index != 1 for i in issues if i.kind == "PAD")
    pad_issues = [i for i in issues if i.kind == "PAD"]
    if pad_issues:
        assert all(p.index == -1 for p in pad_issues)
    assert stats_got and stats_got[0]["n"] == 2


def test_unreliable_align_layers_and_warning(app):
    import types

    w = _wizard(app)
    assert w._unreliable_align_layers() == set()

    w._prescreen_ctx = {
        "align_results": {
            0: {
                "top": types.SimpleNamespace(gko_priority=True),
                "bottom": types.SimpleNamespace(gko_priority=False),
            }
        }
    }
    assert w._unreliable_align_layers() == {"top"}

    from services.prescreen import PrescreenIssue
    w._show_step(5)
    w._on_prescreen_finished([
        PrescreenIssue(kind="PAD", index=0, designator="C1", x=1.0, y=2.0),
    ])
    text = w._prescreen_summary.text()
    assert "unreliable" in text
    assert "#D97706" in w._prescreen_summary.styleSheet()


def test_prescreen_stats_gauge_line(app):
    from services.prescreen import PrescreenIssue
    w = _wizard(app)
    w._show_step(5)
    w._on_prescreen_stats({"n": 484, "median_mm": 1.45, "p95_mm": 3.2})
    w._on_prescreen_finished([])
    text = w._prescreen_summary.text()
    assert "1.45" in text and "484" in text

    w._on_prescreen_stats({"n": 0, "median_mm": None, "p95_mm": None})
    w._on_prescreen_finished([])
    assert "no paste data" in w._prescreen_summary.text()


def test_paste_file_filters_include_gpt_gpb():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    dlg_src = (root / "ui" / "gerber_file_dialog.py").read_text(encoding="utf-8")
    assert ".gpt" in dlg_src and ".gpb" in dlg_src


def test_get_prescreen_context_returns_paths_and_ctx(app):
    w = _wizard(app)
    assert w.get_prescreen_context() == (None, None, None, None)
    w._gko_path = "board.gko"
    w._gtp_path = "top.gtp"
    w._gbp_path = "bot.gbp"
    w._prescreen_ctx = {"origin_mode": "panel", "rotation_angle": 0}
    gko, gtp, gbp, ctx = w.get_prescreen_context()
    assert (gko, gtp, gbp) == ("board.gko", "top.gtp", "bot.gbp")
    assert ctx["origin_mode"] == "panel"


def test_wizard_browse_filters_include_gpt_gpb():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    wiz_src = (root / "ui" / "origin_align_wizard.py").read_text(encoding="utf-8")
    assert "*.gpt" in wiz_src and "*.gpb" in wiz_src

"""Align-to-pad: shift one side of components by one picked offset."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from models.review import ReviewRecord  # noqa: E402
from services.gerber.gerber_render import RenderData  # noqa: E402
from ui.gerber_viewer import GerberViewer  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _records():
    return [
        ReviewRecord(designator="R1", layer="top",
                     old_x=10.0, old_y=20.0, old_rotation=0.0),
        ReviewRecord(designator="C1", layer="top",
                     old_x=30.0, old_y=40.0, old_rotation=90.0),
        ReviewRecord(designator="B1", layer="bottom",
                     old_x=11.0, old_y=21.0, old_rotation=0.0,
                     status="OK"),
        ReviewRecord(designator="B2", layer="bottom",
                     old_x=12.0, old_y=22.0, old_rotation=0.0,
                     status="Pending"),
    ]


def _layers():
    from services.gerber.layer_scan import LayerInfo

    return [
        LayerInfo(path="C:/p/board.gtl", file_name="board.gtl",
                  name="Top copper", role="copper", side="top"),
    ]


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


def _viewer(app, records, monkeypatch, layers=None):
    v = _NoopGerberViewer(records, layers or _layers())
    v._layer_data = [RenderData() for _ in v._layers]
    v._loaded = True
    v._board_center = (0.0, 0.0)
    for stub in ("_redraw", "_apply_layer", "_fit_scene",
                 "_rebuild_marker_overlay"):
        monkeypatch.setattr(v, stub, lambda *a, **k: None)
    return v


def _accept_yes(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))


def _capture_deferred(monkeypatch):
    """Align runs behind a QTimer.singleShot(0); capture and run it later."""
    from PySide6.QtCore import QTimer

    pending = []

    def fake_single_shot(msec, callback, *args):
        if msec <= 0:
            pending.append(lambda: callback(*args))
            return None
        return real_single_shot(msec, callback, *args)

    real_single_shot = QTimer.singleShot
    monkeypatch.setattr(QTimer, "singleShot", fake_single_shot)
    return pending


def _accept_no(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.No))


def _select_first_top(v):
    v._combo_layer.setCurrentIndex(0)
    v._selected_marker_index = 0


def assert_close(a, b):
    assert abs(a - b) < 1e-6, f"{a} != {b}"


# ----------------------------------------------------------------------
# bulk apply: the delta lands in the frame of the record coordinates
# ----------------------------------------------------------------------

def test_apply_offsets_all_same_side_records(app, monkeypatch):
    records = _records()
    records[0].status = "Pending"
    records[1].status = "Edited"
    v = _viewer(app, records, monkeypatch)
    _accept_yes(monkeypatch)
    emitted = []
    v.align_edited.connect(lambda idx: emitted.append(list(idx)))

    # A picked pad at the record-frame point (11.5, 19.0): +1.5 X, -1.0 Y.
    ref, other = v._records[0], v._records[1]
    v._apply_align_delta(ref, 11.5, 19.0, snapped=True)

    assert_close(ref.new_x, 11.5)
    assert_close(ref.new_y, 19.0)
    assert_close(other.new_x, records[1].old_x + 1.5)
    assert_close(other.new_y, records[1].old_y - 1.0)
    for rec in (ref, other):
        assert rec.status == "Aligned"
        assert rec.review_time
    # Old values picked up for the history log of the main window.
    assert ref._align_old == (10.0, 20.0, 0.0, "")
    assert other._align_old == (30.0, 40.0, 90.0, "")

    assert len(emitted) == 1
    assert sorted(emitted[0]) == [0, 1]


def test_opposite_side_is_never_touched(app, monkeypatch):
    records = _records()
    records[2].status = "OK"
    records[3].status = "Pending"
    v = _viewer(app, records, monkeypatch)
    _accept_yes(monkeypatch)

    v._apply_align_delta(v._records[0], 11.5, 19.0, snapped=True)

    for rec in (v._records[2], v._records[3]):
        assert rec.status in ("OK", "Pending")
        assert rec.new_x is None and rec.new_y is None
        assert rec.review_time is None
        assert not hasattr(rec, "_align_old")


def test_zero_delta_applies_nothing(app, monkeypatch):
    records = _records()
    v = _viewer(app, records, monkeypatch)
    _accept_yes(monkeypatch)
    v._apply_align_delta(v._records[0], 10.0, 20.0, snapped=True)
    assert all(r.status == "Pending" for r in records[:2])
    assert all(r.review_time is None for r in records)


def test_declined_change_applies_nothing(app, monkeypatch):
    records = _records()
    v = _viewer(app, records, monkeypatch)
    _accept_no(monkeypatch)
    v._apply_align_delta(v._records[0], 15.0, 25.0, snapped=True)
    assert v._records[0].status == "Pending"
    assert v._records[1].new_x is None


def test_second_correction_compounds_on_first(app, monkeypatch):
    records = _records()
    v = _viewer(app, records, monkeypatch)
    _accept_yes(monkeypatch)
    ref, other = v._records[0], v._records[1]

    v._apply_align_delta(ref, 12.0, 17.0, snapped=True)   # (+2, -3)
    first_x, first_y = ref.new_x, ref.new_y
    v._apply_align_delta(ref, 14.5, 15.75, snapped=True)  # (+2.5, -1.25)

    assert_close(ref.new_x - first_x, 2.5)
    assert_close(ref.new_y - first_y, -1.25)
    # The history values of the second round hold the first round.
    assert ref._align_old == (first_x, first_y, 0.0, "")
    assert_close(other.new_x - other.old_x, 4.5)


def test_new_values_win_over_old_base(app, monkeypatch):
    records = _records()
    records[0].new_x = 10.5   # a manual nudge stands already
    records[0].new_y = 20.5
    v = _viewer(app, records, monkeypatch)
    _accept_yes(monkeypatch)
    ref = v._records[0]
    v._apply_align_delta(ref, 11.5, 20.5, snapped=True)   # (+1.0, +0.0)
    assert_close(ref.new_x, 11.5)
    assert_close(ref.new_y, 20.5)


def test_unsnapped_click_warns_in_the_dialog(app, monkeypatch):
    records = _records()
    texts = []
    v = _viewer(app, records, monkeypatch)
    _accept_yes(monkeypatch)

    import ui.gerber_viewer as gv
    real_translate = gv.tr

    def capturing_tr(key, **kwargs):
        texts.append(key.format(**kwargs) if kwargs else key)
        return real_translate(key, **kwargs)

    monkeypatch.setattr(gv, "tr", capturing_tr)
    v._apply_align_delta(v._records[0], 15.0, 25.0, snapped=False)
    assert any("Warning" in text for text in texts)


# ----------------------------------------------------------------------
# picking on the board: scene - origin - snap
# ----------------------------------------------------------------------

def test_click_subtracts_the_origin_and_applies(app, monkeypatch):
    records = _records()
    v = _viewer(app, records, monkeypatch)
    _accept_yes(monkeypatch)
    deferred = _capture_deferred(monkeypatch)
    _select_first_top(v)
    v._origin_x = 3.0
    v._origin_y = 4.0

    v._btn_align_pad.setChecked(True)
    assert v._align_pad_mode is True
    assert v._view._align_pad_mode is True

    # Scene point of the record-frame pick (12, 17): (12+3, -(17+4)).
    v._on_align_pad_clicked(15.0, -21.0)

    # The mode left itself; the work runs deferred (macOS freeze fix).
    assert v._align_pad_mode is False
    assert v._btn_align_pad.isChecked() is False
    assert v._records[0].status == "Pending"     # not applied yet
    assert len(deferred) == 1

    deferred[0]()

    ref, other = v._records[0], v._records[1]
    assert_close(ref.new_x, 12.0)
    assert_close(ref.new_y, 17.0)
    assert_close(other.new_x, other.old_x + 2.0)
    assert_close(other.new_y, other.old_y - 3.0)


def test_mode_needs_a_selected_component(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch)
    v._selected_marker_index = -1
    v._btn_align_pad.setChecked(True)
    assert v._align_pad_mode is False
    assert v._view._align_pad_mode is False


def test_right_click_or_esc_cancels_the_mode(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch)
    _select_first_top(v)
    v._btn_align_pad.setChecked(True)
    assert v._align_pad_mode is True

    v._view.align_pad_cancel.emit()
    assert v._align_pad_mode is False
    assert v._btn_align_pad.isChecked() is False


def test_click_without_selection_cancels_the_mode(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch)
    _select_first_top(v)
    v._btn_align_pad.setChecked(True)
    v._selected_marker_index = -1     # deselected after entering the mode
    v._on_align_pad_clicked(100.0, -100.0)
    assert v._align_pad_mode is False


# ----------------------------------------------------------------------
# snap preview: circle at the pad centre + live offset read-out
# ----------------------------------------------------------------------

def test_hover_shows_snap_circle_and_live_offset(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch)
    _select_first_top(v)
    v._origin_x = 3.0
    v._origin_y = 4.0
    # The pad lives in the file frame: mirror of the scene hover point.
    monkeypatch.setattr(v, "_snap_info", lambda gx, gy, force=False: (15.0, 21.0, 1.0))
    v._btn_align_pad.setChecked(True)

    # Hover at the scene point of board (12, 17): (15, -21) → Δ (+2, -3).
    v._on_align_move(15.0, -21.0)

    item = v._align_snap_item
    assert item is not None
    center = item.rect().center()
    assert_close(center.x(), 15.0)
    assert_close(center.y(), -21.0)
    text = v._lbl_status.text()
    assert "ΔX: +2.0000 mm" in text
    assert "ΔY: -3.0000 mm" in text
    assert "(snap)" in text


def test_hover_without_pad_stays_raw(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch)
    _select_first_top(v)
    monkeypatch.setattr(v, "_snap_info", lambda gx, gy, force=False: None)
    v._btn_align_pad.setChecked(True)

    v._on_align_move(100.0, -50.0)

    assert v._align_snap_item is None
    text = v._lbl_status.text()
    assert "(raw)" in text
    assert "(snap)" not in text


def test_preview_circle_is_cleared_when_the_mode_ends(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch)
    _select_first_top(v)
    monkeypatch.setattr(v, "_snap_info", lambda gx, gy, force=False: (15.0, 21.0, 1.0))
    v._btn_align_pad.setChecked(True)
    v._on_align_move(15.0, -21.0)
    assert v._align_snap_item is not None

    v._view.align_pad_cancel.emit()

    assert v._align_snap_item is None


# ----------------------------------------------------------------------
# pad snap roles: paste, then mask, then copper as stand-in
# ----------------------------------------------------------------------

from gerber_layers_helper import (  # noqa: E402
    make_layer, set_layer_data)
from services.gerber.gerber_render import FlashShape  # noqa: E402


def _flash(x, y, size=1.0):
    return FlashShape(cx=x, cy=y, kind="circle", w=size, h=size)


def _snap_layers():
    return [
        make_layer("Top Paste", "paste", side="top", file_name="a.gtp"),
        make_layer("Top Mask", "mask", side="top", file_name="a.gts"),
        make_layer("Top Copper", "copper", side="top", file_name="a.gtl"),
    ]


def _empty():
    return RenderData()


def test_pad_grid_falls_back_to_mask_flashes(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch, layers=_snap_layers())
    set_layer_data(v, "paste", _empty(), "top")
    set_layer_data(v, "mask",
                   RenderData(flashes=[_flash(7.0, 8.0, 0.8)]), "top")
    v._pad_grid_cache = {}

    grid = v._pad_grid(True)

    assert not grid.is_empty()
    assert grid.nearest_point(7.05, 8.02) == (7.0, 8.0, 0.8)


def test_pad_grid_prefers_paste_over_mask(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch, layers=_snap_layers())
    set_layer_data(v, "paste",
                   RenderData(flashes=[_flash(50.0, 60.0)]), "top")
    set_layer_data(v, "mask",
                   RenderData(flashes=[_flash(7.0, 8.0)]), "top")
    v._pad_grid_cache = {}

    grid = v._pad_grid(True)

    assert grid.nearest_point(50.01, 60.01) == (50.0, 60.0, 1.0)
    # Mask pads are not mixed in: the mask-only corner stays empty.
    assert grid.nearest_point(7.01, 8.01) is None


def test_pad_grid_uses_copper_when_paste_and_mask_are_missing(
        app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch, layers=_snap_layers())
    set_layer_data(v, "paste", _empty(), "top")
    set_layer_data(v, "mask", _empty(), "top")
    set_layer_data(v, "copper",
                   RenderData(flashes=[_flash(12.0, 34.0, 1.5)]), "top")
    v._pad_grid_cache = {}

    grid = v._pad_grid(True)

    assert grid.nearest_point(12.02, 33.98) == (12.0, 34.0, 1.5)


def test_pad_grid_cache_clears_on_a_fresh_load(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch, layers=_snap_layers())
    set_layer_data(v, "paste",
                   RenderData(flashes=[_flash(1.0, 2.0)]), "top")
    v._pad_grid_cache = {}
    assert not v._pad_grid(True).is_empty()

    for stub in ("_rebuild_layer_list", "_hide_layers_outside_the_board",
                 "_align_drill_layer", "_compute_board_center",
                 "_board_size", "_show_load_warnings"):
        monkeypatch.setattr(v, stub,
                            lambda *a, _s=stub: [] if "outside" in _s else None)
    monkeypatch.setattr(v, "_compute_board_center", lambda: (0.0, 0.0))
    monkeypatch.setattr(v, "_board_size", lambda: 10.0)
    set_layer_data(v, "paste", _empty(), "top")
    v._on_load_finished([_empty()])

    assert v._pad_grid(True).is_empty()


def test_no_pad_side_warns_when_the_mode_turns_on(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch, layers=_snap_layers())
    _select_first_top(v)
    v._pad_grid_cache = {}      # no layer geometry at all

    v._btn_align_pad.setChecked(True)

    assert "no pads on the" in v._lbl_status.text()


# ----------------------------------------------------------------------
# region centers, paste strokes, and snap_enabled independence
# ----------------------------------------------------------------------

def test_pad_grid_computes_bbox_center_for_polygon_regions(app, monkeypatch):
    v = _viewer(app, _records(), monkeypatch, layers=_snap_layers())
    set_layer_data(v, "paste", _empty(), "top")
    set_layer_data(v, "mask", _empty(), "top")
    # Region where first point is (10, 20), but bbox is (10, 20) -> (14, 26). True center = (12, 23).
    poly_fl = FlashShape(
        cx=10.0, cy=20.0, kind="polygon",
        pts=[(10.0, 20.0), (14.0, 20.0), (14.0, 26.0), (10.0, 26.0)],
        pts_local=False,
    )
    set_layer_data(v, "copper", RenderData(flashes=[poly_fl]), "top")
    v._pad_grid_cache = {}

    grid = v._pad_grid(True)
    hit = grid.nearest_point(12.1, 22.9)
    assert hit is not None
    assert_close(hit[0], 12.0)
    assert_close(hit[1], 23.0)


def test_pad_grid_detects_isolated_paste_strokes_as_pads(app, monkeypatch):
    from services.gerber.gerber_render import LineShape, ApertureInfo
    v = _viewer(app, _records(), monkeypatch, layers=_snap_layers())

    # Paste layer with 2 isolated short strokes (pads) and 1 connected 2-segment outline
    lines = [
        # Pad 1: from (10, 20) to (10, 22), mid (10, 21)
        LineShape(x1=10.0, y1=20.0, x2=10.0, y2=22.0, width=1.0, dcode=10),
        # Pad 2: from (30, 40) to (32, 40), mid (31, 40)
        LineShape(x1=30.0, y1=40.0, x2=32.0, y2=40.0, width=0.8, dcode=11),
        # Connected chain: (50, 50)->(50, 60)->(55, 60)
        LineShape(x1=50.0, y1=50.0, x2=50.0, y2=60.0, width=0.2, dcode=12),
        LineShape(x1=50.0, y1=60.0, x2=55.0, y2=60.0, width=0.2, dcode=12),
    ]
    apertures = {
        10: ApertureInfo(number=10, kind="rect", params=(1.0, 1.0)),
        11: ApertureInfo(number=11, kind="circle", params=(0.8,)),
        12: ApertureInfo(number=12, kind="circle", params=(0.2,)),
    }
    set_layer_data(v, "paste", RenderData(lines=lines, apertures=apertures), "top")
    v._pad_grid_cache = {}

    grid = v._pad_grid(True)
    # Pad 1 mid
    h1 = grid.nearest_point(10.05, 20.95)
    assert h1 is not None
    assert_close(h1[0], 10.0)
    assert_close(h1[1], 21.0)

    # Pad 2 mid
    h2 = grid.nearest_point(31.02, 39.98)
    assert h2 is not None
    assert_close(h2[0], 31.0)
    assert_close(h2[1], 40.0)

    # Connected outline midpoint should NOT be in pad grid
    h_chain = grid.nearest_point(50.0, 55.0)
    assert h_chain is None


def test_align_mode_snaps_even_when_global_snap_is_disabled(app, monkeypatch):
    records = _records()
    v = _viewer(app, records, monkeypatch, layers=_snap_layers())
    set_layer_data(v, "paste", RenderData(flashes=[_flash(15.0, 21.0, 1.0)]), "top")
    v._pad_grid_cache = {}
    _select_first_top(v)
    v._origin_x = 0.0
    v._origin_y = 0.0
    v._snap_enabled = False  # Global snap is OFF (as in test-data-02)

    v._btn_align_pad.setChecked(True)
    v._on_align_move(15.05, -21.05)

    assert v._align_snap_item is not None
    center = v._align_snap_item.rect().center()
    assert_close(center.x(), 15.0)
    assert_close(center.y(), -21.0)
    assert "(snap)" in v._lbl_status.text()



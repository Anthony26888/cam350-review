import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from models.review import ReviewRecord
from services.gerber.gerber_render import FlashShape, LineShape, RenderData
from ui.gerber_viewer import GerberViewer, _CROSS_BOARD_RATIO


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


@pytest.fixture()
def viewer(app):
    return _NoopGerberViewer([], r"C:\nonexistent.gko")


def test_apply_display_settings_round_trip(viewer):
    settings = {
        "layer": 1,
        "rotation": 180,
        "invert_rot": True,
        "flip": True,
        "mirror_x": True,
        "offset_x": 1.25,
        "offset_y": -0.5,
        "outline": False,
        "paste": True,
        "silk": False,
        "pickplace": True,
        "crosshair": False,
        "mag_factor": 10.0,
    }
    viewer.apply_display_settings(settings)
    d = viewer.display_settings()
    assert d["layer"] == 1
    assert d["rotation"] == 180
    assert d["invert_rot"] is True
    assert d["flip"] is True
    assert d["mirror_x"] is True
    assert d["offset_x"] == 1.25
    assert d["offset_y"] == -0.5
    assert d["outline"] is False
    assert d["paste"] is True
    assert d["silk"] is False
    assert d["pickplace"] is True
    assert d["crosshair"] is False
    assert d["mag_factor"] == 10.0


def test_default_settings_when_none(viewer):
    d = viewer.display_settings()
    assert d["layer"] == 0
    assert d["rotation"] == 0
    assert d["invert_rot"] is False
    assert d["flip"] is False
    assert d["mirror_x"] is False
    assert d["offset_x"] == 0.0
    assert d["offset_y"] == 0.0
    assert d["outline"] is True
    assert d["paste"] is True
    assert d["silk"] is True
    assert d["pickplace"] is True
    assert d["crosshair"] is True
    assert d["mag_factor"] == 6.0


def test_apply_invalid_does_not_crash(viewer):
    viewer.apply_display_settings(None)
    viewer.apply_display_settings({})
    viewer.apply_display_settings("nope")


def test_display_changes_not_live_until_save(viewer, monkeypatch):
    viewer._loaded = True
    calls = []
    monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
    viewer._combo_rot.setCurrentIndex(1)
    viewer._chk_flip.setChecked(True)
    viewer._chk_mirror_x.setChecked(True)
    viewer._spin_off_x.setValue(1.5)
    viewer._chk_outline.setChecked(False)
    viewer._chk_paste.setChecked(False)
    viewer._chk_silk.setChecked(False)
    viewer._chk_pickplace.setChecked(False)
    viewer._chk_crosshair.setChecked(False)
    assert calls == []


def test_save_display_settings_applies_redraw(viewer, monkeypatch):
    viewer._loaded = True
    calls = []
    monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
    saved = []
    viewer.settings_saved.connect(saved.append)
    viewer._combo_rot.setCurrentIndex(2)  # 180
    viewer._chk_flip.setChecked(True)
    viewer._spin_off_y.setValue(-0.75)
    viewer._save_display_settings()
    assert calls == [1]
    assert len(saved) == 1
    d = saved[0]
    assert d["rotation"] == 180
    assert d["flip"] is True
    assert d["offset_y"] == -0.75


def test_cancel_display_restores_widgets(viewer, monkeypatch):
    viewer._loaded = True
    calls = []
    monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
    viewer._display_snapshot = viewer.display_settings()
    viewer._combo_rot.setCurrentIndex(3)
    viewer._chk_flip.setChecked(True)
    viewer._on_display_rejected()
    assert viewer._combo_rot.currentIndex() == 0
    assert viewer._chk_flip.isChecked() is False
    assert calls == []


def test_reload_records_keeps_display_settings(viewer, monkeypatch):
    viewer._loaded = True
    viewer._combo_rot.setCurrentIndex(1)
    viewer._chk_flip.setChecked(True)
    calls = []
    monkeypatch.setattr(viewer, "refresh_records",
                        lambda records: calls.append(records))
    viewer._on_reload_records()
    # Reload re-syncs data but must not touch display settings
    assert calls == [viewer._records]
    assert viewer._combo_rot.currentIndex() == 1
    assert viewer._chk_flip.isChecked() is True


def test_pickplace_markers_stay_fixed_on_rotation(viewer):
    viewer._loaded = True
    viewer._records = [
        ReviewRecord(designator="R1", layer="Top",
                     old_x=10.0, old_y=20.0, old_rotation=30.0),
    ]
    viewer._component_index = [0]
    viewer._outline = RenderData()
    viewer._top = RenderData()
    viewer._bottom = RenderData()
    viewer._silk = RenderData()
    viewer._silk_bottom = RenderData()
    viewer._combo_layer.setCurrentIndex(0)
    viewer._cross_half = viewer._board_size() * _CROSS_BOARD_RATIO

    viewer._redraw()
    before = list(viewer._overlay._markers)
    assert before[0][0] == pytest.approx(10.0)
    assert before[0][1] == pytest.approx(-20.0)
    assert before[0][2] == pytest.approx(30.0)

    viewer._combo_rot.setCurrentIndex(1)  # 90°
    viewer._redraw()
    after = list(viewer._overlay._markers)
    # PickPlace is aligned to origin from the start, so rotation must not move it
    assert after == before


def test_pickplace_markers_stay_fixed_on_mirror_x(viewer):
    viewer._loaded = True
    viewer._records = [
        ReviewRecord(designator="R1", layer="Top",
                     old_x=10.0, old_y=20.0, old_rotation=30.0),
    ]
    viewer._component_index = [0]
    viewer._outline = RenderData()
    viewer._top = RenderData()
    viewer._bottom = RenderData()
    viewer._silk = RenderData()
    viewer._silk_bottom = RenderData()
    viewer._combo_layer.setCurrentIndex(0)
    viewer._cross_half = viewer._board_size() * _CROSS_BOARD_RATIO

    viewer._redraw()
    before = list(viewer._overlay._markers)

    viewer._chk_mirror_x.setChecked(True)
    viewer._redraw()
    after = list(viewer._overlay._markers)
    # PickPlace stays fixed; only the Gerber drawing mirrors
    assert after == before


def test_bring_gerber_to_origin_sets_offsets(viewer):
    viewer._loaded = True
    viewer._outline = RenderData(lines=[LineShape(x1=265.9, y1=163.3, x2=418.9, y2=391.9)])
    viewer._top = RenderData()
    viewer._bottom = RenderData()
    viewer._silk = RenderData()
    viewer._silk_bottom = RenderData()
    viewer._combo_layer.setCurrentIndex(0)
    viewer._board_center = viewer._compute_board_center()

    viewer._bring_gerber_to_origin()
    d = viewer.display_settings()
    assert d["offset_x"] == pytest.approx(-265.9)
    assert d["offset_y"] == pytest.approx(-163.3)


def test_bring_gerber_to_origin_fallback_to_paste(viewer):
    viewer._loaded = True
    viewer._outline = RenderData()
    viewer._top = RenderData(
        lines=[LineShape(x1=100.0, y1=50.0, x2=200.0, y2=150.0)]
    )
    viewer._bottom = RenderData()
    viewer._silk = RenderData()
    viewer._silk_bottom = RenderData()
    viewer._combo_layer.setCurrentIndex(0)
    viewer._board_center = viewer._compute_board_center()

    viewer._bring_gerber_to_origin()
    d = viewer.display_settings()
    assert d["offset_x"] == pytest.approx(-100.0)
    assert d["offset_y"] == pytest.approx(-50.0)


def test_gerber_scene_rect_outline(viewer):
    viewer._loaded = True
    viewer._outline = RenderData(lines=[LineShape(x1=265.9, y1=163.3, x2=418.9, y2=391.9)])
    viewer._top = RenderData()
    viewer._bottom = RenderData()
    viewer._board_center = viewer._compute_board_center()
    rect = viewer._gerber_scene_rect()
    assert rect.left() == pytest.approx(265.9)
    assert rect.top() == pytest.approx(-391.9)
    assert rect.width() == pytest.approx(153.0)
    assert rect.height() == pytest.approx(228.6)


def test_gerber_scene_rect_applies_offset(viewer):
    viewer._loaded = True
    viewer._outline = RenderData(lines=[LineShape(x1=265.9, y1=163.3, x2=418.9, y2=391.9)])
    viewer._top = RenderData()
    viewer._bottom = RenderData()
    viewer._board_center = viewer._compute_board_center()
    viewer._spin_off_x.setValue(-265.9)
    viewer._spin_off_y.setValue(-163.3)
    rect = viewer._gerber_scene_rect()
    assert rect.left() == pytest.approx(0.0)
    assert rect.top() == pytest.approx(-228.6)
    assert rect.right() == pytest.approx(153.0)


def test_fit_scene_gerber_only_when_markers_near(viewer):
    viewer._loaded = True
    viewer._outline = RenderData(lines=[LineShape(x1=0.0, y1=0.0, x2=100.0, y2=100.0)])
    viewer._top = RenderData()
    viewer._bottom = RenderData()
    viewer._board_center = viewer._compute_board_center()
    viewer._records = [
        ReviewRecord(designator="R1", layer="Top",
                     old_x=10.0, old_y=20.0, old_rotation=30.0),
    ]
    viewer._component_index = [0]
    viewer._redraw()
    assert viewer._overlay is not None
    viewer._fit_scene()
    assert abs(viewer._view.transform().m11()) > 0.0


def test_fit_scene_unions_far_markers(viewer):
    viewer._loaded = True
    viewer._outline = RenderData(lines=[LineShape(x1=0.0, y1=0.0, x2=100.0, y2=100.0)])
    viewer._top = RenderData()
    viewer._bottom = RenderData()
    viewer._board_center = viewer._compute_board_center()
    viewer._records = [
        ReviewRecord(designator="R1", layer="Top",
                     old_x=1000.0, old_y=1000.0, old_rotation=30.0),
    ]
    viewer._component_index = [0]
    viewer._redraw()
    assert viewer._overlay is not None
    viewer._fit_scene()
    assert abs(viewer._view.transform().m11()) > 0.0


def test_group_by_mpn_builds_grouped_rows(viewer):
    viewer._records = [
        ReviewRecord(designator="C1", mpn="C0402", layer="Top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="C0402", layer="Top",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
        ReviewRecord(designator="R1", mpn="R0603", layer="Top",
                     old_x=5.0, old_y=6.0, old_rotation=0.0),
    ]
    viewer._group_by_mpn = True
    viewer._apply_layer()
    assert viewer._table_components.rowCount() == 2
    assert viewer._component_index == [0, 2]
    assert viewer._group_rows == [[0, 1], [2]]
    assert viewer._table_components.horizontalHeaderItem(1).text() == "MPN"
    assert viewer._table_components.horizontalHeaderItem(2).text() == "Designator"
    assert viewer._table_components.horizontalHeaderItem(3).text() == "Qty"
    assert viewer._table_components.item(0, 1).text() == "C0402"
    assert viewer._table_components.item(0, 2).text() == "C1, C2"
    assert viewer._table_components.item(0, 3).text() == "2"
    assert viewer._table_components.item(1, 1).text() == "R0603"
    assert viewer._table_components.item(1, 3).text() == "1"


def test_group_by_mpn_respects_search_filter(viewer):
    viewer._records = [
        ReviewRecord(designator="C1", mpn="C0402", layer="Top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="C0402", layer="Top",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
        ReviewRecord(designator="R1", mpn="R0603", layer="Top",
                     old_x=5.0, old_y=6.0, old_rotation=0.0),
    ]
    viewer._group_by_mpn = True
    viewer._search_input.setText("c")
    viewer._apply_layer()
    assert viewer._table_components.rowCount() == 1
    assert viewer._component_index == [0]
    assert viewer._group_rows == [[0, 1]]


def test_group_by_mpn_respects_layer(viewer):
    viewer._records = [
        ReviewRecord(designator="C1", mpn="C0402", layer="Top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="C0402", layer="Bottom",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
    ]
    viewer._group_by_mpn = True
    viewer._combo_layer.setCurrentIndex(1)
    viewer._apply_layer()
    assert viewer._table_components.rowCount() == 1
    assert viewer._component_index == [0]
    assert viewer._group_rows == [[0]]


def test_group_by_mpn_restores_multi_highlight(viewer):
    viewer._records = [
        ReviewRecord(designator="C1", mpn="C0402", layer="Top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="C0402", layer="Top",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
        ReviewRecord(designator="R1", mpn="R0603", layer="Top",
                     old_x=5.0, old_y=6.0, old_rotation=0.0),
    ]
    viewer._group_by_mpn = True
    viewer._apply_layer()
    viewer._on_row_changed(0)
    assert viewer._selected_marker_indices == {0, 1}
    viewer._on_row_changed(1)
    assert viewer._selected_marker_indices == {2}


def test_group_by_mpn_double_click_highlights_group(viewer):
    viewer._records = [
        ReviewRecord(designator="C1", mpn="C0402", layer="Top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="C0402", layer="Top",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
        ReviewRecord(designator="R1", mpn="R0603", layer="Top",
                     old_x=5.0, old_y=6.0, old_rotation=0.0),
    ]
    viewer._group_by_mpn = True
    viewer._apply_layer()
    viewer._on_component_double_clicked(0, 1)
    assert viewer._selected_marker_indices == {0, 1}


def test_group_by_mpn_table_wraps_and_sets_width(viewer):
    viewer._records = [
        ReviewRecord(designator="C1", mpn="C0402", layer="Top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="C0402", layer="Top",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
    ]
    assert viewer._table_components.wordWrap() is True
    viewer._chk_group_mpn.setChecked(True)
    assert viewer._group_by_mpn is True
    assert viewer._table_components.columnWidth(2) == 200
    viewer._chk_group_mpn.setChecked(False)
    assert viewer._group_by_mpn is False
    assert viewer._table_components.columnWidth(2) != 200


def test_group_by_mpn_toggle_resets_selection(viewer):
    viewer._records = [
        ReviewRecord(designator="C1", mpn="C0402", layer="Top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="C0402", layer="Top",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
    ]
    viewer._chk_group_mpn.setChecked(True)
    assert viewer._group_by_mpn is True
    assert viewer._table_components.rowCount() == 1
    viewer._chk_group_mpn.setChecked(False)
    assert viewer._group_by_mpn is False
    assert viewer._table_components.rowCount() == 2


def test_color_defaults_in_settings(viewer):
    d = viewer.display_settings()
    assert d["outline_color"] == "#fff8fafc"
    assert d["paste_top_color"] == "#d222d3ee"
    assert d["paste_bottom_color"] == "#d2fbbf24"
    assert d["silk_color"] == "#dcf0abfc"
    assert d["cross_color"] == "#ffef4444"
    assert d["highlight_color"] == "#ff39ff14"
    assert d["frame"] is True


def test_apply_color_settings_round_trip(viewer):
    settings = {
        "outline_color": "#ff112233",
        "paste_top_color": "#aaff0000",
        "silk_color": "#ff00ff00",
        "cross_color": "#ff0000ff",
        "highlight_color": "#ff123456",
        "frame": False,
    }
    viewer.apply_display_settings(settings)
    d = viewer.display_settings()
    assert d["outline_color"] == "#ff112233"
    assert d["paste_top_color"] == "#aaff0000"
    assert d["silk_color"] == "#ff00ff00"
    assert d["cross_color"] == "#ff0000ff"
    assert d["highlight_color"] == "#ff123456"
    assert d["frame"] is False
    assert viewer._colors["outline"] == QColor("#ff112233")
    assert viewer._colors["highlight"] == QColor("#ff123456")
    assert viewer._show_frame is False


def test_color_settings_ignore_invalid(viewer):
    viewer.apply_display_settings({"outline_color": "not-a-color"})
    assert viewer._colors["outline"] == QColor("#F8FAFC")


def test_color_pending_applied_on_save(viewer):
    viewer._color_pending["cross"] = "#ff00ff00"
    viewer._save_display_settings()
    assert viewer._colors["cross"] == QColor("#ff00ff00")
    assert viewer._color_pending == {}
    d = viewer.display_settings()
    assert d["cross_color"] == "#ff00ff00"


def test_cancel_color_restores(viewer):
    viewer._colors["cross"] = QColor("#ff00ff00")
    viewer._display_snapshot = viewer.display_settings()
    viewer._color_pending["cross"] = "#ffff0000"
    viewer._on_display_rejected()
    assert viewer._color_pending == {}


def test_saving_indicator_hidden_by_default(viewer):
    assert viewer._progress_save.isHidden() is True
    assert viewer._lbl_saving.isHidden() is True
    assert viewer._btn_save_disp.isEnabled() is True


def test_save_shows_loading_indicator(viewer, monkeypatch):
    seen = {}
    def fake_redraw():
        seen["progress_hidden"] = viewer._progress_save.isHidden()
        seen["lbl_hidden"] = viewer._lbl_saving.isHidden()
        seen["btn_enabled"] = viewer._btn_save_disp.isEnabled()
    monkeypatch.setattr(viewer, "_redraw", fake_redraw)
    viewer._save_display_settings()
    assert seen["progress_hidden"] is False
    assert seen["lbl_hidden"] is False
    assert seen["btn_enabled"] is False


def test_open_display_dialog_resets_saving_state(viewer, monkeypatch):
    viewer._btn_save_disp.setEnabled(False)
    viewer._progress_save.setVisible(True)
    viewer._lbl_saving.setVisible(True)
    monkeypatch.setattr(viewer._display_dialog, "exec", lambda: None)
    viewer._open_display_dialog()
    assert viewer._btn_save_disp.isEnabled() is True
    assert viewer._progress_save.isHidden() is True
    assert viewer._lbl_saving.isHidden() is True


def test_paste_layer_renders_lines_and_fills(viewer):
    viewer._loaded = True
    viewer._top = RenderData(
        lines=[LineShape(x1=0.0, y1=0.0, x2=10.0, y2=0.0, width=1.0)],
        flashes=[FlashShape(cx=5.0, cy=5.0, kind="circle", w=2.0, h=2.0)],
    )
    viewer._chk_paste.setChecked(True)
    viewer._apply_style(0.0, False, False, 0.0, 0.0, True)
    assert viewer._line_items.get("paste")
    assert viewer._fill_items.get("paste") is not None


def test_paste_layer_hidden_when_unchecked(viewer):
    viewer._loaded = True
    viewer._top = RenderData(
        lines=[LineShape(x1=0.0, y1=0.0, x2=10.0, y2=0.0, width=1.0)],
        flashes=[FlashShape(cx=5.0, cy=5.0, kind="circle", w=2.0, h=2.0)],
    )
    viewer._chk_paste.setChecked(True)
    viewer._apply_style(0.0, False, False, 0.0, 0.0, True)
    line_items = viewer._line_items["paste"]
    fill_item = viewer._fill_items["paste"]
    assert line_items and all(i.isVisible() for i in line_items)
    assert fill_item is not None and fill_item.isVisible()
    viewer._chk_paste.setChecked(False)
    viewer._apply_style(0.0, False, False, 0.0, 0.0, True)
    assert not any(i.isVisible() for i in line_items)
    assert not fill_item.isVisible()
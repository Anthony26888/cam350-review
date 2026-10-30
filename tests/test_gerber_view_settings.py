import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from gerber_layers_helper import LAYERS, make_layer, make_layers
from models.review import ReviewRecord
from services.gerber.gerber_render import FlashShape, LineShape, RenderData
from ui.gerber_viewer import GerberViewer, _CROSS_BOARD_RATIO


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


def _role_index(viewer, role, side=""):
    for index, layer in enumerate(viewer._layers):
        if layer.role != role:
            continue
        if side and layer.side and layer.side != side:
            continue
        return index
    return -1


def _set_layer(viewer, role, data, side=""):
    """Give one layer of the viewer its geometry."""
    index = _role_index(viewer, role, side)
    if index >= 0:
        viewer._layer_data[index] = data
    return index


@pytest.fixture()
def viewer(app):
    v = _NoopGerberViewer([], list(LAYERS))
    v._layer_data = [RenderData() for _ in LAYERS]
    return v


def test_apply_display_settings_round_trip(viewer):
    settings = {
        "layer": 1,
        "rotation": 180,
        "flip": True,
        "mirror_x": True,
        "pickplace": True,
        "crosshair": False,
        "mag_factor": 10.0,
        "grid": True,
        "grid_cols": 4,
        "grid_rows": 5,
    }
    viewer.apply_display_settings(settings)
    d = viewer.display_settings()
    assert d["layer"] == 1
    assert d["rotation"] == 180
    assert d["flip"] is True
    assert d["mirror_x"] is True
    assert d["layers"]
    assert d["active_layer"]
    assert d["pickplace"] is True
    assert d["crosshair"] is False
    assert d["mag_factor"] == 10.0
    assert d["grid"] is True
    assert d["grid_cols"] == 4
    assert d["grid_rows"] == 5


def test_default_settings_when_none(viewer):
    d = viewer.display_settings()
    assert d["layer"] == 0
    assert d["rotation"] == 0
    assert d["flip"] is False
    assert d["mirror_x"] is False
    assert d["layer_transforms"] == {
        "top": {"rotation": 0, "flip": False, "mirror_x": False},
        "bottom": {"rotation": 0, "flip": False, "mirror_x": False},
    }
    assert len(d["layers"]) == len(LAYERS)
    assert all(entry["state"] == "normal" for entry in d["layers"])
    assert d["pickplace"] is True
    assert d["crosshair"] is True
    assert d["mag_factor"] == 6.0
    assert d["grid"] is False
    assert d["grid_cols"] == 3
    assert d["grid_rows"] == 3


def test_layer_transforms_are_independent(viewer):
    viewer._set_rotation(90, emit=False)
    viewer._chk_flip.setChecked(True)

    viewer._combo_layer.setCurrentIndex(1)
    assert viewer._rotation == 0
    assert viewer._chk_flip.isChecked() is False
    viewer._set_rotation(180, emit=False)
    viewer._chk_mirror_x.setChecked(True)

    viewer._combo_layer.setCurrentIndex(0)
    assert viewer._rotation == 90
    assert viewer._chk_flip.isChecked() is True
    assert viewer._chk_mirror_x.isChecked() is False

    viewer._combo_layer.setCurrentIndex(1)
    assert viewer._rotation == 180
    assert viewer._chk_flip.isChecked() is False
    assert viewer._chk_mirror_x.isChecked() is True


def test_layer_transforms_round_trip(viewer):
    settings = {
        "layer": 1,
        "rotation": 0,
        "flip": False,
        "mirror_x": False,
        "layer_transforms": {
            "top": {"rotation": 90, "flip": True, "mirror_x": False},
            "bottom": {"rotation": 270, "flip": False, "mirror_x": True},
        },
    }
    viewer.apply_display_settings(settings)
    assert viewer._rotation == 270
    assert viewer._chk_flip.isChecked() is False
    assert viewer._chk_mirror_x.isChecked() is True

    d = viewer.display_settings()
    assert d["layer_transforms"]["top"] == {
        "rotation": 90, "flip": True, "mirror_x": False}
    assert d["layer_transforms"]["bottom"] == {
        "rotation": 270, "flip": False, "mirror_x": True}

    viewer._combo_layer.setCurrentIndex(0)
    assert viewer._rotation == 90
    assert viewer._chk_flip.isChecked() is True
    assert viewer._chk_mirror_x.isChecked() is False


def test_legacy_global_transform_fills_both_sides(viewer):
    viewer.apply_display_settings({
        "layer": 1, "rotation": 180, "flip": True, "mirror_x": True,
    })
    assert viewer._rotation == 180
    assert viewer._chk_flip.isChecked() is True
    assert viewer._chk_mirror_x.isChecked() is True
    d = viewer.display_settings()
    expected = {"rotation": 180, "flip": True, "mirror_x": True}
    assert d["layer_transforms"]["top"] == expected
    assert d["layer_transforms"]["bottom"] == expected


def test_partial_layer_transforms_fall_back_to_global(viewer):
    viewer.apply_display_settings({
        "layer": 0,
        "rotation": 90,
        "flip": True,
        "mirror_x": False,
        "layer_transforms": {"top": {"rotation": 270}},
    })
    d = viewer.display_settings()
    assert d["layer_transforms"]["top"] == {
        "rotation": 270, "flip": True, "mirror_x": False}
    assert d["layer_transforms"]["bottom"] == {
        "rotation": 90, "flip": True, "mirror_x": False}


def test_invalid_layer_transforms_do_not_crash(viewer):
    viewer.apply_display_settings({
        "layer_transforms": {
            "top": "not-a-transform",
            "bottom": {"rotation": "not-a-number"},
        },
    })
    d = viewer.display_settings()
    assert d["layer_transforms"]["top"] == {
        "rotation": 0, "flip": False, "mirror_x": False}
    assert d["layer_transforms"]["bottom"] == {
        "rotation": 0, "flip": False, "mirror_x": False}


def test_transform_change_emits_full_layer_map(viewer):
    saved = []
    viewer.settings_saved.connect(saved.append)
    viewer._set_rotation(90)
    assert saved
    assert saved[-1]["layer_transforms"]["top"]["rotation"] == 90
    assert saved[-1]["layer_transforms"]["bottom"]["rotation"] == 0


def test_layer_switch_does_not_emit_settings(viewer):
    saved = []
    viewer.settings_saved.connect(saved.append)
    viewer._combo_layer.setCurrentIndex(1)
    assert saved == []


def test_partial_settings_keep_the_current_transform(viewer):
    viewer._set_rotation(90, emit=False)
    viewer._chk_flip.setChecked(True)
    viewer.apply_display_settings({"snap": False})
    assert viewer._rotation == 90
    assert viewer._chk_flip.isChecked() is True


def test_apply_invalid_does_not_crash(viewer):
    viewer.apply_display_settings(None)
    viewer.apply_display_settings({})
    viewer.apply_display_settings("nope")


def test_grid_draft_changes_not_live_until_save(viewer, monkeypatch):
    viewer._loaded = True
    calls = []
    monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
    viewer._grid_available = True
    viewer._update_grid_info()
    # Drafts may be changed as much as they like:
    viewer._gd_chk_grid.setChecked(True)
    viewer._gd_spin_cols.setValue(5)
    viewer._gd_spin_rows.setValue(4)
    viewer._gd_spin_tol.setValue(1.5)
    assert viewer._chk_grid.isChecked() is False
    assert viewer._spin_grid_cols.value() == 3
    assert viewer._spin_grid_rows.value() == 3
    assert viewer._spin_snap_tol.value() != 1.5
    # ... nothing is redrawn until the user saves
    assert calls == []
    viewer._save_grid_dialog()
    assert viewer._chk_grid.isChecked() is True
    assert viewer._spin_grid_cols.value() == 5
    assert viewer._spin_grid_rows.value() == 4
    assert viewer._spin_snap_tol.value() == pytest.approx(1.5)


def test_the_crosshair_of_the_card_is_live_at_once(viewer, monkeypatch):
    # The crosshair stands in the card now, so it is drawn right away.
    viewer._loaded = True
    calls = []
    monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
    viewer._chk_crosshair.setChecked(False)
    assert calls


def test_pickplace_dialog_save_applies(viewer, monkeypatch):
    viewer._loaded = True
    calls = []
    monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
    saved = []
    viewer.settings_saved.connect(saved.append)
    viewer._sync_pickplace_dialog()
    viewer._pp_chk_pickplace.setChecked(False)
    viewer._pp_spin_cross_scale.setValue(3.5)
    viewer._pp_color_draft["cross"] = "#ff00ff00"
    viewer._save_pickplace_dialog()
    assert viewer._chk_pickplace.isChecked() is False
    assert viewer._spin_cross_scale.value() == pytest.approx(3.5)
    assert viewer._colors["cross"] == QColor("#ff00ff00")
    assert viewer._pp_color_draft == {}
    assert calls  # the save path redraws (the toggled state widget does too)
    assert len(saved) == 1
    d = saved[0]
    assert d["pickplace"] is False
    assert d["crosshair_scale"] == pytest.approx(3.5)
    assert d["cross_color"] == "#ff00ff00"


def test_pickplace_dialog_cancel_discards(viewer, monkeypatch):
    viewer._loaded = True
    calls = []
    monkeypatch.setattr(viewer, "_redraw", lambda: calls.append(1))
    viewer._sync_pickplace_dialog()
    viewer._pp_chk_pickplace.setChecked(False)
    viewer._pp_color_draft["cross"] = "#ffff0000"
    viewer._cancel_pickplace_dialog()
    assert viewer._chk_pickplace.isChecked() is True
    assert viewer._pp_color_draft == {}
    assert calls == []


def test_reload_records_keeps_display_settings(viewer, monkeypatch):
    viewer._loaded = True
    viewer._set_rotation(90, emit=False)
    viewer._chk_flip.setChecked(True)
    calls = []
    monkeypatch.setattr(viewer, "refresh_records",
                        lambda records: calls.append(records))
    viewer._on_reload_records()
    # Reload re-syncs data but must not touch display settings
    assert calls == [viewer._records]
    assert viewer._rotation == 90
    assert viewer._chk_flip.isChecked() is True


def test_pickplace_markers_stay_fixed_on_rotation(viewer):
    viewer._loaded = True
    viewer._records = [
        ReviewRecord(designator="R1", layer="Top",
                     old_x=10.0, old_y=20.0, old_rotation=30.0),
    ]
    viewer._component_index = [0]
    _set_layer(viewer, "profile", RenderData())
    _set_layer(viewer, "paste", RenderData(), "top")
    _set_layer(viewer, "paste", RenderData(), "bottom")
    _set_layer(viewer, "silk", RenderData(), "top")
    _set_layer(viewer, "silk", RenderData(), "bottom")
    viewer._combo_layer.setCurrentIndex(0)
    viewer._cross_half = viewer._board_size() * _CROSS_BOARD_RATIO

    viewer._redraw()
    before = list(viewer._overlay._markers)
    assert before[0][0] == pytest.approx(10.0)
    assert before[0][1] == pytest.approx(-20.0)
    assert before[0][2] == pytest.approx(30.0)

    viewer._set_rotation(90, emit=False)
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
    _set_layer(viewer, "profile", RenderData())
    _set_layer(viewer, "paste", RenderData(), "top")
    _set_layer(viewer, "paste", RenderData(), "bottom")
    _set_layer(viewer, "silk", RenderData(), "top")
    _set_layer(viewer, "silk", RenderData(), "bottom")
    viewer._combo_layer.setCurrentIndex(0)
    viewer._cross_half = viewer._board_size() * _CROSS_BOARD_RATIO

    viewer._redraw()
    before = list(viewer._overlay._markers)

    viewer._chk_mirror_x.setChecked(True)
    viewer._redraw()
    after = list(viewer._overlay._markers)
    # PickPlace stays fixed; only the Gerber drawing mirrors
    assert after == before


def test_gerber_scene_rect_outline(viewer):
    viewer._loaded = True
    _set_layer(viewer, "profile", RenderData(lines=[LineShape(x1=265.9, y1=163.3, x2=418.9, y2=391.9)]))
    _set_layer(viewer, "paste", RenderData(), "top")
    _set_layer(viewer, "paste", RenderData(), "bottom")
    viewer._board_center = viewer._compute_board_center()
    rect = viewer._gerber_scene_rect()
    assert rect.left() == pytest.approx(265.9)
    assert rect.top() == pytest.approx(-391.9)
    assert rect.width() == pytest.approx(153.0)
    assert rect.height() == pytest.approx(228.6)


def test_gerber_scene_rect_applies_rotation(viewer):
    viewer._loaded = True
    _set_layer(viewer, "profile", RenderData(lines=[LineShape(x1=265.9, y1=163.3, x2=418.9, y2=391.9)]))
    _set_layer(viewer, "paste", RenderData(), "top")
    _set_layer(viewer, "paste", RenderData(), "bottom")
    viewer._board_center = viewer._compute_board_center()
    viewer._set_rotation(90, emit=False)
    rect = viewer._gerber_scene_rect()
    # A 90° turn swaps width and height of the board
    assert rect.width() == pytest.approx(228.6)
    assert rect.height() == pytest.approx(153.0)


def test_fit_scene_gerber_only_when_markers_near(viewer):
    viewer._loaded = True
    _set_layer(viewer, "profile", RenderData(lines=[LineShape(x1=0.0, y1=0.0, x2=100.0, y2=100.0)]))
    _set_layer(viewer, "paste", RenderData(), "top")
    _set_layer(viewer, "paste", RenderData(), "bottom")
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
    _set_layer(viewer, "profile", RenderData(lines=[LineShape(x1=0.0, y1=0.0, x2=100.0, y2=100.0)]))
    _set_layer(viewer, "paste", RenderData(), "top")
    _set_layer(viewer, "paste", RenderData(), "bottom")
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
    colours = {entry["name"]: entry["color"] for entry in d["layers"]}
    assert colours["Board Outline"] == "#fff8fafc"
    assert colours["Top Paste"] == "#d222d3ee"
    assert colours["Bottom Paste"] == "#d2fbbf24"
    assert colours["Top Silkscreen"] == "#dcf0abfc"
    assert d["cross_color"] == "#ffef4444"
    assert d["highlight_color"] == "#ff39ff14"
    assert d["frame"] is True


def test_apply_color_settings_round_trip(viewer):
    settings = {
        "layers": [
            {"key": LAYERS[0].key(), "color": "#ff112233"},
            {"key": LAYERS[1].key(), "color": "#aaff0000"},
        ],
        "cross_color": "#ff0000ff",
        "highlight_color": "#ff123456",
        "frame": False,
    }
    viewer.apply_display_settings(settings)
    d = viewer.display_settings()
    colours = {entry["key"]: entry["color"] for entry in d["layers"]}
    assert colours[LAYERS[0].key()] == "#ff112233"
    assert colours[LAYERS[1].key()] == "#aaff0000"
    assert d["cross_color"] == "#ff0000ff"
    assert d["highlight_color"] == "#ff123456"
    assert d["frame"] is False
    assert viewer._layer_colors[0] == QColor("#ff112233")
    assert viewer._colors["highlight"] == QColor("#ff123456")
    assert viewer._show_frame is False


def test_color_settings_ignore_invalid(viewer):
    viewer.apply_display_settings(
        {"layers": [{"key": LAYERS[0].key(), "color": "not-a-color"}]})
    assert viewer._layer_colors[0] == QColor("#F8FAFC")


def test_color_draft_applied_on_save(viewer):
    viewer._pp_color_draft["cross"] = "#ff00ff00"
    viewer._save_pickplace_dialog()
    assert viewer._colors["cross"] == QColor("#ff00ff00")
    assert viewer._pp_color_draft == {}
    d = viewer.display_settings()
    assert d["cross_color"] == "#ff00ff00"


def test_cancel_color_discards_draft(viewer):
    viewer._colors["cross"] = QColor("#ff00ff00")
    viewer._pp_color_draft["cross"] = "#ffff0000"
    viewer._cancel_pickplace_dialog()
    assert viewer._colors["cross"] == QColor("#ff00ff00")
    assert viewer._pp_color_draft == {}


def test_full_crosshair_is_always_on(viewer):
    assert viewer._view._full_cross_enabled is True


def test_rotate_menu_follows_set_rotation(viewer):
    viewer._set_rotation(180, emit=False)
    viewer._sync_transform_controls()
    checked = [a.data() for a in viewer._btn_rotate.menu().actions()
               if a.isChecked()]
    assert checked == [180]
    # The stacked toolbar button keeps its fixed label
    assert viewer._btn_rotate.text() == "Rotate"


def test_flip_toolbar_buttons_follow_the_state_widgets(viewer):
    # Mirror Y belongs to Flip Y, Mirror X belongs to Flip X
    viewer._chk_flip.setChecked(True)
    assert viewer._btn_flip_y.isChecked() is True
    assert viewer._btn_flip_x.isChecked() is False
    viewer._chk_mirror_x.setChecked(True)
    assert viewer._btn_flip_x.isChecked() is True
    # ... and the buttons move the state widgets back
    viewer._btn_flip_y.setChecked(False)
    assert viewer._chk_flip.isChecked() is False
    viewer._btn_flip_x.setChecked(False)
    assert viewer._chk_mirror_x.isChecked() is False


def test_grid_dialog_information_shows_the_board(viewer):
    viewer._loaded = True
    _set_layer(viewer, "profile", RenderData(
        lines=[LineShape(x1=0.0, y1=0.0, x2=100.0, y2=200.0)]))
    _set_layer(viewer, "paste", RenderData(), "top")
    _set_layer(viewer, "paste", RenderData(), "bottom")
    viewer._board_center = viewer._compute_board_center()
    viewer._grid_available = True
    viewer._update_grid_info()
    info = viewer._lbl_grid_info.text()
    assert "100.00" in info
    assert "200.00" in info


def test_grid_dialog_information_when_board_missing(viewer):
    viewer._update_grid_info()
    assert viewer._lbl_grid_info.text()


def test_paste_layer_renders_lines_and_fills(viewer):
    viewer._loaded = True
    _set_layer(viewer, "paste", RenderData(
        lines=[LineShape(x1=0.0, y1=0.0, x2=10.0, y2=0.0, width=1.0)],
        flashes=[FlashShape(cx=5.0, cy=5.0, kind="circle", w=2.0, h=2.0)],
    ), "top")
    viewer._apply_style(0.0, False, False, 0.0, 0.0, True)
    assert viewer._layer_items


def test_paste_layer_hidden_when_unchecked(viewer):
    viewer._loaded = True
    _set_layer(viewer, "paste", RenderData(
        lines=[LineShape(x1=0.0, y1=0.0, x2=10.0, y2=0.0, width=1.0)],
        flashes=[FlashShape(cx=5.0, cy=5.0, kind="circle", w=2.0, h=2.0)],
    ), "top")
    index = _role_index(viewer, "paste", "top")
    viewer._apply_style(0.0, False, False, 0.0, 0.0, True)
    item = viewer._layer_items[index]
    assert item is not None
    assert item.isVisible()
    viewer._layer_states[index] = "hidden"
    viewer._apply_style(0.0, False, False, 0.0, 0.0, True)
    assert not item.isVisible()
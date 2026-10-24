"""Choosing the origin of the coordinates of the Gerber by hand."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from services.gerber.gerber_render import RenderData  # noqa: E402
from ui.gerber_viewer import GerberViewer, _target_icon  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _layers():
    from services.gerber.layer_scan import LayerInfo

    return [
        LayerInfo(path="C:/p/board.gtl", file_name="board.gtl",
                  name="Top copper", role="copper", side="top"),
    ]


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


@pytest.fixture()
def viewer(app):
    v = _NoopGerberViewer([], _layers())
    v._layer_data = [RenderData() for _ in v._layers]
    v._loaded = True
    v._board_center = (0.0, 0.0)
    v._redraw()
    return v


class TestTheToolbar:
    def test_the_toolbar_holds_the_button(self, viewer):
        assert viewer._toolbar is not None
        assert viewer._btn_set_origin in viewer._toolbar.findChildren(
            type(viewer._btn_set_origin))

    def test_the_button_is_stacked(self, viewer):
        assert viewer._btn_set_origin.toolButtonStyle() \
            == Qt.ToolButtonTextUnderIcon

    def test_the_button_is_checkable(self, viewer):
        assert viewer._btn_set_origin.isCheckable()

    def test_the_icon_is_drawn(self):
        icon = _target_icon()
        assert not icon.isNull()
        assert icon.availableSizes()


class TestChoosingByClicking:
    def test_the_button_turns_the_mode_on(self, viewer):
        viewer._btn_set_origin.setChecked(True)
        assert viewer._origin_mode is True
        assert viewer._view._origin_mode is True

    def test_a_click_sets_the_origin(self, viewer, monkeypatch):
        monkeypatch.setattr(viewer, "_redraw", lambda: None)
        viewer._btn_set_origin.setChecked(True)
        # A point of the board, in the coordinates of the scene.
        viewer._on_origin_picked(12.0, -34.0)
        assert viewer._origin_x == pytest.approx(12.0)
        assert viewer._origin_y == pytest.approx(34.0)
        assert viewer._origin_mode is False

    def test_the_mark_moves_to_the_new_origin(self, viewer, monkeypatch):
        monkeypatch.setattr(viewer, "_redraw", lambda: None)
        viewer._origin_x = 12.0
        viewer._origin_y = 34.0
        viewer._update_origin_marker(0.0, False, 0.0, 0.0, False)
        box = viewer._origin_marker.boundingRect()
        assert box.center().x() == pytest.approx(12.0, abs=0.01)
        # The scene has the y downwards.
        assert box.center().y() == pytest.approx(-34.0, abs=0.01)


class TestTheNumbers:
    def test_the_cursor_is_counted_from_the_origin(self, viewer, monkeypatch):
        monkeypatch.setattr(viewer, "_redraw", lambda: None)
        viewer._origin_x = 10.0
        viewer._origin_y = 20.0
        viewer._update_origin_marker(0.0, False, 0.0, 0.0, False)
        viewer._update_coord_label(10.0, -20.0)
        assert "0.00" in viewer._lbl_coord.text()

    def test_the_fields_move_the_origin(self, viewer, monkeypatch):
        monkeypatch.setattr(viewer, "_redraw", lambda: None)
        viewer._spin_goto_x.setValue(5.0)
        viewer._spin_goto_y.setValue(-7.0)
        viewer._on_origin_from_fields()
        # The fields count the y upwards, like the readout does.
        assert viewer._origin_x == pytest.approx(5.0)
        assert viewer._origin_y == pytest.approx(-7.0)

    def test_the_go_button_uses_the_same_system(self, viewer, monkeypatch):
        centred = []
        monkeypatch.setattr(viewer, "_view", type("V", (), {
            "centerOn": lambda self, x, y: centred.append((x, y)),
            "set_origin_mode": lambda self, active: None,
        })())
        monkeypatch.setattr(viewer, "_update_goto_crosshair", lambda: None)
        monkeypatch.setattr(viewer, "_update_magnifier", lambda *a: None)
        viewer._origin_x = 10.0
        viewer._origin_y = 20.0
        viewer._update_origin_marker(0.0, False, 0.0, 0.0, False)
        viewer._spin_goto_x.setValue(3.0)
        viewer._spin_goto_y.setValue(4.0)
        viewer._goto_coord()
        # The point of the fields is counted from the origin; the scene
        # has the y downwards.
        assert centred[-1][0] == pytest.approx(13.0)
        assert centred[-1][1] == pytest.approx(-24.0)


class TestTheSetting:
    def test_the_origin_is_remembered(self, viewer):
        viewer._origin_x = 3.5
        viewer._origin_y = -7.25
        settings = viewer.display_settings()
        assert settings["origin_x"] == pytest.approx(3.5)
        assert settings["origin_y"] == pytest.approx(-7.25)

    def test_the_origin_is_read_back(self, viewer):
        viewer.apply_display_settings({"origin_x": 3.5, "origin_y": -7.25})
        assert viewer._origin_x == pytest.approx(3.5)
        assert viewer._origin_y == pytest.approx(-7.25)

    def test_a_session_without_the_key_keeps_the_origin_of_the_file(self, viewer):
        viewer.apply_display_settings({"crosshair": True})
        assert viewer._origin_x == pytest.approx(0.0)
        assert viewer._origin_y == pytest.approx(0.0)


class TestTheComponentTable:
    """The table keeps the coordinates of the file, always."""

    def test_the_table_shows_the_coordinates_of_the_file(self, viewer):
        from models.review import ReviewRecord

        record = ReviewRecord(designator="R1", mpn="10k", layer="Top",
                               old_x=12.34, old_y=56.78, old_rotation=0.0)
        viewer._records = [record]
        viewer._apply_layer()
        assert viewer._table_components.item(0, 2).text() == "12.340"
        assert viewer._table_components.item(0, 3).text() == "56.780"

    def test_the_table_does_not_change_with_the_origin(self, viewer):
        from models.review import ReviewRecord

        record = ReviewRecord(designator="R1", mpn="10k", layer="Top",
                               old_x=12.34, old_y=56.78, old_rotation=0.0)
        viewer._records = [record]
        viewer._apply_layer()
        before = viewer._table_components.item(0, 2).text()
        viewer._origin_x = 5.0
        viewer._origin_y = 7.0
        viewer._apply_layer()
        assert viewer._table_components.item(0, 2).text() == before
        assert viewer._table_components.item(0, 3).text() == "56.780"

    def test_the_menu_does_not_change_with_the_origin(self, viewer):
        from models.review import ReviewRecord

        record = ReviewRecord(designator="R1", mpn="10k", layer="Top",
                               old_x=12.34, old_y=56.78, old_rotation=0.0)
        viewer._origin_x = 100.0
        viewer._origin_y = 200.0
        info = viewer._component_info_text(record)
        assert "X: 12.340" in info
        assert "Y: 56.780" in info

    def test_the_record_keeps_the_coordinates_of_the_file(self, viewer):
        from models.review import ReviewRecord

        record = ReviewRecord(designator="R1", mpn="10k", layer="Top",
                               old_x=12.34, old_y=56.78, old_rotation=0.0)
        viewer._records = [record]
        viewer._origin_x = 100.0
        viewer._origin_y = 200.0
        viewer._apply_layer()
        # The data of the review is untouched.
        assert record.old_x == pytest.approx(12.34)
        assert record.old_y == pytest.approx(56.78)


class TestTheTwoSystems:
    """The readout shows the origin and the file, the table shows the origin."""

    def _viewer_with_record(self, app):
        from models.review import ReviewRecord

        v = _NoopGerberViewer([], _layers())
        v._layer_data = [RenderData() for _ in v._layers]
        v._records = [ReviewRecord(designator="R1", mpn="10k", layer="Top",
                                   old_x=10.0, old_y=20.0, old_rotation=0.0)]
        v._loaded = True
        v._board_center = (0.0, 0.0)
        v._redraw()
        v._apply_layer()
        return v

    def test_the_readout_shows_both_systems(self, app):
        v = self._viewer_with_record(app)
        v._update_coord_label(10.0, -20.0)
        text = v._lbl_coord.text()
        # The origin counts: 10 - 0, 20 - 0.
        assert "X: 10.00" in text
        assert "Y: 20.00" in text
        # The file: 10.00 / 20.00.
        assert "(10.00 / 20.00)" in text

    def test_the_file_numbers_are_the_ones_of_the_table(self, app):
        v = self._viewer_with_record(app)
        v._origin_x, v._origin_y = 5.0, 5.0
        v._redraw()
        v._apply_layer()
        v._update_coord_label(10.0, -20.0)
        text = v._lbl_coord.text()
        # The origin counts: 10 - 5, 20 - 5.
        assert "X: 5.00" in text
        assert "Y: 15.00" in text
        # The file does not move.
        assert "(10.00 / 20.00)" in text
        # The table keeps the coordinates of the file, so the numbers in
        # the brackets can be checked against it.
        assert v._table_components.item(0, 2).text() == "10.000"
        assert v._table_components.item(0, 3).text() == "20.000"

    def test_the_origin_reads_zero(self, app):
        v = self._viewer_with_record(app)
        v._origin_x, v._origin_y = 5.0, 5.0
        v._redraw()
        v._update_coord_label(5.0, -5.0)
        assert "X: 0.00  Y: 0.00" in v._lbl_coord.text()

    def test_the_markers_follow_the_origin(self, app):
        # The origin is where the board counts from, so the parts of the
        # Pick&Place stand on the board and follow it.
        v = self._viewer_with_record(app)
        before = list(v._marker_tuples())
        v._origin_x, v._origin_y = 5.0, 5.0
        v._redraw()
        after = list(v._marker_tuples())
        assert after[0][0] == pytest.approx(before[0][0] + 5.0)
        assert after[0][1] == pytest.approx(before[0][1] - 5.0)

    def test_the_markers_do_not_follow_the_turn_of_the_page(self, app):
        # The Gerber is turned to come to the parts, so the parts stay.
        v = self._viewer_with_record(app)
        before = list(v._marker_tuples())
        v._set_rotation(90, emit=False)
        v._redraw()
        assert list(v._marker_tuples()) == before

    def test_the_menu_shows_the_coordinates_of_the_file(self, app):
        v = self._viewer_with_record(app)
        v._origin_x, v._origin_y = 5.0, 5.0
        info = v._component_info_text(v._records[0])
        assert "X: 10.000" in info
        assert "Y: 20.000" in info

    def test_the_go_button_jumps_to_the_point_of_the_fields(self, app):
        centred = []
        v = self._viewer_with_record(app)
        v._view.centerOn = lambda x, y: centred.append((x, y))
        v._origin_x, v._origin_y = 5.0, 5.0
        v._spin_goto_x.setValue(3.0)
        v._spin_goto_y.setValue(4.0)
        v._goto_coord()
        # The fields count from the origin: the point of the file is
        # origin + (3, 4).
        assert centred[-1][0] == pytest.approx(8.0)
        assert centred[-1][1] == pytest.approx(-9.0)

    def test_the_fields_move_the_origin(self, app):
        v = self._viewer_with_record(app)
        v._origin_x, v._origin_y = 5.0, 5.0
        v._spin_goto_x.setValue(-5.0)
        v._spin_goto_y.setValue(-7.0)
        v._on_origin_from_fields()
        # The fields count from the origin, so the origin moves by that.
        assert v._origin_x == pytest.approx(0.0)
        assert v._origin_y == pytest.approx(-2.0)


class TestTheMarkAtTheOrigin:
    """The mark stands where the operator put it, and it reads 0,00."""

    def _viewer(self, app, rotation=0):
        v = _NoopGerberViewer([], _layers())
        v._layer_data = [RenderData() for _ in v._layers]
        v._loaded = True
        v._board_center = (0.0, 0.0)
        v._set_rotation(rotation * 90, emit=False)
        v._redraw()
        return v

    def _pick(self, viewer, sx, sy):
        viewer._on_origin_picked(sx, sy)
        box = viewer._origin_marker.boundingRect()
        return box.center()

    def test_the_mark_stands_where_the_point_was_clicked(self, app):
        v = self._viewer(app)
        centre = self._pick(v, 40.0, -20.0)
        assert centre.x() == pytest.approx(40.0, abs=0.01)
        assert centre.y() == pytest.approx(-20.0, abs=0.01)

    def test_the_mark_reads_zero(self, app):
        v = self._viewer(app)
        self._pick(v, 40.0, -20.0)
        v._update_coord_label(40.0, -20.0)
        assert "X: 0.00  Y: 0.00" in v._lbl_coord.text()

    def test_the_mark_reads_zero_when_the_board_is_turned(self, app):
        v = self._viewer(app, rotation=1)
        self._pick(v, 40.0, -20.0)
        v._update_coord_label(40.0, -20.0)
        assert "X: 0.00  Y: 0.00" in v._lbl_coord.text()

    def test_the_go_button_jumps_to_the_mark(self, app):
        centred = []
        v = self._viewer(app)
        v._view.centerOn = lambda x, y: centred.append((x, y))
        self._pick(v, 40.0, -20.0)
        v._spin_goto_x.setValue(0.0)
        v._spin_goto_y.setValue(0.0)
        v._goto_coord()
        assert centred[-1][0] == pytest.approx(40.0)
        assert centred[-1][1] == pytest.approx(-20.0)

    def test_the_origin_moves_with_the_fields(self, app):
        v = self._viewer(app)
        self._pick(v, 40.0, -20.0)
        v._spin_goto_x.setValue(5.0)
        v._spin_goto_y.setValue(-3.0)
        v._on_origin_from_fields()
        centre = v._origin_marker.boundingRect().center()
        assert centre.x() == pytest.approx(45.0, abs=0.01)
        assert centre.y() == pytest.approx(-17.0, abs=0.01)
        v._update_coord_label(45.0, -17.0)
        assert "X: 0.00  Y: 0.00" in v._lbl_coord.text()


class TestTheMarksOnTheBoard:
    """The origin is the point of the Gerber that stands for the (0,0)."""

    def _viewer(self, app):
        from models.review import ReviewRecord

        v = _NoopGerberViewer([], _layers())
        v._layer_data = [RenderData() for _ in v._layers]
        v._records = [ReviewRecord(designator="R1", mpn="10k", layer="Top",
                                   old_x=10.0, old_y=20.0, old_rotation=0.0)]
        v._loaded = True
        v._board_center = (0.0, 0.0)
        v._redraw()
        v._apply_layer()
        return v

    def test_the_mark_stands_on_the_pad_when_the_origin_is_the_corner(self, app):
        # The board corner lies at (100, 50) of the file; the part R1 is
        # 10 mm to the right and 20 mm up of it, so its pad lies at
        # (110, 70).
        v = self._viewer(app)
        v._origin_x, v._origin_y = 100.0, 50.0
        v._redraw()
        marker = v._marker_tuples()[0]
        assert marker[0] == pytest.approx(110.0)
        assert marker[1] == pytest.approx(-70.0)

    def test_the_coordinates_read_at_the_mark_are_the_ones_of_the_table(self, app):
        v = self._viewer(app)
        v._origin_x, v._origin_y = 100.0, 50.0
        v._redraw()
        marker = v._marker_tuples()[0]
        v._update_coord_label(marker[0], marker[1])
        text = v._lbl_coord.text()
        # The origin counts: (110 - 100, 70 - 50) = (10, 20), the same
        # numbers the table shows.
        assert "X: 10.00" in text
        assert "Y: 20.00" in text
        assert v._table_components.item(0, 2).text() == "10.000"
        assert v._table_components.item(0, 3).text() == "20.000"


class TestTheMagnifier:
    """The magnifier looks at the mark, not at the old place."""

    def _viewer(self, app):
        from models.review import ReviewRecord

        v = _NoopGerberViewer([], _layers())
        v._layer_data = [RenderData() for _ in v._layers]
        v._records = [ReviewRecord(designator="R1", mpn="10k", layer="Top",
                                   old_x=10.0, old_y=20.0, old_rotation=0.0)]
        v._loaded = True
        v._board_center = (0.0, 0.0)
        v._redraw()
        v._apply_layer()
        v._origin_x, v._origin_y = 100.0, 50.0
        v._redraw()
        v._apply_layer()
        return v

    def test_a_double_click_looks_at_the_mark(self, app):
        v = self._viewer(app)
        marker = v._marker_tuples()[0]
        v._on_component_double_clicked(0, 0)
        assert v._mag_target[0] == pytest.approx(marker[0])
        assert v._mag_target[1] == pytest.approx(marker[1])

    def test_the_chosen_mark_is_looked_at(self, app):
        v = self._viewer(app)
        marker = v._marker_tuples()[0]
        v._selected_marker_index = 0
        v._selected_marker_indices = {0}
        v._restore_highlight()
        v._on_row_changed(0, 0, 0, 0)
        assert v._mag_target[0] == pytest.approx(marker[0])
        assert v._mag_target[1] == pytest.approx(marker[1])

    def test_the_rotation_dialog_locks_on_the_mark(self, app):
        v = self._viewer(app)
        marker = v._marker_tuples()[0]
        v._edit_rotation_for_row(0)
        assert v._rotation_lock_xy[0] == pytest.approx(marker[0])
        assert v._rotation_lock_xy[1] == pytest.approx(marker[1])
        # The dialog must not be left open after the test.
        if v._rotation_dialog is not None:
            v._rotation_dialog.close()
            v._rotation_dialog = None
        v._rotation_lock_xy = None

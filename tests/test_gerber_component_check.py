import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtCore import QRectF, QObject, Signal
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from models.review import ReviewRecord
from services.gerber.gerber_render import LineShape, RenderData
from ui.gerber_viewer import GerberViewer, MarkerOverlayItem, _ROT_EDIT_MAG_FACTOR


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


def _make_records():
    return [
        ReviewRecord(designator="C1", mpn="M1", layer="Top", old_x=10.0, old_y=20.0, old_rotation=0),
        ReviewRecord(designator="R1", mpn="M2", layer="Top", old_x=30.0, old_y=40.0, old_rotation=90),
        ReviewRecord(designator="C2", mpn="M3", layer="Bottom", old_x=50.0, old_y=60.0, old_rotation=0),
    ]


@pytest.fixture()
def viewer(app):
    v = _NoopGerberViewer(_make_records(), r"C:\nonexistent.gko")
    v._outline = RenderData(lines=[LineShape(x1=0.0, y1=0.0, x2=100.0, y2=100.0)])
    v._loaded = True
    v.show()
    v._redraw()  # Build initial scene including pickplace overlay
    return v


def _enable_grid(viewer):
    viewer._grid_available = True
    viewer._chk_grid.setChecked(True)


def _enable_pickplace(viewer):
    _enable_grid(viewer)
    viewer._chk_pickplace.setChecked(True)


class _FakeMsgBox:
    Yes = QMessageBox.Yes
    No = QMessageBox.No
    answer = QMessageBox.Yes
    last_text = ""

    @staticmethod
    def question(*args, **kwargs):
        _FakeMsgBox.last_text = args[2] if len(args) > 2 else kwargs.get("text", "")
        return _FakeMsgBox.answer


def test_component_table_has_status_column(viewer):
    headers = [viewer._table_components.horizontalHeaderItem(c).text()
               for c in range(viewer._table_components.columnCount())]
    assert "Status" in headers
    assert viewer._table_components.columnCount() == 6


def test_grouped_table_has_status_column(viewer):
    viewer._chk_group_mpn.setChecked(True)
    headers = [viewer._table_components.horizontalHeaderItem(c).text()
               for c in range(viewer._table_components.columnCount())]
    assert "Status" in headers
    assert viewer._table_components.columnCount() == 5


def test_status_icon_initial_unchecked(viewer):
    _enable_grid(viewer)
    status_item = viewer._table_components.item(0, viewer._table_components.columnCount() - 1)
    assert status_item is not None
    assert status_item.icon().isNull() is False
    assert viewer._records[0].checked is False


def test_status_icon_cached(viewer):
    assert GerberViewer._status_icon(True) is GerberViewer._status_icon(True)
    assert GerberViewer._status_icon(False) is GerberViewer._status_icon(False)
    assert GerberViewer._status_icon(True) is not GerberViewer._status_icon(False)


def test_status_row_update_targeted(viewer, monkeypatch):
    _enable_grid(viewer)
    monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
    _FakeMsgBox.answer = QMessageBox.Yes
    viewer._on_mag_clicked(10.0, -20.0)
    col = viewer._table_components.columnCount() - 1
    assert viewer._records[0].checked is True
    assert viewer._records[1].checked is False
    assert viewer._table_components.item(0, col).icon().cacheKey() == GerberViewer._status_icon(True).cacheKey()
    assert viewer._table_components.item(1, col).icon().cacheKey() == GerberViewer._status_icon(False).cacheKey()


def test_confirm_component_marks_checked(viewer, monkeypatch):
    _enable_grid(viewer)
    monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
    _FakeMsgBox.answer = QMessageBox.Yes
    emitted = []
    viewer.checked_changed.connect(emitted.append)
    viewer._on_mag_clicked(10.0, -20.0)
    assert viewer._records[0].checked is True
    assert emitted == [0]
    status_item = viewer._table_components.item(0, viewer._table_components.columnCount() - 1)
    assert status_item is not None and status_item.icon().isNull() is False


def test_confirm_declined_keeps_unchecked(viewer, monkeypatch):
    _enable_grid(viewer)
    monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
    _FakeMsgBox.answer = QMessageBox.No
    viewer._on_mag_clicked(10.0, -20.0)
    assert viewer._records[0].checked is False


def test_recheck_undoes_check(viewer, monkeypatch):
    _enable_grid(viewer)
    monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
    _FakeMsgBox.answer = QMessageBox.Yes
    viewer._on_mag_clicked(10.0, -20.0)
    assert viewer._records[0].checked is True
    viewer._on_mag_clicked(10.0, -20.0)
    assert viewer._records[0].checked is False


def test_undo_declined_keeps_checked(viewer, monkeypatch):
    _enable_grid(viewer)
    monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
    _FakeMsgBox.answer = QMessageBox.Yes
    viewer._on_mag_clicked(10.0, -20.0)
    assert viewer._records[0].checked is True
    _FakeMsgBox.answer = QMessageBox.No
    viewer._on_mag_clicked(10.0, -20.0)
    assert viewer._records[0].checked is True


def test_mag_click_ignored_when_grid_off(viewer, monkeypatch):
    monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
    _FakeMsgBox.answer = QMessageBox.Yes
    viewer._on_mag_clicked(10.0, -20.0)
    assert viewer._records[0].checked is False


def test_mag_click_miss_outside_tolerance(viewer, monkeypatch):
    _enable_grid(viewer)
    monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
    _FakeMsgBox.answer = QMessageBox.Yes
    viewer._on_mag_clicked(99.0, -99.0)
    assert viewer._records[0].checked is False
    assert viewer._records[1].checked is False


def test_bottom_layer_uses_separate_check_state(viewer, monkeypatch):
    _enable_grid(viewer)
    monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
    _FakeMsgBox.answer = QMessageBox.Yes
    viewer._combo_layer.setCurrentIndex(1)
    viewer._on_mag_clicked(50.0, -60.0)
    assert viewer._records[2].checked is True
    assert viewer._records[0].checked is False


def test_confirm_dialog_shows_component_info(viewer, monkeypatch):
    _enable_grid(viewer)
    monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
    _FakeMsgBox.answer = QMessageBox.Yes
    viewer._records[0].remark = "check pad area"
    _FakeMsgBox.last_text = ""
    viewer._on_mag_clicked(10.0, -20.0)
    assert "C1" in _FakeMsgBox.last_text
    assert "M1" in _FakeMsgBox.last_text
    assert "check pad area" in _FakeMsgBox.last_text
    assert viewer._records[0].checked is True


def test_undo_dialog_shows_component_info(viewer, monkeypatch):
    _enable_grid(viewer)
    monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
    _FakeMsgBox.answer = QMessageBox.Yes
    viewer._on_mag_clicked(10.0, -20.0)
    assert viewer._records[0].checked is True
    _FakeMsgBox.last_text = ""
    viewer._on_mag_clicked(10.0, -20.0)
    assert "C1" in _FakeMsgBox.last_text
    assert "M1" in _FakeMsgBox.last_text
    assert viewer._records[0].checked is False


def test_overlay_checked_indices():
    overlay = MarkerOverlayItem(
        [(0.0, 0.0, 0.0, 1.0), (5.0, 5.0, 0.0, 1.0)],
        checked_indices={1},
    )
    assert overlay._checked_indices == {1}
    overlay.set_checked_indices({0, 1})
    assert overlay._checked_indices == {0, 1}


def test_refresh_records_rebuilds_component_table(viewer):
    _enable_grid(viewer)
    records = viewer._records[:2]
    viewer.refresh_records(records)
    assert viewer._records is records
    assert viewer._table_components.rowCount() == 2
    assert viewer._table_components.item(1, 1).text() == "R1"
    scene_items = [it for it in viewer._scene.items() if isinstance(it, MarkerOverlayItem)]
    assert len(scene_items) == 1
    assert len(scene_items[0]._markers) == 2


def test_refresh_records_clamps_stale_selection(viewer):
    _enable_grid(viewer)
    viewer._selected_marker_index = 1
    viewer._selected_marker_indices = {0, 1}
    viewer.refresh_records(viewer._records[:1])
    assert viewer._selected_marker_index == -1
    assert all(i < len(viewer._current_layer_records()) for i in viewer._selected_marker_indices)


def test_refresh_records_keeps_rendered_layers(viewer):
    _enable_grid(viewer)
    viewer._chk_outline.setChecked(True)
    viewer._redraw()
    outline_before = list(viewer._line_items.get("outline", []))
    assert outline_before
    viewer.refresh_records(viewer._records[:2])
    assert viewer._line_items.get("outline") == outline_before
    overlays = [it for it in viewer._scene.items() if isinstance(it, MarkerOverlayItem)]
    assert len(overlays) == 1
    assert len(overlays[0]._markers) == 2


class _FakeRotDialog(QObject):
    accepted = Signal()
    finished = Signal()
    instances = []
    value = 90.0
    ic = False

    def __init__(self, record, *args, **kwargs):
        super().__init__()
        self.record = record
        self.kwargs = kwargs
        type(self).instances.append(self)

    def show(self):
        # For tests, directly emit accepted to simulate user clicking OK
        self.accepted.emit()

    def new_rotation(self):
        return type(self).value

    def is_ic_mode(self):
        return type(self).ic

    def close(self):
        self.finished.emit()


def _patch_rot_dialog(monkeypatch):
    _FakeRotDialog.instances = []
    monkeypatch.setattr("ui.gerber_viewer.RotationEditDialog", _FakeRotDialog)


def test_edit_rotation_for_row_applies_and_emits(viewer, monkeypatch):
    _enable_grid(viewer)
    _patch_rot_dialog(monkeypatch)
    _FakeRotDialog.value = 90.0
    emitted = []
    viewer.rotation_edited.connect(emitted.append)
    viewer._edit_rotation_for_row(0)
    rec = viewer._records[0]
    assert rec.new_rotation == 90.0
    assert rec.status == "Edited"
    assert rec.review_time
    assert emitted == [0]
    assert viewer._table_components.item(0, 4).text() == "90°"
    assert viewer._overlay is not None
    assert abs(viewer._overlay._markers[0][2] - 90.0) < 1e-6


def test_edit_rotation_cancelled_keeps_record(viewer, monkeypatch):
    _enable_grid(viewer)
    _patch_rot_dialog(monkeypatch)
    # Simulate user clicking Cancel by not emitting accepted, only finished
    original_show = _FakeRotDialog.show

    def show_cancel(self):
        self.finished.emit()

    monkeypatch.setattr(_FakeRotDialog, "show", show_cancel)
    emitted = []
    viewer.rotation_edited.connect(emitted.append)
    viewer._edit_rotation_for_row(0)
    assert viewer._records[0].new_rotation is None
    assert viewer._records[0].status != "Edited"
    assert emitted == []


def test_edit_rotation_same_value_no_signal(viewer, monkeypatch):
    _enable_grid(viewer)
    _patch_rot_dialog(monkeypatch)
    _FakeRotDialog.value = float(_make_records()[0].old_rotation)
    emitted = []
    viewer.rotation_edited.connect(emitted.append)
    viewer._edit_rotation_for_row(0)
    assert emitted == []
    assert viewer._records[0].status != "Edited"


def test_show_rotation_preview_updates_correct_marker(viewer):
    _enable_pickplace(viewer)
    viewer.show_rotation_preview(0, 45.0)
    assert viewer._overlay is not None
    assert abs(viewer._overlay._markers[0][2] - 45.0) < 1e-6
    # Other markers unchanged
    assert abs(viewer._overlay._markers[1][2] - 90.0) < 1e-6


def test_clear_rotation_preview_restores_original(viewer):
    _enable_pickplace(viewer)
    viewer.show_rotation_preview(0, 45.0)
    assert abs(viewer._overlay._markers[0][2] - 45.0) < 1e-6
    viewer.clear_rotation_preview()
    assert abs(viewer._overlay._markers[0][2] - 0.0) < 1e-6


def test_rebuild_marker_overlay_preserves_preview(viewer):
    _enable_pickplace(viewer)
    viewer.show_rotation_preview(1, 180.0)
    assert abs(viewer._overlay._markers[1][2] - 180.0) < 1e-6
    # Trigger rebuild (e.g., toggle crosshair)
    viewer._chk_crosshair.setChecked(False)
    viewer._chk_crosshair.setChecked(True)
    assert abs(viewer._overlay._markers[1][2] - 180.0) < 1e-6


def test_show_rotation_preview_handles_dead_overlay(viewer):
    _enable_pickplace(viewer)
    viewer.show_rotation_preview(0, 45.0)
    # Simulate overlay being deleted externally
    viewer._overlay = None
    # Should not raise
    viewer.show_rotation_preview(0, 90.0)
    viewer.clear_rotation_preview()


def test_reload_records_reflects_external_changes(viewer):
    """Viewer shares the record list; Reload re-reads it after edits."""
    _enable_pickplace(viewer)
    assert len(viewer._current_layer_records()) == 2
    # Main window edits: rotate C1 and delete R1 (same live list object)
    viewer._records[0].new_rotation = 135.0
    removed = viewer._records.pop(1)
    assert viewer._records[0] is not removed
    viewer._on_reload_records()
    # Table now has one row with the new rotation
    table = viewer._table_components
    assert table.rowCount() == 1
    assert table.item(0, 4).text() == "135°"
    # Marker overlay rebuilt for the single remaining component
    assert viewer._overlay is not None
    assert len(viewer._overlay._markers) == 1
    assert abs(viewer._overlay._markers[0][2] - 135.0) < 1e-6


def test_reload_clears_stale_rotation_preview(viewer):
    _enable_pickplace(viewer)
    viewer.show_rotation_preview(0, 45.0)
    assert abs(viewer._overlay._markers[0][2] - 45.0) < 1e-6
    viewer._records[0].new_rotation = 200.0
    viewer._on_reload_records()
    assert viewer._rotation_preview is None
    assert abs(viewer._overlay._markers[0][2] - 200.0) < 1e-6


def test_edit_rotation_boosts_magnifier_zoom(viewer, monkeypatch):
    """Opening Edit Rotation should boost magnifier zoom and lock on component."""
    _enable_pickplace(viewer)
    original_factor = viewer._mag_factor

    class _FakeDialog(QObject):
        accepted = Signal()
        finished = Signal()

        def __init__(self, record, *args, **kwargs):
            super().__init__()
            self.record = record
            self.preview_cb = kwargs.get("preview_cb")

        def show(self):
            # Emit immediately to avoid timer issues after test cleanup
            self.accepted.emit()

        def new_rotation(self):
            return 45.0

    monkeypatch.setattr("ui.gerber_viewer.RotationEditDialog", _FakeDialog)

    # Open edit rotation for row 0
    viewer._edit_rotation_for_row(0)

    # Check zoom was boosted
    assert viewer._mag_factor == _ROT_EDIT_MAG_FACTOR
    assert viewer._rot_mag_saved == original_factor
    assert viewer._rotation_lock_xy is not None
    assert viewer._mag_target == viewer._rotation_lock_xy

    # Close the fake dialog (simulate finished)
    viewer._on_rotation_edit_closed()

    # Check zoom restored
    assert viewer._mag_factor == original_factor
    assert viewer._rot_mag_saved is None
    assert viewer._rotation_lock_xy is None


def test_magnifier_lock_ignores_cursor_moves_during_edit(viewer, monkeypatch):
    """While editing rotation, _update_magnifier should ignore cursor moves."""
    _enable_pickplace(viewer)

    class _FakeDialog(QObject):
        accepted = Signal()
        finished = Signal()

        def __init__(self, record, *args, **kwargs):
            super().__init__()
            self.preview_cb = kwargs.get("preview_cb")

        def show(self):
            pass

        def new_rotation(self):
            return 45.0

    monkeypatch.setattr("ui.gerber_viewer.RotationEditDialog", _FakeDialog)
    viewer._edit_rotation_for_row(0)

    # Try to move magnifier elsewhere
    old_target = viewer._mag_target
    viewer._update_magnifier(999.0, -999.0)
    # Target should stay locked on component
    assert viewer._mag_target == old_target

    viewer._on_rotation_edit_closed()
    # After close, cursor moves should work again (ensure grid is off)
    viewer._grid_active = False
    viewer._update_magnifier(100.0, -200.0)
    assert viewer._mag_target == (100.0, -200.0)


def test_magnifier_uses_factor_zoom_during_edit_even_with_grid_on(viewer, monkeypatch):
    """With Grid ON, refresh should use factor zoom (not cell-fit) while editing."""
    _enable_pickplace(viewer)
    viewer._grid_active = True
    viewer._mag_cell_rect = QRectF(0, 0, 10, 10)  # pretend grid cell rect is set

    class _FakeDialog(QObject):
        accepted = Signal()
        finished = Signal()

        def __init__(self, record, *args, **kwargs):
            super().__init__()
            self.preview_cb = kwargs.get("preview_cb")

        def show(self):
            pass

        def new_rotation(self):
            return 45.0

    monkeypatch.setattr("ui.gerber_viewer.RotationEditDialog", _FakeDialog)
    viewer._edit_rotation_for_row(0)

    # Refresh should use factor path, not cell-fit
    viewer._refresh_magnifier()
    # If cell-fit was used, transform would be affine scale+translate; factor path uses uniform scale
    # Check by verifying _mag_view.transform is uniform scale
    t = viewer._mag_view.transform()
    assert abs(t.m11() - t.m22()) < 1e-6  # uniform scale
    assert abs(t.m12()) < 1e-6 and abs(t.m21()) < 1e-6  # no shear/rotation

    viewer._on_rotation_edit_closed()


# ---------------------------------------------------------------------------
# IC rotation convention: markers draw at (rot + 45) for flagged records and
# the flag is persisted through the edit-rotation commit path.
# ---------------------------------------------------------------------------

def test_marker_tuples_offset_ic_records(viewer):
    _enable_pickplace(viewer)
    recs = viewer._current_layer_records()
    assert len(recs) >= 2
    recs[0].is_ic_rotation = True
    recs[0].new_rotation = 270.0
    markers = viewer._marker_tuples()
    # IC record draws at 270+45=315; normal record keeps its own value
    assert abs(markers[0][2] - 315.0) < 1e-6
    assert abs(markers[1][2] - 90.0) < 1e-6
    # Live preview override still wins over the IC offset
    viewer.show_rotation_preview(0, 10.0)
    assert abs(viewer._overlay._markers[0][2] - 10.0) < 1e-6
    viewer.clear_rotation_preview()


def test_edit_commit_ic_persists_flag_and_direction(viewer, monkeypatch):
    _enable_pickplace(viewer)
    _patch_rot_dialog(monkeypatch)
    _FakeRotDialog.value = 270.0
    _FakeRotDialog.ic = True
    viewer._edit_rotation_for_row(0)
    rec = viewer._records[0]
    assert rec.is_ic_rotation is True
    assert rec.new_rotation == 270.0
    # Overlay arrow now sits at the IC needle bearing: 270+45 = 315
    assert abs(viewer._overlay._markers[0][2] - 315.0) < 1e-6


def test_edit_commit_normal_clears_flag(viewer, monkeypatch):
    _enable_pickplace(viewer)
    viewer._records[0].is_ic_rotation = True
    _patch_rot_dialog(monkeypatch)
    _FakeRotDialog.value = 45.0
    _FakeRotDialog.ic = False
    viewer._edit_rotation_for_row(0)
    rec = viewer._records[0]
    assert rec.is_ic_rotation is False
    assert abs(viewer._overlay._markers[0][2] - 45.0) < 1e-6


def test_edit_same_value_mode_switch_still_marks_edited(viewer, monkeypatch):
    """Switching convention with an unchanged number is a real edit."""
    _enable_pickplace(viewer)
    viewer._records[0].new_rotation = 90.0   # current effective value
    _patch_rot_dialog(monkeypatch)
    _FakeRotDialog.value = 90.0              # same number...
    _FakeRotDialog.ic = True                 # ...but now interpreted as IC
    emitted = []
    viewer.rotation_edited.connect(emitted.append)
    viewer._edit_rotation_for_row(0)
    rec = viewer._records[0]
    assert rec.is_ic_rotation is True
    assert rec.status == "Edited"
    assert emitted == [viewer._record_index_in_records(rec)]
    assert abs(viewer._overlay._markers[0][2] - 135.0) < 1e-6
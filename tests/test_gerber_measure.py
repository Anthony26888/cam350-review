import pytest

from services.gerber.gerber_transform import (
    apply_inverse_transform,
    apply_transform,
)

pytest.importorskip("PySide6")
import os  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QMouseEvent, QPen, QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from ui.gerber_viewer import GerberView, GerberViewer, MeasurementItem, PadGrid
from services.gerber.gerber_render import FlashShape, RenderData  # noqa: E402
from models.review import ReviewRecord  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_view() -> GerberView:
    view = GerberView()
    scene = QGraphicsScene(view)
    scene.addRect(0.0, 0.0, 2000.0, 2000.0)
    view.setScene(scene)
    view.resize(400, 300)
    view.show()
    view.viewport().grab()
    return view


def _mouse(view, kind, x, y, button=Qt.MouseButton.LeftButton):
    return QMouseEvent(
        kind, QPointF(x, y), button, button,
        Qt.KeyboardModifier.NoModifier,
    )


@pytest.mark.parametrize("angle", [0, 90, 180, 270, 45, 359])
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("mirror_x", [False, True])
def test_inverse_transform_roundtrip(angle, mirror, mirror_x):
    cx, cy, ox, oy = 12.5, -7.0, 100.0, -80.0
    pts = [(0.0, 0.0), (10.5, 20.25), (-5.0, 3.75), (123.456, -0.001)]
    for x, y in pts:
        tx, ty = apply_transform(x, y, mirror, angle, ox, oy, cx, cy, mirror_x)
        rx, ry = apply_inverse_transform(
            tx, ty, mirror, angle, ox, oy, cx, cy, mirror_x,
        )
        assert rx == pytest.approx(x, abs=1e-9)
        assert ry == pytest.approx(y, abs=1e-9)


def test_measurement_item_render(qapp):
    view = _make_view()
    item = MeasurementItem(
        QPointF(100.0, 100.0), QPointF(250.0, 160.0), 160.0, QColor("#38BDF8"),
    )
    view.scene().addItem(item)
    view.scene().invalidate()
    view.viewport().grab()          # exercises paint()
    assert item.boundingRect().contains(QPointF(100.0, 100.0))
    assert item.boundingRect().contains(QPointF(250.0, 160.0))
    assert item.zValue() == 80


def test_measure_mode_click_emits_points(qapp):
    view = _make_view()
    seen = []
    view.measure_clicked.connect(lambda x, y: seen.append((x, y)))
    view.set_measure_mode(True)
    view.mousePressEvent(_mouse(view, QMouseEvent.Type.MouseButtonPress, 50, 60))
    expected = view.mapToScene(QPoint(50, 60))
    assert seen == [(expected.x(), expected.y())]
    # drag-mode must be disabled so pressing does not start a pan
    assert view._pan_pixmap is None
    assert view._measure_mode is True


def test_measure_mode_right_click_cancels(qapp):
    view = _make_view()
    cancelled = []
    view.measure_cancel.connect(lambda: cancelled.append(True))
    view.set_measure_mode(True)
    view.mousePressEvent(_mouse(
        view, QMouseEvent.Type.MouseButtonPress, 50, 60,
        button=Qt.MouseButton.RightButton,
    ))
    assert cancelled == [True]


def test_measure_mode_esc_cancels(qapp):
    from PySide6.QtGui import QKeyEvent
    view = _make_view()
    cancelled = []
    view.measure_cancel.connect(lambda: cancelled.append(True))
    view.set_measure_mode(True)
    ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Escape,
                   Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(ev)
    assert cancelled == [True]


def test_measure_mode_toggle_drag_mode(qapp):
    view = _make_view()
    view.set_measure_mode(True)
    assert view.dragMode() == view.DragMode.NoDrag
    view.set_measure_mode(False)
    assert view.dragMode() == view.DragMode.ScrollHandDrag


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


def _make_viewer():
    viewer = _NoopGerberViewer([], r"C:\nonexistent.gko")
    viewer._top = RenderData(flashes=[
        FlashShape(cx=50.0, cy=60.0, kind="circle", w=1.0, h=1.0),
        FlashShape(cx=120.0, cy=-30.0, kind="circle", w=1.0, h=1.0),
    ])
    viewer._pad_grid_cache = {}
    viewer._loaded = True
    return viewer


def test_pad_grid_nearest_point_hits():
    grid = PadGrid([(10.0, 20.0, 1.0), (30.0, 40.0, 0.5)])
    assert grid.nearest_point(10.4, 20.3) == (10.0, 20.0, 1.0)
    assert grid.nearest_point(15.0, 15.0) is None


def test_pad_grid_nearest_point_respects_tol():
    grid = PadGrid([(10.0, 20.0, 0.5)])
    assert grid.nearest_point(11.2, 20.0, tol=1.0) is None
    assert grid.nearest_point(11.2, 20.0, tol=1.3) == (10.0, 20.0, 0.5)


def test_pad_grid_nearest_still_returns_size():
    grid = PadGrid([(10.0, 20.0, 1.5)])
    assert grid.nearest(10.8, 20.0) == 1.5


def test_snap_gerber_hits_pad(qapp):
    viewer = _make_viewer()
    assert viewer._snap_gerber(50.4, 60.3) == (50.0, 60.0)


def test_snap_gerber_keeps_raw_when_far(qapp):
    viewer = _make_viewer()
    assert viewer._snap_gerber(5.0, 5.0) == (5.0, 5.0)


def test_snap_gerber_disabled_keeps_raw(qapp):
    viewer = _make_viewer()
    viewer._snap_enabled = False
    assert viewer._snap_gerber(50.4, 60.3) == (50.4, 60.3)


def test_measure_click_snaps_start_point(qapp):
    viewer = _make_viewer()
    viewer._measure_mode = True
    viewer._on_measure_clicked(50.5, -60.4)      # near pad (50,60) -> snaps
    viewer._on_measure_clicked(10.0, -10.0)      # far from any pad -> raw
    assert viewer._measurements == [(50.0, 60.0, 10.0, 10.0)]


def test_measure_click_snap_disabled_uses_raw(qapp):
    viewer = _make_viewer()
    viewer._snap_enabled = False
    viewer._measure_mode = True
    viewer._on_measure_clicked(50.5, -60.4)
    viewer._on_measure_clicked(10.0, -10.0)
    assert viewer._measurements == [(50.5, 60.4, 10.0, 10.0)]


def test_measure_move_creates_snap_indicator(qapp):
    viewer = _make_viewer()
    viewer._measure_mode = True
    viewer._measure_start = (50.0, 60.0)
    viewer._on_measure_move(50.6, -60.3)
    assert viewer._measure_snap_item is not None
    assert viewer._measure_preview is not None
    c = viewer._measure_snap_item.rect().center()
    assert c.x() == pytest.approx(50.0)
    assert c.y() == pytest.approx(-60.0)
    viewer._on_measure_cancel()
    assert viewer._measure_snap_item is None
    assert viewer._measure_preview is None


def test_measure_move_no_snap_no_indicator(qapp):
    viewer = _make_viewer()
    viewer._measure_mode = True
    viewer._measure_start = (50.0, 60.0)
    viewer._on_measure_move(5.0, -5.0)
    assert viewer._measure_snap_item is None
    assert viewer._measure_preview is not None


def test_snap_toggle_removes_indicator(qapp):
    viewer = _make_viewer()
    viewer._measure_mode = True
    viewer._measure_start = (50.0, 60.0)
    viewer._on_measure_move(50.6, -60.3)
    assert viewer._measure_snap_item is not None
    viewer._on_snap_toggled(False)
    assert viewer._measure_snap_item is None
    assert viewer._snap_enabled is False
    assert viewer._snap_gerber(50.4, 60.3) == (50.4, 60.3)


def test_enabled_snap_tolerance_spinbox_value(qapp):
    viewer = _make_viewer()
    viewer._spin_snap_tol.setValue(2.5)
    viewer._on_snap_tol_changed(2.5)
    assert viewer._snap_tol == 2.5
    assert viewer._spin_snap_tol.value() == 2.5


def test_display_settings_snap_defaults(qapp):
    viewer = _make_viewer()
    d = viewer.display_settings()
    assert d["snap"] is True
    assert d["snap_tol"] == 1.0


def test_display_settings_snap_round_trip(qapp):
    viewer = _make_viewer()
    viewer.apply_display_settings({"snap": False, "snap_tol": 2.5})
    d = viewer.display_settings()
    assert d["snap"] is False
    assert d["snap_tol"] == 2.5
    viewer.apply_display_settings({"snap": True, "snap_tol": 0.5})
    d = viewer.display_settings()
    assert d["snap"] is True
    assert d["snap_tol"] == 0.5


def _with_ctrl(monkeypatch, active: bool) -> None:
    monkeypatch.setattr(
        QApplication, "keyboardModifiers",
        lambda: (Qt.KeyboardModifier.ControlModifier if active
                 else Qt.KeyboardModifier.NoModifier))


def test_snap_button_syncs_checkbox(qapp):
    viewer = _make_viewer()
    assert viewer._btn_snap.isChecked()
    viewer._btn_snap.setChecked(False)
    assert viewer._snap_enabled is False
    assert viewer._chk_snap.isChecked() is False


def test_snap_checkbox_syncs_button(qapp):
    viewer = _make_viewer()
    assert viewer._chk_snap.isChecked()
    viewer._chk_snap.setChecked(False)
    assert viewer._btn_snap.isChecked() is False
    assert viewer._snap_enabled is False
    viewer._chk_snap.setChecked(True)
    assert viewer._btn_snap.isChecked()
    assert viewer._snap_enabled is True


def test_measure_ctrl_bypass_flag(qapp, monkeypatch):
    viewer = _make_viewer()
    _with_ctrl(monkeypatch, False)
    assert viewer._measure_ctrl_bypass() is False
    _with_ctrl(monkeypatch, True)
    assert viewer._measure_ctrl_bypass() is True


def test_ctrl_bypass_click_uses_raw(qapp, monkeypatch):
    viewer = _make_viewer()
    viewer._measure_mode = True
    _with_ctrl(monkeypatch, True)
    viewer._on_measure_clicked(50.5, -60.4)   # near pad (50,60) but ctrl -> raw
    viewer._on_measure_clicked(10.0, -10.0)
    assert viewer._measurements == [(50.5, 60.4, 10.0, 10.0)]


def test_ctrl_bypass_move_no_snap_indicator(qapp, monkeypatch):
    viewer = _make_viewer()
    viewer._measure_mode = True
    viewer._measure_start = (50.0, 60.0)
    _with_ctrl(monkeypatch, True)
    viewer._on_measure_move(50.6, -60.3)
    assert viewer._measure_snap_item is None
    assert viewer._measure_preview is not None
    assert "snap off" in viewer._lbl_status.text()


def test_compact_default_shows_options(qapp):
    viewer = _make_viewer()
    assert viewer._btn_compact.isChecked()
    assert viewer._compact_hidden is False
    assert viewer._options_widget.isHidden() is False
    assert viewer._lbl_status.isHidden() is False


def test_compact_toggle_hides_options_and_stats_keeps_search(qapp):
    viewer = _make_viewer()
    viewer._btn_compact.setChecked(False)
    assert viewer._compact_hidden is True
    assert viewer._options_widget.isHidden() is True
    assert viewer._lbl_status.isHidden() is True
    assert viewer._search_input.isHidden() is False
    assert viewer._table_components.isHidden() is False
    viewer._btn_compact.setChecked(True)
    assert viewer._compact_hidden is False
    assert viewer._options_widget.isHidden() is False
    assert viewer._lbl_status.isHidden() is False
    assert viewer._search_input.isHidden() is False
    assert viewer._table_components.isHidden() is False


def test_display_settings_compact_round_trip(qapp):
    viewer = _make_viewer()
    assert viewer.display_settings()["compact"] is True
    viewer.apply_display_settings({"compact": False})
    assert viewer._compact_hidden is True
    assert viewer.display_settings()["compact"] is False
    viewer.apply_display_settings({"compact": True})
    assert viewer._compact_hidden is False


def _make_records():
    return [
        ReviewRecord(designator="C1", mpn="CAP-100UF", layer="top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="CAP-47UF", layer="top",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
        ReviewRecord(designator="R1", mpn="RES-10K", layer="top",
                     old_x=5.0, old_y=6.0, old_rotation=0.0),
    ]


def _make_viewer_with_records():
    viewer = _NoopGerberViewer(_make_records(), r"C:\nonexistent.gko")
    viewer._top = RenderData(flashes=[
        FlashShape(cx=50.0, cy=60.0, kind="circle", w=1.0, h=1.0),
    ])
    viewer._pad_grid_cache = {}
    viewer._loaded = True
    return viewer


def test_record_matches_search_designator(qapp):
    viewer = _make_viewer()
    rec = _make_records()[0]
    assert viewer._record_matches_search(rec, "c1") is True
    assert viewer._record_matches_search(rec, "C1") is True


def test_record_matches_search_mpn(qapp):
    viewer = _make_viewer()
    rec = _make_records()[0]
    assert viewer._record_matches_search(rec, "cap") is True
    assert viewer._record_matches_search(rec, "100uf") is True
    assert viewer._record_matches_search(rec, "res") is False


def test_record_matches_search_empty(qapp):
    viewer = _make_viewer()
    assert viewer._record_matches_search(_make_records()[0], "") is True


def test_apply_layer_search_by_mpn(qapp):
    viewer = _make_viewer_with_records()
    viewer._search_input.setText("cap")
    viewer._apply_layer()
    assert viewer._table_components.rowCount() == 2


def test_apply_layer_search_by_designator(qapp):
    viewer = _make_viewer_with_records()
    viewer._search_input.setText("c2")
    viewer._apply_layer()
    assert viewer._table_components.rowCount() == 1


def test_apply_layer_search_no_result(qapp):
    viewer = _make_viewer_with_records()
    viewer._search_input.setText("zzz")
    viewer._apply_layer()
    assert viewer._table_components.rowCount() == 0


def test_apply_layer_empty_search_all_rows(qapp):
    viewer = _make_viewer_with_records()
    viewer._search_input.setText("")
    viewer._apply_layer()
    assert viewer._table_components.rowCount() == 3


def test_grouped_search_by_mpn(qapp):
    viewer = _make_viewer_with_records()
    viewer._chk_group_mpn.setChecked(True)
    viewer._search_input.setText("cap")
    viewer._apply_layer()
    assert viewer._table_components.rowCount() == 2
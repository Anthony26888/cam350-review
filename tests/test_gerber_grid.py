import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from services.gerber.gerber_render import LineShape, RenderData
from ui.gerber_viewer import GerberViewer, _magnifier_scale


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


@pytest.fixture()
def viewer(app):
    v = _NoopGerberViewer([], r"C:\nonexistent.gko")
    v._outline = RenderData(lines=[LineShape(x1=0.0, y1=0.0, x2=100.0, y2=100.0)])
    v._loaded = True
    v.show()
    return v


def _enable_grid(viewer):
    viewer._grid_available = True
    viewer._chk_grid.setEnabled(True)


def test_grid_widgets_exist(viewer):
    assert hasattr(viewer, "_chk_grid")
    assert hasattr(viewer, "_spin_grid_cols")
    assert hasattr(viewer, "_spin_grid_rows")
    assert hasattr(viewer, "_spin_grid_opacity")
    assert hasattr(viewer, "_spin_grid_width")


def test_grid_default_pen_clear(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    pen = viewer._grid_item.pen()
    assert pen.widthF() == pytest.approx(2.0)
    assert pen.color().alpha() == 255
    assert pen.style().name == "DashLine"


def test_grid_style_change_updates_pen(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    first = viewer._grid_item
    viewer._spin_grid_opacity.setValue(100)
    viewer._spin_grid_width.setValue(3.0)
    assert viewer._grid_item is not first
    assert first not in viewer._scene.items()
    pen = viewer._grid_item.pen()
    assert pen.widthF() == pytest.approx(3.0)
    assert pen.color().alpha() == 100


def test_grid_style_round_trip(viewer):
    _enable_grid(viewer)
    viewer._spin_grid_opacity.setValue(120)
    viewer._spin_grid_width.setValue(2.5)
    settings = viewer.display_settings()
    assert settings["grid_opacity"] == 120
    assert settings["grid_width"] == pytest.approx(2.5)
    viewer.apply_display_settings({"grid_opacity": 80, "grid_width": 3.5})
    assert viewer._grid_opacity == 80
    assert viewer._grid_width == pytest.approx(3.5)
    assert viewer._spin_grid_opacity.value() == 80
    assert viewer._spin_grid_width.value() == pytest.approx(3.5)


def test_grid_checkbox_disabled_by_default(viewer):
    assert viewer._chk_grid.isEnabled() is False


def test_grid_checkbox_enabled_after_fit_scene(viewer):
    viewer._fit_scene()
    assert viewer._chk_grid.isEnabled() is True


def test_toggle_grid_enables_view_lock(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    assert viewer._grid_active is True
    assert viewer._view._grid_active is True
    assert viewer._view.dragMode().name == "NoDrag"


def test_grid_cannot_toggle_before_fit(viewer):
    viewer._chk_grid.setChecked(True)
    assert viewer._grid_active is False
    assert viewer._view._grid_active is False
    assert viewer._view.dragMode().name == "ScrollHandDrag"


def test_toggle_grid_off_restores_drag(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    viewer._chk_grid.setChecked(False)
    assert viewer._grid_active is False
    assert viewer._view._grid_active is False
    assert viewer._view.dragMode().name == "ScrollHandDrag"


def test_update_grid_draws_item(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    assert viewer._grid_item is not None
    assert viewer._grid_item in viewer._scene.items()
    assert viewer._grid_rect is not None
    assert viewer._grid_item.zValue() == 60


def test_update_grid_removes_item_when_off(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    item = viewer._grid_item
    viewer._chk_grid.setChecked(False)
    assert viewer._grid_item is None
    assert item not in viewer._scene.items()


def test_grid_params_change_redraws(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    first = viewer._grid_item
    viewer._spin_grid_cols.setValue(5)
    viewer._spin_grid_rows.setValue(4)
    assert viewer._grid_item is not None
    assert viewer._grid_item is not first
    assert first not in viewer._scene.items()


def test_grid_survives_redraw(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    viewer._redraw()
    assert viewer._grid_item is not None
    assert viewer._grid_item in viewer._scene.items()


def test_grid_cell_click_sets_magnifier_cell(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    rect = viewer._grid_rect
    assert rect is not None
    viewer._on_grid_cell_clicked(10.0, -10.0)
    cell = viewer._mag_cell_rect
    assert cell is not None
    assert cell.width() == pytest.approx(rect.width() / 3)
    assert cell.height() == pytest.approx(rect.height() / 3)
    assert viewer._mag_target == (cell.center().x(), cell.center().y())


def test_grid_cell_click_clamped(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    viewer._on_grid_cell_clicked(1e9, 1e9)
    cell = viewer._mag_cell_rect
    rect = viewer._grid_rect
    assert cell is not None
    assert cell.right() == pytest.approx(rect.right())
    assert cell.bottom() == pytest.approx(rect.bottom())


def test_grid_cell_click_ignored_when_off(viewer):
    viewer._on_grid_cell_clicked(10.0, -10.0)
    assert viewer._mag_cell_rect is None


def test_magnifier_fits_cell(viewer, monkeypatch):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    viewer._on_grid_cell_clicked(10.0, -10.0)
    vp = type("VP", (), {})()
    vp.width = lambda: 400.0
    vp.height = lambda: 300.0
    monkeypatch.setattr(viewer._mag_view, "viewport", lambda: vp)
    viewer._refresh_magnifier()
    cell = viewer._mag_cell_rect
    cover = max(400.0 / cell.width(), 300.0 / cell.height())
    assert viewer._mag_view.transform().m11() == pytest.approx(cover)


def test_magnifier_cell_covers_viewport(viewer, monkeypatch):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    viewer._on_grid_cell_clicked(10.0, -10.0)
    vp = type("VP", (), {})()
    vp.width = lambda: 400.0
    vp.height = lambda: 300.0
    monkeypatch.setattr(viewer._mag_view, "viewport", lambda: vp)
    viewer._refresh_magnifier()
    cell = viewer._mag_cell_rect
    scale = viewer._mag_view.transform().m11()
    assert scale >= 400.0 / cell.width()
    assert scale >= 300.0 / cell.height()


def test_hover_keeps_cell_locked_when_grid_active(viewer, monkeypatch):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    viewer._on_grid_cell_clicked(10.0, -10.0)
    cell = viewer._mag_cell_rect
    assert cell is not None
    monkeypatch.setattr(viewer._view, "_zoom_active", False)
    monkeypatch.setattr(viewer._view, "_panning", False)
    viewer._update_magnifier(5.0, -5.0)
    assert viewer._mag_cell_rect is cell
    assert viewer._mag_target == (cell.center().x(), cell.center().y())


def test_hover_follows_again_after_grid_off(viewer, monkeypatch):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    viewer._on_grid_cell_clicked(10.0, -10.0)
    assert viewer._mag_cell_rect is not None
    viewer._chk_grid.setChecked(False)
    assert viewer._mag_cell_rect is None
    monkeypatch.setattr(viewer._view, "_zoom_active", False)
    monkeypatch.setattr(viewer._view, "_panning", False)
    viewer._update_magnifier(5.0, -5.0)
    assert viewer._mag_cell_rect is None
    assert viewer._mag_target == (5.0, -5.0)


def test_wheel_ignored_when_grid_active(viewer, monkeypatch):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)

    class Event:
        def ignore(self):
            self.ignored = True

    event = Event()
    monkeypatch.setattr(
        viewer._view, "_set_fast_render", lambda: pytest.fail("should not zoom")
    )
    viewer._view.wheelEvent(event)
    assert getattr(event, "ignored", False) is True


def test_mag_factor_change_keeps_cell_when_grid_active(viewer, monkeypatch):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    viewer._on_grid_cell_clicked(10.0, -10.0)
    cell = viewer._mag_cell_rect
    assert cell is not None
    vp = type("VP", (), {})()
    vp.width = lambda: 400.0
    vp.height = lambda: 300.0
    monkeypatch.setattr(viewer._mag_view, "viewport", lambda: vp)
    viewer._refresh_magnifier()
    scale_before = viewer._mag_view.transform().m11()
    for i in range(viewer._combo_mag.count()):
        if viewer._combo_mag.itemData(i) == 10.0:
            viewer._combo_mag.setCurrentIndex(i)
            break
    assert viewer._mag_cell_rect is cell
    scale_after = viewer._mag_view.transform().m11()
    assert scale_after == pytest.approx(scale_before)


def test_grid_cell_zoom_factor_ignored(viewer, monkeypatch):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    viewer._on_grid_cell_clicked(10.0, -10.0)
    vp = type("VP", (), {})()
    vp.width = lambda: 400.0
    vp.height = lambda: 300.0
    monkeypatch.setattr(viewer._mag_view, "viewport", lambda: vp)
    for f in (3.0, 4.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 25.0):
        viewer._mag_factor = f
        viewer._refresh_magnifier()
        cell = viewer._mag_cell_rect
        cover = max(400.0 / cell.width(), 300.0 / cell.height())
        assert viewer._mag_view.transform().m11() == pytest.approx(cover)


def test_mag_factor_change_clears_cell_when_grid_off(viewer, monkeypatch):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    viewer._on_grid_cell_clicked(10.0, -10.0)
    assert viewer._mag_cell_rect is not None
    viewer._chk_grid.setChecked(False)
    assert viewer._mag_cell_rect is None
    vp = type("VP", (), {})()
    vp.width = lambda: 400.0
    vp.height = lambda: 300.0
    monkeypatch.setattr(viewer._mag_view, "viewport", lambda: vp)
    for i in range(viewer._combo_mag.count()):
        if viewer._combo_mag.itemData(i) == 10.0:
            viewer._combo_mag.setCurrentIndex(i)
            break
    assert viewer._mag_cell_rect is None


def test_reload_records_leaves_grid_alone(viewer):
    _enable_grid(viewer)
    viewer._chk_grid.setChecked(True)
    assert viewer._grid_active is True
    viewer._on_reload_records()
    # Reload only refreshes data; grid state is untouched
    assert viewer._grid_active is True
    assert viewer._view.dragMode().name != "ScrollHandDrag"
    assert viewer._chk_grid.isEnabled() is True

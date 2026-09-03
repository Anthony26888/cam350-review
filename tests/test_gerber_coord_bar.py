import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.gerber_viewer import GerberViewer


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


@pytest.fixture()
def viewer(app):
    return _NoopGerberViewer([], r"C:\nonexistent.gko")


def test_coord_bar_widgets_exist(viewer):
    assert hasattr(viewer, "_lbl_coord")
    assert hasattr(viewer, "_spin_goto_x")
    assert hasattr(viewer, "_spin_goto_y")
    assert hasattr(viewer, "_btn_goto")


def test_coord_label_blank_by_default(viewer):
    assert "X: --" in viewer._lbl_coord.text()


def test_update_coord_label_flips_y(viewer):
    viewer._loaded = True
    viewer._update_coord_label(10.5, 20.25)
    assert viewer._lbl_coord.text() == "X: 10.50  Y: -20.25"


def test_update_coord_label_ignored_when_not_loaded(viewer):
    viewer._lbl_coord.setText("custom")
    viewer._update_coord_label(1.0, 2.0)
    assert viewer._lbl_coord.text() == "custom"


def test_clear_coord_label_resets(viewer):
    viewer._loaded = True
    viewer._update_coord_label(1.5, -2.5)
    viewer._clear_coord_label()
    assert "X: --" in viewer._lbl_coord.text()


def test_goto_coord_centers_view_and_magnifier(viewer, monkeypatch):
    viewer._loaded = True
    viewer._spin_goto_x.setValue(12.5)
    viewer._spin_goto_y.setValue(-7.25)
    centered = []
    monkeypatch.setattr(viewer._view, "centerOn", lambda x, y: centered.append((x, y)))
    viewer._goto_coord()
    assert centered == [(12.5, 7.25)]
    assert viewer._mag_target == (12.5, 7.25)


def test_goto_coord_ignored_when_not_loaded(viewer, monkeypatch):
    monkeypatch.setattr(
        viewer._view, "centerOn", lambda x, y: pytest.fail("should not center")
    )
    viewer._goto_coord()
    assert viewer._mag_target is None


def test_goto_coord_adds_crosshair(viewer):
    viewer._loaded = True
    viewer._spin_goto_x.setValue(12.5)
    viewer._spin_goto_y.setValue(-7.25)
    viewer._goto_coord()
    assert viewer._goto_pos == (12.5, 7.25)
    assert viewer._goto_crosshair is not None
    assert viewer._goto_crosshair in viewer._scene.items()


def test_goto_coord_replaces_crosshair(viewer):
    viewer._loaded = True
    viewer._spin_goto_x.setValue(1.0)
    viewer._spin_goto_y.setValue(2.0)
    viewer._goto_coord()
    first = viewer._goto_crosshair
    viewer._spin_goto_x.setValue(3.0)
    viewer._spin_goto_y.setValue(4.0)
    viewer._goto_coord()
    assert viewer._goto_crosshair is not None
    assert viewer._goto_crosshair is not first
    assert first not in viewer._scene.items()
    assert viewer._goto_crosshair in viewer._scene.items()


def test_goto_crosshair_cleared_when_not_loaded(viewer):
    viewer._loaded = True
    viewer._spin_goto_x.setValue(1.0)
    viewer._spin_goto_y.setValue(2.0)
    viewer._goto_coord()
    assert viewer._goto_crosshair is not None
    viewer._loaded = False
    viewer._update_goto_crosshair()
    assert viewer._goto_crosshair is None


def test_goto_crosshair_survives_redraw(viewer):
    viewer._loaded = True
    viewer._spin_goto_x.setValue(5.0)
    viewer._spin_goto_y.setValue(6.0)
    viewer._goto_coord()
    viewer._redraw()
    assert viewer._goto_crosshair is not None
    assert viewer._goto_crosshair in viewer._scene.items()


def test_goto_coord_after_redraw_no_crash(viewer):
    viewer._loaded = True
    viewer._spin_goto_x.setValue(1.0)
    viewer._spin_goto_y.setValue(2.0)
    viewer._goto_coord()
    viewer._redraw()
    viewer._spin_goto_x.setValue(7.0)
    viewer._spin_goto_y.setValue(8.0)
    viewer._goto_coord()
    assert viewer._goto_crosshair is not None
    assert viewer._goto_crosshair in viewer._scene.items()
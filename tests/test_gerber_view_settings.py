import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from models.review import ReviewRecord
from services.gerber.gerber_render import RenderData
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
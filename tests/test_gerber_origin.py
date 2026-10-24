"""The mark of the origin of the coordinates in the Gerber View."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from services.gerber.gerber_render import RenderData  # noqa: E402
from ui.gerber_viewer import (  # noqa: E402
    ORIGIN_MARKER_HALF, GerberViewer,
)


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


class TestTheMark:
    def test_the_mark_is_drawn_when_it_is_wanted(self, viewer):
        assert viewer._chk_origin.isChecked()
        assert viewer._origin_marker is not None

    def test_the_mark_can_be_taken_away(self, viewer):
        viewer._chk_origin.setChecked(False)
        assert viewer._origin_marker is None
        viewer._chk_origin.setChecked(True)
        assert viewer._origin_marker is not None

    def test_the_mark_stands_at_the_origin(self, viewer):
        # The origin of the file is the point (0,0); the scene has the y
        # downwards, so the mark sits at (0,0) as well.
        box = viewer._origin_marker.boundingRect()
        assert box.center().x() == pytest.approx(0.0, abs=0.01)
        assert box.center().y() == pytest.approx(0.0, abs=0.01)

    def test_the_mark_follows_the_turn(self, viewer):
        viewer._set_rotation(90, emit=False)   # 90 degrees
        viewer._redraw()
        box = viewer._origin_marker.boundingRect()
        # The origin does not move when the page is turned.
        assert box.center().x() == pytest.approx(0.0, abs=0.01)
        assert box.center().y() == pytest.approx(0.0, abs=0.01)

    def test_the_diagonals_are_five_millimetres_long(self, viewer):
        # The pen is cosmetic, so the width of the item is not the size
        # of the mark; the path itself is.
        box = viewer._origin_marker.path().boundingRect()
        assert box.width() == pytest.approx(2 * ORIGIN_MARKER_HALF, abs=0.01)
        assert box.height() == pytest.approx(2 * ORIGIN_MARKER_HALF, abs=0.01)

    def test_the_mark_is_two_lines(self, viewer):
        # Two diagonals: four points.
        assert viewer._origin_marker.path().elementCount() == 4

    def test_the_name_of_the_origin_is_not_written(self, viewer):
        # The mark stands alone: there is no text beside it.
        assert getattr(viewer, "_origin_label", None) is None
        texts = [item.text() for item in viewer._scene.items()
                 if hasattr(item, "text")]
        assert "0,0" not in texts

    def test_the_mark_is_grey(self, viewer):
        assert viewer._origin_marker.pen().color().name() == "#c0c0c0"

    def test_the_mark_lies_over_the_layers(self, viewer):
        assert viewer._origin_marker.zValue() > 1000.0


class TestTheSetting:
    def test_the_mark_is_remembered(self, viewer):
        settings = viewer.display_settings()
        assert settings["show_origin"] is True
        viewer._chk_origin.setChecked(False)
        assert viewer.display_settings()["show_origin"] is False

    def test_the_mark_is_read_back(self, viewer):
        viewer.apply_display_settings({"show_origin": False})
        assert viewer._chk_origin.isChecked() is False
        assert viewer._show_origin is False

    def test_a_session_without_the_key_shows_the_mark(self, viewer):
        viewer.apply_display_settings({"crosshair": True})
        assert viewer._chk_origin.isChecked() is True

"""PCB Info picking on the Gerber: board corners and BOC points."""

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
from ui.gerber_viewer import GerberViewer  # noqa: E402


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


class _FakeDialog:
    def __init__(self):
        self.calls = []

    def apply_pick(self, key, points):
        self.calls.append((key, list(points)))


def _viewer(app, monkeypatch):
    v = _NoopGerberViewer([], _layers())
    v._layer_data = [RenderData() for _ in v._layers]
    v._loaded = True
    v._board_center = (0.0, 0.0)
    for stub in ("_redraw", "_apply_layer", "_fit_scene",
                 "_rebuild_marker_overlay"):
        monkeypatch.setattr(v, stub, lambda *a, **k: None)
    return v


def test_boc_pick_uses_board_coordinates(app, monkeypatch):
    v = _viewer(app, monkeypatch)
    dlg = _FakeDialog()
    v._pcb_dialog = dlg
    v._origin_x = 5.0
    v._origin_y = 2.0
    v._start_pcb_pick("boc1")
    assert v._pcb_pick_key == "boc1"
    v._on_pcb_pick_clicked(15.0, -12.0)
    assert dlg.calls == [("boc1", [(10.0, 10.0)])]
    assert v._pcb_pick_key is None
    v.close()


def test_board_pick_needs_two_opposite_corners(app, monkeypatch):
    v = _viewer(app, monkeypatch)
    dlg = _FakeDialog()
    v._pcb_dialog = dlg
    v._origin_x = 0.0
    v._origin_y = 0.0
    v._start_pcb_pick("board")
    v._on_pcb_pick_clicked(0.0, 0.0)
    assert dlg.calls == []
    assert v._pcb_pick_key == "board"
    v._on_pcb_pick_clicked(100.0, -50.0)
    assert dlg.calls == [("board", [(0.0, 0.0), (100.0, 50.0)])]
    assert v._pcb_pick_key is None
    v.close()


def test_cancel_pcb_pick_clears_state(app, monkeypatch):
    v = _viewer(app, monkeypatch)
    v._pcb_dialog = _FakeDialog()
    v._start_pcb_pick("boc2")
    v._cancel_pcb_pick()
    assert v._pcb_pick_key is None
    assert v._pcb_pick_points == []
    v.close()

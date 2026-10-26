"""Trace pad: the copper of the net of a clicked pad lights up."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from models.review import ReviewRecord  # noqa: E402
from services.gerber.gerber_render import FlashShape, LineShape, RenderData  # noqa: E402
from services.gerber.layer_scan import LayerInfo  # noqa: E402
from ui.gerber_viewer import GerberViewer, Z_TRACE  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _records():
    return [
        ReviewRecord(designator="R1", layer="top",
                     old_x=0.0, old_y=0.0, old_rotation=0.0),
        ReviewRecord(designator="C1", layer="top",
                     old_x=20.0, old_y=10.0, old_rotation=0.0),
    ]


def _layers():
    return [
        LayerInfo(path="C:/p/board.gtl", file_name="board.gtl",
                  name="Top copper", role="copper", side="top"),
    ]


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


def _wire_data():
    data = RenderData()
    data.arcs = []
    data.lines = [
        LineShape(x1=0.0, y1=0.0, x2=10.0, y2=0.0, width=0.2),
        LineShape(x1=10.0, y1=0.0, x2=20.0, y2=0.0, width=0.2),
        LineShape(x1=20.0, y1=0.0, x2=20.0, y2=10.0, width=0.2),
    ]
    data.flashes = [
        FlashShape(cx=0.0, cy=0.0, kind="circle", w=1.0, h=1.0),
        FlashShape(cx=20.0, cy=10.0, kind="circle", w=0.8, h=0.8),
        FlashShape(cx=50.0, cy=50.0, kind="circle", w=1.2, h=1.2),
    ]
    return data


def _viewer(app, records=_records(), layers=_layers(), datas=None):
    v = _NoopGerberViewer(records, layers)
    v._layer_data = datas or [_wire_data() for _ in layers]
    v._loaded = True
    v._board_center = (0.0, 0.0)
    return v


def _turn_on(v):
    v._btn_trace.blockSignals(True)
    v._btn_trace.setChecked(True)
    v._btn_trace.blockSignals(False)
    v._trace_mode = True
    v._view.set_trace_mode(True)


def test_the_mode_turns_on_and_off(app):
    v = _viewer(app)
    v._btn_trace.setEnabled(True)
    v._btn_trace.setChecked(True)
    assert v._trace_mode is True
    assert "Trace pad:" in v._lbl_status.text()
    v._btn_trace.setChecked(False)
    assert v._trace_mode is False
    assert "Trace pad cancelled." in v._lbl_status.text()


def test_a_click_lights_the_net_of_the_pad(app):
    v = _viewer(app)
    _turn_on(v)
    # Click the wire between the two pads: raw (10, 0) is scene (10, 0).
    v._on_trace_picked(10.0, 0.0)
    assert v._trace_line_item is not None
    assert v._trace_line_item.zValue() == Z_TRACE
    assert v._trace_fill_item is not None
    assert v._trace_fill_item.zValue() == Z_TRACE
    assert "Trace pad (Top copper):" in v._lbl_status.text()
    assert "5 traces" in v._lbl_status.text()
    assert "R1" in v._lbl_status.text()
    assert "C1" in v._lbl_status.text()
    v._btn_trace.setChecked(False)


def test_a_second_pad_of_the_same_net_connects(app):
    v = _viewer(app)
    _turn_on(v)
    v._on_trace_picked(0.0, 0.0)
    v._on_trace_picked(20.0, -10.0)  # raw (20, 10), the second pad
    assert "CONNECTED" in v._lbl_status.text()
    v._btn_trace.setChecked(False)


def test_a_second_pad_of_another_net_does_not_connect(app):
    v = _viewer(app)
    _turn_on(v)
    v._on_trace_picked(0.0, 0.0)
    v._on_trace_picked(50.0, -50.0)  # the isolated pad
    assert "NOT connected" in v._lbl_status.text()
    v._btn_trace.setChecked(False)


def test_a_click_on_empty_copper_reports_no_pad(app):
    v = _viewer(app)
    _turn_on(v)
    v._on_trace_picked(60.0, 0.0)
    assert "no pad at the clicked point" in v._lbl_status.text()
    v._btn_trace.setChecked(False)


def test_a_repeat_click_moves_to_the_next_copper_layer(app):
    layers = [
        LayerInfo(path="C:/p/board.gtl", file_name="board.gtl",
                  name="Top copper", role="copper", side="top"),
        LayerInfo(path="C:/p/board.g1", file_name="board.g1",
                  name="G1", role="copper", side="top"),
    ]
    inner = _wire_data()
    v = _viewer(app, layers=layers, datas=[_wire_data(), inner])
    _turn_on(v)
    v._on_trace_picked(10.0, 0.0)
    assert "Trace pad (Top copper):" in v._lbl_status.text()
    v._on_trace_picked(10.0, 0.0)
    assert "Trace pad (G1):" in v._lbl_status.text()
    v._btn_trace.setChecked(False)


def test_esc_cancels_the_trace(app):
    v = _viewer(app)
    _turn_on(v)
    v._on_trace_picked(10.0, 0.0)
    assert v._trace_line_item is not None
    v._view.trace_pad_cancel.emit()
    assert v._trace_mode is False
    assert v._btn_trace.isChecked() is False
    assert v._trace_line_item is None and v._trace_fill_item is None
    assert v._trace_first is None


def test_changing_the_side_clears_the_trace(app):
    v = _viewer(app)
    _turn_on(v)
    v._on_trace_picked(10.0, 0.0)
    assert v._trace_line_item is not None
    v._combo_layer.setCurrentIndex(1)
    assert v._trace_line_item is None and v._trace_fill_item is None
    v._btn_trace.setChecked(False)


def test_the_start_of_load_wipes_the_trace_state(app):
    v = _viewer(app)
    _turn_on(v)
    v._on_trace_picked(10.0, 0.0)
    data = _wire_data()
    v._on_load_finished([data])
    assert v._active_trace is None
    assert v._trace_indices == {}
    assert v._trace_line_item is None and v._trace_fill_item is None
    v._btn_trace.setChecked(False)


def test_the_layers_of_other_sides_are_ignored(app):
    layers = [
        LayerInfo(path="C:/p/board.gtl", file_name="board.gtl",
                  name="Top copper", role="copper", side="top"),
        LayerInfo(path="C:/p/board.gbl", file_name="board.gbl",
                  name="Bottom copper", role="copper", side="bottom"),
    ]
    v = _viewer(app, records=_records(), layers=layers)
    _turn_on(v)
    v._combo_layer.setCurrentIndex(0)
    v._on_trace_picked(10.0, 0.0)
    # Only the top copper carries a pad here: no cycle is offered.
    assert "click again" not in v._lbl_status.text()
    v._btn_trace.setChecked(False)


def test_a_pour_is_counted_but_not_painted(app):
    data = _wire_data()
    data.arcs = []
    # A pour that hangs on the wire of the net: it joins the trace but
    # must not be painted, so the picture stays clear.
    data.flashes = data.flashes + [
        FlashShape(cx=150.0, cy=150.0, kind="polygon",
                   pts=[(130.0, 130.0), (170.0, 130.0), (170.0, 170.0),
                        (130.0, 170.0)],
                   pts_local=False),
    ]
    v = _viewer(app, datas=[data])
    _turn_on(v)
    v._on_trace_picked(10.0, 0.0)
    assert v._trace_fill_item is not None
    listed = v._pad_name_list(data, v._active_trace[2].flashes,
                              v._active_trace[3])
    assert listed  # the pour sits in the net anyway
    n_strokes = 3
    # The fill path holds only the two round pads, not the square pour.
    fill_rect = v._trace_fill_item.path().boundingRect()
    assert fill_rect.width() < 30.0  # a pour spans 40 mm, pads shallow
    assert v._trace_line_item.path().elementCount() >= n_strokes
    v._btn_trace.setChecked(False)


def test_the_wires_of_the_net_are_one_bright_chain(app):
    from PySide6.QtGui import QPen
    v = _viewer(app)
    _turn_on(v)
    v._on_trace_picked(10.0, 0.0)
    pen = v._trace_line_item.pen()
    assert isinstance(pen, QPen)
    assert pen.widthF() == pytest.approx(0.6)
    assert not pen.isCosmetic()  # millimetres, so the zoom scales the line
    v._btn_trace.setChecked(False)


def test_plane_pad_shows_popup_at_cursor(app):
    from PySide6.QtCore import QPoint
    data = _wire_data()
    # A massive pour touching pad 0 at (0, 0)
    data.flashes.append(
        FlashShape(cx=0.0, cy=0.0, kind="polygon",
                   pts=[(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)],
                   pts_local=False)
    )
    v = _viewer(app, datas=[data])
    _turn_on(v)
    v._on_trace_picked(0.0, 0.0, screen_pos=QPoint(100, 100))
    assert v._trace_popup is not None
    assert v._trace_popup.isHidden() is False
    assert "GND/PWR PLANE" in v._trace_popup.text()
    assert "R1" in v._trace_popup.text()

    # Cancel hides popup
    v._view.trace_pad_cancel.emit()
    assert v._trace_popup.isHidden() is True


def test_normal_net_does_not_show_plane_popup(app):
    from PySide6.QtCore import QPoint
    v = _viewer(app)
    _turn_on(v)
    v._on_trace_picked(10.0, 0.0, screen_pos=QPoint(100, 100))
    # For a normal wire net without massive copper pour, popup is hidden or not created
    if v._trace_popup is not None:
        assert v._trace_popup.isHidden() is True
    v._btn_trace.setChecked(False)


def test_small_polygon_pad_is_rendered_in_fill(app):
    data = RenderData()
    data.lines = []
    data.arcs = []
    # A small polygon pad (e.g. 2x2 mm SMD pad)
    data.flashes = [
        FlashShape(cx=0.0, cy=0.0, kind="polygon",
                   pts=[(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
                   pts_local=True)
    ]
    v = _viewer(app, datas=[data])
    _turn_on(v)
    v._on_trace_picked(0.0, 0.0)
    assert v._trace_fill_item is not None
    assert not v._trace_fill_item.path().isEmpty()
    # It should not be treated as a plane
    assert "GND/Power" not in v._lbl_status.text()
    v._btn_trace.setChecked(False)


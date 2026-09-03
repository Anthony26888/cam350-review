import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QGraphicsScene

from ui.gerber_viewer import GerberView, MarkerOverlayItem


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_view() -> GerberView:
    view = GerberView()
    scene = QGraphicsScene(view)
    path = QPainterPath()
    path.addRect(0.0, 0.0, 4000.0, 4000.0)  # larger than viewport -> scrollbars
    scene.addPath(path, QPen(Qt.GlobalColor.white))
    view.setScene(scene)
    view.resize(640, 480)
    view.show()
    view.viewport().grab()
    return view


def _wheel(view: GerberView, angle: int = 120) -> QWheelEvent:
    pos = QPointF(100.0, 100.0)
    ev = QWheelEvent(
        pos, pos, QPoint(0, 0), QPoint(0, angle),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    return ev


def _mouse(view, kind, x, y):
    return QMouseEvent(kind, QPointF(x, y),
                       Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def test_wheel_zoom_is_deferred(qapp):
    view = _make_view()
    view.wheelEvent(_wheel(view))
    assert view._zoom_pixmap is not None
    assert view._zoom_ratio == pytest.approx(1.15)
    assert view._fast_render is True
    assert view._zoom_active is True
    assert view.transform().m11() == pytest.approx(1.0)


def test_wheel_zoom_out_clamps_ratio(qapp):
    view = _make_view()
    for _ in range(50):
        view.wheelEvent(_wheel(view, angle=-120))
    assert view._zoom_pixmap is not None
    assert view._zoom_ratio == pytest.approx(0.002)


def test_restore_applies_transform_and_clears_state(qapp):
    view = _make_view()
    view.wheelEvent(_wheel(view))
    view._restore_smooth_render()
    assert view.transform().m11() == pytest.approx(1.15)
    assert view._zoom_pixmap is None
    assert view._zoom_ratio == pytest.approx(1.0)
    assert view._zoom_active is False
    assert view._fast_render is False


def test_pan_snapshot_defers_render_and_applies_once(qapp):
    view = _make_view()
    hbar, vbar = view.horizontalScrollBar(), view.verticalScrollBar()
    base_h, base_v = hbar.value(), vbar.value()

    view.mousePressEvent(_mouse(view, QMouseEvent.Type.MouseButtonPress, 200, 150))
    assert view._panning is True
    assert view._pan_pixmap is not None          # snapshot taken once
    assert view.transform().m11() == pytest.approx(1.0)

    view.mouseMoveEvent(_mouse(view, QMouseEvent.Type.MouseMove, 240, 180))
    assert view._pan_offset == QPoint(40, 30)
    # Scene untouched during the gesture (scrollbars frozen)
    assert hbar.value() == base_h and vbar.value() == base_v

    view.mouseMoveEvent(_mouse(view, QMouseEvent.Type.MouseMove, 260, 190))
    assert view._pan_offset == QPoint(60, 40)

    view.mouseReleaseEvent(_mouse(view, QMouseEvent.Type.MouseButtonRelease, 260, 190))
    assert view._pan_pixmap is None and view._panning is False
    # Whole gesture applied as one scroll (content moves opposite to hand)
    assert hbar.value() == base_h - 60
    assert vbar.value() == base_v - 40


def test_pan_plain_click_no_scroll(qapp):
    view = _make_view()
    hbar, vbar = view.horizontalScrollBar(), view.verticalScrollBar()
    base_h, base_v = hbar.value(), vbar.value()
    view.mousePressEvent(_mouse(view, QMouseEvent.Type.MouseButtonPress, 100, 100))
    view.mouseReleaseEvent(_mouse(view, QMouseEvent.Type.MouseButtonRelease, 100, 100))
    assert view._pan_pixmap is None
    assert hbar.value() == base_h
    assert vbar.value() == base_v


def test_pan_skipped_during_wheel_fast_window(qapp):
    view = _make_view()
    view.wheelEvent(_wheel(view))                # fast-render window opens
    view.mousePressEvent(_mouse(view, QMouseEvent.Type.MouseButtonPress, 100, 100))
    assert view._pan_pixmap is None              # falls back to legacy drag
    view._restore_smooth_render()


def test_overlay_culls_offscreen_markers():
    item = MarkerOverlayItem(
        [(0.0, 0.0, 0.0, 5.0), (5000.0, 5000.0, 0.0, 5.0)],
    )
    from PySide6.QtCore import QRectF
    near = QRectF(-50, -50, 100, 100)            # contains marker 0 only
    assert item._outside_exposed(0.0, 0.0, 20.0, near) is False
    assert item._outside_exposed(5000.0, 5000.0, 20.0, near) is True
    assert item._outside_exposed(0.0, 0.0, 20.0, None) is False

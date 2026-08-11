import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QApplication, QGraphicsScene

from ui.gerber_viewer import GerberView


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_view() -> GerberView:
    view = GerberView()
    scene = QGraphicsScene(view)
    path = QPainterPath()
    path.addRect(0.0, 0.0, 100.0, 100.0)
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

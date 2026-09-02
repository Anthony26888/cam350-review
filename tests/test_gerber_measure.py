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

from ui.gerber_viewer import GerberView, MeasurementItem  # noqa: E402


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
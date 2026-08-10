import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QTransform
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

from ui.gerber_viewer import (
    _MAG_FACTOR, _MAG_MIN_SCALE, _magnifier_scale,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_magnifier_scale_fixed_floor():
    # very large board -> crawl below the readability floor
    scale = _magnifier_scale(5000.0, 300, 220)
    assert scale >= _MAG_MIN_SCALE


def test_magnifier_scale_is_five_x_of_fit():
    board = 200.0
    vw, vh = 300, 220
    scale = _magnifier_scale(board, vw, vh)
    base = min(vw, vh) / board
    assert scale == pytest.approx(max(base * _MAG_FACTOR, _MAG_MIN_SCALE))


def test_magnifier_scale_independent_of_bigest_window():
    a = _magnifier_scale(200.0, 300, 220)
    b = _magnifier_scale(200.0, 300, 220)
    assert a == b


def test_magnifier_view_centers_on_scene_point(app):
    scene = QGraphicsScene()
    view = QGraphicsView(scene)
    view.setMinimumSize(300, 220)
    view.resize(320, 240)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    view.show()

    scene.addRect(QRectF(0, 0, 2000, 2000), QColor(255, 255, 255))

    target = (1234.0, 987.0)
    scale = _magnifier_scale(2000.0, view.viewport().width(), view.viewport().height())
    view.setTransform(QTransform().fromScale(scale, scale))
    view.centerOn(*target)

    center = view.mapToScene(view.viewport().rect().center())
    assert abs(center.x() - target[0]) * scale <= 1.5
    assert abs(center.y() - target[1]) * scale <= 1.5
    assert view.transform().m11() == pytest.approx(scale)
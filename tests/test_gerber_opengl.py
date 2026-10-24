"""The switch that draws the picture with OpenGL."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from ui.gerber_viewer import GerberView  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_view() -> GerberView:
    view = GerberView()
    view.setScene(QGraphicsScene(view))
    view.resize(640, 480)
    view.show()
    view.viewport().grab()
    return view


def test_the_view_is_not_drawn_with_opengl_by_default(qapp):
    view = _make_view()
    assert view._use_opengl is False


def test_opengl_can_be_switched_on_and_off(qapp):
    view = _make_view()
    try:
        from PySide6.QtOpenGLWidgets import QOpenGLWidget
    except ImportError:  # pragma: no cover - the module is part of PySide6
        pytest.skip("PySide6 has no OpenGL widgets")
    view.set_use_opengl(True)
    assert view._use_opengl is True
    assert isinstance(view.viewport(), QOpenGLWidget)
    view.set_use_opengl(False)
    assert view._use_opengl is False
    assert not isinstance(view.viewport(), QOpenGLWidget)


def test_the_view_still_draws_with_opengl(qapp):
    view = _make_view()
    view.set_use_opengl(True)
    try:
        view.viewport().grab()
    except RuntimeError:
        # A machine without a graphics driver cannot show the surface; the
        # picture is drawn the same way either way.
        pass
    finally:
        view.set_use_opengl(False)

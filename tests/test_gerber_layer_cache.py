"""The caches keep a big board quick between two clicks.

A colour change that only dims the layer, a turn back to a familiar
angle, and a first appearance of a fresh board all have to behave the
way the reader of a board expects: nothing is thrown away that still
describes the artwork.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor, QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from services.gerber.gerber_render import FlashShape, RenderData  # noqa: E402
from services.gerber.layer_scan import LayerInfo  # noqa: E402
from services.gerber.render.layer import (  # noqa: E402
    DrawOp,
    LayerItem,
    LayerPaths,
)
import ui.gerber_viewer as gerber_viewer_module  # noqa: E402
from ui.gerber_viewer import GerberViewer, _LayerPathCache  # noqa: E402


def test_alpha_only_does_not_throw_the_pictures_away():
    item = LayerItem(_paths(), QColor(0, 120, 250, 255))
    cleared = []
    item._cache.clear = lambda: cleared.append(1)
    item.set_color(QColor(0, 120, 250, 180))
    assert cleared == []
    item.set_color(QColor(0, 120, 250, 110))
    assert cleared == []


def test_a_new_colour_throws_the_pictures_away():
    item = LayerItem(_paths(), QColor(0, 120, 250, 255))
    cleared = []
    item._cache.clear = lambda: cleared.append(1)
    item.set_color(QColor(255, 0, 0, 255))
    assert cleared == [1]
    assert item.color() == QColor(255, 0, 0, 255)


def test_the_cache_of_the_built_paths_keeps_two_turns_per_layer():
    cache = _LayerPathCache()
    cache.put(0, (1,), "third")
    cache.put(0, (2,), "also third")
    cache.put(0, (3,), "new third")
    # Only the two transforms that came last stay: the ones the reader of
    # the page flips between.
    assert cache.get(0, (1,)) is None
    assert cache.get(0, (2,)) == "also third"
    assert cache.get(0, (3,)) == "new third"
    # Layers are swept apart, so a busy copper page keeps its turns.
    cache.put(1, (1,), "other layer")
    assert cache.get(1, (1,)) == "other layer"
    assert cache.get(0, (3,)) == "new third"
    cache.clear()
    assert cache.get(0, (3,)) is None
    assert cache.get(1, (1,)) is None


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _paths():
    path = QPainterPath()
    path.addRect(0.0, 0.0, 10.0, 10.0)
    return LayerPaths(
        ops=[DrawOp(path=path, width=1.0)],
        tile_rect=QRectF(0.0, 0.0, 1000.0, 1000.0), tile_columns=1,
        tile_rows=1)


def _data():
    return RenderData(
        lines=[], arcs=[], flashes=[FlashShape(cx=5.0, cy=5.0,
                                               kind="circle", w=1.0, h=1.0)])


def _layers():
    return [LayerInfo(path="C:/p/a.gtl", file_name="a.gtl", name="Top",
                      role="copper", side="top")]


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


def _viewer(app, datas=None):
    v = _NoopGerberViewer([], _layers())
    v._layer_data = datas or [_data() for _ in _layers()]
    v._loaded = True
    v._board_center = (0.0, 0.0)
    return v


def test_a_familiar_angle_is_drawn_without_a_walk(app, monkeypatch):
    v = _viewer(app)
    data = v._layer_data[0]
    calls = []

    def counting(*a, **k):
        calls.append(1)
        return _paths()

    monkeypatch.setattr(gerber_viewer_module, "build_layer_paths", counting)
    v._render_layer(0, data, 0.0, False, 0.0, 0.0)
    item1 = v._layer_items[0]
    v._render_layer(0, data, 0.0, False, 0.0, 0.0)
    assert calls == [1]
    assert v._layer_items[0] is not item1


def test_a_fresh_board_forgets_the_built_paths(app, monkeypatch):
    v = _viewer(app)
    v._layer_path_cache.put(0, (True, 0.0, False, False), (_paths(), None))
    monkeypatch.setattr(v, "_redraw", lambda *a, **k: None)
    monkeypatch.setattr(v, "_fit_scene", lambda: None)
    v._on_load_finished([_data()])
    assert v._layer_path_cache.get(0, (True, 0.0, False, False)) is None

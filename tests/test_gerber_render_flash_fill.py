"""The fill of the flashed pads: unions and holes.

Pads are macro apertures whose primitives overlap on purpose (a rounded
rectangle is two rectangles plus four corner circles).  The overlap has to
fill, and the primitives with the exposure turned off have to cut out of
the pad.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath  # noqa: E402

from services.gerber.gerber_render import (  # noqa: E402
    ApertureMacro, FlashShape, RenderData,
)
from services.gerber.render.layer import (  # noqa: E402
    TILE_MIN_ELEMENTS, build_layer_paths,
)
from ui.gerber_viewer import _add_flash  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _draw_flash_to_image(fl: FlashShape, size: int = 100):
    """Render one flash into a square image, the way a layer does.

    Returns the image and a probe that turns a path coordinate into a
    pixel, so the assertions do not have to count pixels.
    """
    path = QPainterPath()
    _add_flash(path, fl)
    assert path.elementCount() > 0
    bounds = path.boundingRect()
    assert bounds.width() > 0 and bounds.height() > 0
    side = max(bounds.width(), bounds.height())
    scale = (size - 10.0) / side

    def probe(px: float, py: float):
        return (int((px - bounds.left()) * scale) + 5,
                int((py - bounds.top()) * scale) + 5)

    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(255, 0, 0)))
    painter.translate(5, 5)
    painter.scale(scale, scale)
    painter.translate(-bounds.left(), -bounds.top())
    painter.drawPath(path)
    painter.end()
    return image, probe


def _alpha(image: QImage, x: int, y: int) -> int:
    return image.pixelColor(x, y).alpha()


def _roundrect_macro() -> ApertureMacro:
    """Two overlapping rectangles and four corner circles, exposure on.

    The shapes stand relative to the flash, exactly like the adapter
    leaves them for the renderer.
    """
    macro = ApertureMacro("ROUNDEDRECT")
    macro.polygons = [
        ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)),
        ((-0.6, -0.4), (0.6, -0.4), (0.6, 0.4), (-0.6, 0.4)),
    ]
    macro.circles = [(0.075, 0.075, 0.1), (-0.075, 0.075, 0.1),
                     (0.075, -0.075, 0.1), (-0.075, -0.075, 0.1)]
    return macro


def test_overlapping_macro_primitives_fill_their_union(qapp):
    image, probe = _draw_flash_to_image(FlashShape(
        kind="macro", macro=_roundrect_macro(),
        cx=0.0, cy=0.0, w=2.0, h=2.0))
    # The centre is covered by both rectangles: overlap has to fill.
    assert _alpha(image, *probe(0.0, 0.0)) == 255
    # A corner circle overlaps both rectangles: covered three times?
    # Still filled — the union is the pad, not the even count of it.
    assert _alpha(image, *probe(0.075, -0.075)) == 255


def test_macro_exposure_off_primitives_punch_holes(qapp):
    # End to end: exposure-off primitive → adapter → hole list → cut.
    from services.gerber.spec.adapter import _macro_from_shapes
    from services.gerber.spec.am_primitive import parse_macro_body

    macro = parse_macro_body("HOLED", [
        "1,1,2.0,0,0,0",   # disc, exposure on
        "1,0,0.8,0,0,0",   # circle in the middle, exposure off
    ])
    shapes = macro.evaluate()
    legacy = _macro_from_shapes(shapes)
    assert legacy.hole_circles  # the sink arrived as a hole
    image, probe = _draw_flash_to_image(FlashShape(
        kind="macro", macro=legacy, cx=0.0, cy=0.0, w=2.0, h=2.0))
    assert _alpha(image, *probe(0.0, 0.0)) == 0      # the middle is a hole
    assert _alpha(image, *probe(-0.8, 0.0)) == 255   # the ring stays


def test_macro_hole_list_shapes_punch_holes(qapp):
    # Disc with a hole that the adapter already separated out.
    macro = ApertureMacro()
    macro.circles = [(0.0, 0.0, 1.0)]
    macro.hole_circles.append((0.6, 0.0, 0.3))
    image, probe = _draw_flash_to_image(FlashShape(
        kind="macro", macro=macro, cx=0.0, cy=0.0, w=2.0, h=2.0))
    assert _alpha(image, *probe(0.6, 0.0)) == 0      # hole list cut it out
    assert _alpha(image, *probe(-0.8, 0.0)) == 255   # the disc stays


def test_region_polygon_with_holes_stays_empty_inside(qapp):
    outer = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
    hole = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    image, probe = _draw_flash_to_image(FlashShape(
        kind="polygon", pts=outer, holes=[hole],
        cx=0.0, cy=0.0))
    assert _alpha(image, *probe(0.0, 0.0)) == 0      # the hole
    assert _alpha(image, *probe(-0.9, 0.0)) == 255   # outer ring without hole
    assert _alpha(image, *probe(0.0, -0.9)) == 255


def test_plain_flash_paths_keep_their_winding(qapp):
    image, probe = _draw_flash_to_image(FlashShape(
        kind="rect", w=1.0, h=1.0, cx=0.0, cy=0.0))
    assert _alpha(image, *probe(0.0, 0.0)) == 255


# ----------------------------------------------------------------------
# the tiled grid keeps big shapes and big arcs
# ----------------------------------------------------------------------

def _min_tiling(monkeypatch):
    from services.gerber.render import layer as layer_module

    monkeypatch.setattr(layer_module, "TILE_MIN_ELEMENTS", 1)


def test_a_flash_bigger_than_a_tile_is_always_drawn(qapp, monkeypatch):
    _min_tiling(monkeypatch)
    data = RenderData()
    data.flashes.append(FlashShape(kind="rect", w=40.0, h=40.0,
                                   cx=30.0, cy=30.0))
    data.set_bbox((0.0, 0.0, 60.0, 60.0))
    paths = build_layer_paths(data, 0.0, False, 0.0, 0.0)
    assert paths.has_tiles
    assert paths.ops and paths.ops[0].tile == -1


def test_a_small_flash_sits_in_its_tile(qapp, monkeypatch):
    _min_tiling(monkeypatch)
    data = RenderData()
    data.flashes.append(FlashShape(kind="circle", cx=30.0, cy=30.0,
                                   w=0.5, h=0.5))
    data.set_bbox((0.0, 0.0, 60.0, 60.0))
    paths = build_layer_paths(data, 0.0, False, 0.0, 0.0)
    assert paths.has_tiles
    assert paths.ops and paths.ops[0].tile >= 0


def test_an_arc_wider_than_a_tile_is_always_drawn(qapp, monkeypatch):
    _min_tiling(monkeypatch)
    data = RenderData()
    from services.gerber.gerber_render import ArcShape

    # A tiny flash turns the tiling on: the walk counts lines and
    # flashes, so a layer of arcs alone has none.
    data.flashes.append(FlashShape(kind="circle", cx=50.0, cy=50.0,
                                   w=0.2, h=0.2))
    # Quarter circle of radius 20 mm: the bulge runs over a tile.
    data.arcs.append(ArcShape(x1=0.0, y1=0.0, x2=20.0, y2=20.0,
                              cx=0.0, cy=20.0, clockwise=False,
                              width=0.2))
    data.set_bbox((0.0, 0.0, 60.0, 60.0))
    paths = build_layer_paths(data, 0.0, False, 0.0, 0.0)
    assert paths.has_tiles
    stroke_ops = [op for op in paths.ops if not op.fill]
    assert stroke_ops and stroke_ops[0].tile == -1


# ----------------------------------------------------------------------
# G36 regions: the contours of one block stay together
# ----------------------------------------------------------------------

def test_region_contours_hold_together_with_holes(tmp_path):
    from services.gerber.spec.adapter import to_render_data
    from services.gerber.spec.loader import load

    path = tmp_path / "region.gbr"
    path.write_text(
        "%FSLAX34Y34*%\n%MOIN*%\n%LPD*%\n"
        "%ADD10C,0.010000*%\nD10*\n"
        "G36*\n"
        "X1000000Y1000000D02*\nX3000000Y1000000D01*\n"
        "X3000000Y3000000D01*\nX1000000Y3000000D01*\n"
        "X1000000Y1000000D01*\n"
        "X1500000Y1500000D02*\nX2500000Y1500000D01*\n"
        "X2500000Y2500000D01*\nX1500000Y2500000D01*\n"
        "X1500000Y1500000D01*\n"
        "G37*\nM02%\n",
        encoding="utf-8")
    result = load(str(path))
    assert result.ok
    data = to_render_data(result.image)
    polys = [fl for fl in data.flashes if fl.kind == "polygon"]
    assert len(polys) == 1
    assert polys[0].holes, "the second contour is a hole"
    assert len(polys[0].pts) == 5        # outer, closed
    assert len(polys[0].holes[0]) == 5   # hole, closed

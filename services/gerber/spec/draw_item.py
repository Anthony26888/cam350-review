"""Draw items produced by the spec parser.

A single flat item type covers everything the renderer has to draw.  It is
deliberately richer than the legacy ``LineShape``/``ArcShape``/``FlashShape``
triple because the legacy model could not express two things that matter:

* the polarity of a *stroked* primitive (only flashed primitives carried it),
* the true shape of a flashed aperture macro (it was flattened to a polygon
  list without the exposure information, so holes in a macro were lost).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .am_primitive import MacroShape

# Item kinds.
KIND_SEGMENT = "segment"
KIND_ARC = "arc"
KIND_CIRCLE = "circle"
KIND_RECT = "rect"
KIND_OBLONG = "oblong"
KIND_POLYGON = "polygon"
KIND_MACRO = "macro"

#: Kinds that are drawn as a filled area.
FILLED_KINDS = frozenset({KIND_CIRCLE, KIND_RECT, KIND_OBLONG, KIND_POLYGON, KIND_MACRO})


@dataclass(slots=True)
class DrawItem:
    """One drawable primitive.

    All coordinates are internal units (10 nm).  ``x``/``y`` is the start
    point of a segment or arc, and the centre of a flashed shape.
    """

    kind: str
    x: int = 0
    y: int = 0
    x2: int = 0
    y2: int = 0
    cx: int = 0
    cy: int = 0
    width: int = 0
    clockwise: bool = False
    diameter: int = 0
    height: int = 0
    rotation: float = 0.0
    points: tuple[tuple[int, int], ...] = ()
    macro_shapes: tuple[MacroShape, ...] = ()
    dcode: int = 0
    negative: bool = False
    attributes: dict = field(default_factory=dict)

    @property
    def filled(self) -> bool:
        return self.kind in FILLED_KINDS

    def bbox(self) -> tuple[int, int, int, int]:
        """Axis aligned bounding box in internal units.

        Stroked primitives include half of the pen width, so the box covers
        the artwork that is actually put on the board and not only the path
        the pen follows.
        """
        if self.kind == KIND_SEGMENT:
            half = self.width // 2
            return (min(self.x, self.x2) - half, min(self.y, self.y2) - half,
                    max(self.x, self.x2) + half, max(self.y, self.y2) + half)
        if self.kind == KIND_ARC:
            return self._arc_bbox()
        if self.kind == KIND_CIRCLE:
            r = self.diameter // 2
            return (self.x - r, self.y - r, self.x + r, self.y + r)
        if self.kind in (KIND_RECT, KIND_OBLONG):
            hw = self.diameter // 2
            hh = self.height // 2
            return (self.x - hw, self.y - hh, self.x + hw, self.y + hh)
        if self.kind == KIND_POLYGON:
            if not self.points:
                return (self.x, self.y, self.x, self.y)
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            return (min(xs), min(ys), max(xs), max(ys))
        if self.kind == KIND_MACRO:
            return self._macro_bbox()
        return (self.x, self.y, self.x, self.y)

    def _arc_radius(self) -> int:
        dx = self.x - self.cx
        dy = self.y - self.cy
        return int((dx * dx + dy * dy) ** 0.5)

    def _arc_bbox(self) -> tuple[int, int, int, int]:
        """Bounding box of the swept part of the arc, not of the whole circle."""
        import math

        half = self.width // 2
        dx = self.x - self.cx
        dy = self.y - self.cy
        radius = math.hypot(dx, dy)
        if radius <= 0:
            return (self.x - half, self.y - half, self.x + half, self.y + half)

        start = math.atan2(dy, dx)
        end = math.atan2(self.y2 - self.cy, self.x2 - self.cx)
        full = (self.x == self.x2 and self.y == self.y2)
        if self.clockwise:
            sweep = -((start - end) % (2.0 * math.pi))
        else:
            sweep = (end - start) % (2.0 * math.pi)
        if full:
            sweep = -2.0 * math.pi if self.clockwise else 2.0 * math.pi

        angles = [start, end]
        for quadrant in range(4):
            angle = quadrant * math.pi / 2.0
            if sweep > 0:
                inside = (angle - start) % (2.0 * math.pi) <= sweep + 1e-9
            else:
                inside = (start - angle) % (2.0 * math.pi) <= -sweep + 1e-9
            if inside:
                angles.append(angle)

        xs = [self.cx + radius * math.cos(a) for a in angles]
        ys = [self.cy + radius * math.sin(a) for a in angles]
        return (int(min(xs)) - half, int(min(ys)) - half,
                int(max(xs)) + half, int(max(ys)) + half)

    def _macro_bbox(self) -> tuple[int, int, int, int]:
        xs: list[float] = []
        ys: list[float] = []
        for shape in self.macro_shapes:
            if shape.kind == "circle":
                r = shape.diameter / 2.0
                xs.extend((shape.cx - r, shape.cx + r))
                ys.extend((shape.cy - r, shape.cy + r))
            else:
                for px, py in shape.points:
                    xs.append(px)
                    ys.append(py)
        if not xs:
            return (self.x, self.y, self.x, self.y)
        return (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))


def bounding_box(items: Iterable[DrawItem]) -> tuple[int, int, int, int] | None:
    """Union bounding box of a collection of items, in internal units."""
    minx = miny = None
    maxx = maxy = None
    for item in items:
        x1, y1, x2, y2 = item.bbox()
        if minx is None:
            minx, miny, maxx, maxy = x1, y1, x2, y2
            continue
        minx = min(minx, x1)
        miny = min(miny, y1)
        maxx = max(maxx, x2)
        maxy = max(maxy, y2)
    if minx is None:
        return None
    return (minx, miny, maxx, maxy)

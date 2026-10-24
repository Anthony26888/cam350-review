"""Find the shape of a layer that is under the pointer.

The Gerber format does not draw shapes one by one, it draws a picture with
a pen.  The viewer nevertheless wants to tell the user which aperture the
shape under the pointer was drawn with, the way the reference viewer does.

The search uses a grid over the layer, so that only the shapes near the
pointer have to be looked at.  The grid is built the first time it is
needed, because a layer that is only looked at does not pay for it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from services.gerber.gerber_render import RenderData
from services.gerber.gerber_transform import AffineTransform, apply_inverse_transform


@dataclass
class PickedShape:
    """The shape that is under the pointer."""

    #: The D code of the aperture the shape was drawn with.
    dcode: int = 0
    #: ``flash``, ``stroke`` or ``arc``.
    kind: str = ""
    #: How far the pointer is from the shape, in millimetres.
    distance: float = 0.0
    #: The place of the shape, in millimetres.
    x: float = 0.0
    y: float = 0.0
    #: The attributes of the object (%TO) or of the aperture (%TA).
    attributes: Dict[str, str] = field(default_factory=dict)


def _point_to_segment(px: float, py: float,
                       x1: float, y1: float, x2: float, y2: float) -> float:
    """The distance of a point from a line segment."""
    dx = x2 - x1
    dy = y2 - y1
    length = dx * dx + dy * dy
    if length <= 0.0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / length
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


class ApertureIndex:
    """The shapes of one layer, arranged for a quick search.

    The shapes are looked for in the coordinate system of the file, so the
    display transform is only used to go back from the place of the
    pointer to the place of the file.
    """

    #: The number of cells of the grid on each side.
    GRID = 64

    def __init__(self, render_data: RenderData,
                 mirror: bool = False, angle: float = 0.0,
                 off_x: float = 0.0, off_y: float = 0.0,
                 center: Tuple[float, float] = (0.0, 0.0),
                 mirror_x: bool = False):
        self._data = render_data
        self._mirror = mirror
        self._angle = angle
        self._off_x = off_x
        self._off_y = off_y
        self._center = center
        self._mirror_x = mirror_x
        self._cells: Dict[int, List[int]] = {}
        self._bounds: Optional[Tuple[float, float, float, float]] = None
        self._cell = 0.0
        self._columns = 1
        self._rows = 1
        self._built = False

    # ------------------------------------------------------------------
    def _build(self) -> None:
        """Put every shape into the cell it belongs to."""
        self._built = True
        data = self._data
        min_x = min_y = math.inf
        max_x = max_y = -math.inf
        for fl in data.flashes:
            half = max(fl.w, fl.h) / 2.0
            min_x = min(min_x, fl.cx - half)
            max_x = max(max_x, fl.cx + half)
            min_y = min(min_y, fl.cy - half)
            max_y = max(max_y, fl.cy + half)
        for ln in data.lines:
            min_x = min(min_x, ln.x1, ln.x2)
            max_x = max(max_x, ln.x1, ln.x2)
            min_y = min(min_y, ln.y1, ln.y2)
            max_y = max(max_y, ln.y1, ln.y2)
        for ar in data.arcs:
            min_x = min(min_x, ar.x1, ar.x2)
            max_x = max(max_x, ar.x1, ar.x2)
            min_y = min(min_y, ar.y1, ar.y2)
            max_y = max(max_y, ar.y1, ar.y2)
        if min_x > max_x or min_y > max_y:
            self._bounds = None
            return
        margin = max(max_x - min_x, max_y - min_y) * 0.01 + 1e-6
        min_x -= margin
        min_y -= margin
        max_x += margin
        max_y += margin
        self._bounds = (min_x, min_y, max_x, max_y)
        # The cells are square, so that the number of cells that have to be
        # looked at for a given radius does not depend on the shape of the
        # layer.
        self._cell = max(max_x - min_x, max_y - min_y) / self.GRID
        if self._cell <= 0.0:
            self._cell = 1.0
        self._columns = max(1, int(math.ceil((max_x - min_x) / self._cell)))
        self._rows = max(1, int(math.ceil((max_y - min_y) / self._cell)))

        cells = self._cells
        for index, fl in enumerate(data.flashes):
            half = max(fl.w, fl.h) / 2.0
            self._add(fl.cx - half, fl.cy - half, fl.cx + half, fl.cy + half,
                      ("flash", index))
        for index, ln in enumerate(data.lines):
            self._add(ln.x1, ln.y1, ln.x2, ln.y2, ("stroke", index))
        for index, ar in enumerate(data.arcs):
            self._add(ar.x1, ar.y1, ar.x2, ar.y2, ("arc", index))

    def _add(self, x1: float, y1: float, x2: float, y2: float,
             entry) -> None:
        """Put one shape into every cell it touches."""
        bounds = self._bounds
        if bounds is None:
            return
        min_x, min_y, _max_x, _max_y = bounds
        col1 = int((min(x1, x2) - min_x) / self._cell)
        col2 = int((max(x1, x2) - min_x) / self._cell)
        row1 = int((min(y1, y2) - min_y) / self._cell)
        row2 = int((max(y1, y2) - min_y) / self._cell)
        if col1 < 0:
            col1 = 0
        elif col1 >= self._columns:
            col1 = self._columns - 1
        if col2 < 0:
            col2 = 0
        elif col2 >= self._columns:
            col2 = self._columns - 1
        if row1 < 0:
            row1 = 0
        elif row1 >= self._rows:
            row1 = self._rows - 1
        if row2 < 0:
            row2 = 0
        elif row2 >= self._rows:
            row2 = self._rows - 1
        for row in range(row1, row2 + 1):
            base = row * self._columns
            for col in range(col1, col2 + 1):
                self._cells.setdefault(base + col, []).append(entry)

    # ------------------------------------------------------------------
    def to_file(self, x: float, y: float) -> Tuple[float, float]:
        """The place of the pointer in the coordinate system of the file."""
        return apply_inverse_transform(x, y, self._mirror, self._angle,
                                       self._off_x, self._off_y,
                                       self._center[0], self._center[1],
                                       self._mirror_x)

    def pick(self, x: float, y: float, radius: float = 0.12) -> Optional[PickedShape]:
        """The shape that is under the place, or None.

        The place is in the coordinate system of the file.
        """
        if not self._built:
            self._build()
        bounds = self._bounds
        if bounds is None:
            return None
        min_x, min_y, _max_x, _max_y = bounds
        col = int((x - min_x) / self._cell)
        row = int((y - min_y) / self._cell)
        if col < 0 or row < 0 or col >= self._columns or row >= self._rows:
            return None
        # A shape can reach into the cells next to the one of the pointer,
        # so every cell within the radius is looked at.
        reach = int(radius / self._cell) + 1
        best: Optional[PickedShape] = None
        for neighbour_row in range(max(0, row - reach), min(self._rows, row + reach + 1)):
            base = neighbour_row * self._columns
            for neighbour_col in range(max(0, col - reach),
                                       min(self._columns, col + reach + 1)):
                entries = self._cells.get(base + neighbour_col)
                if not entries:
                    continue
                for kind, index in entries:
                    found = self._check(kind, index, x, y, radius)
                    if found is None:
                        continue
                    if best is None or found.distance < best.distance:
                        best = found
        return best

    def _check(self, kind: str, index: int, x: float, y: float,
               radius: float) -> Optional[PickedShape]:
        data = self._data
        if kind == "flash":
            fl = data.flashes[index]
            distance = math.hypot(x - fl.cx, y - fl.cy)
            if distance > max(fl.w, fl.h) / 2.0 + radius:
                return None
            return PickedShape(dcode=fl.dcode, kind="flash", distance=distance,
                               x=fl.cx, y=fl.cy)
        if kind == "stroke":
            ln = data.lines[index]
            distance = _point_to_segment(x, y, ln.x1, ln.y1, ln.x2, ln.y2)
            if distance > ln.width / 2.0 + radius:
                return None
            return PickedShape(dcode=ln.dcode, kind="stroke", distance=distance,
                               x=ln.x1, y=ln.y1)
        ar = data.arcs[index]
        distance = _point_to_segment(x, y, ar.x1, ar.y1, ar.x2, ar.y2)
        if distance > ar.width / 2.0 + radius:
            return None
        return PickedShape(dcode=ar.dcode, kind="arc", distance=distance,
                           x=ar.x1, y=ar.y1)

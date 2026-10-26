"""Trace the copper that is connected to one pad.

A pad does not stand alone: the copper that touches it reaches other pads
of the same net.  This module walks the connected artwork of one copper
layer from a picked pad, the way a reference CAM tool marks the net.

The model is deliberately geometric and light: every primitive becomes a
small contact shape (a disc for a flash, a capsule for a stroke, a chain
of capsules for an arc), and a flood fill joins the shapes that touch.
Polarity matters: a *clear* object removes copper, so it never joins the
trace (an antipad cannot carry the net over the hole it carves).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from services.gerber.gerber_render import RenderData

#: The cells of the spatial hash, in millimetres.
_CELL = 5.0

#: How finely an arc is cut into capsules for the touch tests.
_ARC_STEP_DEG = 30.0


@dataclass
class TracedComponent:
    """One connected piece of copper of a layer.

    The members are indices into the collections of the ``RenderData``
    the trace ran on, so the caller can build a picture of the net from
    the very same shapes.
    """

    strokes: List[int] = field(default_factory=list)
    arcs: List[int] = field(default_factory=list)
    flashes: List[int] = field(default_factory=list)
    #: The flash the trace started from and the place it was picked by.
    seed_flash: int = -1
    seed_x: float = 0.0
    seed_y: float = 0.0
    is_plane: bool = False
    is_path: bool = False
    path_length: float = 0.0

    def count(self) -> int:
        return len(self.strokes) + len(self.arcs) + len(self.flashes)


def _flash_radius(fl) -> float:
    """The reach of a flash around its centre, for the pick test."""
    if fl.kind == "circle":
        return max(fl.w, 0.0) / 2.0
    if fl.kind in ("rect", "oblong"):
        # Every rotation reaches at most over the half diagonal.
        return math.hypot(fl.w, fl.h) / 2.0
    if fl.kind == "polygon" and fl.pts:
        xs = [p[0] - fl.cx for p in fl.pts]
        ys = [p[1] - fl.cy for p in fl.pts]
        return max((math.hypot(x, y) for x, y in zip(xs, ys)), default=0.0)
    if fl.kind == "macro":
        r = 0.0
        for mx, my, rad in (fl.macro.circles if fl.macro else []):
            r = max(r, math.hypot(mx, my) + rad)
        for pts in (fl.macro.polygons if fl.macro else []):
            for px, py in pts:
                r = max(r, math.hypot(px, py))
        for x1, y1, x2, y2, width in (fl.macro.segments if fl.macro else []):
            r = max(r, math.hypot(x1, y1) + width / 2.0,
                    math.hypot(x2, y2) + width / 2.0)
        return max(r, fl.w / 2.0, fl.h / 2.0)
    return max(fl.w, fl.h) / 2.0


def _polygon_area(pts) -> float:
    """The unsigned area of a closed chain of points (shoelace)."""
    total = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _point_in_contours(px: float, py: float, contours) -> bool:
    """Even-odd fill: inside when the contours cross the ray oddly."""
    inside = False
    for pts in contours:
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            if (y1 > py) != (y2 > py):
                t = (py - y1) / (y2 - y1)
                if x1 + t * (x2 - x1) > px:
                    inside = not inside
    return inside


def _contour_pieces(kind: str, index: int, pts, reach_cap: float = 0.0,
                    lattice: bool = True) -> List["_Primitive"]:
    """The contact pieces of a filled polygon: exact boundary capsules
    plus a coarse lattice of discs that covers the interior, so a stroke
    that runs through the middle of a big region still joins."""
    pieces: List[_Primitive] = []
    n = len(pts)
    if n < 2:
        return pieces
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if x1 == x2 and y1 == y2:
            continue
        pieces.append(_Primitive(kind, index, 0.0, seg=(x1, y1, x2, y2)))
    if not lattice:
        return pieces
    area = _polygon_area(pts)
    if area <= 0.0:
        return pieces
    step = max(0.9, math.sqrt(area / 64.0))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    radius = step * 0.45
    if reach_cap > 0.0:
        radius = min(radius, reach_cap)
    y0, y1 = min(ys), max(ys)
    x0, x1 = min(xs), max(xs)
    if x1 - x0 <= step and y1 - y0 <= step:
        # A small polygon is covered by one disc at its centre.
        cx, cy = sum(xs) / n, sum(ys) / n
        if _point_in_contours(cx, cy, [pts]):
            pieces.append(_Primitive(kind, index, radius, x=cx, y=cy))
        return pieces
    y = y0 + step * 0.5
    while y < y1:
        x = x0 + step * 0.5
        while x < x1:
            if _point_in_contours(x, y, [pts]):
                pieces.append(_Primitive(kind, index, radius, x=x, y=y))
            x += step
        y += step
    return pieces


def _flash_contact_shapes(i: int, fl) -> List["_Primitive"]:
    """The exact contact surface of one flash, in the frame of the file.

    A pad spans a real area: the reach that matters is its surface, not
    the reach of a bubble around the centre.  A big pour that covers half
    the board must not soften every trace within a huge radius, so the
    surface is broken into small pieces: the boundary as capsules with no
    width, plus a coarse lattice inside the area.
    """
    kind = fl.kind
    if kind == "circle":
        r = fl.w / 2.0
        if r <= 0.0:
            return []
        return [_Primitive("flash", i, r, x=fl.cx, y=fl.cy)]
    if kind in ("rect", "oblong"):
        w2, h2 = fl.w / 2.0, fl.h / 2.0
        a = math.radians(fl.rot)
        ca, sa = math.cos(a), math.sin(a)

        def to_world(lx: float, ly: float) -> Tuple[float, float]:
            return (fl.cx + lx * ca - ly * sa, fl.cy + lx * sa + ly * ca)

        corners = [(-w2, -h2), (w2, -h2), (w2, h2), (-w2, h2)]
        pts = [to_world(lx, ly) for lx, ly in corners]
        pieces = _contour_pieces("flash", i, pts, lattice=False)
        # The lattice of the body, so a stroke through the middle joins.
        step = max(0.9, math.sqrt(fl.w * fl.h / 64.0))
        radius = min(step * 0.45, min(w2, h2))
        x_stop = max(0.0, w2 - step * 0.5)
        y_stop = max(0.0, h2 - step * 0.5)
        lx = -x_stop
        while lx <= x_stop + 1e-9:
            ly = -y_stop
            while ly <= y_stop + 1e-9:
                gx, gy = to_world(lx, ly)
                pieces.append(_Primitive("flash", i, radius, x=gx, y=gy))
                ly += step
            lx += step
        # The round ends of an oblong reach past the body corners.
        if kind == "oblong" and fl.w > 0.0 and fl.h > 0.0:
            r = min(w2, h2)
            if r > 0.0:
                if fl.w >= fl.h:
                    for sign in (-1.0, 1.0):
                        gx, gy = to_world(sign * (w2 - r), 0.0)
                        pieces.append(_Primitive("flash", i, r, x=gx, y=gy))
                else:
                    for sign in (-1.0, 1.0):
                        gx, gy = to_world(0.0, sign * (h2 - r))
                        pieces.append(_Primitive("flash", i, r, x=gx, y=gy))
        return pieces
    if kind == "polygon" and fl.pts:
        if fl.pts_local:
            a = math.radians(fl.rot)
            ca, sa = math.cos(a), math.sin(a)
            pts = [(fl.cx + lx * ca - ly * sa, fl.cy + lx * sa + ly * ca)
                   for lx, ly in fl.pts]
        else:
            pts = list(fl.pts)
        pieces = _contour_pieces("flash", i, pts)
        # The contours that cut themselves out of the region carry the
        # edges of the copper around the hole too.
        for contour in (fl.holes or ()):
            pieces += _contour_pieces("flash", i, contour)
        return pieces
    if kind == "macro" and fl.macro:
        a = math.radians(fl.rot)
        ca, sa = math.cos(a), math.sin(a)

        def to_world(lx: float, ly: float) -> Tuple[float, float]:
            return (fl.cx + lx * ca - ly * sa, fl.cy + lx * sa + ly * ca)

        pieces: List[_Primitive] = []
        for mx, my, mr in fl.macro.circles:
            if mr <= 0.0:
                continue
            gx, gy = to_world(mx, my)
            pieces.append(_Primitive("flash", i, mr, x=gx, y=gy))
        for x1, y1, x2, y2, width in fl.macro.segments:
            gx1, gy1 = to_world(x1, y1)
            gx2, gy2 = to_world(x2, y2)
            half = width / 2.0
            if half <= 0.0:
                continue
            pieces.append(_Primitive("flash", i, half, seg=(gx1, gy1, gx2,
                                                            gy2)))
        for poly_pts in fl.macro.polygons:
            pts_local = [to_world(lx, ly) for lx, ly in poly_pts]
            pieces += _contour_pieces("flash", i, pts_local)
        return pieces
    return []


def _point_segment_distance(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    length2 = dx * dx + dy * dy
    if length2 <= 0.0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / length2
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _segment_distance(x1, y1, x2, y2, u1, v1, u2, v2) -> float:
    """The distance between two closed segments."""
    # When the segments cross, the distance is zero.
    def cross(ox, oy, ax, ay, bx, by):
        return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)

    d1 = cross(u1, v1, u2, v2, x1, y1)
    d2 = cross(u1, v1, u2, v2, x2, y2)
    d3 = cross(x1, y1, x2, y2, u1, v1)
    d4 = cross(x1, y1, x2, y2, u2, v2)
    if ((d1 > 0) != (d2 > 0) or d1 == 0 or d2 == 0) and \
            ((d3 > 0) != (d4 > 0) or d3 == 0 or d4 == 0):
        return 0.0
    return min(
        _point_segment_distance(x1, y1, u1, v1, u2, v2),
        _point_segment_distance(x2, y2, u1, v1, u2, v2),
        _point_segment_distance(u1, v1, x1, y1, x2, y2),
        _point_segment_distance(u2, v2, x1, y1, x2, y2),
    )


def _arc_chords(ar) -> List[Tuple[float, float, float, float, float]]:
    """Cut an arc into capsules: (x1, y1, x2, y2, width)."""
    radius = math.hypot(ar.x1 - ar.cx, ar.y1 - ar.cy)
    if radius <= 1e-9:
        return [(ar.x1, ar.y1, ar.x2, ar.y2, ar.width)]
    start = math.atan2(ar.y1 - ar.cy, ar.x1 - ar.cx)
    end = math.atan2(ar.y2 - ar.cy, ar.x2 - ar.cx)
    if ar.clockwise:
        sweep = -((start - end) % (2.0 * math.pi))
    else:
        sweep = (end - start) % (2.0 * math.pi)
    if abs(sweep) < 1e-12:
        sweep = -2.0 * math.pi if ar.clockwise else 2.0 * math.pi
    steps = max(2, int(math.ceil(abs(sweep) / math.radians(_ARC_STEP_DEG))))
    chords: List[Tuple[float, float, float, float, float]] = []
    px, py = ar.x1, ar.y1
    for index in range(1, steps + 1):
        angle = start + sweep * index / steps
        nx, ny = ar.cx + radius * math.cos(angle), ar.cy + radius * math.sin(angle)
        chords.append((px, py, nx, ny, ar.width))
        px, py = nx, ny
    return chords


@dataclass
class _Primitive:
    """One contact shape of the trace graph."""

    #: ``flash``, ``stroke`` or ``arc``.
    kind: str
    #: Index into the source collection.
    index: int
    radius: float
    seg: Optional[Tuple[float, float, float, float]] = None
    x: float = 0.0
    y: float = 0.0
    box: Optional[Tuple[float, float, float, float]] = None

    def _compute_box(self) -> Tuple[float, float, float, float]:
        if self.seg is None:
            return (self.x - self.radius, self.y - self.radius,
                    self.x + self.radius, self.y + self.radius)
        x1, y1, x2, y2 = self.seg
        r = self.radius
        return (min(x1, x2) - r, min(y1, y2) - r, max(x1, x2) + r,
                max(y1, y2) + r)

    def bounds(self) -> Tuple[float, float, float, float]:
        if self.box is None:
            self.box = self._compute_box()
        return self.box

    def touches(self, other: "_Primitive") -> bool:
        reach = self.radius + other.radius
        a_min_x, a_min_y, a_max_x, a_max_y = self.bounds()
        b_min_x, b_min_y, b_max_x, b_max_y = other.bounds()
        if a_max_x + reach < b_min_x or b_max_x + reach < a_min_x or \
                a_max_y + reach < b_min_y or b_max_y + reach < a_min_y:
            return False
        if self.kind == other.kind and self.index == other.index:
            return True  # Pieces of one body belong together.
        if self.seg is None and other.seg is None:
            return math.hypot(self.x - other.x,
                              self.y - other.y) <= reach
        if self.seg is not None and other.seg is not None:
            return _segment_distance(*self.seg, *other.seg) <= reach
        if self.seg is None:
            return _point_segment_distance(
                self.x, self.y, *other.seg) <= reach
        return _point_segment_distance(other.x, other.y, *self.seg) <= reach


class _TraceIndex:
    """The primitives of one layer, arranged for a quick flood fill."""

    def __init__(self) -> None:
        self._primitives: List[_Primitive] = []
        self._cells: dict = {}
        # One record per flash: the place to pick and the reach around it.
        self.seeds: List[Tuple[int, float, float, float]] = []
        # The contact pieces of every flash, so a pick can measure the
        # distance to the true surface instead of the bubble of the whole
        # shape — a big pour must not swallow the nearest pad pick.
        self.flash_pieces: Dict[int, List[_Primitive]] = {}
        # Polygon contours for exact point-in-polygon tests
        self.polygon_contours: Dict[int, Tuple[List[Tuple[float, float]], List[List[Tuple[float, float]]]]] = {}
        # Flashes that a trace already walked over: the net every flash
        # belongs to, so a repeated pick on one net answers at once.
        self.traced_flashes: Dict[int, "TracedComponent"] = {}
        self._bounds = None

    @staticmethod
    def _cell_range(bounds):
        min_x, min_y, max_x, max_y = bounds
        lo_x, hi_x = int(min_x // _CELL), int(max_x // _CELL)
        lo_y, hi_y = int(min_y // _CELL), int(max_y // _CELL)
        return ((lo_x, hi_x), (lo_y, hi_y))

    def add(self, primitive: _Primitive) -> None:
        self._primitives.append(primitive)
        key_index = len(self._primitives) - 1
        (lo_x, hi_x), (lo_y, hi_y) = self._cell_range(primitive.bounds())
        for cx in range(lo_x, hi_x + 1):
            for cy in range(lo_y, hi_y + 1):
                self._cells.setdefault((cx, cy), []).append(key_index)

    def near(self, primitive: _Primitive) -> List[_Primitive]:
        """The primitives that may touch the given one."""
        min_x, min_y, max_x, max_y = primitive.bounds()
        lo_x, hi_x = int(min_x // _CELL), int(max_x // _CELL)
        lo_y, hi_y = int(min_y // _CELL), int(max_y // _CELL)
        out: List[_Primitive] = []
        seen = set()
        for cx in range(lo_x, hi_x + 1):
            for cy in range(lo_y, hi_y + 1):
                for idx in self._cells.get((cx, cy), ()):
                    if idx in seen:
                        continue
                    seen.add(idx)
                    out.append(self._primitives[idx])
        return out

    def primitives(self) -> List[_Primitive]:
        return self._primitives


def build_index(data: RenderData) -> _TraceIndex:
    """The trace index of one copper layer."""
    index = _TraceIndex()
    lines = data.lines
    for i, ln in enumerate(lines):
        if ln.negative:
            continue
        index.add(_Primitive("stroke", i, max(ln.width, 0.10) / 2.0,
                             seg=(ln.x1, ln.y1, ln.x2, ln.y2)))
    for i, ar in enumerate(data.arcs):
        if ar.negative:
            continue
        for j, (x1, y1, x2, y2, width) in enumerate(_arc_chords(ar)):
            index.add(_Primitive("arc", i, max(width, 0.10) / 2.0,
                                 seg=(x1, y1, x2, y2)))
    for i, fl in enumerate(data.flashes):
        if fl.negative:
            continue
        pieces = _flash_contact_shapes(i, fl)
        reach = _flash_radius(fl)
        if pieces or reach > 0.0:
            index.seeds.append((i, fl.cx, fl.cy, reach))
        for piece in pieces:
            index.add(piece)
            index.flash_pieces.setdefault(i, []).append(piece)
        if fl.kind == "polygon" and fl.pts:
            if fl.pts_local:
                a = math.radians(fl.rot)
                ca, sa = math.cos(a), math.sin(a)
                outer = [(fl.cx + lx * ca - ly * sa, fl.cy + lx * sa + ly * ca)
                         for lx, ly in fl.pts]
            else:
                outer = list(fl.pts)
            holes = list(fl.holes or ())
            index.polygon_contours[i] = (outer, holes)
    return index


def _shape_point_distance(prim: _Primitive, px: float, py: float) -> float:
    """The distance from a point to the surface of a contact piece."""
    if prim.seg is None:
        d = math.hypot(prim.x - px, prim.y - py) - prim.radius
        return max(d, 0.0)
    d = _point_segment_distance(px, py, *prim.seg) - prim.radius
    return max(d, 0.0)


def pick_flash(index: _TraceIndex, px: float, py: float,
               tol: float = 1.0) -> Optional[int]:
    """The flash the click landed on: the nearest within its reach."""
    best = -1
    best_score = float("inf")
    for fl_index, cx, cy, reach in index.seeds:
        poly_data = index.polygon_contours.get(fl_index)
        if poly_data is not None:
            outer, holes = poly_data
            if _point_in_contours(px, py, [outer]):
                in_hole = False
                for h in holes:
                    if _point_in_contours(px, py, [h]):
                        in_hole = True
                        break
                if not in_hole:
                    # Point is strictly inside this polygon/plane!
                    # Give preference to smaller polygons (smaller reach)
                    score = max(reach, 0.0) * 1e-4
                    if score < best_score:
                        best_score = score
                        best = fl_index
                    continue

        pieces = index.flash_pieces.get(fl_index)
        if pieces:
            d = min(_shape_point_distance(prim, px, py)
                    for prim in pieces)
        else:
            d = math.hypot(cx - px, cy - py) - reach
        if d > tol:
            continue
        # A pad that spans an area ties with the point lattice of a big
        # pour: the smaller shape wins, so a click on a pad stays a pick
        # of the pad.
        score = d + max(reach, 0.0) * 1e-4
        if score < best_score:
            best_score = score
            best = fl_index
    if best >= 0:
        return best
    return None


def _closest_point_on_segment(px, py, x1, y1, x2, y2) -> Tuple[float, float]:
    dx, dy = x2 - x1, y2 - y1
    length2 = dx * dx + dy * dy
    if length2 <= 0.0:
        return x1, y1
    t = ((px - x1) * dx + (py - y1) * dy) / length2
    t = max(0.0, min(1.0, t))
    return x1 + t * dx, y1 + t * dy


def pick_seed(index: _TraceIndex, px: float, py: float,
              tol: float = 1.0) -> Optional[Tuple[str, int, float, float]]:
    """The primitive the click landed on.

    A flash wins over a stroke: a click between a pad and its wire
    starts at the pad.  The result carries the place that starts the
    trace: for a flash its centre, for a stroke the point on the line
    that sits closest to the click.
    """
    flash_hit = pick_flash(index, px, py, tol)
    if flash_hit is not None:
        for fl_index, cx, cy, _reach in index.seeds:
            if fl_index == flash_hit:
                return ("flash", flash_hit, cx, cy)
    best = None
    best_d = float("inf")
    best_point = (px, py)
    for prim in index.primitives():
        shell = prim.radius
        if prim.seg is None:
            d = math.hypot(prim.x - px, prim.y - py) - shell
            point = (prim.x, prim.y)
        else:
            point = _closest_point_on_segment(px, py, *prim.seg)
            d = math.hypot(point[0] - px, point[1] - py) - shell
        if d <= tol and d < best_d:
            best_d = d
            best = prim
            best_point = point
    if best is None:
        return None
    return (best.kind, best.index, best_point[0], best_point[1])


def is_copper_plane(data: RenderData, fl_index: int) -> bool:
    """True if the flash is a true copper plane / pour polygon rather than a pad.

    A true plane pour typically has an area >= 30.0 mm^2 (or spans at least 6mm on both axes),
    while SMT pads and thermal pads rarely exceed 25 mm^2 unless they are huge copper fills.
    """
    if fl_index < 0 or fl_index >= len(data.flashes):
        return False
    fl = data.flashes[fl_index]
    if fl.kind == "polygon" and fl.pts:
        xs = [p[0] for p in fl.pts]
        ys = [p[1] for p in fl.pts]
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        area = _polygon_area(fl.pts)
        # Big pours span significantly in both dimensions and have substantial area
        if area >= 30.0 and (w >= 5.0 and h >= 5.0):
            return True
        if area >= 60.0:
            return True
    return False


def _is_large_pour(data: RenderData, fl_index: int) -> bool:
    return is_copper_plane(data, fl_index)


def trace_component(data: RenderData,
                    px: float, py: float, tol: float = 1.0,
                    index: Optional[_TraceIndex] = None,
                    seed: Optional[Tuple[str, int, float, float]] = None,
                    limit_planes: bool = True,
                    ) -> Optional[TracedComponent]:
    """All copper that is connected to the place the click landed on.

    ``seed`` can carry the primitive a previous pick found, so a trace
    can start from an exact pad instead of a fresh search.
    """
    if index is None:
        index = build_index(data)
    if seed is None:
        seed = pick_seed(index, px, py, tol)
    if seed is None:
        return None
    kind, seed_index, seed_x, seed_y = seed
    # The trace of this pad already ran: the net stays the same, hand
    # the saved component over at once.
    if kind == "flash" and seed_index in index.traced_flashes:
        return index.traced_flashes[seed_index]
    target: Optional[_Primitive] = None
    for prim in index.primitives():
        if prim.kind == kind and prim.index == seed_index:
            target = prim
            if kind == "flash":
                break
    if target is None:
        return None

    component = TracedComponent(seed_flash=seed_index if kind == "flash"
                                else -1, seed_x=seed_x, seed_y=seed_y)
    seen = {id(target)}
    stack = [target]
    plane_encountered = False

    while stack:
        prim = stack.pop()
        if prim.kind == "flash":
            component.flashes.append(prim.index)
            if limit_planes and _is_large_pour(data, prim.index):
                plane_encountered = True
                component.is_plane = True
                # When reaching a massive pour, stop expanding through it to avoid spiderweb
                continue
        elif prim.kind == "stroke":
            component.strokes.append(prim.index)
        else:
            component.arcs.append(prim.index)
        for other in index.near(prim):
            if id(other) in seen:
                continue
            if other.touches(prim):
                seen.add(id(other))
                stack.append(other)

    # Keep a repeated arc out of the same component twice: every chord of
    # an arc belongs to one arc, and near() hands several of them.
    component.arcs = sorted(set(component.arcs))
    component.flashes = sorted(set(component.flashes))
    component.strokes = sorted(set(component.strokes))
    if not plane_encountered:
        for member in component.flashes:
            index.traced_flashes[member] = component
    return component


def find_shortest_path(data: RenderData,
                       src_seed: Tuple[str, int, float, float],
                       dst_seed: Tuple[str, int, float, float],
                       index: Optional[_TraceIndex] = None,
                       ) -> Optional[TracedComponent]:
    """Find the direct shortest path between two points using BFS on primitive graph."""
    if index is None:
        index = build_index(data)
    src_kind, src_idx, src_x, src_y = src_seed
    dst_kind, dst_idx, dst_x, dst_y = dst_seed

    start_prims = [p for p in index.primitives() if p.kind == src_kind and p.index == src_idx]
    dst_prims = {id(p) for p in index.primitives() if p.kind == dst_kind and p.index == dst_idx}
    if not start_prims or not dst_prims:
        return None

    from collections import deque
    queue = deque()
    visited = {}
    for p in start_prims:
        pid = id(p)
        visited[pid] = None  # None parent
        queue.append(p)

    target_hit = None
    while queue:
        curr = queue.popleft()
        if id(curr) in dst_prims:
            target_hit = curr
            break
        for other in index.near(curr):
            oid = id(other)
            if oid in visited:
                continue
            if other.touches(curr):
                visited[oid] = curr
                queue.append(other)

    if target_hit is None:
        return None

    # Reconstruct path from target_hit back to start
    path_prims = []
    curr = target_hit
    while curr is not None:
        path_prims.append(curr)
        curr = visited.get(id(curr))

    path_comp = TracedComponent(
        seed_flash=src_idx if src_kind == "flash" else -1,
        seed_x=src_x, seed_y=src_y,
        is_path=True,
    )
    tot_len = 0.0
    for p in path_prims:
        if p.kind == "flash":
            path_comp.flashes.append(p.index)
        elif p.kind == "stroke":
            path_comp.strokes.append(p.index)
            ln = data.lines[p.index]
            tot_len += math.hypot(ln.x2 - ln.x1, ln.y2 - ln.y1)
        else:
            path_comp.arcs.append(p.index)
            ar = data.arcs[p.index]
            radius = math.hypot(ar.x1 - ar.cx, ar.y1 - ar.cy)
            tot_len += radius * math.pi * 0.5  # estimate chord length

    path_comp.flashes = sorted(set(path_comp.flashes))
    path_comp.strokes = sorted(set(path_comp.strokes))
    path_comp.arcs = sorted(set(path_comp.arcs))
    path_comp.path_length = round(tot_len, 2)
    return path_comp

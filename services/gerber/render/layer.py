"""Layer compositing for the Gerber viewer.

A Gerber layer is not a flat picture: an object with *clear* polarity
removes the artwork underneath it.  The reference implementation therefore
draws the dark content first and then erases the clear content from it,
which is what a negative object means in the format.

Doing that with a boolean path operation is far too slow for a board with
a few hundred thousand primitives, so the layer is composited in an
offscreen buffer instead: the dark content is painted, the clear content is
painted with the ``Clear`` composition mode, and the result is blitted onto
the canvas.  The same mechanism handles negative *strokes*, which a boolean
path operation could not express at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QTransform,
)
from PySide6.QtWidgets import QGraphicsItem

from services.gerber.gerber_render import RenderData
from services.gerber.gerber_transform import AffineTransform, apply_transform

#: The number of tiles the content of a layer is split into.  A view that
#: shows a part of the layer only walks the tiles that are on the screen.
TILE_COLUMNS = 8
TILE_ROWS = 8

#: A layer with fewer elements is drawn as a whole.  The bookkeeping of
#: the tiles costs a little time when the layer is built, and it only pays
#: off for a layer that is big enough to be slow to walk.
TILE_MIN_ELEMENTS = 100000



@dataclass
class DrawOp:
    """One piece of a layer, in the order of the file.

    The order matters: a negative object removes the artwork that was
    drawn before it, and the artwork that comes after it stays.  A file
    of a copper layer holds a negative pour and the positive pads that
    lie on it, and the pads have to stay visible.
    """

    path: QPainterPath
    #: The width of the pen, zero for a filled shape.
    width: float = 0.0
    #: True when the shape is filled instead of stroked.
    fill: bool = False
    #: True when the shape removes the artwork underneath it.
    clear: bool = False
    #: The tile of the grid the shape belongs to, -1 when it is always
    #: drawn because it reaches over a border of the grid.
    tile: int = 0


@dataclass
class LayerPaths:
    """The content of one layer, in scene coordinates and in file order.

    The filled shapes are kept as one path per shape.  A single path with
    hundreds of thousands of elements is very slow to fill with
    antialiasing, because the rasteriser has to walk the whole path again
    for every scan line.

    The content is also split into a grid of tiles.  A view that shows a
    part of the layer only has to walk the tiles that are on the screen,
    which is what makes a zoomed view and the magnifier fast.
    """

    #: Everything that is drawn, in the order of the file.
    ops: List[DrawOp] = field(default_factory=list)

    #: The area the grid covers, and its shape.
    tile_rect: QRectF = field(default_factory=QRectF)
    tile_columns: int = 0
    tile_rows: int = 0

    @property
    def has_clear(self) -> bool:
        """True when the layer removes artwork and needs compositing."""
        return any(op.clear for op in self.ops)

    @property
    def has_tiles(self) -> bool:
        """True when the content is split into a grid of tiles."""
        return self.tile_columns > 0 and self.tile_rows > 0

    def bounds(self) -> QRectF:
        rect = QRectF()
        for op in self.ops:
            rect = rect.united(op.path.boundingRect())
        return rect

    def visible_tiles(self, rect: QRectF) -> range:
        """The tiles that can hold something inside the given area.

        The area is in scene coordinates.
        """
        if not self.has_tiles:
            return range(0)
        grid = self.tile_rect
        if grid.isEmpty():
            return range(0)
        cell_w = grid.width() / self.tile_columns
        cell_h = grid.height() / self.tile_rows
        if cell_w <= 0.0 or cell_h <= 0.0:
            return range(0)
        first_col = int((rect.left() - grid.left()) / cell_w)
        last_col = int((rect.right() - grid.left()) / cell_w)
        first_row = int((rect.top() - grid.top()) / cell_h)
        last_row = int((rect.bottom() - grid.top()) / cell_h)
        first_col = max(0, min(first_col, self.tile_columns - 1))
        last_col = max(0, min(last_col, self.tile_columns - 1))
        first_row = max(0, min(first_row, self.tile_rows - 1))
        last_row = max(0, min(last_row, self.tile_rows - 1))
        if last_col < first_col or last_row < first_row:
            return range(0)
        indices = []
        for row in range(first_row, last_row + 1):
            start = row * self.tile_columns
            for col in range(first_col, last_col + 1):
                indices.append(start + col)
        return indices


def _bucket(store: List[Tuple[QPainterPath, float]], path: QPainterPath, width: float) -> None:
    for existing, _w in store:
        if existing is path:
            return
    store.append((path, width))


def _stroke_buckets(paths: List[Tuple[QPainterPath, float]],
                     width: float,
                     add_line,
                     add_arc) -> None:
    """Group the strokes of one polarity by their pen width."""
    buckets: dict = {}
    for path, _w in paths:
        pass


def _grid_bounds(render_data: RenderData, transform: AffineTransform):
    """The area the tile grid covers, in scene coordinates.

    The corners of the layer are transformed, because a rotation makes the
    area of the layer bigger than the area of its bounding box.
    """
    bbox = render_data.bbox()
    if bbox is None:
        return None
    min_x, min_y, max_x, max_y = bbox
    corners = ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y))
    xs = []
    ys = []
    for x, y in corners:
        tx, ty = transform.apply(x, y)
        xs.append(tx)
        ys.append(-ty)
    left = min(xs)
    top = min(ys)
    right = max(xs)
    bottom = max(ys)
    margin = max(right - left, bottom - top) * 0.02
    return QRectF(left - margin, top - margin,
                   right - left + 2 * margin, bottom - top + 2 * margin)


def _runs_of(render_data: RenderData):
    """The parts of a layer in the order they are in.

    A file that was read by the reduced parser has no order; the parts
    are found from the polarity of the shapes then.
    """
    if render_data.runs:
        return render_data.runs
    runs = []
    counts = [0, 0, 0]
    clear = None
    ordered = []
    for kind_index, shapes in enumerate((render_data.lines, render_data.arcs,
                                        render_data.flashes)):
        for shape in shapes:
            ordered.append((getattr(shape, "seq", 0), kind_index, shape))
    ordered.sort(key=lambda entry: entry[0])
    for _seq, kind_index, shape in ordered:
        shape_clear = bool(shape.negative)
        if clear is None or shape_clear != clear:
            if clear is not None:
                runs.append((clear, counts[0], counts[1], counts[2]))
            clear = shape_clear
            counts = [0, 0, 0]
        counts[kind_index] += 1
    if clear is not None:
        runs.append((clear, counts[0], counts[1], counts[2]))
    return runs


def _stroke_paths_from_rows(
    rows,
    transform: AffineTransform,
    tile_count: int,
    columns: int,
    grid_rows: int,
    inv_cell_w: float,
    inv_cell_h: float,
    grid_left: float,
    grid_top: float,
    stride: int,
    buckets: dict,
    width_numbers: dict,
    width_of_number: list,
) -> List[Tuple[float, int, QPainterPath]]:
    """The stroke paths of one part of a file, from the flat arrays.

    The transform, the width and the tile of every stroke are worked out
    with arrays, so that a part with a few hundred thousand strokes does
    not cost a function call per stroke.  The paths come out in the order
    the loop over the objects would build them, and they hold the same
    points.
    """
    import numpy as np

    a11 = transform.a11
    a12 = transform.a12
    a21 = transform.a21
    a22 = transform.a22
    bx = transform.bx
    by = transform.by
    x1 = rows[:, 0]
    y1 = rows[:, 1]
    x2 = rows[:, 2]
    y2 = rows[:, 3]
    px1 = a11 * x1 + a12 * y1 + bx
    py1 = -(a21 * x1 + a22 * y1 + by)
    px2 = a11 * x2 + a12 * y2 + bx
    py2 = -(a21 * x2 + a22 * y2 + by)
    width = np.maximum(rows[:, 4], 0.002)
    if tile_count:
        col = ((px1 - grid_left) * inv_cell_w).astype(np.int64)
        np.clip(col, 0, columns - 1, out=col)
        row = ((-py1 - grid_top) * inv_cell_h).astype(np.int64)
        np.clip(row, 0, grid_rows - 1, out=row)
        col2 = ((px2 - grid_left) * inv_cell_w).astype(np.int64)
        np.clip(col2, 0, columns - 1, out=col2)
        row2 = ((-py2 - grid_top) * inv_cell_h).astype(np.int64)
        np.clip(row2, 0, grid_rows - 1, out=row2)
        tile = row * columns + col
        # A stroke that reaches over a border of the grid is always drawn,
        # so that it is not cut at the border.
        tile[(col2 != col) | (row2 != row)] = -1
    else:
        tile = np.zeros(len(rows), dtype=np.int64)

    uniq, number = np.unique(width, return_inverse=True)
    # The widths are numbered as the loop over the objects numbers them,
    # so that the arcs of the same width end up in the same path.
    numbers = np.empty(len(uniq), dtype=np.int64)
    for position, value in enumerate(uniq.tolist()):
        known = width_numbers.get(value)
        if known is None:
            known = len(width_numbers)
            width_numbers[value] = known
            width_of_number.append(value)
        numbers[position] = known
    key = numbers[number] * stride + (tile + 1)
    # One pass over the rows instead of a full-array scan per bucket: the
    # rows are grouped by their bucket with one stable sort, so a part
    # with a few hundred thousand strokes does not pay a scan per width.
    bucket_order = np.argsort(key, kind="stable")
    sorted_keys = key[bucket_order]
    starts = np.flatnonzero(np.r_[True, sorted_keys[1:] != sorted_keys[:-1]])
    # The buckets in the order they are met for the first time, so that
    # the paths come out in the order the loop over the objects gives.
    first_order = np.argsort(bucket_order[starts], kind="stable")
    px1_values = px1[bucket_order].tolist()
    py1_values = py1[bucket_order].tolist()
    px2_values = px2[bucket_order].tolist()
    py2_values = py2[bucket_order].tolist()
    for first_position in first_order.tolist():
        begin = int(starts[first_position])
        end = int(starts[first_position + 1]) \
            if first_position + 1 < len(starts) else len(sorted_keys)
        bucket = int(sorted_keys[begin])
        path = buckets.get(bucket)
        if path is None:
            path = QPainterPath()
            buckets[bucket] = path
        for position in range(begin, end):
            path.moveTo(px1_values[position], py1_values[position])
            path.lineTo(px2_values[position], py2_values[position])
    return []


def build_layer_paths(
    render_data: RenderData,
    angle: float,
    mirror: bool,
    off_x: float,
    off_y: float,
    mirror_x: bool = False,
    center: Tuple[float, float] = (0.0, 0.0),
) -> LayerPaths:
    """Build the content of a layer, in the order of the file.

    The geometry is transformed into scene coordinates the same way the
    strokes and the fills of the viewer are, so the result can be drawn
    directly.

    The transform is prepared once as a matrix and the pen width of a stroke
    is only rounded when a new bucket is opened.  A large layer holds a few
    hundred thousand strokes, and a function call per point was the largest
    part of the building time.

    The order of the file is kept: a negative object removes the artwork
    that was drawn before it, so the parts of a file with a negative pour
    and positive pads have to be drawn one after the other.
    """
    from ui.gerber_viewer import _add_flash

    result = LayerPaths()
    transform = AffineTransform(mirror, angle, off_x, off_y,
                                center[0], center[1], mirror_x)
    a11 = transform.a11
    a12 = transform.a12
    a21 = transform.a21
    a22 = transform.a22
    bx = transform.bx
    by = transform.by
    identity = transform.identity

    columns = 0
    rows = 0
    tile_count = 0
    inv_cell_w = 0.0
    inv_cell_h = 0.0
    grid_left = 0.0
    grid_top = 0.0
    if len(render_data.lines) + len(render_data.flashes) >= TILE_MIN_ELEMENTS:
        grid = _grid_bounds(render_data, transform)
        if grid is not None and grid.width() > 0.0 and grid.height() > 0.0:
            columns = TILE_COLUMNS
            rows = TILE_ROWS
            tile_count = columns * rows
            inv_cell_w = columns / grid.width()
            inv_cell_h = rows / grid.height()
            grid_left = grid.left()
            grid_top = grid.top()
            result.tile_rect = grid
            result.tile_columns = columns
            result.tile_rows = rows

    runs = _runs_of(render_data)

    line_at = 0
    arc_at = 0
    flash_at = 0
    for clear, n_lines, n_arcs, n_flashes in runs:
        # The strokes of this part, grouped by their pen width and their
        # tile, so that the rasteriser walks a small path at a time.  The
        # key is a number, so that no tuple is built for every stroke.
        buckets: dict = {}
        width_numbers: dict = {}
        width_of_number: list = []
        stride = tile_count + 2
        last_width = None
        last_number = 0
        stroke_array = render_data.stroke_array()
        if stroke_array is not None:
            # The strokes of a file that was read by the spec parser are
            # in flat arrays; the paths are built from them without a
            # call per stroke.
            stroke_rows = stroke_array[line_at:line_at + n_lines]
            if len(stroke_rows):
                _stroke_paths_from_rows(
                    stroke_rows, transform, tile_count, columns, rows,
                    inv_cell_w, inv_cell_h, grid_left, grid_top, stride,
                    buckets, width_numbers, width_of_number)
        else:
            for ln in render_data.lines[line_at:line_at + n_lines]:
                width = ln.width
                if width < 0.002:
                    width = 0.002
                x1 = ln.x1
                y1 = ln.y1
                x2 = ln.x2
                y2 = ln.y2
                if identity:
                    px1 = x1
                    py1 = -y1
                    px2 = x2
                    py2 = -y2
                else:
                    px1 = a11 * x1 + a12 * y1 + bx
                    py1 = -(a21 * x1 + a22 * y1 + by)
                    px2 = a11 * x2 + a12 * y2 + bx
                    py2 = -(a21 * x2 + a22 * y2 + by)
                if tile_count:
                    col = int((px1 - grid_left) * inv_cell_w)
                    row = int((py1 - grid_top) * inv_cell_h)
                    if col < 0:
                        col = 0
                    elif col >= columns:
                        col = columns - 1
                    if row < 0:
                        row = 0
                    elif row >= rows:
                        row = rows - 1
                    tile = row * columns + col
                    col2 = int((px2 - grid_left) * inv_cell_w)
                    row2 = int((py2 - grid_top) * inv_cell_h)
                    if col2 < 0:
                        col2 = 0
                    elif col2 >= columns:
                        col2 = columns - 1
                    if row2 < 0:
                        row2 = 0
                    elif row2 >= rows:
                        row2 = rows - 1
                    if col2 != col or row2 != row:
                        # A stroke that reaches over a border of the grid is
                        # always drawn, so that it is not cut at the border.
                        tile = -1
                else:
                    tile = 0
                if width != last_width:
                    number = width_numbers.get(width)
                    if number is None:
                        number = len(width_numbers)
                        width_numbers[width] = number
                        width_of_number.append(width)
                    last_width = width
                    last_number = number
                else:
                    number = last_number
                key = number * stride + (tile + 1)
                path = buckets.get(key)
                if path is None:
                    path = QPainterPath()
                    buckets[key] = path
                # Every stroke starts a new subpath, so that the pen puts its
                # cap at the end of the segment.  The reference implementation
                # draws the segments one by one as well, and joining them would
                # change the picture where two segments meet.
                path.moveTo(px1, py1)
                path.lineTo(px2, py2)
        for ar in render_data.arcs[arc_at:arc_at + n_arcs]:
            width = ar.width
            if width < 0.002:
                width = 0.002
            sx, sy = transform.apply(ar.x1, ar.y1)
            ex, ey = transform.apply(ar.x2, ar.y2)
            if tile_count:
                # An arc that bulges over the border of its cell is always
                # drawn: only the two ends of the arc are cheap to check,
                # so a big radius plays it safe.
                radius = math.hypot(ar.x1 - ar.cx, ar.y1 - ar.cy)
                if radius > 0.5 / min(inv_cell_w, inv_cell_h):
                    ar_tile = -1
                else:
                    ar_tile = None
                if ar_tile is None:
                    col = int((sx - grid_left) * inv_cell_w)
                    row = int((-sy - grid_top) * inv_cell_h)
                    if col < 0:
                        col = 0
                    elif col >= columns:
                        col = columns - 1
                    if row < 0:
                        row = 0
                    elif row >= rows:
                        row = rows - 1
                    ar_tile = row * columns + col
                    col2 = int((ex - grid_left) * inv_cell_w)
                    row2 = int((-ey - grid_top) * inv_cell_h)
                    if col2 < 0:
                        col2 = 0
                    elif col2 >= columns:
                        col2 = columns - 1
                    if row2 < 0:
                        row2 = 0
                    elif row2 >= rows:
                        row2 = rows - 1
                    if col2 != col or row2 != row:
                        ar_tile = -1
            else:
                ar_tile = 0
            if width != last_width:
                number = width_numbers.get(width)
                if number is None:
                    number = len(width_numbers)
                    width_numbers[width] = number
                    width_of_number.append(width)
                last_width = width
                last_number = number
            else:
                number = last_number
            key = number * stride + (ar_tile + 1)
            path = buckets.get(key)
            if path is None:
                path = QPainterPath()
                buckets[key] = path
            _append_arc(path, ar, mirror, angle, off_x, off_y,
                        center[0], center[1], mirror_x, transform=transform)
        for key, path in buckets.items():
            number, rest = divmod(key, stride)
            tile = rest - 1
            width = width_of_number[number]
            result.ops.append(DrawOp(path, width, False, clear, tile))

        # The flashed shapes, one path each, so that the fill of a shape
        # does not cost the walk over the whole layer.
        for fl in render_data.flashes[flash_at:flash_at + n_flashes]:
            path = QPainterPath()
            _add_flash(path, fl, mirror, angle, off_x, off_y,
                       center[0], center[1], mirror_x, transform=transform)
            if path.isEmpty():
                continue
            gx, gy = transform.apply(fl.cx, fl.cy)
            if tile_count:
                bounds = path.boundingRect()
                if (bounds.width() > 1.0 / inv_cell_w
                        or bounds.height() > 1.0 / inv_cell_h):
                    # A shape that is bigger than a tile is always drawn:
                    # it would be cut off if only its centre tile were
                    # drawn.
                    flash_tile = -1
                else:
                    col = int((gx - grid_left) * inv_cell_w)
                    row = int((-gy - grid_top) * inv_cell_h)
                    if col < 0:
                        col = 0
                    elif col >= columns:
                        col = columns - 1
                    if row < 0:
                        row = 0
                    elif row >= rows:
                        row = rows - 1
                    flash_tile = row * columns + col
            else:
                flash_tile = 0
            result.ops.append(DrawOp(path, 0.0, True, clear, flash_tile))

        line_at += n_lines
        arc_at += n_arcs
        flash_at += n_flashes
    return result



def _append_arc(path: QPainterPath, ar, mirror, angle, off_x, off_y,
                cx0, cy0, mirror_x, transform: AffineTransform | None = None) -> None:
    """Append an arc stroke, flattened into line segments.

    The segments are produced here instead of with ``QPainterPath.arcTo``
    because a path that mixes thousands of curves and lines is much more
    expensive for the rasteriser than a path that only has lines.

    The points of the arc are found by turning the radius vector with a
    constant angle, so no trigonometry is needed per point.
    """
    if transform is None:
        transform = AffineTransform(mirror, angle, off_x, off_y, cx0, cy0, mirror_x)
    sx, sy = transform.apply(ar.x1, ar.y1)
    ex, ey = transform.apply(ar.x2, ar.y2)
    cx, cy = transform.apply(ar.cx, ar.cy)
    radius = math.hypot(sx - cx, sy - cy)
    if radius <= 1e-9:
        path.moveTo(sx, -sy)
        path.lineTo(ex, -ey)
        return
    start = math.atan2(sy - cy, sx - cx)
    end = math.atan2(ey - cy, ex - cx)
    if ar.clockwise:
        sweep = -((start - end) % (2.0 * math.pi))
    else:
        sweep = (end - start) % (2.0 * math.pi)
    if abs(sweep) < 1e-12:
        # A closed arc is a full circle.
        sweep = -2.0 * math.pi if ar.clockwise else 2.0 * math.pi
    # 10 micrometre chord error.  The arc is flattened into line segments
    # because a path that mixes thousands of curves and lines is much more
    # expensive for the rasteriser than a path that only has lines.
    tolerance = 0.01
    denominator = max(1.0 - tolerance / radius, 0.0)
    step = math.acos(min(denominator, 1.0))
    steps = max(2, int(math.ceil(abs(sweep) / step)))
    turn = sweep / steps
    cos_turn = math.cos(turn)
    sin_turn = math.sin(turn)
    # The radius vector is turned by the same angle for every point, so the
    # trigonometry is done once instead of once per point.
    px = sx - cx
    py = sy - cy
    path.moveTo(sx, -sy)
    for _index in range(steps):
        px, py = (px * cos_turn - py * sin_turn,
                  px * sin_turn + py * cos_turn)
        path.lineTo(cx + px, -(cy + py))



class _RasterCache:
    """A small cache of rendered images.

    The key is the scale and the region an image covers, so the main view
    and the magnifier do not fight over the same entry.
    """

    def __init__(self, max_entries: int = 4):
        self._entries: dict = {}
        self._order: list = []
        self._max = max_entries

    @staticmethod
    def key(scale: float, rect: QRectF):
        return (round(scale, 5),
                round(rect.left(), 3), round(rect.top(), 3),
                round(rect.width(), 3), round(rect.height(), 3))

    def get(self, key):
        return self._entries.get(key)

    def put(self, key, value) -> None:
        if key in self._entries:
            self._order.remove(key)
        self._entries[key] = value
        self._order.append(key)
        while len(self._order) > self._max:
            self._entries.pop(self._order.pop(0), None)

    def clear(self) -> None:
        self._entries.clear()
        self._order.clear()


class LayerItem(QGraphicsItem):
    """One Gerber layer, composited the way the format requires.

    The layer is drawn dark first and the negative content is then erased
    from it, exactly like the negative objects of the format mean.

    The result is kept as an image, so that moving the pointer over a big
    layer does not draw it again.  The image is dropped when the view
    changes in a way that makes it wrong.
    """

    #: Extra room around the visible area, so that a small pan does not
    #: need a new image.
    CACHE_MARGIN = 0.10

    #: Largest edge of a cached image.
    MAX_IMAGE_SIZE = 4096

    #: A stroke that covers less than this many device pixels is cheap to
    #: draw with antialiasing.  Wider strokes make the antialiased stroker
    #: the bottleneck, and then the layer is drawn bigger and scaled down
    #: instead, which gives nearly the same picture for a fraction of the
    #: cost.
    ANTIALIASING_WIDTH_PX = 1.0

    #: How much bigger the image is drawn when the strokes are too wide.
    SUPERSAMPLE = 2

    def __init__(self, paths: LayerPaths, color: QColor, parent=None):
        super().__init__(parent)
        self._paths = paths
        self._color = QColor(color)
        self._bounds = paths.bounds()
        self._cache = _RasterCache()
        self._ink = self._ink_average()

    def _ink_average(self) -> float:
        """The average ink width over the stroke paths of the layer."""
        ink = 0.0
        count = 0
        for op in self._paths.ops:
            if op.fill:
                continue
            elements = max(1, op.path.elementCount())
            ink += op.width * elements
            count += elements
        if not count:
            return 0.0
        return ink / count

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor) -> None:
        """Give the layer its colour, without throwing the pictures away.

        The rendered images hold the artwork with an opaque colour and
        the transparency is applied when they are drawn, so only a change
        of the colour itself (the red, green and blue) makes the images
        wrong.  A change of the alpha alone (dimmed or active) keeps the
        images: the biggest cause of a heavy redraw after a small click
        of the user disappears with this.
        """
        red = color.red()
        green = color.green()
        blue = color.blue()
        changed = (red != self._color.red() or green != self._color.green()
                   or blue != self._color.blue())
        self._color = QColor(color)
        if changed:
            self._cache.clear()
        self.update()

    def set_paths(self, paths: LayerPaths) -> None:
        self._paths = paths
        self._bounds = paths.bounds()
        self._ink = self._ink_average()
        self._cache.clear()
        self.update()

    def set_paths(self, paths: LayerPaths) -> None:
        self._paths = paths
        self._bounds = paths.bounds()
        self._cache.clear()
        self.update()

    # The viewer changes the colour of a layer through the pen or the brush
    # of the scene item, so both are accepted here.
    def setBrush(self, brush) -> None:
        color = brush.color() if hasattr(brush, "color") else None
        if color is not None:
            self.set_color(color)

    def pen(self) -> QPen:
        return QPen(self._color)

    def setPen(self, pen) -> None:
        color = pen.color() if hasattr(pen, "color") else None
        if color is not None:
            self.set_color(color)

    def boundingRect(self) -> QRectF:
        return self._bounds

    def _quality(self, scale: float) -> tuple[int, bool]:
        """How the layer has to be drawn at the given scale.

        Returns the supersampling factor and whether antialiasing is used.
        The antialiased stroker of a very large path is by far the most
        expensive part of the drawing, but it only becomes expensive when
        the strokes cover several device pixels.  The average ink width
        was measured once when the paths came in, so the walk over every
        path no longer happens per picture.
        """
        ink = self._ink
        if ink <= 0.0:
            return (1, True)
        if ink * scale >= self.ANTIALIASING_WIDTH_PX:
            return (self.SUPERSAMPLE, False)
        return (1, True)


    def _render(self, scene_rect: QRectF, scale: float):
        """Draw the layer into an image that covers the given area.

        The image holds the artwork with an opaque colour.  The
        transparency of the layer is applied when the image is drawn, so
        that shapes which overlap each other do not blend twice.

        The parts are drawn in the order of the file, so that a negative
        object removes the artwork that was drawn before it.  Only the
        tiles that are inside the area are drawn: the rasteriser has to
        walk the whole path for every scan line, so a view that shows a
        small part of a large layer is much faster this way.
        """
        supersample, antialias = self._quality(scale)
        effective = scale * supersample
        longest = max(scene_rect.width(), scene_rect.height())
        if longest * effective > self.MAX_IMAGE_SIZE:
            effective = self.MAX_IMAGE_SIZE / max(longest, 1e-9)
        width = max(1, int(round(scene_rect.width() * effective)))
        height = max(1, int(round(scene_rect.height() * effective)))

        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        buf = QPainter(image)
        buf.setRenderHint(QPainter.RenderHint.Antialiasing, antialias)
        buf.scale(effective, effective)
        buf.translate(-scene_rect.left(), -scene_rect.top())
        opaque = QColor(self._color)
        opaque.setAlpha(255)

        paths = self._paths
        visible = None
        if paths.has_tiles:
            visible = set(paths.visible_tiles(scene_rect))
        current_clear = None
        current_fill = None
        current_width = None
        for op in paths.ops:
            if visible is not None and op.tile >= 0 and op.tile not in visible:
                continue
            if op.clear != current_clear:
                current_clear = op.clear
                buf.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_Clear
                    if op.clear else
                    QPainter.CompositionMode.CompositionMode_SourceOver)
            if op.fill:
                if current_fill is not True:
                    current_fill = True
                    buf.setPen(Qt.PenStyle.NoPen)
                    buf.setBrush(QBrush(opaque))
                buf.drawPath(op.path)
            else:
                if current_fill is not False or current_width != op.width:
                    current_fill = False
                    current_width = op.width
                    buf.setPen(QPen(opaque, op.width))
                    buf.setBrush(Qt.BrushStyle.NoBrush)
                buf.drawPath(op.path)
        buf.end()
        return (image, scene_rect)


    def paint(self, painter: QPainter, option, widget=None) -> None:
        device_rect = painter.viewport()
        if device_rect.isEmpty():
            # Not attached to a widget: fall back to the paint device.
            device_rect = QRectF(painter.device().rect())
        if device_rect.isEmpty():
            return
        transform = painter.transform()
        scale = abs(transform.m11())
        if scale <= 0:
            return

        inverse, _ok = transform.inverted()
        visible = inverse.mapRect(QRectF(device_rect))
        margin = max(visible.width(), visible.height()) * self.CACHE_MARGIN
        wanted = visible.adjusted(-margin, -margin, margin, margin)

        key = _RasterCache.key(scale, wanted)
        entry = self._cache.get(key)
        if entry is None:
            entry = self._render(wanted, scale)
            self._cache.put(key, entry)
        image, scene_rect = entry

        target = transform.mapRect(QRectF(scene_rect))
        painter.save()
        painter.resetTransform()
        # The image holds the artwork with an opaque colour, the
        # transparency of the layer is applied here.
        painter.setOpacity(self._color.alpha() / 255.0)
        painter.drawImage(target, image)
        painter.restore()


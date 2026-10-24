"""Adapter from the spec engine model to the render model of the viewer.

The viewer still draws with ``QPainterPath`` items, so the geometry the spec
engine produces is converted into the ``RenderData`` structure the renderer
consumes.  The conversion is lossless for everything the renderer can
express, and it keeps the information the renderer does not use yet (the
holes of an aperture macro, the polarity of a stroke) so the next renderer
can pick it up.
"""

from __future__ import annotations

import itertools
import math

from services.gerber.gerber_render import (
    ApertureInfo,
    ApertureMacro,
    ArcShape,
    FlashShape,
    RenderData,
)

from .draw_item import (
    KIND_ARC,
    KIND_CIRCLE,
    KIND_MACRO,
    KIND_OBLONG,
    KIND_POLYGON,
    KIND_RECT,
    KIND_SEGMENT,
)
from .am_primitive import MacroShape
from .file_image import FileImage
from .units import IU_PER_MM

#: Number of sides used when a circle has to become a polygon.
CIRCLE_SEGMENTS = 48


def _to_mm(value: int) -> float:
    return value / IU_PER_MM


def _macro_from_shapes(shapes) -> ApertureMacro:
    """Convert evaluated macro shapes into the aperture macro structure."""
    circles: list[tuple[float, float, float]] = []
    polygons: list[list[tuple[float, float]]] = []
    segments: list[tuple[float, float, float, float, float]] = []
    holes_circles: list[tuple[float, float, float]] = []
    holes_polygons: list[list[tuple[float, float]]] = []
    for shape in shapes:
        if shape.kind == "circle":
            entry = (shape.cx, shape.cy, shape.diameter / 2.0)
            if shape.exposure:
                circles.append(entry)
            else:
                holes_circles.append(entry)
        else:
            pts = [(px, py) for px, py in shape.points]
            if shape.exposure:
                polygons.append(pts)
            else:
                holes_polygons.append(pts)
    macro = ApertureMacro()
    macro.circles = circles
    macro.polygons = polygons
    macro.segments = segments
    macro.hole_circles = holes_circles
    macro.hole_polygons = holes_polygons
    return macro


def _circle_to_polygon(cx: float, cy: float, diameter: float) -> list[tuple[float, float]]:
    radius = diameter / 2.0
    return [
        (cx + radius * math.cos(2.0 * math.pi * i / CIRCLE_SEGMENTS),
         cy + radius * math.sin(2.0 * math.pi * i / CIRCLE_SEGMENTS))
        for i in range(CIRCLE_SEGMENTS)
    ]


def drill_to_render_data(drill) -> RenderData:
    """Convert a parsed drill file into the viewer's render model.

    A hole becomes a flashed circle with the diameter of its tool, a slot
    becomes the rounded shape that is milled.
    """
    data = RenderData()
    for hole in drill.holes:
        data.flashes.append(FlashShape(
            cx=_to_mm(hole.x), cy=_to_mm(hole.y),
            kind="circle",
            w=_to_mm(hole.diameter), h=_to_mm(hole.diameter),
        ))
    for slot in drill.slots:
        data.flashes.append(FlashShape(
            cx=_to_mm((slot.x1 + slot.x2) // 2),
            cy=_to_mm((slot.y1 + slot.y2) // 2),
            kind="polygon",
            pts=_slot_points(slot),
        ))
    return data


def _slot_points(slot) -> list[tuple[float, float]]:
    """The outline of a milled slot: a rectangle with two half circles."""
    radius = slot.diameter / 2.0
    x1, y1 = slot.x1 - radius, slot.y1 - radius
    x2, y2 = slot.x2 + radius, slot.y2 + radius
    points: list[tuple[float, float]] = []
    steps = 16
    for index in range(steps + 1):
        angle = math.pi / 2.0 * index / steps
        points.append((x2 + radius * math.cos(angle), y2 + radius * math.sin(angle)))
    for index in range(steps + 1):
        angle = math.pi / 2.0 + math.pi / 2.0 * index / steps
        points.append((x1 + radius * math.cos(angle), y1 + radius * math.sin(angle)))
    return [(px / IU_PER_MM, py / IU_PER_MM) for px, py in points]


def _stroke_array(rows) -> Optional[Any]:
    """The strokes of a layer as flat arrays.

    The rows are the four coordinates, the width, the polarity and the
    D code of every stroke.  The numbers are read one after the other:
    that is twice as fast as handing the rows to numpy as they are.
    """
    if not rows:
        return None
    import itertools

    import numpy as np

    return np.fromiter(
        itertools.chain.from_iterable(rows), dtype=np.float64,
        count=len(rows) * 7).reshape(len(rows), 7)


def _stroke_array_of(lines) -> Optional[Any]:
    """The strokes of a layer as flat arrays, from the stroke objects."""
    rows = [
        (line.x1, line.y1, line.x2, line.y2, line.width,
         1.0 if line.negative else 0.0, float(line.dcode))
        for line in lines
    ]
    return _stroke_array(rows)


def to_render_data(image: FileImage) -> RenderData:
    """Convert a parsed Gerber file into the viewer's render model.

    The strokes are the bulk of a file, so they are converted with a single
    pass and positional arguments: building a few hundred thousand objects
    with keywords is measurably slower.
    """
    data = RenderData()
    # The strokes are the bulk of a file.  They are collected as plain
    # numbers and turned into flat arrays at the end: a file with a few
    # hundred thousand strokes would cost a few hundred thousand objects
    # otherwise, and the objects are only needed by the tools that ask
    # for them.
    segments = []
    arcs = []
    flashes = []
    # The parts of the file in the order they are in.  A negative object
    # removes the artwork that was drawn before it, so the order has to be
    # kept.
    runs = []
    run_clear = None
    run_lines = 0
    run_arcs = 0
    run_flashes = 0

    for item in image.items:
        kind = item.kind
        clear = bool(item.negative)
        if run_clear is None or clear != run_clear:
            if run_clear is not None:
                runs.append((run_clear, run_lines, run_arcs, run_flashes))
            run_clear = clear
            run_lines = 0
            run_arcs = 0
            run_flashes = 0
        if kind == KIND_SEGMENT:
            segments.append((
                item.x, item.y, item.x2, item.y2, item.width,
                1.0 if item.negative else 0.0, float(item.dcode),
            ))
            run_lines += 1
        elif kind == KIND_ARC:
            arcs.append(ArcShape(
                item.x / IU_PER_MM, item.y / IU_PER_MM,
                item.x2 / IU_PER_MM, item.y2 / IU_PER_MM,
                item.cx / IU_PER_MM, item.cy / IU_PER_MM,
                item.clockwise,
                item.width / IU_PER_MM,
                item.negative,
                item.dcode,
            ))
            run_arcs += 1
        elif kind == KIND_CIRCLE:
            flashes.append(FlashShape(
                cx=item.x / IU_PER_MM, cy=item.y / IU_PER_MM,
                kind="circle",
                w=item.diameter / IU_PER_MM, h=item.diameter / IU_PER_MM,
                negative=item.negative,
                dcode=item.dcode,
            ))
            run_flashes += 1
        elif kind == KIND_RECT:
            flashes.append(FlashShape(
                cx=item.x / IU_PER_MM, cy=item.y / IU_PER_MM,
                kind="rect",
                w=item.diameter / IU_PER_MM, h=item.height / IU_PER_MM,
                rot=item.rotation,
                negative=item.negative,
                dcode=item.dcode,
            ))
            run_flashes += 1
        elif kind == KIND_OBLONG:
            flashes.append(FlashShape(
                cx=item.x / IU_PER_MM, cy=item.y / IU_PER_MM,
                kind="oblong",
                w=item.diameter / IU_PER_MM, h=item.height / IU_PER_MM,
                rot=item.rotation,
                negative=item.negative,
                dcode=item.dcode,
            ))
            run_flashes += 1
        elif kind == KIND_POLYGON:
            flashes.append(FlashShape(
                cx=item.x / IU_PER_MM, cy=item.y / IU_PER_MM,
                kind="polygon",
                pts=[(px / IU_PER_MM, py / IU_PER_MM) for px, py in item.points],
                negative=item.negative,
                dcode=item.dcode,
            ))
            run_flashes += 1
        elif kind == KIND_MACRO:
            # The macro shapes are stored in absolute internal units, the
            # renderer expects them relative to the flash position and in
            # millimetres.
            local = []
            for shape in item.macro_shapes:
                if shape.kind == "circle":
                    local.append(MacroShape(
                        shape.kind, shape.exposure,
                        (shape.cx - item.x) / IU_PER_MM,
                        (shape.cy - item.y) / IU_PER_MM,
                        shape.diameter / IU_PER_MM, shape.points))
                else:
                    local.append(MacroShape(
                        shape.kind, shape.exposure,
                        0.0, 0.0, 0.0,
                        tuple(((px - item.x) / IU_PER_MM, (py - item.y) / IU_PER_MM)
                              for px, py in shape.points)))
            flashes.append(FlashShape(
                cx=item.x / IU_PER_MM, cy=item.y / IU_PER_MM,
                kind="macro",
                macro=_macro_from_shapes(local),
                negative=item.negative,
                dcode=item.dcode,
            ))
            run_flashes += 1

    if run_clear is not None:
        runs.append((run_clear, run_lines, run_arcs, run_flashes))
    data.runs = runs
    if segments:
        # The strokes of the file are in millimetres already.
        import numpy as np

        array = np.fromiter(
            itertools.chain.from_iterable(segments), dtype=np.float64,
            count=len(segments) * 7).reshape(len(segments), 7)
        array[:, :5] /= IU_PER_MM
        data.set_stroke_array(array)
    data.arcs = arcs
    data.flashes = flashes
    # The apertures of the file, so that the viewer can tell which one
    # a shape was drawn with.
    for number, aperture in image.apertures.items():
        data.apertures[number] = ApertureInfo(
            number=number,
            kind=aperture.kind,
            params=tuple(aperture.params),
            attributes=dict(aperture.attributes),
            macro_name=(aperture.macro.name if aperture.macro else ""),
        )
    # The area of the layer is known while the items are converted, and
    # handing it over saves walking every primitive a second time.
    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    scale = 1.0 / IU_PER_MM
    for item in image.items:
        x = item.x * scale
        y = item.y * scale
        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        if y > max_y:
            max_y = y
        if item.kind in (KIND_SEGMENT, KIND_ARC):
            x2 = item.x2 * scale
            y2 = item.y2 * scale
            if x2 < min_x:
                min_x = x2
            if x2 > max_x:
                max_x = x2
            if y2 < min_y:
                min_y = y2
            if y2 > max_y:
                max_y = y2
        elif item.kind in (KIND_CIRCLE, KIND_RECT, KIND_OBLONG):
            half_w = item.diameter * scale / 2.0
            half_h = item.height * scale / 2.0
            if x - half_w < min_x:
                min_x = x - half_w
            if x + half_w > max_x:
                max_x = x + half_w
            if y - half_h < min_y:
                min_y = y - half_h
            if y + half_h > max_y:
                max_y = y + half_h
    if min_x > max_x or min_y > max_y:
        min_x = min_y = max_x = max_y = 0.0
    data.set_bbox((min_x, min_y, max_x, max_y))
    return data

"""Gerber -> RenderData conversion backed by the gerbonara library.

This module is the only place that imports gerbonara. It converts gerbonara's
graphic primitives into the lightweight RenderData model used by the viewer.
The legacy parser (gerber_render.parse_render) remains as a fallback.
"""
import math
import warnings
from typing import List

from .gerber_render import ArcShape, FlashShape, LineShape, RenderData


def parse_render_std(path: str) -> RenderData:
    """Parse a Gerber file using gerbonara into RenderData (coordinates in mm)."""
    from gerbonara import GerberFile
    from gerbonara.graphic_primitives import (
        Arc as GpArc,
        ArcPoly,
        Circle,
        Line as GpLine,
        Rectangle,
    )

    data = RenderData()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        file = GerberFile.open(path)

    for obj in file.objects:
        for prim in obj.to_primitives("mm"):
            if isinstance(prim, GpLine):
                data.lines.append(LineShape(
                    prim.x1, prim.y1, prim.x2, prim.y2,
                    prim.width, negative=not prim.polarity_dark,
                ))
            elif isinstance(prim, GpArc):
                data.arcs.append(ArcShape(
                    prim.x1, prim.y1, prim.x2, prim.y2,
                    prim.cx, prim.cy, prim.clockwise, prim.width,
                    negative=not prim.polarity_dark,
                ))
            elif isinstance(prim, Circle):
                data.flashes.append(FlashShape(
                    prim.x, prim.y, kind="circle",
                    w=2.0 * prim.r, h=2.0 * prim.r,
                    negative=not prim.polarity_dark,
                ))
            elif isinstance(prim, Rectangle):
                data.flashes.append(FlashShape(
                    prim.x, prim.y, kind="rect",
                    w=prim.w, h=prim.h, rot=math.degrees(prim.rotation),
                    negative=not prim.polarity_dark,
                ))
            elif isinstance(prim, ArcPoly):
                pts: List[tuple] = list(prim.outline)
                if pts and pts[0] == pts[-1]:
                    pts = pts[:-1]
                data.flashes.append(FlashShape(
                    0.0, 0.0, kind="polygon", pts=pts,
                    negative=not prim.polarity_dark,
                ))
    return data


def parse_layer(path: str) -> RenderData:
    """Parse with gerbonara, falling back to the legacy parser on failure."""
    try:
        return parse_render_std(path)
    except Exception:
        from .gerber_render import parse_render

        return parse_render(path)

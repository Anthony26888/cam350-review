"""Aperture (D code) definitions.

An aperture describes the shape that is flashed at a D03 command, or the pen
that is used for a D01 draw.  The standard apertures are circle, rectangle,
obround and polygon; anything else is an aperture macro.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .am_primitive import ApertureMacro, MacroShape

APERTURE_CIRCLE = "circle"
APERTURE_RECT = "rect"
APERTURE_OBLONG = "obround"
APERTURE_POLYGON = "polygon"
APERTURE_MACRO = "macro"


@dataclass
class DCode:
    """One aperture definition."""

    number: int
    kind: str
    params: tuple[float, ...] = ()
    hole: tuple[float, ...] = ()
    macro: ApertureMacro | None = None
    attributes: dict = field(default_factory=dict)
    _shapes: list[MacroShape] | None = field(default=None, repr=False, compare=False)

    # -- geometry ---------------------------------------------------------
    def line_width(self) -> float:
        """Nominal pen width used when this aperture strokes a D01."""
        if self.kind == APERTURE_CIRCLE:
            return self.params[0] if self.params else 0.0
        if self.kind in (APERTURE_RECT, APERTURE_OBLONG):
            return min(self.params[0], self.params[1]) if len(self.params) >= 2 else 0.0
        if self.kind == APERTURE_POLYGON:
            # The template is P,<diameter>X<vertices>X<rotation>.
            return self.params[0] if self.params else 0.0
        return 0.0

    def shapes_at(self, x: float, y: float) -> list[MacroShape]:
        """Resolved outline of the aperture, placed at ``(x, y)``.

        The result is cached: an aperture is expanded once and then reused for
        every flash, which is what the legacy renderer did *not* do.
        """
        if self.kind != APERTURE_MACRO:
            return self._standard_shapes(x, y)
        if self._shapes is None:
            self._shapes = self.macro.evaluate() if self.macro else []
        return [s.translated(x, y) for s in self._shapes]

    def _standard_shapes(self, x: float, y: float) -> list[MacroShape]:
        import math

        shapes: list[MacroShape] = []
        if self.kind == APERTURE_CIRCLE:
            diameter = self.params[0] if self.params else 0.0
            shapes.append(MacroShape("circle", True, x, y, diameter))
        elif self.kind in (APERTURE_RECT, APERTURE_OBLONG):
            width = self.params[0] if self.params else 0.0
            height = self.params[1] if len(self.params) > 1 else width
            if self.kind == APERTURE_OBLONG and width != height:
                # Obround: a rectangle capped by two half circles.
                r = min(width, height) / 2.0
                straight = abs(width - height)
                if width > height:
                    cx = x - (straight / 2.0) + r
                    shapes.append(MacroShape("circle", True, cx, y, height))
                    shapes.append(MacroShape("circle", True, cx + straight, y, height))
                    shapes.append(MacroShape("polygon", True, points=(
                        (cx, y - r), (cx + straight, y - r),
                        (cx + straight, y + r), (cx, y + r))))
                else:
                    cy = y - (straight / 2.0) + r
                    shapes.append(MacroShape("circle", True, x, cy, width))
                    shapes.append(MacroShape("circle", True, x, cy + straight, width))
                    shapes.append(MacroShape("polygon", True, points=(
                        (x - r, cy), (x + r, cy),
                        (x + r, cy + straight), (x - r, cy + straight))))
            else:
                hw, hh = width / 2.0, height / 2.0
                shapes.append(MacroShape("polygon", True, points=(
                    (x - hw, y - hh), (x + hw, y - hh),
                    (x + hw, y + hh), (x - hw, y + hh))))
        elif self.kind == APERTURE_POLYGON:
            # The template is P,<diameter>X<vertices>X<rotation>.
            diameter = self.params[0] if self.params else 0.0
            count = int(self.params[1]) if len(self.params) > 1 else 3
            rotation = self.params[2] if len(self.params) > 2 else 0.0
            count = max(3, count)
            radius = diameter / 2.0
            pts = []
            for i in range(count):
                angle = math.radians(rotation) + 2.0 * math.pi * i / count
                pts.append((x + radius * math.cos(angle), y + radius * math.sin(angle)))
            shapes.append(MacroShape("polygon", True, points=tuple(pts)))

        if self.hole:
            hole_kind = self.hole[0] if len(self.hole) > 0 else "circle"
            if hole_kind == "circle":
                diameter = self.hole[1] if len(self.hole) > 1 else 0.0
                shapes.append(MacroShape("circle", False, x, y, diameter))
            else:
                width = self.hole[1] if len(self.hole) > 1 else 0.0
                height = self.hole[2] if len(self.hole) > 2 else width
                hw, hh = width / 2.0, height / 2.0
                shapes.append(MacroShape("polygon", False, points=(
                    (x - hw, y - hh), (x + hw, y - hh),
                    (x + hw, y + hh), (x - hw, y + hh))))
        return shapes

"""Gerber aperture macro parsing and evaluation.

An aperture macro is a small program that describes a composite aperture
made of primitive shapes.  This module implements the primitive set defined
by the Gerber specification plus the two widely used extensions:

======  =======================================================
 code    shape
======  =======================================================
 1      circle
 2      vector line
 4      outline (polygon)
 5      regular polygon
 6      moire (concentric rings + crosshair)
 7      thermal
 20     vector line (identical to 2)
 21     centre line (rectangle)
 22     lower-left line (rectangle) - Altium/EDA extension
======  =======================================================

Shape 22 is not part of the original specification but is emitted by a large
share of the boards this tool has to review, so it is supported explicitly.

Every primitive carries an *exposure* flag.  Exposure off inside a macro is a
hole in the aperture, not a separate negative object: the evaluation below
therefore returns an ordered list of shapes where each shape is either added
to or subtracted from the aperture outline.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

#: Primitives this module knows how to evaluate.
KNOWN_PRIMITIVES = frozenset({1, 2, 4, 5, 6, 7, 20, 21, 22})

#: Number of sides used when a circle has to be turned into a polygon.
CIRCLE_SEGMENTS = 64


class MacroError(ValueError):
    """Raised when an aperture macro cannot be parsed or evaluated."""


@dataclass(frozen=True)
class MacroShape:
    """One evaluated primitive of an aperture macro.

    ``kind`` is ``"circle"`` or ``"polygon"``.  ``exposure`` false means the
    shape is a hole that is cut out of the aperture.
    """

    kind: str
    exposure: bool
    # circle
    cx: float = 0.0
    cy: float = 0.0
    diameter: float = 0.0
    # polygon
    points: tuple[tuple[float, float], ...] = ()

    def translated(self, dx: float, dy: float) -> "MacroShape":
        if self.kind == "circle":
            return MacroShape(self.kind, self.exposure, self.cx + dx, self.cy + dy,
                              self.diameter, self.points)
        return MacroShape(self.kind, self.exposure, self.cx, self.cy, self.diameter,
                          tuple((x + dx, y + dy) for x, y in self.points))


@dataclass
class ExpressionError(MacroError):
    """Raised when a macro expression cannot be evaluated."""


_TOKEN_RE = re.compile(r"""
    (?P<number>\d+\.\d*|\.\d+|\d+)
  | (?P<variable>\$\d+)
  | (?P<op>[()+\-*/xX])
  | (?P<ws>\s+)
""", re.VERBOSE)


class _ExprParser:
    """Recursive descent parser for the macro expression subset."""

    def __init__(self, text: str, variables: dict[int, float]):
        self._tokens = self._tokenize(text)
        self._pos = 0
        self._vars = variables

    @staticmethod
    def _tokenize(text: str):
        tokens = []
        pos = 0
        while pos < len(text):
            m = _TOKEN_RE.match(text, pos)
            if not m:
                raise ExpressionError(f"bad macro expression near {text[pos:pos + 12]!r}")
            pos = m.end()
            if m.lastgroup == "ws":
                continue
            tokens.append((m.lastgroup, m.group()))
        return tokens

    def _peek(self):
        return self._tokens[self._pos] if self._pos < len(self._tokens) else (None, None)

    def _next(self):
        tok = self._peek()
        self._pos += 1
        return tok

    def _expect(self, value: str):
        kind, text = self._next()
        if text != value:
            raise ExpressionError(f"expected {value!r}, got {text!r}")

    def parse(self) -> float:
        if not self._tokens:
            raise ExpressionError("empty macro expression")
        value = self._expression()
        if self._pos != len(self._tokens):
            raise ExpressionError("trailing data in macro expression")
        return value

    def _expression(self) -> float:
        value = self._term()
        while True:
            kind, text = self._peek()
            if text in ("+", "-"):
                self._next()
                rhs = self._term()
                value = value + rhs if text == "+" else value - rhs
            else:
                return value

    def _term(self) -> float:
        value = self._factor()
        while True:
            kind, text = self._peek()
            if text in ("x", "X", "*", "/"):
                self._next()
                rhs = self._factor()
                if text == "/":
                    if rhs == 0:
                        raise ExpressionError("division by zero in macro expression")
                    value = value / rhs
                else:
                    value = value * rhs
            else:
                return value

    def _factor(self) -> float:
        kind, text = self._next()
        if kind == "number":
            return float(text)
        if kind == "variable":
            index = int(text[1:])
            if index not in self._vars:
                raise ExpressionError(f"macro variable ${index} used before assignment")
            return self._vars[index]
        if text == "-":
            return -self._factor()
        if text == "+":
            return self._factor()
        if text == "(":
            value = self._expression()
            self._expect(")")
            return value
        raise ExpressionError(f"unexpected token {text!r} in macro expression")


def evaluate_expression(text: str, variables: dict[int, float]) -> float:
    """Evaluate a macro expression, resolving ``$n`` variables."""
    return _ExprParser(text, variables).parse()


@dataclass
class AMPrimitive:
    """One primitive statement of an aperture macro."""

    code: int
    params: list[str] = field(default_factory=list)

    def _eval_params(self, variables: dict[int, float]) -> list[float]:
        return [evaluate_expression(p, variables) for p in self.params]

    @staticmethod
    def _rotate(point: tuple[float, float], degrees: float) -> tuple[float, float]:
        """Rotate a point clockwise around the macro origin.

        Every primitive inside an aperture macro is rotated around the origin
        of the macro definition, never around its own centre.  The Gerber
        layer format specification is explicit about this.
        """
        if not degrees:
            return point
        rad = math.radians(degrees)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        x, y = point
        return (x * cos_a + y * sin_a, -x * sin_a + y * cos_a)

    def evaluate(self, variables: dict[int, float]) -> list[MacroShape]:
        """Turn this primitive into concrete shapes."""
        values = self._eval_params(variables)
        exposure, rest = self._split_exposure(values)
        if self.code == 1:
            return self._circle(rest, exposure)
        if self.code in (2, 20):
            return self._vector_line(rest, exposure)
        if self.code == 4:
            return self._outline(rest, exposure)
        if self.code == 5:
            return self._regular_polygon(rest, exposure)
        if self.code == 6:
            return self._moire(rest, exposure)
        if self.code == 7:
            return self._thermal(rest, exposure)
        if self.code == 21:
            return self._centre_line(rest, exposure)
        if self.code == 22:
            return self._lower_left(rest, exposure)
        raise MacroError(f"unsupported aperture macro primitive {self.code}")

    def _split_exposure(self, values: list[float]) -> tuple[bool, list[float]]:
        """Split the leading exposure value off the parameter list.

        The exposure exists for the primitives 1, 2, 4, 5, 20, 21 and 22.
        The moire and the thermal are always on.  The parameter lists
        without the exposure are still accepted, so both spellings of the
        specification work.
        """
        if self.code in (6, 7):
            return (True, values)
        if not values:
            return (True, values)
        if values[0] in (0, 1) and int(values[0]) == values[0]:
            return (bool(int(values[0])), values[1:])
        return (True, values)

    # -- individual primitives -------------------------------------------
    @staticmethod
    def _circle(v: list[float], exposure: bool) -> list[MacroShape]:
        # diameter, centre x, centre y, [rotation]
        diameter = v[0]
        cx, cy = v[1], v[2]
        rotation = v[3] if len(v) > 3 else 0.0
        if rotation:
            cx, cy = AMPrimitive._rotate((cx, cy), rotation)
        return [MacroShape("circle", exposure, cx, cy, diameter)]

    @staticmethod
    def _vector_line(v: list[float], exposure: bool) -> list[MacroShape]:
        # width, start x, start y, end x, end y, rotation
        width = v[0]
        x1, y1, x2, y2 = v[1], v[2], v[3], v[4]
        rotation = v[5] if len(v) > 5 else 0.0
        points = AMPrimitive._stroke_rect(x1, y1, x2, y2, width)
        if rotation:
            points = tuple(AMPrimitive._rotate(p, rotation) for p in points)
        return [MacroShape("polygon", exposure, points=points)]

    @staticmethod
    def _outline(v: list[float], exposure: bool) -> list[MacroShape]:
        # number of vertices, then the vertices, then an optional rotation
        if len(v) < 2:
            return []
        count = int(v[0])
        if count < 1:
            return []
        coords = v[1:]
        # The outline carries the vertices of the closed contour; the
        # rotation, when present, is the last parameter.
        rotation = 0.0
        if len(coords) % 2 == 1 and len(coords) > 2 * count:
            rotation = coords[-1]
            coords = coords[:-1]
        points = [(coords[i * 2], coords[i * 2 + 1]) for i in range(len(coords) // 2)]
        if not points:
            return []
        if rotation:
            points = [AMPrimitive._rotate(p, rotation) for p in points]
        return [MacroShape("polygon", exposure, points=tuple(points))]

    @staticmethod
    def _regular_polygon(v: list[float], exposure: bool) -> list[MacroShape]:
        # number of vertices, centre x, centre y, diameter, [rotation]
        count = int(v[0])
        if count < 3:
            return []
        cx, cy, diameter = v[1], v[2], v[3]
        rotation = v[4] if len(v) > 4 else 0.0
        radius = diameter / 2.0
        pts = []
        for i in range(count):
            angle = 2.0 * math.pi * i / count
            pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        if rotation:
            pts = [AMPrimitive._rotate(p, rotation) for p in pts]
        return [MacroShape("polygon", exposure, points=tuple(pts))]

    @staticmethod
    def _thermal(v: list[float], exposure: bool) -> list[MacroShape]:
        # centre x, centre y, outer diameter, inner diameter, gap, [rotation]
        cx, cy, outer_d, inner_d = v[0], v[1], v[2], v[3]
        gap = v[4] if len(v) > 4 else 0.0
        rotation = v[5] if len(v) > 5 else 0.0
        shapes = [MacroShape("circle", exposure, cx, cy, outer_d)]
        if inner_d > 0:
            shapes.append(MacroShape("circle", not exposure, cx, cy, inner_d))
        if gap > 0:
            # The cross shaped thermal relief gap.
            half_gap = gap / 2.0
            reach = outer_d
            shapes.append(MacroShape("polygon", not exposure, points=(
                (cx - reach, cy - half_gap), (cx + reach, cy - half_gap),
                (cx + reach, cy + half_gap), (cx - reach, cy + half_gap))))
            shapes.append(MacroShape("polygon", not exposure, points=(
                (cx - half_gap, cy - reach), (cx + half_gap, cy - reach),
                (cx + half_gap, cy + reach), (cx - half_gap, cy + reach))))
        if rotation:
            shapes = [AMPrimitive._rotate_shape(s, rotation) for s in shapes]
        return shapes

    @staticmethod
    def _moire(v: list[float], exposure: bool) -> list[MacroShape]:
        # centre x, centre y, outer diameter, ring thickness, gap, max rings,
        # crosshair thickness, crosshair length, [rotation]
        cx, cy, outer_d = v[0], v[1], v[2]
        ring_thickness = v[3] if len(v) > 3 else 0.0
        gap = v[4] if len(v) > 4 else 0.0
        max_rings = int(v[5]) if len(v) > 5 else 0
        cross_thickness = v[6] if len(v) > 6 else 0.0
        cross_length = v[7] if len(v) > 7 else 0.0
        rotation = v[8] if len(v) > 8 else 0.0

        shapes: list[MacroShape] = [MacroShape("circle", exposure, cx, cy, outer_d)]
        radius = outer_d / 2.0
        for _ in range(max(0, max_rings)):
            if ring_thickness <= 0:
                break
            inner = max(0.0, (radius - ring_thickness) * 2.0)
            shapes.append(MacroShape("circle", not exposure, cx, cy, inner))
            radius -= ring_thickness + gap
            if radius <= 0:
                break
            shapes.append(MacroShape("circle", exposure, cx, cy, radius * 2.0))
        if cross_thickness > 0 and cross_length > 0:
            half_t = cross_thickness / 2.0
            half_l = cross_length / 2.0
            shapes.append(MacroShape("polygon", exposure, points=(
                (cx - half_l, cy - half_t), (cx + half_l, cy - half_t),
                (cx + half_l, cy + half_t), (cx - half_l, cy + half_t))))
            shapes.append(MacroShape("polygon", exposure, points=(
                (cx - half_t, cy - half_l), (cx + half_t, cy - half_l),
                (cx + half_t, cy + half_l), (cx - half_t, cy + half_l))))
        if rotation:
            shapes = [AMPrimitive._rotate_shape(s, rotation) for s in shapes]
        return shapes

    @staticmethod
    def _centre_line(v: list[float], exposure: bool) -> list[MacroShape]:
        # width, height, centre x, centre y, [rotation]
        width, height, cx, cy = v[0], v[1], v[2], v[3]
        rotation = v[4] if len(v) > 4 else 0.0
        half_w, half_h = width / 2.0, height / 2.0
        points = ((cx - half_w, cy - half_h), (cx - half_w, cy + half_h),
                  (cx + half_w, cy + half_h), (cx + half_w, cy - half_h))
        if rotation:
            points = tuple(AMPrimitive._rotate(p, rotation) for p in points)
        return [MacroShape("polygon", exposure, points=points)]

    @staticmethod
    def _lower_left(v: list[float], exposure: bool) -> list[MacroShape]:
        # width, height, lower left x, lower left y, [rotation]
        width, height, x, y = v[0], v[1], v[2], v[3]
        rotation = v[4] if len(v) > 4 else 0.0
        points = ((x, y), (x, y + height), (x + width, y + height), (x + width, y))
        if rotation:
            points = tuple(AMPrimitive._rotate(p, rotation) for p in points)
        return [MacroShape("polygon", exposure, points=points)]

    @staticmethod
    def _rotate_shape(shape: MacroShape, degrees: float) -> MacroShape:
        if shape.kind == "circle":
            cx, cy = AMPrimitive._rotate((shape.cx, shape.cy), degrees)
            return MacroShape(shape.kind, shape.exposure, cx, cy, shape.diameter, shape.points)
        points = tuple(AMPrimitive._rotate(p, degrees) for p in shape.points)
        return MacroShape(shape.kind, shape.exposure, shape.cx, shape.cy,
                          shape.diameter, points)

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _stroke_rect(x1: float, y1: float, x2: float, y2: float, width: float):
        """Rectangle covering a vector line of the given width."""
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length <= 0:
            half = width / 2.0
            return ((x1 - half, y1 - half), (x1 - half, y1 + half),
                    (x1 + half, y1 + half), (x1 + half, y1 - half))
        ux, uy = dx / length, dy / length
        nx, ny = -uy * width / 2.0, ux * width / 2.0
        base_x, base_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        pts = []
        for sx, sy in ((-1, -1), (-1, 1), (1, 1), (1, -1)):
            px = sx * length / 2.0
            py = sy * width / 2.0
            pts.append((base_x + px * ux + py * nx, base_y + px * uy + py * ny))
        return tuple(pts)


class ApertureMacro:
    """A named aperture macro definition."""

    def __init__(self, name: str):
        self.name = name
        self.primitives: list[AMPrimitive] = []
        self.assignments: list[tuple[int, str]] = []
        self._cache: list[MacroShape] | None = None

    # -- parsing ----------------------------------------------------------
    def add_primitive(self, code: int, params: list[str]) -> None:
        self.primitives.append(AMPrimitive(code, params))
        self._cache = None

    def add_assignment(self, index: int, expression: str) -> None:
        self.assignments.append((index, expression))
        self._cache = None

    # -- evaluation -------------------------------------------------------
    def evaluate(self) -> list[MacroShape]:
        """Evaluate the macro into an ordered list of shapes."""
        if self._cache is not None:
            return self._cache
        variables: dict[int, float] = {}
        shapes: list[MacroShape] = []
        for index, expression in self.assignments:
            variables[index] = evaluate_expression(expression, variables)
        for primitive in self.primitives:
            shapes.extend(primitive.evaluate(variables))
        self._cache = shapes
        return shapes

    @property
    def supported(self) -> bool:
        """True when every primitive of this macro is known to us."""
        return all(p.code in KNOWN_PRIMITIVES for p in self.primitives)


def parse_macro_body(name: str, body_lines: list[str]) -> ApertureMacro:
    """Build an :class:`ApertureMacro` from the body of a ``%AM`` statement.

    ``body_lines`` are the lines between ``%AM<name>*`` and the closing
    ``%``.  Each line holds one primitive or one variable assignment.
    """
    macro = ApertureMacro(name)
    for raw in body_lines:
        line = raw.strip()
        if not line or line.startswith("*"):
            line = line.lstrip("*").strip()
            if not line:
                continue
        line = line.rstrip("*").strip()
        if not line:
            continue
        if line.startswith("$"):
            # Either "$1=expression" (assignment) or a bare "$1" reference.
            if "=" in line:
                lhs, rhs = line.split("=", 1)
                index = int(lhs.strip().lstrip("$"))
                macro.add_assignment(index, rhs.strip())
            continue
        parts = line.split(",")
        try:
            code = int(parts[0].strip())
        except ValueError as exc:
            raise MacroError(f"bad aperture macro primitive {line!r}") from exc
        params = [p.strip() for p in parts[1:]]
        macro.add_primitive(code, params)
    return macro

"""Units and coordinate formats for the spec parser.

The spec engine works in *internal units* (IU) of 10 nanometres so that every
coordinate is an exact integer and repeated transforms never accumulate
floating point error.  This mirrors the internal unit used by mainstream
EDA tools for Gerber artwork, where 10 nm is fine enough for every
fabrication feature and coarse enough to keep the numbers small.

Coordinate parsing follows the Gerber ``%FS`` statement:

* ``X<int><frac>`` declares the digit count of the X axis, ``Y<int><frac>``
  the Y axis.
* ``L`` (leading zeros omitted) left-pads the number, ``T`` (trailing zeros
  omitted) right-pads it.
* ``A`` means absolute, ``I`` means incremental.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 10 nm internal unit: 100 000 IU per millimetre.
IU_PER_MM = 100_000
MM_PER_INCH = 25.4

#: Gerber layer polarity.
POLARITY_DARK = "dark"
POLARITY_CLEAR = "clear"


def mm_to_iu(mm: float) -> int:
    """Convert millimetres to internal units (rounded to the nearest IU)."""
    return int(round(mm * IU_PER_MM))


def iu_to_mm(iu: int) -> float:
    """Convert internal units to millimetres."""
    return iu / IU_PER_MM


def inch_to_iu(inch: float) -> int:
    """Convert inches to internal units."""
    return mm_to_iu(inch * MM_PER_INCH)


def uu_to_iu(uu: float) -> int:
    """Convert a value expressed in the file's own unit to internal units.

    ``uu`` is in inches or millimetres depending on the active ``%MO``; the
    caller supplies the matching scale.
    """
    return mm_to_iu(uu * _UNIT_SCALE[0])


# Active file unit scale (millimetres per file unit).  Set by the parser
# before any coordinate is decoded; kept module level to avoid threading a
# unit object through every helper.
_UNIT_SCALE = [1.0]


def set_unit_scale(mm_per_unit: float) -> None:
    """Set how many millimetres one file unit is worth."""
    _UNIT_SCALE[0] = mm_per_unit


def unit_scale() -> float:
    """Current millimetres per file unit."""
    return _UNIT_SCALE[0]


def unit_to_iu(value: float) -> int:
    """Convert a value in the active file unit to internal units."""
    return mm_to_iu(value * _UNIT_SCALE[0])


def iu_to_unit(iu: int) -> float:
    """Convert internal units back to the active file unit."""
    return (iu / IU_PER_MM) / _UNIT_SCALE[0]


class FormatError(ValueError):
    """Raised when a ``%FS`` statement cannot be understood."""


@dataclass(frozen=True)
class AxisFormat:
    """Digit layout of one axis."""

    int_digits: int
    dec_digits: int
    zero_suppress: str  # "L" or "T"

    def __post_init__(self) -> None:
        width = self.int_digits + self.dec_digits
        divisor = 10.0 ** self.dec_digits
        object.__setattr__(self, "_width", width)
        # With leading zeros omitted the written digits are the last ones of
        # the field, so the value is simply the number divided by the
        # decimal divisor - no padding is needed at all.
        object.__setattr__(self, "_leading_factor", 1.0 / divisor)
        # With trailing zeros omitted the written digits are the first ones
        # of the field, so the value grows with the number of missing digits.
        object.__setattr__(self, "_trailing_factors", {
            n: (10.0 ** (width - n)) / divisor for n in range(1, width + 1)
        })

    @property
    def total_digits(self) -> int:
        return self.int_digits + self.dec_digits

    def decode(self, text: str) -> float:
        """Decode one coordinate word into a value in the file unit.

        A large file holds hundreds of thousands of coordinate words,
        and almost all of them are a plain number without a sign.  That
        case is worth a shortcut: the general path below has to look at
        the sign, at the length of the text and at the way the zeros are
        suppressed.
        """
        if text.isdigit():
            length = len(text)
            if length <= self._width:
                try:
                    value = int(text)
                except ValueError:
                    value = None
                if value is not None:
                    if self.zero_suppress == "T":
                        return value * self._trailing_factors[length]
                    return value * self._leading_factor
        sign = 1.0
        first = text[0]
        if first == "-":
            sign = -1.0
            text = text[1:]
        elif first == "+":
            text = text[1:]
        width = self._width
        length = len(text)
        if length > width:
            if self.zero_suppress == "T":
                text = text[:width]
            else:
                text = text[-width:]
            length = width
        try:
            value = int(text)
        except ValueError as exc:
            raise FormatError(f"non numeric coordinate {text!r}") from exc
        if self.zero_suppress == "T":
            value *= self._trailing_factors[length]
        else:
            value *= self._leading_factor
        return sign * value


@dataclass(frozen=True)
class CoordinateFormat:
    """The full ``%FS`` statement: one layout per axis plus the notation."""

    x: AxisFormat
    y: AxisFormat
    notation: str  # "A" absolute, "I" incremental

    @property
    def incremental(self) -> bool:
        return self.notation == "I"

    @staticmethod
    def parse(statement: str) -> "CoordinateFormat":
        """Build a format from the body of a ``%FS`` statement.

        The body looks like ``LAX36Y36`` - zero suppression, notation, then
        the per axis digit counts.
        """
        body = statement.strip()
        if not body:
            raise FormatError("empty %FS statement")

        zero_suppress = "L"
        notation = "A"
        rest = body

        if rest and rest[0] in "LT":
            zero_suppress = rest[0]
            rest = rest[1:]
        if rest and rest[0] in "AI":
            notation = rest[0]
            rest = rest[1:]

        x_fmt = None
        y_fmt = None
        for axis, int_digits, dec_digits in re.findall(r"([XY])(\d)(\d+)", rest):
            axis_fmt = AxisFormat(
                int_digits=int(int_digits),
                dec_digits=int(dec_digits),
                zero_suppress=zero_suppress,
            )
            if axis == "X":
                x_fmt = axis_fmt
            else:
                y_fmt = axis_fmt

        if x_fmt is None or y_fmt is None:
            raise FormatError(f"%FS statement without both axes: {statement!r}")

        return CoordinateFormat(x=x_fmt, y=y_fmt, notation=notation)

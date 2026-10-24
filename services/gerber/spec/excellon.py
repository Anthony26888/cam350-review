"""Excellon / NC drill parser.

NC drill files are the companion of a Gerber set: they describe the holes
that have to be drilled.  The dialect used by CAM tools differs from the
original Excellon proposal in a few places, so this parser is deliberately
tolerant:

* the unit and zero suppression may be given as ``METRIC,LZ`` / ``INCH,TZ``
  or only implied by a leading ``METRIC`` / ``INCH``,
* the coordinate format may come from an ``FMAT,2`` command together with a
  ``;FILE_FORMAT=4:4`` comment, or only from the comment,
* coordinates may omit one axis, which keeps the previous value,
* a slot may be written as ``G85`` between two points, or as a routed path
  delimited by ``M15`` / ``M16``.

All output is in internal units (10 nm) so a drill file can be rendered with
the same pipeline as the Gerber layers.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .units import IU_PER_MM, MM_PER_INCH

#: Chord error used when a routed slot is turned into a polygon.
SLOT_CHORD_ERROR_MM = 0.01

_TOOL_RE = re.compile(r"^T(\d+)(.*)$", re.IGNORECASE)
_FILE_FORMAT_RE = re.compile(r"FILE_FORMAT\s*=\s*(\d)\s*[:;]\s*(\d)", re.IGNORECASE)
_COMMENT_RE = re.compile(r"^;(.*)$")
#: A coordinate word on a line that also carries a mode.
_COORD_RE = re.compile(r"[XY][-+]?\d", re.IGNORECASE)
#: The tool going down and up again: the routed dialect.
_ROUTED_RE = re.compile(r"^\s*M1[56]\b", re.IGNORECASE | re.MULTILINE)


class ExcellonParseError(ValueError):
    """Raised when a drill file cannot be parsed at all."""


@dataclass
class DrillTool:
    """One drill tool definition."""

    number: int
    diameter: float = 0.0  # millimetres
    plated: bool = True
    flute: float = 0.0
    feed: float = 0.0
    speed: float = 0.0


@dataclass
class DrillHole:
    """A single drilled hole."""

    x: int
    y: int
    diameter: int
    plated: bool = True


@dataclass
class DrillSlot:
    """A milled or drilled slot."""

    x1: int
    y1: int
    x2: int
    y2: int
    diameter: int
    plated: bool = True


@dataclass
class ExcellonImage:
    """The parsed content of one NC drill file."""

    holes: list[DrillHole] = field(default_factory=list)
    slots: list[DrillSlot] = field(default_factory=list)
    tools: dict[int, DrillTool] = field(default_factory=dict)
    unit_scale: float = 1.0  # millimetres per file unit
    int_digits: int = 2
    dec_digits: int = 4
    zero_suppress: str = "L"
    plated: bool = True
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False

    @property
    def bbox(self) -> tuple[int, int, int, int] | None:
        xs: list[int] = []
        ys: list[int] = []
        for hole in self.holes:
            r = hole.diameter // 2
            xs.extend((hole.x - r, hole.x + r))
            ys.extend((hole.y - r, hole.y + r))
        for slot in self.slots:
            r = slot.diameter // 2
            xs.extend((slot.x1 - r, slot.x2 + r))
            ys.extend((slot.y1 - r, slot.y2 + r))
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def bbox_mm(self) -> tuple[float, float, float, float] | None:
        box = self.bbox
        if box is None:
            return None
        return (box[0] / IU_PER_MM, box[1] / IU_PER_MM,
                box[2] / IU_PER_MM, box[3] / IU_PER_MM)

    @property
    def drill_sizes(self) -> list[float]:
        return sorted({tool.diameter for tool in self.tools.values() if tool.diameter > 0})


class ExcellonParser:
    """Parse one NC drill file."""

    def __init__(self, text: str, name: str = ""):
        self._text = text
        self._name = name
        self.image = ExcellonImage()
        self._current_x = 0
        self._current_y = 0
        self._current_tool: DrillTool | None = None
        self._routing = False
        self._slot_start: tuple[int, int] | None = None
        self._repeat: tuple[int, int, int] | None = None  # count, dx, dy
        self._pending_x: int | None = None
        self._pending_y: int | None = None
        # Some tools write the drill as the tool going down and up again
        # (M15 and M16) and the slots as a move between the two.  The
        # dialect is decided from the file itself, because the first move
        # comes before the first M15.
        self._routed_style = _ROUTED_RE.search(text) is not None

    # ------------------------------------------------------------------
    @classmethod
    def from_path(cls, path: str) -> "ExcellonParser":
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        return cls(text, os.path.basename(path))

    def parse(self) -> ExcellonImage:
        self._run()
        return self.image

    # ------------------------------------------------------------------
    def _run(self) -> None:
        for raw in self._text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith(";"):
                self._handle_comment(line)
                continue
            if line.startswith("M48"):
                continue
            if line.startswith("M95"):
                continue
            if line == "%":
                continue
            if line.startswith("M30") or line.startswith("M00"):
                break
            if line.startswith("M15"):
                self._routing = True
                self._slot_start = (self._current_x, self._current_y)
                continue
            if line.startswith("M16"):
                self._routing = False
                self._close_slot()
                continue
            if line.startswith("METRIC") or line.startswith("INCH"):
                self._handle_units(line)
                continue
            if line.upper().startswith("FMAT"):
                continue
            if line.startswith("G00") or line.startswith("G0") or line.startswith("G01") or line.startswith("G1"):
                self._handle_gcode(line)
                continue
            if line.startswith("G05") or line.startswith("G81") or line.startswith("G82"):
                continue
            if line.startswith("G85"):
                self._handle_slot(line)
                continue
            if line[0] in "Rr":
                self._handle_repeat(line)
                continue
            if line[0] in "Tt":
                self._handle_tool(line)
                continue
            if line[0] in "XxYy":
                self._handle_coordinate(line)
                continue
            self._warn(f"ignored drill statement {line!r}")

    # ------------------------------------------------------------------
    def _handle_comment(self, line: str) -> None:
        text = line.lstrip(";").strip()
        match = _FILE_FORMAT_RE.search(text)
        if match:
            self.image.int_digits = int(match.group(1))
            self.image.dec_digits = int(match.group(2))
            return
        upper = text.upper()
        if upper.startswith("TYPE="):
            self.image.plated = "NONPLATED" not in upper
            return
        if upper.startswith("FILE_FORMAT"):  # pragma: no cover - covered above
            return

    def _handle_units(self, line: str) -> None:
        upper = line.upper()
        if upper.startswith("METRIC"):
            self.image.unit_scale = 1.0
        else:
            self.image.unit_scale = MM_PER_INCH
        if ",TZ" in upper:
            self.image.zero_suppress = "T"
        elif ",LZ" in upper:
            self.image.zero_suppress = "L"

    def _handle_gcode(self, line: str) -> None:
        # G00/G01 only select the mode; the coordinates follow in the next
        # line or on the same one.
        if "G85" in line.upper():
            self._handle_slot(line)
            return
        if _COORD_RE.search(line):
            # The coordinates are on the same line as the mode.  A move is
            # not a drill hit, so the position is only updated.
            self._update_position(line)

    def _handle_repeat(self, line: str) -> None:
        """``R<n>X<dx>Y<dy>`` - repeat the previous hole."""
        match = re.match(r"^R(\d+)(?:X(-?\d+))?(?:Y(-?\d+))?$", line, re.IGNORECASE)
        if not match:
            self._warn(f"bad repeat statement {line!r}")
            return
        count = int(match.group(1))
        dx = int(match.group(2) or 0)
        dy = int(match.group(3) or 0)
        scale = self.image.unit_scale * IU_PER_MM
        last_hole = self.image.holes[-1] if self.image.holes else None
        if last_hole is None:
            return
        for index in range(1, count):
            self.image.holes.append(DrillHole(
                last_hole.x + int(dx * scale) * index,
                last_hole.y + int(dy * scale) * index,
                last_hole.diameter,
                last_hole.plated,
            ))

    def _handle_tool(self, line: str) -> None:
        match = _TOOL_RE.match(line)
        if not match:
            return
        number = int(match.group(1))
        rest = match.group(2).upper()
        if not rest:
            # A bare T code selects the tool.
            self._current_tool = self.image.tools.get(number)
            return
        tool = self.image.tools.get(number) or DrillTool(number)
        diameter = 0.0
        for part in re.findall(r"C([-+]?\d*\.?\d+)", rest):
            diameter = float(part)
            break
        tool.diameter = diameter
        flute_match = re.search(r"F(\d+)", rest)
        if flute_match:
            tool.flute = float(flute_match.group(1))
        feed_match = re.search(r"S(\d+)", rest)
        if feed_match:
            tool.feed = float(feed_match.group(1))
        speed_match = re.search(r"S(\d+)", rest)
        if speed_match:
            tool.speed = float(speed_match.group(1))
        if "P" in rest and "PLATED" not in rest:
            tool.plated = True
        self.image.tools[number] = tool
        self._current_tool = tool

    def _handle_coordinate(self, line: str) -> None:
        if not self._update_position(line):
            return
        self._emit_position()

    def _update_position(self, line: str) -> bool:
        """Decode the coordinates of a line into the current position."""
        found = False
        for letter, value in re.findall(r"([XY])([-+]?\d+)", line, re.IGNORECASE):
            number = int(value)
            if letter.upper() == "X":
                self._pending_x = number
            else:
                self._pending_y = number
            found = True
        if self._pending_x is None and self._pending_y is None:
            return False
        scale = self.image.unit_scale * IU_PER_MM
        total = self.image.int_digits + self.image.dec_digits
        if self._pending_x is not None:
            self._current_x = int(round(self._decode(self._pending_x, total) * scale))
        if self._pending_y is not None:
            self._current_y = int(round(self._decode(self._pending_y, total) * scale))
        self._pending_x = None
        self._pending_y = None
        return True

    def _handle_slot(self, line: str) -> None:
        """``G85`` between two points defines a slot."""
        self._slot_start = (self._current_x, self._current_y)
        for letter, value in re.findall(r"([XY])([-+]?\d+)", line, re.IGNORECASE):
            number = int(value)
            scale = self.image.unit_scale * IU_PER_MM
            total = self.image.int_digits + self.image.dec_digits
            if letter.upper() == "X":
                self._current_x = int(round(self._decode(number, total) * scale))
            else:
                self._current_y = int(round(self._decode(number, total) * scale))
        self._close_slot()

    def _close_slot(self) -> None:
        if self._slot_start is None:
            return
        tool = self._current_tool
        diameter = int(round(tool.diameter * self.image.unit_scale * IU_PER_MM)) if tool else 0
        if self._slot_start != (self._current_x, self._current_y):
            self.image.slots.append(DrillSlot(
                self._slot_start[0], self._slot_start[1],
                self._current_x, self._current_y,
                diameter, tool.plated if tool else True,
            ))
        elif self._routed_style and tool is not None:
            # The tool went down and up at the same place: that is a hole,
            # not a slot of no length.
            self.image.holes.append(DrillHole(
                self._current_x, self._current_y, diameter, tool.plated))
        self._slot_start = None

    def _emit_position(self) -> None:
        tool = self._current_tool
        if self._routing:
            return
        if self._routed_style:
            # In the routed dialect the drill is expressed by M15 and M16,
            # not by the position itself.
            return
        if tool is None:
            self._warn("drill coordinate without a selected tool")
            return
        diameter = int(round(tool.diameter * self.image.unit_scale * IU_PER_MM))
        self.image.holes.append(DrillHole(
            self._current_x, self._current_y, diameter, tool.plated))

    def _decode(self, value: int, total: int) -> float:
        """Decode one coordinate word into the file unit."""
        sign = 1.0
        if value < 0:
            sign = -1.0
            value = -value
        text = str(value)
        if len(text) < total:
            if self.image.zero_suppress == "T":
                text = text.ljust(total, "0")
            else:
                text = text.zfill(total)
        int_digits = self.image.int_digits
        int_part = text[:int_digits] or "0"
        frac_part = text[int_digits:]
        return sign * float(f"{int_part}.{frac_part}")

    def _warn(self, message: str) -> None:
        if len(self.image.warnings) < 100:
            self.image.warnings.append(message)


def parse_file(path: str) -> ExcellonImage:
    """Parse one NC drill file."""
    return ExcellonParser.from_path(path).parse()

"""The Gerber (RS-274X / X2) parser.

This is a tolerant, character driven parser.  It is written against the
Gerber specification and against the dialects that show up in real CAM
output, which differ from the specification in a handful of well known ways:

* modal single digit operation codes (``D1`` / ``D2`` / ``D3``) instead of
  the ``D01`` / ``D02`` / ``D03`` spelling,
* commands that omit the trailing ``*`` and rely on the modal operation code,
* ``I``/``J`` words attached to a linear ``D01``,
* coordinate statements without an explicit operation mode,
* ``%SR`` blocks that follow another ``%SR`` block.

The parser never aborts on an unknown statement: it records a warning and
carries on, so a single odd file still yields the artwork it does contain.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field

from . import rs274x
from .am_primitive import (
    KNOWN_PRIMITIVES,
    ApertureMacro,
    MacroError,
    MacroShape,
    parse_macro_body,
)
from .dcode import (
    APERTURE_CIRCLE,
    APERTURE_MACRO,
    APERTURE_OBLONG,
    APERTURE_POLYGON,
    APERTURE_RECT,
    DCode,
)
from .draw_item import (
    KIND_ARC,
    KIND_CIRCLE,
    KIND_MACRO,
    KIND_OBLONG,
    KIND_POLYGON,
    KIND_RECT,
    KIND_SEGMENT,
    DrawItem,
)
from .file_image import FileImage, LayerParams
from .units import (
    MM_PER_INCH,
    CoordinateFormat,
    FormatError,
    IU_PER_MM,
)

#: Chord error used when an arc inside a region has to be flattened.
REGION_CHORD_ERROR_MM = 0.005

#: First D code that selects an aperture (D01..D09 are operations).
FIRST_APERTURE_DCODE = 10

#: An extended command block.
_X2_BLOCK_RE = re.compile(r"%[^%]*%")

#: A word of a classic command: a letter followed by an optional number.
_WORD_RE = re.compile(r"([GDMNXYIJ])([+-]?\d*)", re.IGNORECASE)

#: The shape almost every command of a real file has: a coordinate and an
#: operation.
_DRAW_RE = re.compile(r"X([+-]?\d+)Y([+-]?\d+)D0?([123])")

#: A G04 comment: "G4" or "G04" not followed by a digit.
_COMMENT_RE = re.compile(r"^G0*4(?![0-9])")

#: Splits a file into extended command blocks and classic commands.
_BLOCK_RE = re.compile(r"%[^%]*%|[^*%\r\n]+", re.DOTALL)


class GerberParseError(ValueError):
    """Raised when a file cannot be parsed at all."""


@dataclass
class _Unused:
    """Placeholder kept so the dataclass import stays meaningful."""


class GerberParser:
    """Parse one Gerber file into a :class:`FileImage`."""

    def __init__(self, text: str, name: str = ""):
        self._text = text
        self._name = name

        # --- output -------------------------------------------------------
        self.image = FileImage()

        # --- coordinate handling -------------------------------------------
        self._format: CoordinateFormat | None = None
        self._unit_scale = 1.0  # millimetres per file unit
        self._absolute = True

        # --- drawing state ------------------------------------------------
        self._current_x = 0
        self._current_y = 0
        self._pending_x: str | None = None
        self._pending_y: str | None = None
        self._pending_i = "0"
        self._pending_j = "0"
        self._has_pending_i = False
        self._has_pending_j = False
        self._has_pending_ij = False
        self._interpolation = "linear"  # linear | cw | ccw
        self._current_dcode = 0
        #: The attributes of the next object (%TO).
        self._pending_object_attributes: dict = {}
        #: The aperture attributes that arrived before the aperture.
        self._pending_aperture_attributes: dict = {}
        self._current_width = 0
        self._has_image_transform = False
        self._last_operation: int | None = None
        self._polarity_dark = True

        # --- region state -------------------------------------------------
        self._region = False
        self._region_contours: list[list[tuple[int, int]]] = []
        self._region_current: list[tuple[int, int]] = []
        self._region_start: tuple[int, int] | None = None

        # --- image transform ----------------------------------------------
        self._mirror_a = False
        self._mirror_b = False
        self._swap_axes = False
        self._scale_a = 1.0
        self._scale_b = 1.0
        self._offset_a = 0.0
        self._offset_b = 0.0
        self._rotation = 0.0

        # --- step and repeat ----------------------------------------------
        self._sr_stack: list[tuple[int, tuple[int, int, float, float] | None]] = []

        # --- aperture macro body ------------------------------------------
        self._macro_body: list[str] | None = None
        self._macro_name = ""

        # --- deferred aperture macro references ---------------------------
        self._pending_macro_apertures: list[tuple[int, str]] = []

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    @classmethod
    def from_path(cls, path: str) -> "GerberParser":
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        return cls(text, os.path.basename(path))

    def parse(self) -> FileImage:
        """Run the parser and return the resulting image."""
        self._run()
        return self.image

    # ------------------------------------------------------------------
    # top level scan
    # ------------------------------------------------------------------
    def _run(self) -> None:
        # The extended statements are rare, so only they are searched for.
        # The rest of the file is split on the command separator, which is
        # much cheaper than walking it with a regular expression.
        text = self._text
        pos = 0
        for match in _X2_BLOCK_RE.finditer(text):
            start = match.start()
            if start > pos:
                self._run_plain(text[pos:start])
            self._run_x2_statements(rs274x.split_x2_statements(match.group()[1:-1]))
            pos = match.end()
        if pos < len(text):
            self._run_plain(text[pos:])
        self._finish()

    def _run_plain(self, text: str) -> None:
        # Almost every command of a real file carries a coordinate and an
        # operation.  Matching that shape here avoids a function call per
        # command.
        for part in text.split("*"):
            if not part:
                continue
            stripped = part.strip()
            if not stripped:
                continue
            match = _DRAW_RE.fullmatch(stripped)
            if match is not None:
                x_text, y_text, operation = match.groups()
                self._run_draw(x_text, y_text, int(operation))
                continue
            candidate = stripped[1:] if stripped.startswith("%") else stripped
            if candidate.startswith("ADD") and candidate[3:4].isdigit():
                # An extended statement whose opening percent was used to
                # close the block before it.  Some tools write an aperture
                # macro and the next statement with a single percent
                # between them; the definition would then be dropped
                # without a word.
                self._run_x2_statement(rs274x.AD, candidate)
                continue
            self._run_command(stripped)

    def _read_x2_block(self, block: str) -> None:
        """Consume a ``%...%`` block; the delimiters are part of the text."""
        body = block[1:-1] if block.endswith("%") and len(block) > 1 else block[1:]
        statements = rs274x.split_x2_statements(body)
        self._run_x2_statements(statements)

    # ------------------------------------------------------------------
    def _run_x2_statements(self, statements: list[str]) -> None:
        index = 0
        while index < len(statements):
            statement = statements[index]
            if not statement:
                index += 1
                continue
            ident = rs274x.statement_id(statement)
            if ident == rs274x.AM:
                # The macro body is every following statement of this block.
                name = statement[2:].strip()
                body = statements[index + 1:]
                self._run_am(name, body)
                index = len(statements)
                continue
            self._run_x2_statement(ident, statement)
            index += 1

    def _run_x2_statement(self, ident: str, statement: str) -> None:
        body = statement[2:].strip()
        if ident == rs274x.FS:
            try:
                self._format = CoordinateFormat.parse(body)
            except FormatError as exc:
                self._warn(f"%FS statement ignored: {exc}")
                self.image.degraded = True
        elif ident == rs274x.MO:
            upper = body.upper()
            if upper.startswith("IN"):
                self._unit_scale = MM_PER_INCH
            elif upper.startswith("MM"):
                self._unit_scale = 1.0
            else:
                self._warn(f"unknown unit mode %MO{body}")
        elif ident == rs274x.AD:
            self._run_ad(body)
        elif ident == rs274x.LP:
            upper = body.upper()
            if upper.startswith("C"):
                self._polarity_dark = False
                self.image.layer.negative = True
            elif upper.startswith("D"):
                self._polarity_dark = True
                self.image.layer.negative = False
            else:
                self._warn(f"unknown load polarity %LP{body}")
        elif ident == rs274x.IP:
            upper = body.upper()
            if upper.startswith("NEG"):
                self.image.image_negative = True
            elif upper.startswith("POS"):
                self.image.image_negative = False
        elif ident == rs274x.SR:
            self._run_sr(body)
        elif ident == rs274x.LN:
            self.image.layer.name = body
        elif ident == rs274x.TF:
            self._store_attribute(self.image.attributes, body)
        elif ident == rs274x.TA:
            # An aperture attribute belongs to the aperture that is
            # selected at this moment.
            self._store_aperture_attribute(body)
        elif ident == rs274x.TO:
            # An object attribute belongs to the next object that is
            # created.
            self._store_attribute(self._pending_object_attributes, body)
        elif ident == rs274x.TD:
            self._drop_attribute(body)
        elif ident == rs274x.MI:
            upper = body.upper()
            if "A" in upper:
                self._has_image_transform = True
                self._mirror_a = True
            if "B" in upper:
                self._has_image_transform = True
                self._mirror_b = True
        elif ident == rs274x.AS:
            upper = body.upper()
            if "X" in upper and "Y" in upper:
                self._has_image_transform = True
                self._swap_axes = True
            elif "X" in upper:
                self._has_image_transform = True
                self._swap_axes = True
            elif "Y" in upper:
                self._swap_axes = False
        elif ident == rs274x.SF:
            self._run_sf(body)
        elif ident == rs274x.OF:
            self._run_of(body)
        elif ident == rs274x.RO:
            try:
                self._has_image_transform = True
                self._rotation = float(body)
            except ValueError:
                self._warn(f"bad %RO{body}")
        elif ident in (rs274x.KO, rs274x.IN, rs274x.IO, rs274x.IR, rs274x.IJ):
            # Accepted and ignored: they do not change the rendered geometry
            # in a way this tool can act on.
            pass
        else:
            self._warn(f"unknown X2 statement %{statement}")
            self.image.degraded = True

    def _run_ad(self, body: str) -> None:
        """``%ADD<number><template>[,<params>]*%``"""
        body = body.strip()
        if body[:1] == "D":
            body = body[1:]
        if not body:
            return
        number_text = ""
        index = 0
        while index < len(body) and body[index].isdigit():
            number_text += body[index]
            index += 1
        if not number_text:
            self._warn(f"bad aperture definition %AD{body}")
            return
        number = int(number_text)
        template = body[index:].strip()
        if not template:
            self._warn(f"aperture {number} has no template")
            return
        kind_char = template[0].upper()
        if template in self.image.macros:
            # The template names an aperture macro defined by a %AM statement.
            macro = self.image.macros[template]
            self.image.apertures[number] = DCode(number, APERTURE_MACRO, (), (), macro)
            if number == self._current_dcode:
                self._update_current_width()
            return
        if not (len(template) > 1 and template[1] == ","):
            # Not a standard template: a standard one is a single letter
            # followed by the parameter list, so this has to name an
            # aperture macro.  A macro name may start with the same letter
            # as a standard template (ROUNDEDRECTD16 for instance), and
            # treating it as a rectangle would silently drop the shape.
            self._pending_macro_apertures.append((number, template))
            return
        params_text = template[1:]
        hole: list[float] = []
        params: list[float] = []
        if params_text.startswith(","):
            params_text = params_text[1:]
        chunks = [c.strip() for c in params_text.split("X")] if params_text else []
        numbers: list[float] = []
        for chunk in chunks:
            if not chunk:
                continue
            try:
                numbers.append(float(chunk))
            except ValueError:
                self._warn(f"aperture {number} has a non numeric parameter {chunk!r}")

        if kind_char == "C":
            if len(numbers) >= 2:
                kind = "circle"
                params = [numbers[0]]
                hole = ["circle", numbers[1]]
            else:
                kind = APERTURE_CIRCLE
                params = numbers[:1]
        elif kind_char == "R":
            kind = APERTURE_RECT
            params = numbers[:2]
            if len(numbers) >= 4:
                hole = ["rect", numbers[2], numbers[3]]
        elif kind_char == "O":
            kind = APERTURE_OBLONG
            params = numbers[:2]
            if len(numbers) >= 4:
                hole = ["rect", numbers[2], numbers[3]]
        elif kind_char == "P":
            kind = APERTURE_POLYGON
            params = numbers[:3]
            if len(numbers) >= 5:
                hole = ["circle", numbers[4]]
        else:
            # Not a standard template: it has to name an aperture macro.
            self._pending_macro_apertures.append((number, template))
            return

        self.image.apertures[number] = DCode(number, kind, tuple(params), tuple(hole))
        if self._pending_aperture_attributes:
            # The attribute was written before the aperture was defined.
            self.image.apertures[number].attributes.update(
                self._pending_aperture_attributes)
            self._pending_aperture_attributes = {}
        if number == self._current_dcode:
            self._update_current_width()

    def _run_am(self, name: str, body_lines: list[str]) -> None:
        if not name:
            self._warn("aperture macro without a name")
            return
        try:
            macro = parse_macro_body(name, body_lines)
        except MacroError as exc:
            self._warn(f"aperture macro {name} ignored: {exc}")
            self.image.degraded = True
            return
        if not macro.supported:
            unknown = sorted({p.code for p in macro.primitives
                              if p.code not in KNOWN_PRIMITIVES})
            self._warn(f"aperture macro {name} uses unsupported primitive(s) {unknown}")
            self.image.degraded = True
        self.image.macros[name] = macro

    def _run_sr(self, body: str) -> None:
        """``%SR[X<n>][Y<n>][I<step>][J<step>]*%``"""
        upper = body.upper()
        x_repeat = y_repeat = 1
        step_x = step_y = 0.0
        for key in ("X", "Y", "I", "J"):
            marker = f"{key}"
            pos = upper.find(marker)
            if pos < 0:
                continue
            rest = upper[pos + 1:]
            digits = ""
            index = 0
            while index < len(rest) and (rest[index].isdigit() or rest[index] == "."):
                digits += rest[index]
                index += 1
            if not digits:
                continue
            try:
                value = float(digits)
            except ValueError:
                continue
            if key == "X":
                x_repeat = max(1, int(value))
            elif key == "Y":
                y_repeat = max(1, int(value))
            elif key == "I":
                step_x = value
            elif key == "J":
                step_y = value
        # A new %SR closes the block that is still open.
        self._close_sr_block()
        self._sr_stack.append((len(self.image.items), (x_repeat, y_repeat, step_x, step_y)))

    def _close_sr_block(self) -> None:
        if not self._sr_stack:
            return
        start, params = self._sr_stack.pop()
        if params is None:
            return
        x_repeat, y_repeat, step_x, step_y = params
        if x_repeat <= 1 and y_repeat <= 1:
            return
        block = self.image.items[start:]
        if not block:
            return
        for j in range(y_repeat):
            for i in range(x_repeat):
                if i == 0 and j == 0:
                    continue
                dx = i * step_x * IU_PER_MM
                dy = j * step_y * IU_PER_MM
                for item in block:
                    self.image.items.append(_offset_item(item, dx, dy))

    def _run_sf(self, body: str) -> None:
        upper = body.upper()
        values = []
        for chunk in upper.replace(",", "X").split("X"):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                values.append(float(chunk))
            except ValueError:
                pass
        if values:
            self._has_image_transform = True
            self._scale_a = values[0]
        if len(values) > 1:
            self._scale_b = values[1]

    def _run_of(self, body: str) -> None:
        values = []
        for chunk in body.replace(",", "X").split("X"):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                values.append(float(chunk))
            except ValueError:
                pass
        if values:
            self._has_image_transform = True
            self._offset_a = values[0]
        if len(values) > 1:
            self._offset_b = values[1]

    def _store_aperture_attribute(self, body: str) -> None:
        """Store an aperture attribute (%TA) with the selected aperture.

        The attributes of an aperture belong to the aperture, not to
        the file.
        """
        aperture = self.image.apertures.get(self._current_dcode)
        if aperture is None:
            # The attribute arrives before the aperture is defined; it
            # is kept until the aperture appears.
            self._store_attribute(self._pending_aperture_attributes, body)
            return
        self._store_attribute(aperture.attributes, body)


    def _take_object_attributes(self) -> dict:
        """The attributes of the object that is created now.

        An object attribute (%TO) belongs to the next object only.
        """
        if not self._pending_object_attributes:
            return {}
        attributes = self._pending_object_attributes
        self._pending_object_attributes = {}
        return attributes


    def _store_attribute(self, target: dict, body: str) -> None:
        """Store one X2 attribute.

        The statement reads ``%TA.<name>,<value>*%``: the name of the
        attribute follows the dot of the statement, and its value is
        separated by a comma.
        """
        body = body.strip()
        if body.startswith("."):
            body = body[1:]
        if "," in body:
            key, value = body.split(",", 1)
        else:
            key, value = body, ""
        target[key.strip()] = value.strip()

    def _drop_attribute(self, body: str) -> None:
        key = body.split(".", 1)[0].strip()
        self.image.attributes.pop(key, None)

    # ------------------------------------------------------------------
    # classic commands
    # ------------------------------------------------------------------
    def _run_command(self, command: str) -> None:
        stripped = command.strip()
        if not stripped:
            return
        if stripped[0] == "G" and _COMMENT_RE.match(stripped):
            # A G04 comment runs to the end of the command.
            return

        # Almost every command of a real file carries a coordinate and an
        # operation.  Matching that shape in one go avoids walking the words
        # of the command one by one.
        match = _DRAW_RE.fullmatch(stripped)
        if match is not None:
            x_text, y_text, operation = match.groups()
            self._run_draw(x_text, y_text, int(operation))
            return

        for letter, digits in _WORD_RE.findall(stripped):
            if letter == "X":
                if digits:
                    self._pending_x = digits
            elif letter == "Y":
                if digits:
                    self._pending_y = digits
            elif letter == "D":
                if digits:
                    self._on_dcode(int(digits))
            elif letter == "G":
                if digits:
                    self._on_gcode(int(digits))
            elif letter == "I":
                if digits:
                    self._pending_i = digits
                    self._has_pending_i = True
                    self._has_pending_ij = True
            elif letter == "J":
                if digits:
                    self._pending_j = digits
                    self._has_pending_j = True
                    self._has_pending_ij = True
            elif letter == "M":
                if digits:
                    value = int(digits)
                    if value in (0, 1, 2):
                        self._finish()
            # N (line number) is ignored.

        self._apply_pending()

    def _run_draw(self, x_text: str, y_text: str, operation: int) -> None:
        """Handle a command that carries a coordinate and an operation."""
        self._pending_x = None
        self._pending_y = None
        self._has_pending_i = False
        self._has_pending_j = False
        self._has_pending_ij = False
        # The operation stays in effect for the next command, which may only
        # carry a coordinate.
        self._last_operation = operation
        fmt = self._format
        if fmt is None or not self._absolute or self._region:
            # Rare shapes go through the general handling.
            self._pending_x = x_text
            self._pending_y = y_text
            self._on_dcode(operation)
            return

        scale = self._unit_scale * IU_PER_MM
        x = int(fmt.x.decode(x_text) * scale)
        y = int(fmt.y.decode(y_text) * scale)
        if operation == 2:
            self._current_x = x
            self._current_y = y
            return
        if operation == 1:
            self._draw_segment(x, y)
        else:
            self._flash(x, y)
        self._current_x = x
        self._current_y = y

    def _on_gcode(self, value: int) -> None:
        if value == 1:
            self._interpolation = "linear"
        elif value == 2:
            self._interpolation = "cw"
        elif value == 3:
            self._interpolation = "ccw"
        elif value == 36:
            self._region = True
            self._region_contours = []
            self._region_current = []
            self._region_start = None
        elif value == 37:
            self._close_region()
        elif value == 54:
            pass  # the D code that follows selects the aperture
        elif value == 55:
            pass  # deprecated photo mode
        elif value == 70:
            self._unit_scale = MM_PER_INCH
        elif value == 71:
            self._unit_scale = 1.0
        elif value == 74 or value == 75:
            pass  # single / multi quadrant; the multi quadrant reading is used
        elif value == 90:
            self._absolute = True
        elif value == 91:
            self._absolute = False

    def _on_dcode(self, value: int) -> None:
        if value >= FIRST_APERTURE_DCODE:
            self._current_dcode = value
            self._update_current_width()
            return
        if value in (1, 2, 3):
            self._last_operation = value
            self._execute_operation(value)
            self._pending_x = None
            self._pending_y = None
            self._has_pending_i = False
            self._has_pending_j = False
            self._has_pending_ij = False
            return
        if value == 0:
            return

    def _apply_pending(self) -> None:
        """A coordinate word without an operation code reuses the last one."""
        if self._pending_x is None and self._pending_y is None:
            return
        if self._last_operation is None:
            # Coordinates without any operation: remember them for the next
            # operation code, which is what the specification means by a
            # coordinate statement.
            return
        self._execute_operation(self._last_operation)
        self._pending_x = None
        self._pending_y = None
        self._has_pending_i = False
        self._has_pending_j = False
        self._has_pending_ij = False

    # ------------------------------------------------------------------
    # operations
    # ------------------------------------------------------------------
    def _execute_operation(self, operation: int) -> None:
        target_x, target_y = self._resolve_target()
        if operation == 2:
            # Move: the new position becomes the current one.
            if self._region:
                self._close_contour()
                self._region_start = (target_x, target_y)
                self._region_current = [(target_x, target_y)]
            self._current_x = target_x
            self._current_y = target_y
            return

        if operation == 3:
            self._flash(target_x, target_y)
            self._current_x = target_x
            self._current_y = target_y
            return

        # D01 - draw
        if self._region:
            self._region_current.append((target_x, target_y))
            if self._interpolation in ("cw", "ccw") and self._has_pending_ij:
                self._flatten_region_arc(target_x, target_y)
            self._current_x = target_x
            self._current_y = target_y
            return

        if self._interpolation in ("cw", "ccw") and self._has_pending_ij:
            self._draw_arc(target_x, target_y)
        else:
            self._draw_segment(target_x, target_y)
        self._current_x = target_x
        self._current_y = target_y

    def _resolve_target(self) -> tuple[int, int]:
        """Compute the target position of the pending coordinate words."""
        fmt = self._format
        scale = self._unit_scale * IU_PER_MM
        if fmt is None:
            # No %FS seen: assume the raw digits are millimetres.
            x = self._current_x
            y = self._current_y
            if self._pending_x is not None:
                x = int(round(float(self._pending_x) * scale))
            if self._pending_y is not None:
                y = int(round(float(self._pending_y) * scale))
            return (x, y)

        if self._absolute:
            x = self._current_x
            y = self._current_y
            if self._pending_x is not None:
                x = int(round(fmt.x.decode(self._pending_x) * scale))
            if self._pending_y is not None:
                y = int(round(fmt.y.decode(self._pending_y) * scale))
            return (x, y)

        # Incremental: a missing axis keeps its value.
        x = self._current_x
        y = self._current_y
        if self._pending_x is not None:
            x = self._current_x + int(round(fmt.x.decode(self._pending_x) * scale))
        if self._pending_y is not None:
            y = self._current_y + int(round(fmt.y.decode(self._pending_y) * scale))
        return (x, y)

    def _draw_segment(self, target_x: int, target_y: int) -> None:
        width = self._current_width
        item = DrawItem(
            kind=KIND_SEGMENT,
            x=self._current_x,
            y=self._current_y,
            x2=target_x,
            y2=target_y,
            width=width,
            dcode=self._current_dcode,
            negative=not self._polarity_dark,
            attributes=self._take_object_attributes(),
        )
        if self._has_image_transform:
            self._apply_image_transform(item)
        self.image.items.append(item)

    def _update_current_width(self) -> None:
        """The pen width of the current aperture, in internal units."""
        aperture = self.image.apertures.get(self._current_dcode)
        if aperture is None:
            self._current_width = 0
        else:
            self._current_width = int(round(
                aperture.line_width() * self._unit_scale * IU_PER_MM))

    def _decode_axis(self, axis, raw: str) -> int:
        """Decode one coordinate word into internal units."""
        fmt = self._format
        if fmt is None:
            # No %FS seen: treat the raw digits as millimetres.
            return int(round(float(raw) * self._unit_scale * IU_PER_MM))
        return int(round(axis.decode(raw) * self._unit_scale * IU_PER_MM))

    def _draw_arc(self, target_x: int, target_y: int) -> None:
        width = self._current_width
        # I and J are always relative to the start point and use the same
        # digit format as the X and Y axes.  An axis that is not given
        # counts as zero, it does not keep the value of an earlier command.
        fmt = self._format
        if fmt is not None:
            offset_x = self._decode_axis(fmt.x, self._pending_i if self._has_pending_i else "0")
            offset_y = self._decode_axis(fmt.y, self._pending_j if self._has_pending_j else "0")
        else:
            offset_x = int(round(float(self._pending_i if self._has_pending_i else 0)
                                 * self._unit_scale * IU_PER_MM))
            offset_y = int(round(float(self._pending_j if self._has_pending_j else 0)
                                 * self._unit_scale * IU_PER_MM))
        centre_x = self._current_x + offset_x
        centre_y = self._current_y + offset_y
        item = DrawItem(
            kind=KIND_ARC,
            x=self._current_x,
            y=self._current_y,
            x2=target_x,
            y2=target_y,
            cx=centre_x,
            cy=centre_y,
            width=width,
            clockwise=(self._interpolation == "cw"),
            dcode=self._current_dcode,
            negative=not self._polarity_dark,
            attributes=self._take_object_attributes(),
        )
        self._emit(item)

    def _flash(self, target_x: int, target_y: int) -> None:
        aperture = self.image.apertures.get(self._current_dcode)
        if aperture is None:
            self._warn(f"D03 without a defined aperture (D{self._current_dcode})")
            return
        scale = self._unit_scale * IU_PER_MM
        fx = target_x / scale
        fy = target_y / scale
        shapes = aperture.shapes_at(fx, fy)
        negative = not self._polarity_dark
        if aperture.kind == APERTURE_MACRO:
            kind = KIND_MACRO
        elif aperture.kind == APERTURE_CIRCLE:
            kind = KIND_CIRCLE
        elif aperture.kind == APERTURE_RECT:
            kind = KIND_RECT
        elif aperture.kind == APERTURE_OBLONG:
            kind = KIND_OBLONG
        elif aperture.kind == APERTURE_POLYGON:
            kind = KIND_POLYGON
        else:
            kind = KIND_CIRCLE

        item = DrawItem(
            kind=kind,
            x=target_x,
            y=target_y,
            diameter=int(round(aperture.params[0] * scale)) if aperture.params else 0,
            height=int(round(aperture.params[1] * scale)) if len(aperture.params) > 1 else 0,
            rotation=aperture.params[2] if len(aperture.params) > 2 else 0.0,
            dcode=self._current_dcode,
            negative=negative,
            attributes=self._take_object_attributes(),
        )
        if kind == KIND_POLYGON:
            item.points = tuple(
                (int(round(px * scale)), int(round(py * scale)))
                for px, py in _aperture_polygon_points(aperture, fx, fy)
            )
        if kind == KIND_MACRO:
            item.macro_shapes = tuple(
                _shape_to_iu(self._transform_shape(shape), scale) for shape in shapes
            )
        self._emit(item)

    def _emit(self, item: DrawItem) -> None:
        if self._has_image_transform:
            self._apply_image_transform(item)
        self.image.items.append(item)

    # ------------------------------------------------------------------
    # region handling
    # ------------------------------------------------------------------
    def _close_contour(self) -> None:
        if len(self._region_current) >= 3:
            self._region_contours.append(list(self._region_current))
        self._region_current = []
        self._region_start = None

    def _close_region(self) -> None:
        self._close_contour()
        self._region = False
        contours = [contour for contour in self._region_contours
                    if len(contour) >= 3]
        self._region_contours = []
        if not contours:
            return
        closed = []
        for contour in contours:
            if contour[0] != contour[-1]:
                contour = contour + [contour[0]]
            closed.append(contour)
        # The contours of one G36 block stay together: an inner contour
        # cuts itself out of the outer one, so the holes of a pour keep
        # being holes.  Each one alone would be filled as its own island.
        item = DrawItem(
            kind=KIND_POLYGON,
            x=closed[0][0][0],
            y=closed[0][0][1],
            points=tuple(closed[0]),
            holes=tuple(tuple(contour) for contour in closed[1:]),
            negative=not self._polarity_dark,
            attributes=self._take_object_attributes(),
        )
        self._emit(item)

    def _flatten_region_arc(self, target_x: int, target_y: int) -> None:
        """An arc inside a region is flattened into points."""
        fmt = self._format
        if fmt is not None:
            offset_x = self._decode_axis(fmt.x, self._pending_i if self._has_pending_i else "0")
            offset_y = self._decode_axis(fmt.y, self._pending_j if self._has_pending_j else "0")
        else:
            offset_x = int(round(float(self._pending_i if self._has_pending_i else 0)
                                 * self._unit_scale * IU_PER_MM))
            offset_y = int(round(float(self._pending_j if self._has_pending_j else 0)
                                 * self._unit_scale * IU_PER_MM))
        centre_x = self._current_x + offset_x
        centre_y = self._current_y + offset_y
        r = math.hypot(self._current_x - centre_x, self._current_y - centre_y)
        if r <= 0:
            return
        start = math.atan2(self._current_y - centre_y, self._current_x - centre_x)
        end = math.atan2(target_y - centre_y, target_x - centre_x)
        if self._interpolation == "cw":
            sweep = -((start - end) % (2 * math.pi))
        else:
            sweep = (end - start) % (2 * math.pi)
        if abs(sweep) < 1e-12:
            sweep = -2 * math.pi if self._interpolation == "cw" else 2 * math.pi
        tolerance = REGION_CHORD_ERROR_MM * IU_PER_MM
        denominator = max(1.0 - tolerance / r, 0.0)
        step = math.acos(min(denominator, 1.0))
        steps = max(2, int(math.ceil(abs(sweep) / step)))
        for index in range(1, steps):
            angle = start + sweep * index / steps
            px = int(round(centre_x + r * math.cos(angle)))
            py = int(round(centre_y + r * math.sin(angle)))
            self._region_current.append((px, py))

    # ------------------------------------------------------------------
    # image level transform
    # ------------------------------------------------------------------
    def _apply_image_transform(self, item: DrawItem) -> None:
        if not self._has_image_transform:
            return
        scale = self._unit_scale * IU_PER_MM
        item.x, item.y = self._transform_point(item.x, item.y, scale)
        item.x2, item.y2 = self._transform_point(item.x2, item.y2, scale)
        item.cx, item.cy = self._transform_point(item.cx, item.cy, scale)
        if item.points:
            item.points = tuple(
                self._transform_point(px, py, scale) for px, py in item.points
            )

    def _transform_point(self, x: int, y: int, scale: float) -> tuple[int, int]:
        """Apply the image level transform to one point given in internal units."""
        fx, fy = self._transform_point_units(x / scale, y / scale)
        return (int(round(fx * scale)), int(round(fy * scale)))

    def _transform_point_units(self, fx: float, fy: float) -> tuple[float, float]:
        """Apply the image level transform to a point in file units."""
        if self._swap_axes:
            fx, fy = fy, fx
        fx *= self._scale_a
        fy *= self._scale_b
        if self._mirror_a:
            fx = -fx
        if self._mirror_b:
            fy = -fy
        if self._rotation:
            rad = math.radians(self._rotation)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            fx, fy = fx * cos_a - fy * sin_a, fx * sin_a + fy * cos_a
        fx += self._offset_a
        fy += self._offset_b
        return (fx, fy)

    def _transform_shape(self, shape: MacroShape) -> MacroShape:
        """Apply the image level transform to a macro shape given in file units."""
        if not (self._mirror_a or self._mirror_b or self._swap_axes
                or self._scale_a != 1.0 or self._scale_b != 1.0
                or self._offset_a or self._offset_b or self._rotation):
            return shape
        if shape.kind == "circle":
            cx, cy = self._transform_point_units(shape.cx, shape.cy)
            return MacroShape(shape.kind, shape.exposure, cx, cy,
                              shape.diameter * self._scale_a, shape.points)
        points = tuple(self._transform_point_units(px, py) for px, py in shape.points)
        return MacroShape(shape.kind, shape.exposure, shape.cx, shape.cy,
                          shape.diameter, points)

    # ------------------------------------------------------------------
    # finishing
    # ------------------------------------------------------------------
    def _finish(self) -> None:
        if self._region:
            self._close_region()
        self._close_sr_block()
        # An aperture may be declared before the macro it names.
        for number, name in self._pending_macro_apertures:
            macro = self.image.macros.get(name)
            if macro is None:
                self._warn(f"aperture {number} references unknown macro {name!r}")
                self.image.degraded = True
                continue
            self.image.apertures[number] = DCode(number, APERTURE_MACRO, (), (), macro)
            if number == self._current_dcode:
                self._update_current_width()
        self._pending_macro_apertures = []

    def _warn(self, message: str) -> None:
        if len(self.image.warnings) < 200:
            self.image.warnings.append(message)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _read_int(text: str, pos: int) -> tuple[int | None, int]:
    start = pos
    while pos < len(text) and text[pos].isdigit():
        pos += 1
    if pos == start:
        return (None, pos)
    return (int(text[start:pos]), pos)


def _read_coord(text: str, pos: int) -> tuple[str | None, int]:
    """Read a (possibly signed) coordinate word.

    The word is returned as a *string*: the number of digits it carries is
    part of the meaning, because the zero suppression declared by ``%FS``
    decides how it is padded.
    """
    start = pos
    sign = ""
    if pos < len(text) and text[pos] in "+-":
        sign = text[pos]
        pos += 1
    digits_start = pos
    while pos < len(text) and text[pos].isdigit():
        pos += 1
    if pos == digits_start:
        return (None, start)
    return (sign + text[digits_start:pos], pos)


def _offset_item(item: DrawItem, dx: int, dy: int) -> DrawItem:
    """Copy of an item shifted by (dx, dy) internal units."""
    clone = DrawItem(
        kind=item.kind, x=item.x + dx, y=item.y + dy,
        x2=item.x2 + dx, y2=item.y2 + dy,
        cx=item.cx + dx, cy=item.cy + dy,
        width=item.width, clockwise=item.clockwise,
        diameter=item.diameter, height=item.height, rotation=item.rotation,
        points=tuple((px + dx, py + dy) for px, py in item.points),
        holes=tuple(
            tuple((px + dx, py + dy) for px, py in contour)
            for contour in item.holes
        ),
        macro_shapes=item.macro_shapes, dcode=item.dcode,
        negative=item.negative, attributes=dict(item.attributes),
    )
    return clone


def _aperture_polygon_points(aperture: DCode, fx: float, fy: float):
    shapes = aperture.shapes_at(fx, fy)
    for shape in shapes:
        if shape.kind == "polygon":
            return shape.points
    return ()


def _shape_to_iu(shape: MacroShape, scale: float) -> MacroShape:
    """Convert a macro shape from file units to internal units."""
    if shape.kind == "circle":
        return MacroShape(shape.kind, shape.exposure,
                          int(round(shape.cx * scale)), int(round(shape.cy * scale)),
                          int(round(shape.diameter * scale)), shape.points)
    return MacroShape(shape.kind, shape.exposure, shape.cx, shape.cy, shape.diameter,
                      tuple((int(round(px * scale)), int(round(py * scale)))
                            for px, py in shape.points))


def parse_file(path: str) -> FileImage:
    """Parse one Gerber file and return the resulting image."""
    return GerberParser.from_path(path).parse()

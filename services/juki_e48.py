"""Juki .e48 export for the QP100 machine.

The layout was reverse engineered from real QP100 files.  A template file is
used for the fixed machine/header blocks; only the data tables and the board
parameters are rewritten.
"""

from __future__ import annotations

import math
import os
import struct
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

from models.pcb_info import PcbInfo
from models.review import ReviewRecord
from services.bom_compare import is_bottom_layer

PLACEMENT_OFFSET = 0x2FD0
PLACEMENT_RECORD_SIZE = 100
PART_RECORD_SIZE = 1043
REFDES_RECORD_SIZE = 12
M001_BLOCK_SIZE = 0x7248
UNKNOWN_BLOCK_SIZE = 2427
MAX_PLACEMENTS = 6000
MAX_PARTS = 700
DESIGNATOR_SIZE = 6
MPN_SIZE = 117


class E48ValidationError(ValueError):
    """Raised when data cannot be represented in a Juki .e48 file."""


@dataclass(frozen=True)
class E48Component:
    designator: str
    mpn: str
    x: float
    y: float
    rotation: float


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<H", data, offset, value)


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", data, offset, value)


def _put_u16_be(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into(">H", data, offset, value)


def _round_half_up(value: float) -> int:
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def _scaled(value: float, factor: float, label: str) -> int:
    result = _round_half_up(float(value) * factor)
    if result < 0 or result > 0xFFFFFFFF:
        raise E48ValidationError(
            f"{label} is outside the range supported by the .e48 format: {value}"
        )
    return result


def _scaled_u16(value: float, factor: float, label: str) -> int:
    result = _round_half_up(float(value) * factor)
    if result < 0 or result > 0xFFFF:
        raise E48ValidationError(
            f"{label} is outside the range supported by the .e48 format: {value}"
        )
    return result


def _scaled_coord(value: float, factor: float, label: str) -> int:
    result = math.floor(float(value) * factor + 1e-9)
    if result < 0 or result > 0xFFFFFFFF:
        raise E48ValidationError(
            f"{label} is outside the range supported by the .e48 format: {value}"
        )
    return result


def _ascii_field(value: str, size: int, label: str) -> bytes:
    text = (value or "").strip()
    if not text:
        raise E48ValidationError(f"{label} must not be empty.")
    try:
        raw = text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise E48ValidationError(
            f"{label} contains non-ASCII characters: {text}"
        ) from exc
    if len(raw) > size:
        raise E48ValidationError(
            f"{label} is longer than {size} characters: {text}"
        )
    return raw.ljust(size, b"\x00")


def missing_pcb_info_fields(pcb: PcbInfo) -> List[str]:
    """Return the human readable names of required PCB fields that are unset."""
    missing: List[str] = []
    if not pcb.board_width or pcb.board_width <= 0:
        missing.append("Board Width")
    if not pcb.board_height or pcb.board_height <= 0:
        missing.append("Board Height")
    if not pcb.working_area_width or pcb.working_area_width <= 0:
        missing.append("Working Area Width")
    if not pcb.thickness or pcb.thickness <= 0:
        missing.append("Thickness")
    for index in range(1, 4):
        x = getattr(pcb, f"x_boc{index}")
        y = getattr(pcb, f"y_boc{index}")
        if x == 0 and y == 0:
            missing.append(f"BOC {index}")
    return missing


def components_from_review_records(
    records: Sequence[ReviewRecord], bottom: bool
) -> List[E48Component]:
    """Build the export list for one side from reviewed records."""
    selected = [
        record
        for record in records
        if record.status != "Deleted" and is_bottom_layer(record.layer) == bottom
    ]
    selected.sort(key=lambda record: record.row_index)

    components: List[E48Component] = []
    for record in selected:
        if record.block or record.block_rotation:
            raise E48ValidationError(
                "Panelized data is not supported for Juki .e48 export."
            )
        designator = (record.designator or "").strip()
        if not designator:
            continue
        x = record.new_x if record.new_x is not None else record.old_x
        y = record.new_y if record.new_y is not None else record.old_y
        rotation = (
            record.new_rotation
            if record.new_rotation is not None
            else record.old_rotation
        )
        components.append(
            E48Component(
                designator=designator,
                mpn=(record.mpn or "").strip(),
                x=float(x or 0.0),
                y=float(y or 0.0),
                rotation=float(rotation or 0.0),
            )
        )
    return components


def _validate_template(template: bytes) -> None:
    if len(template) < PLACEMENT_OFFSET:
        raise E48ValidationError("The selected .e48 template is too small.")
    placement_offset = _u32(template, 0x56)
    if placement_offset != PLACEMENT_OFFSET:
        raise E48ValidationError(
            "The selected .e48 template uses an unsupported layout."
        )
    if _u16(template, 0x5E) != PLACEMENT_RECORD_SIZE:
        raise E48ValidationError(
            "The selected .e48 template has an unsupported placement size."
        )
    if _u16(template, 0x6E) != PART_RECORD_SIZE:
        raise E48ValidationError(
            "The selected .e48 template has an unsupported part size."
        )
    if _u16(template, 0xEE) != REFDES_RECORD_SIZE:
        raise E48ValidationError(
            "The selected .e48 template has an unsupported refdes size."
        )
    m001_offset = _u32(template, 0x86)
    unknown_offset = _u32(template, 0xD6)
    if m001_offset + M001_BLOCK_SIZE > len(template):
        raise E48ValidationError("The selected .e48 template is incomplete.")
    if unknown_offset + UNKNOWN_BLOCK_SIZE > len(template):
        raise E48ValidationError("The selected .e48 template is incomplete.")


def _build_part_table(
    components: Sequence[E48Component],
) -> tuple[List[bytes], List[int]]:
    part_names: List[bytes] = []
    usage: List[int] = []
    index_by_mpn: dict[str, int] = {}
    for component in components:
        mpn = (component.mpn or "").strip()
        if not mpn:
            raise E48ValidationError(
                f"Component {component.designator!r} has no MPN."
            )
        if mpn not in index_by_mpn:
            index_by_mpn[mpn] = len(part_names)
            part_names.append(_ascii_field(mpn, MPN_SIZE, "MPN"))
            usage.append(0)
        usage[index_by_mpn[mpn]] += 1
    return part_names, usage


def build_e48_bytes(
    template: bytes,
    pcb_info: PcbInfo,
    components: Sequence[E48Component],
    timestamp: Optional[int] = None,
) -> bytes:
    """Build a complete .e48 file from a template and reviewed components."""
    _validate_template(template)

    missing = missing_pcb_info_fields(pcb_info)
    if missing:
        raise E48ValidationError(
            "PCB Info is incomplete: " + ", ".join(missing)
        )

    n = len(components)
    if n > MAX_PLACEMENTS:
        raise E48ValidationError(
            f"Too many placements for a .e48 file: {n} (maximum {MAX_PLACEMENTS})."
        )

    part_names, part_usage = _build_part_table(components)
    part_count = len(part_names)
    if part_count > MAX_PARTS:
        raise E48ValidationError(
            f"Too many unique parts for a .e48 file: {part_count} "
            f"(maximum {MAX_PARTS})."
        )

    placement_offset = PLACEMENT_OFFSET
    part_offset = placement_offset + n * PLACEMENT_RECORD_SIZE
    m001_offset = part_offset + part_count * PART_RECORD_SIZE
    unknown_offset = m001_offset + M001_BLOCK_SIZE
    refdes_offset = unknown_offset + UNKNOWN_BLOCK_SIZE
    file_size = refdes_offset + n * REFDES_RECORD_SIZE

    data = bytearray(template[:placement_offset])
    data.extend(b"\x00" * (file_size - placement_offset))

    # The title is not written; the output filename is the title in the UI.
    data[0x00:0x20] = b"\x00" * 0x20

    _put_u32(data, 0x56, placement_offset)
    _put_u16(data, 0x5E, PLACEMENT_RECORD_SIZE)
    _put_u16(data, 0x62, n)
    _put_u32(data, 0x66, part_offset)
    _put_u16(data, 0x6E, PART_RECORD_SIZE)
    _put_u16(data, 0x72, part_count)
    _put_u32(data, 0x86, m001_offset)
    _put_u32(data, 0xD6, unknown_offset)
    _put_u32(data, 0xE6, refdes_offset)
    _put_u16(data, 0xEE, REFDES_RECORD_SIZE)
    _put_u16(data, 0xF2, n)

    _put_u32(data, 0x228, n * PLACEMENT_RECORD_SIZE)
    _put_u16(data, 0x230, MAX_PLACEMENTS - n)
    _put_u16(data, 0x234, n)
    _put_u16(data, 0x238, n)
    _put_u32(data, 0x23C, part_count * PART_RECORD_SIZE)
    _put_u16(data, 0x240, PART_RECORD_SIZE)
    _put_u16(data, 0x244, MAX_PARTS - part_count)
    _put_u32(data, 0x248, part_count)
    _put_u32(data, 0x2F0, n * REFDES_RECORD_SIZE)
    _put_u16(data, 0x2F4, REFDES_RECORD_SIZE)
    _put_u16(data, 0x2F8, MAX_PLACEMENTS - n)
    _put_u16(data, 0x2FC, n)
    _put_u16(data, 0x300, n)

    _put_u32(data, 0x43E, int(timestamp if timestamp is not None else time.time()))
    _put_u32(data, 0x448, _scaled(pcb_info.board_width, 10000, "Board Width"))
    _put_u32(data, 0x44C, _scaled(pcb_info.board_height, 10000, "Board Height"))
    _put_u32(
        data, 0x450, _scaled(pcb_info.position_working, 10000, "Position Working")
    )
    _put_u32(
        data, 0x458,
        _scaled(pcb_info.working_area_width, 10000, "Working Area Width"),
    )
    _put_u16(
        data, 0x460,
        _scaled_u16(pcb_info.thickness, 39.3701, "Thickness"),
    )

    # Placements.
    for index, component in enumerate(components):
        offset = placement_offset + index * PLACEMENT_RECORD_SIZE
        data[offset:offset + DESIGNATOR_SIZE] = _ascii_field(
            component.designator, DESIGNATOR_SIZE, "Designator"
        )
        _put_u16(data, offset + 0x06, 2)
        _put_u32(data, offset + 0x08, _scaled_coord(component.x, 10000, "X"))
        _put_u32(data, offset + 0x0C, _scaled_coord(component.y, 10000, "Y"))
        rotation = float(component.rotation) % 360.0
        _put_u16(data, offset + 0x10, _scaled_u16(rotation, 80, "Rotation"))
        _put_u16(data, offset + 0x12, 4)
        _put_u16_be(data, offset + 0x1C, 31)

    # Part table.
    for index, (name, count) in enumerate(zip(part_names, part_usage)):
        offset = part_offset + index * PART_RECORD_SIZE
        data[offset:offset + MPN_SIZE] = name
        data[offset + 0x75] = 1
        data[offset + 0x76] = count & 0xFF
        data[offset + 0x77] = (count >> 8) & 0xFF

    # The part index is written after the part table is known.
    part_index_by_mpn = {
        name.rstrip(b"\x00").decode("ascii"): index
        for index, name in enumerate(part_names)
    }
    for index, component in enumerate(components):
        offset = placement_offset + index * PLACEMENT_RECORD_SIZE
        part_index = part_index_by_mpn[(component.mpn or "").strip()]
        _put_u16_be(data, offset + 0x1E, part_index)

    # M001 block: copy the template block and overwrite the three marks.
    template_m001_offset = _u32(template, 0x86)
    data[m001_offset:m001_offset + M001_BLOCK_SIZE] = template[
        template_m001_offset:template_m001_offset + M001_BLOCK_SIZE
    ]
    m001 = bytearray(data[m001_offset:m001_offset + M001_BLOCK_SIZE])
    _put_u16(m001, 0x12, 3)
    for index in range(3):
        mark_offset = 0x20 + index * 0x80
        m001[mark_offset:mark_offset + 0x80] = b"\x00" * 0x80
        _put_u32(
            m001, mark_offset + 0x08,
            _scaled(getattr(pcb_info, f"x_boc{index + 1}"), 10000, f"BOC {index + 1} X"),
        )
        _put_u32(
            m001, mark_offset + 0x0C,
            _scaled(getattr(pcb_info, f"y_boc{index + 1}"), 10000, f"BOC {index + 1} Y"),
        )
        _put_u32(m001, mark_offset + 0x10, 0x00030000)
    data[m001_offset:m001_offset + M001_BLOCK_SIZE] = m001

    # Unknown block: copy verbatim from the template.
    template_unknown_offset = _u32(template, 0xD6)
    data[unknown_offset:unknown_offset + UNKNOWN_BLOCK_SIZE] = template[
        template_unknown_offset:template_unknown_offset + UNKNOWN_BLOCK_SIZE
    ]

    # Refdes table.
    for index, component in enumerate(components):
        offset = refdes_offset + index * REFDES_RECORD_SIZE
        data[offset] = 0
        data[offset + 1:offset + 1 + DESIGNATOR_SIZE] = _ascii_field(
            component.designator, DESIGNATOR_SIZE, "Designator"
        )

    return bytes(data)


def export_e48(
    template_path: str,
    output_path: str,
    pcb_info: PcbInfo,
    components: Sequence[E48Component],
    timestamp: Optional[int] = None,
) -> str:
    with open(template_path, "rb") as handle:
        template = handle.read()
    payload = build_e48_bytes(template, pcb_info, components, timestamp=timestamp)
    parent = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(parent, exist_ok=True)
    with open(output_path, "wb") as handle:
        handle.write(payload)
    return output_path

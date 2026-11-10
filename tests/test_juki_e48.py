import csv
import struct
from pathlib import Path

import openpyxl
import pytest

from models.pcb_info import PcbInfo
from models.review import ReviewRecord
from services.juki_e48 import (
    E48Component,
    E48ValidationError,
    MAX_PARTS,
    MAX_PLACEMENTS,
    PART_RECORD_SIZE,
    PLACEMENT_OFFSET,
    PLACEMENT_RECORD_SIZE,
    REFDES_RECORD_SIZE,
    build_e48_bytes,
    components_from_review_records,
    export_e48,
    missing_pcb_info_fields,
)

FIXTURES = Path(__file__).parent / "fixtures" / "e48"


def _pcb_from_row(row) -> PcbInfo:
    values = [float(value) for value in row[:11]]
    return PcbInfo(
        board_width=values[0],
        board_height=values[1],
        working_area_width=values[2],
        position_working=values[3],
        x_boc1=values[4],
        y_boc1=values[5],
        x_boc2=values[6],
        y_boc2=values[7],
        x_boc3=values[8],
        y_boc3=values[9],
        thickness=values[10],
    )


def _components_from_rows(rows) -> list[E48Component]:
    components = []
    for row in rows:
        if not row or not row[0]:
            continue
        components.append(
            E48Component(
                designator=str(row[0]).strip(),
                mpn=str(row[1]).strip(),
                x=float(row[2]),
                y=float(row[3]),
                rotation=float(row[4]),
            )
        )
    return components


def _read_csv(path: Path) -> tuple[PcbInfo, list[E48Component]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    return _pcb_from_row(rows[0]), _components_from_rows(rows[1:])


def _read_xlsx(path: Path) -> tuple[PcbInfo, list[E48Component]]:
    workbook = openpyxl.load_workbook(str(path), data_only=True)
    try:
        rows = list(workbook.active.iter_rows(values_only=True))
    finally:
        workbook.close()
    return _pcb_from_row(rows[0]), _components_from_rows(rows[1:])


def _timestamp(data: bytes) -> int:
    return struct.unpack_from("<I", data, 0x43E)[0]


def _valid_pcb() -> PcbInfo:
    return PcbInfo(
        board_width=190.0,
        board_height=100.0,
        working_area_width=190.0,
        position_working=0.0,
        x_boc1=9.261,
        y_boc1=23.45,
        x_boc2=9.756,
        y_boc2=82.461,
        x_boc3=174.99,
        y_boc3=71.61,
        thickness=1.6,
    )


def _template() -> bytes:
    return (FIXTURES / "tnm103_top.e48").read_bytes()


@pytest.mark.parametrize("stem", ["tnm103_top", "tnm103_bot"])
def test_round_trip_tnm103(stem):
    pcb, components = _read_csv(FIXTURES / f"{stem}.csv")
    expected = (FIXTURES / f"{stem}.e48").read_bytes()
    assert build_e48_bytes(
        expected, pcb, components, timestamp=_timestamp(expected)
    ) == expected


def test_round_trip_tnm102_with_tnm103_template():
    pcb, components = _read_xlsx(FIXTURES / "tnm102_top.xlsx")
    template = (FIXTURES / "tnm103_top.e48").read_bytes()
    expected = (FIXTURES / "tnm102_top.e48").read_bytes()
    assert build_e48_bytes(
        template, pcb, components, timestamp=_timestamp(expected)
    ) == expected


def test_export_e48_writes_file(tmp_path):
    pcb, components = _read_csv(FIXTURES / "tnm103_top.csv")
    expected = (FIXTURES / "tnm103_top.e48").read_bytes()
    output = tmp_path / "out" / "tnm103_top.e48"
    result = export_e48(
        str(FIXTURES / "tnm103_top.e48"),
        str(output),
        pcb,
        components,
        timestamp=_timestamp(expected),
    )
    assert result == str(output)
    assert output.read_bytes() == expected


def test_header_counts_offsets_and_capacity():
    components = [
        E48Component("R1", "A", 1.0, 2.0, 90.0),
        E48Component("R2", "A", 3.0, 4.0, 180.0),
        E48Component("C1", "B", 5.0, 6.0, 0.0),
    ]
    data = build_e48_bytes(_template(), _valid_pcb(), components, timestamp=123)

    part_offset = PLACEMENT_OFFSET + 3 * PLACEMENT_RECORD_SIZE
    m001_offset = part_offset + 2 * PART_RECORD_SIZE
    unknown_offset = m001_offset + 0x7248
    refdes_offset = unknown_offset + 2427

    assert struct.unpack_from("<H", data, 0x62)[0] == 3
    assert struct.unpack_from("<H", data, 0x72)[0] == 2
    assert struct.unpack_from("<I", data, 0x66)[0] == part_offset
    assert struct.unpack_from("<I", data, 0x86)[0] == m001_offset
    assert struct.unpack_from("<I", data, 0xD6)[0] == unknown_offset
    assert struct.unpack_from("<I", data, 0xE6)[0] == refdes_offset
    assert struct.unpack_from("<I", data, 0x228)[0] == 3 * PLACEMENT_RECORD_SIZE
    assert struct.unpack_from("<I", data, 0x23C)[0] == 2 * PART_RECORD_SIZE
    assert struct.unpack_from("<I", data, 0x248)[0] == 2
    assert struct.unpack_from("<I", data, 0x2F0)[0] == 3 * REFDES_RECORD_SIZE
    assert struct.unpack_from("<H", data, 0x230)[0] == MAX_PLACEMENTS - 3
    assert struct.unpack_from("<H", data, 0x244)[0] == MAX_PARTS - 2
    assert struct.unpack_from("<I", data, 0x43E)[0] == 123
    assert len(data) == refdes_offset + 3 * REFDES_RECORD_SIZE


def test_components_from_review_records_filters_and_orders():
    records = [
        ReviewRecord(
            designator="R2", mpn="B", layer="Bottom",
            old_x=2.0, old_y=2.0, old_rotation=0.0, row_index=2,
        ),
        ReviewRecord(
            designator="R1", mpn="A", layer="Top",
            old_x=1.0, old_y=1.0, old_rotation=0.0, row_index=1,
        ),
        ReviewRecord(
            designator="R3", mpn="C", layer="Top",
            old_x=3.0, old_y=3.0, old_rotation=0.0, row_index=3,
            status="Deleted",
        ),
        ReviewRecord(
            designator="R4", mpn="D", layer="Top",
            old_x=4.0, old_y=4.0, old_rotation=0.0, row_index=4,
            new_x=40.0, new_y=50.0, new_rotation=90.0,
        ),
    ]

    top = components_from_review_records(records, bottom=False)
    assert [component.designator for component in top] == ["R1", "R4"]
    assert top[1].x == 40.0
    assert top[1].y == 50.0
    assert top[1].rotation == 90.0

    bottom = components_from_review_records(records, bottom=True)
    assert [component.designator for component in bottom] == ["R2"]


def test_components_from_review_records_rejects_panelized_data():
    record = ReviewRecord(
        designator="R1", mpn="A", layer="Top", old_x=1.0, old_y=1.0,
        block=1,
    )
    with pytest.raises(E48ValidationError, match="Panelized"):
        components_from_review_records([record], bottom=False)


def test_missing_pcb_info_fields():
    empty = PcbInfo(
        board_width=0.0,
        board_height=0.0,
        working_area_width=0.0,
        thickness=0.0,
    )
    assert missing_pcb_info_fields(empty) == [
        "Board Width",
        "Board Height",
        "Working Area Width",
        "Thickness",
        "BOC 1",
        "BOC 2",
        "BOC 3",
    ]
    assert missing_pcb_info_fields(_valid_pcb()) == []


def test_validation_rejects_bad_fields():
    pcb = _valid_pcb()
    with pytest.raises(E48ValidationError, match="Designator"):
        build_e48_bytes(
            _template(), pcb, [E48Component("TOOLONG", "A", 1.0, 2.0, 0.0)],
        )
    with pytest.raises(E48ValidationError, match="MPN"):
        build_e48_bytes(
            _template(), pcb, [E48Component("R1", "", 1.0, 2.0, 0.0)],
        )
    with pytest.raises(E48ValidationError, match="non-ASCII"):
        build_e48_bytes(
            _template(), pcb, [E48Component("R1", "Linh kiện", 1.0, 2.0, 0.0)],
        )
    with pytest.raises(E48ValidationError, match="Board Width"):
        build_e48_bytes(
            _template(), PcbInfo(board_width=-1.0, board_height=1.0,
                                 working_area_width=1.0, thickness=1.6,
                                 x_boc1=1.0, y_boc1=1.0, x_boc2=1.0,
                                 y_boc2=1.0, x_boc3=1.0, y_boc3=1.0),
            [E48Component("R1", "A", 1.0, 2.0, 0.0)],
        )


def test_validation_rejects_too_many_parts():
    components = [
        E48Component(f"R{index}", f"MPN{index}", 1.0, 2.0, 0.0)
        for index in range(MAX_PARTS + 1)
    ]
    with pytest.raises(E48ValidationError, match="Too many unique parts"):
        build_e48_bytes(_template(), _valid_pcb(), components)


def test_validation_rejects_too_many_placements():
    components = [
        E48Component(f"R{index % 1000}", "A", 1.0, 2.0, 0.0)
        for index in range(MAX_PLACEMENTS + 1)
    ]
    with pytest.raises(E48ValidationError, match="Too many placements"):
        build_e48_bytes(_template(), _valid_pcb(), components)

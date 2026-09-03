import csv

import openpyxl

from models.pcb_info import PcbInfo
from models.pickplace import PickPlaceData, PickPlaceComponent
from models.review import ReviewRecord
from services.export_service import ExportService


def _records():
    return [
        ReviewRecord(
            designator="C1", mpn="MPN1", layer="Top",
            old_x=1.0, old_y=2.0, old_rotation=0,
            new_x=3.0, new_y=4.0, new_rotation=90,
            status="Edited", remark="ok", review_time="2026-01-01 00:00:00",
        ),
        ReviewRecord(
            designator="C2", mpn="MPN2", layer="Bottom",
            old_x=5.0, old_y=6.0, old_rotation=0,
            status="Pending",
        ),
    ]


def test_export_report(tmp_path):
    path = tmp_path / "report.xlsx"
    ExportService.export_report(_records(), str(path))
    wb = openpyxl.load_workbook(str(path))
    ws = wb.active
    assert ws.cell(row=1, column=1).value == "Designator"
    assert ws.cell(row=2, column=1).value == "C1"
    assert ws.cell(row=2, column=7).value == 3.0  # New X (edited)
    assert ws.cell(row=3, column=7).value in (None, "")  # New X (pending -> empty)
    assert ws.cell(row=3, column=13).value == "Pending"
    wb.close()


def test_export_pickplace_fixed(tmp_path):
    data = PickPlaceData(
        headers=["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
        components=[
            PickPlaceComponent(designator="C1", mpn="MPN1", layer="Top", x=1, y=2, rotation=0),
            PickPlaceComponent(designator="C2", mpn="MPN2", layer="Bottom", x=5, y=6, rotation=0),
        ],
        raw_data=[
            {"Designator": "C1", "MPN": "MPN1", "Layer": "Top", "X": 1, "Y": 2, "Rotation": 0},
            {"Designator": "C2", "MPN": "MPN2", "Layer": "Bottom", "X": 5, "Y": 6, "Rotation": 0},
        ],
    )
    path = tmp_path / "fixed.csv"
    ExportService.export_pickplace_fixed(_records(), data, str(path))
    rows = _read_csv(path)
    assert len(rows) == 2
    assert rows[0] == ["C1", "MPN1", "3.0", "4.0", "90"]  # Layer removed, X/Y overridden
    assert rows[1] == ["C2", "MPN2", "5", "6", "0"]
    assert not any("Layer" in row for row in rows)


def test_export_pickplace_fixed_ic_flag_keeps_raw_value(tmp_path):
    """IC convention only affects on-screen direction; exports stay raw."""
    data = PickPlaceData(
        headers=["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
        components=[
            PickPlaceComponent(designator="C1", mpn="MPN1", layer="Top", x=1, y=2, rotation=0),
        ],
        raw_data=[
            {"Designator": "C1", "MPN": "MPN1", "Layer": "Top", "X": 1, "Y": 2, "Rotation": 0},
        ],
    )
    records = _records()[:1]
    assert records[0].designator == "C1"
    records[0].is_ic_rotation = True
    path = tmp_path / "fixed_ic.csv"
    ExportService.export_pickplace_fixed(records, data, str(path))
    rows = _read_csv(path)
    assert rows[0] == ["C1", "MPN1", "3.0", "4.0", "90"]  # raw 90, not +45


def test_export_pickplace_fixed_skips_inactive(tmp_path):
    data = PickPlaceData(
        headers=["Designator", "X", "Y"],
        components=[
            PickPlaceComponent(designator="C1", x=1, y=2),
            PickPlaceComponent(designator="DELETED", x=3, y=4),
        ],
        raw_data=[
            {"Designator": "C1", "X": 1, "Y": 2},
            {"Designator": "DELETED", "X": 3, "Y": 4},
        ],
    )
    records = [
        ReviewRecord(designator="C1", old_x=1, old_y=2, status="OK",
                     new_x=1, new_y=2, new_rotation=0),
    ]
    path = tmp_path / "fixed2.csv"
    ExportService.export_pickplace_fixed(records, data, str(path))
    rows = _read_csv(path)
    assert len(rows) == 1  # only C1 row
    assert rows[0][0] == "C1"


def _fixed_data():
    return PickPlaceData(
        headers=["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
        components=[
            PickPlaceComponent(designator="C1", mpn="MPN1", layer="Top", x=1, y=2, rotation=0),
        ],
        raw_data=[
            {"Designator": "C1", "MPN": "MPN1", "Layer": "Top", "X": 1, "Y": 2, "Rotation": 0},
        ],
    )


def test_export_pickplace_fixed_with_pcb_info(tmp_path):
    pcb = PcbInfo(
        board_width=100.5, board_height=80.25, working_area_width=50,
        position_working=12.5, x_boc1=10, y_boc1=20,
        x_boc2=30, y_boc2=40, x_boc3=50, y_boc3=60, thickness=1.6,
    )
    path = tmp_path / "fixed_pcb.csv"
    ExportService.export_pickplace_fixed(_records(), _fixed_data(), str(path), pcb)
    rows = _read_csv(path)
    assert rows[0] == ["100.5", "80.25", "50", "12.5", "10", "20", "30", "40", "50", "60", "1.6"]
    assert rows[1][0] == "C1"  # no header, data follows pcb_info row


def test_export_pickplace_fixed_without_pcb_info_keeps_layout(tmp_path):
    path = tmp_path / "fixed_nopcb.csv"
    ExportService.export_pickplace_fixed(_records(), _fixed_data(), str(path))
    rows = _read_csv(path)
    assert rows[0] == ["C1", "MPN1", "3.0", "4.0", "90"]  # no header, data on first row


def _read_csv(path) -> list:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))

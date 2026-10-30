import csv
import os

import openpyxl

from models.bom import BomRow
from models.pcb_info import PcbInfo
from models.pickplace import PickPlaceData, PickPlaceComponent
from models.review import ReviewRecord
from services.export_service import ExportService


def _xl_text(value: str) -> str:
    if not value:
        return ""
    return '="' + value.replace('"', '""') + '"'


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
    assert ws.cell(row=1, column=2).value == "MPN"
    assert ws.cell(row=2, column=1).value == "C1"
    assert ws.cell(row=2, column=2).value == "MPN1"
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
    assert rows[0] == ["C1", _xl_text("MPN1"), "3.0", "4.0", "90"]  # Layer removed, X/Y overridden
    assert rows[1] == ["C2", _xl_text("MPN2"), "5", "6", "0"]
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
    assert rows[0] == ["C1", _xl_text("MPN1"), "3.0", "4.0", "90"]  # raw 90, not +45


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
    assert rows[0] == ["C1", "", "1", "2"]  # MPN added after Designator


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
    assert rows[1][1] == _xl_text("MPN1")


def test_export_pickplace_fixed_without_pcb_info_keeps_layout(tmp_path):
    path = tmp_path / "fixed_nopcb.csv"
    ExportService.export_pickplace_fixed(_records(), _fixed_data(), str(path))
    rows = _read_csv(path)
    assert rows[0] == ["C1", _xl_text("MPN1"), "3.0", "4.0", "90"]  # no header, data on first row


def test_export_pickplace_fixed_adds_mpn_when_source_lacks_it(tmp_path):
    data = PickPlaceData(
        headers=["Designator", "X", "Y", "Rotation"],
        components=[
            PickPlaceComponent(designator="C1", x=1, y=2, rotation=0),
        ],
        raw_data=[
            {"Designator": "C1", "X": 1, "Y": 2, "Rotation": 0},
        ],
        column_mapping={
            "designator": "Designator", "x": "X", "y": "Y",
            "rotation": "Rotation",
        },
    )
    records = [
        ReviewRecord(designator="C1", mpn="MPN-FROM-BOM", layer="Top",
                     old_x=1, old_y=2, old_rotation=0, status="OK"),
    ]
    path = tmp_path / "fixed_add_mpn.csv"
    ExportService.export_pickplace_fixed(records, data, str(path))
    rows = _read_csv(path)
    assert rows == [["C1", _xl_text("MPN-FROM-BOM"), "1", "2", "0"]]


def test_export_pickplace_fixed_uses_current_record_mpn(tmp_path):
    data = _fixed_data()
    data.raw_data[0]["MPN"] = "STALE-MPN"
    records = _records()[:1]
    records[0].mpn = "CURRENT-MPN"
    path = tmp_path / "fixed_current_mpn.csv"
    ExportService.export_pickplace_fixed(records, data, str(path))
    rows = _read_csv(path)
    assert rows[0] == ["C1", _xl_text("CURRENT-MPN"), "3.0", "4.0", "90"]


def test_export_pickplace_fixed_mpn_keeps_leading_zeros_for_excel(tmp_path):
    records = _records()[:1]
    records[0].mpn = "001234"
    path = tmp_path / "fixed_leading_zero.csv"
    ExportService.export_pickplace_fixed(records, _fixed_data(), str(path))
    rows = _read_csv(path)
    assert rows[0][1] == '="001234"'


def test_export_pickplace_fixed_mpn_escapes_quotes_for_excel(tmp_path):
    records = _records()[:1]
    records[0].mpn = 'A"B'
    path = tmp_path / "fixed_quoted_mpn.csv"
    ExportService.export_pickplace_fixed(records, _fixed_data(), str(path))
    rows = _read_csv(path)
    assert rows[0][1] == '="A""B"'


def test_export_pickplace_fixed_keeps_mapped_mpn_column_name(tmp_path):
    data = PickPlaceData(
        headers=["Designator", "Part Number", "X", "Y", "Rotation"],
        components=[
            PickPlaceComponent(designator="C1", mpn="OLD", x=1, y=2, rotation=0),
        ],
        raw_data=[
            {"Designator": "C1", "Part Number": "OLD", "X": 1, "Y": 2,
             "Rotation": 0},
        ],
        column_mapping={
            "designator": "Designator", "mpn": "Part Number",
            "x": "X", "y": "Y", "rotation": "Rotation",
        },
    )
    records = [
        ReviewRecord(designator="C1", mpn="NEW", layer="Top",
                     old_x=1, old_y=2, old_rotation=0, status="OK"),
    ]
    path = tmp_path / "fixed_mapped_mpn.csv"
    ExportService.export_pickplace_fixed(records, data, str(path))
    rows = _read_csv(path)
    assert rows == [["C1", _xl_text("NEW"), "1", "2", "0"]]


def test_export_pickplace_fixed_mapped_designator_and_missing_mpn(tmp_path):
    data = PickPlaceData(
        headers=["Ref", "Xpos", "Ypos", "Angle"],
        components=[
            PickPlaceComponent(designator="C1", x=1, y=2, rotation=0),
        ],
        raw_data=[
            {"Ref": "C1", "Xpos": 1, "Ypos": 2, "Angle": 0},
        ],
        column_mapping={
            "designator": "Ref", "x": "Xpos", "y": "Ypos",
            "rotation": "Angle",
        },
    )
    records = [
        ReviewRecord(designator="C1", mpn="MPN-FROM-BOM", layer="Top",
                     old_x=1, old_y=2, old_rotation=0, status="Edited",
                     new_x=7, new_y=8, new_rotation=90),
    ]
    path = tmp_path / "fixed_mapped_designator.csv"
    ExportService.export_pickplace_fixed(records, data, str(path))
    rows = _read_csv(path)
    assert rows == [["C1", _xl_text("MPN-FROM-BOM"), "7", "8", "90"]]


def _layered_data():
    return PickPlaceData(
        headers=["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
        components=[
            PickPlaceComponent(designator="C1", mpn="M1", layer="Top",
                               x=1, y=2, rotation=0),
            PickPlaceComponent(designator="C2", mpn="M2", layer="Bottom",
                               x=3, y=4, rotation=90),
            PickPlaceComponent(designator="C3", mpn="M3", layer="",
                               x=5, y=6, rotation=0),
            PickPlaceComponent(designator="C4", mpn="M4", layer="Top",
                               x=7, y=8, rotation=0),
        ],
        raw_data=[
            {"Designator": "C1", "MPN": "M1", "Layer": "Top", "X": 1, "Y": 2, "Rotation": 0},
            {"Designator": "C2", "MPN": "M2", "Layer": "Bottom", "X": 3, "Y": 4, "Rotation": 90},
            {"Designator": "C3", "MPN": "M3", "Layer": "", "X": 5, "Y": 6, "Rotation": 0},
            {"Designator": "C4", "MPN": "M4", "Layer": "Top", "X": 7, "Y": 8, "Rotation": 0},
        ],
    )


def _layered_records():
    return [
        ReviewRecord(designator="C1", mpn="M1", layer="Top",
                     old_x=1, old_y=2, old_rotation=0, status="OK",
                     new_x=1, new_y=2, new_rotation=0),
        ReviewRecord(designator="C2", mpn="M2", layer="Bottom",
                     old_x=3, old_y=4, old_rotation=90, status="Pending"),
        ReviewRecord(designator="C3", mpn="M3", layer="",
                     old_x=5, old_y=6, old_rotation=0, status="Pending"),
    ]


def test_export_fixed_by_layer_splits_top_bottom(tmp_path):
    data = _layered_data()
    top_path = tmp_path / "top.csv"
    bottom_path = tmp_path / "bottom.csv"
    n_top = ExportService.export_pickplace_fixed_by_layer(
        _layered_records(), data, str(top_path), "top")
    n_bottom = ExportService.export_pickplace_fixed_by_layer(
        _layered_records(), data, str(bottom_path), "bottom")
    assert n_top == 2  # C1 + C3 (empty layer counts as Top)
    top_rows = _read_csv(top_path)
    bottom_rows = _read_csv(bottom_path)
    assert [r[0] for r in top_rows] == ["C1", "C3"]
    assert [r[0] for r in bottom_rows] == ["C2"]
    # same fixed format: layer column dropped, edited values used
    assert top_rows[0] == ["C1", _xl_text("M1"), "1", "2", "0"]
    assert n_bottom == 1


def test_export_fixed_by_layer_empty_writes_nothing(tmp_path):
    data = _layered_data()
    path = tmp_path / "only_top_bottom.csv"
    n = ExportService.export_pickplace_fixed_by_layer(
        [r for r in _layered_records() if r.layer != "Bottom"],
        data, str(path), "bottom")
    assert n == 0
    assert not os.path.exists(str(path))


def test_export_pickplace_fixed_panelized_drops_block_column(tmp_path):
    """Panelized records (blocks 0+1) export without any Panel_Instance column."""
    data = PickPlaceData(
        headers=["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
        components=[
            PickPlaceComponent(designator="C1", mpn="MPN1", layer="Top", x=1, y=2, rotation=0),
        ],
        raw_data=[
            {"Designator": "C1", "MPN": "MPN1", "Layer": "Top", "X": 1, "Y": 2, "Rotation": 0},
        ],
    )
    records = [
        ReviewRecord(designator="C1", old_x=1, old_y=2, old_rotation=0,
                     status="OK", new_x=1, new_y=2, new_rotation=0, block=0),
        ReviewRecord(designator="C1_2", base_designator="C1",
                     old_x=11, old_y=2, old_rotation=0,
                     status="OK", new_x=11, new_y=2, new_rotation=0, block=1),
    ]
    path = tmp_path / "fixed_panel.csv"
    ExportService.export_pickplace_fixed(records, data, str(path))
    rows = _read_csv(path)
    assert len(rows) == 2  # both blocks still written
    assert rows[0][0] == "C1"
    assert rows[1][0] == "C1_2"
    assert all(len(row) == 5 for row in rows)  # no extra block column
    assert not any("Panel_Instance" in (cell or "") for row in rows for cell in row)


def test_export_pickplace_fixed_source_block_column_dropped(tmp_path):
    """A source file whose Panel_Instance column is all 1s exports clean."""
    data = PickPlaceData(
        headers=["Designator", "MPN", "Layer", "X", "Y", "Rotation", "Panel_Instance"],
        components=[
            PickPlaceComponent(designator="C1", mpn="MPN1", layer="Top", x=1, y=2,
                               rotation=0, panel_instance=1),
        ],
        raw_data=[
            {"Designator": "C1", "MPN": "MPN1", "Layer": "Top", "X": 1, "Y": 2,
             "Rotation": 0, "Panel_Instance": 1},
        ],
    )
    records = [
        ReviewRecord(designator="C1", mpn="MPN1", old_x=1, old_y=2,
                     old_rotation=0, status="OK",
                     new_x=1, new_y=2, new_rotation=0),
    ]
    path = tmp_path / "fixed_srcblock.csv"
    ExportService.export_pickplace_fixed(records, data, str(path))
    rows = _read_csv(path)
    assert rows[0] == ["C1", _xl_text("MPN1"), "1", "2", "0"]
    assert not any("Panel_Instance" in (cell or "") for row in rows for cell in row)


def _read_csv(path) -> list:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def _bom_rows():
    return [
        BomRow(stt=1, designator_display="C1,C2,C3", designators=["C1", "C2", "C3"],
               mpn="M-A", description="Cap", quantity=3, note=""),
        BomRow(stt=2, designator_display="R9", designators=["R9"],
               mpn="M-B", description="Res", quantity=1, note="n"),
    ]


def test_export_bom_fixed_styled_xlsx(tmp_path):
    path = tmp_path / "bom_fixed.xlsx"
    ExportService.export_bom_fixed(
        _bom_rows(), str(path), {2: ["R9"]}, {"C2", "R9"}, "BOM REPORT")
    wb = openpyxl.load_workbook(str(path), rich_text=True)
    ws = wb.active
    # merged red title, size 24
    assert ws.merged_cells == "A1:G1"
    title = ws.cell(row=1, column=1)
    assert title.value == "BOM REPORT"
    assert title.font.size == 24
    assert title.font.color.rgb == "00FF0000"
    assert title.font.name == "Times New Roman"
    # gray header, Times 13
    header = ws.cell(row=2, column=1)
    assert header.value == "STT"
    assert ws.cell(row=2, column=3).value == "MPN"
    assert header.fill.start_color.rgb == "00D9D9D9"
    assert header.font.size == 13
    assert header.font.name == "Times New Roman"
    # body: Times 13, thin borders everywhere
    body = ws.cell(row=3, column=3)
    assert body.value == "M-A"
    assert body.font.size == 13
    assert body.font.name == "Times New Roman"
    assert body.border.left.style == "thin"
    assert body.border.bottom.style == "thin"
    assert ws.cell(row=4, column=7).value == "R9"  # missing column
    # single Bottom designator: plain value + red cell font
    assert ws.cell(row=4, column=2).value == "R9"
    assert ws.cell(row=4, column=2).font.color.rgb == "00FF0000"
    # multi-name cell keeps rich text: only C2 red, C1/C3 black
    from openpyxl.cell.rich_text import CellRichText
    des3 = ws.cell(row=3, column=2).value
    assert isinstance(des3, CellRichText)
    red_texts = []
    for b in des3:
        if isinstance(b, str):
            continue
        color = getattr(getattr(b, "font", None), "color", None)
        if getattr(color, "rgb", "") == "00FF0000":
            red_texts.append(b.text)
    assert red_texts == ["C2"]
    wb.close()


def test_export_bom_fixed_empty_writes_title_and_header(tmp_path):
    path = tmp_path / "bom_empty.xlsx"
    ExportService.export_bom_fixed([], str(path), title="T")
    wb = openpyxl.load_workbook(str(path))
    ws = wb.active
    assert ws.cell(row=1, column=1).value == "T"
    assert ws.cell(row=2, column=1).value == "STT"
    assert ws.max_row == 2
    wb.close()

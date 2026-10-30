import openpyxl

from models.bom import BomRow
from services.bom_compare import compare, is_bottom_layer
from services.bom_reader import (
    clean_designators,
    guess_bom_mapping,
    BomReader,
)


def test_clean_range():
    display, expanded = clean_designators("C1-C4")
    assert expanded == ["C1", "C2", "C3", "C4"]
    assert display == "C1,C2,C3,C4"


def test_clean_separators_and_dots():
    _, expanded = clean_designators("C1; C2 /C3,, C4.")
    assert expanded == ["C1", "C2", "C3", "C4"]


def test_clean_junk_parens():
    display, expanded = clean_designators("C1 (spare), C2")
    assert expanded == ["C1", "C2"]
    assert display == "C1,C2"


def test_clean_reverse_and_case():
    _, expanded = clean_designators("C4-C1")
    assert expanded == ["C1", "C2", "C3", "C4"]
    _, expanded = clean_designators("c1-c2")
    assert [d.upper() for d in expanded] == ["C1", "C2"]


def test_clean_padding_and_prefix():
    _, expanded = clean_designators("C01-C03")
    assert expanded == ["C01", "C02", "C03"]
    _, expanded = clean_designators("LED1-LED3")
    assert expanded == ["LED1", "LED2", "LED3"]


def test_clean_huge_and_foreign_range_kept():
    display, expanded = clean_designators("C1-C9999")
    assert expanded == ["C1-C9999"]
    display, expanded = clean_designators("C1-X5")
    assert expanded == ["C1-X5"]


def test_clean_dedup_and_empty():
    assert clean_designators("") == ("", [])
    assert clean_designators(None) == ("", [])
    _, expanded = clean_designators("C1,c1,C2")
    assert expanded == ["C1", "C2"]


def test_guess_bom_mapping_aliases():
    headers = ["RefDes List", "Part Number", "Desc", "Q'TY", "Ghi chú"]
    mapping = guess_bom_mapping(headers)
    assert mapping["designator"] == "RefDes List"
    assert mapping["mpn"] == "Part Number"
    assert mapping["description"] == "Desc"
    assert mapping["quantity"] == "Q'TY"
    assert mapping["note"] == "Ghi chú"


def _write_bom(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Ref", "MPN", "Desc", "Qty", "Note"])
    for r in rows:
        ws.append(r)
    wb.save(str(path))
    wb.close()


def test_bom_reader_grouped(tmp_path):
    path = tmp_path / "bom.xlsx"
    _write_bom(path, [
        ["C1-C3", "MPN-A", "Cap", 3, ""],
        ["R1; R2", "MPN-B", "Res", 2, "n1"],
        ["", "MPN-X", "X", 1, ""],
    ])
    mapping = {"designator": "Ref", "mpn": "MPN", "description": "Desc",
               "quantity": "Qty", "note": "Note"}
    rows = BomReader.read_with_mapping(str(path), mapping)
    assert len(rows) == 2
    assert rows[0].designators == ["C1", "C2", "C3"]
    assert rows[0].designator_display == "C1,C2,C3"
    assert rows[0].quantity == 3
    assert rows[1].note == "n1"
    assert rows[1].stt == 2


def test_compare_missing_extra_mismatch_fillable():
    bom = [
        BomRow(stt=1, designator_display="C1,C2", designators=["C1", "C2"],
               mpn="M-A", quantity=2),
        BomRow(stt=2, designator_display="R9", designators=["R9"],
               mpn="M-B", quantity=1),
        BomRow(stt=3, designator_display="U1", designators=["U1"],
               mpn="", quantity=1),
    ]
    pp = [("C1", "", "Top"), ("C2", "M-X", "Top"),
          ("U1", "", "Bottom"), ("D9", "M-D", "Top")]
    diff = compare(bom, pp)
    assert [r.stt for r, _ in diff.missing] == [2]
    assert diff.missing[0][1] == ["R9"]
    assert diff.extra == ["D9"]
    assert diff.mpn_mismatch == [("C2", "M-X", "M-A", 1)]
    assert ("C1", "M-A", 1) in diff.mpn_fillable
    assert ("U1", "", 1) not in diff.mpn_fillable  # BOM MPN empty: nothing to fill


def test_compare_conflicts_first_wins():
    bom = [
        BomRow(stt=1, designators=["C1"], mpn="M-A"),
        BomRow(stt=2, designators=["C1"], mpn="M-B"),
    ]
    diff = compare(bom, [("C1", "", "Top")])
    assert diff.bom_map["C1"] == ("M-A", 1)
    assert len(diff.conflicts) == 1
    assert diff.mpn_fillable == [("C1", "M-A", 1)]


def test_compare_qty_note():
    bom = [BomRow(stt=1, designators=["C1", "C2"], mpn="M-A", quantity=5)]
    diff = compare(bom, [("C1", "M-A", "Top"), ("C2", "M-A", "Top")])
    assert len(diff.qty_notes) == 1


def test_is_bottom_layer():
    for v in ["Bot", "BOTTOM", "BottomLayer", "b", "bottom layer"]:
        assert is_bottom_layer(v)
    assert not is_bottom_layer("Top")
    assert not is_bottom_layer("")
    assert not is_bottom_layer(None)


def test_bom_reader_reports_progress(tmp_path):
    path = tmp_path / "progress_bom.xlsx"
    _write_bom(path, [
        ["C1", "M1", "Cap", 1, ""],
        ["C2", "M2", "Cap", 1, ""],
        ["C3", "M3", "Cap", 1, ""],
    ])
    mapping = {"designator": "Ref", "mpn": "MPN", "description": "Desc",
               "quantity": "Qty", "note": "Note"}
    calls = []
    rows = BomReader.read_with_mapping(
        str(path), mapping,
        progress=lambda done, total: calls.append((done, total)),
    )
    assert len(rows) == 3
    assert calls[-1] == (3, 3)
    assert all(done <= total for done, total in calls)

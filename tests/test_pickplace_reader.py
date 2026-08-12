import openpyxl
import pytest

from services.pickplace_reader import (
    PickPlaceReader,
    guess_mapping,
    STANDARD_MAPPING,
)


def _make_xlsx(path, headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)
    wb.close()


def test_read_valid_file(tmp_path):
    path = tmp_path / "pickplace.xlsx"
    _make_xlsx(
        path,
        ["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
        [["C1", "MPN1", "Top", 1.5, 2.5, 90], ["C2", "MPN2", "Bottom", -3, 0, 0]],
    )
    data = PickPlaceReader.read(str(path))
    assert data.count == 2
    assert data.components[0].designator == "C1"
    assert data.components[0].x == 1.5
    assert data.components[0].rotation == 90
    assert data.components[1].y == 0


def test_read_skips_empty_rows(tmp_path):
    path = tmp_path / "pickplace.xlsx"
    _make_xlsx(
        path,
        ["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
        [["C1", "MPN1", "Top", 1, 2, 0], [None, None, None, None, None, None]],
    )
    data = PickPlaceReader.read(str(path))
    assert data.count == 1


def test_read_missing_column(tmp_path):
    path = tmp_path / "bad.xlsx"
    _make_xlsx(
        path,
        ["Designator", "MPN", "Layer", "X", "Y"],
        [["C1", "MPN1", "Top", 1, 2]],
    )
    with pytest.raises(ValueError):
        PickPlaceReader.read(str(path))


def test_read_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        PickPlaceReader.read(str(tmp_path / "nope.xlsx"))


def test_read_with_custom_mapping(tmp_path):
    path = tmp_path / "custom.xlsx"
    _make_xlsx(
        path,
        ["Ref", "Part Number", "Side", "Xpos", "Ypos", "Angle"],
        [["C1", "MPN1", "Top", 1.5, 2.5, 90], ["C2", "MPN2", "Bottom", -3, 0, 0]],
    )
    mapping = {
        "designator": "Ref",
        "mpn": "Part Number",
        "layer": "Side",
        "x": "Xpos",
        "y": "Ypos",
        "rotation": "Angle",
    }
    data = PickPlaceReader.read_with_mapping(str(path), mapping)
    assert data.count == 2
    assert data.components[0].designator == "C1"
    assert data.components[0].x == 1.5
    assert data.components[1].layer == "Bottom"
    assert data.column_mapping == mapping
    assert data.headers == ["Ref", "Part Number", "Side", "Xpos", "Ypos", "Angle"]


def test_read_with_partial_mapping_keeps_raw_headers(tmp_path):
    path = tmp_path / "partial.xlsx"
    _make_xlsx(
        path,
        ["Ref", "Comment", "Xpos", "Ypos"],
        [["C1", "10K", 1.0, 2.0]],
    )
    mapping = {"designator": "Ref", "x": "Xpos", "y": "Ypos"}
    data = PickPlaceReader.read_with_mapping(
        str(path), mapping, required=["designator", "x", "y"]
    )
    assert data.count == 1
    comp = data.components[0]
    assert comp.designator == "C1"
    assert comp.x == 1.0
    assert comp.y == 2.0
    assert comp.mpn == ""
    assert data.raw_data[0]["Comment"] == "10K"


def test_read_with_mapping_missing_required(tmp_path):
    path = tmp_path / "missing_required.xlsx"
    _make_xlsx(
        path,
        ["Ref", "Side", "Xpos", "Ypos"],
        [["C1", "Top", 1.0, 2.0]],
    )
    mapping = {"designator": "Ref", "layer": "Side", "x": "Xpos"}
    with pytest.raises(ValueError):
        PickPlaceReader.read_with_mapping(
            str(path), mapping, required=["designator", "x", "y"]
        )


def test_read_with_mapping_bad_header_name(tmp_path):
    path = tmp_path / "bad_header.xlsx"
    _make_xlsx(
        path,
        ["Ref", "Xpos", "Ypos"],
        [["C1", 1.0, 2.0]],
    )
    mapping = {"designator": "Ref", "x": "Missing X", "y": "Ypos"}
    with pytest.raises(ValueError):
        PickPlaceReader.read_with_mapping(
            str(path), mapping, required=["designator", "x", "y"]
        )


def test_guess_mapping_standard():
    mapping = guess_mapping(["Designator", "MPN", "Layer", "X", "Y", "Rotation"])
    assert mapping == STANDARD_MAPPING


def test_guess_mapping_aliases():
    mapping = guess_mapping(
        ["Ref Des", "Part No", "Side", "Center X", "Center Y", "Theta"]
    )
    assert mapping["designator"] == "Ref Des"
    assert mapping["mpn"] == "Part No"
    assert mapping["layer"] == "Side"
    assert mapping["x"] == "Center X"
    assert mapping["y"] == "Center Y"
    assert mapping["rotation"] == "Theta"


def test_guess_mapping_partial():
    mapping = guess_mapping(["Ref", "X (mm)", "Y(mm)"])
    assert mapping == {"designator": "Ref", "x": "X (mm)", "y": "Y(mm)"}


def test_guess_mapping_empty():
    assert guess_mapping([]) == {}


def test_read_headers(tmp_path):
    path = tmp_path / "headers.xlsx"
    _make_xlsx(
        path,
        ["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
        [["C1", "MPN1", "Top", 1, 2, 0]],
    )
    assert PickPlaceReader.read_headers(str(path)) == [
        "Designator", "MPN", "Layer", "X", "Y", "Rotation",
    ]


def test_read_headers_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        PickPlaceReader.read_headers(str(tmp_path / "nope.xlsx"))

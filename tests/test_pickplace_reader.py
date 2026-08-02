import openpyxl
import pytest

from services.pickplace_reader import PickPlaceReader


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

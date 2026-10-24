import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from models.review import ReviewRecord
from ui.table_widget import TableWidget, _COLUMNS


def _records():
    return [
        ReviewRecord(designator="C1", mpn="", layer="Top",
                     old_x=1, old_y=2, old_rotation=0, status="Pending"),
        ReviewRecord(designator="C2", mpn="M-X", layer="Bottom",
                     old_x=3, old_y=4, old_rotation=0, status="OK"),
        ReviewRecord(designator="D9", mpn="M-D", layer="Top",
                     old_x=5, old_y=6, old_rotation=0, status="Pending"),
    ]


def _table(records):
    app = QApplication.instance() or QApplication([])
    t = TableWidget()
    t.set_records(records)
    return t


def test_no_missing_mpn_column():
    t = _table(_records())
    assert t._table.columnCount() == 13
    assert "Missing MPN" not in list(_COLUMNS)


def test_extra_rows_tinted_and_filterable():
    t = _table(_records())
    t.set_bom_overlay({"D9"}, {})
    bg = t._table.item(2, 0).background().color()
    assert (bg.red(), bg.green(), bg.blue()) == (0xFE, 0xF3, 0xC7)
    bg0 = t._table.item(0, 0).background()
    assert bg0 is not None
    # status filter "Extra" shows only D9
    idx = t._status_filter.findData("Extra")
    assert idx >= 0
    t._status_filter.setCurrentIndex(idx)
    assert t._filtered == [2]


def test_mpn_mismatch_red_with_tooltip():
    t = _table(_records())
    t.set_bom_overlay(set(), {"C2": ("M-X", "M-A", 1)})
    mpn_item = t._table.item(1, 4)
    fg = mpn_item.foreground().color()
    assert (fg.red(), fg.green(), fg.blue()) == (0xDC, 0x26, 0x26)
    assert "1" in mpn_item.toolTip() and "M-A" in mpn_item.toolTip()
    # non-mismatched MPN cell not red
    fg0 = t._table.item(0, 4).foreground()
    assert fg0 is not None


def test_clear_bom_overlay_resets():
    t = _table(_records())
    t.set_bom_overlay({"D9"}, {"C2": ("M-X", "M-A", 1)})
    t.clear_bom_overlay()
    assert t._extra_set == set()
    assert t._mpn_mismatch == {}

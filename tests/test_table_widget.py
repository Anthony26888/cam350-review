import os
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from models.review import ReviewRecord
from ui.i18n import tr
from ui.table_widget import (
    TableWidget, _CHECK_COLUMN, _check_icon,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _records():
    return [
        ReviewRecord(designator="C1", mpn="MPN1", layer="Top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="MPN2", layer="Bottom",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
        ReviewRecord(designator="R1", mpn="MPN3", layer="Top",
                     old_x=5.0, old_y=6.0, old_rotation=0.0),
    ]


@pytest.fixture()
def table(app):
    return TableWidget()


def test_layer_filter_populates_unique(table):
    table.set_records(_records())
    items = [table._layer_filter.itemData(i) for i in range(table._layer_filter.count())]
    assert items[0] is None  # All
    assert set(items[1:]) == {"Top", "Bottom"}


def test_layer_filter_filters_rows(table):
    table.set_records(_records())
    counts = []
    table.filter_changed.connect(lambda f, t: counts.append((f, t)))
    idx = table._layer_filter.findData("Top")
    table._layer_filter.setCurrentIndex(idx)
    assert table._table.rowCount() == 2
    assert counts[-1] == (2, 3)


def test_layer_filter_all_shows_all(table):
    table.set_records(_records())
    table._layer_filter.setCurrentIndex(0)
    assert table._table.rowCount() == 3


def test_layer_filter_case_insensitive(table):
    table.set_records([
        ReviewRecord(designator="C1", mpn="M", layer="Top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="M", layer="bottom",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
    ])
    idx = table._layer_filter.findData("Top")
    assert idx >= 0
    table._layer_filter.setCurrentIndex(idx)
    # "bottom" record matches the "Top" filter case-insensitively only for Top;
    # the bottom record must NOT match Top
    assert table._table.rowCount() == 1


def test_layer_filter_case_insensitive_matches_variant(table):
    table.set_records([
        ReviewRecord(designator="C1", mpn="M", layer="top",
                     old_x=1.0, old_y=2.0, old_rotation=0.0),
        ReviewRecord(designator="C2", mpn="M", layer="Bottom",
                     old_x=3.0, old_y=4.0, old_rotation=0.0),
    ])
    idx = table._layer_filter.findData("top")
    assert idx >= 0
    table._layer_filter.setCurrentIndex(idx)
    assert table._table.rowCount() == 1


def test_clear_filters_resets_layer(table):
    table.set_records(_records())
    idx = table._layer_filter.findData("Top")
    table._layer_filter.setCurrentIndex(idx)
    assert table._table.rowCount() == 2
    table._clear_filters()
    assert table._layer_filter.currentData() is None
    assert table._table.rowCount() == 3


def test_layer_filter_preserved_on_set_records(table):
    table.set_records(_records())
    idx = table._layer_filter.findData("Bottom")
    table._layer_filter.setCurrentIndex(idx)
    table.set_records(_records())
    assert table._layer_filter.currentData() == "Bottom"
    assert table._table.rowCount() == 1


def test_layer_filter_drops_when_layer_absent(table):
    table.set_records(_records())
    idx = table._layer_filter.findData("Bottom")
    table._layer_filter.setCurrentIndex(idx)
    table.set_records([r for r in _records() if r.layer == "Top"])
    assert table._layer_filter.currentData() is None
    assert table._table.rowCount() == 2


def _checked_records():
    recs = _records()
    recs[0].checked = True
    recs[2].checked = True
    return recs


def test_table_has_checked_column(table):
    table.set_records(_records())
    assert table._table.columnCount() == 13
    header = table._table.horizontalHeaderItem(_CHECK_COLUMN)
    assert header is not None
    assert header.text() == "Checked"


def test_checked_filter_checked_only(table):
    table.set_records(_checked_records())
    idx = table._checked_filter.findData("Checked")
    table._checked_filter.setCurrentIndex(idx)
    assert table._table.rowCount() == 2


def test_checked_filter_unchecked_only(table):
    table.set_records(_checked_records())
    idx = table._checked_filter.findData("Unchecked")
    table._checked_filter.setCurrentIndex(idx)
    assert table._table.rowCount() == 1
    item = table._table.item(0, _CHECK_COLUMN)
    assert item is not None
    assert item.icon().cacheKey() == _check_icon(False).cacheKey()


def test_checked_icon_reflects_state(table):
    table.set_records(_checked_records())
    checked_item = table._table.item(0, _CHECK_COLUMN)
    unchecked_item = table._table.item(1, _CHECK_COLUMN)
    assert checked_item.icon().cacheKey() == _check_icon(True).cacheKey()
    assert unchecked_item.icon().cacheKey() == _check_icon(False).cacheKey()


def test_update_record_checked_updates_icon(table):
    table.set_records(_records())
    table._records[0].checked = True
    table.update_record_checked(0)
    item = table._table.item(0, _CHECK_COLUMN)
    assert item.icon().cacheKey() == _check_icon(True).cacheKey()


def test_update_record_checked_with_filter_reapplies(table):
    table.set_records(_records())
    idx = table._checked_filter.findData("Checked")
    table._checked_filter.setCurrentIndex(idx)
    assert table._table.rowCount() == 0
    table._records[1].checked = True
    table.update_record_checked(1)
    assert table._table.rowCount() == 1
    assert table._table.item(0, _CHECK_COLUMN).icon().cacheKey() == _check_icon(True).cacheKey()


def test_clear_filters_resets_checked_filter(table):
    table.set_records(_records())
    idx = table._checked_filter.findData("Unchecked")
    table._checked_filter.setCurrentIndex(idx)
    assert table._table.rowCount() == 3
    table._clear_filters()
    assert table._checked_filter.currentData() == "All"
    assert table._table.rowCount() == 3


def test_flags_column_constants_and_render(table):
    from ui.table_widget import (
        _COLUMNS, _FLAGS_COLUMN, _STATUS_COLUMN, _REMARK_COLUMN,
    )
    assert _COLUMNS[9] == "Flags"
    assert _STATUS_COLUMN == 10
    assert _REMARK_COLUMN == 12

    recs = _records()
    recs[1].prescreen_flags = ["ROT", "PAD"]
    table.set_records(recs)
    item = table._table.item(1, _FLAGS_COLUMN)
    assert item.text() == "ROT·PAD"
    assert item.toolTip()
    empty = table._table.item(0, _FLAGS_COLUMN)
    assert empty.text() == ""
    assert not empty.toolTip()
    assert tr("Status") == table._table.horizontalHeaderItem(_STATUS_COLUMN).text()


def test_update_all_rows_refreshes_flags(table):
    from ui.table_widget import _FLAGS_COLUMN
    recs = _records()
    table.set_records(recs)
    assert table._table.item(0, _FLAGS_COLUMN).text() == ""
    recs[0].prescreen_flags = ["OUT"]
    table.update_all_rows()
    assert table._table.item(0, _FLAGS_COLUMN).text() == "OUT"


def test_update_all_rows_restores_header_mode(table):
    from PySide6.QtWidgets import QHeaderView
    recs = _records()
    table.set_records(recs)
    header = table._table.horizontalHeader()
    original = header.sectionResizeMode(0)

    for r in recs:
        r.prescreen_flags = ["ROT"]
    table.update_all_rows()
    assert header.sectionResizeMode(0) == original


def test_update_all_rows_restores_mode_on_error(table, monkeypatch):
    recs = _records()
    table.set_records(recs)
    header = table._table.horizontalHeader()
    original = header.sectionResizeMode(0)

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(table, "_set_row_values", boom)
    with pytest.raises(RuntimeError):
        table.update_all_rows()
    assert header.sectionResizeMode(0) == original


def test_refresh_table_restores_header_mode(table):
    recs = _records()
    header = table._table.horizontalHeader()
    original = header.sectionResizeMode(0)
    table.set_records(recs)  # triggers _refresh_table
    assert header.sectionResizeMode(0) == original
    assert table._table.rowCount() == 3


def test_context_menu_emits_dismiss_signal(app, monkeypatch):
    from PySide6.QtCore import QPoint
    import ui.table_widget as tw

    class _FakeMenu:
        def __init__(self, parent=None):
            self.actions = []

        def addAction(self, text):
            act = types.SimpleNamespace(text=text)
            self.actions.append(act)
            return act

        def exec(self, pos):
            return self.actions[0]

    monkeypatch.setattr(tw, "QMenu", _FakeMenu)

    recs = _records()
    recs[2].prescreen_flags = ["DUP"]
    t = TableWidget()
    t.set_records(recs)
    received = []
    t.flag_dismiss_requested.connect(received.append)
    t._on_context_menu(QPoint(5, 5))
    # row 0 has no flags -> nothing emitted yet
    assert received == []
    t._on_context_menu(QPoint(5, 5))  # same row again; still no flags
    t._records[0].prescreen_flags = ["ROT"]
    t.update_all_rows()
    t._on_context_menu(QPoint(5, 5))
    assert received == [0]


def test_block_column_shows_value_and_color(table):
    from ui.table_widget import _BLOCK_COLUMN, _block_color
    recs = _records()
    recs.append(ReviewRecord(
        designator="C1", mpn="MPN1", layer="Top",
        old_x=100.0, old_y=2.0, old_rotation=0.0,
        block=1, block_rotation=180,
    ))
    table.set_records(recs)
    # block 0 rows show empty cell
    assert table._table.item(0, _BLOCK_COLUMN).text() == ""
    # block 1 row shows the block number with a distinct color
    item = table._table.item(3, _BLOCK_COLUMN)
    assert item.text() == "1"
    assert item.foreground().color().name() == _block_color(1).name()
    assert item.toolTip()
    assert _block_color(0) is None


def test_block_filter_reloads_and_filters(table):
    recs = _records()
    recs.append(ReviewRecord(
        designator="C1", mpn="MPN1", layer="Top",
        old_x=100.0, old_y=2.0, old_rotation=0.0, block=1,
    ))
    recs.append(ReviewRecord(
        designator="C1", mpn="MPN1", layer="Top",
        old_x=200.0, old_y=2.0, old_rotation=0.0, block=2,
    ))
    table.set_records(recs)
    assert table._table.rowCount() == 5
    idx = table._block_filter.findData(1)
    assert idx >= 0
    table._block_filter.setCurrentIndex(idx)
    assert table._table.rowCount() == 1
    assert table._table.item(0, 1).text() == "4"  # the block-1 record row
    table._clear_filters()
    assert table._block_filter.currentData() is None
    assert table._table.rowCount() == 5


def test_block_filter_preserved_on_set_records(table):
    recs = _records()
    recs.append(ReviewRecord(
        designator="C2", mpn="MPN2", layer="Bottom",
        old_x=9.0, old_y=9.0, old_rotation=0.0, block=3,
    ))
    table.set_records(recs)
    idx = table._block_filter.findData(3)
    table._block_filter.setCurrentIndex(idx)
    assert table._table.rowCount() == 1
    table.set_records(recs)
    assert table._block_filter.currentData() == 3
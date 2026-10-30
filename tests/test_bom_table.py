import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QHeaderView

from models.bom import BomRow
from ui.bom_table_widget import (
    BomTableWidget,
    BomDesignatorDelegate,
    designator_cell_html,
    _BOM_DESIGNATOR_HTML_ROLE,
    _DESIGNATOR_COLUMN,
    _DESIGNATOR_WIDTH,
    _MISSING_COLUMN,
    _MISSING_WIDTH,
)


def _rows():
    return [
        BomRow(stt=1, designator_display="C1,C2", designators=["C1", "C2"],
               mpn="M-A", description="Cap", quantity=2, note=""),
        BomRow(stt=2, designator_display="R9", designators=["R9"],
               mpn="M-B", description="Res", quantity=5, note="n"),
    ]


def _panel():
    app = QApplication.instance() or QApplication([])
    return BomTableWidget()


def test_bom_table_empty_placeholder():
    panel = _panel()
    assert panel.row_count() == 1
    assert "BOM" in panel._table.item(0, 0).text()


def test_bom_table_missing_and_red_bottom():
    panel = _panel()
    panel.set_bom_rows(_rows())
    panel.set_compare({2: ["R9"]}, {"R9"}, {2})
    assert panel.row_count() == 2
    # missing column (last)
    assert panel._table.item(0, 6).text() == ""
    assert panel._table.item(1, 6).text() == "R9"
    # whole-cell foreground no longer used; red lives in the HTML role
    html = panel._table.item(1, 1).data(_BOM_DESIGNATOR_HTML_ROLE)
    assert '<span style="color:#DC2626;">R9</span>' in html
    html0 = panel._table.item(0, 1).data(_BOM_DESIGNATOR_HTML_ROLE)
    assert "color:#DC2626" not in html0
    assert "C1" in html0 and "C2" in html0
    # qty warn background on row 2 (stt=2, qty 5 vs 1 designator)
    bg = panel._table.item(1, 4).background().color()
    assert (bg.red(), bg.green(), bg.blue()) == (0xFE, 0xF3, 0xC7)


def test_only_bottom_designator_red():
    # C1..C5 with C3 Bottom: only C3 red, the rest normal
    html = designator_cell_html(
        ["C1", "C2", "C3", "C4", "C5"], {"C3"})
    assert html.count('color:#DC2626') == 1
    assert "<span " not in html.split("C1")[0]
    assert '<span style="color:#DC2626;">C3</span>' in html
    assert html.endswith("C4, C5")
    # all Top: no red at all
    assert "color:#DC2626" not in designator_cell_html(["C1", "C2"], set())
    # all Bottom: every name red
    html_all = designator_cell_html(["C1", "C2"], {"C1", "C2"})
    assert html_all.count('color:#DC2626') == 2


def test_designator_delegate_renders_without_crash():
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QStyleOptionViewItem
    panel = _panel()
    panel.set_bom_rows(_rows())
    panel.set_compare({2: ["R9"]}, {"R9"}, {2})
    delegate = panel._table.itemDelegateForColumn(_DESIGNATOR_COLUMN)
    assert isinstance(delegate, BomDesignatorDelegate)
    index = panel._table.model().index(1, _DESIGNATOR_COLUMN)
    opt = QStyleOptionViewItem()
    opt.initFrom(panel._table)
    opt.rect = panel._table.visualRect(index)
    hint = delegate.sizeHint(opt, index)
    assert hint.height() > 0
    img = QImage(300, 60, QImage.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    delegate.paint(painter, opt, index)
    painter.end()


def test_bom_table_search_and_clear():
    panel = _panel()
    panel.set_bom_rows(_rows())
    assert panel.row_count() == 2
    panel._search.setText("R9")
    assert panel.row_count() == 1
    assert panel._table.item(0, 1).text() == "R9"
    panel.clear()
    assert panel.row_count() == 1


def test_designator_column_fixed_width():
    from PySide6.QtCore import Qt
    panel = _panel()
    header = panel._table.horizontalHeader()
    # every column user-resizable, last one absorbs leftover viewport space
    for col in range(7):
        assert header.sectionResizeMode(col) == QHeaderView.Interactive
    assert header.stretchLastSection() is True
    assert panel._table.textElideMode() == Qt.ElideNone
    # initial widths applied on first data render
    panel.set_bom_rows(_rows())
    assert panel._table.columnWidth(_DESIGNATOR_COLUMN) == _DESIGNATOR_WIDTH == 300
    assert panel._table.columnWidth(_MISSING_COLUMN) == _MISSING_WIDTH == 170
    # grouped designators still fully shown (wrapped, not clipped)
    assert panel._table.item(0, 1).text() == "C1, C2"


def test_user_widths_survive_refresh():
    panel = _panel()
    panel.set_bom_rows(_rows())
    panel._table.setColumnWidth(2, 250)
    panel._table.setColumnWidth(_DESIGNATOR_COLUMN, 320)
    panel._refresh()
    panel.set_compare({2: ["R9"]}, {"R9"}, {2})
    assert panel._table.columnWidth(2) == 250
    assert panel._table.columnWidth(_DESIGNATOR_COLUMN) == 320


def test_click_expands_row():
    panel = _panel()
    panel.set_bom_rows(_rows())
    panel.set_compare({2: ["R9"]}, {"R9"}, {2})
    # clicking a row expands it to full wrapped height (never shrinks it)
    before = panel._table.rowHeight(0)
    panel._on_cell_clicked(0, 1)
    assert panel._table.rowHeight(0) >= before
    assert panel._table.rowHeight(0) > 0


def test_refit_rows_noop_when_hidden_fits_when_shown():
    panel = _panel()
    assert not panel.isVisible()
    panel.set_bom_rows(_rows())
    panel.refit_rows()  # hidden: must not crash, heights untouched
    panel.show()
    panel.refit_rows()
    short = panel._table.rowHeight(1)
    panel._table.setColumnWidth(_DESIGNATOR_COLUMN, 60)
    panel.refit_rows()
    assert panel._table.rowHeight(0) >= short
    assert panel._table.rowHeight(0) > 0


def test_tab_change_refits_bom_table():
    import types
    from ui.main_window import MainWindow

    calls = []

    class _Tabs:
        def indexOf(self, widget):
            return 1

    h = types.SimpleNamespace()
    h._table_tabs = _Tabs()
    h._bom_table = types.SimpleNamespace(
        refit_rows=lambda: calls.append("refit"))
    MainWindow._on_table_tab_changed.__get__(h)(1)
    assert calls == ["refit"]
    MainWindow._on_table_tab_changed.__get__(h)(0)
    assert calls == ["refit"]  # other tabs untouched


def test_bom_table_combined_setter_refreshes_once():
    panel = _panel()
    calls = []
    panel._refresh = lambda: calls.append(True)
    panel.set_bom_rows(_rows(), {2: ["R9"]}, {"R9"}, {2})
    assert calls == [True]
    assert panel._missing == {2: ["R9"]}
    assert panel._bottom_keys == {"R9"}
    assert panel._qty_warn == {2}

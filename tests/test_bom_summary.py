import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from models.bom import BomRow
from services.bom_compare import summarize_bom_row


def _row():
    return BomRow(stt=3, designator_display="C1,C2,C3,C4,C5",
                  designators=["C1", "C2", "C3", "C4", "C5"],
                  mpn="M-A", quantity=5)


def test_summarize_partitions_top_bottom_missing():
    layers = {"C1": {"Top"}, "C2": {"Top"}, "C3": {"Bottom"},
              "C4": {"Top"}, "C5": {"Top"}}
    keys = set(layers)
    s = summarize_bom_row(_row(), layers, keys)
    assert s.top == ["C1", "C2", "C4", "C5"]
    assert s.bottom == ["C3"]
    assert s.missing == []
    assert s.stt == 3 and s.mpn == "M-A" and s.quantity == 5


def test_summarize_missing_and_dedup():
    layers = {"C1": {"Top"}}
    s = summarize_bom_row(_row(), layers, {"C1"})
    assert s.top == ["C1"]
    assert s.missing == ["C2", "C3", "C4", "C5"]
    assert s.bottom == []


def test_summarize_mixed_and_empty_layer():
    layers = {"C1": {"Top", "Bottom"}, "C2": {""}, "C3": {"bot"}}
    s = summarize_bom_row(_row(), layers, {"C1", "C2", "C3"})
    assert s.mixed_layers == ["C1", "C2"]
    assert s.bottom == ["C3"]
    assert s.top == []


def test_summarize_bottom_variants():
    layers = {"C1": {"BottomLayer"}, "C2": {"b"}, "C3": {"Top"}}
    s = summarize_bom_row(_row(), layers, set(layers))
    assert s.bottom == ["C1", "C2"]
    assert s.top == ["C3"]


def test_bom_summary_widget_show_hide():
    from ui.review_panel import ReviewPanel, share_percents, share_legend_text
    app = QApplication.instance() or QApplication([])
    panel = ReviewPanel()
    assert panel._info_stack.currentIndex() == 0
    assert panel._info_stack.currentWidget() is panel._info_group
    layers = {"C1": {"Top"}, "C3": {"Bottom"}}
    s = summarize_bom_row(_row(), layers, {"C1", "C3"})
    panel.display_bom_summary(s)
    assert panel._info_stack.currentIndex() == 1
    assert panel._info_stack.currentWidget() is panel._bom_summary_group
    assert panel._lbl_bom_mpn.text() == "M-A"
    assert panel._lbl_bom_mpn.font().bold() is True
    assert panel._lbl_bom_qty.text() == "5 pcs"
    assert "(1 pcs)" in panel._lbl_bom_top_cap.text()
    assert "C1" in panel._lbl_bom_top.text()
    assert "(1 pcs)" in panel._lbl_bom_bottom_cap.text()
    assert "C3" in panel._lbl_bom_bottom.text()
    assert "(3 pcs)" in panel._lbl_bom_missing_cap.text()
    assert panel._lbl_bom_share.text() == "Top 20% · Bottom 20% · Missing 60%"
    assert share_legend_text(3, 1, 1, 5) == "Top 60% · Bottom 20% · Missing 20%"
    assert not hasattr(panel, "_bom_share_bar")
    assert share_percents(3, 1, 1, 5) == (60, 20, 20)
    assert share_percents(0, 0, 0, 0) == (0, 0, 0)
    assert sum(share_percents(1, 1, 1, 3)) == 100
    panel.clear_bom_summary()
    assert panel._info_stack.currentIndex() == 0
    assert panel._info_stack.currentWidget() is panel._info_group
    assert panel._lbl_bom_mpn.text() == "-"
    assert "(0 pcs)" in panel._lbl_bom_top_cap.text()


def test_info_and_summary_share_geometry():
    from ui.review_panel import ReviewPanel
    app = QApplication.instance() or QApplication([])
    panel = ReviewPanel()
    panel.show()
    layers = {"C1": {"Top"}, "C3": {"Bottom"}}
    panel.display_bom_summary(summarize_bom_row(_row(), layers, {"C1", "C3"}))
    panel._info_stack.setCurrentIndex(1)
    h_summary = panel._info_stack.geometry().height()
    panel._info_stack.setCurrentIndex(0)
    h_info = panel._info_stack.geometry().height()
    # one shared slot: identical height in both modes
    assert h_summary == h_info
    assert panel._info_stack.count() == 2


def test_bom_row_click_emits_stt():
    from ui.bom_table_widget import BomTableWidget
    app = QApplication.instance() or QApplication([])
    widget = BomTableWidget()
    got = []
    widget.bom_row_selected.connect(got.append)
    widget.set_bom_rows([
        BomRow(stt=7, designator_display="C1", designators=["C1"], mpn="M"),
        BomRow(stt=9, designator_display="C2", designators=["C2"], mpn="M"),
    ])
    widget._on_cell_clicked(1, 0)
    assert got == [9]

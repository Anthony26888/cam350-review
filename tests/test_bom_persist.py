"""BOM survives a PickPlace load (BOM-first workflow)."""
import types

from models.bom import BomRow
from models.pickplace import PickPlaceData, PickPlaceComponent
from models.review import ReviewRecord
from ui.main_window import MainWindow


class _Repo:
    def __init__(self):
        self._next_id = 0

    def insert(self, record):
        self._next_id += 1
        return self._next_id

    def delete_all(self):
        pass

    def update(self, record):
        pass


class _HistoryRepo:
    def add(self, entry):
        return 1

    def clear_all(self):
        pass

    def list_by(self, *args, **kwargs):
        return []


class _Table:
    def __init__(self):
        self.overlay_calls = []

    def set_records(self, records):
        pass

    def select_record(self, index):
        pass

    def update_record_row(self, index):
        pass

    def set_bom_overlay(self, extra, mismatch):
        self.overlay_calls.append((set(extra), dict(mismatch)))

    def clear_bom_overlay(self):
        pass


class _Panel:
    def __init__(self):
        self.history_reloads = 0

    def set_record_list(self, records):
        pass

    def display_record(self, *args):
        pass

    def clear_record(self):
        pass

    def update_stats(self, *args):
        pass

    def reload_history(self, entries):
        self.history_reloads += 1


class _Btn:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def setEnabled(self, enabled):
        self.enabled = enabled

    def isEnabled(self):
        return self.enabled


class _ConfigMgr:
    def update(self, **kwargs):
        pass


def _holder():
    h = types.SimpleNamespace()
    h._records = []
    h._current_index = -1
    h._dirty = False
    h._pickplace_data = None
    h._panel_config = None
    h._pre_panel_snapshot = None
    h._jump_popup = None
    h._gerber_viewer = None
    h._config_mgr = _ConfigMgr()
    h._repo = _Repo()
    h._history_repo = _HistoryRepo()
    h._table_widget = _Table()
    h._review_panel = _Panel()
    h._bom_table = None
    h._table_tabs = None
    h._status_label = types.SimpleNamespace(setText=lambda t: None)
    h._bom_rows = [
        BomRow(stt=1, designator_display="C1,C2", designators=["C1", "C2"],
               mpn="M-A", quantity=2),
        BomRow(stt=2, designator_display="R9", designators=["R9"],
               mpn="M-B", quantity=1),
    ]
    h._bom_source_file = "bom.xlsx"
    h._bom_diff = None
    h._undo_stack = []
    h._redo_stack = []
    h._undo_action = None
    h._redo_action = None
    for name in ["_btn_export_report", "_btn_export_fixed", "_btn_batch_edit",
                 "_btn_ok_checked", "_btn_delete", "_btn_align",
                 "_btn_pcb_info", "_btn_new", "_btn_save",
                 "_btn_gerber_check"]:
        setattr(h, name, _Btn())
    h._gerber_check_action = _Btn()
    for name in ["_align_action", "_export_report_action",
                 "_export_fixed_action", "_pcb_info_action", "_new_action",
                 "_save_action", "_save_as_action"]:
        setattr(h, name, _Btn())
    h._panelize_action = None
    h._clear_panelize_action = None
    h._panel_config = None
    h._pre_panel_snapshot = None
    for name in ["_apply_loaded_pickplace", "_refresh_bom_compare",
                 "_update_bom_tab_texts", "_select_and_display",
                 "_refresh_history_panel", "_update_progress",
                 "_update_gerber_view_button", "_sync_action_states",
                 "_clear_gerber_config", "_pickplace_tuples",
                 "_auto_fill_mpn", "_push_undo", "_log_history",
                 "_update_undo_actions", "_record_snapshot"]:
        setattr(h, name, getattr(MainWindow, name).__get__(h))
    return h


def _pickplace_data():
    return PickPlaceData(
        headers=["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
        components=[
            PickPlaceComponent(designator="C1", mpn="", layer="Top",
                               x=1, y=2, rotation=0, row=1),
            PickPlaceComponent(designator="C2", mpn="M-A", layer="Top",
                               x=3, y=4, rotation=0, row=2),
            PickPlaceComponent(designator="D9", mpn="M-D", layer="Top",
                               x=5, y=6, rotation=0, row=3),
        ],
        raw_data=[],
    )


def test_bom_survives_pickplace_load():
    h = _holder()
    h._apply_loaded_pickplace(_pickplace_data(), "pp.xlsx")
    # BOM rows untouched
    assert len(h._bom_rows) == 2
    assert h._bom_source_file == "bom.xlsx"
    # compare recomputed on the NEW records: R9 missing, D9 extra.
    # C1 was empty and auto-filled from BOM, so nothing remains fillable.
    assert h._bom_diff is not None
    assert [r.stt for r, _ in h._bom_diff.missing] == [2]
    assert h._bom_diff.extra == ["D9"]
    assert h._bom_diff.mpn_fillable == []
    # overlay refreshed for the new record set
    assert h._table_widget.overlay_calls
    extra, _mismatch = h._table_widget.overlay_calls[-1]
    assert extra == {"D9"}
    # 3 records loaded normally
    assert [r.designator for r in h._records] == ["C1", "C2", "D9"]
    # empty MPN auto-filled from BOM on PickPlace load (no prompt)
    by_des = {r.designator: r for r in h._records}
    assert by_des["C1"].mpn == "M-A"
    assert by_des["C2"].mpn == "M-A"  # already present, untouched
    assert by_des["D9"].mpn == "M-D"

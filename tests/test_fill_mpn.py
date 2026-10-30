import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import types

from models.bom import BomRow
from models.review import ReviewRecord
from services.bom_compare import compare
from services.session_service import SessionService
from ui.main_window import MainWindow
from ui.review_panel import history_change_text
from models.history import HistoryEntry


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Repo:
    def __init__(self, records):
        self._records = {id(r): r for r in records}
        self.updated_many = []

    def update(self, record):
        pass

    def update_many(self, records):
        self.updated_many.extend(records)


class _HistoryRepo:
    def __init__(self):
        self.entries = []
        self.add_many_calls = 0

    def add(self, entry):
        self.entries.append(entry)
        return len(self.entries)

    def add_many(self, entries):
        self.add_many_calls += 1
        self.entries.extend(entries)

    def list_by(self, *args, **kwargs):
        return []


class _Table:
    def __init__(self):
        self.rows_updated = []
        self.overlay = None

    def update_record_row(self, index):
        self.rows_updated.append(index)

    def update_rows(self, indices):
        self.rows_updated.extend(indices)

    def set_bom_overlay(self, extra, mismatch):
        self.overlay = (set(extra), dict(mismatch))


class _Panel:
    def reload_history(self, entries):
        pass

    def update_stats(self, *args):
        pass


def _holder(records):
    _app()
    h = types.SimpleNamespace()
    h._records = records
    h._current_index = 0
    h._dirty = False
    h._repo = _Repo(records)
    h._history_repo = _HistoryRepo()
    h._table_widget = _Table()
    h._review_panel = _Panel()
    h._status_label = types.SimpleNamespace(text="", setText=lambda t: setattr(h._status_label, "text", t))
    h._undo_stack = []
    h._redo_stack = []
    h._undo_action = None
    h._redo_action = None
    h._bom_diff = None
    for name in ["_auto_fill_mpn", "_refresh_bom_compare",
                 "_update_bom_tab_texts",
                 "_record_snapshot", "_push_undo", "_update_progress",
                 "_update_undo_actions", "_history_entry", "_log_history"]:
        setattr(h, name, getattr(MainWindow, name).__get__(h))
    return h


def _bom_rows():
    return [
        BomRow(stt=1, designator_display="C1,C2", designators=["C1", "C2"],
               mpn="M-A", quantity=2),
        BomRow(stt=2, designator_display="C1", designators=["C1"],
               mpn="M-B", quantity=1),
        BomRow(stt=3, designator_display="C3", designators=["C3"],
               mpn="M-C", quantity=1),
    ]


def _records():
    return [
        ReviewRecord(designator="C1", mpn="", layer="Top",
                     old_x=1, old_y=2, old_rotation=0, status="Pending"),
        ReviewRecord(designator="C2", mpn="M-OLD", layer="Top",
                     old_x=3, old_y=4, old_rotation=0, status="Pending"),
        ReviewRecord(designator="C3", mpn="", layer="Bottom",
                     old_x=5, old_y=6, old_rotation=0, status="Pending"),
    ]


def test_auto_fill_mpn_fills_only_empty():
    h = _holder(_records())
    h._bom_rows = _bom_rows()
    h._refresh_bom_compare()
    assert h._bom_diff is not None
    # conflict: C1 claimed by rows 1 (M-A) and 2 (M-B) -> first wins
    assert len(h._bom_diff.conflicts) == 1
    filled = h._auto_fill_mpn()
    assert filled == 2
    by_des = {r.designator: r for r in h._records}
    assert by_des["C1"].mpn == "M-A"
    assert by_des["C2"].mpn == "M-OLD"  # non-empty untouched
    assert by_des["C3"].mpn == "M-C"
    # history logged per filled row
    assert len(h._history_repo.entries) == 2
    assert h._history_repo.add_many_calls == 1
    assert len(h._repo.updated_many) == 2
    assert h._table_widget.rows_updated == [0, 2]
    assert all(e.action == "BOM" for e in h._history_repo.entries)
    assert {e.designator for e in h._history_repo.entries} == {"C1", "C3"}


def test_auto_fill_mpn_idempotent():
    h = _holder(_records())
    h._bom_rows = _bom_rows()
    h._refresh_bom_compare()
    assert h._auto_fill_mpn() == 2
    assert h._auto_fill_mpn() == 0  # second run: nothing empty, no dup history
    assert len(h._history_repo.entries) == 2
    assert len(h._undo_stack) == 1  # single undo step for the batch


def test_history_change_text_mpn():
    e = HistoryEntry(designator="C1", action="BOM", mpn_new="M-A",
                     created_at="2026-10-04 10:00:00")
    s = history_change_text(e)
    assert "MPN: M-A" in s
    e2 = HistoryEntry(designator="C1", action="Edit", mpn_old="M-A",
                      mpn_new="M-B", old_x=1.0, new_x=1.0)
    s2 = history_change_text(e2)
    assert "MPN: M-A->M-B" in s2
    assert "X:" not in s2  # unchanged values hidden


def test_history_mpn_roundtrip_dict():
    e = HistoryEntry(designator="C1", action="BOM", mpn_new="M-A")
    back = HistoryEntry.from_dict(e.to_dict())
    assert back.mpn_new == "M-A"
    assert back.mpn_old == ""


def test_session_bom_roundtrip(tmp_path):
    path = str(tmp_path / "s.cam350review")
    rows = [BomRow(stt=1, designator_display="C1,C2",
                   designators=["C1", "C2"], mpn="M-A", quantity=2).to_dict()]
    SessionService.save(path, [], bom_rows=rows, bom_source_file="b.xlsx")
    loaded = SessionService.load(str(path))
    assert loaded.version == 8
    assert loaded.bom_source_file == "b.xlsx"
    back = [BomRow.from_dict(d) for d in loaded.bom_rows]
    assert back[0].designators == ["C1", "C2"]
    assert back[0].mpn == "M-A"


def test_session_legacy_without_bom(tmp_path):
    import json
    path = tmp_path / "old.cam350review"
    path.write_text(json.dumps({"version": 7, "records": []}), encoding="utf-8")
    loaded = SessionService.load(str(path))
    assert loaded.bom_rows == []
    assert loaded.bom_source_file == ""


def test_auto_fill_mpn_reports_progress():
    h = _holder(_records())
    h._bom_rows = _bom_rows()
    h._refresh_bom_compare()
    calls = []
    assert h._auto_fill_mpn(
        progress=lambda done, total: calls.append((done, total))) == 2
    assert calls[-1] == (2, 2)


def test_apply_bom_rows_reports_progress():
    h = _holder(_records())
    h._sync_action_states = lambda: None
    h._apply_bom_rows = MainWindow._apply_bom_rows.__get__(h)
    calls = []
    h._apply_bom_rows(
        _bom_rows(), "bom.xlsx",
        progress=lambda message, pct: calls.append(pct),
    )
    assert calls[-1] == 100
    assert all(0 <= pct <= 100 for pct in calls)

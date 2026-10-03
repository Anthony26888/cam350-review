import os
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from models.review import ReviewRecord
from services.session_service import SessionService
from ui.main_window import MainWindow


class _Repo:
    def __init__(self, records):
        self._records = list(records)
        self.updated = []
        self.bulk_updated = []
        self.deleted_ids = []
        self.delete_all_count = 0
        self._next_id = max([r.id for r in self._records], default=0) + 1

    def update(self, record):
        self.updated.append(record)

    def update_many(self, records):
        self.bulk_updated.extend(list(records))
        self.updated.extend(records)

    def delete_by_id(self, rid):
        self.deleted_ids.append(rid)
        self._records = [r for r in self._records if r.id != rid]

    def delete_all(self):
        self.delete_all_count += 1
        self._records = []

    def insert(self, record):
        record.id = self._next_id
        self._next_id += 1
        self._records.append(record)
        return record.id

    def get_all(self):
        return list(self._records)


class _Table:
    def __init__(self):
        self.records_set = None
        self.selected = None
        self.checked = set()
        self.cleared_count = 0
        self.row_updated = []

    def set_records(self, records):
        self.records_set = list(records)

    def get_checked_indices(self):
        return sorted(self.checked)

    def clear_checked(self):
        self.cleared_count += 1
        self.checked = set()

    def select_record(self, index):
        self.selected = index

    def update_record_row(self, index):
        self.row_updated.append(index)

    def update_all_rows(self):
        self.all_rows_updated = True


class _Panel:
    def __init__(self):
        self.lists = []
        self.displayed = None

    def set_record_list(self, records):
        self.lists.append(list(records))

    def display_record(self, record, index, total, text=""):
        self.displayed = (record, index, total)

    def clear_record(self):
        self.displayed = None


class _Popup:
    def __init__(self, visible=True):
        self.visible = visible
        self.shown_at = []
        self.data_set = None
        self.closed = False

    def isVisible(self):
        return self.visible and not self.closed

    def show_at(self, records, index):
        self.shown_at.append((list(records), index))

    def set_records(self, records, index):
        self.data_set = (list(records), index)

    def close(self):
        self.closed = True


class _Viewer:
    def __init__(self):
        self.refreshed = []
        self.closed = False

    def refresh_records(self, records):
        self.refreshed.append(list(records))

    def close(self):
        self.closed = True


class _Label:
    def __init__(self):
        self.text = ""

    def setText(self, t):
        self.text = t


class _Btn:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def setEnabled(self, e):
        self.enabled = e

    def isEnabled(self):
        return self.enabled


def _record(des, rec_id):
    r = ReviewRecord(designator=des)
    r.id = rec_id
    return r


def _holder(records, popup=None, viewer=None, current_index=0):
    h = types.SimpleNamespace()
    h._records = records
    h._current_index = current_index
    h._session_file = "s.cam350review"
    h._dirty = True
    h._pickplace_data = object()
    h._repo = _Repo(records)
    h._table_widget = _Table()
    h._review_panel = _Panel()
    h._jump_popup = popup
    h._gerber_viewer = viewer
    h._status_label = _Label()
    h._undo_stack = []
    h._redo_stack = []
    h._undo_action = None
    h._redo_action = None
    for name in ["_btn_export_report", "_btn_export_fixed", "_btn_batch_edit",
                 "_btn_ok_checked", "_btn_delete", "_btn_align", "_btn_pcb_info",
                 "_btn_new", "_btn_save"]:
        setattr(h, name, _Btn(True))
    for name in ["_popup_delete", "_delete_selected", "_sync_after_mutation",
                 "_close_jump_popup", "_close_gerber_viewer", "_close_prescreen_dialog",
                 "_clear_all",
                 "_restore_records", "_select_and_display", "_push_undo",
                 "_log_history", "_refresh_history_panel",
                 "_collect_history_dicts", "_restore_history"]:
        try:
            setattr(h, name, getattr(MainWindow, name).__get__(h))
        except AttributeError:
            pass
    h._history_repo = types.SimpleNamespace(
        add=lambda e: 0,
        list_by=lambda *a, **k: [],
        get_all=lambda *a, **k: [],
        clear_all=lambda: None,
    )
    h._record_snapshot = MainWindow._record_snapshot.__get__(h)
    h._update_undo_actions = MainWindow._update_undo_actions.__get__(h)
    h._update_progress = lambda: None
    h._sync_action_states = lambda: None
    h._update_gerber_view_button = lambda: None
    h._clear_gerber_config = lambda: None
    return h


@pytest.fixture()
def mb(monkeypatch):
    class _MB:
        Yes = QMessageBox.Yes
        No = QMessageBox.No
        answer = QMessageBox.Yes
        instances = []

        def __init__(self, *args, **kwargs):
            self.flags = {}
            self.text = ""
            _MB.instances.append(self)

        def setWindowTitle(self, title):
            pass

        def setText(self, text):
            self.text = text

        def setStandardButtons(self, buttons):
            pass

        def setWindowFlag(self, flag, on=True):
            self.flags[flag] = on

        def exec(self):
            return _MB.answer

        @staticmethod
        def question(*args, **kwargs):
            box = _MB()
            return _MB.answer

        @staticmethod
        def warning(*args, **kwargs):
            return QMessageBox.Ok

    monkeypatch.setattr("ui.main_window.QMessageBox", _MB)
    _MB.instances = []
    return _MB


def test_popup_delete_resyncs_all_views(mb):
    records = [_record("C1", 1), _record("C2", 2), _record("C3", 3)]
    popup = _Popup(visible=True)
    viewer = _Viewer()
    h = _holder(records, popup=popup, viewer=viewer, current_index=1)
    h._popup_delete(1)
    assert h._repo.deleted_ids == [2]
    assert [r.designator for r in h._records] == ["C1", "C3"]
    assert h._table_widget.records_set == h._records
    assert popup.shown_at == [(h._records, 1)]
    assert viewer.refreshed[-1] == h._records
    assert "C2" in h._status_label.text
    assert len(h._undo_stack) == 1


def test_popup_delete_last_record_closes_viewer_and_popup(mb):
    records = [_record("C1", 1)]
    popup = _Popup(visible=True)
    viewer = _Viewer()
    h = _holder(records, popup=popup, viewer=viewer, current_index=0)
    h._popup_delete(0)
    assert viewer.closed is True
    assert popup.closed is True
    assert h._gerber_viewer is None
    assert h._jump_popup is None
    assert h._records == []
    assert h._repo.delete_all_count == 1


def test_popup_delete_hidden_popup_not_reopened(mb):
    records = [_record("C1", 1), _record("C2", 2)]
    popup = _Popup(visible=False)
    h = _holder(records, popup=popup, current_index=0)
    h._popup_delete(0)
    assert popup.closed is False
    assert popup.shown_at == []
    assert popup.data_set == (h._records, 0)


def test_delete_selected_removes_checked_rows_and_resyncs(mb):
    records = [_record(f"C{i}", i + 1) for i in range(4)]
    table = _Table()
    table.checked = {0, 2}
    popup = _Popup(visible=True)
    viewer = _Viewer()
    h = _holder(records, popup=popup, viewer=viewer, current_index=3)
    h._table_widget = table
    h._delete_selected()
    assert [r.designator for r in h._records] == ["C1", "C3"]
    assert {r.status for r in h._repo.updated} == {"Deleted"}
    assert table.cleared_count == 1
    assert popup.shown_at == [(h._records, 1)]
    assert viewer.refreshed[-1] == h._records


def test_delete_selected_no_selection_warns_only(mb):
    records = [_record("C1", 1)]
    h = _holder(records, current_index=0)
    h._delete_selected()
    assert mb.instances == []
    assert len(h._records) == 1
    assert h._undo_stack == []


def test_clear_all_swallows_closed_qt_objects():
    class _DeadViewer:
        def close(self):
            raise RuntimeError("wrapped C/C++ object has been deleted")

    class _DeadPopup(_DeadViewer):
        pass

    records = [_record("C1", 1)]
    h = _holder(records, popup=_DeadPopup(), viewer=_DeadViewer())
    h._clear_all()
    assert h._gerber_viewer is None
    assert h._jump_popup is None
    assert h._current_index == -1


def test_restore_records_resyncs_popup_and_viewer(mb):
    snap_records = [_record("X1", 0), _record("Y2", 0)]
    snap = SessionService.records_to_list(snap_records)
    old = [_record("C1", 1), _record("C2", 2), _record("C3", 3)]
    popup = _Popup(visible=True)
    viewer = _Viewer()
    h = _holder(old, popup=popup, viewer=viewer, current_index=2)
    h._restore_records(snap)
    assert [r.designator for r in h._records] == ["X1", "Y2"]
    assert all(r.id > 0 for r in h._records)
    target = min(2, len(h._records) - 1)
    assert popup.shown_at == [(h._records, target)]
    assert viewer.refreshed[-1] == h._records


def test_sync_after_mutation_without_popup_or_viewer():
    records = [_record("C1", 1), _record("C2", 2)]
    h = _holder(records, popup=None, viewer=None, current_index=5)
    h._sync_after_mutation(min(5, len(records) - 1))
    assert h._table_widget.selected == 1
    assert h._review_panel.lists[-1] == records


def test_toolbar_action_buttons_are_connected():
    src = (Path(__file__).resolve().parents[1] / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "self._btn_delete.clicked.connect(self._delete_selected)" in src
    assert "self._btn_ok_checked.clicked.connect(self._mark_checked_ok)" in src


def test_popup_delete_confirm_box_is_topmost(mb):
    records = [_record("C1", 1), _record("C2", 2)]
    h = _holder(records, current_index=0)
    h._popup_delete(0)
    assert mb.instances, "confirm box must be created"
    box = mb.instances[0]
    assert box.flags.get(Qt.WindowStaysOnTopHint) is True
    assert "C1" in box.text
    assert [r.designator for r in h._records] == ["C2"]


def test_on_gerber_rotation_edited_persists_and_refreshes():
    records = [_record("C1", 1)]
    h = _holder(records, current_index=0)
    handler = MainWindow._on_gerber_rotation_edited.__get__(h)
    rec = h._records[0]
    rec.new_rotation = 45.0
    rec.status = "Edited"
    handler(0)
    assert h._repo.updated == [rec]
    assert h._table_widget.row_updated == [0]
    assert "C1" in h._status_label.text

    h._repo.updated.clear()
    handler(5)
    assert h._repo.updated == []


class _FlagViewer:
    def __init__(self):
        self.flag_calls = []

    def set_flagged_indices(self, indices):
        self.flag_calls.append(set(indices))


def _prescreen_holder(records, viewer=None):
    h = _holder(records, viewer=viewer)
    h._prescreen_dismissed = set()
    for name in ["_apply_prescreen_result", "_on_flag_dismiss",
                 "_current_flagged_indices", "_sync_viewer_flags"]:
        setattr(h, name, getattr(MainWindow, name).__get__(h))
    return h


def test_apply_prescreen_result_fills_flags_and_viewer():
    from services.prescreen import PrescreenIssue

    records = [_record("C1", 1), _record("C2", 2)]
    viewer = _FlagViewer()
    h = _prescreen_holder(records, viewer=viewer)

    issues = [
        PrescreenIssue(kind="ROT", index=1, designator="C2", x=3.0, y=4.0),
        PrescreenIssue(kind="PAD", index=1, designator="C2", x=3.0, y=4.0),
        PrescreenIssue(kind="OUT", index=0, designator="C1", x=99.0, y=0.0),
    ]
    MainWindow._apply_prescreen_result.__get__(h)(issues)
    assert records[1].prescreen_flags == ["ROT", "PAD"]
    assert records[0].prescreen_flags == ["OUT"]
    assert viewer.flag_calls == [{1, 0}]
    assert "Pre-screen" in h._status_label.text
    assert "3" in h._status_label.text


def test_apply_prescreen_result_none_keeps_state_untouched():
    records = [_record("C1", 1)]
    records[0].prescreen_flags = ["DUP"]
    h = _prescreen_holder(records)
    MainWindow._apply_prescreen_result.__get__(h)(None)
    assert records[0].prescreen_flags == ["DUP"]


def test_on_flag_dismiss_persists_key_and_clears():
    records = [_record("C1", 1)]
    records[0].old_x, records[0].old_y = 10.0, 20.0
    records[0].prescreen_flags = ["ROT", "DUP"]
    h = _prescreen_holder(records)
    h._table_widget.update_all_rows = lambda: None

    MainWindow._on_flag_dismiss.__get__(h)(0)
    assert records[0].prescreen_flags == []
    assert h._prescreen_dismissed == {
        "ROT:C1:10.000:20.000",
        "DUP:C1:10.000:20.000",
    }
    assert h._dirty is True


def test_apply_align_record_defers_db_write_until_flush(monkeypatch):
    monkeypatch.setattr("ui.main_window.log_event", lambda *a, **k: None)
    records = [_record("C1", 1), _record("C2", 2)]
    h = _holder(records)
    h._pending_align_writes = []

    apply_rec = MainWindow._apply_align_record.__get__(h)
    flush = MainWindow._flush_align_writes.__get__(h)
    h._find_record = MainWindow._find_record.__get__(h)

    apply_rec("C1", 10.0, 20.0, 90.0)
    apply_rec("C2", None, None, 45.0)  # duplicate designator skipped
    assert h._repo.updated == []            # deferred
    assert len(h._pending_align_writes) == 2
    assert records[0].status == "Aligned"
    assert records[0].review_time

    flush()
    flush()                                  # second flush is a no-op
    assert h._repo.bulk_updated == [records[0], records[1]]
    assert h._repo.updated == [records[0], records[1]]
    assert h._pending_align_writes == []
    assert h._dirty is True


class _BusyDlg:
    def __init__(self, text=""):
        self.text = text
        self.closed = False

    def reset(self):
        pass

    def close(self):
        self.closed = True

    def deleteLater(self):
        pass


def test_run_with_busy_dialog_executes_and_closes():
    created = []

    def factory(text):
        d = _BusyDlg(text)
        created.append(d)
        return d

    ran = []
    h = types.SimpleNamespace()
    MainWindow._run_with_busy_dialog.__get__(h)(
        "msg", lambda: ran.append(1), dialog_factory=factory,
    )
    assert ran == [1]
    assert created and created[0].closed is True


def test_run_with_busy_dialog_closes_on_error():
    created = []

    def factory(text):
        d = _BusyDlg(text)
        created.append(d)
        return d

    def boom():
        raise ValueError("boom")

    h = types.SimpleNamespace()
    with pytest.raises(ValueError):
        MainWindow._run_with_busy_dialog.__get__(h)(
            "msg", boom, dialog_factory=factory,
        )
    assert created and created[0].closed is True

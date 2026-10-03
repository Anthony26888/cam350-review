import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from database.database import Database
from database.history_repo import HistoryRepo
from models.history import HistoryEntry
from services.session_service import SessionService


def test_history_repo_add_list(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "h.db"))
    monkeypatch.setattr(Database, "_instance", db)
    repo = HistoryRepo()
    repo.add(HistoryEntry(designator="R12", block=0, action="Import",
                          new_x=10.0, new_y=20.0, new_rotation=0.0,
                          created_at="2026-10-03 09:30:05"))
    repo.add(HistoryEntry(designator="R12", block=0, action="Edit",
                          old_x=10.0, new_x=11.5,
                          old_rotation=0.0, new_rotation=90.0,
                          remark="lech", created_at="2026-10-03 10:15:30"))
    entries = repo.list_by("R12", 0)
    assert len(entries) == 2
    # newest first
    assert entries[0].action == "Edit"
    assert entries[1].action == "Import"
    assert "11.5" in str(entries[0].new_x)


def test_format_history_entry_detail():
    from ui.review_panel import format_history_entry
    e = HistoryEntry(designator="R12", action="Edit",
                     old_x=10.0, new_x=11.5,
                     old_y=20.0, new_y=20.0,
                     old_rotation=0.0, new_rotation=90.0,
                     remark="lech 1.5mm",
                     created_at="2026-10-03 10:15:30")
    s = format_history_entry(e)
    assert "10:15:30" in s
    assert "Edit" in s
    assert "10->11.5" in s
    assert "0°->90°" in s
    # Y unchanged -> hidden
    assert "Y:" not in s


def test_format_import_entry():
    from ui.review_panel import format_history_entry
    e = HistoryEntry(designator="R1", action="Import",
                     new_x=10.0, new_y=20.0, new_rotation=0.0,
                     created_at="2026-10-03 09:30:05")
    s = format_history_entry(e)
    assert "Import" in s
    assert "X: 10" in s


def test_review_panel_reload_history():
    from PySide6.QtWidgets import QApplication
    from ui.review_panel import ReviewPanel
    app = QApplication.instance() or QApplication([])
    panel = ReviewPanel()
    assert panel._history_table.columnCount() == 3
    # empty -> placeholder spanning 3 cols
    panel.reload_history([])
    assert panel._history_table.rowCount() == 1
    panel.reload_history([
        HistoryEntry(designator="R12", action="Edit",
                     old_x=1.0, new_x=2.0,
                     created_at="2026-10-03 10:00:00"),
    ])
    assert panel._history_table.rowCount() == 1
    assert panel._history_table.columnCount() == 3
    assert "10:00:00" in panel._history_table.item(0, 0).text()
    assert "Edit" in panel._history_table.item(0, 1).text()
    assert "1->2" in panel._history_table.item(0, 2).text()
    panel.clear_record()
    assert panel._history_table.rowCount() == 1


def test_session_history_roundtrip(tmp_path):
    path = str(tmp_path / "s.cam350review")
    hist = [HistoryEntry(designator="R12", block=0, action="Edit",
                         old_x=10.0, new_x=11.5,
                         created_at="2026-10-03 10:15:30").to_dict()]
    SessionService.save(path, [], history=hist)
    loaded = SessionService.load(path)
    assert loaded.history[0]["designator"] == "R12"
    back = HistoryEntry.from_dict(loaded.history[0])
    assert back.new_x == 11.5

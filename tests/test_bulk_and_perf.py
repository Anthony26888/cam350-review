import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from database.database import Database
from models.review import ReviewRecord
from utils.perf_log import Timer, log_event


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _make_db(tmp_path):
    return Database(db_path=str(tmp_path / "t.db"))


def test_transaction_commits_once(tmp_path):
    db = _make_db(tmp_path)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO review (designator) VALUES ('A')"
        )
        conn.execute(
            "INSERT INTO review (designator) VALUES ('B')"
        )
    rows = db.fetchall("SELECT designator FROM review")
    assert sorted(r["designator"] for r in rows) == ["A", "B"]


def test_transaction_rolls_back_on_error(tmp_path):
    db = _make_db(tmp_path)
    with pytest.raises(ValueError):
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO review (designator) VALUES ('X')"
            )
            raise ValueError("boom")
    assert db.fetchall("SELECT * FROM review") == []


def test_update_many_persists_all_in_one_commit(tmp_path, monkeypatch):
    from database.review_repo import ReviewRepo

    db = _make_db(tmp_path)
    monkeypatch.setattr(Database, "_instance", db)
    repo = ReviewRepo()

    recs = []
    for i in range(5):
        r = ReviewRecord(designator=f"C{i}")
        r.id = repo.insert(r)
        recs.append(r)

    for i, r in enumerate(recs):
        r.status = "Edited"
        r.new_x = float(i)
    repo.update_many(recs)

    loaded = repo.get_all()
    by_id = {r.id: r for r in loaded}
    for i, orig in enumerate(recs):
        got = by_id[orig.id]
        assert got.status == "Edited"
        assert got.new_x == float(i)


def test_update_many_empty_is_noop(tmp_path, monkeypatch):
    from database.review_repo import ReviewRepo

    db = _make_db(tmp_path)
    monkeypatch.setattr(Database, "_instance", db)
    repo = ReviewRepo()
    repo.update_many([])  # must not raise
    assert repo.get_all() == []


def test_perf_log_event_appends_line(tmp_path):
    log_event("unit_test", base_dir=str(tmp_path), ms=42, rows=7)
    text = (tmp_path / "perf.log").read_text(encoding="utf-8")
    assert "unit_test |" in text
    assert "ms=42" in text
    assert "rows=7" in text


def test_perf_log_timer_measures():
    t = Timer()
    assert t.ms() >= 0


def test_prescreen_stale_generation_ignored(app):
    from ui.origin_align_wizard import OriginAlignWizard
    from models.pickplace import PickPlaceData

    w = OriginAlignWizard(PickPlaceData(headers=[], file_path=""),
                          records=[], apply_callback=lambda *a: None)
    w._show_step(5)
    w._prescreen_generation = 7

    w._on_prescreen_finished([], gen=99)
    assert w._prescreen_issues is None  # stale -> ignored

    w._on_prescreen_finished([], gen=7)
    assert w._prescreen_issues == []

    w._on_prescreen_failed("late error", gen=1)
    assert "late error" not in w._prescreen_summary.text()

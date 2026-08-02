from models.review import ReviewRecord
from services.session_service import SessionService


def _make_record(designator="C1", status="Pending"):
    return ReviewRecord(
        id=3,
        designator=designator,
        mpn="MPN1",
        layer="Top",
        old_x=1.0,
        old_y=2.0,
        old_rotation=90,
        new_x=1.5,
        new_y=2.5,
        new_rotation=180,
        status=status,
        remark="check pad",
        review_time="2026-01-01 00:00:00",
        datasheet="http://example.com/ds",
        row_index=5,
    )


def test_records_round_trip():
    record = _make_record()
    data = SessionService.records_to_list([record])
    restored = SessionService.list_to_records(data)
    assert len(restored) == 1
    r = restored[0]
    assert r.designator == "C1"
    assert r.new_x == 1.5
    assert r.new_rotation == 180
    assert r.status == "Pending"
    assert r.remark == "check pad"
    assert r.row_index == 5


def test_save_and_load(tmp_path):
    path = tmp_path / "session.cam350review"
    record = _make_record()
    SessionService.save(str(path), [record], source_file="src.xlsx", current_index=2)
    loaded = SessionService.load(str(path))
    assert loaded.version == 1
    assert loaded.source_file == "src.xlsx"
    assert loaded.current_index == 2
    assert len(loaded.records) == 1
    assert loaded.records[0]["designator"] == "C1"


def test_load_missing_file(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        SessionService.load(str(tmp_path / "missing.cam350review"))

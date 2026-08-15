from models.review import ReviewRecord
from services.session_service import SessionService, compress_text, decompress_text


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
    assert loaded.version == 5
    assert loaded.source_file == "src.xlsx"
    assert loaded.current_index == 2
    assert len(loaded.records) == 1
    assert loaded.records[0]["designator"] == "C1"
    assert loaded.pcb_info is None


def test_save_and_load_gerber_paths(tmp_path):
    path = tmp_path / "session_gerber.cam350review"
    record = _make_record()
    SessionService.save(
        str(path), [record], source_file="src.xlsx",
        gerberGko=r"D:\gerber\b.GKO",
        gerberGtp=r"D:\gerber\b.GTP",
        gerberGbp=r"D:\gerber\b.GBP",
        gerberGto=r"D:\gerber\b.GTO",
        gerberGbo=r"D:\gerber\b.GBO",
    )
    loaded = SessionService.load(str(path))
    assert loaded.version == 5
    assert loaded.gerberGko == r"D:\gerber\b.GKO"
    assert loaded.gerberGtp == r"D:\gerber\b.GTP"
    assert loaded.gerberGbp == r"D:\gerber\b.GBP"
    assert loaded.gerberGto == r"D:\gerber\b.GTO"
    assert loaded.gerberGbo == r"D:\gerber\b.GBO"


def test_save_gerber_defaults_empty(tmp_path):
    path = tmp_path / "session_default.cam350review"
    record = _make_record()
    SessionService.save(str(path), [record])
    loaded = SessionService.load(str(path))
    assert loaded.gerberGko == ""
    assert loaded.gerberGbo == ""


def test_save_and_load_with_pcb_info(tmp_path):
    path = tmp_path / "session_pcb.cam350review"
    record = _make_record()
    pcb_info = {
        "board_width": 120.5,
        "board_height": 90.0,
        "working_area_width": 120.5,
        "position_working": 0.0,
        "x_boc1": 10.0, "y_boc1": 20.0,
        "x_boc2": 30.0, "y_boc2": 40.0,
        "x_boc3": 50.0, "y_boc3": 60.0,
        "thickness": 1.6,
    }
    SessionService.save(str(path), [record], source_file="src.xlsx", pcb_info=pcb_info)
    loaded = SessionService.load(str(path))
    assert loaded.pcb_info == pcb_info
    assert loaded.pcb_info["board_width"] == 120.5


def test_save_and_load_gerber_view(tmp_path):
    path = tmp_path / "session_view.cam350review"
    record = _make_record()
    gerber_view = {
        "layer": 1,
        "rotation": 180,
        "flip": True,
        "offset_x": 1.25,
        "offset_y": -0.5,
        "outline": False,
        "paste": True,
        "silk": True,
        "pickplace": False,
        "crosshair": True,
        "invert_rot": True,
    }
    SessionService.save(str(path), [record], source_file="src.xlsx", gerber_view=gerber_view)
    loaded = SessionService.load(str(path))
    assert loaded.gerber_view == gerber_view
    assert loaded.gerber_view["rotation"] == 180
    assert loaded.gerber_view["offset_y"] == -0.5


def test_save_gerber_view_defaults_none(tmp_path):
    path = tmp_path / "session_view_empty.cam350review"
    record = _make_record()
    SessionService.save(str(path), [record])
    loaded = SessionService.load(str(path))
    assert loaded.gerber_view is None


def test_load_legacy_version(tmp_path):
    import json
    path = tmp_path / "legacy.cam350review"
    data = {
        "version": 1,
        "source_file": "old.xlsx",
        "current_index": 0,
        "records": [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    loaded = SessionService.load(str(path))
    assert loaded.version == 1
    assert loaded.pcb_info is None


def test_save_and_load_column_mapping(tmp_path):
    path = tmp_path / "session_mapping.cam350review"
    record = _make_record()
    mapping = {
        "designator": "Ref",
        "mpn": "Part Number",
        "layer": "Side",
        "x": "Xpos",
        "y": "Ypos",
        "rotation": "Angle",
    }
    SessionService.save(
        str(path), [record], source_file="src.xlsx", column_mapping=mapping
    )
    loaded = SessionService.load(str(path))
    assert loaded.version == 5
    assert loaded.column_mapping == mapping
    assert loaded.column_mapping["x"] == "Xpos"


def test_save_column_mapping_defaults_none(tmp_path):
    path = tmp_path / "session_mapping_empty.cam350review"
    record = _make_record()
    SessionService.save(str(path), [record])
    loaded = SessionService.load(str(path))
    assert loaded.column_mapping is None


def test_load_missing_file(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        SessionService.load(str(tmp_path / "missing.cam350review"))


def test_compress_round_trip():
    text = "%FSLAX24Y24*%\n%MOIN*%\nG01*\nX100Y100D02*\nM02*\n"
    payload = compress_text(text)
    assert decompress_text(payload) == text


def test_save_and_load_gerber_files(tmp_path):
    path = tmp_path / "session_gerber_files.cam350review"
    record = _make_record()
    gerber_files = {
        "gerberGko": compress_text("GKO-CONTENT\n%MOMM*%\nM02*"),
        "gerberGtp": compress_text("GTP-CONTENT"),
    }
    SessionService.save(
        str(path), [record], source_file="src.xlsx",
        gerberGko=r"D:\gerber\b.GKO", gerberGtp=r"D:\gerber\b.GTP",
        gerber_files=gerber_files,
    )
    loaded = SessionService.load(str(path))
    assert loaded.version == 5
    assert loaded.gerber_files is not None
    assert decompress_text(loaded.gerber_files["gerberGko"]) == "GKO-CONTENT\n%MOMM*%\nM02*"
    assert decompress_text(loaded.gerber_files["gerberGtp"]) == "GTP-CONTENT"


def test_save_gerber_files_defaults_none(tmp_path):
    path = tmp_path / "session_no_gerber_files.cam350review"
    record = _make_record()
    SessionService.save(str(path), [record])
    loaded = SessionService.load(str(path))
    assert loaded.gerber_files is None


def test_load_legacy_v4_gerber_files_none(tmp_path):
    import json
    path = tmp_path / "legacy_v4.cam350review"
    data = {
        "version": 4,
        "source_file": "old.xlsx",
        "current_index": 0,
        "records": [],
        "gerberGko": r"D:\gerber\b.GKO",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    loaded = SessionService.load(str(path))
    assert loaded.version == 4
    assert loaded.gerber_files is None
    assert loaded.gerberGko == r"D:\gerber\b.GKO"

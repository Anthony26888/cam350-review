import csv

import pytest

from database.database import Database
from database.review_repo import ReviewRepo
from models.pickplace import PickPlaceData, PickPlaceComponent
from models.review import ReviewRecord
from services.export_service import ExportService
from services.panelize_service import (
    PanelBlock, PanelConfig, PanelError, is_panelized, panelize_records,
    transform_point,
)


def _base_records():
    return [
        ReviewRecord(
            designator="C1", mpn="M1", layer="Top",
            old_x=10.0, old_y=20.0, old_rotation=0.0,
        ),
        ReviewRecord(
            designator="C2", mpn="M2", layer="Top",
            old_x=30.0, old_y=40.0, old_rotation=90.0,
        ),
    ]


def _cfg_2blocks(flipped=True):
    # For a flipped block the entered origin is the cell's top-right corner.
    block1 = PanelBlock(index=1, origin_x=200.0, origin_y=100.0, rotation=180) if flipped \
        else PanelBlock(index=1, origin_x=110.0, origin_y=0.0)
    return PanelConfig(blocks=[
        PanelBlock(index=0, origin_x=0.0, origin_y=0.0),
        block1,
    ])


def test_rebuild_grid_raster():
    cfg = PanelConfig(nx=2, ny=2, dx=100.0, dy=120.0)
    cfg.rebuild_grid()
    assert cfg.count == 4
    b1 = cfg.block_by_index(1)
    assert (b1.origin_x, b1.origin_y) == (100.0, 0.0)
    b3 = cfg.block_by_index(3)
    assert (b3.origin_x, b3.origin_y) == (100.0, 120.0)


def test_panelize_two_blocks_pure_shift():
    cfg = _cfg_2blocks(flipped=False)
    recs = panelize_records(_base_records(), cfg)
    assert len(recs) == 4
    assert is_panelized(recs)

    c1_block0 = recs[0]
    assert c1_block0.designator == "C1"
    assert c1_block0.block == 0
    assert (c1_block0.old_x, c1_block0.old_y) == (10.0, 20.0)

    c1_block1 = recs[2]
    assert c1_block1.block == 1
    assert c1_block1.designator == "C1_2"  # renamed for the 2nd block
    assert c1_block1.old_x == pytest.approx(120.0)
    assert c1_block1.old_y == pytest.approx(20.0)


def test_panelize_flipped_block_mirrors_top_right():
    # C1 (10,20) @ 180° and block-1 origin (200,100):
    # X' = 200 - 10 = 190 ; Y' = 100 - 20 = 80
    cfg = _cfg_2blocks(flipped=True)
    recs = panelize_records(_base_records(), cfg)
    assert len(recs) == 4

    c1_block1 = recs[2]
    assert c1_block1.block == 1
    assert c1_block1.block_rotation == 180
    assert c1_block1.old_x == pytest.approx(190.0)
    assert c1_block1.old_y == pytest.approx(80.0)
    assert c1_block1.old_rotation == pytest.approx(180.0)

    c2_block1 = recs[3]
    # X' = 200 - 30 = 170 ; Y' = 100 - 40 = 60
    assert c2_block1.old_x == pytest.approx(170.0)
    assert c2_block1.old_y == pytest.approx(60.0)
    assert c2_block1.old_rotation == pytest.approx(270.0)


def test_transform_point_identity_and_shift():
    cfg = _cfg_2blocks(flipped=False)
    assert transform_point(10.0, 20.0, cfg, None) == (10.0, 20.0)
    block1 = cfg.block_by_index(1)
    assert transform_point(10.0, 20.0, cfg, block1) == (120.0, 20.0)


def test_transform_point_flipped_top_right():
    cfg = _cfg_2blocks(flipped=True)
    block1 = cfg.block_by_index(1)
    # block-1 origin is the cell's top-right corner (200,100)
    assert transform_point(10.0, 20.0, cfg, block1) == (190.0, 80.0)


def test_double_panelize_raises():
    cfg = _cfg_2blocks(flipped=False)
    recs = panelize_records(_base_records(), cfg)
    with pytest.raises(PanelError):
        panelize_records(recs, cfg)


def test_panelize_single_block_identity():
    cfg = PanelConfig(blocks=[PanelBlock(index=0)])
    recs = panelize_records(_base_records(), cfg)
    assert len(recs) == 2
    assert recs[0].block == 0
    assert recs[0].old_x == 10.0
    assert recs[0].old_y == 20.0


def test_panelize_preserves_edited_coords_on_identity_block():
    cfg = PanelConfig(blocks=[PanelBlock(index=0)])
    base = _base_records()
    base[0].new_x = 5.0
    base[0].new_y = 6.0
    base[0].new_rotation = 45.0
    recs = panelize_records(base, cfg)
    assert recs[0].old_x == 10.0
    assert recs[0].old_y == 20.0
    assert recs[0].new_x == 5.0
    assert recs[0].new_y == 6.0
    assert recs[0].new_rotation == 45.0


def test_panelize_edited_base_uses_top_right_origin():
    cfg = _cfg_2blocks(flipped=True)
    base = _base_records()
    base[0].new_x = 5.0  # effective C1 = (5, 20)
    recs = panelize_records(base, cfg)
    c1_block1 = recs[2]
    # X' = 200 - 5 = 195 ; Y' = 100 - 20 = 80
    assert c1_block1.old_x == pytest.approx(195.0)
    assert c1_block1.old_y == pytest.approx(80.0)
    assert c1_block1.new_x == pytest.approx(195.0)


def test_panelize_block0_flipped():
    cfg = PanelConfig(blocks=[
        PanelBlock(index=0, origin_x=0.0, origin_y=0.0, rotation=180),
        PanelBlock(index=1, origin_x=110.0, origin_y=0.0),
    ])
    recs = panelize_records(_base_records(), cfg)
    c1_block0 = recs[0]
    # rotating (10,20) by 180° around (0,0) -> (-10,-20)
    assert c1_block0.old_x == pytest.approx(-10.0)
    assert c1_block0.old_y == pytest.approx(-20.0)
    assert c1_block0.old_rotation == pytest.approx(180.0)


def test_config_serialize_roundtrip():
    cfg = PanelConfig(blocks=[
        PanelBlock(index=0, origin_x=0.0, origin_y=0.0),
        PanelBlock(index=1, origin_x=110.0, origin_y=5.0,
                   rotation=180, designator="sub1"),
    ])
    data = cfg.to_dict()
    restored = PanelConfig.from_dict(data)
    assert restored.count == 2
    b1 = restored.block_by_index(1)
    assert (b1.origin_x, b1.origin_y) == (110.0, 5.0)
    assert b1.rotation == 180
    assert b1.designator == "sub1"


def _base_pickplace():
    return PickPlaceData(
        headers=["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
        components=[
            PickPlaceComponent(designator="C1", mpn="M1", layer="Top", x=10, y=20, rotation=0),
            PickPlaceComponent(designator="C2", mpn="M2", layer="Top", x=30, y=40, rotation=90),
        ],
        raw_data=[
            {"Designator": "C1", "MPN": "M1", "Layer": "Top", "X": 10, "Y": 20, "Rotation": 0},
            {"Designator": "C2", "MPN": "M2", "Layer": "Top", "X": 30, "Y": 40, "Rotation": 90},
        ],
    )


def test_export_panelized_keeps_names_and_adds_block(tmp_path):
    cfg = PanelConfig(blocks=[
        PanelBlock(index=0, origin_x=0.0, origin_y=0.0),
        PanelBlock(index=1, origin_x=200.0, origin_y=100.0, rotation=180),
        PanelBlock(index=2, origin_x=0.0, origin_y=90.0),
        PanelBlock(index=3, origin_x=110.0, origin_y=90.0),
    ])
    recs = panelize_records(_base_records(), cfg)
    path = tmp_path / "panel.csv"
    ExportService.export_pickplace_fixed(recs, _base_pickplace(), str(path))
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 8
    # block 0, C1: original coords
    assert rows[0][0] == "C1"
    assert rows[0][2] == "10"
    assert rows[0][5] == ""
    # block 1 (flipped, origin (200,100)) C1: (190, 80), rotation 180, block=1
    row_b1_c1 = rows[2]
    assert row_b1_c1[0] == "C1_2"
    assert row_b1_c1[2] == "190.0"
    assert row_b1_c1[3] == "80.0"
    assert row_b1_c1[4] == "180.0"
    assert row_b1_c1[5] == "1"
    # block 2 C2: origin (0,90) unrotated -> (30,130), renamed C2_3
    row_b2_c2 = rows[5]
    assert row_b2_c2[0] == "C2_3"
    assert row_b2_c2[2] == "30.0"
    assert row_b2_c2[3] == "130.0"
    assert row_b2_c2[5] == "2"
    # block 3 keeps its block index and is renamed C2_4
    assert rows[7][0] == "C2_4"
    assert rows[7][5] == "3"


def test_review_repo_block_round_trip(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "panel.db"))
    monkeypatch.setattr(Database, "_instance", db)
    repo = ReviewRepo()
    rec = ReviewRecord(
        designator="C1", layer="Top", old_x=1.0, old_y=2.0,
        block=2, block_rotation=180,
    )
    rec.id = repo.insert(rec)
    loaded = repo.get_all()[0]
    assert loaded.block == 2
    assert loaded.block_rotation == 180
    loaded.block_rotation = 0
    repo.update(loaded)
    assert repo.get_by_id(loaded.id).block_rotation == 0
    # default block when absent
    plain = ReviewRecord(designator="R1", layer="Top", old_x=3.0, old_y=4.0)
    plain.id = repo.insert(plain)
    assert repo.get_by_id(plain.id).block == 0


def test_database_migrates_block_columns(tmp_path):
    import sqlite3
    path = str(tmp_path / "migrate.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE review (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            designator TEXT NOT NULL,
            mpn TEXT DEFAULT '',
            layer TEXT DEFAULT '',
            old_x REAL DEFAULT 0.0,
            old_y REAL DEFAULT 0.0,
            old_rotation REAL DEFAULT 0.0,
            new_x REAL, new_y REAL, new_rotation REAL,
            status TEXT DEFAULT 'Pending',
            remark TEXT DEFAULT '', review_time TEXT,
            datasheet TEXT DEFAULT '', checked INTEGER DEFAULT 0,
            row_index INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()
    db = Database(path)
    columns = {row["name"] for row in db.fetchall("PRAGMA table_info(review)")}
    assert "block" in columns
    assert "block_rotation" in columns


@pytest.fixture(scope="module")
def qapp():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_panelize_dialog_defaults_and_accept(qapp):
    from PySide6.QtCore import Qt
    from ui.panelize_dialog import PanelizeDialog
    dlg = PanelizeDialog(_base_records())
    assert dlg._config.count == 1
    assert dlg.panel_config is None
    assert dlg._spin_count.value() == 1
    assert dlg._origins_table.rowCount() == 1
    assert dlg._origins_table.item(0, 0).text() == "B1"
    assert dlg._origins_table.item(0, 1).text() == "0.0000"
    # block 1 origin is locked
    assert not (dlg._origins_table.item(0, 1).flags() & Qt.ItemIsEditable)
    dlg._on_accept()
    assert dlg.panel_config is not None
    assert dlg.panel_config.count == 1
    dlg.close()


def test_panelize_dialog_count_and_origin_edit(qapp):
    from ui.panelize_dialog import PanelizeDialog
    dlg = PanelizeDialog(_base_records())
    dlg._spin_count.setValue(2)
    assert dlg._config.count == 2
    assert dlg._origins_table.rowCount() == 2
    dlg._origins_table.item(1, 1).setText("110.5")
    assert dlg._config.block_by_index(1).origin_x == pytest.approx(110.5)
    dlg._origins_table.item(1, 2).setText("not-a-number")
    assert dlg._origins_table.item(1, 2).text() == "0.0000"
    assert dlg._config.block_by_index(1).origin_y == pytest.approx(0.0)
    dlg.close()


def test_panelize_dialog_block_click_toggles(qapp):
    from ui.panelize_dialog import PanelizeDialog
    dlg = PanelizeDialog([], config=_cfg_2blocks(flipped=False))
    assert dlg._config.block_by_index(1).rotation == 0
    dlg._on_block_clicked(1)
    assert dlg._config.block_by_index(1).rotation == 180
    dlg._on_block_clicked(1)
    assert dlg._config.block_by_index(1).rotation == 0
    dlg.close()


def test_panelize_dialog_preview_matches_service(qapp):
    from ui.panelize_dialog import PanelizeDialog
    dlg = PanelizeDialog(_base_records(), config=_cfg_2blocks(flipped=True))
    dlg._refresh_preview()
    rows = dlg._preview_rows()
    assert len(rows) == 2 * 2  # 2 sample records x 2 blocks
    # block 2 of C1 flipped around its origin (200,100): C1 -> (190, 80), rot 180
    assert rows[2] == ("C1_2", 1, pytest.approx(190.0), pytest.approx(80.0), 180.0)
    # accept produces the same coords the service would emit
    dlg._on_accept()
    assert dlg.panel_config.to_dict() == dlg._config.to_dict()
    dlg.close()


def test_panelize_dialog_flip_needs_no_extra_input(qapp, monkeypatch):
    from ui.panelize_dialog import PanelizeDialog
    # bare origins + one flipped block, no pitch/size/detect anywhere
    dlg = PanelizeDialog(_base_records(), config=_cfg_2blocks(flipped=True))
    monkeypatch.setattr(dlg, "accept", lambda: None)
    dlg._on_accept()
    assert dlg.panel_config is not None
    assert dlg.panel_config.block_by_index(1).rotation == 180
    dlg.close()


def test_panelize_dialog_rejects_no_records(qapp, monkeypatch):
    from ui.panelize_dialog import PanelizeDialog
    warnings = []

    class _FakeMB:
        def __init__(self, *a, **k):
            pass

        @staticmethod
        def warning(parent, title, text):
            warnings.append(text)

    monkeypatch.setattr("ui.panelize_dialog.QMessageBox", _FakeMB)
    dlg = PanelizeDialog([])
    monkeypatch.setattr(dlg, "accept", lambda: None)
    dlg._on_accept()
    assert warnings
    assert dlg.panel_config is None
    dlg.close()


def test_panelize_dialog_detect_fills_origins(qapp, monkeypatch):
    from ui.panelize_dialog import PanelizeDialog
    from services.gerber.panel_detector import BoardInstance, PanelInfo

    info = PanelInfo(
        kind="A", nx=2, ny=1, dx_mm=110.0, dy_mm=0.0,
        panel_origin=(500.0, 200.0), panel_w=230.0, panel_h=80.0,
        instances=[
            BoardInstance(origin=(500.0, 200.0), w=100.0, h=80.0, sub_name="s1", k=0),
            BoardInstance(origin=(610.0, 200.0), w=100.0, h=80.0, sub_name="s1", k=1),
        ],
    )
    monkeypatch.setattr("ui.panelize_dialog.detect_panel", lambda path: info)
    dlg = PanelizeDialog(_base_records(), gko_path="panel.gko")
    dlg._detect_from_gko()
    assert dlg._config.count == 2
    assert dlg._config.block_by_index(0).origin_x == 0.0
    assert dlg._config.block_by_index(0).origin_y == 0.0
    assert dlg._config.block_by_index(1).origin_x == pytest.approx(110.0)
    assert dlg._config.block_by_index(1).origin_y == pytest.approx(0.0)
    assert dlg._origins_table.rowCount() == 2
    assert dlg._spin_count.value() == 2
    dlg.close()


def test_panelize_dialog_detect_keeps_flip_flags(qapp, monkeypatch):
    from ui.panelize_dialog import PanelizeDialog
    from services.gerber.panel_detector import BoardInstance, PanelInfo

    info = PanelInfo(
        kind="B",
        instances=[
            BoardInstance(origin=(0.0, 0.0), w=100.0, h=60.0, k=0),
            BoardInstance(origin=(110.0, 0.0), w=100.0, h=60.0, k=1),
        ],
    )
    monkeypatch.setattr("ui.panelize_dialog.detect_panel", lambda path: info)
    dlg = PanelizeDialog(_base_records(), gko_path="panel.gko")
    # build a 2-block config in advance with block 2 flipped
    cfg = PanelConfig(blocks=[
        PanelBlock(index=0, origin_x=0.0, origin_y=0.0),
        PanelBlock(index=1, origin_x=0.0, origin_y=0.0, rotation=180),
    ])
    dlg._config = cfg
    dlg._sync_widgets_from_config()
    dlg._detect_from_gko()
    assert dlg._config.block_by_index(1).rotation == 180
    assert dlg._config.block_by_index(1).origin_x == pytest.approx(110.0)
    dlg.close()


def test_panelize_dialog_detect_single_board_keeps_config(qapp, monkeypatch):
    from ui.panelize_dialog import PanelizeDialog
    from services.gerber.panel_detector import BoardInstance, PanelInfo
    warnings = []

    class _FakeMB:
        def __init__(self, *a, **k):
            pass

        @staticmethod
        def information(parent, title, text):
            warnings.append(text)

    info = PanelInfo(kind="single", instances=[BoardInstance(origin=(0.0, 0.0), w=100.0, h=80.0)])
    monkeypatch.setattr("ui.panelize_dialog.detect_panel", lambda path: info)
    monkeypatch.setattr("ui.panelize_dialog.QMessageBox", _FakeMB)
    dlg = PanelizeDialog(_base_records(), gko_path="board.gko")
    before = dlg._config.to_dict()
    dlg._detect_from_gko()
    assert dlg._config.to_dict() == before
    assert warnings
    dlg.close()

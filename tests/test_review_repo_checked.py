import sqlite3

import pytest

from database.database import Database
from database.review_repo import ReviewRepo
from models.review import ReviewRecord


def test_review_repo_checked_round_trip(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "test.db"))
    monkeypatch.setattr(Database, "_instance", db)
    repo = ReviewRepo()

    rec = ReviewRecord(designator="C1", layer="Top", old_x=1.0, old_y=2.0)
    rec.checked = True
    rec.id = repo.insert(rec)

    loaded = repo.get_all()[0]
    assert loaded.checked is True

    loaded.checked = False
    repo.update(loaded)
    assert repo.get_all()[0].checked is False


def test_database_migrates_checked_column(tmp_path):
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
            new_x REAL,
            new_y REAL,
            new_rotation REAL,
            status TEXT DEFAULT 'Pending',
            remark TEXT DEFAULT '',
            review_time TEXT,
            datasheet TEXT DEFAULT '',
            row_index INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    columns = {row["name"] for row in db.fetchall("PRAGMA table_info(review)")}
    assert "checked" in columns
    assert "is_ic_rotation" in columns


def test_review_repo_ic_rotation_round_trip(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "ic.db"))
    monkeypatch.setattr(Database, "_instance", db)
    repo = ReviewRepo()

    rec = ReviewRecord(designator="U1", layer="Top",
                       old_x=1.0, old_y=2.0, new_rotation=270.0,
                       is_ic_rotation=True)
    rec.id = repo.insert(rec)

    loaded = repo.get_all()[0]
    assert loaded.is_ic_rotation is True

    # Legacy rows (flag absent at insert time) default to False
    plain = ReviewRecord(designator="R1", layer="Top", old_x=3.0, old_y=4.0)
    plain.id = repo.insert(plain)
    assert repo.get_by_id(plain.id).is_ic_rotation is False

    # Update clears the flag
    loaded.is_ic_rotation = False
    repo.update(loaded)
    assert repo.get_by_id(loaded.id).is_ic_rotation is False
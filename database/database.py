import sqlite3
import os
import shutil
from typing import Optional

from utils.path_utils import user_data_dir


class Database:
    _instance: Optional["Database"] = None

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            db_dir = user_data_dir()
            db_path = os.path.join(db_dir, "cam350_review.db")
            self._migrate_legacy(db_path)
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    @staticmethod
    def _migrate_legacy(new_path: str) -> None:
        if os.path.exists(new_path):
            return
        legacy = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "cam350_review.db"
        )
        if os.path.exists(legacy):
            try:
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                shutil.copyfile(legacy, new_path)
            except IOError:
                pass

    @staticmethod
    def instance() -> "Database":
        if Database._instance is None:
            Database._instance = Database()
        return Database._instance

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review (
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
        self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(review)")
        columns = {row[1] for row in cursor.fetchall()}
        if "datasheet" not in columns:
            conn.execute("ALTER TABLE review ADD COLUMN datasheet TEXT DEFAULT ''")
            conn.commit()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = self._get_connection()
        try:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor
        except sqlite3.Error as e:
            raise RuntimeError(f"Database error: {e}")

    def fetchone(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(query, params)
            return cursor.fetchone()
        except sqlite3.Error as e:
            raise RuntimeError(f"Database error: {e}")

    def fetchall(self, query: str, params: tuple = ()) -> list:
        conn = self._get_connection()
        try:
            cursor = conn.execute(query, params)
            return cursor.fetchall()
        except sqlite3.Error as e:
            raise RuntimeError(f"Database error: {e}")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def db_path(self) -> str:
        return self._db_path

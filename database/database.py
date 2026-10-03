import sqlite3
import os
import shutil
from contextlib import contextmanager
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
                checked INTEGER DEFAULT 0,
                row_index INTEGER DEFAULT 0,
                is_ic_rotation INTEGER DEFAULT 0,
                block INTEGER DEFAULT 0,
                block_rotation INTEGER DEFAULT 0,
                base_designator TEXT DEFAULT ''
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
        if "checked" not in columns:
            conn.execute("ALTER TABLE review ADD COLUMN checked INTEGER DEFAULT 0")
            conn.commit()
        if "is_ic_rotation" not in columns:
            conn.execute(
                "ALTER TABLE review ADD COLUMN is_ic_rotation INTEGER DEFAULT 0"
            )
            conn.commit()
        if "block" not in columns:
            conn.execute("ALTER TABLE review ADD COLUMN block INTEGER DEFAULT 0")
            conn.commit()
        if "block_rotation" not in columns:
            conn.execute(
                "ALTER TABLE review ADD COLUMN block_rotation INTEGER DEFAULT 0"
            )
            conn.commit()
        if "base_designator" not in columns:
            conn.execute(
                "ALTER TABLE review ADD COLUMN base_designator TEXT DEFAULT ''"
            )
            conn.commit()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS component_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                designator TEXT NOT NULL,
                block INTEGER DEFAULT 0,
                action TEXT DEFAULT '',
                old_x REAL,
                old_y REAL,
                old_rotation REAL,
                new_x REAL,
                new_y REAL,
                new_rotation REAL,
                remark TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hist_des
            ON component_history(designator, block, id DESC)
            """
        )
        conn.commit()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pcb_info (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                board_width REAL DEFAULT 0,
                board_height REAL DEFAULT 0,
                working_area_width REAL DEFAULT 0,
                position_working REAL DEFAULT 0,
                x_boc1 REAL DEFAULT 0,
                y_boc1 REAL DEFAULT 0,
                x_boc2 REAL DEFAULT 0,
                y_boc2 REAL DEFAULT 0,
                x_boc3 REAL DEFAULT 0,
                y_boc3 REAL DEFAULT 0,
                thickness REAL DEFAULT 1.6
            )
            """
        )
        conn.commit()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = self._get_connection()
        try:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor
        except sqlite3.Error as e:
            raise RuntimeError(f"Database error: {e}")

    @contextmanager
    def transaction(self):
        """Batch many writes into a single commit.

        Commits once on clean exit; rolls back on any exception so partial
        batches never persist.
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute_many(self, query: str, seq_of_params) -> None:
        conn = self._get_connection()
        try:
            with self.transaction() as conn:
                conn.executemany(query, list(seq_of_params))
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

from typing import List

from database.database import Database
from models.history import HistoryEntry


class HistoryRepo:
    def __init__(self) -> None:
        self._db = Database.instance()

    @staticmethod
    def _entry_params(entry: HistoryEntry) -> tuple:
        return (
            entry.designator,
            entry.block,
            entry.action,
            entry.old_x,
            entry.old_y,
            entry.old_rotation,
            entry.new_x,
            entry.new_y,
            entry.new_rotation,
            entry.mpn_old,
            entry.mpn_new,
            entry.remark,
            entry.created_at,
        )

    def add(self, entry: HistoryEntry) -> int:
        cursor = self._db.execute(
            """
            INSERT INTO component_history
                (designator, block, action, old_x, old_y, old_rotation,
                 new_x, new_y, new_rotation, mpn_old, mpn_new, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._entry_params(entry),
        )
        return cursor.lastrowid or 0

    def add_many(self, entries) -> None:
        """Insert many history rows in one transaction/commit."""
        entries = list(entries)
        if not entries:
            return
        self._db.execute_many(
            """
            INSERT INTO component_history
                (designator, block, action, old_x, old_y, old_rotation,
                 new_x, new_y, new_rotation, mpn_old, mpn_new, remark, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [self._entry_params(entry) for entry in entries],
        )

    def list_by(self, designator: str, block: int = 0, limit: int = 100) -> List[HistoryEntry]:
        rows = self._db.fetchall(
            """
            SELECT * FROM component_history
            WHERE designator=? AND block=?
            ORDER BY id DESC LIMIT ?
            """,
            (designator, block, limit),
        )
        return [self._row_to_entry(r) for r in rows]

    def get_all(self, limit: int = 5000) -> List[HistoryEntry]:
        rows = self._db.fetchall(
            "SELECT * FROM component_history ORDER BY id ASC LIMIT ?", (limit,)
        )
        return [self._row_to_entry(r) for r in rows]

    def clear_all(self) -> None:
        self._db.execute("DELETE FROM component_history")
        self._db.execute("DELETE FROM sqlite_sequence WHERE name='component_history'")

    @staticmethod
    def _row_to_entry(row) -> HistoryEntry:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        return HistoryEntry(
            id=row["id"],
            designator=row["designator"],
            block=int(row["block"] or 0),
            action=row["action"] or "",
            old_x=row["old_x"],
            old_y=row["old_y"],
            old_rotation=row["old_rotation"],
            new_x=row["new_x"],
            new_y=row["new_y"],
            new_rotation=row["new_rotation"],
            mpn_old=row["mpn_old"] if "mpn_old" in keys and row["mpn_old"] else "",
            mpn_new=row["mpn_new"] if "mpn_new" in keys and row["mpn_new"] else "",
            remark=row["remark"] or "",
            created_at=row["created_at"] or "",
        )

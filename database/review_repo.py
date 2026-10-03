from typing import List, Optional

from database.database import Database
from models.review import ReviewRecord


class ReviewRepo:
    def __init__(self) -> None:
        self._db = Database.instance()

    def insert(self, record: ReviewRecord) -> int:
        cursor = self._db.execute(
            """
            INSERT INTO review (designator, mpn, layer, old_x, old_y, old_rotation,
                                new_x, new_y, new_rotation, status, remark, review_time, datasheet, checked, row_index,
                                is_ic_rotation, block, block_rotation, base_designator)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.designator,
                record.mpn,
                record.layer,
                record.old_x,
                record.old_y,
                record.old_rotation,
                record.new_x,
                record.new_y,
                record.new_rotation,
                record.status,
                record.remark,
                record.review_time,
                record.datasheet,
                1 if record.checked else 0,
                record.row_index,
                1 if record.is_ic_rotation else 0,
                record.block,
                record.block_rotation,
                record.base_designator,
            ),
        )
        return cursor.lastrowid or 0

    def update(self, record: ReviewRecord) -> None:
        self._db.execute(
            """
            UPDATE review SET mpn=?, layer=?, old_x=?, old_y=?, old_rotation=?,
                              new_x=?, new_y=?, new_rotation=?, status=?, remark=?,
                              review_time=?, datasheet=?, checked=?, is_ic_rotation=?,
                              block=?, block_rotation=?, base_designator=?
            WHERE id=?
            """,
            self._update_params(record),
        )

    @staticmethod
    def _update_params(record: ReviewRecord) -> tuple:
        return (
            record.mpn,
            record.layer,
            record.old_x,
            record.old_y,
            record.old_rotation,
            record.new_x,
            record.new_y,
            record.new_rotation,
            record.status,
            record.remark,
            record.review_time,
            record.datasheet,
            1 if record.checked else 0,
            1 if record.is_ic_rotation else 0,
            record.block,
            record.block_rotation,
            record.base_designator,
            record.id,
        )

    def update_many(self, records) -> None:
        """Persist many records in a single transaction/commit."""
        records = list(records)
        if not records:
            return
        self._db.execute_many(
            """
            UPDATE review SET mpn=?, layer=?, old_x=?, old_y=?, old_rotation=?,
                              new_x=?, new_y=?, new_rotation=?, status=?, remark=?,
                              review_time=?, datasheet=?, checked=?, is_ic_rotation=?,
                              block=?, block_rotation=?, base_designator=?
            WHERE id=?
            """,
            [self._update_params(r) for r in records],
        )

    def get_by_id(self, record_id: int) -> Optional[ReviewRecord]:
        row = self._db.fetchone("SELECT * FROM review WHERE id=?", (record_id,))
        if row is None:
            return None
        return self._row_to_record(row)

    def get_all(self) -> List[ReviewRecord]:
        rows = self._db.fetchall("SELECT * FROM review ORDER BY row_index ASC")
        return [self._row_to_record(r) for r in rows]

    def get_pending(self) -> List[ReviewRecord]:
        rows = self._db.fetchall(
            "SELECT * FROM review WHERE status='Pending' ORDER BY row_index ASC"
        )
        return [self._row_to_record(r) for r in rows]

    def delete_by_id(self, record_id: int) -> None:
        self._db.execute("DELETE FROM review WHERE id=?", (record_id,))

    def delete_all(self) -> None:
        self._db.execute("DELETE FROM review")
        self._db.execute("DELETE FROM sqlite_sequence WHERE name='review'")

    def count_by_status(self, status: str) -> int:
        row = self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM review WHERE status=?", (status,)
        )
        return row["cnt"] if row else 0

    def total_count(self) -> int:
        row = self._db.fetchone("SELECT COUNT(*) as cnt FROM review")
        return row["cnt"] if row else 0

    def get_last_review_id(self) -> int:
        row = self._db.fetchone(
            "SELECT id FROM review ORDER BY id DESC LIMIT 1"
        )
        return row["id"] if row else 0

    @staticmethod
    def _row_to_record(row) -> ReviewRecord:
        return ReviewRecord(
            id=row["id"],
            designator=row["designator"],
            mpn=row["mpn"],
            layer=row["layer"],
            old_x=row["old_x"],
            old_y=row["old_y"],
            old_rotation=row["old_rotation"],
            new_x=row["new_x"],
            new_y=row["new_y"],
            new_rotation=row["new_rotation"],
            status=row["status"],
            remark=row["remark"],
            review_time=row["review_time"],
            datasheet=row["datasheet"],
            checked=bool(row["checked"]),
            row_index=row["row_index"],
            is_ic_rotation=bool(row["is_ic_rotation"]),
            block=int(row["block"] or 0),
            block_rotation=int(row["block_rotation"] or 0),
            base_designator=row["base_designator"] or "",
        )

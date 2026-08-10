from typing import Optional

from database.database import Database
from models.pcb_info import PcbInfo


class PcbInfoRepo:
    def __init__(self) -> None:
        self._db = Database.instance()

    def load(self) -> PcbInfo:
        row = self._db.fetchone("SELECT * FROM pcb_info WHERE id=1")
        if row is None:
            return PcbInfo()
        return PcbInfo(
            board_width=row["board_width"] or 0.0,
            board_height=row["board_height"] or 0.0,
            working_area_width=row["working_area_width"] or 0.0,
            position_working=float(row["position_working"] or 0.0),
            x_boc1=row["x_boc1"] or 0.0,
            y_boc1=row["y_boc1"] or 0.0,
            x_boc2=row["x_boc2"] or 0.0,
            y_boc2=row["y_boc2"] or 0.0,
            x_boc3=row["x_boc3"] or 0.0,
            y_boc3=row["y_boc3"] or 0.0,
            thickness=row["thickness"] or 1.6,
        )

    def save(self, pcb: PcbInfo) -> None:
        self._db.execute(
            """
            INSERT INTO pcb_info (
                id, board_width, board_height, working_area_width, position_working,
                x_boc1, y_boc1, x_boc2, y_boc2, x_boc3, y_boc3, thickness
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                board_width=excluded.board_width,
                board_height=excluded.board_height,
                working_area_width=excluded.working_area_width,
                position_working=excluded.position_working,
                x_boc1=excluded.x_boc1,
                y_boc1=excluded.y_boc1,
                x_boc2=excluded.x_boc2,
                y_boc2=excluded.y_boc2,
                x_boc3=excluded.x_boc3,
                y_boc3=excluded.y_boc3,
                thickness=excluded.thickness
            """,
            (
                pcb.board_width,
                pcb.board_height,
                pcb.working_area_width,
                pcb.position_working,
                pcb.x_boc1,
                pcb.y_boc1,
                pcb.x_boc2,
                pcb.y_boc2,
                pcb.x_boc3,
                pcb.y_boc3,
                pcb.thickness,
            ),
        )

    def clear(self) -> None:
        self._db.execute("DELETE FROM pcb_info WHERE id=1")
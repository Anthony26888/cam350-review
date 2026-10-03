from dataclasses import dataclass
from typing import Optional


@dataclass
class HistoryEntry:
    designator: str = ""
    block: int = 0
    action: str = ""
    old_x: Optional[float] = None
    old_y: Optional[float] = None
    old_rotation: Optional[float] = None
    new_x: Optional[float] = None
    new_y: Optional[float] = None
    new_rotation: Optional[float] = None
    remark: str = ""
    created_at: str = ""
    id: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "designator": self.designator,
            "block": self.block,
            "action": self.action,
            "old_x": self.old_x,
            "old_y": self.old_y,
            "old_rotation": self.old_rotation,
            "new_x": self.new_x,
            "new_y": self.new_y,
            "new_rotation": self.new_rotation,
            "remark": self.remark,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "HistoryEntry":
        return HistoryEntry(
            id=int(data.get("id", 0)),
            designator=data.get("designator", ""),
            block=int(data.get("block", 0) or 0),
            action=data.get("action", ""),
            old_x=data.get("old_x"),
            old_y=data.get("old_y"),
            old_rotation=data.get("old_rotation"),
            new_x=data.get("new_x"),
            new_y=data.get("new_y"),
            new_rotation=data.get("new_rotation"),
            remark=data.get("remark", "") or "",
            created_at=data.get("created_at", "") or "",
        )

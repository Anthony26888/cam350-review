from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ReviewRecord:
    designator: str = ""
    mpn: str = ""
    layer: str = ""
    old_x: float = 0.0
    old_y: float = 0.0
    old_rotation: float = 0.0
    new_x: Optional[float] = None
    new_y: Optional[float] = None
    new_rotation: Optional[float] = None
    status: str = "Pending"
    remark: str = ""
    review_time: Optional[str] = None
    datasheet: str = ""
    id: int = 0
    row_index: int = 0

    @property
    def needs_edit(self) -> bool:
        return self.status == "Edited"

    @property
    def is_ok(self) -> bool:
        return self.status == "OK"

    @property
    def is_pending(self) -> bool:
        return self.status == "Pending"

    @property
    def has_modifications(self) -> bool:
        return (
            self.new_x is not None
            or self.new_y is not None
            or self.new_rotation is not None
        )

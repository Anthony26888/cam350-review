from dataclasses import dataclass, field
from typing import List


@dataclass
class BomRow:
    stt: int = 0
    designator_raw: str = ""
    designator_display: str = ""
    designators: List[str] = field(default_factory=list)
    mpn: str = ""
    description: str = ""
    quantity: int = 0
    quantity_raw: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "stt": self.stt,
            "designator_raw": self.designator_raw,
            "designator_display": self.designator_display,
            "designators": list(self.designators),
            "mpn": self.mpn,
            "description": self.description,
            "quantity": self.quantity,
            "quantity_raw": self.quantity_raw,
            "note": self.note,
        }

    @staticmethod
    def from_dict(data: dict) -> "BomRow":
        return BomRow(
            stt=int(data.get("stt", 0) or 0),
            designator_raw=data.get("designator_raw", "") or "",
            designator_display=data.get("designator_display", "") or "",
            designators=list(data.get("designators") or []),
            mpn=data.get("mpn", "") or "",
            description=data.get("description", "") or "",
            quantity=int(data.get("quantity", 0) or 0),
            quantity_raw=data.get("quantity_raw", "") or "",
            note=data.get("note", "") or "",
        )

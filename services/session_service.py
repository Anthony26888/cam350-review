import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from models.review import ReviewRecord


SESSION_VERSION = 1


class SessionData:
    def __init__(self) -> None:
        self.version: int = SESSION_VERSION
        self.source_file: str = ""
        self.current_index: int = 0
        self.records: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "source_file": self.source_file,
            "current_index": self.current_index,
            "records": self.records,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SessionData":
        obj = SessionData()
        obj.version = data.get("version", SESSION_VERSION)
        obj.source_file = data.get("source_file", "")
        obj.current_index = data.get("current_index", 0)
        obj.records = data.get("records", [])
        return obj


class SessionService:

    @staticmethod
    def records_to_list(records: List[ReviewRecord]) -> List[Dict[str, Any]]:
        result = []
        for r in records:
            result.append({
                "id": r.id,
                "designator": r.designator,
                "mpn": r.mpn,
                "layer": r.layer,
                "old_x": r.old_x,
                "old_y": r.old_y,
                "old_rotation": r.old_rotation,
                "new_x": r.new_x,
                "new_y": r.new_y,
                "new_rotation": r.new_rotation,
                "status": r.status,
                "remark": r.remark,
                "review_time": r.review_time,
                "row_index": r.row_index,
            })
        return result

    @staticmethod
    def list_to_records(data: List[Dict[str, Any]]) -> List[ReviewRecord]:
        records = []
        for item in data:
            records.append(ReviewRecord(
                id=item.get("id", 0),
                designator=item.get("designator", ""),
                mpn=item.get("mpn", ""),
                layer=item.get("layer", ""),
                old_x=item.get("old_x", 0.0),
                old_y=item.get("old_y", 0.0),
                old_rotation=item.get("old_rotation", 0.0),
                new_x=item.get("new_x"),
                new_y=item.get("new_y"),
                new_rotation=item.get("new_rotation"),
                status=item.get("status", "Pending"),
                remark=item.get("remark", ""),
                review_time=item.get("review_time"),
                row_index=item.get("row_index", 0),
            ))
        return records

    @staticmethod
    def save(
        file_path: str,
        records: List[ReviewRecord],
        source_file: str = "",
        current_index: int = 0,
    ) -> None:
        data = SessionData()
        data.source_file = source_file
        data.current_index = current_index
        data.records = SessionService.records_to_list(records)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data.to_dict(), f, indent=2, ensure_ascii=False)

    @staticmethod
    def load(file_path: str) -> SessionData:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Session file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        return SessionData.from_dict(raw)

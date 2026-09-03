import base64
import json
import os
import zlib
from datetime import datetime
from typing import List, Optional, Dict, Any

from models.review import ReviewRecord


SESSION_VERSION = 5


def compress_text(text: str) -> str:
    return base64.b64encode(zlib.compress(text.encode("utf-8"), 9)).decode("ascii")


def decompress_text(payload: str) -> str:
    return zlib.decompress(base64.b64decode(payload.encode("ascii"))).decode("utf-8")


class SessionData:
    def __init__(self) -> None:
        self.version: int = SESSION_VERSION
        self.source_file: str = ""
        self.current_index: int = 0
        self.records: List[Dict[str, Any]] = []
        self.pcb_info: Optional[Dict[str, Any]] = None
        self.gerberGko: str = ""
        self.gerberGtp: str = ""
        self.gerberGbp: str = ""
        self.gerberGto: str = ""
        self.gerberGbo: str = ""
        self.gerber_view: Optional[Dict[str, Any]] = None
        self.column_mapping: Optional[Dict[str, str]] = None
        self.gerber_files: Optional[Dict[str, str]] = None
        self.prescreen_dismissed: List[str] = []
        self.prescreen_ctx: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "source_file": self.source_file,
            "current_index": self.current_index,
            "records": self.records,
            "pcb_info": self.pcb_info,
            "gerberGko": self.gerberGko,
            "gerberGtp": self.gerberGtp,
            "gerberGbp": self.gerberGbp,
            "gerberGto": self.gerberGto,
            "gerberGbo": self.gerberGbo,
            "gerber_view": self.gerber_view,
            "column_mapping": self.column_mapping,
            "gerber_files": self.gerber_files,
            "prescreen_dismissed": self.prescreen_dismissed,
            "prescreen_ctx": self.prescreen_ctx,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SessionData":
        obj = SessionData()
        obj.version = data.get("version", SESSION_VERSION)
        obj.source_file = data.get("source_file", "")
        obj.current_index = data.get("current_index", 0)
        obj.records = data.get("records", [])
        obj.pcb_info = data.get("pcb_info")
        obj.gerberGko = data.get("gerberGko", "")
        obj.gerberGtp = data.get("gerberGtp", "")
        obj.gerberGbp = data.get("gerberGbp", "")
        obj.gerberGto = data.get("gerberGto", "")
        obj.gerberGbo = data.get("gerberGbo", "")
        obj.gerber_view = data.get("gerber_view") or None
        obj.column_mapping = data.get("column_mapping") or None
        obj.gerber_files = data.get("gerber_files") or None
        obj.prescreen_dismissed = list(data.get("prescreen_dismissed") or [])
        obj.prescreen_ctx = data.get("prescreen_ctx") or None
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
                "datasheet": r.datasheet,
                "checked": r.checked,
                "row_index": r.row_index,
                "is_ic_rotation": bool(r.is_ic_rotation),
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
                datasheet=item.get("datasheet", ""),
                checked=bool(item.get("checked", False)),
                row_index=item.get("row_index", 0),
                is_ic_rotation=bool(item.get("is_ic_rotation", False)),
            ))
        return records

    @staticmethod
    def save(
        file_path: str,
        records: List[ReviewRecord],
        source_file: str = "",
        current_index: int = 0,
        pcb_info: Optional[Dict[str, Any]] = None,
        gerberGko: str = "",
        gerberGtp: str = "",
        gerberGbp: str = "",
        gerberGto: str = "",
        gerberGbo: str = "",
        gerber_view: Optional[Dict[str, Any]] = None,
        column_mapping: Optional[Dict[str, str]] = None,
        gerber_files: Optional[Dict[str, str]] = None,
        prescreen_dismissed: Optional[List[str]] = None,
        prescreen_ctx: Optional[Dict[str, Any]] = None,
    ) -> None:
        data = SessionData()
        data.source_file = source_file
        data.current_index = current_index
        data.records = SessionService.records_to_list(records)
        data.pcb_info = pcb_info
        data.gerberGko = gerberGko
        data.gerberGtp = gerberGtp
        data.gerberGbp = gerberGbp
        data.gerberGto = gerberGto
        data.gerberGbo = gerberGbo
        data.gerber_view = gerber_view
        data.column_mapping = column_mapping
        data.gerber_files = gerber_files
        data.prescreen_dismissed = list(prescreen_dismissed or [])
        data.prescreen_ctx = prescreen_ctx or None

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data.to_dict(), f, indent=2, ensure_ascii=False)

    @staticmethod
    def load(file_path: str) -> SessionData:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Session file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        return SessionData.from_dict(raw)

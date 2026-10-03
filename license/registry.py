import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

REGISTRY_FILENAME = "licenses.json"
DEFAULT_WARNING_DAYS = 30


def default_registry_path() -> Path:
    env = os.environ.get("CAM350_LICENSE_REGISTRY")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / REGISTRY_FILENAME
    here = Path(__file__).resolve().parent.parent
    return here / "secrets" / REGISTRY_FILENAME


def status_of(expiry: str, today: Optional[str] = None, warning_days: int = DEFAULT_WARNING_DAYS) -> str:
    today = today or date.today().isoformat()
    try:
        days_left = (date.fromisoformat(expiry) - date.fromisoformat(today)).days
    except (ValueError, TypeError):
        return "invalid"
    if days_left < 0:
        return "expired"
    if days_left <= warning_days:
        return "expiring"
    return "valid"


def days_left_of(expiry: str, today: Optional[str] = None) -> int:
    today = today or date.today().isoformat()
    try:
        return (date.fromisoformat(expiry) - date.fromisoformat(today)).days
    except (ValueError, TypeError):
        return 0


class LicenseRegistry:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or default_registry_path()
        self.data: Dict[str, Any] = {
            "warning_days": DEFAULT_WARNING_DAYS,
            "licenses": [],
        }
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if isinstance(data.get("licenses"), list):
                    self.data["licenses"] = data["licenses"]
                if isinstance(data.get("warning_days"), int):
                    self.data["warning_days"] = data["warning_days"]
        except (json.JSONDecodeError, IOError):
            pass

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            raise RuntimeError(f"Failed to save license registry: {e}")

    @property
    def warning_days(self) -> int:
        return int(self.data.get("warning_days", DEFAULT_WARNING_DAYS))

    @warning_days.setter
    def warning_days(self, value: int) -> None:
        self.data["warning_days"] = max(0, int(value))
        self.save()

    def all(self) -> List[Dict[str, Any]]:
        return self.data["licenses"]

    def find_by_hwid(self, hwid: str) -> Optional[Dict[str, Any]]:
        for lic in self.data["licenses"]:
            if lic.get("hwid") == hwid:
                return lic
        return None

    def find_by_id(self, lic_id: str) -> Optional[Dict[str, Any]]:
        for lic in self.data["licenses"]:
            if lic.get("id") == lic_id:
                return lic
        return None

    def add(self, hwid: str, customer: str, expiry: str, issued_at: Optional[str] = None,
            device: str = "", notes: str = "", key: str = "") -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "customer": customer,
            "device": device,
            "hwid": hwid,
            "issued_at": issued_at or datetime.now().isoformat(timespec="seconds"),
            "expiry": expiry,
            "notes": notes,
            "key": key,
            "renewals": [],
        }
        self.data["licenses"].append(record)
        self.save()
        return record

    def update(self, lic_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        record = self.find_by_id(lic_id)
        if record is None:
            return None
        for field in ("customer", "device", "hwid", "expiry", "notes", "key", "issued_at"):
            if field in kwargs:
                record[field] = kwargs[field]
        self.save()
        return record

    def delete(self, lic_id: str) -> bool:
        before = len(self.data["licenses"])
        self.data["licenses"] = [lic for lic in self.data["licenses"] if lic.get("id") != lic_id]
        removed = len(self.data["licenses"]) < before
        if removed:
            self.save()
        return removed

    def renew(self, lic_id: str, days: int, new_key: str,
              when: Optional[str] = None) -> Optional[Dict[str, Any]]:
        record = self.find_by_id(lic_id)
        if record is None:
            return None
        old_expiry = record.get("expiry", "")
        today = date.today().isoformat()
        base_date = today
        if when:
            try:
                base_date = date.fromisoformat(when[:10]).isoformat()
            except (ValueError, TypeError):
                base_date = today
        base = max(old_expiry, base_date) if old_expiry else base_date
        try:
            new_expiry = (date.fromisoformat(base) + timedelta(days=days)).isoformat()
        except (ValueError, TypeError):
            new_expiry = (date.fromisoformat(today) + timedelta(days=days)).isoformat()
        old_key = record.get("key", "")
        history: Dict[str, Any] = {
            "date": when or datetime.now().isoformat(timespec="seconds"),
            "days": days,
            "old_expiry": old_expiry,
            "new_expiry": new_expiry,
            "old_key": old_key,
            "new_key": new_key,
        }
        record.setdefault("renewals", []).append(history)
        record["expiry"] = new_expiry
        record["key"] = new_key
        self.save()
        return record
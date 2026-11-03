from datetime import date
import json
import os
import sys
from typing import Optional

if sys.platform == "win32":
    import winreg

from config.config_manager import ConfigManager
from utils.path_utils import user_data_dir

_REG_ROOT = winreg.HKEY_CURRENT_USER if sys.platform == "win32" else None
_REG_PATH = r"Software\CAM350Review"
_VAL_MAX_SEEN = "MaxSeenDate"
_VAL_HWID = "Hwid"
_STATE_FILE = "license_state.json"


def _state_path() -> str:
    return os.path.join(user_data_dir(), _STATE_FILE)


def _read_state() -> dict:
    try:
        with open(_state_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(data: dict) -> None:
    path = _state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(tmp, path)
    except OSError:
        pass


def save_license_key(key: str) -> None:
    ConfigManager.instance().update(licenseKey=key)


def load_license_key() -> str:
    return ConfigManager.instance().config.licenseKey or ""


def _reg_open():
    if _REG_ROOT is None:
        return None
    try:
        return winreg.CreateKey(_REG_ROOT, _REG_PATH)
    except OSError:
        return None


def save_hwid(hwid: str) -> None:
    if _REG_ROOT is None:
        state = _read_state()
        state[_VAL_HWID] = hwid
        _write_state(state)
        return
    key = _reg_open()
    if key is None:
        return
    try:
        winreg.SetValueEx(key, _VAL_HWID, 0, winreg.REG_SZ, hwid)
    except OSError:
        pass
    finally:
        winreg.CloseKey(key)


def get_max_seen_date() -> Optional[str]:
    if _REG_ROOT is None:
        value = _read_state().get(_VAL_MAX_SEEN)
        return str(value) if value else None
    key = _reg_open()
    if key is None:
        return None
    try:
        value, _ = winreg.QueryValueEx(key, _VAL_MAX_SEEN)
        return str(value)
    except OSError:
        return None
    finally:
        winreg.CloseKey(key)


def set_max_seen_date(day: str) -> None:
    if _REG_ROOT is None:
        state = _read_state()
        state[_VAL_MAX_SEEN] = day
        _write_state(state)
        return
    key = _reg_open()
    if key is None:
        return
    try:
        winreg.SetValueEx(key, _VAL_MAX_SEEN, 0, winreg.REG_SZ, day)
    except OSError:
        pass
    finally:
        winreg.CloseKey(key)


def is_clock_rollback(today: str, max_seen: Optional[str]) -> bool:
    if not max_seen:
        return False
    try:
        return today < max_seen
    except TypeError:
        return False


def update_max_seen(today: str) -> None:
    max_seen = get_max_seen_date()
    if max_seen is None or today > max_seen:
        set_max_seen_date(today)


def today_iso() -> str:
    return date.today().isoformat()

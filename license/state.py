from datetime import date
from typing import Optional

import winreg

from config.config_manager import ConfigManager

_REG_ROOT = winreg.HKEY_CURRENT_USER
_REG_PATH = r"Software\CAM350Review"
_VAL_MAX_SEEN = "MaxSeenDate"
_VAL_HWID = "Hwid"


def save_license_key(key: str) -> None:
    ConfigManager.instance().update(licenseKey=key)


def load_license_key() -> str:
    return ConfigManager.instance().config.licenseKey or ""


def _reg_open():
    try:
        return winreg.CreateKey(_REG_ROOT, _REG_PATH)
    except OSError:
        return None


def save_hwid(hwid: str) -> None:
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

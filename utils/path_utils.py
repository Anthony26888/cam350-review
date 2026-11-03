import sys
import os


def resource_path(relative_path: str) -> str:
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _legacy_data_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".cam350_review", "CAM350_Review")


def _data_dir_for_platform() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return os.path.join(base, "CAM350_Review")
        return _legacy_data_dir()
    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"), "Library", "Application Support",
            "CAM350_Review",
        )
    base = os.environ.get("XDG_DATA_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "CAM350_Review")


def user_data_dir() -> str:
    if sys.platform == "win32":
        path = _data_dir_for_platform()
    else:
        legacy = _legacy_data_dir()
        path = legacy if os.path.isdir(legacy) else _data_dir_for_platform()
    os.makedirs(path, exist_ok=True)
    return path

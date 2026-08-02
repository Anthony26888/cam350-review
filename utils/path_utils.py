import sys
import os


def resource_path(relative_path: str) -> str:
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def user_data_dir() -> str:
    base = os.environ.get("APPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".cam350_review")
    path = os.path.join(base, "CAM350_Review")
    os.makedirs(path, exist_ok=True)
    return path

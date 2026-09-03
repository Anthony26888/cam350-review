"""Lightweight always-on performance logging.

Appends one line per event to %APPDATA%/CAM350_Review/perf.log so slow
operations can be diagnosed from real user machines.
"""

import os
import time

from utils.path_utils import user_data_dir


def log_event(tag: str, base_dir: str = None, **fields) -> None:
    try:
        directory = base_dir if base_dir is not None else user_data_dir()
        path = os.path.join(directory, "perf.log")
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        parts = " ".join(f"{k}={v}" for k, v in fields.items())
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {tag} | {parts}\n")
    except OSError:
        pass


class Timer:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    def ms(self) -> int:
        return int(round((time.perf_counter() - self._t0) * 1000))

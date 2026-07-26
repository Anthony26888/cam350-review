import time
from typing import Optional

import pyautogui
import win32gui
import win32con


from config.config_manager import ConfigManager


class Cam350Controller:
    def __init__(self) -> None:
        self._config_mgr = ConfigManager.instance()
        self._hwnd: Optional[int] = None

    def _find_window(self) -> Optional[int]:
        title = self._config_mgr.config.windowTitle

        search_titles = []
        if title:
            search_titles.append(title)
        search_titles.append("CAM350")

        def enum_callback(hwnd: int, _: list) -> None:
            if self._hwnd is not None:
                return
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                for t in search_titles:
                    if t.lower() in window_text.lower():
                        self._hwnd = hwnd
                        return

        self._hwnd = None
        win32gui.EnumWindows(enum_callback, None)

        if self._hwnd is None:
            msg = f"CAM350 window not found"
            if title:
                msg += f" (searched for '{title}' and 'CAM350')"
            raise RuntimeError(f"{msg}. Is CAM350 running?")

        return self._hwnd

    @staticmethod
    def detect_window_title() -> str:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            return win32gui.GetWindowText(hwnd)
        return ""

    def is_running(self) -> bool:
        try:
            self._find_window()
            return self._hwnd is not None
        except RuntimeError:
            return False

    def activate(self) -> None:
        hwnd = self._find_window()
        if hwnd is None:
            return

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.2)

    def jump_to(self, x: float, y: float) -> None:
        config = self._config_mgr.config

        if not config.xTextbox.x or not config.yTextbox.x:
            raise RuntimeError("CAM350 not calibrated. Please run calibration first.")

        self.activate()
        time.sleep(0.1)

        pyautogui.click(config.xTextbox.x, config.xTextbox.y)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.write(str(x))
        time.sleep(0.05)

        pyautogui.press("tab")
        time.sleep(0.05)
        pyautogui.write(str(y))
        time.sleep(0.05)

        pyautogui.press("enter")
        time.sleep(config.delay / 1000.0)

    def test_jump(self) -> bool:
        config = self._config_mgr.config
        if not config.xTextbox.x or not config.yTextbox.x:
            return False

        if not self.is_running():
            return False

        try:
            self.activate()
            pyautogui.click(config.xTextbox.x, config.xTextbox.y)
            return True
        except Exception:
            return False

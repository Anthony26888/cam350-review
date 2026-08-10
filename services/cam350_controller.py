import ctypes
from ctypes import wintypes
import re
import time
from typing import Optional

import pyautogui
import win32gui
import win32con
import win32clipboard


from config.config_manager import ConfigManager

_NUMBER_RE = r"[-+]?\d+(?:\.\d+)?"
_WM_GETTEXTLENGTH = 0x000E
_WM_GETTEXT = 0x000D

_user32 = ctypes.windll.user32


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


_user32.WindowFromPoint.restype = wintypes.HWND
_user32.WindowFromPoint.argtypes = [_POINT]
_user32.SendMessageW.restype = ctypes.c_ssize_t
_user32.SendMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    ctypes.c_void_p,
]


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

        for _ in range(2):
            # Bypass the foreground-window lock by simulating an Alt press/release,
            # otherwise SetForegroundWindow from this process may be ignored.
            _user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
            try:
                try:
                    win32gui.SetForegroundWindow(hwnd)
                    win32gui.BringWindowToTop(hwnd)
                except Exception:
                    # SetForegroundWindow may fail under the foreground lock;
                    # keep trying best-effort on the next iteration.
                    pass
            finally:
                # Always release Alt so a failed activation can never leave
                # the key held down (which would break every later hotkey).
                _user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.15)
            if win32gui.GetForegroundWindow() == hwnd:
                break

        if win32gui.GetForegroundWindow() != hwnd:
            raise RuntimeError(
                "Không thể kích hoạt cửa sổ CAM350. Vui lòng đưa CAM350 lên foreground rồi thử lại."
            )

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

    def read_value(self, axis: str) -> float:
        """Read the coordinate from the calibrated X/Y textbox in CAM350."""
        config = self._config_mgr.config
        pos = config.xTextbox if axis == "x" else config.yTextbox
        if not pos.x or not pos.y:
            raise RuntimeError(
                "CAM350 not calibrated. Please run calibration first."
            )

        self.activate()
        time.sleep(0.15)
        pyautogui.click(pos.x, pos.y)
        time.sleep(0.2)

        # 1) Read the control text directly (most reliable, no clipboard involved).
        text = self._read_control_text(pos.x, pos.y)
        match = re.search(_NUMBER_RE, str(text or ""))
        if match is not None:
            return float(match.group())

        # 2) Fallback: select + copy + read clipboard, retrying.
        for attempt in range(3):
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)
            self._clear_clipboard()
            pyautogui.hotkey("ctrl", "c")

            text = self._read_clipboard()
            match = re.search(_NUMBER_RE, str(text or ""))
            if match is not None:
                return float(match.group())

            if attempt == 1:
                pyautogui.doubleClick(pos.x, pos.y)
                time.sleep(0.15)
            time.sleep(0.25)

        raise RuntimeError(
            f"No numeric value found in CAM350 {axis.upper()} field. "
            f"Position ({pos.x}, {pos.y}), clipboard content was: {text!r}"
        )

    def run_origin_macro(self, origin_x: float, origin_y: float, layer: str = "top", angle_deg: int = 0) -> tuple:
        """Align-origin macro (Step 5). When angle_deg == 90 the board is first
        rotated 90° (Ctrl+Alt+R); for 'bottom' Ctrl+Alt+B is pressed first to
        view the Bottom layer, then Ctrl+Alt+X reveals the Space Origin marker,
        CAM350 is jumped to the given origin (in mm) and confirmed with Enter.
        Returns (origin_x, origin_y)."""
        config = self._config_mgr.config
        if not config.xTextbox.x or not config.yTextbox.x:
            raise RuntimeError(
                "CAM350 not calibrated. Please run calibration first."
            )

        self.activate()
        time.sleep(0.2)

        try:
            if layer == "bottom":
                pyautogui.hotkey("ctrl", "alt", "b")
                time.sleep(0.5)

            if angle_deg == 90:
                pyautogui.hotkey("ctrl", "alt", "r")
                time.sleep(0.5)

            pyautogui.hotkey("ctrl", "alt", "x")
            time.sleep(0.5)

            self.jump_to(origin_x, origin_y)
            time.sleep(1.0)
            pyautogui.press("enter")
        finally:
            self._release_modifiers()

        return origin_x, origin_y

    def _release_modifiers(self) -> None:
        """Safety net: release Ctrl/Alt/Shift so no key is left held down
        if a macro is interrupted by an exception."""
        for vk in (win32con.VK_CONTROL, win32con.VK_MENU, win32con.VK_SHIFT):
            try:
                _user32.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
            except Exception:
                pass

    @staticmethod
    def _read_control_text(x: int, y: int) -> str:
        """Send WM_GETTEXT to the window/control located at screen (x, y)."""
        try:
            hwnd = _user32.WindowFromPoint(_POINT(int(x), int(y)))
            if not hwnd:
                return ""
            length = _user32.SendMessageW(hwnd, _WM_GETTEXTLENGTH, 0, 0)
            if not length or length < 0 or length > 4096:
                return ""
            buf = ctypes.create_unicode_buffer(int(length) + 1)
            _user32.SendMessageW(hwnd, _WM_GETTEXT, len(buf), ctypes.cast(buf, ctypes.c_void_p))
            return buf.value
        except Exception:
            return ""

    @staticmethod
    def _clear_clipboard() -> None:
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass

    @staticmethod
    def _read_clipboard() -> str:
        """Read the clipboard, retrying until a numeric value appears (copy may lag)."""
        last_text = ""
        for _ in range(12):
            time.sleep(0.1)
            try:
                win32clipboard.OpenClipboard()
                try:
                    if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                        last_text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                finally:
                    win32clipboard.CloseClipboard()
            except Exception:
                pass
            if re.search(_NUMBER_RE, str(last_text or "")):
                return last_text
        return last_text

import ctypes
from ctypes import wintypes

DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36

COLORREF_DEFAULT = 0x00000000 | 0xFFFFFFFF

_dwmapi = ctypes.windll.dwmapi


def _colorref(color: str) -> int:
    if not color or not isinstance(color, str):
        return COLORREF_DEFAULT
    value = int(color.lstrip("#"), 16)
    red = (value >> 16) & 0xFF
    green = (value >> 8) & 0xFF
    blue = value & 0xFF
    return (blue << 16) | (green << 8) | red


def set_titlebar_theme(
    hwnd: int,
    *,
    caption: str = "#1E293B",
    text: str = "#FFFFFF",
    border: str = "#1E293B",
) -> bool:
    """Set a fixed caption (title bar) color via the Windows DWM API.

    Works on Windows 11 22H2+ (build 22621+). On older systems the
    attributes are ignored and this degrades to a no-op, keeping the
    native theme behaviour.
    """
    if not hwnd:
        return False

    attrs = (
        (DWMWA_BORDER_COLOR, _colorref(border)),
        (DWMWA_CAPTION_COLOR, _colorref(caption)),
        (DWMWA_TEXT_COLOR, _colorref(text)),
    )

    ok = True
    for attr, value in attrs:
        result = wintypes.DWORD(value)
        hr = _dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            attr,
            ctypes.byref(result),
            ctypes.sizeof(result),
        )
        if hr != 0:
            ok = False
    return ok
import ctypes
import hashlib
import winreg
from typing import List


def _machine_guid() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip()
    except OSError:
        return ""


def _volume_serials() -> List[str]:
    serials: List[str] = []
    kernel32 = ctypes.windll.kernel32
    get_volume = kernel32.GetVolumeInformationW
    get_volume.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    get_volume.restype = ctypes.c_int
    for drive in ("C:\\", "D:\\"):
        serial = ctypes.c_uint32(0)
        ok = get_volume(drive, None, 0, ctypes.byref(serial), None, None, None, 0)
        if ok and serial.value:
            serials.append(format(serial.value, "08X"))
    return serials


def get_hwid() -> str:
    guid = _machine_guid()
    serials = _volume_serials()
    raw = "|".join([guid] + serials).strip("|")
    if not raw:
        raw = "unknown-machine"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32].upper()

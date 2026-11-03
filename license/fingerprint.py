import ctypes
import hashlib
import os
import sys
from typing import List

if sys.platform == "win32":
    import winreg


def _machine_guid() -> str:
    if sys.platform != "win32":
        return ""
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
    if sys.platform != "win32":
        return serials
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


def _read_first_line(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _linux_machine_id() -> str:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        value = _read_first_line(path)
        if value:
            return value
    return ""


_VIRTUAL_IFACE_PREFIXES = (
    "lo", "docker", "veth", "br-", "virbr", "tun", "tap",
    "vmnet", "vboxnet", "zt", "tailscale",
)


def _linux_mac_addresses() -> List[str]:
    macs: List[str] = []
    net_dir = "/sys/class/net"
    try:
        names = sorted(os.listdir(net_dir))
    except OSError:
        return macs
    for name in names:
        if name.startswith(_VIRTUAL_IFACE_PREFIXES):
            continue
        address = _read_first_line(os.path.join(net_dir, name, "address")).lower()
        if address and address != "00:00:00:00:00:00":
            macs.append(address)
    return macs


def _raw_fingerprint() -> str:
    if sys.platform == "win32":
        return "|".join([_machine_guid()] + _volume_serials()).strip("|")
    if sys.platform == "linux":
        return "|".join([_linux_machine_id()] + _linux_mac_addresses()).strip("|")
    return ""


def get_hwid() -> str:
    raw = _raw_fingerprint()
    if not raw:
        raw = "unknown-machine"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32].upper()

"""Cross-platform behaviour: Linux HWID, data paths and Windows-only guards."""

from __future__ import annotations

import json
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import license.fingerprint as fingerprint  # noqa: E402
import license.state as license_state  # noqa: E402
import utils.path_utils as path_utils  # noqa: E402


def test_linux_fingerprint_uses_machine_id_and_macs(monkeypatch):
    monkeypatch.setattr(fingerprint.sys, "platform", "linux")
    monkeypatch.setattr(fingerprint, "_linux_machine_id", lambda: "abc123")
    monkeypatch.setattr(
        fingerprint, "_linux_mac_addresses", lambda: ["aa:bb:cc:dd:ee:ff"]
    )
    assert fingerprint._raw_fingerprint() == "abc123|aa:bb:cc:dd:ee:ff"


def test_linux_fingerprint_falls_back_to_unknown_machine(monkeypatch):
    monkeypatch.setattr(fingerprint.sys, "platform", "linux")
    monkeypatch.setattr(fingerprint, "_linux_machine_id", lambda: "")
    monkeypatch.setattr(fingerprint, "_linux_mac_addresses", lambda: [])
    raw = fingerprint._raw_fingerprint()
    assert raw == ""
    assert len(fingerprint.get_hwid()) == 32


def test_get_hwid_is_stable_and_uppercase(monkeypatch):
    monkeypatch.setattr(fingerprint, "_raw_fingerprint", lambda: "fixed-machine")
    hwid = fingerprint.get_hwid()
    assert hwid == fingerprint.get_hwid()
    assert len(hwid) == 32
    assert hwid.isupper()


def test_linux_user_data_dir_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.setattr(path_utils.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(
        path_utils, "_legacy_data_dir", lambda: str(tmp_path / "legacy")
    )
    path = path_utils.user_data_dir()
    assert path == str(tmp_path / "CAM350_Review")
    assert os.path.isdir(path)


def test_linux_user_data_dir_keeps_legacy_folder(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    monkeypatch.setattr(path_utils.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(path_utils, "_legacy_data_dir", lambda: str(legacy))
    assert path_utils.user_data_dir() == str(legacy)


def test_license_state_file_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(license_state, "_REG_ROOT", None)
    monkeypatch.setattr(license_state, "user_data_dir", lambda: str(tmp_path))

    license_state.set_max_seen_date("2026-01-01")
    assert license_state.get_max_seen_date() == "2026-01-01"

    license_state.save_hwid("HWID123")
    data = json.loads((tmp_path / "license_state.json").read_text(encoding="utf-8"))
    assert data["Hwid"] == "HWID123"


def test_windows_only_modules_import_without_windows():
    import ui.calibration_wizard  # noqa: F401
    import ui.pcb_info_dialog  # noqa: F401

    import utils.dwm_theme as dwm

    assert dwm.set_titlebar_theme(0) is False

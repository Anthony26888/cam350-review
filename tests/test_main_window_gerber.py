import os
import types

from config.config_manager import ConfigManager
from ui.main_window import MainWindow


def _make_holder(config_path: str) -> types.SimpleNamespace:
    mgr = ConfigManager(config_path)
    holder = types.SimpleNamespace()
    holder._config_mgr = mgr
    holder._restore_session_gerber = MainWindow._restore_session_gerber.__get__(holder)
    holder._existing_gerber_paths = MainWindow._existing_gerber_paths.__get__(holder)
    return holder


def _session_with(**gerber) -> types.SimpleNamespace:
    s = types.SimpleNamespace()
    for key, val in gerber.items():
        setattr(s, key, val)
    return s


def test_restore_session_with_gerber_updates_config(tmp_path):
    holder = _make_holder(str(tmp_path / "config.json"))
    holder._restore_session_gerber(
        _session_with(gerberGko="A.gko", gerberGbo="B.gbo"))
    cfg = holder._config_mgr.config
    assert cfg.gerberGko == "A.gko"
    assert cfg.gerberGbo == "B.gbo"


def test_restore_session_empty_clears_config(tmp_path):
    holder = _make_holder(str(tmp_path / "config.json"))
    holder._config_mgr.update(gerberGko="OLD.gko", gerberGbo="OLD.gbo")
    holder._restore_session_gerber(_session_with())
    cfg = holder._config_mgr.config
    assert cfg.gerberGko == ""
    assert cfg.gerberGbo == ""
    assert cfg.gerberGtp == ""
    assert cfg.gerberGbp == ""
    assert cfg.gerberGto == ""


def test_restore_session_legacy_no_attr_clears_config(tmp_path):
    holder = _make_holder(str(tmp_path / "config.json"))
    holder._config_mgr.update(gerberGko="OLD.gko")
    # legacy session objects may lack gerber attributes entirely
    legacy = types.SimpleNamespace()
    holder._restore_session_gerber(legacy)
    assert holder._config_mgr.config.gerberGko == ""


def test_existing_gerber_paths_filters_missing(tmp_path):
    existing = tmp_path / "exist.gko"
    existing.write_text("x")
    holder = _make_holder(str(tmp_path / "config.json"))
    holder._config_mgr.update(gerberGko=str(existing), gerberGbo="missing.gbo")
    result = holder._existing_gerber_paths()
    assert result.get("gerberGko") == str(existing)
    assert "gerberGbo" not in result
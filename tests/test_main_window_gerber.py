import os
import types

from config.config_manager import ConfigManager
from services.session_service import compress_text
from ui.main_window import MainWindow

#: A Gerber file that the layer scan can read.
GERBER = "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.2*%\nG54D10*\nX010000Y020000D03*\nM02*\n"


def _make_holder(config_path: str) -> types.SimpleNamespace:
    mgr = ConfigManager(config_path)
    holder = types.SimpleNamespace()
    holder._config_mgr = mgr
    holder._restore_session_gerber = MainWindow._restore_session_gerber.__get__(holder)
    holder._existing_gerber_paths = MainWindow._existing_gerber_paths.__get__(holder)
    holder._existing_gerber_layers = MainWindow._existing_gerber_layers.__get__(holder)
    holder._existing_gerber_folder = MainWindow._existing_gerber_folder.__get__(holder)
    holder._migrate_gerber_layers = MainWindow._migrate_gerber_layers.__get__(holder)
    holder._clear_gerber_config = MainWindow._clear_gerber_config.__get__(holder)
    holder._materialize_embedded_gerber = MainWindow._materialize_embedded_gerber
    return holder


def _session_with(**gerber) -> types.SimpleNamespace:
    s = types.SimpleNamespace()
    for key, val in gerber.items():
        setattr(s, key, val)
    return s


def _write_layer(folder, name="board.gko", text=GERBER):
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_restore_session_with_gerber_updates_config(tmp_path):
    holder = _make_holder(str(tmp_path / "config.json"))
    path = _write_layer(tmp_path)
    holder._restore_session_gerber(_session_with(
        gerberFolder=str(tmp_path),
        gerberLayers=[{"path": path, "name": "Board Outline"}],
    ))
    cfg = holder._config_mgr.config
    assert cfg.gerberFolder == str(tmp_path)
    assert cfg.gerberLayers
    assert cfg.gerberLayers[0]["path"] == path


def test_restore_session_empty_clears_config(tmp_path):
    holder = _make_holder(str(tmp_path / "config.json"))
    holder._config_mgr.update(gerberFolder="OLD", gerberLayers=[{"path": "x"}])
    holder._restore_session_gerber(_session_with())
    cfg = holder._config_mgr.config
    assert cfg.gerberFolder == ""
    assert cfg.gerberLayers == []


def test_restore_session_legacy_no_attr_clears_config(tmp_path):
    holder = _make_holder(str(tmp_path / "config.json"))
    holder._config_mgr.update(gerberFolder="OLD", gerberLayers=[{"path": "x"}])
    # legacy session objects may lack gerber attributes entirely
    legacy = types.SimpleNamespace()
    holder._restore_session_gerber(legacy)
    assert holder._config_mgr.config.gerberFolder == ""
    assert holder._config_mgr.config.gerberLayers == []


def test_existing_gerber_layers_filters_missing(tmp_path):
    existing = _write_layer(tmp_path)
    holder = _make_holder(str(tmp_path / "config.json"))
    holder._config_mgr.update(gerberLayers=[
        {"path": existing},
        {"path": str(tmp_path / "missing.gko")},
    ])
    layers = holder._existing_gerber_layers()
    assert [layer.path for layer in layers] == [existing]


def test_a_setup_of_the_old_kind_becomes_layers(tmp_path):
    # The layers used to be picked one by one, by the role of the file.
    outline = _write_layer(tmp_path, "board.gko")
    holder = _make_holder(str(tmp_path / "config.json"))
    holder._config_mgr.update(gerberGko=outline)
    layers = holder._existing_gerber_layers()
    assert [layer.path for layer in layers] == [outline]
    assert holder._existing_gerber_folder() == str(tmp_path)


def test_clear_gerber_config_clears_all_fields(tmp_path):
    holder = _make_holder(str(tmp_path / "config.json"))
    holder._config_mgr.update(
        gerberFolder="C:/somewhere",
        gerberLayers=[{"path": "A.gko"}],
    )
    holder._clear_gerber_config()
    cfg = holder._config_mgr.config
    assert cfg.gerberFolder == ""
    assert cfg.gerberLayers == []


def test_restore_session_uses_embedded_gerber_when_missing(tmp_path, monkeypatch):
    from utils import path_utils

    fake_tmp = tmp_path / "appdata"
    monkeypatch.setattr(path_utils, "user_data_dir", lambda: str(fake_tmp))

    holder = _make_holder(str(tmp_path / "config.json"))
    embedded = {"D:/missing/b.GKO": compress_text(GERBER)}
    holder._restore_session_gerber(_session_with(
        gerberLayers=[{"path": "D:/missing/b.GKO"}],
        gerber_files=embedded,
    ))
    cfg = holder._config_mgr.config
    assert cfg.gerberLayers
    path = cfg.gerberLayers[0]["path"]
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        assert f.read() == GERBER


def test_restore_session_keeps_existing_path_over_embedded(tmp_path, monkeypatch):
    from utils import path_utils

    fake_tmp = tmp_path / "appdata"
    monkeypatch.setattr(path_utils, "user_data_dir", lambda: str(fake_tmp))

    existing = _write_layer(tmp_path, "real.gko", "REAL")
    holder = _make_holder(str(tmp_path / "config.json"))
    embedded = {existing: compress_text("EMBEDDED")}
    holder._restore_session_gerber(_session_with(
        gerberLayers=[{"path": existing}],
        gerber_files=embedded,
    ))
    cfg = holder._config_mgr.config
    assert cfg.gerberLayers[0]["path"] == existing

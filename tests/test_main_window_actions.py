import types

from ui.main_window import MainWindow


def _btn(initial: bool) -> types.SimpleNamespace:
    b = types.SimpleNamespace(enabled=initial)
    b.isEnabled = lambda: b.enabled
    return b


def _act() -> types.SimpleNamespace:
    a = types.SimpleNamespace(enabled=False)
    a.setEnabled = lambda e: setattr(a, "enabled", e)
    return a


def _holder() -> types.SimpleNamespace:
    h = types.SimpleNamespace()
    h._align_action = _act()
    h._export_report_action = _act()
    h._export_fixed_action = _act()
    h._pcb_info_action = _act()
    h._new_action = _act()
    h._save_action = _act()
    h._save_as_action = _act()
    h._panelize_action = _act()
    h._clear_panelize_action = _act()
    h._panel_config = None
    h._pre_panel_snapshot = None
    h._btn_align = _btn(True)
    h._btn_export_report = _btn(True)
    h._btn_export_fixed = _btn(True)
    h._btn_pcb_info = _btn(True)
    h._btn_new = _btn(True)
    h._btn_save = _btn(True)
    h._sync_action_states = MainWindow._sync_action_states.__get__(h)
    return h


def test_sync_action_states_mirrors_buttons():
    h = _holder()
    h._btn_align.enabled = True
    h._btn_export_report.enabled = False
    h._btn_export_fixed.enabled = True
    h._btn_pcb_info.enabled = False
    h._btn_new.enabled = True
    h._btn_save.enabled = False
    h._sync_action_states()
    assert h._align_action.enabled is True
    assert h._export_report_action.enabled is False
    assert h._export_fixed_action.enabled is True
    assert h._pcb_info_action.enabled is False
    assert h._new_action.enabled is True
    assert h._save_action.enabled is False
    assert h._save_as_action.enabled is False


def test_sync_action_states_false():
    h = _holder()
    h._btn_align.enabled = False
    h._btn_export_report.enabled = False
    h._btn_export_fixed.enabled = False
    h._btn_pcb_info.enabled = False
    h._btn_new.enabled = False
    h._btn_save.enabled = False
    h._sync_action_states()
    assert h._align_action.enabled is False
    assert h._export_report_action.enabled is False
    assert h._export_fixed_action.enabled is False
    assert h._pcb_info_action.enabled is False
    assert h._new_action.enabled is False
    assert h._save_action.enabled is False
    assert h._save_as_action.enabled is False
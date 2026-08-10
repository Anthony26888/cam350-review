from database.database import Database
from database.pcb_info_repo import PcbInfoRepo
from models.pcb_info import PcbInfo


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "test.db"))
    monkeypatch.setattr(Database, "_instance", db)

    repo = PcbInfoRepo()
    pcb = PcbInfo(
        board_width=100.5,
        board_height=80.25,
        working_area_width=50.0,
        position_working=12.5,
        x_boc1=10, y_boc1=20,
        x_boc2=30, y_boc2=40,
        x_boc3=50, y_boc3=60,
        thickness=1.6,
    )
    repo.save(pcb)

    loaded = repo.load()
    assert loaded.board_width == 100.5
    assert loaded.board_height == 80.25
    assert loaded.working_area_width == 50.0
    assert loaded.position_working == 12.5
    assert loaded.x_boc1 == 10 and loaded.y_boc1 == 20
    assert loaded.x_boc2 == 30 and loaded.y_boc2 == 40
    assert loaded.x_boc3 == 50 and loaded.y_boc3 == 60
    assert loaded.thickness == 1.6
    assert loaded.has_data()

    db.close()


def test_load_empty(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "empty.db"))
    monkeypatch.setattr(Database, "_instance", db)

    loaded = PcbInfoRepo().load()
    assert loaded.board_width == 0.0
    assert loaded.position_working == 0.0
    assert loaded.thickness == 1.6

    db.close()


def test_save_overwrites(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "overwrite.db"))
    monkeypatch.setattr(Database, "_instance", db)

    repo = PcbInfoRepo()
    repo.save(PcbInfo(board_width=1.0))
    repo.save(PcbInfo(board_width=2.0, thickness=3.0))

    loaded = repo.load()
    assert loaded.board_width == 2.0
    assert loaded.thickness == 3.0

    db.close()


def test_align_origin_saves_panel_dimensions(tmp_path, monkeypatch):
    from ui.origin_align_wizard import OriginAlignWizard

    db = Database(str(tmp_path / "align.db"))
    monkeypatch.setattr(Database, "_instance", db)

    wizard = OriginAlignWizard.__new__(OriginAlignWizard)

    class FakePanel:
        panel_w = 120.75
        panel_h = 90.5

    wizard._panel_info = FakePanel()
    wizard._save_panel_to_pcb_info()

    loaded = PcbInfoRepo().load()
    assert loaded.board_width == 120.75
    assert loaded.board_height == 90.5
    assert loaded.working_area_width == 120.75

    db.close()


def _stub_panel(ox, oy, w, h=0.0):
    class FakePanel:
        def __init__(self):
            self.panel_origin = (ox, oy)
            self.panel_w = w
            self.panel_h = h
    return FakePanel()


class _CheckedRb:
    def isChecked(self):
        return True


def _stub_wizard(monkeypatch):
    import types

    class FakeRb:
        def isChecked(self):
            return False

    class FakePanel:
        def __init__(self, ox, oy, w):
            self.panel_origin = (ox, oy)
            self.panel_w = w

    class FakeBtn:
        def setEnabled(self, _enabled):
            pass

    class FakeLabel:
        def setText(self, _txt):
            pass

        def setStyleSheet(self, _css):
            pass

    calls = {}

    class FakeCam350:
        def run_origin_macro(self, ox, oy, layer="top", angle_deg=0):
            calls["ox"] = ox
            calls["oy"] = oy
            calls["layer"] = layer
            calls["angle_deg"] = angle_deg

    from ui.origin_align_wizard import OriginAlignWizard
    wizard = OriginAlignWizard.__new__(OriginAlignWizard)
    wizard._rb_layer_bottom = FakeRb()
    wizard._macro_running = False
    wizard._btn_run_macro = FakeBtn()
    wizard._btn_next = FakeBtn()
    wizard._btn_back = FakeBtn()
    wizard._btn_cancel = FakeBtn()
    wizard._lbl_macro_status = FakeLabel()
    wizard._cam350 = FakeCam350()
    wizard._chosen_rotation_angle = 0
    return wizard, calls


def test_execute_macro_rotation_90_top(monkeypatch):
    wizard, calls = _stub_wizard(monkeypatch)
    wizard._chosen_rotation_angle = 90
    wizard._rotation_angle = 90
    wizard._panel_info = _stub_panel(100.0, 200.0, 120.75, 300.0)

    wizard._execute_macro()

    assert calls["ox"] == 100.0
    assert calls["oy"] == 300.0 + 200.0
    assert calls["layer"] == "top"
    assert calls["angle_deg"] == 90


def test_execute_macro_rotation_90_bottom(monkeypatch):
    wizard, calls = _stub_wizard(monkeypatch)
    wizard._chosen_rotation_angle = 90
    wizard._rotation_angle = 90
    wizard._panel_info = _stub_panel(100.0, 200.0, 120.75, h=300.0)
    wizard._rb_layer_bottom = _CheckedRb()

    wizard._execute_macro()

    assert calls["ox"] == 100.0
    assert calls["oy"] == 200.0
    assert calls["layer"] == "bottom"
    assert calls["angle_deg"] == 90


def test_execute_macro_rotation_90_uses_chosen_angle(monkeypatch):
    wizard, calls = _stub_wizard(monkeypatch)
    wizard._chosen_rotation_angle = 90
    wizard._rotation_angle = 0
    wizard._panel_info = _stub_panel(100.0, 200.0, 120.75, h=300.0)

    wizard._execute_macro()

    assert calls["angle_deg"] == 90


def test_execute_macro_rotation_0_panel(monkeypatch):
    wizard, calls = _stub_wizard(monkeypatch)
    wizard._chosen_rotation_angle = 0
    wizard._rotation_angle = 0
    wizard._panel_info = _stub_panel(100.0, 200.0, 120.75)

    wizard._execute_macro()

    assert calls["ox"] == 100.0
    assert calls["oy"] == 200.0
    assert calls["layer"] == "top"
    assert calls["angle_deg"] == 0


def test_execute_macro_rotation_0_bottom(monkeypatch):
    wizard, calls = _stub_wizard(monkeypatch)
    wizard._chosen_rotation_angle = 0
    wizard._rotation_angle = 0
    wizard._panel_info = _stub_panel(100.0, 200.0, 120.75, h=300.0)
    wizard._rb_layer_bottom = _CheckedRb()

    wizard._execute_macro()

    assert calls["ox"] == 100.0 + 120.75
    assert calls["oy"] == 200.0
    assert calls["layer"] == "bottom"
    assert calls["angle_deg"] == 0


def test_pcb_info_dict_round_trip():
    pcb = PcbInfo(
        board_width=12.5, board_height=8.25, working_area_width=12.5,
        position_working=1.0, x_boc1=1, y_boc1=2, x_boc2=3, y_boc2=4,
        x_boc3=5, y_boc3=6, thickness=1.6,
    )
    restored = PcbInfo.from_dict(pcb.to_dict())
    assert restored == pcb


def test_repo_clear(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "clear.db"))
    monkeypatch.setattr(Database, "_instance", db)

    repo = PcbInfoRepo()
    repo.save(PcbInfo(board_width=100.0))
    assert repo.load().board_width == 100.0

    repo.clear()
    loaded = repo.load()
    assert loaded.board_width == 0.0
    assert loaded.thickness == 1.6

    db.close()

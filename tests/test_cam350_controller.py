import pywintypes
import pytest
import win32con

from services import cam350_controller
from services.cam350_controller import Cam350Controller


class FakePoint:
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y


class FakeConfig:
    xTextbox = FakePoint(100, 100)
    yTextbox = FakePoint(200, 200)
    delay = 150


class FakeConfigManager:
    def __init__(self):
        self.config = FakeConfig()


@pytest.fixture
def fake_cam350(monkeypatch):
    fake_calls = {
        "hotkey": [],
        "press": [],
        "activate": 0,
        "jump": [],
    }

    monkeypatch.setattr(
        cam350_controller.ConfigManager, "instance",
        lambda: FakeConfigManager(),
    )
    monkeypatch.setattr(cam350_controller.time, "sleep", lambda s: None)

    controller = Cam350Controller()

    def fake_activate():
        fake_calls["activate"] += 1

    def fake_read(axis):
        return 10.5 if axis == "x" else 20.25

    def fake_jump(x, y):
        fake_calls["jump"].append((x, y))

    def fake_hotkey(*keys):
        fake_calls["hotkey"].append(keys)

    def fake_press(key):
        fake_calls["press"].append(key)

    monkeypatch.setattr(controller, "activate", fake_activate)
    monkeypatch.setattr(controller, "read_value", fake_read)
    monkeypatch.setattr(controller, "jump_to", fake_jump)
    monkeypatch.setattr(cam350_controller.pyautogui, "hotkey", fake_hotkey)
    monkeypatch.setattr(cam350_controller.pyautogui, "press", fake_press)

    return controller, fake_calls


def test_run_origin_macro_flow(fake_cam350):
    controller, calls = fake_cam350

    result = controller.run_origin_macro(10.5, 20.25)

    assert result == (10.5, 20.25)
    assert calls["hotkey"] == [("ctrl", "alt", "x")]
    assert calls["jump"] == [(10.5, 20.25)]
    assert calls["press"] == ["enter"]
    assert calls["activate"] == 1


def test_run_origin_macro_bottom_layer(fake_cam350):
    controller, calls = fake_cam350

    result = controller.run_origin_macro(200.0, 20.25, layer="bottom")

    assert result == (200.0, 20.25)
    assert calls["hotkey"] == [("ctrl", "alt", "b"), ("ctrl", "alt", "x")]
    assert calls["jump"] == [(200.0, 20.25)]
    assert calls["press"] == ["enter"]
    assert calls["activate"] == 1


def test_run_origin_macro_requires_calibration(monkeypatch):
    class EmptyConfig(FakeConfig):
        xTextbox = FakePoint(0, 0)
        yTextbox = FakePoint(0, 0)

    class EmptyManager:
        config = EmptyConfig()

    monkeypatch.setattr(
        cam350_controller.ConfigManager, "instance",
        lambda: EmptyManager(),
    )

    controller = Cam350Controller()
    with pytest.raises(RuntimeError):
        controller.run_origin_macro(10.5, 20.25)


def test_run_rotation_macro_90_top(fake_cam350):
    controller, calls = fake_cam350

    result = controller.run_origin_macro(10.5, 20.25, angle_deg=90)

    assert result == (10.5, 20.25)
    assert calls["hotkey"] == [("ctrl", "alt", "r"), ("ctrl", "alt", "x")]
    assert calls["jump"] == [(10.5, 20.25)]
    assert calls["press"] == ["enter"]
    assert calls["activate"] == 1


def test_run_rotation_macro_90_bottom(fake_cam350):
    controller, calls = fake_cam350

    result = controller.run_origin_macro(200.0, 20.25, layer="bottom", angle_deg=90)

    assert result == (200.0, 20.25)
    assert calls["hotkey"] == [
        ("ctrl", "alt", "b"),
        ("ctrl", "alt", "r"),
        ("ctrl", "alt", "x"),
    ]
    assert calls["jump"] == [(200.0, 20.25)]
    assert calls["press"] == ["enter"]


def test_run_rotation_macro_0_no_rotation(fake_cam350):
    controller, calls = fake_cam350

    controller.run_origin_macro(10.5, 20.25, angle_deg=0)

    assert calls["hotkey"] == [("ctrl", "alt", "x")]
    assert calls["jump"] == [(10.5, 20.25)]


def test_run_rotation_macro_requires_calibration(monkeypatch):
    class EmptyConfig(FakeConfig):
        xTextbox = FakePoint(0, 0)
        yTextbox = FakePoint(0, 0)

    class EmptyManager:
        config = EmptyConfig()

    monkeypatch.setattr(
        cam350_controller.ConfigManager, "instance",
        lambda: EmptyManager(),
    )

    controller = Cam350Controller()
    with pytest.raises(RuntimeError):
        controller.run_origin_macro(10.5, 20.25, angle_deg=90)


class FakeUser32:
    def __init__(self):
        self.events = []

    def keybd_event(self, vk, scan, flags, extra=0):
        self.events.append((vk, flags))


@pytest.fixture
def activate_env(monkeypatch):
    monkeypatch.setattr(
        cam350_controller.ConfigManager, "instance",
        lambda: FakeConfigManager(),
    )
    monkeypatch.setattr(cam350_controller.time, "sleep", lambda s: None)

    fake_user32 = FakeUser32()
    monkeypatch.setattr(cam350_controller, "_user32", fake_user32)

    state = {"fg": 1234, "set_foreground_raises": False}

    class FakeWin32Gui:
        @staticmethod
        def IsIconic(hwnd):
            return False

        @staticmethod
        def ShowWindow(hwnd, cmd):
            return True

        @staticmethod
        def SetForegroundWindow(hwnd):
            if state["set_foreground_raises"]:
                raise pywintypes.error(
                    0, "SetForegroundWindow", "No message is available"
                )
            state["fg"] = hwnd
            return True

        @staticmethod
        def BringWindowToTop(hwnd):
            return True

        @staticmethod
        def GetForegroundWindow():
            return state["fg"]

    monkeypatch.setattr(cam350_controller, "win32gui", FakeWin32Gui)

    controller = Cam350Controller()
    monkeypatch.setattr(controller, "_find_window", lambda: 1234)
    return controller, fake_user32, state


def test_activate_releases_alt_even_when_setforegroundwindow_raises(activate_env):
    controller, fake_user32, state = activate_env
    state["set_foreground_raises"] = True

    controller.activate()

    alt_events = [e for e in fake_user32.events if e[0] == win32con.VK_MENU]
    assert len(alt_events) == 2
    assert alt_events[0][1] == 0
    assert alt_events[1][1] == win32con.KEYEVENTF_KEYUP


def test_activate_succeeds_when_cam350_already_foreground(activate_env):
    controller, fake_user32, _ = activate_env

    controller.activate()

    alt_events = [e for e in fake_user32.events if e[0] == win32con.VK_MENU]
    assert len(alt_events) == 2
    assert alt_events[0][1] == 0
    assert alt_events[1][1] == win32con.KEYEVENTF_KEYUP


def test_activate_raises_clear_error_and_releases_alt_when_focus_fails(activate_env):
    controller, fake_user32, state = activate_env
    state["set_foreground_raises"] = True
    state["fg"] = 9999

    with pytest.raises(RuntimeError, match="CAM350"):
        controller.activate()

    alt_events = [e for e in fake_user32.events if e[0] == win32con.VK_MENU]
    assert len(alt_events) == 4
    assert alt_events[0][1] == 0
    assert alt_events[1][1] == win32con.KEYEVENTF_KEYUP
    assert alt_events[2][1] == 0
    assert alt_events[3][1] == win32con.KEYEVENTF_KEYUP


def test_run_origin_macro_releases_modifiers_on_failure(monkeypatch):
    monkeypatch.setattr(
        cam350_controller.ConfigManager, "instance",
        lambda: FakeConfigManager(),
    )
    monkeypatch.setattr(cam350_controller.time, "sleep", lambda s: None)

    fake_user32 = FakeUser32()
    monkeypatch.setattr(cam350_controller, "_user32", fake_user32)
    monkeypatch.setattr(cam350_controller.pyautogui, "hotkey", lambda *a, **k: None)
    monkeypatch.setattr(cam350_controller.pyautogui, "press", lambda *a, **k: None)

    controller = Cam350Controller()
    monkeypatch.setattr(controller, "activate", lambda: None)

    def boom(x, y):
        raise RuntimeError("jump failed")

    monkeypatch.setattr(controller, "jump_to", boom)

    with pytest.raises(RuntimeError, match="jump failed"):
        controller.run_origin_macro(10.5, 20.25)

    keyups = {
        e[0]
        for e in fake_user32.events
        if e[1] == win32con.KEYEVENTF_KEYUP
    }
    assert keyups == {win32con.VK_CONTROL, win32con.VK_MENU, win32con.VK_SHIFT}

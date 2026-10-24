import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import types

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


class _FakeDialog:
    def __init__(self):
        self.closed = False

    def reset(self):
        pass

    def close(self):
        self.closed = True

    def deleteLater(self):
        pass


def _holder():
    app = QApplication.instance() or QApplication([])
    h = types.SimpleNamespace()
    h._run_with_busy_dialog = MainWindow._run_with_busy_dialog.__get__(h)
    return h, app


def test_busy_dialog_returns_value_and_closes():
    h, app = _holder()
    dlg = _FakeDialog()
    result = h._run_with_busy_dialog(
        "Working...", lambda: 42, dialog_factory=lambda _t: dlg)
    assert result == 42
    assert dlg.closed
    assert app.overrideCursor() is None


def test_busy_dialog_error_still_closes_and_reraises():
    h, app = _holder()
    dlg = _FakeDialog()

    def _boom():
        raise ValueError("bad file")

    try:
        h._run_with_busy_dialog(
            "Working...", _boom, dialog_factory=lambda _t: dlg)
    except ValueError as e:
        assert str(e) == "bad file"
    else:
        raise AssertionError("expected ValueError to propagate")
    assert dlg.closed
    assert app.overrideCursor() is None


def test_busy_dialog_shows_wait_cursor_while_running():
    h, app = _holder()
    seen = []
    dlg = _FakeDialog()

    def _work():
        seen.append(app.overrideCursor())
        return "done"

    assert h._run_with_busy_dialog(
        "Working...", _work, dialog_factory=lambda _t: dlg) == "done"
    assert seen and seen[0] is not None
    assert seen[0].shape() == Qt.WaitCursor
    assert app.overrideCursor() is None

"""Flipping all components and their coordinates across the X/Y axis."""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from models.review import ReviewRecord  # noqa: E402
from gerber_layers_helper import make_layers  # noqa: E402
from services.gerber.gerber_render import LineShape, RenderData  # noqa: E402
from ui.gerber_viewer import GerberViewer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _NoopGerberViewer(GerberViewer):
    def _start_load(self):
        pass


class _FakeMsgBox:
    Yes = QMessageBox.Yes
    No = QMessageBox.No
    answer = QMessageBox.Yes
    last_text = ""

    @staticmethod
    def question(*args, **kwargs):
        _FakeMsgBox.last_text = args[2] if len(args) > 2 else kwargs.get("text", "")
        return _FakeMsgBox.answer


class _FakeProgress:
    closed = 0

    def __init__(self, *args, **kwargs):
        pass

    def setWindowTitle(self, _t):
        pass

    def setCancelButton(self, _b):
        pass

    def setWindowModality(self, _m):
        pass

    def setMinimumDuration(self, _d):
        pass

    def setValue(self, _v):
        pass

    def close(self):
        _FakeProgress.closed += 1


def _make_records():
    return [
        ReviewRecord(designator="C1", mpn="M1", layer="Top",
                     old_x=10.0, old_y=20.0, old_rotation=0.0),
        ReviewRecord(designator="R1", mpn="M2", layer="Bottom",
                     old_x=30.0, old_y=-40.0, old_rotation=90.0),
    ]


def _viewer(app, monkeypatch=None):
    v = _NoopGerberViewer(_make_records(), make_layers())
    v._layer_data = [RenderData(lines=[LineShape(x1=0.0, y1=0.0,
                                                x2=100.0, y2=100.0)])]
    v._loaded = True
    v.show()
    v._redraw()
    for b in v._btn_check_controls:
        b.setEnabled(True)
    if monkeypatch is not None:
        monkeypatch.setattr("ui.gerber_viewer.QMessageBox", _FakeMsgBox)
        monkeypatch.setattr("ui.gerber_viewer.QProgressDialog", _FakeProgress)
    return v


def test_flip_records_button_disabled_before_load(app):
    v = _NoopGerberViewer(_make_records(), make_layers())
    assert not v._btn_flip_records_x.isEnabled()
    assert not v._btn_flip_records_y.isEnabled()
    assert v._btn_flip_records_x in v._btn_check_controls
    assert v._btn_flip_records_y in v._btn_check_controls
    assert not v._btn_flip_records.isEnabled()
    assert v._btn_flip_records in v._btn_check_controls


def test_flip_x_updates_coords_and_rotation(app, monkeypatch):
    v = _viewer(app, monkeypatch)
    _FakeMsgBox.answer = QMessageBox.Yes
    emitted = []
    v.rotation_edited.connect(emitted.append)
    v._on_flip_records("X")
    rec_top, rec_bot = v._records
    assert rec_top.new_x == pytest.approx(10.0)
    assert rec_top.new_y == pytest.approx(-20.0)
    assert rec_top.new_rotation == pytest.approx(0.0)
    assert rec_top.old_x == 10.0 and rec_top.old_y == 20.0
    # Only the shown (top) layer is flipped.
    assert rec_bot.new_x is None and rec_bot.new_y is None
    assert rec_bot.new_rotation is None and rec_bot.status == "Pending"
    assert rec_top.status == "Edited" and rec_top.review_time
    assert emitted == [v._record_index_in_records(rec_top)]
    assert "top-side" in _FakeMsgBox.last_text \
        or "flip" in _FakeMsgBox.last_text.lower()


def test_flip_x_on_bottom_layer_touches_bottom_only(app, monkeypatch):
    v = _viewer(app, monkeypatch)
    _FakeMsgBox.answer = QMessageBox.Yes
    v._combo_layer.setCurrentIndex(1)
    v._on_flip_records("X")
    rec_top, rec_bot = v._records
    assert rec_bot.new_y == pytest.approx(40.0)     # -(-40)
    assert rec_bot.new_x == pytest.approx(30.0)
    assert rec_bot.new_rotation == pytest.approx(270.0)  # -90 % 360
    assert rec_bot.status == "Edited" and rec_bot.review_time
    # Top side untouched.
    assert rec_top.new_x is None and rec_top.new_y is None
    assert rec_top.status == "Pending"
    assert "bottom-side" in _FakeMsgBox.last_text


def test_flip_y_updates_coords_and_rotation(app, monkeypatch):
    v = _viewer(app, monkeypatch)
    _FakeMsgBox.answer = QMessageBox.Yes
    v._on_flip_records("Y")
    rec_top, rec_bot = v._records
    assert rec_top.new_x == pytest.approx(-10.0)
    assert rec_top.new_y == pytest.approx(20.0)
    assert rec_top.new_rotation == pytest.approx(0.0)
    assert rec_bot.new_x is None and rec_bot.new_y is None


def test_flip_uses_existing_new_values(app, monkeypatch):
    v = _viewer(app, monkeypatch)
    v._records[0].new_x = 100.0
    v._records[0].new_y = 50.0
    v._records[0].new_rotation = 45.0
    _FakeMsgBox.answer = QMessageBox.Yes
    v._on_flip_records("X")
    top = v._records[0]
    assert top.new_x == pytest.approx(100.0)
    assert top.new_y == pytest.approx(-50.0)
    assert top.new_rotation == pytest.approx(315.0)


def test_flip_declined_keeps_records(app, monkeypatch):
    v = _viewer(app, monkeypatch)
    _FakeMsgBox.answer = QMessageBox.No
    emitted = []
    v.rotation_edited.connect(emitted.append)
    v._on_flip_records("X")
    for rec in v._records:
        assert rec.new_x is None and rec.new_y is None
        assert rec.new_rotation is None
        assert rec.status == "Pending"
    assert emitted == []


def test_flip_shows_progress_dialog(app, monkeypatch):
    v = _viewer(app, monkeypatch)
    _FakeMsgBox.answer = QMessageBox.Yes
    _FakeProgress.closed = 0
    v._on_flip_records("Y")
    assert _FakeProgress.closed == 1
    assert "top-side components across the Y axis" in _FakeMsgBox.last_text

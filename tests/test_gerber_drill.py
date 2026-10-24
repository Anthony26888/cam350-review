"""Tests for the NC drill support of the Gerber viewer."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from services.gerber.gerber_render_lib import load_drill
from services.gerber.spec.excellon import ExcellonParser
from services.gerber.spec.loader import detect_kind
from ui.gerber_file_dialog import GerberFileDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


EXCELLON = (
    "M48\n"
    ";FILE_FORMAT=4:4\n"
    "METRIC,LZ\n"
    "T01F00S00C0.2000\n"
    "T02F00S00C0.4000\n"
    "%\n"
    "T01\n"
    "X00100000Y00200000\n"
    "X00300000Y00400000\n"
    "T02\n"
    "X00500000Y00600000\n"
    "M30\n"
)


def test_excellon_is_detected(tmp_path):
    path = tmp_path / "board.drl"
    path.write_text(EXCELLON, encoding="utf-8")
    assert detect_kind(str(path)) == "excellon"


def test_excellon_holes_become_flashed_circles(tmp_path):
    path = tmp_path / "board.drl"
    path.write_text(EXCELLON, encoding="utf-8")
    data, info = load_drill(str(path))
    assert info.parser == "spec"
    assert info.degraded is False
    assert len(data.flashes) == 3
    # The tool diameter becomes the size of the flashed circle.
    assert data.flashes[0].w == pytest.approx(0.2, abs=0.001)
    assert data.flashes[2].w == pytest.approx(0.4, abs=0.001)
    # 10.0000 mm and 20.0000 mm with the 4:4 format.
    assert data.flashes[0].cx == pytest.approx(10.0, abs=0.01)
    assert data.flashes[0].cy == pytest.approx(20.0, abs=0.01)


def test_a_drill_file_written_as_gerber_is_accepted(tmp_path):
    path = tmp_path / "board.drl"
    path.write_text(
        "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.100000*%\n"
        "D10*\nX100000Y200000D03*\n",
        encoding="utf-8",
    )
    data, info = load_drill(str(path))
    assert info.parser == "spec"
    assert len(data.flashes) == 1
    assert data.flashes[0].kind == "circle"


def test_an_unreadable_drill_file_is_reported(tmp_path):
    path = tmp_path / "board.drl"
    path.write_text("nothing useful here\n", encoding="utf-8")
    data, info = load_drill(str(path))
    assert data.flashes == []
    assert info.error is not None


def test_a_drill_file_becomes_a_layer_of_the_list(app, tmp_path):
    # The drill file used to have a field of its own; it is now a layer
    # like every other file of the folder.
    from services.gerber.layer_scan import scan_folder

    path = tmp_path / "board.drl"
    path.write_text(EXCELLON, encoding="utf-8")
    layers = scan_folder(str(tmp_path))
    assert [layer.role for layer in layers] == ["drill"]
    assert layers[0].is_drill is True

    dialog = GerberFileDialog(str(tmp_path))
    assert len(dialog.selected_layers()) == 1
    assert dialog.selected_layers()[0].is_drill is True

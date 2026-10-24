"""The dialog that picks the folder of the Gerber files."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from services.gerber.layer_scan import ROLE_COPPER, ROLE_PROFILE  # noqa: E402
from ui.gerber_file_dialog import GerberFileDialog  # noqa: E402

COPPER = (
    "%FSLAX44Y44*%\n%MOIN*%\n"
    "%TF.FileFunction,Copper,L1,Top,Signal*%\n"
    "%ADD10C,0.2000*%\n"
    "G54D10*\nX010000Y020000D03*\n"
)
OUTLINE = "%FSLAX44Y44*%\n%MOIN*%\n%ADD10C,0.2000*%\nG54D10*\nX010000Y020000D03*\n"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _write(folder, name, text):
    path = os.path.join(str(folder), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class TestGerberFileDialog:
    def test_the_files_of_the_folder_become_layers(self, qapp, tmp_path):
        _write(tmp_path, "outline.gko", OUTLINE)
        _write(tmp_path, "top.gbr", COPPER)
        dialog = GerberFileDialog(str(tmp_path))
        layers = dialog.selected_layers()
        assert len(layers) == 2
        assert [layer.role for layer in layers] == [ROLE_PROFILE, ROLE_COPPER]
        assert dialog.selected_folder() == str(tmp_path)

    def test_the_table_shows_the_layers(self, qapp, tmp_path):
        _write(tmp_path, "top.gbr", COPPER)
        dialog = GerberFileDialog(str(tmp_path))
        assert dialog._table.rowCount() == 1
        assert dialog._table.item(0, 0).text() == "Copper,L1,Top,Signal"
        assert dialog._table.item(0, 1).text() == "top.gbr"

    def test_a_folder_without_artwork_has_no_layer(self, qapp, tmp_path):
        _write(tmp_path, "readme.txt", "hello")
        dialog = GerberFileDialog(str(tmp_path))
        assert dialog.selected_layers() == []
        assert dialog._btn_next.isEnabled() is False

    def test_a_layer_can_be_taken_away(self, qapp, tmp_path):
        _write(tmp_path, "outline.gko", OUTLINE)
        _write(tmp_path, "top.gbr", COPPER)
        dialog = GerberFileDialog(str(tmp_path))
        dialog._table.setCurrentCell(1, 0)
        dialog._remove_layer()
        assert len(dialog.selected_layers()) == 1
        assert dialog.selected_layers()[0].role == ROLE_PROFILE

    def test_the_layers_that_are_given_are_kept(self, qapp, tmp_path):
        from services.gerber.layer_scan import scan_folder
        _write(tmp_path, "top.gbr", COPPER)
        layers = scan_folder(str(tmp_path))
        dialog = GerberFileDialog(str(tmp_path), layers)
        assert len(dialog.selected_layers()) == 1
        assert dialog._table.rowCount() == 1

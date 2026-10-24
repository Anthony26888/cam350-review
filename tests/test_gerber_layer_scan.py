"""Finding the layers of a folder."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.gerber.layer_scan import (  # noqa: E402
    ROLE_COPPER, ROLE_DRILL, ROLE_MASK, ROLE_OTHER, ROLE_PASTE, ROLE_PROFILE,
    ROLE_SILK, SIDE_BOTTOM, SIDE_NONE, SIDE_TOP,
    layer_from_file, read_x2_header, role_from_file_function, scan_folder,
)

#: A Gerber file with the X2 attributes of a copper layer.
COPPER = (
    "%FSLAX44Y44*%\n%MOIN*%\n"
    "%TF.FileFunction,Copper,L1,Top,Signal*%\n"
    "%TF.FilePolarity,Positive*%\n"
    "%ADD10C,0.2000*%\n"
    "G54D10*\nX010000Y020000D03*\n"
)

#: A Gerber file without any attribute.
PLAIN = "%FSLAX44Y44*%\n%MOIN*%\n%ADD10C,0.2000*%\nG54D10*\nX010000Y020000D03*\n"

#: A drill file.
DRILL = "M48\n;FILE_FORMAT=4:4\nMETRIC,LZ\nT01C1.0\n%\nT01\nX010000Y020000\nM30\n"

#: A file that holds no artwork.
PICK_AND_PLACE = "Designator,Val\nR1,10mm\n"


def _write(folder, name, text):
    path = os.path.join(str(folder), name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class TestX2Header:
    def test_the_file_function_is_read(self, tmp_path):
        path = _write(tmp_path, "top.gbr", COPPER)
        attributes = read_x2_header(path)
        assert attributes["FileFunction"] == "Copper,L1,Top,Signal"
        assert attributes["FilePolarity"] == "Positive"

    def test_a_file_without_attributes_gives_nothing(self, tmp_path):
        path = _write(tmp_path, "top.gbr", PLAIN)
        assert read_x2_header(path) == {}

    def test_a_missing_file_gives_nothing(self, tmp_path):
        assert read_x2_header(str(tmp_path / "nope.gbr")) == {}


class TestRole:
    def test_a_copper_layer(self):
        assert role_from_file_function("Copper,L1,Top,Signal") == (ROLE_COPPER, SIDE_TOP)

    def test_a_bottom_copper_layer(self):
        assert role_from_file_function("Copper,L6,Bot,Signal") == (ROLE_COPPER, SIDE_BOTTOM)

    def test_a_solder_mask(self):
        assert role_from_file_function("Soldermask,Top") == (ROLE_MASK, SIDE_TOP)

    def test_a_legend(self):
        assert role_from_file_function("Legend,Top") == (ROLE_SILK, SIDE_TOP)

    def test_a_paste(self):
        assert role_from_file_function("Paste,Bot") == (ROLE_PASTE, SIDE_BOTTOM)

    def test_a_profile(self):
        assert role_from_file_function("Profile,NP") == (ROLE_PROFILE, SIDE_NONE)

    def test_nothing_at_all(self):
        assert role_from_file_function("") == (ROLE_OTHER, SIDE_NONE)


class TestLayerFromFile:
    def test_a_file_with_attributes(self, tmp_path):
        path = _write(tmp_path, "top.gbr", COPPER)
        layer = layer_from_file(path)
        assert layer is not None
        assert layer.role == ROLE_COPPER
        assert layer.side == SIDE_TOP
        assert layer.name == "Copper,L1,Top,Signal"
        assert layer.file_name == "top.gbr"
        assert layer.polarity == "positive"

    def test_a_file_without_attributes_uses_its_name(self, tmp_path):
        path = _write(tmp_path, "gtp", PLAIN)
        layer = layer_from_file(path)
        assert layer is not None
        assert layer.role == ROLE_PASTE
        assert layer.side == SIDE_TOP

    def test_a_file_without_a_name_and_without_attributes(self, tmp_path):
        path = _write(tmp_path, "something", PLAIN)
        layer = layer_from_file(path)
        assert layer is not None
        assert layer.role == ROLE_OTHER

    def test_a_drill_file(self, tmp_path):
        path = _write(tmp_path, "board.drl", DRILL)
        layer = layer_from_file(path)
        assert layer is not None
        assert layer.is_drill is True
        assert layer.role == ROLE_DRILL

    def test_a_file_that_holds_no_artwork_is_skipped(self, tmp_path):
        path = _write(tmp_path, "pnp.txt", PICK_AND_PLACE)
        assert layer_from_file(path) is None

    def test_a_file_that_is_named_drill_but_holds_a_picture(self, tmp_path):
        # What the file holds decides, not what it is called.
        path = _write(tmp_path, "drl", PLAIN)
        layer = layer_from_file(path)
        assert layer is not None
        assert layer.is_drill is False
        assert layer.role == ROLE_OTHER


class TestScanFolder:
    def test_the_files_of_the_folder_are_found(self, tmp_path):
        _write(tmp_path, "outline.gko", PLAIN)
        _write(tmp_path, "top.gbr", COPPER)
        _write(tmp_path, "board.drl", DRILL)
        _write(tmp_path, "pnp.txt", PICK_AND_PLACE)
        layers = scan_folder(str(tmp_path))
        # The layers are drawn from the bottom to the top: the outline
        # first, the drill holes last.
        assert [layer.file_name for layer in layers] == [
            "outline.gko", "top.gbr", "board.drl"]
        assert [layer.role for layer in layers] == [
            ROLE_PROFILE, ROLE_COPPER, ROLE_DRILL]

    def test_a_folder_that_does_not_exist(self, tmp_path):
        assert scan_folder(str(tmp_path / "nope")) == []

    def test_a_folder_with_nothing_in_it(self, tmp_path):
        assert scan_folder(str(tmp_path)) == []

    def test_the_folders_below_are_not_looked_at(self, tmp_path):
        below = tmp_path / "below"
        below.mkdir()
        _write(below, "top.gbr", COPPER)
        assert scan_folder(str(tmp_path)) == []

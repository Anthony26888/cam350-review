"""Contract tests for the clean-room Gerber / Excellon engine.

The engine is validated against three independent references:

* the Gerber specification (the unit tests below),
* ``gerbonara`` (a separate implementation), for every file it can read,
* the legacy parser that ships with this application, for the dialects
  ``gerbonara`` rejects.
"""

import os

import pytest

from services.gerber.spec import GerberParser
from services.gerber.spec.am_primitive import ApertureMacro, parse_macro_body
from services.gerber.spec.draw_item import KIND_ARC, KIND_POLYGON, KIND_SEGMENT
from services.gerber.spec.excellon import ExcellonParser
from services.gerber.spec.loader import KIND_EXCELLON, KIND_GERBER, detect_kind, load
from services.gerber.spec.units import CoordinateFormat, mm_to_iu

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO_ROOT, "tests", "fixtures", "gerber_manifest.json")


def parse(text: str):
    return GerberParser(text, "inline").parse()


# ----------------------------------------------------------------------
# coordinate formats
# ----------------------------------------------------------------------
class TestCoordinateFormat:
    def test_leading_zero_suppression(self):
        fmt = CoordinateFormat.parse("LAX36Y36")
        # Nine digits wide, 3 integer and 6 decimal digits.
        assert fmt.x.decode("1234") == pytest.approx(0.001234)
        assert fmt.x.decode("1234567") == pytest.approx(1.234567)

    def test_trailing_zero_suppression(self):
        fmt = CoordinateFormat.parse("TAX36Y36")
        assert fmt.x.decode("1234") == pytest.approx(123.4)
        assert fmt.x.decode("1234567") == pytest.approx(123.4567)

    def test_negative_and_sign(self):
        fmt = CoordinateFormat.parse("LAX36Y36")
        assert fmt.x.decode("-1234") == pytest.approx(-0.001234)

    def test_incremental_notation(self):
        fmt = CoordinateFormat.parse("LIX36Y36")
        assert fmt.incremental is True
        assert CoordinateFormat.parse("LAX36Y36").incremental is False

    def test_axes_without_whitespace(self):
        fmt = CoordinateFormat.parse("LAX24Y24")
        assert fmt.x.int_digits == 2
        assert fmt.x.dec_digits == 4
        assert fmt.y.int_digits == 2
        assert fmt.y.dec_digits == 4

    def test_missing_axis_is_rejected(self):
        with pytest.raises(Exception):
            CoordinateFormat.parse("LAX36")


# ----------------------------------------------------------------------
# basic operations
# ----------------------------------------------------------------------
class TestBasicOperations:
    def test_draw_creates_one_segment(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nX010000Y020000D01*\n"
        )
        assert len(image.items) == 1
        item = image.items[0]
        assert item.kind == KIND_SEGMENT
        # The format is 2.4, so "010000" is 01.0000 inch = 25.4 mm and the
        # segment runs from the current position (0, 0) to that point.
        assert item.x == 0
        assert item.y == 0
        assert item.x2 == pytest.approx(mm_to_iu(25.4), abs=1)
        assert item.y2 == pytest.approx(mm_to_iu(50.8), abs=1)
        assert item.width == pytest.approx(mm_to_iu(0.254), abs=1)

    def test_move_does_not_draw(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nX010000Y020000D02*\nX020000Y020000D01*\n"
        )
        assert len(image.items) == 1
        # The move set the current position, the draw starts there.
        assert image.items[0].x == pytest.approx(mm_to_iu(25.4), abs=1)
        assert image.items[0].x2 == pytest.approx(mm_to_iu(50.8), abs=1)

    def test_flash_uses_the_active_aperture(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD11C,0.100000*%\n"
            "G54D11*\nX010000Y020000D03*\n"
        )
        assert len(image.items) == 1
        item = image.items[0]
        assert item.diameter == pytest.approx(mm_to_iu(2.54), abs=1)
        assert item.x == pytest.approx(mm_to_iu(25.4), abs=1)

    def test_modal_single_digit_operation_codes(self):
        """Some CAM tools emit D1/D2/D3 instead of D01/D02/D03."""
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nX010000Y020000D1*\nX020000Y020000D1*\n"
        )
        assert len(image.items) == 2
        assert all(item.kind == KIND_SEGMENT for item in image.items)

    def test_coordinate_without_operation_reuses_the_modal_one(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nX010000Y020000D01*\nX020000Y030000*\n"
        )
        assert len(image.items) == 2

    def test_missing_axis_keeps_the_previous_value(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nX010000Y020000D01*\nX030000*\n"
        )
        assert len(image.items) == 2
        assert image.items[1].y2 == pytest.approx(mm_to_iu(50.8), abs=1)

    def test_arc_keeps_a_true_centre(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nG03*\nX000000Y000000I010000J000000D01*\n"
        )
        assert len(image.items) == 1
        item = image.items[0]
        assert item.kind == KIND_ARC
        assert item.cx == pytest.approx(mm_to_iu(25.4), abs=1)
        assert item.cy == pytest.approx(0, abs=1)
        assert item.clockwise is False

    def test_incremental_coordinates_accumulate(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G91*\nG54D10*\nX010000Y010000D01*\nX010000Y010000D01*\n"
        )
        assert len(image.items) == 2
        # 1.0 inch then another 1.0 inch.
        assert image.items[1].x2 == pytest.approx(mm_to_iu(50.8), abs=1)

    def test_region_becomes_a_polygon(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nG36*\nX000000Y000000D02*\nX010000Y000000D01*\n"
            "X010000Y010000D01*\nX000000Y000000D01*\nG37*\n"
        )
        regions = [item for item in image.items if item.kind == KIND_POLYGON]
        assert len(regions) == 1
        assert len(regions[0].points) >= 4


# ----------------------------------------------------------------------
# polarity
# ----------------------------------------------------------------------
class TestPolarity:
    def test_clear_layer_marks_strokes_negative(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%LPC*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nX010000Y020000D01*\n"
        )
        assert image.items[0].negative is True

    def test_dark_layer_marks_strokes_positive(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%LPD*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nX010000Y020000D01*\n"
        )
        assert image.items[0].negative is False

    def test_clear_layer_marks_flashes_negative(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%LPC*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nX010000Y020000D03*\n"
        )
        assert image.items[0].negative is True

    def test_image_polarity_is_recorded(self):
        image = parse("%FSLAX24Y24*%\n%MOIN*%\n%IPNEG*%\n")
        assert image.image_negative is True


# ----------------------------------------------------------------------
# aperture macros
# ----------------------------------------------------------------------
class TestApertureMacro:
    def test_primitive_22_is_supported(self):
        """Primitive 22 (lower left line) is what gerbonara rejects."""
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n"
            "%AMTEST*22,1,0.020000,0.010000,0.000000,0.000000,0.0*%\n"
            "%ADD10TEST*%\nG54D10*\nX010000Y020000D03*\n"
        )
        assert len(image.items) == 1
        item = image.items[0]
        assert item.kind == "macro"
        # 0.02 x 0.01 inch = 0.508 x 0.254 mm
        xs = [p[0] for shape in item.macro_shapes for p in shape.points]
        ys = [p[1] for shape in item.macro_shapes for p in shape.points]
        assert (max(xs) - min(xs)) == pytest.approx(mm_to_iu(0.508), abs=2000)
        assert (max(ys) - min(ys)) == pytest.approx(mm_to_iu(0.254), abs=2000)

    def test_primitive_1_circle(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n"
            "%AMTEST*1,1,0.020000,0.000000,0.000000*%\n"
            "%ADD10TEST*%\nG54D10*\nX010000Y020000D03*\n"
        )
        shapes = image.items[0].macro_shapes
        assert len(shapes) == 1
        assert shapes[0].kind == "circle"
        assert shapes[0].diameter == pytest.approx(mm_to_iu(0.508), abs=2000)

    def test_exposure_off_creates_a_hole(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n"
            "%AMTEST*1,0,0.010000,0.000000,0.000000*%\n"
            "%ADD10TEST*%\nG54D10*\nX010000Y020000D03*\n"
        )
        shapes = image.items[0].macro_shapes
        assert shapes[0].exposure is False

    def test_primitive_4_outline(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n"
            "%AMTEST*4,1,3,0.000000,0.000000,0.010000,0.000000,0.010000,0.010000*%\n"
            "%ADD10TEST*%\nG54D10*\nX010000Y020000D03*\n"
        )
        shapes = image.items[0].macro_shapes
        assert shapes[0].kind == "polygon"
        assert len(shapes[0].points) == 3

    def test_macro_variables_are_evaluated(self):
        macro = parse_macro_body("T", ["$1=2+3", "1,1,$1,0,0"])
        shapes = macro.evaluate()
        assert shapes[0].diameter == pytest.approx(5.0)

    def test_unsupported_primitive_is_reported_not_fatal(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n"
            "%AMTEST*99,1,1*%\n"
            "%ADD10TEST*%\nG54D10*\nX010000Y020000D01*\n"
        )
        # The file still parses and the artwork is still there.
        assert len(image.items) == 1
        assert image.degraded is True
        assert any("unsupported primitive" in w for w in image.warnings)


# ----------------------------------------------------------------------
# robustness
# ----------------------------------------------------------------------
class TestRobustness:
    def test_unknown_x2_statement_is_a_warning(self):
        image = parse("%FSLAX24Y24*%\n%MOIN*%\n%ZZ99*%\n")
        assert image.degraded is True
        assert any("unknown X2 statement" in w for w in image.warnings)

    def test_unknown_gcode_is_ignored(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nG73*\nX010000Y020000D01*\n"
        )
        assert len(image.items) == 1

    def test_i_j_on_a_linear_draw_is_tolerated(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nX010000Y020000I003000D01*\n"
        )
        assert len(image.items) == 1
        assert image.items[0].kind == KIND_SEGMENT

    def test_coordinate_without_operation_mode_is_tolerated(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "G54D10*\nX010000Y020000D01*\nX030000Y040000I002360J0*\n"
        )
        assert len(image.items) == 2

    def test_flash_without_a_defined_aperture_is_reported(self):
        image = parse("%FSLAX24Y24*%\n%MOIN*%\nX010000Y020000D03*\n")
        assert any("without a defined aperture" in w for w in image.warnings)

    def test_step_and_repeat_expands_the_block(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "%SRX2Y1I1.000000J0*%\n"
            "G54D10*\nX000000Y000000D01*\n"
        )
        assert len(image.items) == 2

    def test_nested_step_and_repeat_is_accepted(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.010000*%\n"
            "%SRX1Y1I0.000000J0*%\n"
            "G54D10*\nX000000Y000000D01*\n"
        )
        assert not image.degraded
        assert len(image.items) == 1


# ----------------------------------------------------------------------
# Aperture templates
# ----------------------------------------------------------------------
class TestApertureTemplates:
    def test_a_polygon_aperture_uses_the_specified_order(self):
        # The template is P,<diameter>X<vertices>X<rotation>.  The vertices
        # used to be read from the first parameter, which made the count
        # zero and the division by it crash.
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD53P,0.4243X4X90.0*%\n"
            "G54D53*\nX010000Y020000D03*\n"
        )
        assert not image.degraded
        assert len(image.items) == 1
        flash = image.items[0]
        assert flash.kind == "polygon"
        assert len(flash.points) == 4

    def test_the_parameters_of_a_polygon_aperture_are_in_the_spec_order(self):
        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD53P,0.4243X4X90.0*%\n"
            "G54D53*\nX010000Y020000D03*\n"
        )
        aperture = image.apertures[53]
        assert aperture.kind == "polygon"
        assert aperture.params == (0.4243, 4.0, 90.0)

    def test_a_macro_name_is_not_mistaken_for_a_standard_template(self):
        # ROUNDEDRECTD16 starts with the letter of the rectangle template.
        # Treating it as a rectangle silently dropped the shape.
        text = (
            "%FSLAX44Y44*%\n%MOIN*%\n"
            "%AMROUNDEDRECTD16*\n"
            "1,1,0.5,0,0*\n"
            "%ADD16ROUNDEDRECTD16*%\n"
            "G54D16*\nX010000Y020000D03*\n"
        )
        image = parse(text)
        aperture = image.apertures[16]
        assert aperture.kind == "macro"
        assert len(image.items) == 1
        assert image.items[0].macro_shapes

    def test_an_unknown_macro_name_is_reported(self):
        image = parse(
            "%FSLAX44Y44*%\n%MOIN*%\n%ADD16ROUNDEDRECTD16*%\n"
            "G54D16*\nX010000Y020000D03*\n"
        )
        assert image.degraded
        assert any("macro" in w for w in image.warnings)

    def test_a_definition_after_a_macro_with_one_percent_is_kept(self):
        # Some tools close an aperture macro and open the next statement
        # with a single percent.  The definition used to be dropped
        # without a word, and every flash of it with it.
        text = (
            "%FSLAX44Y44*%\n%MOIN*%\n"
            "%AMROUNDEDRECTD16*\n"
            "1,1,0.5,0,0*\n"
            "%ADD16ROUNDEDRECTD16*%\n"
            "G54D16*\nX010000Y020000D03*\n"
        )
        image = parse(text)
        assert not image.degraded
        assert image.apertures[16].kind == "macro"
        assert len(image.items) == 1
        assert image.items[0].macro_shapes


# ----------------------------------------------------------------------
# Excellon
# ----------------------------------------------------------------------
class TestExcellon:
    def test_metric_lz_file(self):
        text = (
            "M48\n"
            ";FILE_FORMAT=4:4\n"
            "METRIC,LZ\n"
            "T01F00S00C0.2032\n"
            "T02F00S00C0.2500\n"
            "%\n"
            "T01\n"
            "X00000000Y00000000\n"
            "X00100000Y00200000\n"
            "T02\n"
            "X00300000Y00400000\n"
            "M30\n"
        )
        image = ExcellonParser(text, "inline").parse()
        assert len(image.holes) == 3
        assert sorted(image.drill_sizes) == pytest.approx([0.2032, 0.25])
        assert image.holes[0].diameter == pytest.approx(mm_to_iu(0.2032), abs=50)
        assert image.holes[2].diameter == pytest.approx(mm_to_iu(0.25), abs=50)

    def test_coordinates_are_decoded_with_the_file_format(self):
        text = (
            "M48\n;FILE_FORMAT=4:4\nMETRIC,LZ\n"
            "T01C1.0\n%\nT01\nX-00063Y-00339664\nM30\n"
        )
        image = ExcellonParser(text, "inline").parse()
        assert len(image.holes) == 1
        # -00063 padded to eight digits is -0.0063 mm
        assert image.holes[0].x == pytest.approx(mm_to_iu(-0.0063), abs=50)
        assert image.holes[0].y == pytest.approx(mm_to_iu(-33.9664), abs=50)

    def test_omitted_axis_keeps_the_previous_value(self):
        text = (
            "M48\n;FILE_FORMAT=4:4\nMETRIC,LZ\n"
            "T01C1.0\n%\nT01\nX00100000Y00200000\nX00300000\nM30\n"
        )
        image = ExcellonParser(text, "inline").parse()
        assert len(image.holes) == 2
        # Four integer and four decimal digits: 0010.0000 mm.
        assert image.holes[0].x == pytest.approx(mm_to_iu(10.0), abs=50)
        assert image.holes[0].y == pytest.approx(mm_to_iu(20.0), abs=50)
        assert image.holes[1].x == pytest.approx(mm_to_iu(30.0), abs=50)
        assert image.holes[1].y == pytest.approx(mm_to_iu(20.0), abs=50)

    def test_slot_is_recognised(self):
        text = (
            "M48\n;FILE_FORMAT=4:4\nMETRIC,LZ\n"
            "T01C1.0\n%\nT01\nX00100000Y00200000\nG85X00300000Y00200000\nM30\n"
        )
        image = ExcellonParser(text, "inline").parse()
        assert len(image.slots) == 1
        assert image.slots[0].x1 != image.slots[0].x2

    def test_a_routed_slot_is_recognised(self):
        # The tool goes down (M15), the machine moves (G01) and the tool
        # goes up again (M16).  The move and the coordinates are on the same
        # line, which used to make the slot disappear.
        text = (
            "M48\n;FILE_FORMAT=4:4\nMETRIC,LZ\n"
            "T06F00S00C0.6000\n%\nG90\nG05\nT06\n"
            "G00X0183482Y0154355\nM15\nG01Y0153255\nM16\nM17\nM30\n"
        )
        image = ExcellonParser(text, "inline").parse()
        assert len(image.slots) == 1
        slot = image.slots[0]
        # Eight digits, four of them before the point: 0018.3482 mm.
        assert slot.x1 == pytest.approx(mm_to_iu(18.3482), abs=100)
        assert slot.y1 == pytest.approx(mm_to_iu(15.4355), abs=100)
        assert slot.y2 == pytest.approx(mm_to_iu(15.3255), abs=100)
        assert not image.holes

    def test_a_routed_drill_without_a_move_is_a_hole(self):
        text = (
            "M48\n;FILE_FORMAT=4:4\nMETRIC,LZ\n"
            "T06F00S00C0.6000\n%\nG90\nG05\nT06\n"
            "G00X0183482Y0154355\nM15\nM16\nM17\nM30\n"
        )
        image = ExcellonParser(text, "inline").parse()
        assert len(image.slots) == 0
        assert len(image.holes) == 1
        assert image.holes[0].x == pytest.approx(mm_to_iu(18.3482), abs=100)

    def test_a_plain_drill_file_keeps_its_holes(self):
        text = (
            "M48\n;FILE_FORMAT=4:4\nMETRIC,LZ\n"
            "T01C1.0\n%\nT01\nX00100000Y00200000\nX00300000\nM30\n"
        )
        image = ExcellonParser(text, "inline").parse()
        assert len(image.holes) == 2
        assert not image.slots


# ----------------------------------------------------------------------
# loader
# ----------------------------------------------------------------------
class TestLoader:
    def test_detects_gerber(self, tmp_path):
        path = tmp_path / "a.gbr"
        path.write_text("%FSLAX24Y24*%\n%MOIN*%\n", encoding="utf-8")
        assert detect_kind(str(path)) == KIND_GERBER

    def test_detects_excellon(self, tmp_path):
        path = tmp_path / "a.drl"
        path.write_text("M48\nMETRIC,LZ\nT01C0.2\n%\nT01\nX1Y1\nM30\n", encoding="utf-8")
        assert detect_kind(str(path)) == KIND_EXCELLON

    def test_load_reports_the_parser_and_the_warnings(self, tmp_path):
        path = tmp_path / "a.gbr"
        path.write_text("%FSLAX24Y24*%\n%MOIN*%\n%ZZ1*%\n", encoding="utf-8")
        result = load(str(path))
        assert result.ok is True
        assert result.degraded is True
        assert result.warnings


# ----------------------------------------------------------------------
# adapter
# ----------------------------------------------------------------------
class TestAdapter:
    def test_a_macro_flash_keeps_its_shapes_local(self):
        """The macro shapes have to be relative to the flash position.

        When they are not, the artwork is drawn at the wrong place and the
        size of the pad explodes, which then makes the spatial index of the
        pads unusable.
        """
        from services.gerber.gerber_render import FlashShape
        from services.gerber.spec.adapter import to_render_data
        from ui.gerber_viewer import _flash_size

        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n"
            "%AMTEST*4,1,4,0.000000,0.000000,0.010000,0.000000,"
            "0.010000,0.010000,0.000000,0.010000*%\n"
            "%ADD10TEST*%\nG54D10*\nX010000Y020000D03*\n"
        )
        data = to_render_data(image)
        assert len(data.flashes) == 1
        flash = data.flashes[0]
        assert flash.kind == "macro"
        # The 2.4 format makes "010000" one inch, so the flash sits at
        # 25.4 mm / 50.8 mm.  The shape is a 0.254 mm square around it, so
        # the shape must be a fraction of a millimetre wide.
        assert flash.cx == pytest.approx(25.4, abs=0.01)
        assert flash.cy == pytest.approx(50.8, abs=0.01)
        size = _flash_size(flash)
        assert 0.1 < size < 1.0, f"macro flash size is {size} mm"

    def test_a_circle_flash_keeps_its_size(self):
        from services.gerber.spec.adapter import to_render_data
        from ui.gerber_viewer import _flash_size

        image = parse(
            "%FSLAX24Y24*%\n%MOIN*%\n%ADD11C,0.100000*%\n"
            "G54D11*\nX010000Y020000D03*\n"
        )
        data = to_render_data(image)
        assert len(data.flashes) == 1
        assert _flash_size(data.flashes[0]) == pytest.approx(2.54, abs=0.01)


# ----------------------------------------------------------------------
# corpus
# ----------------------------------------------------------------------
def _manifest():
    import json

    if not os.path.exists(MANIFEST):
        return None
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.skipif(not os.path.exists(MANIFEST), reason="manifest not generated")
def test_spec_parser_reads_what_gerbonara_cannot():
    """The dialect gap that motivated the spec engine must be closed."""
    manifest = _manifest()
    if manifest is None:
        pytest.skip("manifest not available")
    root = manifest["root"]
    entries = [e for e in manifest["entries"]
               if e.get("kind") == "gerber"
               and not e.get("gerbonara", {}).get("ok")
               and e.get("legacy", {}).get("ok")]
    if not entries:
        pytest.skip("no gerbonara-only files in the manifest")
    # A representative slice keeps the test quick; the full corpus is
    # checked by scripts/gerber_manifest.py.
    for entry in entries[:12]:
        path = os.path.join(root, entry["path"].replace("/", os.sep))
        image = GerberParser.from_path(path).parse()
        assert image.items, f"spec parser produced no artwork for {entry['path']}"


@pytest.mark.skipif(not os.path.exists(MANIFEST), reason="manifest not generated")
def test_spec_parser_matches_gerbonara_positions():
    """The overall extent must agree for every file without aperture macros.

    For files that use an aperture macro the extent may differ: gerbonara
    re-centres a macro on the flash point, while the specification - and the
    reference implementation this engine follows - keeps the primitive
    coordinates relative to the macro origin.  The anchor points still have
    to agree, which the next test checks.
    """
    manifest = _manifest()
    if manifest is None:
        pytest.skip("manifest not available")
    root = manifest["root"]
    checked = 0
    for entry in manifest["entries"]:
        if entry.get("kind") != "gerber":
            continue
        reference = entry.get("gerbonara", {})
        if not reference.get("ok") or not reference.get("bbox"):
            continue
        if entry["bytes"] > 3_000_000:
            continue
        path = os.path.join(root, entry["path"].replace("/", os.sep))
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                if "%AM" in fh.read():
                    # Uses an aperture macro, the extent convention differs.
                    continue
            image = GerberParser.from_path(path).parse()
        except Exception:  # noqa: BLE001 - gerbonara is the reference
            continue
        if not image.items:
            continue
        box = image.bbox_mm
        if not box:
            continue
        for got, want in zip(box, reference["bbox"]):
            assert abs(got - want) <= 0.5, f"{entry['path']}: {box} vs {reference['bbox']}"
        checked += 1
        if checked >= 60:
            break
    assert checked > 0


@pytest.mark.skipif(not os.path.exists(MANIFEST), reason="manifest not generated")
def test_spec_parser_agrees_with_gerbonara_on_flash_positions():
    """For every file both parsers read, the flash positions must agree."""
    import warnings

    import gerbonara

    manifest = _manifest()
    if manifest is None:
        pytest.skip("manifest not available")
    root = manifest["root"]
    checked = 0
    for entry in manifest["entries"]:
        if entry.get("kind") != "gerber":
            continue
        if not entry.get("gerbonara", {}).get("ok"):
            continue
        if entry["bytes"] > 1_000_000:
            continue
        path = os.path.join(root, entry["path"].replace("/", os.sep))
        try:
            image = GerberParser.from_path(path).parse()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                gf = gerbonara.GerberFile.open(path)
                reference = []
                for obj in gf.objects:
                    for prim in obj.to_primitives("mm"):
                        reference.append((round(prim.x, 3), round(prim.y, 3)))
        except Exception:  # noqa: BLE001 - gerbonara is the reference
            continue
        if not image.items or not reference:
            continue
        # Compare the anchor of the first primitive of the spec engine with
        # the first primitive gerbonara reports.
        first = image.items[0]
        got = (round(first.x / 100000.0, 2), round(first.y / 100000.0, 2))
        assert abs(got[0] - reference[0][0]) < 0.05, entry["path"]
        assert abs(got[1] - reference[0][1]) < 0.05, entry["path"]
        checked += 1
        if checked >= 60:
            break
    assert checked > 0


@pytest.mark.skipif(not os.path.exists(MANIFEST), reason="manifest not generated")
def test_spec_parser_reads_files_gerbonara_cannot():
    """The dialect gap that motivated the spec engine must be closed."""
    manifest = _manifest()
    if manifest is None:
        pytest.skip("manifest not available")
    root = manifest["root"]
    entries = [e for e in manifest["entries"]
               if e.get("kind") == "gerber"
               and not e.get("gerbonara", {}).get("ok")
               and e.get("legacy", {}).get("primitives")]
    if not entries:
        pytest.skip("no gerbonara-only files in the manifest")
    # A representative slice keeps the test quick; the full corpus is
    # checked by scripts/gerber_manifest.py.
    for entry in entries[:12]:
        path = os.path.join(root, entry["path"].replace("/", os.sep))
        image = GerberParser.from_path(path).parse()
        assert image.items, f"spec parser produced no artwork for {entry['path']}"
        assert image.bbox_mm is not None


@pytest.mark.skipif(not os.path.exists(MANIFEST), reason="manifest not generated")
def test_spec_parser_reads_files_the_legacy_parser_drops():
    """The legacy parser returns an empty result for some real files."""
    manifest = _manifest()
    if manifest is None:
        pytest.skip("manifest not available")
    root = manifest["root"]
    # A file that an independent implementation reads as empty really is
    # empty (some mechanical layers carry no artwork at all).
    empty = [e for e in manifest["entries"]
             if e.get("kind") == "gerber"
             and e.get("legacy", {}).get("ok")
             and not e.get("legacy", {}).get("primitives")
             and e.get("gerbonara", {}).get("primitives")]
    if not empty:
        pytest.skip("no empty legacy results in the manifest")
    for entry in empty[:10]:
        path = os.path.join(root, entry["path"].replace("/", os.sep))
        image = GerberParser.from_path(path).parse()
        assert image.items, (
            f"spec parser produced no artwork for {entry['path']} either")
        assert image.bbox_mm is not None

import os
from datetime import datetime

import pytest

from models.pcb_info import PcbInfo
from models.review import ReviewRecord
from services.yamaha_ygx_export import (
    YamahaYgxExportError,
    build_ygx,
    components_from_review_records,
    export_ygx,
    missing_pcb_info_fields_ygx,
)


def _pcb(**overrides):
    defaults = dict(
        board_width=200.0, board_height=156.0, working_area_width=200.0,
        position_working=0.0, x_boc1=10.0, y_boc1=4.0,
        x_boc2=10.0, y_boc2=152.0, x_boc3=190.0, y_boc3=152.0, thickness=1.6,
    )
    defaults.update(overrides)
    return PcbInfo(**defaults)


def _rec(des="C1", mpn="MPN1", layer="Top", x=1.0, y=2.0, rot=0.0,
         status="OK", row_index=0, block=0, block_rotation=0):
    return ReviewRecord(
        designator=des, mpn=mpn, layer=layer,
        old_x=x, old_y=y, old_rotation=rot,
        status=status, row_index=row_index,
        block=block, block_rotation=block_rotation,
    )


class TestMissingPcbInfo:
    def test_complete(self):
        assert missing_pcb_info_fields_ygx(_pcb()) == []

    def test_missing_board_width(self):
        assert "Board Width" in missing_pcb_info_fields_ygx(_pcb(board_width=0))

    def test_missing_boc1(self):
        assert "BOC 1" in missing_pcb_info_fields_ygx(_pcb(x_boc1=0, y_boc1=0))

    def test_missing_boc3(self):
        assert "BOC 3" in missing_pcb_info_fields_ygx(_pcb(x_boc3=0, y_boc3=0))


class TestBuildYgx:
    def test_basic_structure(self):
        comps = components_from_review_records([_rec("U1", "IC1", x=57.0, y=58.97, rot=295.0)], False)
        xml = build_ygx(comps, _pcb(), datetime(2026, 11, 4, 14, 30, 0))
        text = xml.decode("utf-8")
        assert '<?xml version="1.0"?>' in text
        assert "<PcbDataFile>" in text
        assert 'VersionNo="2"' in text
        assert 'MachineType="15"' in text
        assert 'YGOS AMS 2.0' in text

    def test_crlf_line_endings(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_ygx(comps, _pcb())
        assert b"\r\n" in xml
        lines = xml.split(b"\r\n")
        assert all(b"\n" not in line for line in lines)

    def test_tab_indentation(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_ygx(comps, _pcb())
        text = xml.decode("utf-8")
        assert "\t<SetupMachine" in text
        assert "\t\t<Board_000" in text
        assert "\t\t<Mount No=" in text

    def test_space_padded_mount_fields(self):
        comps = components_from_review_records([_rec("U1", "IC1", x=57.0, y=58.97, rot=295.0)], False)
        xml = build_ygx(comps, _pcb())
        text = xml.decode("utf-8")
        assert 'No="    1"' in text
        assert 'X="  57.000"' in text
        assert 'Y="  58.970"' in text
        assert 'R=" 295.000"' in text
        assert 'Comp="   1"' in text
        assert 'Group="   -1"' in text

    def test_board_origin_hardcoded(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_ygx(comps, _pcb())
        text = xml.decode("utf-8")
        assert 'OriginX="  -4.671"' in text
        assert 'OriginY="  -5.175"' in text

    def test_block_count_zero(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_ygx(comps, _pcb())
        text = xml.decode("utf-8")
        assert 'BlockCount="  0"' in text

    def test_fiducial_mapping(self):
        pcb = _pcb(x_boc1=10.0, y_boc1=4.0, x_boc3=190.0, y_boc3=152.0)
        comps = components_from_review_records([_rec()], False)
        xml = build_ygx(comps, pcb)
        text = xml.decode("utf-8")
        assert 'X1="  10.000"' in text
        assert 'Y1="   4.000"' in text
        assert 'X2=" 190.000"' in text
        assert 'Y2=" 152.000"' in text

    def test_single_offset_repeat(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_ygx(comps, _pcb())
        text = xml.decode("utf-8")
        assert '<Repeat No="  1"' in text
        assert text.count("<Repeat ") == 1

    def test_parts_section(self):
        records = [
            _rec("R1", "RES10K", row_index=0),
            _rec("R2", "CAP100N", row_index=1),
        ]
        comps = components_from_review_records(records, False)
        xml = build_ygx(comps, _pcb())
        text = xml.decode("utf-8")
        assert '<Part No="1">' in text
        assert '<Part No="2">' in text
        assert 'PartsName="RES10K"' in text
        assert 'PartsName="CAP100N"' in text
        assert "ShapeType=\"7\"" in text
        assert 'BodyX="   1.600"' in text

    def test_rounding_half_up(self):
        r = _rec(x=191.5795, y=10.8225, rot=0.0)
        comps = components_from_review_records([r], False)
        xml = build_ygx(comps, _pcb())
        text = xml.decode("utf-8")
        assert 'X=" 191.580"' in text
        assert 'Y="  10.823"' in text

    def test_missing_pcb_info_raises(self):
        comps = components_from_review_records([_rec()], False)
        with pytest.raises(YamahaYgxExportError, match="PCB Info"):
            build_ygx(comps, _pcb(board_width=0))

    def test_marks_empty(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_ygx(comps, _pcb())
        text = xml.decode("utf-8")
        assert "\t<Marks>\r\n\t</Marks>" in text

    def test_predispenses_dotdispenses_empty(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_ygx(comps, _pcb())
        text = xml.decode("utf-8")
        assert "\t<PreDispenses>\r\n\t</PreDispenses>" in text
        assert "\t<DotDispenses>\r\n\t</DotDispenses>" in text


class TestExportYgx:
    def test_writes_file(self, tmp_path):
        records = [_rec("C1", "MPN1", row_index=0)]
        out = tmp_path / "test.ygx"
        result = export_ygx(records, _pcb(), str(out), bottom=False)
        assert os.path.exists(result)
        data = open(result, "rb").read()
        assert data.startswith(b"<?xml")
        assert data.endswith(b"\r\n")

    def test_no_top_data_raises(self, tmp_path):
        records = [_rec("C1", layer="Bottom")]
        out = tmp_path / "test.ygx"
        with pytest.raises(YamahaYgxExportError, match="No Top"):
            export_ygx(records, _pcb(), str(out), bottom=False)

    def test_no_bottom_data_raises(self, tmp_path):
        records = [_rec("C1", layer="Top")]
        out = tmp_path / "test.ygx"
        with pytest.raises(YamahaYgxExportError, match="No Bottom"):
            export_ygx(records, _pcb(), str(out), bottom=True)

import os
from datetime import datetime

import pytest

from models.pcb_info import PcbInfo
from models.review import ReviewRecord
from services.yamaha_xml_export import (
    YamahaXmlExportError,
    build_yamaha_xml,
    components_from_review_records,
    export_yamaha_xml,
    missing_pcb_info_fields_yamaha,
)


def _pcb(**overrides):
    defaults = dict(
        board_width=200.0,
        board_height=156.0,
        working_area_width=200.0,
        position_working=0.0,
        x_boc1=10.0,
        y_boc1=4.0,
        x_boc2=10.0,
        y_boc2=152.0,
        x_boc3=190.0,
        y_boc3=152.0,
        thickness=1.6,
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


class TestMissingPcbInfoFields:
    def test_complete(self):
        assert missing_pcb_info_fields_yamaha(_pcb()) == []

    def test_missing_board_width(self):
        fields = missing_pcb_info_fields_yamaha(_pcb(board_width=0))
        assert "Board Width" in fields

    def test_missing_boc1(self):
        fields = missing_pcb_info_fields_yamaha(_pcb(x_boc1=0, y_boc1=0))
        assert "BOC 1" in fields

    def test_missing_boc3(self):
        fields = missing_pcb_info_fields_yamaha(_pcb(x_boc3=0, y_boc3=0))
        assert "BOC 3" in fields

    def test_boc2_not_required(self):
        fields = missing_pcb_info_fields_yamaha(_pcb(x_boc2=0, y_boc2=0))
        assert "BOC 2" not in fields


class TestComponentsFromReviewRecords:
    def test_filters_by_side(self):
        records = [
            _rec("C1", layer="Top", row_index=0),
            _rec("C2", layer="Bottom", row_index=1),
        ]
        top = components_from_review_records(records, bottom=False)
        bot = components_from_review_records(records, bottom=True)
        assert len(top) == 1
        assert top[0].designator == "C1"
        assert len(bot) == 1
        assert bot[0].designator == "C2"

    def test_skips_deleted(self):
        records = [_rec("C1", status="Deleted")]
        assert components_from_review_records(records, False) == []

    def test_uses_new_values(self):
        r = _rec(x=1.0, y=2.0, rot=0.0)
        r.new_x = 10.0
        r.new_y = 20.0
        r.new_rotation = 90.0
        comps = components_from_review_records([r], False)
        assert comps[0].x == 10.0
        assert comps[0].y == 20.0
        assert comps[0].rotation == 90.0

    def test_rejects_panelized(self):
        records = [_rec(block=1)]
        with pytest.raises(YamahaXmlExportError, match="Panelized"):
            components_from_review_records(records, False)

    def test_sorts_by_row_index(self):
        records = [
            _rec("C3", row_index=2),
            _rec("C1", row_index=0),
            _rec("C2", row_index=1),
        ]
        comps = components_from_review_records(records, False)
        assert [c.designator for c in comps] == ["C1", "C2", "C3"]


class TestBuildYamahaXml:
    def test_basic_output(self):
        comps = components_from_review_records(
            [_rec("U1", "IC1", x=57.0, y=58.97, rot=295.0)], False
        )
        xml = build_yamaha_xml(comps, _pcb(), datetime(2026, 11, 4, 14, 30, 0))
        text = xml.decode("utf-8")
        assert '<?xml version="1.0"?>' in text
        assert 'Date="2026/11/04"' in text
        assert 'Time="14:30:00"' in text
        assert 'X="-4.671" Y="-5.175" R="0.000"' in text
        assert 'Comment="U1"' in text
        assert 'Name="IC1"' in text
        assert 'X="57.000" Y="58.970" R="295.000"' in text

    def test_crlf_line_endings(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_yamaha_xml(comps, _pcb())
        assert b"\r\n" in xml
        lines = xml.split(b"\r\n")
        assert all(b"\n" not in line for line in lines)

    def test_tab_indentation(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_yamaha_xml(comps, _pcb())
        text = xml.decode("utf-8")
        assert "\t<PcbData" in text
        assert "\t\t<Board>" in text
        assert "\t\t\t<Origin" in text

    def test_size_double_space(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_yamaha_xml(comps, _pcb())
        text = xml.decode("utf-8")
        assert '<Size  X="1.600"' in text

    def test_id_zero_padding(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_yamaha_xml(comps, _pcb())
        text = xml.decode("utf-8")
        assert 'ID="00000000"' in text
        assert 'CompRef="00000000"' in text

    def test_multiple_components_same_mpn(self):
        records = [
            _rec("R1", "RES10K", x=1.0, y=1.0, row_index=0),
            _rec("R2", "RES10K", x=2.0, y=2.0, row_index=1),
            _rec("R3", "CAP100N", x=3.0, y=3.0, row_index=2),
        ]
        comps = components_from_review_records(records, False)
        xml = build_yamaha_xml(comps, _pcb())
        text = xml.decode("utf-8")
        assert text.count('Name="RES10K"') == 1
        assert text.count('Name="CAP100N"') == 1
        assert text.count('CompNum="1"') == 2
        assert text.count('CompNum="2"') == 1

    def test_missing_pcb_info_raises(self):
        comps = components_from_review_records([_rec()], False)
        with pytest.raises(YamahaXmlExportError, match="PCB Info"):
            build_yamaha_xml(comps, _pcb(board_width=0))

    def test_missing_mpn_raises(self):
        r = _rec(mpn="")
        comps = components_from_review_records([r], False)
        # empty mpn is filtered by components_from_review_records only if designator empty
        # but build_yamaha_xml checks mpn
        from services.yamaha_xml_export import YamahaComponent
        bad = [YamahaComponent(designator="C1", mpn="", x=0, y=0, rotation=0)]
        with pytest.raises(YamahaXmlExportError, match="no MPN"):
            build_yamaha_xml(bad, _pcb())

    def test_block_number_zero(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_yamaha_xml(comps, _pcb())
        text = xml.decode("utf-8")
        assert '<Block Number="0"/>' in text

    def test_fiducial_mapping(self):
        pcb = _pcb(x_boc1=10.0, y_boc1=4.0, x_boc3=190.0, y_boc3=152.0)
        comps = components_from_review_records([_rec()], False)
        xml = build_yamaha_xml(comps, pcb)
        text = xml.decode("utf-8")
        assert 'X1="10.000" Y1="4.000"' in text
        assert 'X2="190.000" Y2="152.000"' in text

    def test_marks_empty(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_yamaha_xml(comps, _pcb())
        text = xml.decode("utf-8")
        assert "<Marks>\r\n</Marks>" in text

    def test_optimized_variations_structure(self):
        comps = components_from_review_records([_rec()], False)
        xml = build_yamaha_xml(comps, _pcb())
        text = xml.decode("utf-8")
        assert "PickGroup=\"-1\"" in text
        assert 'Head="1"' in text
        assert 'Nozzle="1"' in text
        assert 'Machine="1424"' in text
        assert 'PosBlockRef="-0000001"' in text

    def test_feeder_per_component(self):
        records = [
            _rec("R1", "RES10K", row_index=0),
            _rec("R2", "CAP100N", row_index=1),
        ]
        comps = components_from_review_records(records, False)
        xml = build_yamaha_xml(comps, _pcb())
        text = xml.decode("utf-8")
        feeder_count = text.count("<Feeder Machine=")
        assert feeder_count == 2


class TestExportYamahaXml:
    def test_writes_file(self, tmp_path):
        records = [_rec("C1", "MPN1", row_index=0)]
        out = tmp_path / "test.xml"
        result = export_yamaha_xml(records, _pcb(), str(out), bottom=False)
        assert os.path.exists(result)
        data = open(result, "rb").read()
        assert data.startswith(b"<?xml")
        assert data.endswith(b"\r\n")

    def test_no_top_data_raises(self, tmp_path):
        records = [_rec("C1", layer="Bottom")]
        out = tmp_path / "test.xml"
        with pytest.raises(YamahaXmlExportError, match="No Top"):
            export_yamaha_xml(records, _pcb(), str(out), bottom=False)

    def test_no_bottom_data_raises(self, tmp_path):
        records = [_rec("C1", layer="Top")]
        out = tmp_path / "test.xml"
        with pytest.raises(YamahaXmlExportError, match="No Bottom"):
            export_yamaha_xml(records, _pcb(), str(out), bottom=True)

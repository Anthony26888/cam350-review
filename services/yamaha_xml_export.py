from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence

from models.pcb_info import PcbInfo
from models.review import ReviewRecord
from services.bom_compare import is_bottom_layer
from utils.path_utils import resource_path

_TEMPLATE_PATH = resource_path("assets/yamaha_template.xml")

_COMPONENT_BODY = (
    '\t<Component No="{no}" Name="{name}" Comment="" ID="{id}" DatabaseNo="{db_no}" FixedComp="0">\r\n'
    '\t\t<Library Use="0"/>\r\n'
    '\t\t<CompNumList Machine="1424" IBMFNo="{ibmf_no}"/>\r\n'
    '\t\t<Feeder Package="0" Type="0" Pitch="0"/>\r\n'
    '\t\t<Shape Type="7">\r\n'
    '\t\t\t<Size  X="1.600" Y="3.200" Z="0.500"/>\r\n'
    '\t\t\t<Lead>\r\n'
    '\t\t\t\t<Common RulerOffset="3"/>\r\n'
    '\t\t\t</Lead>\r\n'
    '\t\t\t<AlignSize X="1.700" Y="3.300" Z="0.400"/>\r\n'
    '\t\t</Shape>\r\n'
    '\t\t<Vision Module="0">\r\n'
    '\t\t\t<Light Setting="0" AllLightOn="0"/>\r\n'
    '\t\t\t<Recognition AutoThreshold="1" LightLevel="3" Threshold="30" Torelance="30" SerachArea="0.800" InsideRecognition="0"/>\r\n'
    '\t\t\t<Datum Angle="0"/>\r\n'
    '\t\t\t<MultiMACS Use="0"/>\r\n'
    '\t\t\t<Co-Planarity CompIntensity="0" Level="0" Threshold="0" Ruler="0"/>\r\n'
    '\t\t\t<DDD DDDThreshold="70" DDDLightCoax="4" DDDLightMain="3" DDDLightSide="4" DDDBrightArea="25" DDDHeightCheck="0.000" DDDExecPass="3"/>\r\n'
    '\t\t\t<Laser ErrDetect="0"/>\r\n'
    '\t\t</Vision>\r\n'
    '\t\t<PickMount>\r\n'
    '\t\t\t<Nozzle Required="3"/>\r\n'
    '\t\t\t<Vacuum Check="1"/>\r\n'
    '\t\t\t<Pick Timer="0" Height="0.000" Action="0" Speed="0" Angle="0" Level="30" CorrectPos="0" SingleDir="0" Down="0" Up="0" SecondSrvDown="0" SecondSrvUp="0"/>\r\n'
    '\t\t\t<Mount Timer="0" Height="0.500" Action="0" Speed="0" XYSpeed="0" VacuumLevel="30" SingleDir="0" Down="0" Up="0" SecondSrvDown="0" SecondSrvUp="0"/>\r\n'
    '\t\t\t<Dump Point="0" Retry="3"/>\r\n'
    '\t\t\t<ConvY Speed="3"/>\r\n'
    '\t\t\t<Count OutStop="0"/>\r\n'
    '\t\t</PickMount>\r\n'
    '\t\t<Dispense>\r\n'
    '\t\t\t<Nozzle Size="3" Shot="0" Unit="0"/>\r\n'
    '\t\t\t<Position>\r\n'
    '\t\t\t\t<Ref X="0.000" Y="0.000" R="0.000"/>\r\n'
    '\t\t\t\t<DotExt X="0.000" Y="0.000"/>\r\n'
    '\t\t\t\t<Amount X="1" Y="1"/>\r\n'
    '\t\t\t</Position>\r\n'
    '\t\t</Dispense>\r\n'
    '\t</Component>'
)


class YamahaXmlExportError(ValueError):
    pass


@dataclass(frozen=True)
class YamahaComponent:
    designator: str
    mpn: str
    x: float
    y: float
    rotation: float


def _fmt_coord(value: float) -> str:
    return format(float(value), ".3f")


def _fmt_id(value: int) -> str:
    return f"{value:08d}"


def missing_pcb_info_fields_yamaha(pcb: PcbInfo) -> List[str]:
    missing: List[str] = []
    if not pcb.board_width or pcb.board_width <= 0:
        missing.append("Board Width")
    if not pcb.board_height or pcb.board_height <= 0:
        missing.append("Board Height")
    if not pcb.thickness or pcb.thickness <= 0:
        missing.append("Thickness")
    if pcb.x_boc1 == 0 and pcb.y_boc1 == 0:
        missing.append("BOC 1")
    if pcb.x_boc3 == 0 and pcb.y_boc3 == 0:
        missing.append("BOC 3")
    return missing


def components_from_review_records(
    records: Sequence[ReviewRecord], bottom: bool
) -> List[YamahaComponent]:
    selected = [
        r for r in records
        if r.status != "Deleted" and is_bottom_layer(r.layer) == bottom
    ]
    selected.sort(key=lambda r: r.row_index)

    result: List[YamahaComponent] = []
    for r in selected:
        if r.block or r.block_rotation:
            raise YamahaXmlExportError(
                "Panelized data is not supported for Yamaha XML export."
            )
        designator = (r.designator or "").strip()
        if not designator:
            continue
        x = r.new_x if r.new_x is not None else r.old_x
        y = r.new_y if r.new_y is not None else r.old_y
        rot = r.new_rotation if r.new_rotation is not None else r.old_rotation
        result.append(YamahaComponent(
            designator=designator,
            mpn=(r.mpn or "").strip(),
            x=float(x or 0.0),
            y=float(y or 0.0),
            rotation=float(rot or 0.0),
        ))
    return result


def _build_component_table(
    components: Sequence[YamahaComponent],
) -> tuple[dict[str, int], List[str]]:
    mpn_to_comp_no: dict[str, int] = {}
    comp_lines: List[str] = []
    for comp in components:
        mpn = comp.mpn
        if not mpn:
            raise YamahaXmlExportError(
                f"Component {comp.designator!r} has no MPN."
            )
        if mpn not in mpn_to_comp_no:
            no = len(mpn_to_comp_no) + 1
            mpn_to_comp_no[mpn] = no
            comp_lines.append(_COMPONENT_BODY.format(
                no=no,
                name=mpn,
                id=_fmt_id(no - 1),
                db_no=no,
                ibmf_no=no,
            ))
    return mpn_to_comp_no, comp_lines


def build_yamaha_xml(
    components: Sequence[YamahaComponent],
    pcb_info: PcbInfo,
    timestamp: Optional[datetime] = None,
) -> bytes:
    missing = missing_pcb_info_fields_yamaha(pcb_info)
    if missing:
        raise YamahaXmlExportError(
            "PCB Info is incomplete: " + ", ".join(missing)
        )

    ts = timestamp or datetime.now()
    date_str = ts.strftime("%Y/%m/%d")
    time_str = ts.strftime("%H:%M:%S")

    mpn_to_comp_no, comp_lines = _build_component_table(components)

    mount_lines: List[str] = []
    opt_mount_lines: List[str] = []
    for i, comp in enumerate(components):
        no = i + 1
        comp_no = mpn_to_comp_no[comp.mpn]
        mount_lines.append(
            f'\t\t<Mount No="{no}" X="{_fmt_coord(comp.x)}" Y="{_fmt_coord(comp.y)}" '
            f'R="{_fmt_coord(comp.rotation)}" FidRef="-0000001" BadRef="-0000001" '
            f'CompRef="{_fmt_id(comp_no - 1)}" ID="{_fmt_id(no - 1)}" Exist="1" '
            f'Comment="{comp.designator}" CompNum="{comp_no}"/>'
        )
        opt_mount_lines.append(
            f'\t\t\t<Mount No="{no}" PickGroup="-1" PickOrder="1" MountGroup="-1" '
            f'MountOrder="{no}" Machine="1424" Head="1" Nozzle="1" Exec="0" '
            f'PosMountRef="{_fmt_id(no - 1)}" SetupFeederRef="{_fmt_id(comp_no - 1)}" '
            f'PosBlockRef="-0000001" OptFlag="0"/>'
        )

    feeder_lines: List[str] = []
    for comp_no in range(1, len(mpn_to_comp_no) + 1):
        feeder_lines.append(
            f'\t\t\t<Feeder Machine="1424" Number="1" Definition="0" X="0.000" Y="0.000" '
            f'Opt="0" Group="0" ID="{_fmt_id(comp_no - 1)}" '
            f'CompRef="{_fmt_id(comp_no - 1)}" AltFeederRef="-0000001"/>'
        )

    with open(_TEMPLATE_PATH, "rb") as f:
        template = f.read().decode("utf-8")

    output = template.format(
        date=date_str,
        time=time_str,
        board_width=_fmt_coord(pcb_info.board_width),
        board_height=_fmt_coord(pcb_info.board_height),
        thickness=_fmt_coord(pcb_info.thickness),
        boc1_x=_fmt_coord(pcb_info.x_boc1),
        boc1_y=_fmt_coord(pcb_info.y_boc1),
        boc3_x=_fmt_coord(pcb_info.x_boc3),
        boc3_y=_fmt_coord(pcb_info.y_boc3),
        mounts="\r\n".join(mount_lines),
        opt_mounts="\r\n".join(opt_mount_lines),
        feeders="\r\n".join(feeder_lines),
        components="\r\n".join(comp_lines),
    )

    return output.encode("utf-8")


def export_yamaha_xml(
    records: Sequence[ReviewRecord],
    pcb_info: PcbInfo,
    file_path: str,
    bottom: bool,
    timestamp: Optional[datetime] = None,
) -> str:
    components = components_from_review_records(records, bottom)
    if not components:
        side = "Bottom" if bottom else "Top"
        raise YamahaXmlExportError(f"No {side} data to export.")

    xml_bytes = build_yamaha_xml(components, pcb_info, timestamp)

    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(xml_bytes)

    return file_path

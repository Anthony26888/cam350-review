from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import List, Optional, Sequence

from models.pcb_info import PcbInfo
from models.review import ReviewRecord
from services.bom_compare import is_bottom_layer


class YamahaYgxExportError(ValueError):
    pass


@dataclass(frozen=True)
class YgxComponent:
    designator: str
    mpn: str
    x: float
    y: float
    rotation: float


def _fmt_coord(value: float) -> str:
    d = Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    s = format(d, ".3f")
    return f"{s:>8}"


def _fmt_int(value: int, width: int) -> str:
    return f"{value:>{width}d}"


_BOARD_STATIC = (
    '\t\t<Board_101 PcbFixWay="1" ConvPreFixTimer="   0.500" TransHeight="15" '
    'ConvTimer="   0.000" YSpeed="3" TransMode="0" ConvSpeed="0" PartHeight=" 0.0"/>\r\n'
    '\t\t<Board_102 MountExec="0" VacCheck="0" Alignment="0" CoPlanarity="0" '
    'PrePick="1" RetrySeq="1" SkipRetry="0" PositionFreeSetup="0" TrayPre="0" FixedComp="0"/>\r\n'
    '\t\t<Board_103 BadSortA="0" BadSortB="0" BadSortC="0"/>\r\n'
    '\t\t<Board_104 Comment=""/>\r\n'
    '\t\t<Board_105 PreDisp="0" DotDisp="0" DotCheck="0" Refresh="0"/>\r\n'
    '\t\t<Board_106 SpecialFunction="0"/>\r\n'
    '\t\t<Board_108 HeadA1="0" HeadA2="0" HeadA3="0" HeadA4="0" HeadA5="0" HeadA6="0" '
    'HeadA7="0" HeadA8="0" HeadA9="0" HeadA10="0" HeadA11="0" HeadA12="0" '
    'HeadA13="0" HeadA14="0" HeadA15="0" HeadA16="0"/>\r\n'
    '\t\t<Board_109 HeadB1="0" HeadB2="0" HeadB3="0" HeadB4="0" HeadB5="0" HeadB6="0" '
    'HeadB7="0" HeadB8="0" HeadB9="0" HeadB10="0" HeadB11="0" HeadB12="0" '
    'HeadB13="0" HeadB14="0" HeadB15="0" HeadB16="0"/>\r\n'
    '\t\t<Board_110 TempControlA1="0" TempControlA2="0" TempControlA3="0" TempControlA4="0" '
    'TempControlA5="0" TempControlA6="0" TempControlA7="0" TempControlA8="0"/>\r\n'
    '\t\t<Board_111 TargetTempA1="  0" TargetTempA2="  0" TargetTempA3="  0" TargetTempA4="  0" '
    'TargetTempA5="  0" TargetTempA6="  0" TargetTempA7="  0" TargetTempA8="  0"/>'
)

_PART_TEMPLATE = (
    '\t\t<Part No="{no}">\r\n'
    '\t\t\t<Part_001 PartsName="{name}" Comment="" DatabaseNo="{db_no}" '
    'LibraryUse="0" LibraryFolder="0" LibraryPath=""/>\r\n'
    '\t\t\t<Part_002 ShapeType="7" Package="0" FdrType="0"/>\r\n'
    '\t\t\t<Part_003 Setno="1" Definition="0" XPos="    0.000" YPos="    0.000" '
    'FdrIdxStep="0" Optimize="0" PartsGroupNo="0" FixCmp="0" SwFdr="0"/>\r\n'
    '\t\t\t<Part_013 BodyX="   1.600" BodyY="   3.200" BodyZ="   0.500" '
    'MoldX="   1.700" MoldY="   3.300" MoldZ="   0.400" Thicknesschk="0"/>\r\n'
    '\t\t\t<Part_021 RlrOffset="3"/>\r\n'
    '\t\t\t<Part_071 Alignment="0" AutoThreshold="1" Threshold="30" Tolerance="30" '
    'SearchArea="   0.800" DatumAngle="0" CompIntensity="0" MultiMACS="0"/>\r\n'
    '\t\t\t<Part_072 LightSetting="0" LightLevel="3"/>\r\n'
    '\t\t\t<Part_074 CoplaLevel="0" CoplaThreshold="0"/>\r\n'
    '\t\t\t<Part_076 LightMode="0" MainLightLevel="3" CoaxsLightLevel="3" SideLightLevel="0"/>\r\n'
    '\t\t\t<Part_080 Nozzle="3" XYSpeed="0" ConvYSpeed="3" FdrAngle="0" VacChk="1" '
    'CorrectPos="0" Action="0" PickStart="0" Dump="0" Retry="3"/>\r\n'
    '\t\t\t<Part_081 PckHeight=" 0.000" PckTimer="0.00" PckSpeed="0" PckVLevel="30" '
    'PckSingleDir="0" PckCtrlDown="0" PckCtrlUp="0" NozzleTouchHeight=" 0.000"/>\r\n'
    '\t\t\t<Part_083 MntHeight=" 0.500" MntTimer="0.00" MntSpeed="0" MntPLevel="30" '
    'MntSingleDir="0" MntCtrlDown="0" MntCtrlUp="0"/>\r\n'
    '\t\t\t<Part_200 DspCType="3" DNozzle="0" Dtimer="0" DXpos="   0.000" DYpos="   0.000" '
    'DspAngle="0" DXpt="   0.000" DYpt="   0.000" DXtime="1" DYtime="1"/>\r\n'
    '\t\t\t<Part_520 SVUse="0" SVBringBack="0" SVBodyLimit="0.000"/>\r\n'
    '\t\t</Part>'
)


def missing_pcb_info_fields_ygx(pcb: PcbInfo) -> List[str]:
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
) -> List[YgxComponent]:
    selected = [
        r for r in records
        if r.status != "Deleted" and is_bottom_layer(r.layer) == bottom
    ]
    selected.sort(key=lambda r: r.row_index)

    result: List[YgxComponent] = []
    for r in selected:
        if r.block or r.block_rotation:
            raise YamahaYgxExportError(
                "Panelized data is not supported for Yamaha YGX export."
            )
        designator = (r.designator or "").strip()
        if not designator:
            continue
        x = r.new_x if r.new_x is not None else r.old_x
        y = r.new_y if r.new_y is not None else r.old_y
        rot = r.new_rotation if r.new_rotation is not None else r.old_rotation
        result.append(YgxComponent(
            designator=designator,
            mpn=(r.mpn or "").strip(),
            x=float(x or 0.0),
            y=float(y or 0.0),
            rotation=float(rot or 0.0),
        ))
    return result


def build_ygx(
    components: Sequence[YgxComponent],
    pcb_info: PcbInfo,
    timestamp: Optional[datetime] = None,
) -> bytes:
    missing = missing_pcb_info_fields_ygx(pcb_info)
    if missing:
        raise YamahaYgxExportError(
            "PCB Info is incomplete: " + ", ".join(missing)
        )

    ts = timestamp or datetime.now()
    date_str = ts.strftime("%Y/%m/%d")
    time_str = ts.strftime("%H:%M:%S")

    mpn_to_comp_no: dict[str, int] = {}
    for comp in components:
        if comp.mpn and comp.mpn not in mpn_to_comp_no:
            mpn_to_comp_no[comp.mpn] = len(mpn_to_comp_no) + 1

    bw = _fmt_coord(pcb_info.board_width)
    bh = _fmt_coord(pcb_info.board_height)
    thick_d = Decimal(str(pcb_info.thickness)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    thick = format(thick_d, ".3f")
    boc1x = _fmt_coord(pcb_info.x_boc1)
    boc1y = _fmt_coord(pcb_info.y_boc1)
    boc3x = _fmt_coord(pcb_info.x_boc3)
    boc3y = _fmt_coord(pcb_info.y_boc3)

    lines: List[str] = []
    lines.append('<?xml version="1.0"?>')
    lines.append("<PcbDataFile>")
    lines.append(f'<LastEditing Date="{date_str}" Time="{time_str}" VersionNo="2">')
    lines.append('\t<SetupMachine No=" 1" Name="yamaha       " ID="1424"/>')
    lines.append("</LastEditing>")
    lines.append('<Machine No=" 1" MachineType="15" SubMachineType="1" Version="YGOS AMS 2.0  (B2.45 R0.101)">')
    lines.append(f'\t<Property LastEditingDate="{date_str}" LastEditingTime="{time_str}" VersionNo="2"/>')
    lines.append("\t<Board>")
    lines.append(f'\t\t<Board_000 OriginX="  -4.671" OriginY="  -5.175" SizeX="{bw}" SizeY="{bh}" BlockCount="  0" SizeZ="{thick}"/>')
    lines.append(_BOARD_STATIC)
    lines.append("\t</Board>")
    lines.append("\t<Fiducial>")
    lines.append('\t\t<FidUse Pcb="0" Blk="1" Local="0"/>')
    lines.append(f'\t\t<PcbFid          X1="{boc1x}" Y1="{boc1y}" Mark1="  1" X2="{boc3x}" Y2="{boc3y}" Mark2="  0"/>')
    lines.append('\t\t<BlkFid          X1="   0.000" Y1="   0.000" Mark1="  1" X2="   0.000" Y2="   0.000" Mark2="  0"/>')
    lines.append("\t</Fiducial>")
    lines.append("\t<BadMark>")
    lines.append('\t\t<BadUse Pcb="1" Blk="1" Local="0"/>')
    lines.append('\t\t<PcbBad          X="   0.000" Y="   0.000" Mark="  1"/>')
    lines.append('\t\t<BlkBad          X="   0.000" Y="   0.000" Mark="  1"/>')
    lines.append("\t</BadMark>")
    lines.append("\t<Offset>")
    lines.append('\t\t<Repeat No="  1" X="   0.000" Y="   0.000" R="   0.000" Exec="0" Comment=""/>')
    lines.append("\t</Offset>")
    lines.append("\t<Mounts>")

    for i, comp in enumerate(components):
        no = i + 1
        comp_no = mpn_to_comp_no.get(comp.mpn, 1)
        lines.append(
            f'\t\t<Mount No="{_fmt_int(no, 5)}" X="{_fmt_coord(comp.x)}" Y="{_fmt_coord(comp.y)}" '
            f'R="{_fmt_coord(comp.rotation)}" Fid="  0" Bad="  0" Comp="{_fmt_int(comp_no, 4)}" '
            f'Group="   -1" Opt="  1" Head=" 1" Nozzle="  0" Exec="0" Comment="{comp.designator}"/>'
        )

    lines.append("\t</Mounts>")
    lines.append("\t<PreDispenses>")
    lines.append("\t</PreDispenses>")
    lines.append("\t<DotDispenses>")
    lines.append("\t</DotDispenses>")
    lines.append("\t<Parts>")

    for comp_no in range(1, len(mpn_to_comp_no) + 1):
        mpn = next(m for m, n in mpn_to_comp_no.items() if n == comp_no)
        lines.append(_PART_TEMPLATE.format(no=comp_no, name=mpn, db_no=comp_no))

    lines.append("\t</Parts>")
    lines.append("\t<Marks>")
    lines.append("\t</Marks>")
    lines.append("</Machine>")
    lines.append("</PcbDataFile>")

    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def export_ygx(
    records: Sequence[ReviewRecord],
    pcb_info: PcbInfo,
    file_path: str,
    bottom: bool,
    timestamp: Optional[datetime] = None,
) -> str:
    components = components_from_review_records(records, bottom)
    if not components:
        side = "Bottom" if bottom else "Top"
        raise YamahaYgxExportError(f"No {side} data to export.")

    xml_bytes = build_ygx(components, pcb_info, timestamp)

    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(xml_bytes)

    return file_path

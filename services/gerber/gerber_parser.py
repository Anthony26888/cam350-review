import re
from typing import List, Optional, Tuple


class GerberPoint:
    def __init__(self, x_mm: float, y_mm: float, layer_name: Optional[str] = None):
        self.x_mm = x_mm
        self.y_mm = y_mm
        self.layer_name = layer_name

    def __repr__(self) -> str:
        return f"GerberPoint({self.x_mm:.4f}, {self.y_mm:.4f}, layer={self.layer_name})"


class SRBlock:
    def __init__(self, name: Optional[str], nx: int, ny: int, dx_in: float, dy_in: float):
        self.name = name
        self.nx = nx
        self.ny = ny
        self.dx_in = dx_in
        self.dy_in = dy_in

    def __repr__(self) -> str:
        return f"SRBlock(name={self.name}, nx={self.nx}, ny={self.ny}, dx={self.dx_in}, dy={self.dy_in})"


def parse_sr_blocks(path: str) -> List[SRBlock]:
    blocks = []
    cur_name: Optional[str] = None
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            m = re.match(r'%LN(.+?)\*%', line)
            if m:
                cur_name = m.group(1)
            m = re.match(r'%SRX(\d+)Y(\d+)I([\d.]+)J([\d.]+)\*%', line)
            if m:
                blocks.append(SRBlock(
                    name=cur_name,
                    nx=int(m.group(1)),
                    ny=int(m.group(2)),
                    dx_in=float(m.group(3)),
                    dy_in=float(m.group(4)),
                ))
    return blocks


def _parse_coord(value: str, decimals: int, int_places: int) -> float:
    sign = -1.0 if value.startswith('-') else 1.0
    digits = value.lstrip('-+')
    total_width = int_places + decimals
    if len(digits) < total_width:
        digits = digits.zfill(total_width)
    int_part = digits[:int_places] or '0'
    frac_part = digits[int_places:]
    return sign * float(f"{int_part}.{frac_part}")


def parse_gerber_points(
    path: str,
    codes: Tuple[str, ...] = ('1', '2'),
) -> List[GerberPoint]:
    x = y = 0.0
    cur_name: Optional[str] = None
    unit_inch = True
    int_places = 4
    decimals = 4

    pts: List[GerberPoint] = []

    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if line.startswith('%MOIN*%'):
                unit_inch = True
                continue
            if line.startswith('%MOMM*%'):
                unit_inch = False
                continue

            m_fs = re.match(r'%FSLAX(\d)(\d)Y(\d)(\d)\*%', line)
            if m_fs:
                int_places = int(m_fs.group(1))
                decimals = int(m_fs.group(2))
                continue

            m_ln = re.match(r'%LN(.+?)\*%', line)
            if m_ln:
                cur_name = m_ln.group(1)
                continue

            if line.startswith('%'):
                continue

            m_cmd = re.match(r'(X(-?\d+))?(Y(-?\d+))?D0?(\d)\*?$', line)
            if not m_cmd:
                continue

            if m_cmd.group(2):
                x = _parse_coord(m_cmd.group(2), decimals, int_places)
            if m_cmd.group(4):
                y = _parse_coord(m_cmd.group(4), decimals, int_places)

            code = m_cmd.group(5)
            if code in codes:
                x_mm = x * 25.4 if unit_inch else x
                y_mm = y * 25.4 if unit_inch else y
                pts.append(GerberPoint(x_mm, y_mm, cur_name))

    return pts


def bbox(pts: List[GerberPoint]) -> Tuple[Tuple[float, float], float, float]:
    if not pts:
        return (0.0, 0.0), 0.0, 0.0
    xs = [p.x_mm for p in pts]
    ys = [p.y_mm for p in pts]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    return (xmin, ymin), (xmax - xmin), (ymax - ymin)


def parse_flashes(
    path: str,
    sub_block_name: Optional[str] = None,
) -> List[GerberPoint]:
    pts = parse_gerber_points(path, codes=('3',))
    if sub_block_name:
        pts = [p for p in pts if p.layer_name == sub_block_name]
    return pts


def crop_to_instance(
    gtp_all: List[GerberPoint],
    k: int,
    dy_mm: float,
    board_h_mm: float,
    margin_mm: float = 5.0,
) -> List[GerberPoint]:
    lo = k * dy_mm - margin_mm
    hi = k * dy_mm + board_h_mm + margin_mm
    return [p for p in gtp_all if lo <= p.y_mm <= hi]

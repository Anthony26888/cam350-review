import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

MM_PER_INCH = 25.4


@dataclass
class LineShape:
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    width: float = 0.1
    negative: bool = False


@dataclass
class ArcShape:
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    cx: float = 0.0  # absolute center
    cy: float = 0.0  # absolute center
    clockwise: bool = True
    width: float = 0.1
    negative: bool = False


@dataclass
class FlashShape:
    cx: float = 0.0
    cy: float = 0.0
    kind: str = "circle"  # circle | rect | oblong | polygon | macro
    w: float = 0.0
    h: float = 0.0
    rot: float = 0.0
    pts: Optional[List[Tuple[float, float]]] = None
    macro: Optional["ApertureMacro"] = None
    negative: bool = False


@dataclass
class ApertureMacro:
    circles: List[Tuple[float, float, float]] = field(default_factory=list)  # (cx, cy, r) mm
    polygons: List[List[Tuple[float, float]]] = field(default_factory=list)  # point lists mm
    segments: List[Tuple[float, float, float, float, float]] = field(default_factory=list)  # (x1,y1,x2,y2,width)


@dataclass
class RenderData:
    lines: List[LineShape] = field(default_factory=list)
    arcs: List[ArcShape] = field(default_factory=list)
    flashes: List[FlashShape] = field(default_factory=list)

    def bbox(self) -> Tuple[float, float, float, float]:
        xs: List[float] = []
        ys: List[float] = []
        for ln in self.lines:
            xs += [ln.x1, ln.x2]
            ys += [ln.y1, ln.y2]
        for ar in self.arcs:
            for sx, sy in _sample_arc(ar.x1, ar.y1, ar.x2, ar.y2, ar.cx, ar.cy, ar.clockwise, 12):
                xs.append(sx)
                ys.append(sy)
        for f in self.flashes:
            xs.append(f.cx)
            ys.append(f.cy)
            if f.pts:
                xs += [p[0] for p in f.pts]
                ys += [p[1] for p in f.pts]
        if not xs:
            return 0.0, 0.0, 0.0, 0.0
        return min(xs), min(ys), max(xs), max(ys)


def _polygon_verts(diameter: float, n: int, rotation: float) -> List[Tuple[float, float]]:
    if n < 3:
        n = 3
    pts: List[Tuple[float, float]] = []
    r = diameter / 2.0
    theta0 = math.radians(rotation)
    for i in range(n):
        a = theta0 + 2.0 * math.pi * i / n
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def _sample_arc(
    x1: float, y1: float, x2: float, y2: float,
    cx: float, cy: float, clockwise: bool, steps: int,
) -> List[Tuple[float, float]]:
    """Sample an arc (absolute center) into `steps` points."""
    radius = math.hypot(x1 - cx, y1 - cy)
    if radius <= 1e-9:
        return [(x1, y1), (x2, y2)]
    start_ang = math.atan2(y1 - cy, x1 - cx)
    end_ang = math.atan2(y2 - cy, x2 - cx)
    if clockwise:
        sweep = -((start_ang - end_ang) % (2.0 * math.pi))
    else:
        sweep = (end_ang - start_ang) % (2.0 * math.pi)
    pts: List[Tuple[float, float]] = []
    for k in range(steps + 1):
        a = start_ang + sweep * k / steps
        pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return pts


def _macro_tokens(text: str) -> List[float]:
    tokens: List[float] = []
    for m in re.finditer(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        tokens.append(float(m.group(0)))
    return tokens


def _parse_macro(text: str, scale: float) -> ApertureMacro:
    macro = ApertureMacro()
    tokens = _macro_tokens(text)
    i = 0
    n = len(tokens)

    def take(cnt: int) -> List[float]:
        nonlocal i
        end = min(i + cnt, n)
        vals = tokens[i:end]
        i = end
        return vals

    while i < n:
        ptype = int(tokens[i]); i += 1
        if ptype == 1 and n - i >= 4:  # circle: exposure, diameter, cx, cy
            vals = take(4)
            exposure, diameter, x, y = vals[:4]
            if exposure:
                macro.circles.append((x * scale, y * scale, diameter / 2.0 * scale))
        elif ptype == 20 and n - i >= 7:  # line: exposure, width, x1, y1, x2, y2, rot
            vals = take(7)
            exposure, width = vals[0], vals[1]
            x1, y1, x2, y2 = vals[2:6]
            if exposure:
                macro.segments.append((
                    x1 * scale, y1 * scale, x2 * scale, y2 * scale, width * scale
                ))
        elif ptype == 21 and n - i >= 6:  # center line -> rectangle: exp, W, H, cx, cy, rot
            vals = take(6)
            exposure, width, height, x, y, rot = vals[:6]
            if exposure:
                half_w = width / 2.0 * scale
                half_h = height / 2.0 * scale
                cx = x * scale
                cy = y * scale
                ang = math.radians(rot)
                c, s = math.cos(ang), math.sin(ang)
                corners = []
                for hx, hy in ((-half_w, -half_h), (half_w, -half_h),
                               (half_w, half_h), (-half_w, half_h)):
                    corners.append((cx + hx * c - hy * s, cy + hx * s + hy * c))
                macro.polygons.append(corners)
        elif ptype == 2 and n - i >= 6:  # legacy center line -> rectangle
            vals = take(6)
            exposure, width, height, x, y, rot = vals
            if exposure:
                half_w = width / 2.0 * scale
                half_h = height / 2.0 * scale
                cx = x * scale
                cy = y * scale
                ang = math.radians(rot)
                c, s = math.cos(ang), math.sin(ang)
                corners = []
                for hx, hy in ((-half_w, -half_h), (half_w, -half_h),
                               (half_w, half_h), (-half_w, half_h)):
                    corners.append((cx + hx * c - hy * s, cy + hx * s + hy * c))
                macro.polygons.append(corners)
        elif ptype == 4 and n - i >= 3:  # outline polygon (may span many lines)
            exposure = tokens[i]; i += 1
            cnt = int(tokens[i]); i += 1
            pts_coords = take(2 * cnt)
            if exposure and cnt >= 3 and len(pts_coords) >= 2 * cnt:
                pts = [
                    (pts_coords[2 * k] * scale, pts_coords[2 * k + 1] * scale)
                    for k in range(cnt)
                ]
                macro.polygons.append(pts)
            take(1)  # trailing rotation terminator
        elif ptype == 5 and n - i >= 6:  # regular polygon: exp, n, cx, cy, diameter, rot
            vals = take(6)
            exposure, cnt_n, cx, cy, diameter, rot = vals[:6]
            if exposure:
                pts = _polygon_verts(diameter * scale, int(cnt_n), rot)
                pts = [(cx * scale + px, cy * scale + py) for px, py in pts]
                macro.polygons.append(pts)
        elif ptype == 7 and n - i >= 6:  # thermal -> outer disc approximation
            vals = take(6)
            exposure, cx, cy, outer_d = vals[:4]
            if exposure:
                macro.circles.append((cx * scale, cy * scale, outer_d / 2.0 * scale))
        elif ptype == 22 and n - i >= 6:  # outline polygon (N pts) or lower-left rect (KiCad)
            exposure = tokens[i]; i += 1
            n_pts = int(tokens[i]) if i < n and float(tokens[i]).is_integer() else 0
            if n_pts >= 3 and n - i - 1 >= 2 * n_pts + 1:
                i += 1  # skip the point count
                pts_coords = take(2 * n_pts)
                rot = take(1)[0]
                if exposure:
                    pts = [
                        (pts_coords[2 * k] * scale, pts_coords[2 * k + 1] * scale)
                        for k in range(n_pts)
                    ]
                    ang = math.radians(rot)
                    c, s = math.cos(ang), math.sin(ang)
                    pts = [(x * c - y * s, x * s + y * c) for x, y in pts]
                    macro.polygons.append(pts)
            else:
                width, height, x_ll, y_ll, rot = take(5)
                if exposure:
                    ang = math.radians(rot)
                    c, s = math.cos(ang), math.sin(ang)
                    corners = []
                    for px, py in ((0, 0), (width, 0), (width, height), (0, height)):
                        ex = x_ll + px
                        ey = y_ll + py
                        corners.append((ex * c - ey * s, ex * s + ey * c))
                    macro.polygons.append(
                        [(x * scale, y * scale) for x, y in corners]
                    )
        else:
            # Unknown primitive: skip its own row, keep parsing the rest.
            take(1)
    return macro


class _Aperture:
    def __init__(self, kind: str, w: float = 0.0, h: float = 0.0,
                 rot: float = 0.0, macro: Optional[ApertureMacro] = None,
                 pts: Optional[List[Tuple[float, float]]] = None):
        self.kind = kind
        self.w = w
        self.h = h
        self.rot = rot
        self.macro = macro
        self.pts = pts

    def draw_width(self) -> float:
        if self.kind == "circle":
            return self.w
        if self.kind in ("rect", "oblong"):
            return min(self.w, self.h)
        if self.kind == "polygon":
            return self.w / 2.0
        return 0.1


def parse_render(path: str) -> RenderData:
    data = RenderData()
    scale = 1.0
    unit_inch = True
    int_places = 4
    decimals = 4
    suppress = "L"
    incremental = False

    apertures: Dict[int, _Aperture] = {}
    macros: Dict[str, ApertureMacro] = {}

    cur_code: Optional[int] = None
    px = py = 0.0
    cx = cy = 0.0
    arc = 0  # 0 none, 2 CW, 3 CCW
    i_off = j_off = 0.0
    region_active = False
    region_vertices: List[Tuple[float, float]] = []

    def _ap() -> Optional[_Aperture]:
        if cur_code is not None:
            return apertures.get(cur_code)
        return None

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        macro_buf: Optional[str] = None
        macro_name = ""
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            if macro_buf is not None:
                if line.endswith("%"):
                    macros[macro_name] = _parse_macro(macro_buf, scale)
                    macro_buf = None
                else:
                    macro_buf += "\n" + line
                continue

            if line.startswith("%AM"):
                macro_name = line[3:].rstrip("*")
                macro_buf = ""
                continue

            if line.startswith("%"):
                if line.startswith("%MOIN*%"):
                    unit_inch = True
                    scale = MM_PER_INCH
                elif line.startswith("%MOMM*%"):
                    unit_inch = False
                    scale = 1.0
                else:
                    m_fs = re.match(r"%FS([LT])([AI])X(\d)(\d)Y(\d)(\d)\*%", line)
                    if m_fs:
                        suppress = m_fs.group(1)
                        incremental = (m_fs.group(2) == "I")
                        int_places = int(m_fs.group(3))
                        decimals = int(m_fs.group(4))
                        continue
                    m_fs_plain = re.match(r"%FSX(\d)(\d)Y(\d)(\d)\*%", line)
                    if m_fs_plain:
                        int_places = int(m_fs_plain.group(1))
                        decimals = int(m_fs_plain.group(2))
                        continue
                    m_add = re.match(r"%ADD(\d+)([A-Za-z][A-Za-z0-9]*)(.*?)\*%", line)
                    if m_add:
                        code = int(m_add.group(1))
                        name = m_add.group(2).upper()
                        rest = m_add.group(3).strip()
                        raw_name = m_add.group(2)
                        parts = [p for p in rest.lstrip(",").split("X") if p]
                        sizes: List[float] = []
                        for p in parts:
                            try:
                                sizes.append(float(p))
                            except ValueError:
                                sizes.append(0.0)
                        if name == "C" and sizes:
                            d = sizes[0] * scale
                            apertures[code] = _Aperture("circle", w=d, h=d)
                        elif name == "R" and len(sizes) >= 2:
                            w = sizes[0] * scale
                            h = sizes[1] * scale
                            rot = sizes[2] if len(sizes) > 2 else 0.0
                            apertures[code] = _Aperture("rect", w=w, h=h, rot=rot)
                        elif name == "O" and len(sizes) >= 2:
                            w = sizes[0] * scale
                            h = sizes[1] * scale
                            rot = sizes[2] if len(sizes) > 2 else 0.0
                            apertures[code] = _Aperture("oblong", w=w, h=h, rot=rot)
                        elif name == "P" and len(sizes) >= 2:
                            d = sizes[0] * scale
                            n = int(sizes[1])
                            rot = sizes[2] if len(sizes) > 2 else 0.0
                            apertures[code] = _Aperture(
                                "polygon", w=d, h=float(n), rot=rot,
                                pts=_polygon_verts(d, n, rot),
                            )
                        elif name.startswith("ROUNDREC") and len(sizes) >= 9:
                            corners = sizes[1:9]
                            xs = [corners[i] for i in range(0, 8, 2)]
                            ys = [corners[i] for i in range(1, 8, 2)]
                            w = (max(xs) - min(xs)) * scale
                            h = (max(ys) - min(ys)) * scale
                            apertures[code] = _Aperture("oblong", w=w, h=h, rot=0.0)
                        elif name.startswith("FREEPOLY"):
                            macro = macros.get(raw_name)
                            if macro and macro.polygons:
                                apertures[code] = _Aperture("polygon", w=0.0, h=0.0, rot=0.0, pts=macro.polygons[0])
                            else:
                                apertures[code] = _Aperture("macro", macro=macro, pts=None)
                        else:
                            macro = macros.get(raw_name)
                            apertures[code] = _Aperture("macro", macro=macro)
                continue

            if line.startswith("G04") or line == "*":
                continue

            if line in ("G01*", "G02*", "G03*", "G75*", "G74*", "G70*", "G71*"):
                if line.startswith("G70"):
                    unit_inch = True
                    scale = MM_PER_INCH
                elif line.startswith("G71"):
                    unit_inch = False
                    scale = 1.0
                elif line.startswith("G02"):
                    arc = 2
                elif line.startswith("G03"):
                    arc = 3
                elif line.startswith("G01"):
                    arc = 0
                continue

            if line == "G36*":
                region_active = True
                region_vertices = []
                continue
            if line == "G37*":
                region_active = False
                if len(region_vertices) >= 3:
                    if (region_vertices[0][0] == region_vertices[-1][0]
                            and region_vertices[0][1] == region_vertices[-1][1]):
                        region_vertices.pop()
                    data.flashes.append(
                        FlashShape(0.0, 0.0, kind="polygon", pts=list(region_vertices))
                    )
                region_vertices = []
                continue

            m_sel = re.match(r"^(?:G54)?D(\d+)\*?$", line)
            if m_sel:
                op_code = int(m_sel.group(1))
                if op_code <= 3:
                    if op_code == 3:
                        ap = _ap()
                        if ap is not None:
                            data.flashes.append(_make_flash(ap, px, py))
                else:
                    cur_code = op_code
                arc = 0
                continue

            m_cmd = re.match(
                r"^(G02|G03)?(X(-?\d+))?(Y(-?\d+))?(I(-?\d+))?(J(-?\d+))?D0?(\d)\*?$",
                line,
            )
            if not m_cmd:
                continue

            if m_cmd.group(1):
                arc = 2 if m_cmd.group(1) == "G02" else 3
            if m_cmd.group(3) is not None:
                v = _parse_num(m_cmd.group(3), int_places, decimals, suppress) * scale
                cx = px + v if incremental else v
            if m_cmd.group(5) is not None:
                v = _parse_num(m_cmd.group(5), int_places, decimals, suppress) * scale
                cy = py + v if incremental else v
            if m_cmd.group(7) is not None:
                i_off = _parse_num(m_cmd.group(7), int_places, decimals, suppress) * scale
            if m_cmd.group(9) is not None:
                j_off = _parse_num(m_cmd.group(9), int_places, decimals, suppress) * scale

            code = m_cmd.group(10)
            ap = _ap()

            if code == "2":  # move
                if region_active:
                    _append_region_points(region_vertices, px, py, cx, cy, i_off, j_off, arc)
                px, py = cx, cy
                arc = 0
                continue
            if code == "3":  # flash
                if ap is not None:
                    data.flashes.append(_make_flash(ap, cx, cy))
                px, py = cx, cy
                arc = 0
                continue
            if code == "1":  # draw
                if region_active:
                    _append_region_points(region_vertices, px, py, cx, cy, i_off, j_off, arc)
                else:
                    width = ap.draw_width() if ap else 0.1
                    if arc and (i_off or j_off):
                        for sx, sy, ex, ey in _arc_points(px, py, cx, cy, i_off, j_off, arc):
                            data.lines.append(LineShape(sx, sy, ex, ey, width))
                    else:
                        data.lines.append(LineShape(px, py, cx, cy, width))
                px, py = cx, cy
                arc = 0
                continue

    return data


def _append_region_points(verts, px, py, ex, ey, i_off, j_off, arc):
    if arc and (i_off or j_off):
        for sx, sy, xe, ye in _arc_points(px, py, ex, ey, i_off, j_off, arc):
            if not verts or (abs(verts[-1][0] - xe) > 1e-9 or abs(verts[-1][1] - ye) > 1e-9):
                verts.append((xe, ye))
    else:
        if not verts or (abs(verts[-1][0] - ex) > 1e-9 or abs(verts[-1][1] - ey) > 1e-9):
            verts.append((ex, ey))


def _parse_num(value: str, int_places: int, decimals: int, suppress: str = "L") -> float:
    sign = -1.0 if value.startswith("-") else 1.0
    digits = value.lstrip("-+")
    total_width = int_places + decimals
    if len(digits) < total_width:
        if suppress == "T":
            digits = digits.ljust(total_width, "0")
        else:
            digits = digits.zfill(total_width)
    int_part = digits[:int_places] or "0"
    frac_part = digits[int_places:]
    return sign * float(f"{int_part}.{frac_part}")


def _make_flash(ap: _Aperture, cx: float, cy: float) -> FlashShape:
    if ap.kind == "macro":
        return FlashShape(cx, cy, kind="macro", macro=ap.macro)
    if ap.kind == "circle":
        return FlashShape(cx, cy, kind="circle", w=ap.w, h=ap.h, rot=ap.rot)
    if ap.kind == "rect":
        return FlashShape(cx, cy, kind="rect", w=ap.w, h=ap.h, rot=ap.rot)
    if ap.kind == "oblong":
        return FlashShape(cx, cy, kind="oblong", w=ap.w, h=ap.h, rot=ap.rot)
    if ap.kind == "polygon":
        return FlashShape(cx, cy, kind="polygon", w=ap.w, h=ap.h, rot=ap.rot, pts=ap.pts)
    return FlashShape(cx, cy, kind="circle", w=0.3, h=0.3)


def _arc_points(
    sx: float, sy: float, ex: float, ey: float,
    i_off: float, j_off: float, direction: int,
) -> List[Tuple[float, float, float, float]]:
    cxx = sx + i_off
    cyy = sy + j_off
    radius = math.hypot(i_off, j_off)
    if radius <= 1e-9:
        return [(sx, sy, ex, ey)]

    start_ang = math.atan2(sy - cyy, sx - cxx)
    end_ang = math.atan2(ey - cyy, ex - cxx)

    if direction == 3:  # CCW
        sweep = (end_ang - start_ang) % (2.0 * math.pi)
    else:  # CW
        sweep = -((start_ang - end_ang) % (2.0 * math.pi))

    if abs(sweep) < 1e-9:
        return [(sx, sy, ex, ey)]

    chord_err = 0.02
    denom = 1.0 - chord_err / radius
    denom = max(denom, 0.0)
    step = math.acos(min(denom, 1.0))
    steps = max(2, int(math.ceil(abs(sweep) / step)))

    pts = []
    last_x, last_y = sx, sy
    for k in range(1, steps + 1):
        a = start_ang + sweep * k / steps
        nx = cxx + radius * math.cos(a)
        ny = cyy + radius * math.sin(a)
        pts.append((last_x, last_y, nx, ny))
        last_x, last_y = nx, ny
    return pts

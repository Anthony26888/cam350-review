from typing import List, Optional, Tuple

from services.gerber.gerber_parser import (
    GerberPoint, SRBlock, parse_sr_blocks, parse_gerber_points, bbox,
)


class BoardInstance:
    def __init__(
        self,
        origin: Tuple[float, float],
        w: float,
        h: float,
        sub_name: Optional[str] = None,
        k: int = 0,
    ):
        self.origin = origin
        self.w = w
        self.h = h
        self.sub_name = sub_name
        self.k = k

    def __repr__(self) -> str:
        return (
            f"BoardInstance(k={self.k}, origin=({self.origin[0]:.4f}, "
            f"{self.origin[1]:.4f}), w={self.w:.4f}, h={self.h:.4f}, "
            f"sub_name={self.sub_name})"
        )


class PanelInfo:
    def __init__(
        self,
        kind: str,
        instances: List[BoardInstance],
        panel_origin: Tuple[float, float] = (0.0, 0.0),
        panel_w: float = 0.0,
        panel_h: float = 0.0,
        sub_block_names: Optional[List[str]] = None,
        dx_mm: float = 0.0,
        dy_mm: float = 0.0,
        nx: int = 1,
        ny: int = 1,
    ):
        self.kind = kind
        self.instances = instances
        self.panel_origin = panel_origin
        self.panel_w = panel_w
        self.panel_h = panel_h
        self.sub_block_names = sub_block_names or []
        self.dx_mm = dx_mm
        self.dy_mm = dy_mm
        self.nx = nx
        self.ny = ny

    @property
    def is_panel(self) -> bool:
        return self.kind in ('A', 'B')

    @property
    def count(self) -> int:
        return len(self.instances)

    def __repr__(self) -> str:
        return (
            f"PanelInfo(kind={self.kind}, count={self.count}, "
            f"panel_origin=({self.panel_origin[0]:.4f}, {self.panel_origin[1]:.4f}), "
            f"panel_w={self.panel_w:.4f}, panel_h={self.panel_h:.4f})"
        )


def detect_panel(gko_path: str) -> PanelInfo:
    blocks = parse_sr_blocks(gko_path)

    all_pts = parse_gerber_points(gko_path, codes=('1', '2'))

    layer_names = list(set(p.layer_name for p in all_pts if p.layer_name))
    sub_names = sorted([n for n in layer_names if '.sub' in (n or '')],
                       key=lambda n: n or '')

    kind_a_block = None
    for b in blocks:
        if b.nx > 1 or b.ny > 1:
            kind_a_block = b
            break

    if kind_a_block:
        # Kind A: step-repeat
        sub_block_name = kind_a_block.name or sub_names[0] if sub_names else None
        if sub_block_name:
            sub_pts = [p for p in all_pts if p.layer_name == sub_block_name]
        else:
            sub_pts, _ = _find_best_layer_pts(all_pts)
        if not sub_pts:
            return _single_board(all_pts)

        origin0, w, h = bbox(sub_pts)
        nx, ny = kind_a_block.nx, kind_a_block.ny
        dx_mm = kind_a_block.dx_in * 25.4
        dy_mm = kind_a_block.dy_in * 25.4

        instances: List[BoardInstance] = []
        for ky in range(ny):
            for kx in range(nx):
                k = ky * nx + kx
                ox = origin0[0] + kx * dx_mm
                oy = origin0[1] + ky * dy_mm
                instances.append(BoardInstance(
                    origin=(ox, oy), w=w, h=h,
                    sub_name=sub_block_name, k=k,
                ))

        # Panel outline block
        panel_block_name = _find_panel_block_name(layer_names, sub_names)
        panel_origin, panel_w, panel_h = (0, 0), 0, 0
        if panel_block_name:
            panel_pts = [p for p in all_pts if p.layer_name == panel_block_name]
            if panel_pts:
                panel_origin, panel_w, panel_h = bbox(panel_pts)

        return PanelInfo(
            kind='A', instances=instances,
            panel_origin=panel_origin, panel_w=panel_w, panel_h=panel_h,
            sub_block_names=[sub_block_name] if sub_block_name else [],
            dx_mm=dx_mm, dy_mm=dy_mm, nx=nx, ny=ny,
        )

    # Kind B: multiple .subN blocks with same size
    if len(sub_names) >= 2:
        sub_bboxes = []
        for sn in sub_names:
            sub_pts = [p for p in all_pts if p.layer_name == sn]
            if sub_pts:
                sub_bboxes.append((sn, bbox(sub_pts)))

        if len(sub_bboxes) >= 2:
            ref_w = sub_bboxes[0][1][1]
            ref_h = sub_bboxes[0][1][2]
            same_size = True
            for _, (_, w, h) in sub_bboxes[1:]:
                if abs(w - ref_w) > 0.01 or abs(h - ref_h) > 0.01:
                    same_size = False
                    break

            if same_size:
                instances = [
                    BoardInstance(origin=origin, w=w, h=h, sub_name=sn, k=i)
                    for i, (sn, (origin, w, h)) in enumerate(sub_bboxes)
                ]

                panel_block_name = _find_panel_block_name(layer_names, sub_names)
                panel_origin, panel_w, panel_h = (0, 0), 0, 0
                if panel_block_name:
                    panel_pts = [p for p in all_pts if p.layer_name == panel_block_name]
                    if panel_pts:
                        panel_origin, panel_w, panel_h = bbox(panel_pts)

                return PanelInfo(
                    kind='B', instances=instances,
                    panel_origin=panel_origin, panel_w=panel_w, panel_h=panel_h,
                    sub_block_names=sub_names,
                )

    # Single board
    return _single_board(all_pts)


def _find_best_layer_pts(all_pts: List[GerberPoint]) -> Tuple[List[GerberPoint], Optional[str]]:
    layer_groups: dict[str, List[GerberPoint]] = {}
    for p in all_pts:
        name = p.layer_name or '__all__'
        layer_groups.setdefault(name, []).append(p)

    candidates = []
    for name, pts in layer_groups.items():
        origin, w, h = bbox(pts)
        area = w * h
        candidates.append((name, pts, origin, w, h, area))

    candidates.sort(key=lambda c: c[5])
    for name, pts, origin, w, h, area in candidates:
        if area < 1.0 or area > 500000.0:
            continue
        ox, oy = origin
        if abs(ox) > 10000.0 or abs(oy) > 10000.0:
            continue
        if len(pts) < 4:
            continue
        return pts, name
    return all_pts, None


def _single_board(all_pts: List[GerberPoint]) -> PanelInfo:
    if not all_pts:
        return PanelInfo(kind='single', instances=[], panel_origin=(0, 0))

    board_pts, chosen_name = _find_best_layer_pts(all_pts)
    origin, w, h = bbox(board_pts)
    instance = BoardInstance(origin=origin, w=w, h=h, sub_name=chosen_name, k=0)
    return PanelInfo(
        kind='single', instances=[instance],
        panel_origin=origin, panel_w=w, panel_h=h,
    )


def _find_panel_block_name(
    layer_names: List[Optional[str]],
    sub_names: List[str],
) -> Optional[str]:
    names_set = set(n for n in layer_names if n)
    sub_set = set(sub_names)
    for n in names_set:
        if n not in sub_set:
            return n
    return None

from typing import List, Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree

from services.gerber.gerber_parser import GerberPoint, parse_flashes, crop_to_instance
from services.gerber.panel_detector import BoardInstance, PanelInfo


class AlignResult:
    def __init__(
        self,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        rotation_angle: float = 0.0,
        n_matched: int = 0,
        n_total: int = 0,
        median_residual: float = -1.0,
        gko_priority: bool = False,
    ):
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.rotation_angle = rotation_angle
        self.n_matched = n_matched
        self.n_total = n_total
        self.median_residual = median_residual
        self.gko_priority = gko_priority

    def __repr__(self) -> str:
        flag = " [GKO_PRIORITY]" if self.gko_priority else ""
        return (
            f"AlignResult(offset=({self.offset_x:.4f}, {self.offset_y:.4f}), "
            f"angle={self.rotation_angle}°, matched={self.n_matched}/{self.n_total}, "
            f"residual={self.median_residual:.6f}mm){flag}"
        )


def _pp_to_array(pp_xs: List[float], pp_ys: List[float]) -> np.ndarray:
    return np.array(list(zip(pp_xs, pp_ys)), dtype=np.float64)


def estimate_offset_bbox(
    pp_xs: List[float],
    pp_ys: List[float],
    board_origin: Tuple[float, float],
    board_w: float,
    board_h: float,
) -> np.ndarray:
    if not pp_xs:
        return np.array([0.0, 0.0])
    mid_pp = np.array([(min(pp_xs) + max(pp_xs)) / 2.0,
                       (min(pp_ys) + max(pp_ys)) / 2.0])
    mid_board = np.array([board_origin[0] + board_w / 2.0,
                          board_origin[1] + board_h / 2.0])
    return mid_board - mid_pp


def estimate_adaptive_threshold(
    pp: np.ndarray,
    min_th: float = 0.8,
    max_th: float = 5.0,
    default: float = 8.0,
) -> float:
    """Ngưỡng khớp pad thích nghi theo mật độ component.

    Dữ liệu board dày (comp cách nhau chỉ ~1.5mm) làm ngưỡng cố định 8mm
    bắt nhầm pad của component lân cận → offset sai. Ngưỡng dùng nửa
    khoảng cách tối thiểu giữa 2 component, bị chặn trong [min_th, max_th].
    """
    n = len(pp)
    if n < 2:
        return default
    tree = cKDTree(pp)
    dists, _ = tree.query(pp, k=2)
    min_nn = float(dists[:, 1].min())
    return float(min(max(min_nn / 2.0, min_th), max_th))


def _solve_offset_from(
    gtp_pts: np.ndarray,
    pp: np.ndarray,
    offset0: np.ndarray,
    dist_threshold: float,
    max_iter: int = 20,
) -> Optional[Tuple[np.ndarray, int, float]]:
    offset = offset0.copy()
    prev_offset = offset.copy()
    per_component = np.empty((0, 2))

    for _ in range(max_iter):
        shifted = pp + offset
        tree = cKDTree(shifted)
        dist_pad, idx_pad = tree.query(gtp_pts)
        keep = dist_pad < dist_threshold

        if not np.any(keep):
            break

        groups = {}
        for gi, pi in zip(np.where(keep)[0], idx_pad[keep]):
            groups.setdefault(pi, []).append(gtp_pts[gi])

        per_component = np.array([
            np.mean(pts, axis=0) - pp[pi]
            for pi, pts in groups.items()
        ])

        if len(per_component) == 0:
            break

        new_offset = np.median(per_component, axis=0)
        offset = new_offset

        if np.linalg.norm(new_offset - prev_offset) < 1e-8:
            break
        prev_offset = new_offset.copy()

    if len(per_component) == 0:
        return None

    resid = per_component - offset
    dist_resid = np.linalg.norm(resid, axis=1)
    median_resid = float(np.median(dist_resid)) if len(dist_resid) > 0 else -1.0
    n_matched = len(per_component)

    return offset, n_matched, median_resid


def solve_offset_median(
    gtp_pts: np.ndarray,
    pp: np.ndarray,
    offset0: np.ndarray,
    max_iter: int = 20,
    dist_threshold: Optional[float] = None,
) -> Optional[Tuple[np.ndarray, int, float]]:
    if len(gtp_pts) == 0 or len(pp) == 0:
        return None
    if dist_threshold is None:
        dist_threshold = estimate_adaptive_threshold(pp)

    # Thử nhiều điểm khởi tạo: 0 (dữ liệu đã aligned) và offset0 (ước lượng
    # bbox/centroid). Dữ liệu thật vốn đã khớp pad nên offset thật = 0;
    # offset0 lớn do component phân bố lệch sẽ làm shift nhầm sang pad lân cận.
    # Chọn kết quả khớp được nhiều component nhất, ưu tiên residual nhỏ.
    candidates = [np.zeros(2, dtype=np.float64), np.asarray(offset0, dtype=np.float64)]
    best = None
    for cand in candidates:
        res = _solve_offset_from(gtp_pts, pp, cand, dist_threshold, max_iter)
        if res is None:
            continue
        offset, n_matched, resid = res
        if best is None:
            best = (offset, n_matched, resid)
            continue
        _, best_n, best_resid = best
        if n_matched > best_n:
            best = (offset, n_matched, resid)
        elif n_matched == best_n and resid < best_resid:
            best = (offset, n_matched, resid)

    return best


def try_rotation(
    gtp_pts: np.ndarray,
    pp: np.ndarray,
    angle_deg: float,
    dist_threshold: Optional[float] = None,
) -> Optional[Tuple[np.ndarray, int, float]]:
    theta = np.radians(angle_deg)
    R = np.array([[np.cos(theta), -np.sin(theta)],
                  [np.sin(theta), np.cos(theta)]])
    pp_rot = pp @ R.T

    mid_pp = pp_rot.mean(axis=0)
    mid_gtp = gtp_pts.mean(axis=0)
    offset0 = mid_gtp - mid_pp

    return solve_offset_median(gtp_pts, pp_rot, offset0, dist_threshold=dist_threshold)


def detect_best_rotation(
    gtp_pts: np.ndarray,
    pp: np.ndarray,
    dist_threshold: Optional[float] = None,
) -> AlignResult:
    best = None
    for angle in (0, 90, 180, 270):
        res = try_rotation(gtp_pts, pp, angle, dist_threshold)
        if res is None:
            continue
        offset, n_matched, resid = res
        if best is None:
            best = (angle, offset, n_matched, resid)
        else:
            _, _, best_n, best_resid = best
            if n_matched >= best_n * 0.5 and resid < best_resid:
                best = (angle, offset, n_matched, resid)

    if best is None:
        return AlignResult()

    angle, offset, n_matched, resid = best
    return AlignResult(
        offset_x=float(offset[0]),
        offset_y=float(offset[1]),
        rotation_angle=float(angle),
        n_matched=n_matched,
        median_residual=resid,
    )


def align_instance(
    instance: BoardInstance,
    pp_xs: List[float],
    pp_ys: List[float],
    gtp_pts: Optional[List[GerberPoint]] = None,
    gbp_pts: Optional[List[GerberPoint]] = None,
    layer: str = "top",
    is_panel: bool = False,
    dy_mm: float = 0.0,
    board_h: float = 0.0,
    detect_rotation: bool = True,
) -> AlignResult:
    pp = _pp_to_array(pp_xs, pp_ys)
    if len(pp) == 0:
        return AlignResult()

    board_origin = instance.origin
    board_w = instance.w
    board_h = board_h or instance.h

    offset0 = estimate_offset_bbox(pp_xs, pp_ys, board_origin, board_w, board_h)

    if gtp_pts is None and gbp_pts is None:
        # No paste data - use bounding-box estimate
        return AlignResult(
            offset_x=float(offset0[0]),
            offset_y=float(offset0[1]),
            rotation_angle=0.0,
            n_total=len(pp),
        )

    paste_pts = gbp_pts if layer.lower() in ("bottom", "bottomlayer") else gtp_pts
    if paste_pts is None or len(paste_pts) == 0:
        return AlignResult(
            offset_x=float(offset0[0]),
            offset_y=float(offset0[1]),
            rotation_angle=0.0,
            n_total=len(pp),
        )

    paste_np = np.array([(p.x_mm, p.y_mm) for p in paste_pts], dtype=np.float64)

    # Khởi tạo offset0 bằng centroid (mid_paste - mid_pp) thay vì bbox:
    # với dữ liệu đã aligned cho kết quả (0,0), khớp với ngưỡng thích nghi nhỏ.
    offset0 = paste_np.mean(axis=0) - pp.mean(axis=0)

    if detect_rotation:
        result = detect_best_rotation(paste_np, pp)
        if result.median_residual >= 0:
            return result

    result = solve_offset_median(paste_np, pp, offset0)
    if result is None:
        return AlignResult(
            offset_x=float(offset0[0]),
            offset_y=float(offset0[1]),
            n_total=len(pp),
        )
    offset, n_matched, resid = result
    return AlignResult(
        offset_x=float(offset[0]),
        offset_y=float(offset[1]),
        rotation_angle=0.0,
        n_matched=n_matched,
        n_total=len(pp),
        median_residual=resid,
    )

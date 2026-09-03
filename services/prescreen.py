"""Pre-screen checks for PickPlace review data.

Pure logic (no Qt imports) so it stays unit-testable offscreen.
Four checks: ROT / PAD / DUP / OUT — see PrescreenConfig thresholds.
"""

from collections import Counter
from dataclasses import dataclass, field
import math
import statistics
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from models.review import ReviewRecord
from services.gerber.offset_applier import ComponentTransform, finalize_frame
from ui.i18n import tr

KIND_ROT = "ROT"
KIND_PAD = "PAD"
KIND_DUP = "DUP"
KIND_OUT = "OUT"

_KIND_ORDER = {KIND_OUT: 0, KIND_PAD: 1, KIND_DUP: 2, KIND_ROT: 3}

_PAD_SEARCH_CELL = 1.0
_PAD_DIST_CAP = 1_000_000.0


@dataclass
class PrescreenConfig:
    enabled: bool = True
    rot_dev: float = 90.0
    rot_min_group: int = 2
    dup_tol: float = 0.05
    pad_median_tol: float = 2.0
    out_margin: float = 1.0


@dataclass
class PrescreenIssue:
    kind: str
    index: int
    designator: str
    x: float
    y: float
    detail: str = ""

    @property
    def dismiss_key(self) -> str:
        return f"{self.kind}:{self.designator}:{self.x:.3f}:{self.y:.3f}"


BBox = Tuple[float, float, float, float]
PastePoints = Sequence[Tuple[float, float]]


def eff_x(rec: ReviewRecord) -> float:
    return rec.new_x if rec.new_x is not None else rec.old_x


def eff_y(rec: ReviewRecord) -> float:
    return rec.new_y if rec.new_y is not None else rec.old_y


def eff_rotation(rec: ReviewRecord) -> float:
    val = rec.new_rotation if rec.new_rotation is not None else rec.old_rotation
    return float(val) % 360.0


def dismiss_key_for(kind: str, rec: ReviewRecord) -> str:
    return f"{kind}:{rec.designator}:{eff_x(rec):.3f}:{eff_y(rec):.3f}"


def _circ_dist(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _grid_buckets(
    pts: Sequence[Tuple[float, float]], cell: float
) -> Dict[Tuple[int, int], List[int]]:
    buckets: Dict[Tuple[int, int], List[int]] = {}
    for i, (x, y) in enumerate(pts):
        buckets.setdefault((int(x // cell), int(y // cell)), []).append(i)
    return buckets


def _check_dup(
    records: List[ReviewRecord], coords: List[Tuple[float, float]], tol: float
) -> List[PrescreenIssue]:
    issues: List[PrescreenIssue] = []
    if tol <= 0:
        return issues
    buckets = _grid_buckets(coords, max(tol, 1e-9))
    claimed: set = set()
    for i, (x, y) in enumerate(coords):
        bx, by = int(x // max(tol, 1e-9)), int(y // max(tol, 1e-9))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in buckets.get((bx + dx, by + dy), ()):
                    if j <= i or j in claimed:
                        continue
                    ox, oy = coords[j]
                    if abs(ox - x) <= tol and abs(oy - y) <= tol:
                        claimed.add(j)
                        rec = records[j]
                        other = records[i]
                        issues.append(PrescreenIssue(
                            kind=KIND_DUP,
                            index=j,
                            designator=rec.designator,
                            x=ox, y=oy,
                            detail=tr("duplicate coordinates with {des}", des=other.designator),
                        ))
                        break
    return issues


def _check_rot(
    records: List[ReviewRecord], rots: List[float], cfg: PrescreenConfig
) -> List[PrescreenIssue]:
    issues: List[PrescreenIssue] = []
    groups: Dict[str, List[int]] = {}
    for i, r in enumerate(records):
        mpn = (r.mpn or "").strip()
        if not mpn:
            continue
        groups.setdefault(mpn, []).append(i)
    for mpn, idxs in groups.items():
        if len(idxs) < max(cfg.rot_min_group, 2):
            continue
        counter: Counter = Counter()
        rep: Dict[float, float] = {}
        for i in idxs:
            key = round(rots[i], 1)
            counter[key] += 1
            rep.setdefault(key, rots[i])
        majority_key, _cnt = counter.most_common(1)[0]
        majority = rep[majority_key]
        for i in idxs:
            dev = _circ_dist(rots[i], majority)
            if dev > cfg.rot_dev:
                rec = records[i]
                issues.append(PrescreenIssue(
                    kind=KIND_ROT,
                    index=i,
                    designator=rec.designator,
                    x=eff_x(rec), y=eff_y(rec),
                    detail=tr(
                        "rotation {rot:.0f}\u00b0 differs from MPN majority {maj:.0f}\u00b0 ({mpn})",
                        rot=rots[i], maj=majority, mpn=mpn,
                    ),
                ))
    return issues


def _nearest_paste_distance(
    x: float, y: float,
    buckets: Dict[Tuple[int, int], List[Tuple[float, float]]],
    cell: float,
) -> float:
    cx = int(x // cell)
    cy = int(y // cell)
    best: Optional[float] = None
    r = 0
    max_r = int(_PAD_DIST_CAP / cell) + 1
    while r <= max_r:
        for i in range(cx - r, cx + r + 1):
            for j in range(cy - r, cy + r + 1):
                if r > 0 and max(abs(i - cx), abs(j - cy)) != r:
                    continue
                for px, py in buckets.get((i, j), ()):
                    d = math.hypot(px - x, py - y)
                    if best is None or d < best:
                        best = d
        if best is not None and best <= r * cell:
            return best
        r += 1
    return best if best is not None else _PAD_DIST_CAP


def _pad_distances(
    coords: List[Tuple[float, float]],
    layers: List[str],
    paste_top: Optional[PastePoints],
    paste_bottom: Optional[PastePoints],
) -> List[float]:
    sources = {"top": paste_top, "bottom": paste_bottom}
    grids: Dict[str, Tuple[Dict[Tuple[int, int], List[Tuple[float, float]]], PastePoints]] = {}
    cell = _PAD_SEARCH_CELL
    for name, pts in sources.items():
        if pts:
            buckets: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
            for px, py in pts:
                buckets.setdefault((int(px // cell), int(py // cell)), []).append((px, py))
            grids[name] = (buckets, pts)
    dists: List[float] = []
    for i, (x, y) in enumerate(coords):
        g = grids.get(layers[i])
        if g is None:
            continue
        dists.append(_nearest_paste_distance(x, y, g[0], cell))
    return dists


def compute_pad_stats(
    records: Sequence[ReviewRecord],
    coords: Optional[Sequence[Tuple[float, float]]] = None,
    paste_top: Optional[PastePoints] = None,
    paste_bottom: Optional[PastePoints] = None,
) -> Dict[str, Optional[float]]:
    """Nearest-paste distance statistics over all evaluable components.

    Distances are measured per component against the paste layer matching its
    own side; components whose side has no paste data are skipped.
    """
    recs = list(records)
    if coords is None:
        coords = [(eff_x(r), eff_y(r)) for r in recs]
    else:
        coords = [(float(x), float(y)) for x, y in coords]
    layers = [("bottom" if "bot" in (r.layer or "").lower() else "top") for r in recs]
    dists = _pad_distances(coords, layers, paste_top, paste_bottom)
    if not dists:
        return {"n": 0, "median_mm": None, "p95_mm": None}
    ds = sorted(min(d, _PAD_DIST_CAP) for d in dists)
    med = statistics.median(ds)
    p95 = ds[min(len(ds) - 1, int(round(0.95 * (len(ds) - 1))))]
    return {"n": len(ds), "median_mm": float(med), "p95_mm": float(p95)}


def _check_out(
    records: List[ReviewRecord],
    coords: List[Tuple[float, float]],
    outline_bbox: Optional[BBox],
    margin: float,
) -> List[PrescreenIssue]:
    issues: List[PrescreenIssue] = []
    if outline_bbox is None:
        return issues
    min_x, min_y, max_x, max_y = outline_bbox
    min_x -= margin
    min_y -= margin
    max_x += margin
    max_y += margin
    for i, (x, y) in enumerate(coords):
        if x < min_x or x > max_x or y < min_y or y > max_y:
            rec = records[i]
            issues.append(PrescreenIssue(
                kind=KIND_OUT,
                index=i,
                designator=rec.designator,
                x=x, y=y,
                detail=tr("outside board outline (+{margin:g} mm)", margin=margin),
            ))
    return issues


def run_prescreen(
    records: Sequence[ReviewRecord],
    paste_top: Optional[PastePoints] = None,
    paste_bottom: Optional[PastePoints] = None,
    outline_bbox: Optional[BBox] = None,
    cfg: Optional[PrescreenConfig] = None,
    dismissed: FrozenSet[str] = frozenset(),
    coords: Optional[Sequence[Tuple[float, float]]] = None,
    rots: Optional[Sequence[float]] = None,
) -> List[PrescreenIssue]:
    """Run the four checks.

    `coords`/`rots` override the per-record coordinates/rotations used by the
    checks (index-aligned with `records`). The Align wizard passes arrays in
    the RAW GERBER frame (orig + alignment offset, before panel-origin
    translation/board rotation/mirror) so PAD/OUT compare against raw GKO/GTP
    geometry correctly. When None, effective record values are used.
    """
    cfg = cfg or PrescreenConfig()
    if not cfg.enabled or not records:
        return []
    recs = list(records)
    if coords is None:
        coords = [(eff_x(r), eff_y(r)) for r in recs]
    else:
        coords = [(float(x), float(y)) for x, y in coords]
    if rots is None:
        rots = [eff_rotation(r) for r in recs]
    else:
        rots = [float(v) % 360.0 for v in rots]

    issues: List[PrescreenIssue] = []
    issues.extend(_check_out(recs, coords, outline_bbox, cfg.out_margin))
    pad_stats = compute_pad_stats(recs, coords=coords, paste_top=paste_top,
                                  paste_bottom=paste_bottom)
    if pad_stats["n"] and pad_stats["median_mm"] is not None \
            and pad_stats["median_mm"] > cfg.pad_median_tol:
        issues.append(PrescreenIssue(
            kind=KIND_PAD,
            index=-1,
            designator="",
            x=0.0, y=0.0,
            detail=tr(
                "median nearest-pad distance {v:.2f} mm exceeds tolerance {tol:g} mm",
                v=pad_stats["median_mm"], tol=cfg.pad_median_tol,
            ),
        ))
    issues.extend(_check_dup(recs, coords, cfg.dup_tol))
    issues.extend(_check_rot(recs, rots, cfg))

    if dismissed:
        issues = [iss for iss in issues if iss.dismiss_key not in dismissed]
    issues.sort(key=lambda iss: (_KIND_ORDER.get(iss.kind, 99), iss.index))
    return issues


def summarize(issues: Iterable[PrescreenIssue]) -> Dict[str, int]:
    counts = {KIND_ROT: 0, KIND_PAD: 0, KIND_DUP: 0, KIND_OUT: 0}
    for iss in issues:
        counts[iss.kind] = counts.get(iss.kind, 0) + 1
    counts["TOTAL"] = sum(counts[k] for k in (KIND_ROT, KIND_PAD, KIND_DUP, KIND_OUT))
    return counts


def transform_points_through_align(
    points: Sequence[Tuple[float, float]],
    layer: str,
    align_results: Optional[dict] = None,
    panel_info=None,
    origin_mode: str = 'panel',
    rotation_angle: int = 0,
    rot_layers: Optional[Dict[str, bool]] = None,
    instance_ks: Optional[Sequence[int]] = None,
) -> List[Tuple[float, float]]:
    """Map raw-gerber-frame points into the FINAL record frame.

    Records go through: step4 offset -> step4b panel translate -> step6 board
    rotate -> step7 bottom mirror. Alignment guarantees gerber points already
    satisfy `point ~= orig + offset`, so here we only re-apply the LAST three
    stages (finalize_frame) to land in the same frame the records end up in.
    Uses the exact same ComponentTransform pipeline as component alignment.
    """
    if panel_info is None:
        return [(float(x), float(y)) for x, y in points]
    out: List[Tuple[float, float]] = []
    for i, (x, y) in enumerate(points):
        k = instance_ks[i] if instance_ks is not None else 0
        ct = ComponentTransform(
            designator="", layer=layer,
            orig_x=float(x), orig_y=float(y), orig_rotation=0.0,
            instance_k=k,
        )
        ct.new_x = float(x)
        ct.new_y = float(y)
        ct.new_rotation = 0.0
        finalize_frame(ct, panel_info, origin_mode, rotation_angle, rot_layers)
        nx = ct.new_x if ct.new_x is not None else x
        ny = ct.new_y if ct.new_y is not None else y
        out.append((nx, ny))
    return out


def assign_instance_by_y(y: float, panel_info) -> int:
    """Same y-midpoint rule AlignWorker uses to assign components."""
    if panel_info is None:
        return 0
    try:
        instances = panel_info.instances
        is_panel = panel_info.is_panel and panel_info.count > 1
    except AttributeError:
        return 0
    if not is_panel or not instances:
        return 0
    best_k, best_dist = 0, float("inf")
    for inst in instances:
        mid_y = inst.origin[1] + inst.h / 2
        d = abs(y - mid_y)
        if d < best_dist:
            best_dist, best_k = d, inst.k
    return best_k


def pack_prescreen_ctx(ctx: Optional[dict]) -> Optional[Dict[str, Any]]:
    """Serialize a prescreen ctx (align_results/panel_info/...) to JSON-safe dict."""
    if not ctx:
        return None
    from services.gerber.panel_detector import PanelInfo
    from services.gerber.origin_aligner import AlignResult

    align_results_out: Dict[str, Any] = {}
    for k, layer_results in (ctx.get("align_results") or {}).items():
        entry: Dict[str, Any] = {}
        for layer, res in (layer_results or {}).items():
            if isinstance(res, AlignResult):
                entry[layer] = res.to_dict()
            elif isinstance(res, dict):
                entry[layer] = res
        align_results_out[str(int(k))] = entry

    panel_info = ctx.get("panel_info")
    panel_dict = panel_info.to_dict() if isinstance(panel_info, PanelInfo) else None

    return {
        "align_results": align_results_out,
        "panel_info": panel_dict,
        "origin_mode": ctx.get("origin_mode", "panel"),
        "rotation_angle": int(ctx.get("rotation_angle") or 0),
        "rot_layers": dict(ctx.get("rot_layers") or {"top": True, "bottom": False}),
    }


def unpack_prescreen_ctx(data: Optional[dict]) -> Optional[dict]:
    """Rebuild a live prescreen ctx from its packed JSON-safe form."""
    if not data:
        return None
    from services.gerber.panel_detector import PanelInfo

    raw_align = data.get("align_results") or {}
    align_results: Dict[int, Dict[str, Any]] = {}
    for key, layer_results in raw_align.items():
        entry: Dict[str, Any] = {}
        for layer, res in (layer_results or {}).items():
            if isinstance(res, dict):
                from services.gerber.origin_aligner import AlignResult
                entry[layer] = AlignResult.from_dict(res)
            else:
                entry[layer] = res
        try:
            align_results[int(key)] = entry
        except (TypeError, ValueError):
            continue

    raw_panel = data.get("panel_info")
    panel_info = PanelInfo.from_dict(raw_panel) if isinstance(raw_panel, dict) else None

    return {
        "align_results": align_results,
        "panel_info": panel_info,
        "origin_mode": data.get("origin_mode", "panel"),
        "rotation_angle": int(data.get("rotation_angle") or 0),
        "rot_layers": dict(data.get("rot_layers") or {"top": True, "bottom": False}),
    }

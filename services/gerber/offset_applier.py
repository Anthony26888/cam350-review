import math
from typing import Dict, List, Optional, Tuple


GKO_PRIORITY_TOL = 0.01


def _layer_frame(layer: str) -> str:
    l = layer.strip().lower()
    return "bottom" if l in ("bottom", "bottomlayer") else "top"


class ComponentTransform:
    def __init__(
        self,
        designator: str,
        layer: str,
        orig_x: float,
        orig_y: float,
        orig_rotation: float,
        instance_k: Optional[int] = None,
    ):
        self.designator = designator
        self.layer = layer
        self.orig_x = orig_x
        self.orig_y = orig_y
        self.orig_rotation = orig_rotation
        self.instance_k = instance_k
        self.new_x: Optional[float] = None
        self.new_y: Optional[float] = None
        self.new_rotation: Optional[float] = None


def rotate_point(x: float, y: float, angle_deg: float) -> Tuple[float, float]:
    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    return (x * c - y * s, x * s + y * c)


def step4_apply_offset(
    comp: ComponentTransform,
    offset_x: float,
    offset_y: float,
    rotation_angle: float,
) -> None:
    if rotation_angle != 0:
        xr, yr = rotate_point(comp.orig_x, comp.orig_y, rotation_angle)
        comp.new_x = xr + offset_x
        comp.new_y = yr + offset_y
        comp.new_rotation = (comp.orig_rotation + rotation_angle) % 360
    else:
        comp.new_x = comp.orig_x + offset_x
        comp.new_y = comp.orig_y + offset_y
        comp.new_rotation = comp.orig_rotation


def step4b_translate_to_panel_origin(
    comp: ComponentTransform,
    panel_origin_x: float,
    panel_origin_y: float,
) -> None:
    if comp.new_x is not None:
        comp.new_x -= panel_origin_x
    if comp.new_y is not None:
        comp.new_y -= panel_origin_y


def step6_rotate(
    comp: ComponentTransform,
    board_w: float,
    board_h: float,
    angle_deg: int = 0,
) -> None:
    if angle_deg == 0:
        return
    layer_norm = comp.layer.strip().lower()
    x = comp.new_x if comp.new_x is not None else comp.orig_x
    y = comp.new_y if comp.new_y is not None else comp.orig_y
    r_orig = comp.new_rotation if comp.new_rotation is not None else comp.orig_rotation

    if layer_norm in ("top", "toplayer"):
        if angle_deg == 90:
            x2 = board_h - y
            y2 = x
            r2 = (r_orig + 90) % 360
        elif angle_deg == 180:
            x2 = board_w - x
            y2 = board_h - y
            r2 = (r_orig + 180) % 360
        elif angle_deg == 270:
            x2 = y
            y2 = board_w - x
            r2 = (r_orig + 270) % 360
        else:
            return
    elif layer_norm in ("bottom", "bottomlayer"):
        if angle_deg == 90:
            x2 = y
            y2 = x
            r2 = (r_orig - 90) % 360
        elif angle_deg == 180:
            x2 = board_w - x
            y2 = board_h - y
            r2 = (r_orig - 180) % 360
        elif angle_deg == 270:
            x2 = board_h + y
            y2 = -x
            r2 = (r_orig - 270) % 360
        else:
            return
    else:
        return

    comp.new_x = x2
    comp.new_y = y2
    comp.new_rotation = r2


def step7_mirror_bottom(
    comp: ComponentTransform,
    ref_width: float,
) -> None:
    layer_norm = comp.layer.strip().lower()
    if layer_norm not in ("bottom", "bottomlayer"):
        return

    x = comp.new_x if comp.new_x is not None else comp.orig_x
    comp.new_x = ref_width - x
    if comp.new_y is None:
        comp.new_y = comp.orig_y
    if comp.new_rotation is None:
        comp.new_rotation = comp.orig_rotation


def _apply_gko_priority(
    result,
    ref_origin: Tuple[float, float],
) -> bool:
    """Ưu tiên gốc từ GKO khi offset khớp pad (GTP) mâu thuẫn với nó.

    GTP chỉ được tin khi khớp gốc GKO trong ngưỡng GKO_PRIORITY_TOL mm.
    Nếu lệch quá ngưỡng và khớp pad không đủ tin cậy (tỷ lệ match thấp
    hoặc residual cao), ghi đè offset bằng gốc GKO để tọa độ component
    giữ nguyên (new = orig), tránh dịch nhầm toàn hệ thống.
    """
    if result.n_matched <= 0:
        return False

    offset = (result.offset_x, result.offset_y)
    delta = math.hypot(offset[0] - ref_origin[0], offset[1] - ref_origin[1])
    if delta <= GKO_PRIORITY_TOL:
        return False

    n_total = result.n_total or 0
    match_ratio = (result.n_matched / n_total) if n_total else 0.0
    unreliable = match_ratio < 0.5 or result.median_residual > 0.5
    if not unreliable:
        return False

    result.offset_x = ref_origin[0]
    result.offset_y = ref_origin[1]
    result.gko_priority = True
    return True


def finalize_frame(
    comp: ComponentTransform,
    panel_info,
    origin_mode: str = 'panel',
    rotation_angle: int = 0,
    rot_layers: Optional[Dict[str, bool]] = None,
) -> None:
    """STEP 4B/6/7: panel-origin translate, board rotate, bottom mirror.

    Operates on whatever new_x/new_y/new_rotation the component already
    carries (falls back to orig_*). Shared by apply_all_transforms and the
    pre-screen gerber-frame mapping so both sides undergo the exact same
    final-frame pipeline.
    """
    if rot_layers is None:
        rot_layers = {"top": True, "bottom": False}

    layer_norm = _layer_frame(comp.layer)

    if origin_mode == 'panel':
        step4b_translate_to_panel_origin(
            comp, panel_info.panel_origin[0], panel_info.panel_origin[1]
        )

    instance = None
    k = comp.instance_k or 0
    if 0 <= k < len(panel_info.instances):
        instance = panel_info.instances[k]

    # STEP 6: Apply panel/board rotation (only for layers enabled in rot_layers)
    if rotation_angle != 0:
        if rot_layers.get(layer_norm, False):
            if origin_mode == 'panel':
                w = panel_info.panel_w
                h = panel_info.panel_h
            else:
                if instance is None:
                    return
                w = instance.w
                h = instance.h
            step6_rotate(comp, w, h, rotation_angle)

    # STEP 7: Mirror Bottom
    skip_mirror = False
    if rotation_angle in (90, 270) and layer_norm == "bottom":
        if rot_layers.get("bottom", False):
            skip_mirror = True
    if not skip_mirror:
        swap_wh = rotation_angle in (90, 270)
        if origin_mode == 'panel':
            ref_w = panel_info.panel_h if swap_wh else panel_info.panel_w
        else:
            if instance is None:
                return
            ref_w = instance.h if swap_wh else instance.w
        step7_mirror_bottom(comp, ref_w)


def apply_all_transforms(
    components: List[ComponentTransform],
    panel_info,
    align_results: dict,
    origin_mode: str = 'panel',
    rotation_angle: int = 0,
    rot_layers: Optional[Dict[str, bool]] = None,
) -> None:
    if rot_layers is None:
        rot_layers = {"top": True, "bottom": False}

    for comp in components:
        k = comp.instance_k or 0
        result = align_results.get(k)
        if result is None:
            continue
        if isinstance(result, dict):
            result = result.get(_layer_frame(comp.layer)) or result.get("top")

        if result is None:
            continue

        instance = panel_info.instances[k] if k < len(panel_info.instances) else None
        if instance is None:
            continue

        # STEP 3.9: Ưu tiên gốc GKO khi offset khớp pad (GTP) mâu thuẫn
        ref_origin = (
            panel_info.panel_origin if origin_mode == 'panel' else instance.origin
        )
        _apply_gko_priority(result, ref_origin)

        # STEP 4: Apply offset + rotation
        step4_apply_offset(comp, result.offset_x, result.offset_y, result.rotation_angle)

        # STEP 4B/6/7
        finalize_frame(comp, panel_info, origin_mode, rotation_angle, rot_layers)


def round_coord(value: float, decimals: int = 4) -> float:
    return round(value, decimals)

import math
import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    Qt, QRect, QRectF, QPointF, QPoint, QSize, QThread, QTimer, Signal,
    QEventLoop,
)
from PySide6.QtGui import (
    QBrush, QColor, QPen, QPainter, QPainterPath, QPolygonF, QRegion,
    QWheelEvent, QFont, QFontMetricsF, QTransform, QPixmap, QMouseEvent, QIcon,
    QCursor, QAction, QActionGroup,
)
from config.config_manager import ConfigManager
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPathItem,
    QGraphicsEllipseItem,
    QComboBox,
    QCheckBox, QGroupBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDoubleSpinBox, QSpinBox, QWidget, QDialog,
    QSizePolicy, QFrame, QColorDialog, QGridLayout, QMenu,
    QProgressBar, QApplication, QFileDialog, QSplitter,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QToolButton, QStyle, QToolBar, QProgressDialog,
)

from models.review import ReviewRecord
from ui.i18n import tr
from ui.style import err_color, muted_color
from ui.rotation_edit_dialog import RotationEditDialog
from services.gerber.gerber_render import (
    RenderData, LineShape, ArcShape, FlashShape, parse_render,
)
from services.gerber.gerber_render_lib import load_drill, load_layer, parse_layer
from services.gerber.drill_aligner import align_drill, points_bbox, shift_render_data
from services.gerber.aperture_picker import ApertureIndex
from services.gerber.layer_scan import (
    LayerInfo, ROLE_COPPER, ROLE_DRILL, ROLE_MASK, ROLE_OTHER, ROLE_PASTE,
    ROLE_PROFILE, ROLE_SILK, SIDE_BOTTOM, SIDE_NONE, SIDE_TOP,
)
from services.gerber.gerber_export import ExportLayer, export_layers
from services.gerber.render.layer import LayerItem, build_layer_paths
from ui.zoom_controller import (
    ZOOM_PRESETS,
    clamp_zoom_factor,
    create_zoom_controller,
    next_preset,
    scale_from_zoom_factor,
    zoom_factor_from_scale,
)
from services.gerber.gerber_transform import (
    AffineTransform, apply_transform, apply_inverse_transform, transform_rot,
)
from services.gerber.trace_net import (
    build_index, find_shortest_path, is_copper_plane, pick_seed, trace_component,
)
from utils.path_utils import resource_path

OUTLINE_COLOR = QColor("#F8FAFC")
TOP_PASTE_COLOR = QColor(34, 211, 238, 210)
BOTTOM_PASTE_COLOR = QColor(251, 191, 36, 210)
SILK_COLOR = QColor(240, 171, 252, 220)
COPPER_COLOR = QColor("#D97706")
MASK_COLOR = QColor("#60A5FA")
OTHER_COLOR = QColor("#94A3B8")
DRILL_COLOR = QColor(96, 165, 250, 235)

#: The colours of the palette of the card, for a dark background.  The
#: first row holds the strong colours, the rest the lighter ones.
LAYER_PALETTE = (
    "#FF5555", "#FF8C00", "#FFD700", "#C8FF00", "#00E676", "#00E5FF",
    "#4D7CFF", "#8A6CFF", "#FF6BD6", "#FFFFFF", "#FFB3B3", "#FFD9A0",
    "#FFF3B0", "#DCFFA8", "#A8FFD8", "#A8E8FF", "#A8C0FF", "#C8B3FF",
    "#FFA8E8", "#B0B0B0", "#7A7A7A", "#5A3E2B", "#2F6B4F", "#7B2F4F",
)

#: The width of the card of the layers, open and closed.
CARD_WIDTH = 350
CARD_WIDTH_COLLAPSED = 36

#: The colour of the mark of the origin of the coordinates.
ORIGIN_COLOR = QColor("#C0C0C0")
#: The half length of the diagonals that mark the origin, in millimetres.
ORIGIN_MARKER_HALF = 1.5

#: The area the page can be scrolled in, in millimetres.  It is very big,
#: so that nothing holds the view back: the zoom factor is what limits
#: how far the page can be shrunk.
SCENE_MARGIN = 1_000_000.0

#: The order the items are drawn in.  The grid lies under the artwork,
#: and the marks of the Pick&Place lie over it, so that a pad never
#: hides them.
Z_GRID = 60
Z_MEASURE = 1200
Z_ORIGIN_MARK = 1300
Z_GOTO_CROSS = 1400
Z_PICKPLACE = 1500
#: The net that is traced lies over every layer of the picture, but
#: under the measure tool, the crosshair and the marks of Pick&Place.
Z_TRACE = 900

#: The place of a layer in the stack by its role.  The copper always
#: lies at the bottom, so the paste, the mask and the silk stay on top
#: of it no matter which layer is active.  The steps of a role are a
#: tenth wide, so even ten inner planes of copper stay well under the
#: mask tier.
_LAYER_ROLE_BASE = {
    ROLE_PROFILE: 0.0,
    ROLE_COPPER: 5.0,
    ROLE_MASK: 10.0,
    ROLE_PASTE: 15.0,
    ROLE_SILK: 20.0,
    ROLE_DRILL: 25.0,
    ROLE_OTHER: 30.0,
}

#: How much a layer that is active gains, so that the active paste, mask
#: or silk stands out over the layers of the same kind below it.  The
#: copper never gains: it has to stay under everything.
_LAYER_ACTIVE_BUMP = 7.0
CROSS_COLOR = QColor("#EF4444")
HIGHLIGHT_COLOR = QColor("#39FF14")
CHECKED_COLOR = QColor("#22C55E")
GRID_COLOR = QColor(100, 116, 139, 160)
BACKGROUND = QColor("#0B1220")
MEASURE_COLOR = QColor("#38BDF8")
#: The colour of the net that is traced: a bright yellow, far from the
#: blue of the measure tool and the green of the checked marks.
TRACE_COLOR = QColor(255, 214, 10)
#: The width of the lines of a traced net, in millimetres.  The wires
#: that lead below this width are drawn at this width, so the chain of
#: the net is seen at any zoom.
_TRACE_LINE_WIDTH = 0.6

_CROSS_BOARD_RATIO = 0.01
_MIN_ARROW_PX = 10.0
_MIN_ARROW_WING_RATIO = 0.3

#: Fraction of the smaller viewport side that starts the auto panning.
_AUTO_PAN_MARGIN = 0.02

#: Interval of the auto panning timer, in milliseconds.
_AUTO_PAN_INTERVAL_MS = 4

#: The state of a layer in the list of layers.
LAYER_STATE_NORMAL = "normal"
LAYER_STATE_DIMMED = "dimmed"
LAYER_STATE_HIDDEN = "hidden"

#: How much of the colour a layer that is dimmed keeps.
LAYER_DIMMED_ALPHA = 76

from ui.icons import lucide_qicon, status_icon


def _build_status_icon(checked: bool) -> QIcon:
    return status_icon(checked)


def _layer_key(layer: str) -> str:
    l = layer.strip().lower()
    if l in ("top", "toplayer", "toplayer.", "top layer", "l1"):
        return "top"
    if l in ("bottom", "bottomlayer", "bottomlayer.", "bottom layer", "l2"):
        return "bottom"
    return "top"


def _record_coord(record: ReviewRecord) -> Tuple[float, float, float]:
    x = record.new_x if record.new_x is not None else record.old_x
    y = record.new_y if record.new_y is not None else record.old_y
    rotation = record.new_rotation if record.new_rotation is not None else record.old_rotation
    return x, y, rotation


#: Pad snap falls back across these roles, best first.
_PAD_SNAP_ROLES = (ROLE_PASTE, ROLE_MASK, ROLE_COPPER)

#: Vertices of a punched-out circle hole in an aperture macro.
_HOLE_SEGS = 24


def _flash_size(fl: FlashShape) -> float:
    if fl.kind == "macro":
        if fl.macro is not None:
            xs: List[float] = []
            ys: List[float] = []
            for poly in fl.macro.polygons:
                xs += [p[0] for p in poly]
                ys += [p[1] for p in poly]
            for mx, my, r in fl.macro.circles:
                xs += [mx - r, mx + r]
                ys += [my - r, my + r]
            for _x1, _y1, x2, y2, _w in fl.macro.segments:
                xs.append(x2)
                ys.append(y2)
            if xs:
                return max(max(xs) - min(xs), max(ys) - min(ys))
        return 1.0
    if fl.kind in ("rect", "oblong"):
        return min(fl.w, fl.h)
    if fl.kind == "polygon" and fl.pts:
        xs = [p[0] for p in fl.pts]
        ys = [p[1] for p in fl.pts]
        return max(max(xs) - min(xs), max(ys) - min(ys))
    return fl.w or 0.3


def _flash_center(fl: FlashShape) -> Tuple[float, float]:
    """Effective pad centre for snap and pick operations."""
    if fl.kind == "polygon" and fl.pts and not fl.pts_local:
        xs = [p[0] for p in fl.pts]
        ys = [p[1] for p in fl.pts]
        return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    return fl.cx, fl.cy


def _paste_stroke_pads(data: RenderData) -> List[Tuple[float, float, float]]:
    """Derive pad centres from isolated strokes on solder paste layers.

    Many CAD systems output surface mount pads as short D01 strokes with
    rectangular or circular apertures rather than flashed apertures.
    Strokes that form connected outlines (like board edges or pour contours)
    are excluded by checking that both endpoints are isolated.
    """
    lines = [ln for ln in data.lines if not ln.negative]
    if not lines:
        return []
    cnt: Dict[Tuple[float, float], int] = defaultdict(int)
    endpoints: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for ln in lines:
        p1 = (round(ln.x1, 3), round(ln.y1, 3))
        p2 = (round(ln.x2, 3), round(ln.y2, 3))
        endpoints.append((p1, p2))
        cnt[p1] += 1
        cnt[p2] += 1

    pads: List[Tuple[float, float, float]] = []
    for ln, (p1, p2) in zip(lines, endpoints):
        if cnt[p1] == 1 and cnt[p2] == 1:
            mx = (ln.x1 + ln.x2) / 2.0
            my = (ln.y1 + ln.y2) / 2.0
            length = math.hypot(ln.x2 - ln.x1, ln.y2 - ln.y1)
            ap = data.apertures.get(ln.dcode)
            dims = [abs(p) for p in (ap.params if ap else ())]
            ap_size = max(dims) if dims else ln.width
            size = max(ap_size, length)
            pads.append((mx, my, size))
    return pads


def _nearest_pad_size(pads_raw, x: float, y: float) -> Optional[float]:
    best: Optional[float] = None
    best_d: Optional[float] = None
    for px, py, size in pads_raw:
        d = math.hypot(px - x, py - y)
        tol = max(1.0, size)
        if d <= tol and (best_d is None or d < best_d):
            best_d = d
            best = size
    return best


class PadGrid:
    """Spatial hash for nearest-pad queries.

    Pads are bucketed into a uniform grid; a query scans only the cells that
    can possibly contain a pad within its tolerance (max(1, size)), turning
    the per-record linear scan (O(n)) into a near-constant lookup.
    """

    _CELL = 5.0

    def __init__(self, pads: List[Tuple[float, float, float]]) -> None:
        self._max_tol = 1.0
        for _px, _py, size in pads:
            tol = max(1.0, size)
            if tol > self._max_tol:
                self._max_tol = tol
        self._radius = max(1, int(math.ceil(self._max_tol / self._CELL)))
        self._cells: Dict[Tuple[int, int], List[Tuple[float, float, float]]] = {}
        for px, py, size in pads:
            key = (int(px // self._CELL), int(py // self._CELL))
            self._cells.setdefault(key, []).append((px, py, size))

    def nearest_point(self, x: float, y: float,
                      tol: float = 1.0) -> Optional[Tuple[float, float, float]]:
        best: Optional[Tuple[float, float, float]] = None
        best_d: Optional[float] = None
        cx, cy = int(x // self._CELL), int(y // self._CELL)
        r = max(self._radius, int(math.ceil(tol / self._CELL)))
        for i in range(cx - r, cx + r + 1):
            for j in range(cy - r, cy + r + 1):
                for px, py, size in self._cells.get((i, j), ()):
                    d = math.hypot(px - x, py - y)
                    t = max(tol, size)
                    if d <= t and (best_d is None or d < best_d):
                        best_d = d
                        best = (px, py, size)
        return best

    def nearest(self, x: float, y: float) -> Optional[float]:
        hit = self.nearest_point(x, y)
        return hit[2] if hit is not None else None

    def is_empty(self) -> bool:
        return not self._cells


def _target_icon(size: int = 24) -> QIcon:
    return lucide_qicon("crosshair", accent="#60A5FA", size=size)


def _rotate_icon(size: int = 24) -> QIcon:
    return lucide_qicon("rotate-cw", accent="#F59E0B", size=size)


def _mirror_icon(size: int = 24, horizontal: bool = False,
                 accent: Optional[QColor] = None) -> QIcon:
    accent_str = accent.name(QColor.HexRgb) if accent is not None else None
    name = (
        "triangles-centerline-dashed-horizontal"
        if not horizontal
        else "triangles-centerline-dashed-vertical"
    )
    return lucide_qicon(name, accent=accent_str, size=size)


def _flip_x_icon(size: int = 24) -> QIcon:
    return lucide_qicon(
        "triangles-centerline-dashed-horizontal", accent="#22D3EE", size=size
    )


def _flip_y_icon(size: int = 24) -> QIcon:
    return lucide_qicon(
        "triangles-centerline-dashed-vertical", accent="#2DD4BF", size=size
    )


def _trace_icon(size: int = 24) -> QIcon:
    return lucide_qicon("route", accent="#FFD60A", size=size)


def _grid_icon(size: int = 24) -> QIcon:
    return lucide_qicon("grid-3x3", accent="#A78BFA", size=size)


def _pickplace_icon(size: int = 24) -> QIcon:
    return lucide_qicon("component", accent="#EF4444", size=size)


def _fit_icon(size: int = 24) -> QIcon:
    return lucide_qicon("scan", accent="#10B981", size=size)


def _export_icon(size: int = 24) -> QIcon:
    return lucide_qicon("image-down", accent="#3B82F6", size=size)


def _reload_icon(size: int = 24) -> QIcon:
    return lucide_qicon("refresh-cw", accent="#FB923C", size=size)


def _ruler_icon(size: int = 24) -> QIcon:
    return lucide_qicon("ruler", accent="#F472B6", size=size)


def _check_icon(size: int = 24) -> QIcon:
    return lucide_qicon("check", accent="#22C55E", size=size)


def _undo_check_icon(size: int = 24) -> QIcon:
    return lucide_qicon("undo-2", accent="#94A3B8", size=size)


def _uncheck_all_icon(size: int = 24) -> QIcon:
    return lucide_qicon("list-x", accent="#DC2626", size=size)


def _rotate_records_icon(size: int = 24) -> QIcon:
    return lucide_qicon("rotate-cw-square", accent="#60A5FA", size=size)


def _flip_records_x_icon(size: int = 24) -> QIcon:
    return lucide_qicon(
        "triangles-centerline-dashed-horizontal", accent="#38BDF8", size=size
    )


def _flip_records_y_icon(size: int = 24) -> QIcon:
    return lucide_qicon(
        "triangles-centerline-dashed-vertical", accent="#A3E635", size=size
    )


def _flip_records_icon(size: int = 24) -> QIcon:
    return _flip_records_y_icon(size)


def _collapse_card_icon(collapsed: bool) -> QIcon:
    return lucide_qicon(
        "panel-left-open" if collapsed else "panel-left-close", size=18
    )


def _crosshair_half(size: Optional[float], fallback: float) -> float:
    if size is None:
        return fallback
    return min(max(size * 1.15, 0.15), fallback)


_MAG_FACTOR = 6.0
_MAG_FACTORS = (3.0, 4.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 25.0)
_ROT_EDIT_MAG_FACTOR = 20.0   # zoom level while editing rotation
_MAG_MIN_SCALE = 1.0

#: The shared card style of the two panels of the right side.
_CARD_QSS = """
QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 0px;
    margin-top: 18px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #0D9488;
    font-size: 11pt;
}
"""


def _magnifier_scale(board_size: float, vw: int, vh: int,
                     factor: float = _MAG_FACTOR) -> float:
    base = min(float(vw), float(vh)) / max(board_size, 1.0)
    return max(base * factor, _MAG_MIN_SCALE)


def _add_flash(
    path: QPainterPath,
    fl: FlashShape,
    mirror: bool = False,
    angle: float = 0.0,
    off_x: float = 0.0,
    off_y: float = 0.0,
    cx0: float = 0.0,
    cy0: float = 0.0,
    mirror_x: bool = False,
    transform: AffineTransform | None = None,
) -> None:
    """Append one flash to `path` with the display transform applied.

    All geometry (position, polygon vertices, aperture-macro primitives) is
    transformed by the same mirror -> rotate -> offset pipeline used for
    stroked lines, so every layer rotates together.

    The transform can be given ready made: a layer holds a few ten thousand
    flashes, and preparing the matrix once for the whole layer is much
    cheaper than a call with a trigonometry for every flash.
    """
    if transform is None:
        transform = AffineTransform(mirror, angle, off_x, off_y, cx0, cy0, mirror_x)
    # The transform is called directly instead of through a helper: a
    # layer holds a few ten thousand flashes, and a closure that is made
    # for every one of them costs more than the transform itself.
    apply = transform.apply
    apply_local = transform.apply_local

    if angle == 0.0 and not mirror and not mirror_x:
        rot = fl.rot
    else:
        rot = transform_rot(fl.rot, mirror, angle, mirror_x)

    if fl.kind == "circle":
        gx, gy = apply(fl.cx, fl.cy)
        r = fl.w / 2.0
        path.addEllipse(gx - r, -gy - r, 2 * r, 2 * r)
        return

    if fl.kind == "rect":
        gx, gy = apply(fl.cx, fl.cy)
        _add_rect_path(path, gx, gy, fl.w, fl.h, math.radians(rot))
        return

    if fl.kind == "oblong":
        gx, gy = apply(fl.cx, fl.cy)
        if abs(rot) < 0.5 or abs(rot - 360.0) < 0.5:
            r = min(fl.w, fl.h) / 2.0
            path.addRoundedRect(
                QRectF(gx - fl.w / 2, -gy - fl.h / 2, fl.w, fl.h), r, r
            )
        else:
            _add_capsule_path(path, gx, gy, fl.w, fl.h, math.radians(rot))
        return

    if fl.kind == "polygon" and fl.pts:
        if fl.pts_local:
            # The points are given relative to the place of the flash.
            gx, gy = apply(fl.cx, fl.cy)
            pts = [
                (gx + lx, -gy - ly)
                for lx, ly in (apply_local(px, py) for px, py in fl.pts)
            ]
        else:
            # The points are given in the coordinates of the file, like the
            # points of a region (G36) and of a polygon aperture.
            pts = [(x, -y) for x, y in (apply(px, py) for px, py in fl.pts)]
        hole_contours = fl.holes or ()
        if hole_contours:
            # The holes of a region cut out of the outer contour: every
            # area covered an even number of times stays empty.  Holes
            # only exist for file-frame regions.
            for contour in hole_contours:
                hole_pts = [(x, -y) for x, y in (apply(px, py)
                                                 for px, py in contour)]
                _add_polygon(path, hole_pts)
            path.setFillRule(Qt.FillRule.OddEvenFill)
        _add_polygon(path, pts)
        return

    if fl.kind == "macro" and fl.macro:
        gx, gy = apply(fl.cx, fl.cy)
        m = fl.macro
        # The primitives of a macro overlap on purpose: the regions where
        # they cross belong to the pad.  The winding rule fills the union,
        # the odd-even rule would carve every crossing into a hole.
        path.setFillRule(Qt.FillRule.WindingFill)
        for mx, my, r in m.circles:
            lx, ly = apply_local(mx, my)
            path.addEllipse(gx + lx - r, -gy - ly - r, 2 * r, 2 * r)
        for poly_pts in m.polygons:
            pts = [
                (gx + lx, -gy - ly)
                for lx, ly in (apply_local(px, py) for px, py in poly_pts)
            ]
            _add_polygon(path, pts)
        for x1, y1, x2, y2, width in m.segments:
            lx1, ly1 = apply_local(x1, y1)
            lx2, ly2 = apply_local(x2, y2)
            ang = math.atan2(ly2 - ly1, lx2 - lx1)
            n2 = width / 2.0
            dx, dy = -math.sin(ang) * n2, math.cos(ang) * n2
            quad = [
                (gx + lx1 + dx, -gy - ly1 - dy),
                (gx + lx1 - dx, -gy - ly1 + dy),
                (gx + lx2 - dx, -gy - ly2 + dy),
                (gx + lx2 + dx, -gy - ly2 - dy),
            ]
            _add_polygon(path, quad)
        # The primitives with the exposure turned off are holes in the
        # pad: they are given a reversed winding so the winding rule
        # cuts them out where they lie inside the artwork.
        for mx, my, r in m.hole_circles:
            if r <= 0:
                continue
            lx, ly = apply_local(mx, my)
            hole_pts = [
                (gx + lx + r * math.cos(2.0 * math.pi * i / _HOLE_SEGS),
                 -gy - ly + r * math.sin(2.0 * math.pi * i / _HOLE_SEGS))
                for i in range(_HOLE_SEGS)
            ]
            _add_polygon(path, hole_pts, hole=True)
        for poly_pts in m.hole_polygons:
            pts = [
                (gx + lx, -gy - ly)
                for lx, ly in (apply_local(px, py) for px, py in poly_pts)
            ]
            _add_polygon(path, pts, hole=True)
        return


def _append_arc_path(
    path: QPainterPath,
    ar: ArcShape,
    mirror: bool,
    angle: float,
    off_x: float,
    off_y: float,
    cx0: float,
    cy0: float,
    mirror_x: bool = False,
) -> None:
    """Append an arc stroke to `path` with the display transform + y-flip."""
    sx, sy = apply_transform(ar.x1, ar.y1, mirror, angle, off_x, off_y, cx0, cy0, mirror_x)
    ex, ey = apply_transform(ar.x2, ar.y2, mirror, angle, off_x, off_y, cx0, cy0, mirror_x)
    cx_, cy_ = apply_transform(ar.cx, ar.cy, mirror, angle, off_x, off_y, cx0, cy0, mirror_x)
    r = math.hypot(sx - cx_, sy - cy_)
    if r <= 1e-9:
        path.moveTo(sx, -sy)
        path.lineTo(ex, -ey)
        return
    rect = QRectF(cx_ - r, -cy_ - r, 2 * r, 2 * r)
    if ar.x1 == ar.x2 and ar.y1 == ar.y2:
        path.addEllipse(rect)
        return
    path.moveTo(sx, -sy)
    a_start = math.degrees(math.atan2(sy - cy_, sx - cx_))
    a_end = math.degrees(math.atan2(ey - cy_, ex - cx_))
    if ar.clockwise:
        sweep = -((a_start - a_end) % 360.0)
    else:
        sweep = (a_end - a_start) % 360.0
    path.arcTo(rect, a_start, sweep)


def _normalize_winding(pts: List[QPointF]) -> List[QPointF]:
    """Reverse a polygon point list so its winding is positive (CCW).

    All filled subpaths must share the same winding direction, otherwise
    Qt.WindingFill cancels overlapping subpaths (e.g. gerbonara expands a
    RoundRect macro into positive-winding circles and negative-winding
    rects, producing hollow pads). Circles/rounded-rects already wind
    positively, so polygons are normalized to match.
    """
    n = len(pts)
    if n < 3:
        return pts
    area = 0.0
    for i in range(n):
        x1, y1 = pts[i].x(), pts[i].y()
        x2, y2 = pts[(i + 1) % n].x(), pts[(i + 1) % n].y()
        area += x1 * y2 - x2 * y1
    if area < 0.0:
        return list(reversed(pts))
    return pts


def _add_polygon(path: QPainterPath, pts: List[Tuple[float, float]],
                 hole: bool = False) -> None:
    """Add a closed polygon with the winding of the subpath made positive.

    The winding is decided on the plain coordinates, so no call into Qt is
    needed to read the points back.

    A hole gets the winding reversed: the flash path is filled with the
    winding rule, so a hole carves itself out of the artwork that surrounds
    it instead of changing the sense of the fill where it overlaps.
    """
    if hole:
        # Same sign convention as the Gerber spec: reversed winding.
        pts = pts[::-1]
    n = len(pts)
    if n >= 3:
        area = 0.0
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        if (area < 0.0) != hole:
            pts = pts[::-1]
    path.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _add_rect_path(path: QPainterPath, gx, gy, w, h, rot):
    hw, hh = w / 2.0, h / 2.0
    c, s = math.cos(rot), math.sin(rot)
    pts = []
    for cx0, cy0 in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
        rx = cx0 * c - cy0 * s
        ry = cx0 * s + cy0 * c
        pts.append((gx + rx, -gy - ry))
    _add_polygon(path, pts)


def _add_capsule_path(path: QPainterPath, cx, cy, w, h, rot):
    r = max(0.0, min(w, h) / 2.0)
    a = max(0.0, w / 2.0 - r)
    pts = []
    n_line = 10
    n_arc = 20
    for i in range(n_line + 1):
        t = i / n_line
        pts.append((-a + 2 * a * t, h / 2.0))
    # The arc is walked with a constant angle, so the trigonometry is done
    # once for the whole arc instead of once for every point.
    turn = math.pi / n_arc
    cos_turn = math.cos(turn)
    sin_turn = math.sin(turn)
    px, py = a + r * math.cos(-math.pi / 2.0), r * math.sin(-math.pi / 2.0)
    for _i in range(n_arc + 1):
        pts.append((px, py))
        px, py = (px * cos_turn - py * sin_turn,
                  px * sin_turn + py * cos_turn)
    for i in range(n_line + 1):
        t = i / n_line
        pts.append((a - 2 * a * t, -h / 2.0))
    turn = math.pi / n_arc
    cos_turn = math.cos(turn)
    sin_turn = math.sin(turn)
    px, py = -a + r * math.cos(math.pi / 2.0), r * math.sin(math.pi / 2.0)
    for _i in range(n_arc + 1):
        pts.append((px, py))
        px, py = (px * cos_turn - py * sin_turn,
                  px * sin_turn + py * cos_turn)
    c, s = math.cos(rot), math.sin(rot)
    out = []
    for gx, gy in pts:
        out.append((cx + gx * c - gy * s, -cy - gx * s - gy * c))
    _add_polygon(path, out)



class PickPlaceMarker(QGraphicsItem):
    def __init__(self, rotation: float, designator: str, info: str,
                 half: float, parent=None) -> None:
        super().__init__(parent)
        self._rotation = rotation
        self.designator = designator
        self._half = half
        self._highlight = False
        self._rad = math.radians(rotation)
        self.setToolTip(f"{designator}\n{info}")
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        ex = self._half * 1.8
        return QRectF(-ex, -ex, 2 * ex, 2 * ex)

    def set_highlight(self, highlight: bool) -> None:
        self._highlight = highlight
        self.update()

    def paint(self, painter, option, widget=None) -> None:
        color = HIGHLIGHT_COLOR if self._highlight else CROSS_COLOR
        if self._highlight:
            hal = self._half * 1.8
            painter.setBrush(Qt.NoBrush)
            frame_pen = QPen(HIGHLIGHT_COLOR, 1.5)
            frame_pen.setCosmetic(True)
            painter.setPen(frame_pen)
            painter.drawRect(QRectF(-hal, -hal, 2 * hal, 2 * hal))
        pen = QPen(color, 3.0 if self._highlight else 2.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        h = self._half
        painter.drawLine(-h, 0.0, h, 0.0)
        painter.drawLine(0.0, -h, 0.0, h)

        # direction: 0°-left, 90°-up, 180°-right, 270°-down
        dx, dy = -math.cos(self._rad), -math.sin(self._rad)
        px, py = -dy, dx  # perpendicular
        tip_x, tip_y = 1.4 * h * dx, 1.4 * h * dy
        base_x, base_y = h * dx, h * dy
        ax = base_x + 0.25 * h * px
        ay = base_y + 0.25 * h * py
        ax2 = base_x - 0.25 * h * px
        ay2 = base_y - 0.25 * h * py

        arrow = QPolygonF([
            QPointF(tip_x, tip_y),
            QPointF(ax, ay),
            QPointF(ax2, ay2),
        ])
        painter.setBrush(color)
        painter.drawPolygon(arrow)
        painter.setBrush(Qt.NoBrush)


class MarkerOverlayItem(QGraphicsItem):
    """Single batch item painting all pickplace markers as vector paths.

    Uses one QGraphicsItem so the scene culls/isolation is cheap, but markers
    are drawn with individual painter transforms (translate + rotate) and a
    cosmetic pen, so they stay razor-sharp at any zoom (no bitmap scaling).
    Each marker carries its own half-size so the crosshair scales with the
    pad underneath.
    """

    def __init__(self, markers: List[Tuple[float, float, float, float]],
                 show_unselected: bool = True, arrow_floor: float = 0.0,
                 arrow_min_px: float = _MIN_ARROW_PX,
                 cross_color: Optional[QColor] = None,
                 highlight_color: Optional[QColor] = None,
                 checked_color: Optional[QColor] = None,
                 checked_indices=None,
                 flagged_indices=None,
                 flag_color: Optional[QColor] = None,
                 show_frame: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._markers = markers  # (x, -y, rot_deg, half)
        self._show_unselected = show_unselected
        self._selected_indices: set = set()
        self._checked_indices: set = set(checked_indices or ())
        self._flagged_indices: set = set(flagged_indices or ())
        self._arrow_floor = arrow_floor
        self._arrow_min_px = arrow_min_px
        self._cross_color = cross_color if cross_color is not None else CROSS_COLOR
        self._highlight_color = highlight_color if highlight_color is not None else HIGHLIGHT_COLOR
        self._checked_color = checked_color if checked_color is not None else CHECKED_COLOR
        self._flag_color = flag_color if flag_color is not None else QColor("#F59E0B")
        self._show_frame = show_frame
        # Expose option.exposedRect so paint() can skip off-screen markers
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption)
        # The marks lie over the artwork, so that a pad never hides them.
        self.setZValue(Z_PICKPLACE)
        self._rect = self._compute_rect()
        self._build_geom()

    def _compute_rect(self) -> QRectF:
        if not self._markers:
            return QRectF()
        pad = max(m[3] for m in self._markers) * 1.8 + self._arrow_floor
        xs = [m[0] for m in self._markers]
        ys = [m[1] for m in self._markers]
        return QRectF(min(xs) - pad, min(ys) - pad,
                      max(xs) - min(xs) + 2 * pad,
                      max(ys) - min(ys) + 2 * pad)

    def _build_geom(self) -> None:
        self._cross: Dict[float, QPainterPath] = {}
        for m in self._markers:
            h = m[3]
            if h in self._cross:
                continue
            cross = QPainterPath()
            cross.moveTo(-h, 0.0)
            cross.lineTo(h, 0.0)
            cross.moveTo(0.0, -h)
            cross.lineTo(0.0, h)
            self._cross[h] = cross

    def set_selected(self, index: int) -> None:
        indices = {index} if index >= 0 else set()
        self.set_selected_indices(indices)

    def set_selected_indices(self, indices) -> None:
        selected = set(indices)
        if selected != self._selected_indices:
            self._selected_indices = selected
            self.update()

    def set_checked_indices(self, indices) -> None:
        checked = set(indices)
        if checked != self._checked_indices:
            self._checked_indices = checked
            self.update()

    def set_flagged_indices(self, indices) -> None:
        flagged = set(indices)
        if flagged != self._flagged_indices:
            self._flagged_indices = flagged
            self.update()

    def set_markers(self, markers: List[Tuple[float, float, float, float]]) -> None:
        self._markers = markers
        self._rect = self._compute_rect()
        self._build_geom()
        self.update()

    def boundingRect(self) -> QRectF:
        return self._rect

    @staticmethod
    def _outside_exposed(mx: float, my: float, radius: float,
                         exposed) -> bool:
        """True when a marker (plus its arrow/frame extent) cannot intersect
        the exposed viewport rect — lets paint() skip it entirely."""
        if exposed is None:
            return False
        return (mx + radius < exposed.left()
                or mx - radius > exposed.right()
                or my + radius < exposed.top()
                or my - radius > exposed.bottom())

    def paint(self, painter: QPainter, option=None, widget=None) -> None:
        if not self._markers:
            return
        pen = QPen(QColor(Qt.black), 2.5)
        pen.setCosmetic(True)
        selected_indices = self._selected_indices
        exposed = getattr(option, "exposedRect", None)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        scale = abs(painter.worldTransform().m11())
        if scale <= 0.0:
            scale = 1.0
        min_len = self._arrow_min_px / scale
        min_wing = self._arrow_min_px * _MIN_ARROW_WING_RATIO / scale
        for i, (mx, my, rot, half) in enumerate(self._markers):
            is_selected = i in selected_indices
            if not self._show_unselected and not is_selected:
                continue
            if i in self._checked_indices:
                color = self._checked_color
            else:
                color = self._highlight_color if is_selected else self._cross_color
            alen = max(0.4 * half, min_len)
            tip = half + alen
            wing = min(max(0.25 * half, min_wing), alen)
            # Cull markers whose whole glyph lies outside the exposed rect
            ext = half * 1.85 if self._show_frame else 0.0
            radius = (tip if tip > ext else ext) + 1.5
            if self._outside_exposed(mx, my, radius, exposed):
                continue
            arrow = QPolygonF([
                QPointF(-tip, 0.0),
                QPointF(-half, -wing),
                QPointF(-half, wing),
            ])
            painter.save()
            painter.translate(mx, my)
            if i in self._flagged_indices:
                hal = half * 1.15
                painter.setBrush(Qt.NoBrush)
                flag_pen = QPen(self._flag_color, 1.6)
                flag_pen.setCosmetic(True)
                flag_pen.setStyle(Qt.DashLine)
                painter.setPen(flag_pen)
                painter.drawRect(QRectF(-hal, -hal, 2 * hal, 2 * hal))
            if is_selected and self._show_frame:
                hal = half * 1.8
                painter.setBrush(Qt.NoBrush)
                frame_pen = QPen(self._highlight_color, 1.5)
                frame_pen.setCosmetic(True)
                painter.setPen(frame_pen)
                painter.drawRect(QRectF(-hal, -hal, 2 * hal, 2 * hal))
            painter.rotate(-rot)
            pen.setColor(color)
            pen.setWidthF(3.0 if is_selected else 2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self._cross[half])
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(arrow)
            painter.setBrush(Qt.NoBrush)
            painter.restore()
        painter.restore()


class MeasurementItem(QGraphicsItem):
    """Dimension annotation: line + end ticks + a mm distance label.

    The end ticks scale with the view so they stay a fixed number of pixels,
    and the label is drawn in device pixels at the midpoint so its text stays
    readable at any zoom.
    """

    _TICK_PX = 6.0
    _LABEL_PX = 13
    _GAP_PX = 4.0
    _HALO_PADDING = 3.0

    def __init__(self, p1: QPointF, p2: QPointF, dist_mm: float,
                 color: QColor, parent=None) -> None:
        super().__init__(parent)
        self._p1 = QPointF(p1)
        self._p2 = QPointF(p2)
        self._dist = dist_mm
        self._color = QColor(color)
        self._rect = self._compute_rect()
        self.setZValue(Z_MEASURE)
        self.setToolTip(tr("Distance: {d:.3f} mm", d=dist_mm))

    def _compute_rect(self) -> QRectF:
        rect = QRectF(self._p1, self._p2).normalized()
        span = max(rect.width(), rect.height())
        # The label is drawn in device pixels, so at low zoom its extent in
        # scene units is huge. Pad generously so boundingRect always covers it.
        pad = max(span * 0.5, 3000.0)
        return rect.adjusted(-pad, -pad, pad, pad)

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option=None, widget=None) -> None:
        scale = abs(painter.worldTransform().m11())
        if scale <= 0.0:
            scale = 1.0
        tick = self._TICK_PX / scale

        pen = QPen(self._color, 2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(self._p1, self._p2)

        dx = self._p2.x() - self._p1.x()
        dy = self._p2.y() - self._p1.y()
        length = math.hypot(dx, dy)
        if length > 1e-9:
            px, py = -dy / length, dx / length
            for p in (self._p1, self._p2):
                painter.drawLine(
                    p.x() - px * tick, p.y() - py * tick,
                    p.x() + px * tick, p.y() + py * tick,
                )
        else:
            px, py = 1.0, 0.0
            painter.drawLine(self._p1.x() - tick, self._p1.y(),
                             self._p1.x() + tick, self._p1.y())

        mid = QPointF((self._p1.x() + self._p2.x()) / 2.0,
                      (self._p1.y() + self._p2.y()) / 2.0)
        if length <= 1e-9:
            ox, oy = 0.0, -1.0
        elif abs(dy) > abs(dx):
            ox, oy = 1.0, 0.0
        else:
            ox, oy = 0.0, -1.0
        gap = self._GAP_PX / scale
        label_scene = mid + QPointF(ox * gap, oy * gap)

        screen = painter.worldTransform().map(label_scene)
        text = tr("{d:.3f} mm", d=self._dist)
        font = QFont()
        font.setPixelSize(self._LABEL_PX)
        painter.save()
        painter.resetTransform()
        painter.translate(screen.x(), screen.y())
        painter.setFont(font)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        fm = QFontMetricsF(font)
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        halo_p = self._HALO_PADDING
        rect = QRectF(-tw / 2.0 - halo_p, -th / 2.0 - halo_p,
                      tw + 2 * halo_p, th + 2 * halo_p)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(11, 18, 32, 200))
        painter.drawRoundedRect(rect, 3.0, 3.0)
        painter.setPen(QPen(self._color, 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.restore()


def _build_fill_path(
    flashes,
    mirror: bool,
    angle: float,
    off_x: float,
    off_y: float,
    center_x: float,
    center_y: float,
    mirror_x: bool = False,
) -> QPainterPath:
    """Build a single fill path for a paste/silk layer.

    Positive flashes are unioned into one solid region (WindingFill), and
    negative flashes are punched out of it. WindingFill keeps overlapping
    pads solid instead of creating holes/cut-lines (OddEven default).
    """
    dark = QPainterPath()
    dark.setFillRule(Qt.WindingFill)
    clear = QPainterPath()
    clear.setFillRule(Qt.WindingFill)
    for fl in flashes:
        target = clear if fl.negative else dark
        _add_flash(target, fl, mirror, angle, off_x, off_y, center_x, center_y, mirror_x)
    final = dark
    if not clear.isEmpty():
        final = QPainterPath(dark.subtracted(clear))
        final.setFillRule(Qt.WindingFill)
    return final


class GerberView(QGraphicsView):
    cursor_moved = Signal(float, float)
    cursor_left = Signal()
    zoom_end = Signal()
    grid_cell_clicked = Signal(float, float)
    measure_clicked = Signal(float, float)
    measure_cancel = Signal()
    crosshair_right_clicked = Signal(float, float)
    origin_picked = Signal(float, float)
    align_pad_picked = Signal(float, float)
    align_pad_cancel = Signal()
    trace_pad_picked = Signal(float, float, QPoint)
    trace_pad_cancel = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(BACKGROUND)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        # Large-gerber smoothness: cheaper rasterization paths
        self.setOptimizationFlags(
            QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing
            | QGraphicsView.OptimizationFlag.DontSavePainterState
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)

        self._panning = False
        self._middle_panning = False
        self._middle_last = QPoint(0, 0)
        self._auto_pan_direction = QPoint(0, 0)
        self._auto_pan_timer: Optional[QTimer] = None
        self._grid_active = False
        self._measure_mode = False
        self._origin_mode = False
        self._align_pad_mode = False
        self._trace_mode = False

        # The crosshair that covers the whole view is always on: it is
        # how the pointer tells where it stands.
        self._full_cross_enabled = True
        self._full_cross_pos: Optional[QPointF] = None
        self.viewport().setCursor(Qt.CrossCursor)

        self._fast_render = False
        self._fast_timer: Optional[QTimer] = None

        self._zoom_pixmap: Optional[QPixmap] = None
        self._zoom_ratio: float = 1.0
        self._zoom_anchor: QPoint = QPoint(0, 0)
        self._zoom_active = False
        self._use_opengl = False
        self._default_viewport = None
        self._zoom_controller = create_zoom_controller()

        # Pan gesture: blit a frozen snapshot instead of scrolling the scene
        self._pan_pixmap: Optional[QPixmap] = None
        self._pan_offset = QPoint(0, 0)

    def set_use_opengl(self, enabled: bool) -> None:
        """Draw the view with OpenGL, or with the usual surface.

        The layer is drawn into a picture and put on the canvas, so the
        picture is the same either way.  OpenGL only changes the way the
        picture is put on the screen, which is quicker on a big board.
        """
        enabled = bool(enabled)
        if enabled == self._use_opengl:
            return
        self._use_opengl = enabled
        if enabled:
            from PySide6.QtOpenGLWidgets import QOpenGLWidget
            self.setViewport(QOpenGLWidget())
            self.setViewportUpdateMode(
                QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        else:
            # The surface that was used before is gone with the switch, a
            # plain one takes its place.
            self.setViewport(QWidget())
            self.setViewportUpdateMode(
                QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.viewport().update()


    def _set_fast_render(self) -> None:
        if self._fast_render:
            return
        self._fast_render = True
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setRenderHint(QPainter.SmoothPixmapTransform, False)

    def _restore_smooth_render(self) -> None:
        if not self._fast_render:
            return
        self._fast_render = False
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setRenderHint(QPainter.Antialiasing, True)
        if self._zoom_pixmap is not None and self._zoom_ratio != 1.0:
            self._apply_zoom_anchor(self._zoom_ratio, self._zoom_anchor)
        self._zoom_pixmap = None
        self._zoom_ratio = 1.0
        self._zoom_active = False
        self.zoom_end.emit()
        self.viewport().update()

    def _apply_zoom_anchor(self, factor: float, anchor: QPoint) -> None:
        """Change the zoom and keep the point under the anchor where it is.

        ``QGraphicsView.scale()`` always scales around the centre of the
        viewport, so the anchor has to be restored afterwards.  The view is
        moved with ``centerOn`` because the scroll bars of a graphics view
        count device pixels, not scene units.
        """
        before = self.mapToScene(anchor)
        self.scale(factor, factor)
        try:
            scale = abs(self.transform().m11())
        except Exception:
            scale = 1.0
        if scale <= 0:
            return
        view = self.viewport().rect()
        centre_x = before.x() + (view.width() / 2.0 - anchor.x()) / scale
        centre_y = before.y() + (view.height() / 2.0 - anchor.y()) / scale
        self.centerOn(centre_x, centre_y)
        self._clamp_zoom()

    def _clamp_zoom(self) -> None:
        """Limit the zoom to the range the reference implementation uses."""
        try:
            scale = abs(self.transform().m11())
        except Exception:
            return
        if scale <= 0:
            return
        factor = zoom_factor_from_scale(scale)
        limited = clamp_zoom_factor(factor)
        if abs(limited - factor) < 1e-9:
            return
        target = scale_from_zoom_factor(limited)
        self.scale(target / scale, target / scale)

    def _schedule_smooth_restore(self) -> None:
        if self._fast_timer is not None:
            self._fast_timer.stop()
        self._fast_timer = QTimer(self)
        self._fast_timer.setSingleShot(True)
        self._fast_timer.setInterval(150)
        self._fast_timer.timeout.connect(self._restore_smooth_render)
        self._fast_timer.start()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._grid_active:
            event.ignore()
            return
        rotation = event.angleDelta().y()
        if rotation == 0:
            event.ignore()
            return
        self._set_fast_render()
        factor = self._zoom_controller.scale_for_rotation(rotation)
        if self._zoom_pixmap is None:
            self._zoom_pixmap = self.viewport().grab()
            self._zoom_ratio = 1.0
        self._zoom_ratio = min(500.0, max(0.002, self._zoom_ratio * factor))
        self._zoom_anchor = event.position().toPoint()
        self._zoom_active = True
        self.viewport().update()
        self._schedule_smooth_restore()

    def fit(self) -> None:
        rect = self.scene().itemsBoundingRect()
        if not rect.isNull():
            self.fitInView(rect, Qt.KeepAspectRatio)

    def fit_to_rect(self, rect: QRectF) -> None:
        if rect is not None and not rect.isNull() and rect.isValid():
            self.fitInView(rect, Qt.KeepAspectRatio)

    def set_measure_mode(self, active: bool) -> None:
        """Enter/exit measure mode: clicks place measurement points."""
        self._measure_mode = bool(active)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setFocusPolicy(Qt.StrongFocus if active else Qt.WheelFocus)
        self.viewport().update()

    def set_origin_mode(self, active: bool) -> None:
        """Enter/exit origin mode: a click places the new origin."""
        self._origin_mode = bool(active)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setFocusPolicy(Qt.StrongFocus if active else Qt.WheelFocus)
        self.viewport().update()

    def set_align_pad_mode(self, active: bool) -> None:
        """Enter/exit align-to-pad mode: a click picks a pad centre."""
        self._align_pad_mode = bool(active)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setFocusPolicy(Qt.StrongFocus if active else Qt.WheelFocus)
        self.viewport().update()

    def set_trace_mode(self, active: bool) -> None:
        """Enter/exit trace mode: a click traces the net of the pad."""
        self._trace_mode = bool(active)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setFocusPolicy(Qt.StrongFocus if active else Qt.WheelFocus)
        self.viewport().update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._grid_active:
            return
        if self._origin_mode:
            if event.button() == Qt.LeftButton:
                sp = self.mapToScene(event.position().toPoint())
                self.origin_picked.emit(sp.x(), sp.y())
                event.accept()
            return
        if self._measure_mode:
            if event.button() == Qt.LeftButton:
                sp = self.mapToScene(event.position().toPoint())
                self.measure_clicked.emit(sp.x(), sp.y())
                event.accept()
            elif event.button() == Qt.RightButton:
                self.measure_cancel.emit()
                event.accept()
            return
        if self._align_pad_mode:
            if event.button() == Qt.LeftButton:
                sp = self.mapToScene(event.position().toPoint())
                self.align_pad_picked.emit(sp.x(), sp.y())
                event.accept()
            elif event.button() == Qt.RightButton:
                self.align_pad_cancel.emit()
                event.accept()
            return
        if self._trace_mode:
            if event.button() == Qt.LeftButton:
                sp = self.mapToScene(event.position().toPoint())
                gp = event.globalPosition().toPoint()
                self.trace_pad_picked.emit(sp.x(), sp.y(), gp)
                event.accept()
            elif event.button() == Qt.RightButton:
                self.trace_pad_cancel.emit()
                event.accept()
            return
        if event.button() == Qt.MiddleButton:
            # The middle button pans the view, the content follows the
            # pointer while the button is held down.
            self._middle_panning = True
            self._middle_last = event.position().toPoint()
            event.accept()
            return
        if event.button() == Qt.RightButton:
            sp = self.mapToScene(event.position().toPoint())
            self.crosshair_right_clicked.emit(sp.x(), sp.y())
            event.accept()
            return
        if event.button() == Qt.LeftButton and not self._fast_render:
            # Freeze the viewport once; drag blits the snapshot (~1 ms/frame)
            self._panning = True
            self._pan_pixmap = self.viewport().grab()
            self._pan_offset = QPoint(0, 0)
            self._pan_press = event.position().toPoint()
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self._panning = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._middle_panning:
            position = event.position().toPoint()
            delta = position - self._middle_last
            self._middle_last = position
            if delta.x() or delta.y():
                # The artwork is blitted from a frozen snapshot while the
                # gesture runs, so a big layer does not have to be drawn
                # again for every mouse move.
                if self._pan_pixmap is None:
                    self._pan_pixmap = self.viewport().grab()
                self._pan_offset = self._pan_offset + delta
                self.viewport().update()
            self._update_auto_pan(event.position().toPoint())
            event.accept()
            return
        old_cross_pos = self._full_cross_pos
        self._full_cross_pos = event.position()
        if self._full_cross_enabled:
            self._update_crosshair_regions(old_cross_pos, self._full_cross_pos)
        sp = self.mapToScene(event.position().toPoint())
        self.cursor_moved.emit(sp.x(), sp.y())
        if self._panning and self._pan_pixmap is not None:
            self._pan_offset = event.position().toPoint() - self._pan_press
            self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _update_auto_pan(self, position: QPoint) -> None:
        """Scroll the view when the pointer is close to an edge."""
        rect = self.viewport().rect()
        if rect.isEmpty():
            return
        margin = int(min(rect.width(), rect.height()) * _AUTO_PAN_MARGIN)
        margin = max(margin, 2)
        direction = QPoint(0, 0)
        if position.x() < margin:
            direction.setX(-(margin - position.x()))
        elif position.x() > rect.right() - margin:
            direction.setX(position.x() - (rect.right() - margin))
        if position.y() < margin:
            direction.setY(-(margin - position.y()))
        elif position.y() > rect.bottom() - margin:
            direction.setY(position.y() - (rect.bottom() - margin))
        self._auto_pan_direction = direction
        if direction.x() or direction.y():
            if self._auto_pan_timer is None:
                self._auto_pan_timer = QTimer(self)
                self._auto_pan_timer.setInterval(_AUTO_PAN_INTERVAL_MS)
                self._auto_pan_timer.timeout.connect(self._auto_pan_tick)
            self._auto_pan_timer.start()
        elif self._auto_pan_timer is not None:
            self._auto_pan_timer.stop()

    def _auto_pan_tick(self) -> None:
        direction = self._auto_pan_direction
        if not (direction.x() or direction.y()):
            if self._auto_pan_timer is not None:
                self._auto_pan_timer.stop()
            return
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - direction.x())
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() - direction.y())

    def leaveEvent(self, event) -> None:
        self.cursor_left.emit()
        old_cross_pos = self._full_cross_pos
        self._full_cross_pos = None
        if self._full_cross_enabled:
            self._update_crosshair_regions(old_cross_pos, None)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._grid_active:
            if event.button() == Qt.LeftButton:
                sp = self.mapToScene(event.position().toPoint())
                self.grid_cell_clicked.emit(sp.x(), sp.y())
                event.accept()
            return
        if event.button() == Qt.MiddleButton:
            self._middle_panning = False
            if self._auto_pan_timer is not None:
                self._auto_pan_timer.stop()
            if self._pan_pixmap is not None:
                # Apply the whole gesture as a single scroll.
                off = self._pan_offset
                self.horizontalScrollBar().setValue(
                    self.horizontalScrollBar().value() - off.x())
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - off.y())
                self._pan_pixmap = None
                self._pan_offset = QPoint(0, 0)
                self.viewport().update()
            event.accept()
            return
        if self._measure_mode:
            event.accept()
            return
        if self._align_pad_mode:
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._pan_pixmap is not None:
            # Apply the whole gesture as a single scroll, then restore real render
            off = self._pan_offset
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - off.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - off.y())
            self._pan_pixmap = None
            self._pan_offset = QPoint(0, 0)
            self._panning = False
            self.viewport().update()
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self._panning = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if self._measure_mode and key == Qt.Key_Escape:
            self.measure_cancel.emit()
            event.accept()
            return
        if self._align_pad_mode and key == Qt.Key_Escape:
            self.align_pad_cancel.emit()
            event.accept()
            return
        if self._trace_mode and key == Qt.Key_Escape:
            self.trace_pad_cancel.emit()
            event.accept()
            return
        modifiers = event.modifiers()
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        if key == Qt.Key_F1:
            self._zoom_step(+1)
            event.accept()
            return
        if key == Qt.Key_F2:
            self._zoom_step(-1)
            event.accept()
            return
        if key == Qt.Key_F4:
            self._center_on_cursor()
            event.accept()
            return
        if key == Qt.Key_F5 and not ctrl:
            self.viewport().update()
            event.accept()
            return
        if key == Qt.Key_Home:
            self.zoom_to_fit()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # zoom helpers, following the reference implementation
    # ------------------------------------------------------------------
    def _current_zoom_factor(self) -> float:
        try:
            scale = abs(self.transform().m11())
        except Exception:
            scale = 1.0
        return zoom_factor_from_scale(scale)

    def _zoom_step(self, direction: int) -> None:
        """Zoom in or out with the keyboard, snapping to the preset levels."""
        factor = next_preset(self._current_zoom_factor(), direction)
        self.set_zoom_factor(factor)

    def set_zoom_factor(self, factor: float) -> None:
        """Set the zoom to a zoom factor, keeping the viewport centre."""
        try:
            scale = abs(self.transform().m11())
        except Exception:
            return
        if scale <= 0:
            return
        target = scale_from_zoom_factor(clamp_zoom_factor(factor))
        self.scale(target / scale, target / scale)

    def zoom_to_fit(self, margin: float = 1.04) -> None:
        """Fit the whole drawing into the viewport.

        The margin keeps a little air around the artwork, the same way the
        reference implementation reserves room for the status bar.
        """
        rect = self.scene().itemsBoundingRect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return
        view_rect = self.viewport().rect()
        if view_rect.width() <= 0 or view_rect.height() <= 0:
            return
        scale = min(
            view_rect.width() / rect.width(),
            view_rect.height() / rect.height(),
        ) / margin
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(rect.center())
        self._clamp_zoom()

    def _center_on_cursor(self) -> None:
        """Move the viewport so the cursor is in the middle."""
        position = self.mapFromGlobal(QCursor.pos())
        if not self.viewport().rect().contains(position):
            return
        self.centerOn(self.mapToScene(position))

    def _update_crosshair_regions(self, old_pos: Optional[QPointF], new_pos: Optional[QPointF]) -> None:
        """Update only the dirty crosshair lines instead of the entire viewport."""
        if not self._full_cross_enabled:
            return
        # In OpenGL mode, partial viewport update is not supported (FullViewportUpdate is active)
        if self._use_opengl:
            self.viewport().update()
            return
        rect = self.viewport().rect()
        margin = 3
        regions = QRegion()
        if old_pos is not None:
            ox = int(old_pos.x())
            oy = int(old_pos.y())
            regions = regions.united(QRect(rect.left(), oy - margin, rect.width(), margin * 2 + 1))
            regions = regions.united(QRect(ox - margin, rect.top(), margin * 2 + 1, rect.height()))
        if new_pos is not None:
            nx = int(new_pos.x())
            ny = int(new_pos.y())
            regions = regions.united(QRect(rect.left(), ny - margin, rect.width(), margin * 2 + 1))
            regions = regions.united(QRect(nx - margin, rect.top(), margin * 2 + 1, rect.height()))
        if not regions.isEmpty():
            self.viewport().update(regions)

    def set_full_crosshair_enabled(self, enabled: bool) -> None:
        self._full_cross_enabled = bool(enabled)
        if enabled:
            self.viewport().setCursor(Qt.CrossCursor)
        else:
            self.viewport().setCursor(Qt.ArrowCursor)
            self._full_cross_pos = None
        self.viewport().update()

    def _paint_full_cross(self) -> None:
        if not self._full_cross_enabled or self._full_cross_pos is None:
            return
        pt = self._full_cross_pos
        painter = QPainter(self.viewport())
        pen = QPen(CROSS_COLOR, 1.2)
        painter.setPen(pen)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.viewport().rect()
        painter.drawLine(QPointF(rect.left(), pt.y()), QPointF(rect.right(), pt.y()))
        painter.drawLine(QPointF(pt.x(), rect.top()), QPointF(pt.x(), rect.bottom()))
        painter.end()

    def paintEvent(self, event: object) -> None:
        if self._zoom_pixmap is not None and self._zoom_ratio != 1.0:
            pm = self._zoom_pixmap
            size = pm.deviceIndependentSize()
            painter = QPainter(self.viewport())
            painter.fillRect(self.viewport().rect(), self.backgroundBrush())
            a = self._zoom_anchor
            painter.translate(a.x(), a.y())
            painter.scale(self._zoom_ratio, self._zoom_ratio)
            painter.translate(-a.x(), -a.y())
            painter.drawPixmap(
                QRectF(0.0, 0.0, size.width(), size.height()), pm,
                QRectF(0.0, 0.0, size.width(), size.height()),
            )
            painter.end()
            self._paint_full_cross()
            event.accept()
            return
        if self._pan_pixmap is not None:
            painter = QPainter(self.viewport())
            painter.fillRect(self.viewport().rect(), self.backgroundBrush())
            painter.drawPixmap(self._pan_offset, self._pan_pixmap)
            painter.end()
            self._paint_full_cross()
            event.accept()
            return
        super().paintEvent(event)
        self._paint_full_cross()


class GerberLoadWorker(QThread):
    progress = Signal(str, int)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, layers: List[LayerInfo], parent=None) -> None:
        super().__init__(parent)
        self._layers = list(layers or [])
        #: How each file was read, so the user can be told when a reduced
        #: parser was used.
        self.load_info: Dict[str, object] = {}

    def run(self) -> None:
        try:
            data: List[RenderData] = []
            count = max(1, len(self._layers))
            for index, layer in enumerate(self._layers):
                self.progress.emit(
                    tr("Reading {name}...", name=layer.name),
                    int(100 * index / count))
                if layer.is_drill:
                    data.append(self._load_drill(layer.path))
                else:
                    data.append(self._load(layer.path, layer.key()))
            self.progress.emit(tr("Done."), 100)
            self.finished.emit(data)
        except Exception as e:
            self.failed.emit(str(e))

    def _load(self, path: str, key: str) -> RenderData:
        """Load one Gerber file and remember how it was read."""
        data, info = load_layer(path)
        self.load_info[key] = info
        return data

    def _load_drill(self, path: str) -> RenderData:
        data, info = load_drill(path)
        self.load_info[os.path.normcase(os.path.abspath(path))] = info
        return data


class MagnifierView(QGraphicsView):
    clicked = Signal(float, float)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            sp = self.mapToScene(event.position().toPoint())
            self.clicked.emit(sp.x(), sp.y())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _LayerPathCache:
    """The built artwork of a layer, kept for the transforms it was drawn.

    Turning, mirroring and the switch between the two sides each ask for
    a full walk over the artwork of a layer, and a user turns the page
    back and forth while reading.  The built paths of up to two transforms
    are kept per layer, so going back to a transform the user has already
    seen costs nothing.  Two copies of a big layer are a few ten mega
    bytes of paths, so the limit of two keeps the memory small.
    """

    #: How many transforms are kept per layer.
    MAX_KEYS = 2

    def __init__(self) -> None:
        self._entries: Dict[int, Dict[tuple, tuple]] = {}

    def get(self, layer_index: int, key: tuple) -> Optional[tuple]:
        return self._entries.get(layer_index, {}).get(key)

    def put(self, layer_index: int, key: tuple, value: tuple) -> None:
        entries = self._entries.get(layer_index)
        if entries is None:
            entries = {}
            self._entries[layer_index] = entries
        if key not in entries:
            # The oldest turn gives way first: a freeze of the RAM stops
            # the cache from growing while the reader of the page works.
            while len(entries) >= self.MAX_KEYS:
                entries.pop(next(iter(entries)))
        entries[key] = value

    def clear(self) -> None:
        self._entries.clear()


class GerberViewer(QWidget):

    settings_saved = Signal(dict)

    checked_changed = Signal(int)

    rotation_edited = Signal(int)

    records_edited = Signal(list)

    align_edited = Signal(list)

    status_message = Signal(str)

    def __init__(
        self,
        records: List[ReviewRecord],
        layers: Optional[List[LayerInfo]] = None,
        parent: Optional[QWidget] = None,
        display_settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Gerber View - Overlay PickPlace"))
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMinimumSize(1100, 700)
        self.resize(1300, 820)
        self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))

        self._records = records
        #: The layers of the picture, in the order they are drawn.
        self._layers: List[LayerInfo] = self._coerce_layers(layers)
        #: The geometry of every layer.
        self._layer_data: List[RenderData] = [RenderData() for _ in self._layers]
        #: The item of every layer in the scene.
        self._layer_items: List[object] = []
        #: The colour of every layer.
        self._layer_colors: List[QColor] = [
            self._default_layer_color(layer) for layer in self._layers]
        #: The state of every layer: normal, dimmed or hidden.
        self._layer_states: List[str] = [
            LAYER_STATE_NORMAL for _ in self._layers]
        #: The layer that is shown on top of the others.
        self._active_layer: int = 0
        #: The layers that do not lie on the board.
        self._outside_layers: List[int] = []
        self._drill_align = None
        self._loaded = False
        self._pads: List[Tuple[float, float, float]] = []
        self._pad_grid_cache: Dict[bool, PadGrid] = {}
        self._layer_path_cache = _LayerPathCache()
        self._scene_key: Optional[tuple] = None
        # The index that finds the shape under the pointer, per layer.
        self._aperture_indices: Dict[int, ApertureIndex] = {}
        self._overlay: Optional[MarkerOverlayItem] = None
        self._goto_pos: Optional[Tuple[float, float]] = None
        self._goto_crosshair: Optional[QGraphicsPathItem] = None
        #: The mark of the origin of the coordinates of the file.
        self._origin_marker: Optional[QGraphicsPathItem] = None
        self._show_origin = True
        #: The origin of the coordinates, in the coordinates of the file.
        self._origin_x: float = 0.0
        self._origin_y: float = 0.0
        #: True while the operator is choosing a new origin by clicking.
        self._origin_mode: bool = False
        self._grid_active = False
        self._grid_available = False
        self._grid_opacity = 255
        self._grid_width = 2.0
        self._grid_item: Optional[QGraphicsPathItem] = None
        self._grid_rect: Optional[QRectF] = None
        self._measure_mode = False
        self._measure_start: Optional[Tuple[float, float]] = None
        self._align_pad_mode = False
        self._align_snap_item: Optional[QGraphicsEllipseItem] = None
        # The traced net: one overlay that lights the connected copper.
        self._trace_mode = False
        self._trace_indices: Dict[int, Any] = {}
        self._active_trace: Optional[Tuple] = None
        self._trace_first: Optional[Tuple[RenderData, Any, str, Tuple]] = None
        self._trace_candidates: Optional[List[Tuple[int, RenderData, int]]] = None
        self._trace_order = 0
        self._trace_last_pick: Optional[Tuple[float, float]] = None
        self._trace_line_item: Optional[QGraphicsPathItem] = None
        self._trace_fill_item: Optional[QGraphicsPathItem] = None
        self._trace_plane_outline_item: Optional[QGraphicsPathItem] = None
        self._trace_popup: Optional[QLabel] = None
        self._trace_popup_timer: Optional[QTimer] = None
        self._measure_preview: Optional[QGraphicsPathItem] = None
        self._measure_snap_item: Optional[QGraphicsEllipseItem] = None
        self._snap_enabled = True
        self._snap_tol = 1.0
        self._measurements: List[Tuple[float, float, float, float]] = []
        self._measurement_items: List[MeasurementItem] = []
        self._mag_cell_rect: Optional[QRectF] = None
        self._board_center: Tuple[float, float] = (0.0, 0.0)
        self._cross_half = _CROSS_BOARD_RATIO
        self._arrow_min_px: float = _MIN_ARROW_PX
        self._crosshair_scale: float = 1.0
        self._selected_marker_index = -1
        self._selected_marker_indices: set = set()
        self._flagged_indices: set = set()
        self._rotation_preview: Optional[Tuple[int, float]] = None
        self._rotation_dialog = None
        self._rotation_ctx = None
        self._component_index: List[int] = []
        self._group_by_mpn = False
        self._group_rows: List[List[int]] = []
        self._scene_scale = 1.0
        self._mag_target: Optional[Tuple[float, float]] = None
        self._mag_factor: float = _MAG_FACTOR
        self._rot_mag_saved: Optional[float] = None
        self._rotation_lock_xy: Optional[Tuple[float, float]] = None
        self._hover_throttle_timer = QTimer(self)
        self._hover_throttle_timer.setSingleShot(True)
        self._hover_throttle_timer.setInterval(20)
        self._hover_throttle_timer.timeout.connect(self._process_throttled_hover)
        self._pending_hover_pos: Optional[Tuple[float, float]] = None
        self._show_frame = True
        self._colors: Dict[str, QColor] = {
            "cross": CROSS_COLOR,
            "highlight": HIGHLIGHT_COLOR,
        }
        self._color_buttons: Dict[str, QPushButton] = {}
        #: The colours the Overlay dialog drafts; they join the picture
        #: only when its Save is pressed.
        self._pp_color_draft: Dict[str, str] = {}
        #: What the palette of the colours works on: a layer of the
        #: picture, the crosshair or the highlight.
        self._color_target: Tuple[str, int] = ("layer", -1)
        #: The angle the layers of the picture turn with, in degrees.
        self._rotation: int = 0
        #: The side whose turn and mirrors the toolbar holds.
        self._transform_side: str = "top"
        #: The turn and the mirrors that every side keeps.
        self._layer_transforms: Dict[str, Dict[str, Any]] = {
            "top": {"rotation": 0, "flip": False, "mirror_x": False},
            "bottom": {"rotation": 0, "flip": False, "mirror_x": False},
        }

        # --- Hidden state widgets --------------------------------------
        # The values the dialogs and the saved session edit.  They are
        # not on the screen: the toolbar and the dialogs hold the look,
        # and these carry the state that the picture is drawn from.
        self._chk_flip = QCheckBox()
        self._chk_flip.toggled.connect(self._on_flip_state_changed)
        self._chk_mirror_x = QCheckBox()
        self._chk_mirror_x.toggled.connect(self._on_mirror_x_state_changed)
        self._chk_pickplace = QCheckBox()
        self._chk_pickplace.setChecked(True)
        self._chk_crosshair = QCheckBox()
        self._chk_crosshair.setChecked(True)
        self._chk_crosshair.toggled.connect(self._on_crosshair_toggled)
        self._spin_cross_scale = QDoubleSpinBox()
        self._spin_cross_scale.setRange(0.5, 5.0)
        self._spin_cross_scale.setSingleStep(0.1)
        self._spin_cross_scale.setDecimals(1)
        self._spin_cross_scale.setValue(1.0)
        self._spin_cross_scale.valueChanged.connect(
            self._on_crosshair_scale_changed)
        self._chk_origin = QCheckBox()
        self._chk_origin.setChecked(True)
        self._chk_origin.toggled.connect(self._on_origin_toggled)
        self._chk_frame = QCheckBox()
        self._chk_frame.setChecked(True)
        self._chk_frame.toggled.connect(self._on_frame_toggled)
        self._spin_arrow_px = QSpinBox()
        self._spin_arrow_px.setRange(5, 100)
        self._spin_arrow_px.setSingleStep(5)
        self._spin_arrow_px.setValue(int(_MIN_ARROW_PX))
        self._spin_arrow_px.valueChanged.connect(self._on_arrow_size_changed)
        self._chk_snap = QCheckBox()
        self._chk_snap.setChecked(True)
        self._chk_snap.toggled.connect(self._on_snap_toggled)
        self._spin_snap_tol = QDoubleSpinBox()
        self._spin_snap_tol.setRange(0.1, 5.0)
        self._spin_snap_tol.setSingleStep(0.1)
        self._spin_snap_tol.setDecimals(1)
        self._spin_snap_tol.setValue(1.0)
        self._spin_snap_tol.valueChanged.connect(self._on_snap_tol_changed)
        self._chk_grid = QCheckBox()
        self._chk_grid.setEnabled(False)
        self._chk_grid.toggled.connect(self._on_grid_toggled)
        self._spin_grid_cols = QSpinBox()
        self._spin_grid_cols.setRange(1, 50)
        self._spin_grid_cols.setValue(3)
        self._spin_grid_cols.valueChanged.connect(self._on_grid_params_changed)
        self._spin_grid_rows = QSpinBox()
        self._spin_grid_rows.setRange(1, 50)
        self._spin_grid_rows.setValue(3)
        self._spin_grid_rows.valueChanged.connect(self._on_grid_params_changed)
        self._spin_grid_opacity = QSpinBox()
        self._spin_grid_opacity.setRange(20, 255)
        self._spin_grid_opacity.setValue(self._grid_opacity)
        self._spin_grid_opacity.setSingleStep(5)
        self._spin_grid_opacity.valueChanged.connect(
            self._on_grid_style_changed)
        self._spin_grid_width = QDoubleSpinBox()
        self._spin_grid_width.setRange(1.0, 4.0)
        self._spin_grid_width.setValue(self._grid_width)
        self._spin_grid_width.setSingleStep(0.5)
        self._spin_grid_width.setDecimals(1)
        self._spin_grid_width.valueChanged.connect(self._on_grid_style_changed)

        self._build_ui()
        self._apply_layer()
        self.apply_display_settings(display_settings or {})
        self._start_load()

    def set_use_opengl(self, enabled: bool) -> None:
        """Draw the picture with OpenGL, or with the usual surface."""
        self._view.set_use_opengl(bool(enabled))

    def use_opengl(self) -> bool:
        """True when the picture is drawn with OpenGL."""
        return bool(self._view._use_opengl)

    @staticmethod
    def _coerce_layers(layers) -> List[LayerInfo]:
        """The layers of the picture, whatever the caller gave.

        A list of layers is used as it is.  A folder is looked at, and a
        single file is taken for the one layer it is.
        """
        from services.gerber.layer_scan import layer_from_file, scan_folder

        if not layers:
            return []
        if isinstance(layers, str):
            if os.path.isdir(layers):
                return scan_folder(layers)
            layer = layer_from_file(layers)
            return [layer] if layer is not None else []
        out: List[LayerInfo] = []
        for entry in layers:
            if isinstance(entry, LayerInfo):
                out.append(entry)
            elif isinstance(entry, str):
                layer = layer_from_file(entry)
                if layer is not None:
                    out.append(layer)
        return out

    def display_settings(self) -> Dict[str, Any]:
        self._store_current_transform()
        settings = {
            "layer": self._combo_layer.currentIndex(),
            "rotation": self._rotation,
            "flip": self._chk_flip.isChecked(),
            "mirror_x": self._chk_mirror_x.isChecked(),
            "layer_transforms": {
                side: dict(self._layer_transforms.get(
                    side, {"rotation": 0, "flip": False, "mirror_x": False}))
                for side in ("top", "bottom")
            },
            "layers": self._layer_settings(),
            "active_layer": self._active_layer_key(),
            "pickplace": self._chk_pickplace.isChecked(),
            "crosshair": self._chk_crosshair.isChecked(),
            "show_origin": self._chk_origin.isChecked(),
            "origin_x": self._origin_x,
            "origin_y": self._origin_y,
            "frame": self._chk_frame.isChecked(),
            "mag_factor": self._mag_factor,
            "arrow_min_px": self._spin_arrow_px.value(),
            "crosshair_scale": self._spin_cross_scale.value(),
            "grid": self._chk_grid.isChecked(),
            "grid_cols": self._spin_grid_cols.value(),
            "grid_rows": self._spin_grid_rows.value(),
            "grid_opacity": self._grid_opacity,
            "grid_width": self._grid_width,
            "snap": self._chk_snap.isChecked(),
            "snap_tol": self._spin_snap_tol.value(),
        }
        for key in ("cross", "highlight"):
            settings[f"{key}_color"] = self._current_color(key).name(QColor.HexArgb)
        return settings

    def apply_display_settings(self, settings: Dict[str, Any]) -> None:
        if not isinstance(settings, dict) or not settings:
            return
        has_transform_settings = (
            isinstance(settings.get("layer_transforms"), dict)
            or "rotation" in settings
            or "flip" in settings
            or "mirror_x" in settings
        )
        fallback = self._normalise_transform(
            settings, {"rotation": 0, "flip": False, "mirror_x": False})
        if has_transform_settings:
            raw_transforms = settings.get("layer_transforms")
            if isinstance(raw_transforms, dict):
                self._layer_transforms = {
                    side: self._normalise_transform(
                        raw_transforms.get(side), fallback)
                    for side in ("top", "bottom")
                }
            else:
                self._layer_transforms = {
                    side: dict(fallback) for side in ("top", "bottom")
                }

        layer_changed = False
        if "layer" in settings:
            try:
                idx = int(settings.get("layer", 0))
            except (TypeError, ValueError):
                idx = -1
            if 0 <= idx < self._combo_layer.count():
                layer_changed = idx != self._combo_layer.currentIndex()
                self._combo_layer.blockSignals(True)
                self._combo_layer.setCurrentIndex(idx)
                self._combo_layer.blockSignals(False)
        if has_transform_settings or layer_changed:
            self._transform_side = self._current_transform_side()
            self._load_transform_for_side(self._transform_side)
        self._apply_layer_settings(settings.get("layers"))
        active = settings.get("active_layer")
        if active:
            for index, layer in enumerate(self._layers):
                if layer.key() == active:
                    self._active_layer = index
                    break
        self._chk_pickplace.setChecked(bool(settings.get("pickplace", True)))
        self._chk_crosshair.setChecked(bool(settings.get("crosshair", True)))
        self._chk_origin.setChecked(bool(settings.get("show_origin", True)))
        self._show_origin = self._chk_origin.isChecked()
        if "origin_x" in settings or "origin_y" in settings:
            self._origin_x = float(settings.get("origin_x", 0.0))
            self._origin_y = float(settings.get("origin_y", 0.0))
        self._chk_frame.setChecked(bool(settings.get("frame", True)))
        self._show_frame = self._chk_frame.isChecked()
        if "mag_factor" in settings:
            target = float(settings.get("mag_factor", _MAG_FACTOR))
            for i in range(self._combo_mag.count()):
                if self._combo_mag.itemData(i) == target:
                    self._combo_mag.setCurrentIndex(i)
                    break
        self._spin_arrow_px.setValue(int(settings.get("arrow_min_px", _MIN_ARROW_PX)))
        self._spin_cross_scale.setValue(float(settings.get("crosshair_scale", 1.0)))
        self._arrow_min_px = float(self._spin_arrow_px.value())
        self._crosshair_scale = float(self._spin_cross_scale.value())
        self._spin_grid_opacity.setValue(int(settings.get("grid_opacity", 255)))
        self._spin_grid_width.setValue(float(settings.get("grid_width", 2.0)))
        self._grid_opacity = self._spin_grid_opacity.value()
        self._grid_width = self._spin_grid_width.value()
        self._chk_snap.setChecked(bool(settings.get("snap", True)))
        self._spin_snap_tol.setValue(float(settings.get("snap_tol", 1.0)))
        self._snap_enabled = self._chk_snap.isChecked()
        self._snap_tol = float(self._spin_snap_tol.value())
        # The grid is turned up late: while nothing is drawn yet the
        # state only keeps the wish of the session, and the grid itself
        # is put on the board when the load has finished.
        if "grid" in settings or "grid_cols" in settings or "grid_rows" in settings:
            self._chk_grid.blockSignals(True)
            self._chk_grid.setChecked(bool(settings.get("grid", False)))
            self._chk_grid.blockSignals(False)
            self._spin_grid_cols.setValue(
                int(settings.get("grid_cols", self._spin_grid_cols.value())))
            self._spin_grid_rows.setValue(
                int(settings.get("grid_rows", self._spin_grid_rows.value())))
        for key in ("cross", "highlight"):
            hex_val = settings.get(f"{key}_color")
            if isinstance(hex_val, str):
                color = QColor(hex_val)
                if color.isValid():
                    self._colors[key] = color
        self._pp_color_draft.clear()
        self._sync_color_buttons()
        self._sync_transform_controls()
        if layer_changed:
            self._clear_trace_result()
            self._apply_layer()
        self._redraw()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # The toolbar of the page: the origin of the coordinates is
        # chosen here.
        self._toolbar = QToolBar()
        self._toolbar.setMovable(False)
        self._toolbar.setFloatable(False)
        self._toolbar.setIconSize(QSize(24, 24))
        self._toolbar.setStyleSheet("""
            QToolButton {
                padding: 2px;
                text-align: center;
                border: 1px solid transparent;
                border-radius: 6px;
                font-size: 8pt;
            }
            QToolButton:hover {
                background: rgba(148, 163, 184, 0.15);
            }
            QToolButton:pressed {
                background: rgba(148, 163, 184, 0.30);
            }
            QToolButton:checked {
                border: 1px solid #22C55E;
                background: rgba(34, 197, 94, 0.18);
                color: #22C55E;
            }
            QToolButton:disabled {
                color: gray;
            }
        """)
        self._toolbar_icon_sources: List[Tuple[QToolButton, Any]] = []

        def _stacked_button(label: str, tooltip: str,
                            icon_factory, checkable: bool = False) -> QToolButton:
            button = QToolButton()
            button.setText(label)
            button.setToolTip(tooltip)
            button.setIcon(icon_factory())
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setCheckable(checkable)
            button.setFixedSize(56, 52)
            self._toolbar_icon_sources.append((button, icon_factory))
            return button

        self._btn_set_origin = _stacked_button(
            tr("Set origin"),
            tr("Click the board to choose a new origin"),
            _target_icon,
            checkable=True
        )
        self._btn_set_origin.clicked.connect(self._on_set_origin_clicked)
        self._btn_set_origin.toggled.connect(self._on_set_origin_clicked)
        self._toolbar.addWidget(self._btn_set_origin)

        self._btn_measure = _stacked_button(
            tr("Measure"),
            tr("Measure distances on the board. Turning the button off "
               "clears all measurements. Right-click or Esc cancels the "
               "current measurement."),
            _ruler_icon, True)
        self._btn_measure.setEnabled(False)
        self._btn_measure.toggled.connect(self._on_measure_toggled)
        self._toolbar.addWidget(self._btn_measure)

        self._btn_align_pad = _stacked_button(
            tr("Align to Pad"),
            tr("Pick the true pad centre of the selected component, then "
               "every component on the same side is shifted by the same "
               "offset. Ctrl click bypasses snapping, Esc or right-click "
               "cancels."),
            _target_icon, True)
        self._btn_align_pad.setEnabled(False)
        self._btn_align_pad.toggled.connect(self._on_align_pad_toggled)
        self._toolbar.addWidget(self._btn_align_pad)

        self._btn_trace = _stacked_button(
            tr("Trace pad"),
            tr("Trace the copper net of a pad: click a pad and the copper "
               "of its net lights up. Click a second pad to see whether "
               "the two connect. Esc or right-click cancels."),
            _trace_icon, True)
        self._btn_trace.setEnabled(False)
        self._btn_trace.toggled.connect(self._on_trace_toggled)
        self._toolbar.addWidget(self._btn_trace)

        # The angle the picture turns with, chosen in a small menu.
        self._btn_rotate = _stacked_button(
            tr("Rotate"), tr("Rotate Gerber"), _rotate_icon)
        self._btn_rotate.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        rotate_menu = QMenu(self._btn_rotate)
        self._rotate_actions = []
        rotate_group = QActionGroup(rotate_menu)
        rotate_group.setExclusive(True)
        for angle in (0, 90, 180, 270):
            action = rotate_menu.addAction(f"{angle}°")
            action.setCheckable(True)
            action.setData(int(angle))
            rotate_group.addAction(action)
            action.triggered.connect(
                lambda _checked=False, a=int(angle): self._set_rotation(a))
            self._rotate_actions.append(action)
        self._btn_rotate.setMenu(rotate_menu)
        self._toolbar.addWidget(self._btn_rotate)

        self._btn_flip_x = _stacked_button(
            tr("Flip X"), tr("Flip Gerber (Mirror X)"), _flip_x_icon, True)
        self._btn_flip_x.toggled.connect(self._on_flip_x_toggled)
        self._toolbar.addWidget(self._btn_flip_x)

        self._btn_flip_y = _stacked_button(
            tr("Flip Y"), tr("Flip Gerber (Mirror Y)"), _flip_y_icon, True)
        self._btn_flip_y.toggled.connect(self._on_flip_y_toggled)
        self._toolbar.addWidget(self._btn_flip_y)

        # The layer of the picture: the top or the bottom side.
        layer_bar = QWidget()
        layer_row = QHBoxLayout(layer_bar)
        layer_row.setContentsMargins(6, 0, 6, 0)
        layer_row.setSpacing(4)
        layer_row.addWidget(QLabel(tr("Layer:")))
        self._combo_layer = QComboBox()
        self._combo_layer.addItem(tr("Top layer (GKO + GTP)"))
        self._combo_layer.addItem(tr("Bottom layer (GKO + GBP)"))
        self._combo_layer.currentIndexChanged.connect(self._on_layer_changed)
        layer_row.addWidget(self._combo_layer)
        self._toolbar.addWidget(layer_bar)

        self._toolbar.addSeparator()
        self._btn_pickplace = _stacked_button(
            tr("PickPlace"),
            tr("Edit the PickPlace overlay (markers, crosshair, colors)"),
            _pickplace_icon)
        self._btn_pickplace.clicked.connect(self._open_pickplace_dialog)
        self._toolbar.addWidget(self._btn_pickplace)

        self._btn_grid = _stacked_button(
            tr("Grid"), tr("Grid settings and information"), _grid_icon)
        self._btn_grid.clicked.connect(self._open_grid_dialog)
        self._toolbar.addWidget(self._btn_grid)

        self._toolbar.addSeparator()
        self._btn_check = _stacked_button(
            tr("Checked"),
            tr("Mark the selected component as checked"),
            _check_icon)
        self._btn_check.clicked.connect(lambda: self._on_check_current(True))
        self._toolbar.addWidget(self._btn_check)

        self._btn_undo_check = _stacked_button(
            tr("Undo check"),
            tr("Uncheck the selected component"),
            _undo_check_icon)
        self._btn_undo_check.clicked.connect(
            lambda: self._on_check_current(False))
        self._toolbar.addWidget(self._btn_undo_check)

        self._btn_uncheck_all = _stacked_button(
            tr("Uncheck all"),
            tr("Clear the checks of all components on this layer"),
            _uncheck_all_icon)
        self._btn_uncheck_all.clicked.connect(self._on_uncheck_all)
        self._toolbar.addWidget(self._btn_uncheck_all)

        self._btn_rotate_records = _stacked_button(
            tr("Rotate comps"),
            tr("Rotate all components with their coordinates "
               "by 0, 90, 180 or 270 degrees around the origin (0, 0)"),
            _rotate_records_icon)
        self._btn_rotate_records.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        rotate_records_menu = QMenu(self._btn_rotate_records)
        for angle in (0, 90, 180, 270):
            action = rotate_records_menu.addAction(
                tr("Component {n}\u00b0", n=angle))
            action.setData(int(angle))
            action.triggered.connect(
                lambda _checked=False, a=int(angle): self._on_rotate_records(a))
        self._btn_rotate_records.setMenu(rotate_records_menu)
        self._toolbar.addWidget(self._btn_rotate_records)

        self._btn_flip_records_x = _stacked_button(
            tr("Flip X comps"),
            tr("Flip all components across the X axis"),
            _flip_records_x_icon)
        self._btn_flip_records_x.clicked.connect(lambda: self._on_flip_records("X"))
        self._toolbar.addWidget(self._btn_flip_records_x)

        self._btn_flip_records_y = _stacked_button(
            tr("Flip Y comps"),
            tr("Flip all components across the Y axis"),
            _flip_records_y_icon)
        self._btn_flip_records_y.clicked.connect(lambda: self._on_flip_records("Y"))
        self._toolbar.addWidget(self._btn_flip_records_y)

        # Backward compatibility alias
        self._btn_flip_records = self._btn_flip_records_x

        self._btn_check_controls = (self._btn_check, self._btn_undo_check,
                                    self._btn_uncheck_all,
                                    self._btn_rotate_records,
                                    self._btn_flip_records_x,
                                    self._btn_flip_records_y)
        for btn in self._btn_check_controls:
            btn.setEnabled(False)

        self._toolbar.addSeparator()
        self._btn_fit = _stacked_button(
            tr("Fit View"), tr("Fit the board into the view"), _fit_icon)
        self._btn_fit.clicked.connect(self._fit_scene)
        self._toolbar.addWidget(self._btn_fit)

        self._btn_export_image = _stacked_button(
            tr("Export image..."),
            tr("Write the picture of the visible layers to a file"),
            _export_icon)
        self._btn_export_image.clicked.connect(self._on_export_image)
        self._toolbar.addWidget(self._btn_export_image)

        self._btn_reload = _stacked_button(
            tr("Reload"),
            tr("Reload latest component data from the main window"),
            _reload_icon)
        self._btn_reload.clicked.connect(self._on_reload_records)
        self._toolbar.addWidget(self._btn_reload)

        self._btn_view_transform = (self._btn_rotate, self._btn_flip_x,
                                    self._btn_flip_y, self._btn_pickplace,
                                    self._btn_grid)
        for btn in self._btn_view_transform:
            btn.setEnabled(False)
        self._sync_transform_controls()
        layout.addWidget(self._toolbar)

        body = QHBoxLayout()
        body.setSpacing(10)

        # The card of the layers stands at the left of the board, the way
        # the reference viewer holds it.  It can be folded away, so that
        # the board gets the whole width.
        self._card = QWidget()
        card_outer = QVBoxLayout(self._card)
        card_outer.setContentsMargins(0, 0, 0, 0)
        card_outer.setSpacing(4)

        card_header = QHBoxLayout()
        card_header.setSpacing(2)
        self._btn_collapse_card = QToolButton()
        self._btn_collapse_card.setAutoRaise(True)
        self._btn_collapse_card.setIcon(
            _collapse_card_icon(False))
        self._btn_collapse_card.setToolTip(tr("Collapse the card"))
        self._btn_collapse_card.clicked.connect(self._on_collapse_card_clicked)
        card_header.addWidget(self._btn_collapse_card)
        self._lbl_card_title = QLabel(tr("Layers + Colors"))
        self._lbl_card_title.setStyleSheet("font-weight: bold;")
        card_header.addWidget(self._lbl_card_title, 1)
        card_outer.addLayout(card_header)

        self._card_content = QWidget()
        self._card_content_layout = QVBoxLayout(self._card_content)
        self._card_content_layout.setContentsMargins(0, 0, 0, 0)
        self._card_content_layout.setSpacing(6)
        self._build_card_content()
        card_outer.addWidget(self._card_content, 1)
        self._card.setFixedWidth(CARD_WIDTH)
        body.addWidget(self._card)

        self._view = GerberView()
        self._scene = QGraphicsScene(self)
        self._view.setScene(self._scene)
        body.addWidget(self._view, 1)

        panel = QVBoxLayout()
        panel.setSpacing(0)
        panel.setContentsMargins(0, 0, 0, 0)

        # The upper card: the search, the table and the status of the
        # components.  The lower card: the magnifier of the details.
        # A splitter between the two cards lets the operator choose how
        # much space each of them gets.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)

        comp_group = QGroupBox(tr("Components"))
        comp_group.setStyleSheet(_CARD_QSS)
        comp_layout = QVBoxLayout(comp_group)
        comp_layout.setSpacing(6)
        comp_layout.setContentsMargins(8, 0, 8, 8)

        self._options_widget = QWidget()
        self._options_layout = QVBoxLayout(self._options_widget)
        self._options_layout.setSpacing(8)
        self._options_layout.setContentsMargins(0, 0, 0, 0)

        comp_row = QHBoxLayout()
        comp_row.addWidget(QLabel(tr("Components:")))
        comp_row.addStretch(1)
        self._chk_group_mpn = QCheckBox(tr("Group by MPN"))
        self._chk_group_mpn.setToolTip(
            tr("Group components by MPN and highlight all designators on double-click")
        )
        self._chk_group_mpn.toggled.connect(self._on_group_mpn_toggled)
        comp_row.addWidget(self._chk_group_mpn)
        self._options_layout.addLayout(comp_row)

        comp_layout.addWidget(self._options_widget)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(tr("Search designator or MPN..."))
        self._search_input.setClearButtonEnabled(True)
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(150)
        self._search_debounce.timeout.connect(self._apply_layer)
        self._search_input.textChanged.connect(self._on_search_changed)
        comp_layout.addWidget(self._search_input)

        self._table_components = QTableWidget()
        self._table_components.setColumnCount(5)
        self._table_components.setHorizontalHeaderLabels([
            tr("#"), tr("Designator"), tr("X"), tr("Y"), tr("Rot"),
        ])
        self._table_components.setSelectionBehavior(QTableWidget.SelectRows)
        self._table_components.setSelectionMode(QTableWidget.SingleSelection)
        self._table_components.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table_components.verticalHeader().setVisible(False)
        self._table_components.horizontalHeader().setStretchLastSection(True)
        self._table_components.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table_components.setWordWrap(True)
        self._table_components.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table_components.currentCellChanged.connect(self._on_row_changed)
        self._table_components.cellDoubleClicked.connect(self._on_component_double_clicked)
        self._table_components.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table_components.customContextMenuRequested.connect(self._on_component_menu)
        comp_layout.addWidget(self._table_components, 1)

        self._lbl_status = QLabel(tr("No data yet."))
        self._lbl_status.setWordWrap(True)
        comp_layout.addWidget(self._lbl_status)

        self._lbl_load_note = QLabel("")
        self._lbl_load_note.setWordWrap(True)
        self._lbl_load_note.setStyleSheet(f"color: {err_color()};")
        self._lbl_load_note.setVisible(False)
        comp_layout.addWidget(self._lbl_load_note)

        splitter.addWidget(comp_group)

        self._mag_group = QGroupBox(tr("Details (Zoom {f:g}x)", f=_MAG_FACTOR))
        self._mag_group.setStyleSheet(_CARD_QSS)
        mag_layout = QVBoxLayout(self._mag_group)
        mag_layout.setSpacing(4)
        mag_layout.setContentsMargins(0, 0, 0, 0)
        mag_row = QHBoxLayout()
        mag_row.addWidget(QLabel(tr("Zoom:")))
        self._combo_mag = QComboBox()
        default_idx = 0
        for i, f in enumerate(_MAG_FACTORS):
            self._combo_mag.addItem(f"{f:g}x", f)
            if abs(f - _MAG_FACTOR) < 1e-9:
                default_idx = i
        self._combo_mag.setCurrentIndex(default_idx)
        self._combo_mag.currentIndexChanged.connect(self._on_mag_factor_changed)
        mag_row.addWidget(self._combo_mag, 1)
        mag_layout.addLayout(mag_row)
        self._mag_view = MagnifierView()
        self._mag_view.setFrameShape(QFrame.NoFrame)
        self._mag_view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self._mag_view.setBackgroundBrush(BACKGROUND)
        self._mag_view.setInteractive(False)
        self._mag_view.setDragMode(QGraphicsView.NoDrag)
        self._mag_view.setTransformationAnchor(QGraphicsView.NoAnchor)
        self._mag_view.setResizeAnchor(QGraphicsView.NoAnchor)
        self._mag_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._mag_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._mag_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._mag_view.setMinimumSize(380, 200)
        self._mag_view.setScene(self._scene)
        mag_layout.addWidget(self._mag_view, 1)
        self._lbl_mag_hint = QLabel(tr("Hover the drawing / select a component to see details."))
        self._lbl_mag_hint.setWordWrap(True)
        mag_layout.addWidget(self._lbl_mag_hint)

        splitter.addWidget(self._mag_group)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 240])
        panel.addWidget(splitter, 1)

        self._view.cursor_moved.connect(self._on_cursor_moved)
        self._view.cursor_left.connect(self._clear_coord_label)
        self._view.cursor_left.connect(self._refresh_magnifier)
        self._view.zoom_end.connect(self._refresh_magnifier)
        self._view.grid_cell_clicked.connect(self._on_grid_cell_clicked)
        self._view.measure_clicked.connect(self._on_measure_clicked)
        self._view.origin_picked.connect(self._on_origin_picked)
        self._view.align_pad_picked.connect(self._on_align_pad_clicked)
        self._view.align_pad_cancel.connect(self._on_align_pad_cancel)
        self._view.trace_pad_picked.connect(self._on_trace_picked)
        self._view.trace_pad_cancel.connect(self._on_trace_cancel)
        self._view.cursor_moved.connect(self._on_align_move)
        self._view.measure_cancel.connect(self._on_measure_cancel)
        self._view.cursor_moved.connect(self._on_measure_move)
        self._view.crosshair_right_clicked.connect(self._on_crosshair_right_clicked)
        self._mag_view.clicked.connect(self._on_mag_clicked)

        self._build_pickplace_dialog()
        self._build_grid_dialog()

        panel_widget = QWidget()
        panel_widget.setLayout(panel)
        panel_widget.setFixedWidth(400)
        body.addWidget(panel_widget)

        layout.addLayout(body, 1)

        coord_bar = QHBoxLayout()
        self._lbl_coord = QLabel(tr("X: --  Y: --"))
        coord_bar.addWidget(self._lbl_coord)
        coord_bar.addStretch(1)
        self._btn_snap = QPushButton(tr("Snap"))
        self._btn_snap.setCheckable(True)
        self._btn_snap.setChecked(True)
        self._btn_snap.setEnabled(False)
        self._btn_snap.setToolTip(
            tr("Toggle snap to pad center when measuring. "
               "Hold Ctrl while clicking to bypass snap for that click.")
        )
        self._btn_snap.toggled.connect(self._on_snap_toggled)
        coord_bar.addWidget(self._btn_snap)
        coord_bar.addWidget(QLabel(tr("X:")))
        self._spin_goto_x = QDoubleSpinBox()
        self._spin_goto_x.setRange(-100000.0, 100000.0)
        self._spin_goto_x.setSingleStep(0.05)
        self._spin_goto_x.setDecimals(2)
        self._spin_goto_x.returnPressed.connect(self._goto_coord)
        coord_bar.addWidget(self._spin_goto_x)
        coord_bar.addWidget(QLabel(tr("Y:")))
        self._spin_goto_y = QDoubleSpinBox()
        self._spin_goto_y.setRange(-100000.0, 100000.0)
        self._spin_goto_y.setSingleStep(0.05)
        self._spin_goto_y.setDecimals(2)
        self._spin_goto_y.returnPressed.connect(self._goto_coord)
        coord_bar.addWidget(self._spin_goto_y)
        self._btn_goto = QPushButton(tr("Go"))
        self._btn_goto.clicked.connect(self._goto_coord)
        coord_bar.addWidget(self._btn_goto)
        self._btn_origin_from_fields = QPushButton(tr("Set origin"))
        self._btn_origin_from_fields.setToolTip(
            tr("Move the origin by the X and Y that are written here"))
        self._btn_origin_from_fields.clicked.connect(self._on_origin_from_fields)
        coord_bar.addWidget(self._btn_origin_from_fields)
        layout.addLayout(coord_bar)

    def refresh_icons(self) -> None:
        """Repaint toolbar icons when the theme changes."""
        for button, icon_factory in getattr(self, "_toolbar_icon_sources", []):
            try:
                button.setIcon(icon_factory())
            except Exception:
                pass

    def _build_card_content(self) -> None:
        """Fill the card with the layers, the colours and the overlay."""
        layout = self._card_content_layout

        # --- The layers of the picture ---
        layers_group = QGroupBox(tr("Layers"))
        layers_layout = QVBoxLayout(layers_group)
        layers_layout.setSpacing(4)

        layer_buttons = QHBoxLayout()
        btn_show_all = QPushButton(tr("Show all"))
        btn_show_all.clicked.connect(
            lambda: self._set_all_layer_states(LAYER_STATE_NORMAL))
        layer_buttons.addWidget(btn_show_all)
        btn_hide_all = QPushButton(tr("Hide all"))
        btn_hide_all.clicked.connect(
            lambda: self._set_all_layer_states(LAYER_STATE_HIDDEN))
        layer_buttons.addWidget(btn_hide_all)
        btn_only_active = QPushButton(tr("Only active"))
        btn_only_active.setToolTip(tr("Show only the layer that is active"))
        btn_only_active.clicked.connect(self._show_only_active_layer)
        layer_buttons.addWidget(btn_only_active)
        layers_layout.addLayout(layer_buttons)

        self._table_layers = QTableWidget()
        self._table_layers.setColumnCount(3)
        self._table_layers.setHorizontalHeaderLabels(
            [tr("Show"), tr("Layer"), tr("File")])
        self._table_layers.verticalHeader().setVisible(False)
        self._table_layers.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table_layers.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._table_layers.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table_layers.setColumnWidth(0, 30)
        self._table_layers.setColumnWidth(2, 150)
        self._table_layers.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self._table_layers.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Interactive)
        self._table_layers.itemChanged.connect(self._on_layer_item_changed)
        self._table_layers.cellClicked.connect(self._on_layer_cell_clicked)
        self._table_layers.setMinimumHeight(160)
        layers_layout.addWidget(self._table_layers, 1)
        layout.addWidget(layers_group, 1)

        # --- The colours ---
        colors_group = QGroupBox(tr("Colors"))
        colors_layout = QVBoxLayout(colors_group)
        colors_layout.setSpacing(4)
        target_row = QHBoxLayout()
        target_row.setSpacing(6)
        self._lbl_color_chip = QLabel()
        self._lbl_color_chip.setFixedSize(18, 18)
        target_row.addWidget(self._lbl_color_chip)
        self._lbl_color_target = QLabel()
        self._lbl_color_target.setStyleSheet(
            f"color: {muted_color()}; font-style: italic;")
        self._lbl_color_target.setWordWrap(True)
        target_row.addWidget(self._lbl_color_target, 1)
        colors_layout.addLayout(target_row)

        palette = QGridLayout()
        palette.setSpacing(3)
        for index, hex_value in enumerate(LAYER_PALETTE):
            button = QPushButton()
            button.setFixedSize(22, 22)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background-color: {hex_value};"
                " border: 1px solid #888; border-radius: 3px; }")
            button.setToolTip(hex_value)
            button.clicked.connect(
                lambda _checked=False, value=hex_value:
                self._apply_palette_color(value))
            palette.addWidget(button, index // 8, index % 8)
        colors_layout.addLayout(palette)

        btn_custom = QPushButton(tr("Custom..."))
        btn_custom.setToolTip(tr("Choose a colour of your own"))
        btn_custom.clicked.connect(self._pick_custom_color)
        colors_layout.addWidget(btn_custom)
        layout.addWidget(colors_group)

        # The marker options of the overlay stand in the PickPlace dialog
        # that the toolbar of the page opens.

        self._update_color_target_label()

    # ------------------------------------------------------------------
    # The dialog of the overlay of the Pick&Place
    # ------------------------------------------------------------------
    def _build_pickplace_dialog(self) -> None:
        """Make the dialog that edits the overlay of the Pick&Place.

        The dialog holds draft widgets: while it is open the picture does
        not change.  Only the Save takes the drafts over.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("PickPlace overlay"))
        layout = QVBoxLayout(dialog)

        markers_group = QGroupBox(tr("PickPlace markers"))
        markers_layout = QVBoxLayout(markers_group)
        markers_layout.setSpacing(4)
        self._pp_chk_pickplace = QCheckBox(tr("Show PickPlace (aligned)"))
        markers_layout.addWidget(self._pp_chk_pickplace)

        cross_row = QHBoxLayout()
        self._pp_chk_crosshair = QCheckBox(tr("Show crosshair"))
        cross_row.addWidget(self._pp_chk_crosshair, 1)
        cross_row.addWidget(self._make_color_swatch("cross"))
        markers_layout.addLayout(cross_row)

        highlight_row = QHBoxLayout()
        highlight_row.addWidget(QLabel(tr("Highlight")))
        highlight_row.addStretch(1)
        highlight_row.addWidget(self._make_color_swatch("highlight"))
        markers_layout.addLayout(highlight_row)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel(tr("Crosshair scale:")))
        self._pp_spin_cross_scale = QDoubleSpinBox()
        self._pp_spin_cross_scale.setRange(0.5, 5.0)
        self._pp_spin_cross_scale.setSingleStep(0.1)
        self._pp_spin_cross_scale.setDecimals(1)
        scale_row.addWidget(self._pp_spin_cross_scale, 1)
        markers_layout.addLayout(scale_row)

        arrow_row = QHBoxLayout()
        arrow_row.addWidget(QLabel(tr("Arrow size:")))
        self._pp_spin_arrow_px = QSpinBox()
        self._pp_spin_arrow_px.setRange(5, 100)
        self._pp_spin_arrow_px.setSingleStep(5)
        self._pp_spin_arrow_px.setSuffix(" px")
        arrow_row.addWidget(self._pp_spin_arrow_px, 1)
        markers_layout.addLayout(arrow_row)

        self._pp_chk_frame = QCheckBox(tr("Show frame"))
        markers_layout.addWidget(self._pp_chk_frame)
        layout.addWidget(markers_group)

        other_group = QGroupBox(tr("Display"))
        other_layout = QVBoxLayout(other_group)
        other_layout.setSpacing(4)
        self._pp_chk_origin = QCheckBox(tr("Show origin (0,0)"))
        self._pp_chk_origin.setToolTip(
            tr("Mark the point the coordinates of the file count from"))
        other_layout.addWidget(self._pp_chk_origin)
        note = QLabel(tr("The crosshair of the view follows the pointer "
                         "across the whole view; it is always on."))
        note.setStyleSheet(f"color: {muted_color()}; font-style: italic;")
        note.setWordWrap(True)
        other_layout.addWidget(note)
        layout.addWidget(other_group)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        btn_cancel = QPushButton(tr("Cancel"))
        btn_cancel.clicked.connect(self._cancel_pickplace_dialog)
        button_row.addWidget(btn_cancel)
        btn_save = QPushButton(tr("Save"))
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._save_pickplace_dialog)
        button_row.addWidget(btn_save)
        layout.addLayout(button_row)

        self._pp_dialog = dialog

    def _sync_pickplace_dialog(self) -> None:
        """Load the state of the overlay into the draft widgets."""
        self._pp_color_draft.clear()
        self._pp_chk_pickplace.setChecked(self._chk_pickplace.isChecked())
        self._pp_chk_crosshair.setChecked(self._chk_crosshair.isChecked())
        self._pp_chk_origin.setChecked(self._chk_origin.isChecked())
        self._pp_chk_frame.setChecked(self._chk_frame.isChecked())
        self._pp_spin_cross_scale.setValue(self._spin_cross_scale.value())
        self._pp_spin_arrow_px.setValue(self._spin_arrow_px.value())
        self._sync_color_buttons()

    def _open_pickplace_dialog(self) -> None:
        self._sync_pickplace_dialog()
        self._pp_dialog.exec()

    def _cancel_pickplace_dialog(self) -> None:
        """Throw the drafts away: nothing has changed on the board."""
        self._pp_color_draft.clear()
        self._sync_color_buttons()
        self._pp_dialog.reject()

    def _save_pickplace_dialog(self) -> None:
        """Take the drafts over and redraw the picture with them."""
        self._chk_pickplace.setChecked(self._pp_chk_pickplace.isChecked())
        self._chk_crosshair.setChecked(self._pp_chk_crosshair.isChecked())
        self._chk_origin.setChecked(self._pp_chk_origin.isChecked())
        self._chk_frame.setChecked(self._pp_chk_frame.isChecked())
        self._spin_cross_scale.setValue(self._pp_spin_cross_scale.value())
        self._spin_arrow_px.setValue(self._pp_spin_arrow_px.value())
        for key, hex_val in self._pp_color_draft.items():
            color = QColor(hex_val)
            if color.isValid():
                self._colors[key] = color
        self._pp_color_draft.clear()
        self._sync_color_buttons()
        self._redraw()
        self._emit_layer_settings()
        self._pp_dialog.accept()

    # ------------------------------------------------------------------
    # The dialog of the grid
    # ------------------------------------------------------------------
    def _build_grid_dialog(self) -> None:
        """Make the dialog of the grid: drafts and a short information."""
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Grid settings"))
        layout = QVBoxLayout(dialog)

        grid_group = QGroupBox(tr("Grid"))
        grid_layout = QVBoxLayout(grid_group)
        grid_layout.setSpacing(4)

        grid_row = QHBoxLayout()
        self._gd_chk_grid = QCheckBox(tr("Show grid"))
        grid_row.addWidget(self._gd_chk_grid)
        grid_row.addWidget(QLabel(tr("Col:")))
        self._gd_spin_cols = QSpinBox()
        self._gd_spin_cols.setRange(1, 50)
        grid_row.addWidget(self._gd_spin_cols)
        grid_row.addWidget(QLabel(tr("Row:")))
        self._gd_spin_rows = QSpinBox()
        self._gd_spin_rows.setRange(1, 50)
        grid_row.addWidget(self._gd_spin_rows)
        grid_row.addStretch(1)
        grid_layout.addLayout(grid_row)

        grid_style_row = QHBoxLayout()
        grid_style_row.addWidget(QLabel(tr("Grid opacity:")))
        self._gd_spin_opacity = QSpinBox()
        self._gd_spin_opacity.setRange(20, 255)
        self._gd_spin_opacity.setSingleStep(5)
        grid_style_row.addWidget(self._gd_spin_opacity)
        grid_style_row.addWidget(QLabel(tr("Grid width:")))
        self._gd_spin_width = QDoubleSpinBox()
        self._gd_spin_width.setRange(1.0, 4.0)
        self._gd_spin_width.setSingleStep(0.5)
        self._gd_spin_width.setDecimals(1)
        grid_style_row.addWidget(self._gd_spin_width)
        grid_style_row.addStretch(1)
        grid_layout.addLayout(grid_style_row)

        self._gd_spin_cols.valueChanged.connect(self._update_grid_info)
        self._gd_spin_rows.valueChanged.connect(self._update_grid_info)
        layout.addWidget(grid_group)

        snap_group = QGroupBox(tr("Snapping"))
        snap_layout = QVBoxLayout(snap_group)
        snap_layout.setSpacing(4)
        snap_row = QHBoxLayout()
        snap_row.addWidget(QLabel(tr("Tolerance:")))
        self._gd_spin_tol = QDoubleSpinBox()
        self._gd_spin_tol.setRange(0.1, 5.0)
        self._gd_spin_tol.setSingleStep(0.1)
        self._gd_spin_tol.setDecimals(1)
        self._gd_spin_tol.setSuffix(" mm")
        self._gd_spin_tol.setToolTip(
            tr("Snap tolerance is in mm and applies to the nearest pad center within the radius."))
        snap_row.addWidget(self._gd_spin_tol)
        snap_row.addStretch(1)
        snap_layout.addLayout(snap_row)
        layout.addWidget(snap_group)

        info_group = QGroupBox(tr("Information"))
        info_layout = QVBoxLayout(info_group)
        self._lbl_grid_info = QLabel()
        self._lbl_grid_info.setWordWrap(True)
        info_layout.addWidget(self._lbl_grid_info)
        layout.addWidget(info_group)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        btn_cancel = QPushButton(tr("Cancel"))
        btn_cancel.clicked.connect(dialog.reject)
        button_row.addWidget(btn_cancel)
        btn_save = QPushButton(tr("Save"))
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._save_grid_dialog)
        button_row.addWidget(btn_save)
        layout.addLayout(button_row)

        self._grid_dialog = dialog

    def _open_grid_dialog(self) -> None:
        """Load the state of the grid into the draft widgets."""
        self._gd_chk_grid.setChecked(self._chk_grid.isChecked())
        self._gd_chk_grid.setEnabled(self._grid_available)
        self._gd_spin_cols.setValue(self._spin_grid_cols.value())
        self._gd_spin_rows.setValue(self._spin_grid_rows.value())
        self._gd_spin_opacity.setValue(self._spin_grid_opacity.value())
        self._gd_spin_width.setValue(self._spin_grid_width.value())
        self._gd_spin_tol.setValue(self._spin_snap_tol.value())
        self._update_grid_info()
        self._grid_dialog.exec()

    def _save_grid_dialog(self) -> None:
        """Take the drafts over and put the grid on the board."""
        if bool(self._gd_chk_grid.isChecked()) != self._chk_grid.isChecked():
            self._chk_grid.setChecked(bool(self._gd_chk_grid.isChecked()))
        self._spin_grid_cols.setValue(self._gd_spin_cols.value())
        self._spin_grid_rows.setValue(self._gd_spin_rows.value())
        self._spin_grid_opacity.setValue(self._gd_spin_opacity.value())
        self._spin_grid_width.setValue(self._gd_spin_width.value())
        self._spin_snap_tol.setValue(self._gd_spin_tol.value())
        self._emit_layer_settings()
        self._grid_dialog.accept()

    def _update_grid_info(self) -> None:
        """Tell how wide one cell of the grid is, and the board as well."""
        if not self._loaded:
            self._lbl_grid_info.setText(tr("The board is not drawn yet."))
            return
        rect = self._gerber_scene_rect()
        if rect.isEmpty() or not rect.isValid():
            self._lbl_grid_info.setText(tr("The board is not drawn yet."))
            return
        cols = max(1, self._gd_spin_cols.value())
        rows = max(1, self._gd_spin_rows.value())
        cell_w = rect.width() / cols
        cell_h = rect.height() / rows
        self._lbl_grid_info.setText(tr(
            "Board: {w:.2f} x {h:.2f} mm\nOne cell: {cw:.2f} x {ch:.2f} mm",
            w=rect.width(), h=rect.height(), cw=cell_w, ch=cell_h))

    # ------------------------------------------------------------------
    # The list of the layers
    # ------------------------------------------------------------------
    def _default_layer_color(self, layer: LayerInfo) -> QColor:
        """The colour a layer has when nothing was chosen for it."""
        if layer.role == ROLE_PROFILE:
            return QColor(OUTLINE_COLOR)
        if layer.role == ROLE_COPPER:
            return QColor(COPPER_COLOR)
        if layer.role == ROLE_MASK:
            return QColor(MASK_COLOR)
        if layer.role == ROLE_PASTE:
            return QColor(TOP_PASTE_COLOR if layer.side != SIDE_BOTTOM
                          else BOTTOM_PASTE_COLOR)
        if layer.role == ROLE_SILK:
            return QColor(SILK_COLOR)
        if layer.role == ROLE_DRILL:
            return QColor(DRILL_COLOR)
        return QColor(OTHER_COLOR)

    def _rebuild_layer_list(self) -> None:
        """Fill the table of the layers."""
        table = self._table_layers
        current = table.currentRow()
        table.blockSignals(True)
        try:
            table.setRowCount(len(self._layers))
            for index, layer in enumerate(self._layers):
                state = self._layer_states[index] if index < len(self._layer_states) \
                    else LAYER_STATE_NORMAL
                tick = QTableWidgetItem("")
                tick.setFlags(
                    Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                tick.setCheckState(
                    Qt.Unchecked if state == LAYER_STATE_HIDDEN else Qt.Checked)
                tick.setData(Qt.ItemDataRole.UserRole, index)
                table.setItem(index, 0, tick)

                name_item = QTableWidgetItem(layer.name)
                name_item.setData(Qt.ItemDataRole.UserRole, index)
                colour = QColor(self._layer_colors[index]) \
                    if index < len(self._layer_colors) else QColor(OTHER_COLOR)
                # The tooltip holds the whole name, the place of the file
                # and the colour of the layer.
                name_item.setToolTip(
                    f"{layer.name}\n{layer.path}\n"
                    + tr("Color: {value}", value=colour.name(QColor.HexArgb)))
                if index == self._active_layer:
                    font = name_item.font()
                    font.setBold(True)
                    name_item.setFont(font)
                table.setItem(index, 1, name_item)

                file_item = QTableWidgetItem(layer.file_name)
                file_item.setToolTip(f"{layer.file_name}\n{layer.path}")
                table.setItem(index, 2, file_item)
        finally:
            table.blockSignals(False)
        if 0 <= current < table.rowCount():
            # The layer that was chosen stays chosen.
            table.selectRow(current)

    def _on_layer_item_changed(self, item: QTableWidgetItem) -> None:
        """The tick of a layer was clicked."""
        if item is None or item.column() != 0:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return
        index = int(index)
        if index >= len(self._layer_states):
            return
        state = LAYER_STATE_HIDDEN \
            if item.checkState() == Qt.Unchecked else LAYER_STATE_NORMAL
        if self._layer_states[index] == state:
            return
        self._layer_states[index] = state
        self._rebuild_layer_list()
        self._redraw()
        self._emit_layer_settings()

    def _on_layer_cell_clicked(self, row: int, column: int) -> None:
        """A cell of the table of the layers was clicked."""
        if column == 0:
            # The tick is looked after by the change of the item.
            return
        # The name of the layer brings it on top of the others, and the
        # palette of the colours works on it from then on.
        self._set_active_layer(row)

    def _emit_layer_settings(self) -> None:
        """Remember the state of the layers, as the display settings are."""
        try:
            self.settings_saved.emit(self.display_settings())
        except RuntimeError:
            pass

    def _set_color_target(self, kind: str, index: int = -1) -> None:
        """Choose what the palette of the colours works on.

        The target is a layer of the picture, or the crosshair of the
        overlay, or the colour of the highlight.
        """
        self._color_target = (kind, index)
        self._update_color_target_label()

    def _color_target_index(self) -> int:
        """The layer the palette of the colours works on."""
        _kind, index = getattr(self, "_color_target", ("layer", -1))
        if 0 <= index < len(self._layers):
            return index
        # Nothing was chosen yet: the layer that is active is the one.
        if 0 <= self._active_layer < len(self._layers):
            return self._active_layer
        return -1

    def _update_color_target_label(self) -> None:
        """Tell what the palette of the colours works on."""
        kind, _index = getattr(self, "_color_target", ("layer", -1))
        if kind == "cross":
            name = tr("Crosshair")
            colour = QColor(self._current_color("cross"))
        elif kind == "highlight":
            name = tr("Highlight")
            colour = QColor(self._current_color("highlight"))
        else:
            index = self._color_target_index()
            if 0 <= index < len(self._layers) \
                    and index < len(self._layer_colors):
                name = self._layers[index].name
                colour = QColor(self._layer_colors[index])
            else:
                name = tr("a layer")
                colour = QColor("#94A3B8")
        # The chip shows the hue in full, however see-through the layer is.
        colour.setAlpha(255)
        chip = getattr(self, "_lbl_color_chip", None)
        if chip is not None:
            chip.setStyleSheet(
                f"background-color: {colour.name(QColor.HexRgb)};"
                " border: 2px solid #22C55E; border-radius: 4px;")
        label = getattr(self, "_lbl_color_target", None)
        if label is not None:
            label.setText(tr("Color for: {name}", name=name))

    def _apply_palette_color(self, hex_value: str) -> None:
        """Give the target of the palette the colour that was picked."""
        kind, index = getattr(self, "_color_target", ("layer", -1))
        if kind == "layer":
            index = self._color_target_index()
            if not 0 <= index < len(self._layer_colors):
                return
            colour = QColor(hex_value)
            # The transparency of the layer is kept.
            colour.setAlpha(QColor(self._layer_colors[index]).alpha())
            self._layer_colors[index] = colour
            self._rebuild_layer_list()
            self._update_color_target_label()
            self._redraw()
        else:
            self._colors[kind] = QColor(hex_value)
            self._update_swatch(kind)
            self._update_color_target_label()
            self._redraw()
        self._emit_layer_settings()

    def _pick_custom_color(self) -> None:
        """Choose a colour of one's own for the target of the palette."""
        kind, _index = getattr(self, "_color_target", ("layer", -1))
        if kind == "layer":
            index = self._color_target_index()
            if not 0 <= index < len(self._layer_colors):
                return
            initial = QColor(self._layer_colors[index])
            name = self._layers[index].name
        else:
            initial = self._current_color(kind)
            name = self._color_label(kind)
        colour = QColorDialog.getColor(
            initial, self, tr("Choose the color of {name}", name=name),
            QColorDialog.ShowAlphaChannel)
        if not colour.isValid():
            return
        if kind == "layer":
            self._layer_colors[index] = colour
            self._rebuild_layer_list()
            self._update_color_target_label()
            self._redraw()
        else:
            self._colors[kind] = colour
            self._update_swatch(kind)
            self._update_color_target_label()
            self._redraw()
        self._emit_layer_settings()

    def _set_all_layer_states(self, state: str) -> None:
        """Show or hide every layer at once."""
        for index in range(len(self._layer_states)):
            self._layer_states[index] = state
        self._rebuild_layer_list()
        self._redraw()
        self._emit_layer_settings()

    def _show_only_active_layer(self) -> None:
        """Show the layer that is active and hide the others."""
        for index in range(len(self._layer_states)):
            self._layer_states[index] = (LAYER_STATE_NORMAL
                                         if index == self._active_layer
                                         else LAYER_STATE_HIDDEN)
        self._rebuild_layer_list()
        self._redraw()
        self._emit_layer_settings()

    def _set_active_layer(self, index: int) -> None:
        """Bring one layer on top of the others."""
        if index < 0 or index >= len(self._layers):
            return
        self._active_layer = index
        if getattr(self, "_color_target", ("layer", -1))[0] == "layer":
            # The palette follows the layer that is active.
            self._color_target = ("layer", index)
            self._update_color_target_label()
        self._rebuild_layer_list()
        self._redraw()
        self._emit_layer_settings()

    def _layer_settings(self) -> List[Dict[str, Any]]:
        """The colour and the state of every layer, to be remembered."""
        settings = []
        for index, layer in enumerate(self._layers):
            colour = self._layer_colors[index] \
                if index < len(self._layer_colors) else QColor(OTHER_COLOR)
            state = self._layer_states[index] \
                if index < len(self._layer_states) else LAYER_STATE_NORMAL
            settings.append({
                "key": layer.key(),
                "name": layer.name,
                "color": colour.name(QColor.HexArgb),
                "state": state,
            })
        return settings

    def _apply_layer_settings(self, settings) -> None:
        """Give the layers the colours and the states they had."""
        if not isinstance(settings, list):
            return
        by_key = {}
        for entry in settings:
            if isinstance(entry, dict) and entry.get("key"):
                by_key[entry["key"]] = entry
        for index, layer in enumerate(self._layers):
            entry = by_key.get(layer.key())
            if not entry:
                continue
            colour = QColor(entry.get("color", ""))
            if colour.isValid() and index < len(self._layer_colors):
                self._layer_colors[index] = colour
            state = entry.get("state")
            if state == LAYER_STATE_DIMMED:
                # The card only has a tick now, so a layer that was dimmed
                # is shown.
                state = LAYER_STATE_NORMAL
            if state in (LAYER_STATE_NORMAL, LAYER_STATE_HIDDEN) and index < len(self._layer_states):
                self._layer_states[index] = state
        self._rebuild_layer_list()

    def _active_layer_key(self) -> str:
        """The key of the layer that is active."""
        if 0 <= self._active_layer < len(self._layers):
            return self._layers[self._active_layer].key()
        return ""

    def _make_color_swatch(self, key: str) -> QPushButton:
        button = QPushButton()
        button.setFixedSize(40, 22)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(self._color_swatch_tooltip(key))
        button.clicked.connect(lambda: self._pick_color(key))
        self._color_buttons[key] = button
        self._update_swatch(key)
        return button

    def _on_collapse_card_clicked(self) -> None:
        """Fold the card away, or open it again."""
        collapsed = self._card_content.isVisible()
        self._card_content.setVisible(not collapsed)
        self._lbl_card_title.setVisible(not collapsed)
        self._card.setFixedWidth(
            CARD_WIDTH_COLLAPSED if collapsed else CARD_WIDTH)
        self._btn_collapse_card.setIcon(_collapse_card_icon(collapsed))
        self._btn_collapse_card.setToolTip(
            tr("Expand the card") if collapsed else tr("Collapse the card"))

    def _on_crosshair_toggled(self, checked: bool) -> None:
        """The crosshair of the overlay is shown, or taken away."""
        self._redraw()
        self._emit_layer_settings()

    def _color_swatch_tooltip(self, key: str) -> str:
        color = self._current_color(key)
        return f"{tr('Color')}: {color.name(QColor.HexArgb)}"

    def _current_color(self, key: str) -> QColor:
        return self._colors[key]

    def _update_swatch(self, key: str) -> None:
        button = self._color_buttons.get(key)
        if button is None:
            return
        color = self._current_color(key)
        button.setStyleSheet(
            f"QPushButton {{ background-color: {color.name(QColor.HexArgb)};"
            f" border: 1px solid #888; border-radius: 3px; }}"
        )
        button.setToolTip(self._color_swatch_tooltip(key))

    def _sync_color_buttons(self) -> None:
        for key in self._color_buttons:
            self._update_swatch(key)

    def _pick_color(self, key: str) -> None:
        # A colour chosen here is a draft: the swatch shows it, and the
        # picture keeps the old one until the Save of the dialog runs.
        self._set_color_target(key)
        draft = self._pp_color_draft.get(key)
        initial = QColor(draft) if draft else self._current_color(key)
        color = QColorDialog.getColor(
            initial, self, tr("Choose {0} color").format(self._color_label(key)),
            QColorDialog.ShowAlphaChannel,
        )
        if color.isValid():
            self._pp_color_draft[key] = color.name(QColor.HexArgb)
            button = self._color_buttons.get(key)
            if button is not None:
                button.setStyleSheet(
                    f"QPushButton {{ background-color: {color.name(QColor.HexArgb)};"
                    f" border: 1px solid #888; border-radius: 3px; }}"
                )
                button.setToolTip(f"{tr('Color')}: {color.name(QColor.HexArgb)}")

    def _color_label(self, key: str) -> str:
        labels = {
            "cross": tr("Crosshair"),
            "highlight": tr("Highlight"),
        }
        return labels.get(key, key)

    def _on_arrow_size_changed(self, value: int) -> None:
        self._arrow_min_px = float(value)

    def _on_crosshair_scale_changed(self, value: float) -> None:
        self._crosshair_scale = float(value)
        self._redraw()

    def _on_frame_toggled(self, checked: bool) -> None:
        self._show_frame = bool(checked)

    # ------------------------------------------------------------------
    # The turn and the mirrors of the picture
    # ------------------------------------------------------------------
    @staticmethod
    def _transform_side_for_index(index: int) -> str:
        return "top" if int(index) == 0 else "bottom"

    def _current_transform_side(self) -> str:
        return self._transform_side_for_index(self._combo_layer.currentIndex())

    @staticmethod
    def _normalise_transform(
        entry: Any, fallback: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not isinstance(entry, dict):
            entry = {}
        try:
            rotation = int(entry.get("rotation", fallback.get("rotation", 0)) or 0)
        except (TypeError, ValueError):
            rotation = int(fallback.get("rotation", 0) or 0)
        return {
            "rotation": rotation % 360,
            "flip": bool(entry.get("flip", fallback.get("flip", False))),
            "mirror_x": bool(
                entry.get("mirror_x", fallback.get("mirror_x", False))),
        }

    def _store_current_transform(self) -> None:
        """Keep the turn and the mirrors that the current side holds."""
        self._layer_transforms[self._transform_side] = {
            "rotation": int(self._rotation) % 360,
            "flip": self._chk_flip.isChecked(),
            "mirror_x": self._chk_mirror_x.isChecked(),
        }

    def _apply_transform_to_widgets(self, transform: Dict[str, Any]) -> None:
        self._rotation = int(transform["rotation"]) % 360
        for widget, key in ((self._chk_flip, "flip"),
                            (self._chk_mirror_x, "mirror_x")):
            widget.blockSignals(True)
            widget.setChecked(bool(transform[key]))
            widget.blockSignals(False)

    def _load_transform_for_side(self, side: str) -> None:
        transform = self._normalise_transform(
            self._layer_transforms.get(side),
            {"rotation": 0, "flip": False, "mirror_x": False},
        )
        self._layer_transforms[side] = transform
        self._apply_transform_to_widgets(transform)

    def _set_rotation(self, angle: int, emit: bool = True) -> None:
        """Turn the picture by a right angle."""
        self._rotation = int(angle) % 360
        self._store_current_transform()
        self._sync_transform_controls()
        self._redraw()
        if emit:
            self._emit_layer_settings()

    def _on_flip_x_toggled(self, checked: bool) -> None:
        """The Flip X of the toolbar mirrors the picture about X."""
        self._chk_mirror_x.blockSignals(True)
        self._chk_mirror_x.setChecked(bool(checked))
        self._chk_mirror_x.blockSignals(False)
        self._store_current_transform()
        self._redraw()
        self._emit_layer_settings()

    def _on_flip_y_toggled(self, checked: bool) -> None:
        """The Flip Y of the toolbar mirrors the picture about Y."""
        self._chk_flip.blockSignals(True)
        self._chk_flip.setChecked(bool(checked))
        self._chk_flip.blockSignals(False)
        self._store_current_transform()
        self._redraw()
        self._emit_layer_settings()

    def _on_flip_state_changed(self, checked: bool) -> None:
        """The state of Mirror Y moved: follow it in the toolbar."""
        btn = getattr(self, "_btn_flip_y", None)
        if btn is not None and btn.isChecked() != bool(checked):
            btn.blockSignals(True)
            btn.setChecked(bool(checked))
            btn.blockSignals(False)
        self._store_current_transform()
        self._redraw()
        self._emit_layer_settings()

    def _on_mirror_x_state_changed(self, checked: bool) -> None:
        """The state of Mirror X moved: follow it in the toolbar."""
        btn = getattr(self, "_btn_flip_x", None)
        if btn is not None and btn.isChecked() != bool(checked):
            btn.blockSignals(True)
            btn.setChecked(bool(checked))
            btn.blockSignals(False)
        self._store_current_transform()
        self._redraw()
        self._emit_layer_settings()

    def _sync_transform_controls(self) -> None:
        """Let the toolbar show the turn and the mirrors that hold now."""
        for action in getattr(self, "_rotate_actions", []):
            action.blockSignals(True)
            action.setChecked(action.data() == int(self._rotation))
            action.blockSignals(False)
        for state_attr, btn_attr in (("_chk_flip", "_btn_flip_y"),
                                     ("_chk_mirror_x", "_btn_flip_x")):
            state = getattr(self, state_attr, None)
            button = getattr(self, btn_attr, None)
            if state is None or button is None:
                continue
            if button.isChecked() != state.isChecked():
                button.blockSignals(True)
                button.setChecked(state.isChecked())
                button.blockSignals(False)

    def _start_load(self) -> None:
        if not self._layers:
            QMessageBox.critical(self, tr("Error"), tr("No Gerber file."))
            self.close()
            return
        self._rebuild_layer_list()
        self._worker = GerberLoadWorker(self._layers, self)
        self._worker.progress.connect(self._on_load_progress)
        self._worker.finished.connect(self._on_load_finished)
        self._worker.failed.connect(self._on_load_failed)
        self._worker.start()

    def _on_load_progress(self, message: str, _pct: int) -> None:
        self._lbl_status.setText(message)

    def _on_load_finished(self, data: list) -> None:
        self._pad_grid_cache.clear()
        self._trace_indices.clear()
        self._layer_path_cache.clear()
        self._clear_trace_result()
        self._layer_data = list(data) if data else [
            RenderData() for _ in self._layers]
        self._rebuild_layer_list()
        self._outside_layers = self._hide_layers_outside_the_board()
        self._align_drill_layer()
        self._loaded = True
        self._board_center = self._compute_board_center()
        self._cross_half = self._board_size() * _CROSS_BOARD_RATIO
        self._apply_layer()
        # The first appearance of a big board names the layer at work
        # between two builds, so the wait is seen and the window answers.
        self._redraw(progress=True)
        self._fit_scene()
        self._lbl_status.setText("")
        self._show_load_warnings()
        self._btn_measure.setEnabled(True)
        self._btn_align_pad.setEnabled(True)
        self._btn_trace.setEnabled(True)
        self._btn_snap.setEnabled(True)
        for button in getattr(self, "_btn_check_controls", ()):
            button.setEnabled(True)
        for button in getattr(self, "_btn_view_transform", ()):
            button.setEnabled(True)

    def _align_drill_layer(self) -> None:
        """Put the drill holes on the board.

        A drill file is written in the coordinate system of the CAM job,
        which is usually not the system the Gerber files of the same board
        use.  The holes sit in the pads, so the offset between the two
        systems is found by matching the holes against the paste; when
        there is no paste the outline is used instead.
        """
        self._drill_align = None
        drills = [d for l, d in zip(self._layers, self._layer_data) if l.is_drill]
        if not any(d.flashes for d in drills):
            return
        holes = []
        for data in drills:
            holes += [(f.cx, f.cy) for f in data.flashes]
        pads = []
        for data in self._role_datas(ROLE_PASTE):
            pads += [(f.cx, f.cy) for f in data.flashes]
        reference = points_bbox(pads) if pads else None
        if reference is None:
            lines = []
            for data in self._role_datas(ROLE_PROFILE):
                lines += [(l.x1, l.y1) for l in data.lines]
                lines += [(l.x2, l.y2) for l in data.lines]
            reference = points_bbox(lines) if lines else None
        result = align_drill(holes, pads, board_bbox=reference)
        if result.applied or result.method == "outline":
            for data in drills:
                shift_render_data(data, result.offset_x, result.offset_y)
        self._drill_align = result

    def _layers_outside_the_board(self) -> List[int]:
        """The layers that do not lie on the board.

        A folder can hold the files of more than one board.  The layers
        that lie mostly outside the outline belong to another board, and
        they are hidden so that the picture stays readable.  When the
        folder has no outline, nothing is told, because the layers of a
        board can be of very different shapes.
        """
        outline = None
        boxes = []
        for layer, data in zip(self._layers, self._layer_data):
            if not (data.lines or data.arcs or data.flashes):
                boxes.append(None)
                continue
            box = data.bbox()
            boxes.append(box)
            if layer.role == ROLE_PROFILE and outline is None:
                outline = box
        if outline is None:
            return []
        out_x, out_y, out_w, out_h = outline
        out_area = max(out_w * out_h, 1e-9)
        outside = []
        for index, box in enumerate(boxes):
            if box is None or index == len(self._layers):
                continue
            if self._layers[index].role == ROLE_PROFILE:
                continue
            x, y, w, h = box
            overlap_w = min(x + w, out_x + out_w) - max(x, out_x)
            overlap_h = min(y + h, out_y + out_h) - max(y, out_y)
            if overlap_w <= 0.0 or overlap_h <= 0.0:
                outside.append(index)
                continue
            # The layer has to lie inside the outline; a layer of another
            # board only touches it.
            inside = (overlap_w * overlap_h) / max(w * h, 1e-9)
            if inside < 0.5:
                outside.append(index)
        return outside

    def _hide_layers_outside_the_board(self) -> List[int]:
        """Hide the layers that belong to another board."""
        outside = self._layers_outside_the_board()
        for index in outside:
            if index < len(self._layer_states):
                self._layer_states[index] = LAYER_STATE_HIDDEN
        if outside:
            self._rebuild_layer_list()
        return outside

    def _show_load_warnings(self) -> None:
        """Tell the operator when a file was read by a reduced parser.

        The layers that do not lie on the board are told about as well.
        """
        notes = []
        worker = getattr(self, "_worker", None)
        infos = getattr(worker, "load_info", {}) if worker is not None else {}
        for key, info in (infos or {}).items():
            if getattr(info, "degraded", False):
                notes.append(f"{key}: {getattr(info, 'parser', '?')}")
        outside = getattr(self, "_outside_layers", []) or []
        if outside:
            names = ", ".join(
                self._layers[index].file_name for index in outside
                if index < len(self._layers))
            notes.append(tr("{n} layers of another board (hidden): {files}",
                            n=len(outside), files=names))
        if not notes:
            self._lbl_load_note.setText("")
            self._lbl_load_note.setVisible(False)
            return
        self._lbl_load_note.setText(
            tr("Gerber layers: {files}", files="; ".join(notes))
        )
        self._lbl_load_note.setVisible(True)

    def _on_load_failed(self, message: str) -> None:
        self._lbl_status.setText(tr("Error reading Gerber file"))
        QMessageBox.critical(self, tr("Error"), tr("Cannot read Gerber:\n{message}", message=message))

    def _on_layer_changed(self) -> None:
        self._store_current_transform()
        self._transform_side = self._current_transform_side()
        self._load_transform_for_side(self._transform_side)
        self._sync_transform_controls()
        # The trace of the other side would show a net of layers that do
        # not belong to the side any more.
        self._clear_trace_result()
        self._apply_layer()
        self._redraw()

    def _on_search_changed(self, _text: str = "") -> None:
        self._search_debounce.start()

    def _record_matches_search(self, record: ReviewRecord, search_text: str) -> bool:
        if not search_text:
            return True
        search_text = search_text.lower()
        return (
            search_text in record.designator.lower()
            or search_text in (record.mpn or "").lower()
        )

    def _apply_layer(
        self, progress_cb: Optional[Callable[[int, int], None]] = None
    ) -> None:
        records = self._current_layer_records()
        search_text = self._search_input.text().strip().lower()
        header = self._table_components.horizontalHeader()
        row_header = self._table_components.verticalHeader()
        self._table_components.setUpdatesEnabled(False)
        row_header.setSectionResizeMode(QHeaderView.Interactive)
        try:
            self._table_components.setRowCount(0)
            self._component_index = []
            self._group_rows = []
            if self._group_by_mpn:
                self._table_components.setColumnCount(5)
                self._table_components.setHorizontalHeaderLabels([
                    tr("#"), tr("MPN"), tr("Designator"), tr("Qty"), tr("Status"),
                ])
                header.setSectionResizeMode(QHeaderView.Interactive)
                self._fill_grouped_table(records, search_text)
                if progress_cb is not None:
                    progress_cb(1, 1)
            else:
                self._table_components.setColumnCount(6)
                self._table_components.setHorizontalHeaderLabels([
                    tr("#"), tr("Designator"), tr("X"), tr("Y"), tr("Rot"), tr("Status"),
                ])
                header.setSectionResizeMode(QHeaderView.Interactive)
                total = max(len(records), 1)
                filled = 0
                for i, record in enumerate(records):
                    if not self._record_matches_search(record, search_text):
                        continue
                    x, y, rotation = _record_coord(record)
                    # The table shows the coordinates of the file; they
                    # do not change when the origin is moved.
                    row = self._table_components.rowCount()
                    values = [
                        str(row + 1),
                        record.designator,
                        f"{x:.3f}",
                        f"{y:.3f}",
                        f"{rotation:.0f}°",
                    ]
                    self._table_components.insertRow(row)
                    for col, val in enumerate(values):
                        item = QTableWidgetItem(val)
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        self._table_components.setItem(row, col, item)
                    status_item = QTableWidgetItem()
                    status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
                    status_item.setIcon(self._status_icon(record.checked))
                    self._table_components.setItem(row, len(values), status_item)
                    self._component_index.append(i)
                    filled += 1
                    if progress_cb is not None and filled % 100 == 0:
                        progress_cb(filled, total)
                if progress_cb is not None:
                    progress_cb(max(filled, 1), total)
        finally:
            self._table_components.resizeColumnsToContents()
            if self._group_by_mpn:
                header.setSectionResizeMode(QHeaderView.ResizeToContents)
                header.setSectionResizeMode(2, QHeaderView.Interactive)
                self._table_components.setColumnWidth(2, 200)
            else:
                header.setSectionResizeMode(QHeaderView.ResizeToContents)
            row_header.setSectionResizeMode(QHeaderView.ResizeToContents)
            self._table_components.setUpdatesEnabled(True)
        self._restore_highlight()

    def _fill_grouped_table(
        self, records: List[ReviewRecord], search_text: str
    ) -> None:
        groups: Dict[str, List[int]] = {}
        order: List[str] = []
        for i, record in enumerate(records):
            if not self._record_matches_search(record, search_text):
                continue
            mpn = (record.mpn or "").strip() or record.designator
            if mpn not in groups:
                groups[mpn] = []
                order.append(mpn)
            groups[mpn].append(i)
        for mpn in order:
            indices = groups[mpn]
            row = self._table_components.rowCount()
            designators = [records[i].designator for i in indices]
            values = [
                str(row + 1),
                mpn,
                ", ".join(designators),
                str(len(designators)),
                "",
            ]
            self._table_components.insertRow(row)
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table_components.setItem(row, col, item)
            rep = records[indices[0]]
            status_item = QTableWidgetItem()
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            status_item.setIcon(self._status_icon(rep.checked))
            self._table_components.setItem(row, len(values), status_item)
            self._component_index.append(indices[0])
            self._group_rows.append(indices)

    def _on_group_mpn_toggled(self, checked: bool) -> None:
        self._group_by_mpn = bool(checked)
        self._selected_marker_index = -1
        self._selected_marker_indices = set()
        self._apply_layer()

    def set_selected(self, index: int) -> None:
        """Show one record as the selected one.

        The viewer is asked to select a record from outside, for instance
        when a difference of the engineering change list is located in the
        picture.
        """
        self._selected_marker_index = int(index)
        self._selected_marker_indices = {int(index)}
        self._apply_layer()

    def set_selected_indices(self, indices) -> None:
        """Show several records as the selected ones."""
        self._selected_marker_indices = {int(i) for i in indices}
        self._selected_marker_index = -1
        self._apply_layer()

    def refresh_records(self, records: List[ReviewRecord]) -> None:
        self._records = records
        layer_count = len(self._current_layer_records())
        if self._selected_marker_index >= layer_count:
            self._selected_marker_index = -1
        self._selected_marker_indices = {
            i for i in self._selected_marker_indices if i < layer_count
        }
        self._apply_layer()
        if getattr(self, "_loaded", False):
            self._rebuild_marker_overlay()

    def _current_layer_records(self) -> List[ReviewRecord]:
        layer = "top" if self._combo_layer.currentIndex() == 0 else "bottom"
        return [r for r in self._records if _layer_key(r.layer) == layer]

    def _restore_highlight(self) -> None:
        overlay = getattr(self, "_overlay", None)
        if overlay is not None:
            overlay.set_selected_indices(self._selected_marker_indices)

    def _checked_layer_indices(self) -> set:
        return {
            i for i, r in enumerate(self._current_layer_records()) if r.checked
        }

    def _record_index_in_records(self, record: ReviewRecord) -> int:
        for i, r in enumerate(self._records):
            if r is record:
                return i
        return -1

    def _component_info_text(self, record: ReviewRecord) -> str:
        """The information of a component, in the coordinates of the file."""
        x, y, rotation = _record_coord(record)
        return tr(
            "Designator: {des}\nMPN: {mpn}\n"
            "X: {x:.3f}  Y: {y:.3f}  Rot: {rot:.0f}\nRemark: {remark}",
            des=record.designator or "-",
            mpn=record.mpn or "-",
            x=x, y=y, rot=rotation,
            remark=record.remark or "-",
        )

    @staticmethod
    def _status_icon(checked: bool) -> QIcon:
        return status_icon(checked)

    def _refresh_component_status(self) -> None:
        layer = self._current_layer_records()
        col = self._table_components.columnCount() - 1
        for row, idx in enumerate(self._component_index):
            if not (0 <= idx < len(layer)):
                continue
            item = self._table_components.item(row, col)
            if item is not None:
                item.setIcon(self._status_icon(layer[idx].checked))

    def _refresh_component_status_row(self, layer_idx: int) -> None:
        layer = self._current_layer_records()
        col = self._table_components.columnCount() - 1
        for row, idx in enumerate(self._component_index):
            in_group = (
                self._group_by_mpn
                and row < len(self._group_rows)
                and layer_idx in self._group_rows[row]
            )
            if idx == layer_idx or in_group:
                item = self._table_components.item(row, col)
                if item is not None and 0 <= idx < len(layer):
                    item.setIcon(self._status_icon(layer[idx].checked))
                return
        self._refresh_component_status()

    def _set_component_status_cell(self, row: int, checked: bool) -> None:
        col = self._table_components.columnCount() - 1
        item = self._table_components.item(row, col)
        if item is not None:
            item.setIcon(self._status_icon(checked))

    def _export_layers(self) -> List[ExportLayer]:
        """The layers that are on the screen, from the bottom to the top."""
        layers: List[ExportLayer] = []
        for index, item in enumerate(self._layer_items):
            if item is None:
                continue
            if index < len(self._layer_states) \
                    and self._layer_states[index] == LAYER_STATE_HIDDEN:
                continue
            try:
                if not item.isVisible():
                    continue
                paths = item._paths
                colour = QColor("#000000")
            except RuntimeError:
                continue
            layers.append(ExportLayer(paths, colour))
        return layers

    def _on_export_image(self) -> None:
        """Write the picture of the visible layers to a file."""
        if not self._loaded:
            return
        layers = self._export_layers()
        if not layers:
            QMessageBox.information(self, tr("Export image..."),
                                    tr("There is no layer to export."))
            return
        path, _selected = QFileDialog.getSaveFileName(
            self, tr("Export image..."), "",
            tr("PNG image (*.png);;PDF document (*.pdf);;SVG picture (*.svg)"))
        if not path:
            return
        suffix = os.path.splitext(path)[1].lower()
        fmt = {".png": "png", ".pdf": "pdf", ".svg": "svg"}.get(suffix)
        if fmt is None:
            QMessageBox.warning(self, tr("Export image..."),
                                tr("The file name must end with .png, .pdf or .svg."))
            return
        try:
            export_layers(layers, path, fmt, background="#FFFFFF")
        except Exception as exc:  # noqa: BLE001 - shown to the user
            QMessageBox.critical(self, tr("Export image..."),
                                 tr("Export failed: {error}").format(error=exc))
            return
        self.status_message.emit(tr("Image exported to {path}").format(path=path))

    def _on_cursor_moved(self, x: float, y: float) -> None:
        self._pending_hover_pos = (x, y)
        if not self._hover_throttle_timer.isActive():
            self._hover_throttle_timer.start()

    def _process_throttled_hover(self) -> None:
        if self._pending_hover_pos is None:
            return
        x, y = self._pending_hover_pos
        self._update_magnifier(x, y)
        self._update_coord_label(x, y)

    def _update_coord_label(self, x: float, y: float) -> None:
        if not self._loaded:
            return
        # The coordinates of the file; the turn of the page is a turn of
        # the drawing only, so they are read without it.
        fx, fy = x, -y
        # The coordinates are counted from the origin that is set now, so
        # they are the ones the component table shows.
        gx = fx - self._origin_x
        gy = fy - self._origin_y
        aperture = self._aperture_at(x, y)
        if aperture:
            self._lbl_coord.setText(tr(
                "X: {gx:.2f}  Y: {gy:.2f}  ({fx:.2f} / {fy:.2f})  |  {ap}",
                gx=gx, gy=gy, fx=fx, fy=fy, ap=aperture))
            return
        self._lbl_coord.setText(tr(
            "X: {gx:.2f}  Y: {gy:.2f}  ({fx:.2f} / {fy:.2f})",
            gx=gx, gy=gy, fx=fx, fy=fy))

    def _aperture_at(self, x: float, y: float) -> str:
        """The aperture of the shape under the pointer, as text.

        The layers are asked from the last to the first, so that a pad of
        a layer that lies on top wins over the outline behind it.
        """
        best_text = ""
        best_distance = None
        for index in sorted(self._aperture_indices.keys(), reverse=True):
            aperture_index = self._aperture_indices[index]
            try:
                fx, fy = aperture_index.to_file(x, y)
                picked = aperture_index.pick(fx, fy)
            except RuntimeError:
                continue
            if picked is None:
                continue
            if best_distance is not None and picked.distance > best_distance:
                continue
            best_distance = picked.distance
            best_text = self._describe_aperture(index, picked)
        return best_text

    def _describe_aperture(self, index: int, picked) -> str:
        """The text of the aperture of one picked shape."""
        data = self._layer_data[index] if index < len(self._layer_data) else None
        info = data.apertures.get(picked.dcode) if data is not None else None
        if info is not None:
            text = info.describe()
        elif picked.dcode:
            text = "D%d" % picked.dcode
        else:
            return ""
        if info is not None and info.attributes:
            extra = ", ".join(
                "%s=%s" % (name, value) for name, value in info.attributes.items())
            if extra:
                text = "%s  (%s)" % (text, extra)
        return text

    def _clear_coord_label(self) -> None:
        if self._hover_throttle_timer.isActive():
            self._hover_throttle_timer.stop()
        self._pending_hover_pos = None
        self._lbl_coord.setText(tr("X: --  Y: --"))

    def _goto_coord(self) -> None:
        if not self._loaded:
            return
        gx = self._spin_goto_x.value()
        gy = self._spin_goto_y.value()
        # The fields count from the origin that is set now, in the
        # coordinates of the board.
        sx = self._origin_x + gx
        sy = -(self._origin_y + gy)
        self._goto_pos = (sx, sy)
        self._update_goto_crosshair()
        self._view.centerOn(sx, sy)
        self._update_magnifier(sx, sy)

    def _update_scene_rect(self) -> None:
        """Let the page reach as far as one wants.

        The scene of a graphics view is the area that can be scrolled, so
        without this the view cannot leave the Gerber.  The area is very
        big, so that the page is not held back at the edge of the board;
        the zoom factor still says how far the page can be shrunk.
        """
        self._scene.setSceneRect(
            -SCENE_MARGIN, -SCENE_MARGIN, SCENE_MARGIN * 2.0, SCENE_MARGIN * 2.0)

    def _update_origin_marker(
        self, angle: float, mirror: bool, off_x: float, off_y: float,
        mirror_x: bool,
    ) -> None:
        """Mark the origin the coordinates of the file count from.

        The mark is two diagonals that make an X, of a fixed size, so that
        it can be seen at every zoom.  It follows the turn of the page, so
        it always stands at the origin of the file.
        """
        for item in (self._origin_marker,):
            if item is not None:
                try:
                    self._scene.removeItem(item)
                except RuntimeError:
                    pass
        self._origin_marker = None
        if not self._show_origin or not self._loaded:
            return
        transform = AffineTransform(
            mirror, angle, off_x, off_y,
            self._board_center[0], self._board_center[1], mirror_x)
        # The origin is a point of the board, the same the components and
        # the table are in; it does not follow the turn of the page.
        x = self._origin_x
        y = -self._origin_y
        half = ORIGIN_MARKER_HALF
        path = QPainterPath()
        path.moveTo(x - half, y - half)
        path.lineTo(x + half, y + half)
        path.moveTo(x - half, y + half)
        path.lineTo(x + half, y - half)
        pen = QPen(ORIGIN_COLOR, 2.0)
        pen.setCosmetic(True)
        self._origin_marker = self._scene.addPath(path, pen)
        # Above the layers, the active one lies at 1000.
        self._origin_marker.setZValue(Z_ORIGIN_MARK)

    def _set_origin(self, gx: float, gy: float) -> None:
        """Put the origin of the coordinates at a point of the file."""
        self._origin_x = float(gx)
        self._origin_y = float(gy)
        self._origin_mode = False
        self._view.set_origin_mode(False)
        self._btn_set_origin.setChecked(False)
        # The table and the overlay keep the coordinates of the file, so
        # only the drawing has to be redone.
        self._redraw()
        self._emit_layer_settings()

    def _on_set_origin_clicked(self, checked: bool) -> None:
        """Choose a new origin by clicking on the board."""
        if not self._loaded and checked:
            self._btn_set_origin.blockSignals(True)
            self._btn_set_origin.setChecked(False)
            self._btn_set_origin.blockSignals(False)
            return
        self._origin_mode = bool(checked)
        if self._origin_mode:
            self._lbl_status.setText(
                tr("Origin mode: click the new origin on the board."))
            self._view.set_origin_mode(True)
            self._view.setFocus(Qt.MouseFocusReason)
        else:
            self._view.set_origin_mode(False)

    def _on_origin_picked(self, sx: float, sy: float) -> None:
        """The operator chose a new origin by clicking on the board.

        The point is taken in the coordinates of the board, the same the
        components and the table are in, so that the point that was
        clicked reads 0,00 from then on.
        """
        if not self._loaded:
            return
        self._set_origin(sx, -sy)
        self._lbl_status.setText(
            tr("Origin set at {x:.2f}, {y:.2f}.", x=sx, y=-sy))

    def _on_origin_from_fields(self) -> None:
        """Move the origin by the X and Y that are written in the footer.

        The fields count from the origin that is set now, so the origin
        moves by that much: the point that was written reads 0,00 then.
        """
        if not self._loaded:
            return
        dx = self._spin_goto_x.value()
        dy = self._spin_goto_y.value()
        gx = self._origin_x + dx
        gy = self._origin_y + dy
        self._set_origin(gx, gy)
        self._lbl_status.setText(
            tr("Origin set at {x:.2f}, {y:.2f}.", x=gx, y=gy))

    def _on_origin_toggled(self, checked: bool) -> None:
        """The mark of the origin is shown, or taken away."""
        self._show_origin = bool(checked)
        self._redraw()
        self._emit_layer_settings()

    def _update_goto_crosshair(self) -> None:
        if self._goto_crosshair is not None:
            try:
                self._scene.removeItem(self._goto_crosshair)
            except RuntimeError:
                pass
            self._goto_crosshair = None
        if self._goto_pos is None or not self._loaded:
            return
        gx, gy = self._goto_pos
        half = self._cross_half * self._crosshair_scale
        if half <= 0:
            half = 0.5
        path = QPainterPath()
        path.moveTo(gx - half, gy)
        path.lineTo(gx + half, gy)
        path.moveTo(gx, gy - half)
        path.lineTo(gx, gy + half)
        pen = QPen(self._colors["highlight"], 2.0)
        pen.setCosmetic(True)
        self._goto_crosshair = self._scene.addPath(path, pen)
        self._goto_crosshair.setZValue(Z_GOTO_CROSS)

    def _on_grid_toggled(self, checked: bool) -> None:
        if checked and not self._grid_available:
            self._chk_grid.setChecked(False)
            return
        self._grid_active = checked
        self._view._grid_active = checked
        self._view.setDragMode(QGraphicsView.NoDrag)
        if not checked:
            self._mag_cell_rect = None
        self._update_grid()

    def _on_grid_params_changed(self) -> None:
        if not self._grid_active or not self._grid_available:
            return
        self._update_grid()

    def _on_grid_style_changed(self) -> None:
        self._grid_opacity = self._spin_grid_opacity.value()
        self._grid_width = self._spin_grid_width.value()
        self._update_grid()

    def _update_grid(self) -> None:
        if self._grid_item is not None:
            try:
                self._scene.removeItem(self._grid_item)
            except RuntimeError:
                pass
            self._grid_item = None
        self._grid_rect = None
        if not self._grid_active or not self._loaded:
            return
        rect = self._gerber_scene_rect()
        if rect.isEmpty() or rect.isNull() or not rect.isValid():
            return
        cols = max(1, self._spin_grid_cols.value())
        rows = max(1, self._spin_grid_rows.value())
        path = QPainterPath()
        for i in range(cols + 1):
            x = rect.left() + rect.width() * i / cols
            path.moveTo(x, rect.top())
            path.lineTo(x, rect.bottom())
        for j in range(rows + 1):
            y = rect.top() + rect.height() * j / rows
            path.moveTo(rect.left(), y)
            path.lineTo(rect.right(), y)
        color = QColor(GRID_COLOR)
        color.setAlpha(self._grid_opacity)
        pen = QPen(color)
        pen.setCosmetic(True)
        pen.setStyle(Qt.DashLine)
        pen.setWidthF(self._grid_width)
        self._grid_item = self._scene.addPath(path, pen)
        self._grid_item.setZValue(Z_GRID)
        self._grid_rect = rect

    def _on_grid_cell_clicked(self, x: float, y: float) -> None:
        if not self._grid_active or not self._loaded:
            return
        rect = self._grid_rect
        if rect is None or rect.isEmpty():
            return
        cols = max(1, self._spin_grid_cols.value())
        rows = max(1, self._spin_grid_rows.value())
        cw = rect.width() / cols
        ch = rect.height() / rows
        col = int((x - rect.left()) / cw) if cw > 0 else 0
        row = int((y - rect.top()) / ch) if ch > 0 else 0
        col = max(0, min(cols - 1, col))
        row = max(0, min(rows - 1, row))
        cell = QRectF(
            rect.left() + col * cw, rect.top() + row * ch,
            cw, ch,
        )
        self._mag_cell_rect = cell
        self._mag_target = (cell.center().x(), cell.center().y())
        self._refresh_magnifier()
        self._update_coord_label(x, y)

    def _on_mag_clicked(self, sx: float, sy: float) -> None:
        if not self._grid_active or not self._loaded:
            return
        records = self._current_layer_records()
        if not records:
            return
        grid = self._pad_grid(self._combo_layer.currentIndex() == 0)
        best = -1
        best_d = float("inf")
        outer = max(self._cross_half * self._crosshair_scale, 0.25)
        outer_d = outer * outer
        for i, record in enumerate(records):
            x, y, _rot = _record_coord(record)
            dx = sx - x
            dy = sy + y
            d2 = dx * dx + dy * dy
            if d2 > outer_d:
                continue
            size = grid.nearest(x, y)
            half = _crosshair_half(size, self._cross_half) * self._crosshair_scale
            tol = max(half, 0.25)
            if d2 <= tol * tol and d2 < best_d:
                best_d = d2
                best = i
        if best < 0:
            return
        record = records[best]
        info = self._component_info_text(record)
        if record.checked:
            ret = QMessageBox.question(
                self, tr("Confirm"),
                tr("Cancel the check for this component?") + "\n\n" + info,
            )
            if ret != QMessageBox.Yes:
                return
            record.checked = False
        else:
            ret = QMessageBox.question(
                self, tr("Confirm"),
                tr("Confirm component exists?") + "\n\n" + info,
            )
            if ret != QMessageBox.Yes:
                return
            record.checked = True
        if self._overlay is not None:
            self._overlay.set_checked_indices(self._checked_layer_indices())
        self._refresh_component_status_row(best)
        self.checked_changed.emit(self._record_index_in_records(record))

    def _on_crosshair_right_clicked(self, sx: float, sy: float) -> None:
        if not self._loaded:
            return
        records = self._current_layer_records()
        if not records:
            return
        # The markers stand in the coordinates of the board, so they are
        # looked up where they are drawn.
        markers = self._marker_tuples()
        best = -1
        best_d = float("inf")
        outer = max(self._cross_half * self._crosshair_scale, 0.25)
        outer_d = outer * outer
        for i, marker in enumerate(markers):
            if i >= len(records):
                break
            mx, my, _rotation, half = marker
            dx = sx - mx
            dy = sy - my
            d2 = dx * dx + dy * dy
            if d2 > outer_d:
                continue
            tol = max(half, 0.25)
            if d2 <= tol * tol and d2 < best_d:
                best_d = d2
                best = i
        if best < 0:
            return
        record = records[best]
        info = self._component_info_text(record)
        menu = QMenu(self)
        act_checked = menu.addAction(tr("Checked"))
        act_checked.setCheckable(True)
        act_checked.setChecked(record.checked)
        chosen = menu.exec(QCursor.pos())
        if chosen != act_checked:
            return
        if record.checked:
            ret = QMessageBox.question(
                self, tr("Confirm"),
                tr("Cancel the check for this component?") + "\n\n" + info,
            )
            if ret != QMessageBox.Yes:
                return
            record.checked = False
        else:
            ret = QMessageBox.question(
                self, tr("Confirm"),
                tr("Confirm component exists?") + "\n\n" + info,
            )
            if ret != QMessageBox.Yes:
                return
            record.checked = True
        if self._overlay is not None:
            self._overlay.set_checked_indices(self._checked_layer_indices())
        self._refresh_component_status_row(best)
        self.checked_changed.emit(self._record_index_in_records(record))

    def _display_transform(self) -> Tuple[float, bool, bool, float, float]:
        return (
            float(self._rotation),
            self._chk_flip.isChecked(),
            self._chk_mirror_x.isChecked(),
            0.0,
            0.0,
        )

    def _scene_to_gerber(self, sx: float, sy: float) -> Tuple[float, float]:
        angle, mirror, mirror_x, off_x, off_y = self._display_transform()
        cx, cy = self._board_center
        return apply_inverse_transform(
            sx, -sy, mirror, angle, off_x, off_y, cx, cy, mirror_x,
        )

    def _gerber_to_scene(self, gx: float, gy: float) -> Tuple[float, float]:
        angle, mirror, mirror_x, off_x, off_y = self._display_transform()
        cx, cy = self._board_center
        tx, ty = apply_transform(gx, gy, mirror, angle, off_x, off_y, cx, cy, mirror_x)
        return tx, -ty

    # ------------------------------------------------------------------
    # Align to pad: shift every component of one side by the offset
    # between the selected component and a clicked pad centre.
    # ------------------------------------------------------------------

    def _selected_ref_record(self) -> Optional[ReviewRecord]:
        records = self._current_layer_records()
        idx = self._selected_marker_index
        if 0 <= idx < len(records):
            return records[idx]
        return None

    def _on_align_pad_toggled(self, checked: bool) -> None:
        if not self._loaded and checked:
            self._btn_align_pad.blockSignals(True)
            self._btn_align_pad.setChecked(False)
            self._btn_align_pad.blockSignals(False)
            return
        if not checked:
            self._align_pad_mode = False
            self._view.set_align_pad_mode(False)
            self._remove_align_snap()
            self._lbl_status.setText(tr("Align to pad cancelled."))
            return
        ref = self._selected_ref_record()
        if ref is None:
            self._btn_align_pad.blockSignals(True)
            self._btn_align_pad.setChecked(False)
            self._btn_align_pad.blockSignals(False)
            self._lbl_status.setText(
                tr("Align to pad: select a component first."))
            return
        # Mutually exclusive with the other click modes.
        if self._measure_mode:
            self._btn_measure.setChecked(False)
        if self._origin_mode:
            self._btn_set_origin.setChecked(False)
        if self._grid_active:
            self._chk_grid.setChecked(False)
        self._align_pad_mode = True
        self._view.set_align_pad_mode(True)
        self._view.setFocus(Qt.MouseFocusReason)
        designator = ref.designator or tr("(no designator)")
        side = tr("top") if self._combo_layer.currentIndex() == 0 \
            else tr("bottom")
        if self._pad_grid(self._combo_layer.currentIndex() == 0).is_empty():
            self._lbl_status.setText(tr(
                "Align to pad: no pads on the {side} side — clicks will "
                "use raw coordinates.", side=side))
        else:
            self._lbl_status.setText(tr(
                "Align to pad: click the true pad centre of {des} "
                "(Ctrl = raw click).", des=designator))

    def _on_align_pad_cancel(self) -> None:
        if not self._align_pad_mode:
            return
        self._align_pad_mode = False
        self._btn_align_pad.blockSignals(True)
        self._btn_align_pad.setChecked(False)
        self._btn_align_pad.blockSignals(False)
        self._view.set_align_pad_mode(False)
        self._remove_align_snap()
        self._lbl_status.setText(tr("Align to pad cancelled."))
        self.status_message.emit(tr("Align to pad cancelled."))

    def _exit_align_pad_mode_silently(self) -> None:
        if not self._align_pad_mode:
            return
        self._align_pad_mode = False
        self._btn_align_pad.blockSignals(True)
        self._btn_align_pad.setChecked(False)
        self._btn_align_pad.blockSignals(False)
        self._view.set_align_pad_mode(False)
        self._remove_align_snap()

    def _on_align_move(self, sx: float, sy: float) -> None:
        """Live snap preview and offset read-out while hovering."""
        if not self._align_pad_mode:
            return
        ref = self._selected_ref_record()
        if ref is None:
            return
        bypass = self._measure_ctrl_bypass()
        gx, gy = self._scene_to_gerber(sx, sy)
        snap_active = not bypass
        pad_size: Optional[float] = None
        if snap_active:
            info = self._snap_info(gx, gy, force=True)
            if info is not None:
                px, py, pad_size = info
                tol = max(getattr(self, "_snap_tol", 1.0), pad_size)
                if math.hypot(px - gx, py - gy) <= tol:
                    gx, gy = px, py
                else:
                    pad_size = None
        ssx, ssy = self._gerber_to_scene(gx, gy)
        if pad_size is not None:
            self._update_align_snap(ssx, ssy, pad_size)
        else:
            self._remove_align_snap()
        bx = ssx - self._origin_x
        by = -ssy - self._origin_y
        rx, ry, _rot = _record_coord(ref)
        designator = ref.designator or tr("(no designator)")
        if pad_size is not None:
            self._lbl_status.setText(tr(
                "Align to pad: {des} | ΔX: {dx:+.4f} mm | "
                "ΔY: {dy:+.4f} mm (snap)",
                des=designator, dx=bx - rx, dy=by - ry))
        else:
            self._lbl_status.setText(tr(
                "Align to pad: {des} | ΔX: {dx:+.4f} mm | "
                "ΔY: {dy:+.4f} mm (raw)",
                des=designator, dx=bx - rx, dy=by - ry))

    def _update_align_snap(self, sx: float, sy: float,
                           pad_size: float) -> None:
        if self._align_snap_item is None:
            pen = QPen(MEASURE_COLOR, 1.2)
            pen.setCosmetic(True)
            brush = QBrush(QColor(MEASURE_COLOR.red(), MEASURE_COLOR.green(),
                                  MEASURE_COLOR.blue(), 50))
            self._align_snap_item = self._scene.addEllipse(
                0.0, 0.0, 1.0, 1.0, pen, brush)
            self._align_snap_item.setZValue(Z_MEASURE)
        r = max(getattr(self, "_snap_tol", 1.0), pad_size)
        self._align_snap_item.setRect(sx - r, sy - r, 2.0 * r, 2.0 * r)

    def _remove_align_snap(self) -> None:
        if self._align_snap_item is not None:
            try:
                self._scene.removeItem(self._align_snap_item)
            except RuntimeError:
                pass
            self._align_snap_item = None

    def _on_align_pad_clicked(self, sx: float, sy: float) -> None:
        if not self._loaded or not self._align_pad_mode:
            return
        ref = self._selected_ref_record()
        if ref is None:
            self.status_message.emit(tr("Align to pad: no component selected."))
            self._exit_align_pad_mode_silently()
            return
        bypass = self._measure_ctrl_bypass()
        gx, gy = self._scene_to_gerber(sx, sy)
        snap_active = not bypass
        snapped = not snap_active
        if snap_active:
            hit = self._snap_info(gx, gy, force=True)
            if hit is not None:
                px, py, pad_size = hit
                tol = max(getattr(self, "_snap_tol", 1.0), pad_size)
                if math.hypot(px - gx, py - gy) <= tol:
                    gx, gy = px, py
                    snapped = True
        # The pad centre snaps in the frame of the file; bring it back
        # the same way the markers were put on the scene, so the offset
        # lands in the frame the coordinates of the components count in.
        bsx, bsy = self._gerber_to_scene(gx, gy)
        bx = bsx - self._origin_x
        by = -bsy - self._origin_y
        self._exit_align_pad_mode_silently()
        # Leave the mouse-press context first: modal dialogs and the busy
        # progress freeze the native event loop on macOS when opened while
        # a mouse press is still being dispatched.
        QTimer.singleShot(
            0, lambda ref=ref, bx=bx, by=by, snapped=snapped:
            self._apply_align_delta(ref, bx, by, snapped))

    def _apply_align_delta(
            self, ref: ReviewRecord, bx: float, by: float, snapped: bool,
    ) -> None:
        """Shift every component of the reference side by one offset."""
        dx, dy = _record_coord(ref)[0], _record_coord(ref)[1]
        dx = round(bx - dx, 4)
        dy = round(by - dy, 4)
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            self._lbl_status.setText(tr("Align to pad: already aligned."))
            self.status_message.emit(tr("Align to pad: already aligned."))
            return

        targets = self._current_layer_records()
        side = "top" if self._combo_layer.currentIndex() == 0 else "bottom"
        warning = ""
        if not snapped:
            warning = "\n\n" + tr(
                "Warning: no pad found near the clicked point; "
                "the raw coordinates are used.")
        ret = QMessageBox.question(
            self, tr("Confirm"),
            tr("Move every {side}-side component by the offset of {des}?\n\n"
               "Offset X: {dx:+.4f} mm\nOffset Y: {dy:+.4f} mm\n"
               "Components to move: {n}{warn}",
               side=tr("top") if side == "top" else tr("bottom"),
               des=ref.designator or tr("(no designator)"),
               dx=dx, dy=dy, n=len(targets), warn=warning),
        )
        if ret != QMessageBox.Yes:
            self._lbl_status.setText(tr("Align to pad cancelled."))
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        changed: List[ReviewRecord] = []
        progress = QProgressDialog(
            tr("Aligning components..."), "", 0, len(targets), self)
        progress.setWindowTitle(tr("Please wait"))
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        for count, record in enumerate(targets, start=1):
            base_x = (record.new_x
                      if record.new_x is not None else record.old_x)
            base_y = (record.new_y
                      if record.new_y is not None else record.old_y)
            base_rot = (record.new_rotation
                        if record.new_rotation is not None
                        else record.old_rotation)
            record._align_old = (base_x, base_y, base_rot, record.remark)
            record.new_x = round(base_x + dx, 4)
            record.new_y = round(base_y + dy, 4)
            record.status = "Aligned"
            record.review_time = timestamp
            changed.append(record)
            progress.setValue(count)
            QApplication.processEvents()

        # The redraw of a big board is the heavy part of the job; the
        # busy dialog stays open so the wait is seen as a progress, not
        # as a frozen app.  The bar is full by now, so switch the dialog
        # to an endless busy marker for the redraw.
        progress.setRange(0, 0)
        progress.setLabelText(tr("Redrawing view..."))
        QApplication.processEvents()
        self._apply_layer()
        self._redraw()
        self._fit_scene()
        self._rebuild_marker_overlay()
        progress.close()
        if changed:
            indices = [self._record_index_in_records(record)
                       for record in changed]
            self.align_edited.emit(indices)
            self._lbl_status.setText(tr(
                "Aligned {n} components by ({dx:+.4f}, {dy:+.4f}) mm.",
                n=len(changed), dx=dx, dy=dy))
            self.status_message.emit(tr(
                "Aligned {n} {side} components.",
                n=len(changed),
                side=tr("top") if side == "top" else tr("bottom")))

    # ------------------------------------------------------------------
    # Trace pad: light the copper that hangs on one clicked pad.
    # ------------------------------------------------------------------

    def _copper_candidates(self) -> List[Tuple[int, RenderData]]:
        """The copper layers of the current side, in the order of the list."""
        side = SIDE_TOP if self._combo_layer.currentIndex() == 0 \
            else SIDE_BOTTOM
        out: List[Tuple[int, RenderData]] = []
        for index, (layer, data) in enumerate(
                zip(self._layers, self._layer_data)):
            if layer.role != ROLE_COPPER:
                continue
            if layer.side and layer.side != side:
                continue
            if data.flashes or data.arcs or len(data.lines):
                out.append((index, data))
        return out

    def _trace_index_for(self, layer_index: int,
                         data: RenderData) -> Any:
        """The trace index of one layer, built once and kept."""
        index = self._trace_indices.get(layer_index)
        if index is None:
            index = build_index(data)
            self._trace_indices[layer_index] = index
        return index

    def _pad_designator(self, gx: float, gy: float) -> str:
        """The designator of the pad that sits at a place of the file."""
        best = None
        best_d = float("inf")
        for record in self._current_layer_records():
            rx, ry, _rotation = _record_coord(record)
            d = math.hypot(rx - gx, ry - gy)
            if d < best_d:
                best_d = d
                best = record
        tol = max(getattr(self, "_snap_tol", 1.0), 1.0)
        if best is not None and best_d <= tol:
            return best.designator or tr("(no designator)")
        return f"X{gx:.2f} Y{gy:.2f}"

    def _pad_name_list(self, data: RenderData, flashes: List[int],
                       origin: Tuple[float, float] = (0.0, 0.0)) -> str:
        """The designators of the pads of a net, near the seed pad first."""
        ordered = []
        for i in flashes:
            fl = data.flashes[i]
            d = math.hypot(fl.cx - origin[0], fl.cy - origin[1])
            ordered.append((d, fl, i))
        ordered.sort(key=lambda entry: entry[0])
        names: List[str] = []
        seen_flash = set()
        chosen_flash = []
        for _d, _fl, i in ordered:
            if i in seen_flash:
                continue
            seen_flash.add(i)
            name = self._pad_designator(_fl.cx, _fl.cy)
            if name in names:
                continue
            names.append(name)
            chosen_flash.append(i)
        shown = names[:8]
        rest = len(names) - len(shown)
        text = ", ".join(shown)
        if rest > 0:
            text += tr(", and {n} more pads", n=rest)
        del chosen_flash
        return text or tr("(no pads)")

    def _on_trace_toggled(self, checked: bool) -> None:
        if not self._loaded and checked:
            self._btn_trace.blockSignals(True)
            self._btn_trace.setChecked(False)
            self._btn_trace.blockSignals(False)
            return
        if not checked:
            self._trace_mode = False
            self._view.set_trace_mode(False)
            self._clear_trace_result()
            self._lbl_status.setText(tr("Trace pad cancelled."))
            return
        # Mutually exclusive with the other click modes.
        if self._measure_mode:
            self._btn_measure.setChecked(False)
        if self._origin_mode:
            self._btn_set_origin.setChecked(False)
        if self._align_pad_mode:
            self._btn_align_pad.setChecked(False)
        if self._grid_active:
            self._chk_grid.setChecked(False)
        self._trace_mode = True
        self._view.set_trace_mode(True)
        self._view.setFocus(Qt.MouseFocusReason)
        self._lbl_status.setText(tr(
            "Trace pad: click a pad of the copper layer (Esc = exit)."))

    def _on_trace_cancel(self) -> None:
        if not self._trace_mode:
            return
        self._trace_mode = False
        self._btn_trace.blockSignals(True)
        self._btn_trace.setChecked(False)
        self._btn_trace.blockSignals(False)
        self._view.set_trace_mode(False)
        self._clear_trace_result()
        self._lbl_status.setText(tr("Trace pad cancelled."))
        self.status_message.emit(tr("Trace pad cancelled."))

    def _restore_trace_overlay(self) -> None:
        """Rebuild the traced net after the scene was rebuilt."""
        active = self._active_trace
        if active is None:
            return
        layer_index, data, component, origin = active
        previous = self._lbl_status.text()
        self._show_trace_result(
            layer_index, data, component,
            self._layers[layer_index].name, origin)
        self._lbl_status.setText(previous)

    def _hide_trace_popup(self) -> None:
        if self._trace_popup_timer is not None:
            self._trace_popup_timer.stop()
        if self._trace_popup is not None:
            self._trace_popup.hide()

    def _show_trace_popup(
        self, title: str, subtitle: str, screen_pos: Optional[QPoint] = None,
    ) -> None:
        """Show a small tooltip popup at/near the mouse cursor."""
        viewport = self._view.viewport()
        if self._trace_popup is None:
            self._trace_popup = QLabel(viewport)
            self._trace_popup.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._trace_popup.setStyleSheet(
                "QLabel {"
                "  background-color: #0F172A;"
                "  border: 1.5px solid #FFD60A;"
                "  border-radius: 6px;"
                "  color: #F8FAFC;"
                "  padding: 4px 8px;"
                "  font-size: 11px;"
                "}"
            )
            self._trace_popup_timer = QTimer(self)
            self._trace_popup_timer.setSingleShot(True)
            self._trace_popup_timer.timeout.connect(self._hide_trace_popup)

        text = (
            f"<div style='font-weight: bold; color: #FFD60A;'>{title}</div>"
            f"<div style='font-size: 10px; color: #E2E8F0;'>{subtitle}</div>"
        )
        self._trace_popup.setText(text)
        self._trace_popup.adjustSize()

        if screen_pos is not None:
            local_pt = viewport.mapFromGlobal(screen_pos)
        else:
            local_pt = viewport.mapFromGlobal(QCursor.pos())

        # Offset 12px right/down to avoid obscuring the pad
        target_x = local_pt.x() + 12
        target_y = local_pt.y() + 12

        pw = self._trace_popup.width()
        ph = self._trace_popup.height()
        vw = viewport.width()
        vh = viewport.height()

        # Clamp/flip so popup stays entirely within viewport
        if target_x + pw > vw - 6:
            target_x = max(6, local_pt.x() - pw - 12)
        if target_y + ph > vh - 6:
            target_y = max(6, local_pt.y() - ph - 12)

        self._trace_popup.move(max(6, target_x), max(6, target_y))
        self._trace_popup.show()
        self._trace_popup.raise_()
        self._trace_popup_timer.start(3000)

    def _clear_trace_result(self) -> None:
        self._hide_trace_popup()
        self._active_trace = None
        self._trace_first = None
        self._trace_candidates = None
        self._trace_last_pick = None
        for name in ("_trace_line_item", "_trace_fill_item", "_trace_plane_outline_item"):
            item = getattr(self, name, None)
            if item is None:
                continue
            try:
                self._scene.removeItem(item)
            except RuntimeError:
                pass
            setattr(self, name, None)

    def _trace_line_itemize(
        self, data: RenderData, component: Any,
        angle: float, mirror: bool, mirror_x: bool,
    ) -> QGraphicsPathItem:
        """The wires of the net, drawn as one bright chain of lines.

        Every wire keeps the line the way it lies, seen in the scene; the
        width of the pen is one working value, big enough to be seen at a
        distance, small enough to keep the nearest wires apart.
        """
        path = QPainterPath()
        from services.gerber.trace_net import _arc_chords
        for i in component.strokes:
            ln = data.lines[i]
            x1, y1 = self._gerber_to_scene(ln.x1, ln.y1)
            x2, y2 = self._gerber_to_scene(ln.x2, ln.y2)
            path.moveTo(x1, y1)
            path.lineTo(x2, y2)
        for i in component.arcs:
            ar = data.arcs[i]
            chords = _arc_chords(ar)
            if not chords:
                continue
            first = True
            for x1, y1, x2, y2, _width in chords:
                sx1, sy1 = self._gerber_to_scene(x1, y1)
                sx2, sy2 = self._gerber_to_scene(x2, y2)
                if first:
                    path.moveTo(sx1, sy1)
                    first = False
                path.lineTo(sx2, sy2)
        pen = QPen(TRACE_COLOR, _TRACE_LINE_WIDTH)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCosmetic(False)  # The width counts in millimetres.
        item = self._scene.addPath(path, pen)
        item.setZValue(Z_TRACE)
        return item

    def _trace_fill_itemize(
        self, data: RenderData, component: Any,
        angle: float, mirror: bool, mirror_x: bool,
        off_x: float, off_y: float,
    ) -> QGraphicsPathItem:
        """The pads of the net, filled in the true shape of the aperture.

        The pads take the colour of the wires, so one net looks like one
        piece of copper.  Only true copper planes/pours are left unfilled
        so they do not paint half the board; small polygon pads are filled.
        For planes, their boundary outline is drawn with a dashed pen so
        the user can see where the connection reaches.
        """
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        outline_path = QPainterPath()
        center_x, center_y = self._board_center
        for i in component.flashes:
            fl = data.flashes[i]
            if is_copper_plane(data, i):
                _add_flash(outline_path, fl, mirror, angle, off_x, off_y,
                           center_x, center_y, mirror_x)
                continue
            _add_flash(path, fl, mirror, angle, off_x, off_y,
                       center_x, center_y, mirror_x)
        item = self._scene.addPath(path, QPen(Qt.NoPen),
                                   QBrush(TRACE_COLOR))
        item.setZValue(Z_TRACE)
        if not outline_path.isEmpty():
            dash_pen = QPen(TRACE_COLOR, 0.4, Qt.DashLine)
            dash_pen.setCosmetic(True)
            self._trace_plane_outline_item = self._scene.addPath(
                outline_path, dash_pen, QBrush(Qt.NoBrush)
            )
            self._trace_plane_outline_item.setZValue(Z_TRACE)
        return item

    def _show_trace_result(self, layer_index: int, data: RenderData,
                           component: Any, layer_name: str,
                           origin: Tuple[float, float]) -> None:
        """Draw the traced net: its wires in one bright chain and its
        pads in the true shape of the apertures, all in one colour."""
        angle, mirror, mirror_x, off_x, off_y = self._display_transform()
        self._active_trace = (layer_index, data, component, origin)
        self._trace_line_item = self._trace_line_itemize(
            data, component, angle, mirror, mirror_x)
        self._trace_fill_item = self._trace_fill_itemize(
            data, component, angle, mirror, mirror_x, off_x, off_y)
        traces = component.count()
        pad_list = self._pad_name_list(data, component.flashes, origin)
        if getattr(component, "is_path", False):
            self._lbl_status.setText(tr(
                "Trace path ({layer}): {length:.2f} mm | {list}.",
                layer=layer_name, length=getattr(component, "path_length", 0.0), list=pad_list))
        elif getattr(component, "is_plane", False):
            self._lbl_status.setText(tr(
                "Trace pad ({layer}): Pad connects to Copper Plane (GND/Power) — limited view.",
                layer=layer_name))
        else:
            self._lbl_status.setText(tr(
                "Trace pad ({layer}): {n} traces on one net: {list}.",
                layer=layer_name, n=traces, list=pad_list))

    def _on_trace_picked(self, sx: float, sy: float,
                         screen_pos: Optional[QPoint] = None) -> None:
        if not self._loaded or not self._trace_mode:
            return
        # A big ground pour walks thousands of shapes: the wait is told
        # with an hourglass, since the click stays in one handler.
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._trace_picked_inner(sx, sy, screen_pos)
        finally:
            QApplication.restoreOverrideCursor()

    def _trace_picked_inner(self, sx: float, sy: float,
                            screen_pos: Optional[QPoint] = None) -> None:
        gx, gy = self._scene_to_gerber(sx, sy)
        repeat = (
            self._trace_last_pick is not None
            and abs(gx - self._trace_last_pick[0]) <= 0.25
            and abs(gy - self._trace_last_pick[1]) <= 0.25
        )
        tol = max(getattr(self, "_snap_tol", 1.0), 1.0)
        chosen: Optional[Tuple] = None
        if repeat and self._trace_candidates and \
                len(self._trace_candidates) > 1:
            # The pads of the copper layers stand on top of each other;
            # a second click on the same spot traces the next layer.
            self._trace_order = \
                (self._trace_order + 1) % len(self._trace_candidates)
            chosen = self._trace_candidates[self._trace_order]
        else:
            picks = []
            for layer_index, data in self._copper_candidates():
                trace_index = self._trace_index_for(layer_index, data)
                seed = pick_seed(trace_index, gx, gy, tol)
                if seed is None:
                    continue
                kind, seed_index, cx, cy = seed
                picks.append(
                    (math.hypot(cx - gx, cy - gy),
                     (layer_index, data, kind, seed_index, cx, cy)))
            if not picks:
                self._trace_candidates = None
                self._trace_last_pick = None
                self._hide_trace_popup()
                self._lbl_status.setText(tr(
                    "Trace pad: no pad at the clicked point — click a "
                    "copper pad."))
                return
            picks.sort(key=lambda entry: entry[0])
            self._trace_candidates = [choice for _d, choice in picks]
            self._trace_order = 0
            chosen = self._trace_candidates[0]
        self._trace_last_pick = (gx, gy)
        layer_index, data, kind, seed_index, seed_x, seed_y = chosen
        trace_index = self._trace_index_for(layer_index, data)
        component = trace_component(
            data, gx, gy, tol, index=trace_index,
            seed=(kind, seed_index, seed_x, seed_y))
        if component is None:
            self._trace_candidates = None
            self._trace_last_pick = None
            self._hide_trace_popup()
            self._lbl_status.setText(tr(
                "Trace pad: no pad at the clicked point — click a "
                "copper pad."))
            return
        layer_name = self._layers[layer_index].name
        # The pad that names the trace: a pad click names its own pad, a
        # wire click names the nearest pad of the net.
        pad_label: Optional[str] = None
        if kind == "flash":
            pad_label = self._pad_designator(seed_x, seed_y)
        else:
            best_fl = None
            best_d = float("inf")
            for i in component.flashes:
                fl = data.flashes[i]
                d = math.hypot(fl.cx - gx, fl.cy - gy)
                if d < best_d:
                    best_d = d
                    best_fl = fl
            if best_fl is not None:
                pad_label = self._pad_designator(best_fl.cx, best_fl.cy)
        verdict = None
        first = self._trace_first
        current_seed = (kind, seed_index, seed_x, seed_y)

        if first is not None and first[0] is data and kind == "flash":
            if seed_index in first[1].flashes:
                # Find direct shortest path between the first clicked point and this pad
                path_component = find_shortest_path(data, first[3], current_seed, index=trace_index)
                if path_component is not None:
                    component = path_component
                verdict = (True, first[2], pad_label, getattr(component, "path_length", 0.0))
            else:
                verdict = (False, first[2], pad_label, 0.0)

        if verdict is not None and verdict[0]:
            self._show_trace_result(layer_index, data, component, layer_name, (gx, gy))
            length_str = f" ({verdict[3]:.2f} mm)" if verdict[3] > 0 else ""
            self._lbl_status.setText(tr(
                "Trace pad: {a} and {b} are CONNECTED — one net{len}.",
                a=verdict[1], b=verdict[2], len=length_str))
            self._hide_trace_popup()
            return

        def restore_trace_hint() -> None:
            if self._trace_candidates is None or \
                    len(self._trace_candidates) <= 1:
                return
            next_choice = self._trace_candidates[
                (self._trace_order + 1) % len(self._trace_candidates)][0]
            next_name = self._layers[next_choice].name
            self._lbl_status.setText(self._lbl_status.text() + " " + tr(
                "Trace pad: several copper layers carry a pad here — "
                "click again on the same spot to trace {layer}.",
                layer=next_name))

        self._trace_first = (data, component, pad_label or tr("(no pads)"), current_seed)
        self._show_trace_result(layer_index, data, component, layer_name,
                                (gx, gy))
        if getattr(component, "is_plane", False):
            # Show small popup right at the cursor position
            des = pad_label or tr("(no pads)")
            sub = f"{des} · {layer_name}" if des != tr("(no pads)") else f"{layer_name} · limited view"
            self._show_trace_popup("GND/PWR PLANE", sub, screen_pos)
        else:
            self._hide_trace_popup()

        if verdict is not None:
            self._lbl_status.setText(tr(
                "Trace pad: {a} and {b} are NOT connected — different "
                "nets.", a=verdict[1], b=verdict[2]))
        restore_trace_hint()

    def _on_measure_toggled(self, checked: bool) -> None:
        if not self._loaded and checked:
            self._btn_measure.blockSignals(True)
            self._btn_measure.setChecked(False)
            self._btn_measure.blockSignals(False)
            return
        self._measure_mode = bool(checked)
        self._btn_measure.setText(
            tr("Stop measure") if self._measure_mode else tr("Measure"))
        if self._measure_mode:
            if self._grid_active:
                self._chk_grid.setChecked(False)
            self._measure_start = None
            self._remove_measure_preview()
            self._lbl_status.setText(tr("Measure mode: click the start point."))
            self._view.set_measure_mode(True)
            self._view.setFocus(Qt.MouseFocusReason)
        else:
            self._view.set_measure_mode(False)
            self._on_measure_cancel()
            self._clear_measurements()

    def _on_snap_toggled(self, checked: bool) -> None:
        self._snap_enabled = bool(checked)
        btn_snap = getattr(self, "_btn_snap", None)
        chk_snap = getattr(self, "_chk_snap", None)
        if btn_snap is not None and btn_snap.isChecked() != bool(checked):
            btn_snap.blockSignals(True)
            btn_snap.setChecked(bool(checked))
            btn_snap.blockSignals(False)
        if chk_snap is not None and chk_snap.isChecked() != bool(checked):
            chk_snap.blockSignals(True)
            chk_snap.setChecked(bool(checked))
            chk_snap.blockSignals(False)
        if not checked:
            self._remove_measure_snap()

    def _on_snap_tol_changed(self, value: float) -> None:
        self._snap_tol = float(value)

    def _snap_info(self, gx: float, gy: float, force: bool = False) -> Optional[Tuple[float, float, float]]:
        if not force and not getattr(self, "_snap_enabled", True):
            return None
        grid = self._pad_grid(self._combo_layer.currentIndex() == 0)
        return grid.nearest_point(gx, gy, getattr(self, "_snap_tol", 1.0))

    def _snap_gerber(self, gx: float, gy: float) -> Tuple[float, float]:
        hit = self._snap_info(gx, gy)
        if hit is None:
            return gx, gy
        px, py, size = hit
        tol = max(getattr(self, "_snap_tol", 1.0), size)
        if math.hypot(px - gx, py - gy) <= tol:
            return px, py
        return gx, gy

    def _measure_ctrl_bypass(self) -> bool:
        return Qt.ControlModifier in QApplication.keyboardModifiers()

    def _on_measure_clicked(self, sx: float, sy: float) -> None:
        if not self._loaded or not self._measure_mode:
            return
        if self._measure_ctrl_bypass():
            gx, gy = self._scene_to_gerber(sx, sy)
        else:
            gx, gy = self._snap_gerber(*self._scene_to_gerber(sx, sy))
        if self._measure_start is None:
            self._measure_start = (gx, gy)
            self._lbl_status.setText(tr("Measure mode: click the end point."))
        else:
            x1, y1 = self._measure_start
            self._measure_start = None
            self._remove_measure_preview()
            self._add_measurement(x1, y1, gx, gy)

    def _on_measure_cancel(self) -> None:
        self._measure_start = None
        self._remove_measure_preview()
        if self._measure_mode:
            self._lbl_status.setText(tr("Measure mode: click the start point."))

    def _on_measure_move(self, sx: float, sy: float) -> None:
        if not self._measure_mode or self._measure_start is None:
            return
        x1, y1 = self._measure_start
        gx, gy = self._scene_to_gerber(sx, sy)
        size: Optional[float] = None
        if not self._measure_ctrl_bypass():
            hit = self._snap_info(gx, gy)
            if hit is not None:
                px, py, pad_size = hit
                tol = max(getattr(self, "_snap_tol", 1.0), pad_size)
                if math.hypot(px - gx, py - gy) <= tol:
                    gx, gy, size = px, py, pad_size
        dist = math.hypot(gx - x1, gy - y1)
        sx1, sy1 = self._gerber_to_scene(x1, y1)
        sx2, sy2 = self._gerber_to_scene(gx, gy)
        path = QPainterPath()
        path.moveTo(sx1, sy1)
        path.lineTo(sx2, sy2)
        if self._measure_preview is None:
            pen = QPen(MEASURE_COLOR, 1.5)
            pen.setCosmetic(True)
            pen.setStyle(Qt.DashLine)
            self._measure_preview = self._scene.addPath(path, pen)
            self._measure_preview.setZValue(Z_MEASURE)
        else:
            try:
                self._measure_preview.setPath(path)
            except RuntimeError:
                self._measure_preview = None
                return
        if size is not None:
            self._update_measure_snap(sx2, sy2, size)
        else:
            self._remove_measure_snap()
        if self._measure_ctrl_bypass():
            self._lbl_status.setText(
                tr("Distance: {d:.3f} mm (snap off)", d=dist))
        else:
            self._lbl_status.setText(tr("Distance: {d:.3f} mm", d=dist))

    def _update_measure_snap(self, sx: float, sy: float, pad_size: float) -> None:
        if self._measure_snap_item is None:
            pen = QPen(MEASURE_COLOR, 1.2)
            pen.setCosmetic(True)
            brush = QBrush(QColor(MEASURE_COLOR.red(), MEASURE_COLOR.green(),
                                 MEASURE_COLOR.blue(), 50))
            self._measure_snap_item = self._scene.addEllipse(0.0, 0.0, 1.0, 1.0, pen, brush)
            self._measure_snap_item.setZValue(Z_MEASURE)
        r = max(getattr(self, "_snap_tol", 1.0), pad_size)
        self._measure_snap_item.setRect(sx - r, sy - r, 2.0 * r, 2.0 * r)

    def _remove_measure_snap(self) -> None:
        if self._measure_snap_item is not None:
            try:
                self._scene.removeItem(self._measure_snap_item)
            except RuntimeError:
                pass
            self._measure_snap_item = None

    def _remove_measure_preview(self) -> None:
        if self._measure_preview is not None:
            try:
                self._scene.removeItem(self._measure_preview)
            except RuntimeError:
                pass
            self._measure_preview = None
        self._remove_measure_snap()

    def _add_measurement(self, x1: float, y1: float,
                         x2: float, y2: float) -> None:
        sx1, sy1 = self._gerber_to_scene(x1, y1)
        sx2, sy2 = self._gerber_to_scene(x2, y2)
        dist = math.hypot(x2 - x1, y2 - y1)
        item = MeasurementItem(
            QPointF(sx1, sy1), QPointF(sx2, sy2), dist, MEASURE_COLOR,
        )
        self._scene.addItem(item)
        self._measurements.append((x1, y1, x2, y2))
        self._measurement_items.append(item)
        self._lbl_status.setText(tr("Distance: {d:.3f} mm", d=dist))

    def _clear_measurements(self) -> None:
        self._measure_start = None
        self._remove_measure_preview()
        for item in self._measurement_items:
            try:
                self._scene.removeItem(item)
            except RuntimeError:
                pass
        self._measurement_items = []
        self._measurements = []
        if self._measure_mode:
            self._lbl_status.setText(tr("Measure mode: click the start point."))

    def _rebuild_measurements(self) -> None:
        for item in self._measurement_items:
            try:
                self._scene.removeItem(item)
            except RuntimeError:
                pass
        self._measurement_items = []
        for x1, y1, x2, y2 in self._measurements:
            sx1, sy1 = self._gerber_to_scene(x1, y1)
            sx2, sy2 = self._gerber_to_scene(x2, y2)
            item = MeasurementItem(
                QPointF(sx1, sy1), QPointF(sx2, sy2),
                math.hypot(x2 - x1, y2 - y1), MEASURE_COLOR,
            )
            self._scene.addItem(item)
            self._measurement_items.append(item)

    def _update_magnifier(self, x: float, y: float) -> None:
        if not self._loaded:
            return
        # While rotation edit dialog is open, magnifier stays locked on the component
        if self._rotation_lock_xy is not None:
            return
        if self._grid_active:
            return
        if getattr(self._view, "_zoom_active", False):
            return
        if getattr(self._view, "_panning", False):
            return
        self._mag_cell_rect = None
        self._mag_target = (x, y)
        self._refresh_magnifier()

    def _set_mag_factor(self, factor: float) -> None:
        """Set magnification factor, sync combo, and refresh."""
        self._mag_factor = factor
        # Sync combo box without triggering handler loop
        self._combo_mag.blockSignals(True)
        for i in range(self._combo_mag.count()):
            data = self._combo_mag.itemData(i)
            if data is not None and abs(float(data) - factor) < 1e-9:
                self._combo_mag.setCurrentIndex(i)
                break
        self._combo_mag.blockSignals(False)
        self._mag_group.setTitle(tr("Details (Zoom {f:g}x)", f=self._mag_factor))
        if not self._grid_active:
            self._mag_cell_rect = None
        self._refresh_magnifier()

    def _on_mag_factor_changed(self) -> None:
        self._mag_factor = float(self._combo_mag.currentData() or _MAG_FACTOR)
        self._mag_group.setTitle(tr("Details (Zoom {f:g}x)", f=self._mag_factor))
        if not self._grid_active:
            self._mag_cell_rect = None
        self._refresh_magnifier()

    def _refresh_magnifier(self) -> None:
        if not self._loaded or self._mag_target is None:
            return
        vp = self._mag_view.viewport()
        vw = max(vp.width(), 1)
        vh = max(vp.height(), 1)
        x, y = self._mag_target
        # While rotation edit is active, use factor-based zoom on the locked point
        if self._rotation_lock_xy is None and self._mag_cell_rect is not None:
            cell = self._mag_cell_rect
            if cell.width() > 0 and cell.height() > 0:
                sx = vw / cell.width()
                sy = vh / cell.height()
                cx, cy = cell.center().x(), cell.center().y()
                dx = vw / 2.0 - sx * cx
                dy = vh / 2.0 - sy * cy
                self._mag_view.setTransform(QTransform(sx, 0, 0, sy, dx, dy))
                self._mag_view.horizontalScrollBar().setValue(0)
                self._mag_view.verticalScrollBar().setValue(0)
                return
        scale = _magnifier_scale(self._board_size(), vw, vh, self._mag_factor)
        self._mag_view.setTransform(QTransform().fromScale(scale, scale))
        self._mag_view.centerOn(x, y)

    def _on_row_changed(self, current_row: int, _col: int = 0,
                        _prev_row: int = -1, _prev_col: int = -1) -> None:
        if self._group_by_mpn and 0 <= current_row < len(self._group_rows):
            self._selected_marker_indices = set(self._group_rows[current_row])
            self._selected_marker_index = (
                self._component_index[current_row] if self._component_index else -1
            )
        elif 0 <= current_row < len(self._component_index):
            self._selected_marker_index = self._component_index[current_row]
            self._selected_marker_indices = {self._selected_marker_index}
        else:
            self._selected_marker_index = -1
            self._selected_marker_indices = set()
        self._restore_highlight()
        if self._selected_marker_index >= 0:
            records = self._current_layer_records()
            if self._selected_marker_index < len(records):
                mx, my = self._marker_pos(records[self._selected_marker_index])
                self._update_magnifier(mx, my)

    def _on_component_double_clicked(self, row: int, _col: int) -> None:
        if not (0 <= row < len(self._component_index)):
            return
        if self._group_by_mpn:
            self._selected_marker_indices = set(self._group_rows[row])
            self._restore_highlight()
        idx = self._component_index[row]
        records = self._current_layer_records()
        if not (0 <= idx < len(records)):
            return
        mx, my = self._marker_pos(records[idx])
        self._update_magnifier(mx, my)

    def _on_component_menu(self, pos) -> None:
        table = self._table_components
        row = table.rowAt(pos.y())
        if not (0 <= row < len(self._component_index)):
            return
        table.selectRow(row)
        if self._group_by_mpn:
            menu = QMenu(self)
            group = self._group_rows[row]
            act_checked = menu.addAction(tr("Checked"))
            act_checked.setCheckable(True)
            records = self._current_layer_records()
            act_checked.setChecked(
                all(0 <= i < len(records) and records[i].checked for i in group)
            )
            chosen = menu.exec(table.viewport().mapToGlobal(pos))
            if chosen == act_checked:
                self._on_group_checked_action(row)
            return
        menu = QMenu(self)
        act_edit = menu.addAction(tr("Edit Rotation"))
        chosen = menu.exec(table.viewport().mapToGlobal(pos))
        if chosen == act_edit:
            self._edit_rotation_for_row(row)

    def _on_check_current(self, checked: bool) -> None:
        """Check/uncheck the component that is chosen in the table."""
        if not self._loaded:
            return
        records = self._current_layer_records()
        if not records:
            return
        row = self._table_components.currentRow()
        if not (0 <= row < len(self._component_index)):
            self._lbl_status.setText(
                tr("Select a component in the table first."))
            return
        if self._group_by_mpn and row < len(self._group_rows):
            self._apply_check_to_group(row, checked)
            return
        idx = self._component_index[row]
        if not (0 <= idx < len(records)):
            return
        record = records[idx]
        if record.checked == checked:
            return
        record.checked = checked
        if self._overlay is not None:
            self._overlay.set_checked_indices(self._checked_layer_indices())
        self._refresh_component_status_row(idx)
        self.checked_changed.emit(self._record_index_in_records(record))

    def _apply_check_to_group(self, row: int, checked: bool) -> None:
        records = self._current_layer_records()
        group = self._group_rows[row]
        if not group or not all(0 <= i < len(records) for i in group):
            return
        changed = False
        for i in group:
            if records[i].checked != checked:
                records[i].checked = checked
                changed = True
        if not changed:
            return
        if self._overlay is not None:
            self._overlay.set_checked_indices(self._checked_layer_indices())
        self._refresh_component_status()
        for i in group:
            self.checked_changed.emit(self._record_index_in_records(records[i]))

    def _on_uncheck_all(self) -> None:
        """Clear the checks of the whole layer that is on the screen."""
        if not self._loaded:
            return
        records = self._current_layer_records()
        if not records or not any(r.checked for r in records):
            return
        ret = QMessageBox.question(
            self, tr("Confirm"),
            tr("Clear the checks of all components on this layer?"),
        )
        if ret != QMessageBox.Yes:
            return
        for record in records:
            record.checked = False
        if self._overlay is not None:
            self._overlay.set_checked_indices(self._checked_layer_indices())
        self._refresh_component_status()
        for record in records:
            self.checked_changed.emit(self._record_index_in_records(record))

    def _on_rotate_records(self, angle: int) -> None:
        """Rotate the components of the shown layer around the origin.

        Angle 0 keeps the coordinates and resets every rotation to 0°.
        """
        if not self._loaded:
            return
        targets = self._current_layer_records()
        if not targets and not self._records:
            return
        side = tr("top") if self._combo_layer.currentIndex() == 0 else tr("bottom")
        if angle == 0:
            ret = QMessageBox.question(
                self, tr("Confirm"),
                tr("Reset the rotation of {n} {side}-side components to 0\u00b0?",
                   n=len(targets), side=side),
            )
            busy_text = tr("Resetting rotation...")
        else:
            ret = QMessageBox.question(
                self, tr("Confirm"),
                tr("Rotate {n} {side}-side components by {a}\u00b0 "
                   "around the origin (0, 0)?",
                   n=len(targets), side=side, a=angle),
            )
            busy_text = tr("Rotating components...")
        if ret != QMessageBox.Yes:
            return
        rad = math.radians(angle)
        c, s = math.cos(rad), math.sin(rad)
        changed = self._apply_bulk_record_changes(
            targets, busy_text,
            lambda record, timestamp: self._rotate_record(
                record, angle, c, s, timestamp),
        )
        if changed:
            if angle == 0:
                self.status_message.emit(
                    tr("Reset the rotation of {n} {side}-side components "
                       "to 0\u00b0", n=len(changed), side=side))
            else:
                self.status_message.emit(
                    tr("Rotated {n} {side}-side components by {a}\u00b0",
                       n=len(changed), side=side, a=angle))
        else:
            self._lbl_status.setText(
                tr("Components are already at the rotated position."))

    @staticmethod
    def _rotate_record(
        record: ReviewRecord, angle: int, c: float, s: float,
        timestamp: str,
    ) -> bool:
        base_x = record.new_x if record.new_x is not None else record.old_x
        base_y = record.new_y if record.new_y is not None else record.old_y
        new_x = round(base_x * c - base_y * s, 4)
        new_y = round(base_x * s + base_y * c, 4)
        if new_x == 0.0:
            new_x = 0.0
        if new_y == 0.0:
            new_y = 0.0
        base_rot = (record.new_rotation
                    if record.new_rotation is not None
                    else record.old_rotation)
        new_rot = (0.0 if angle == 0
                   else round((base_rot + angle) % 360.0, 4))
        # The base values are the values that are on the screen now,
        # so the record only changes when the target differs.
        if (abs(base_x - new_x) < 1e-9 and abs(base_y - new_y) < 1e-9
                and abs(base_rot - new_rot) < 1e-9):
            return False
        record.new_x = new_x
        record.new_y = new_y
        record.new_rotation = new_rot
        record.status = "Edited"
        record.review_time = timestamp
        return True

    def _on_flip_records(self, axis: str) -> None:
        """Flip the components of the shown layer across an axis."""
        if not self._loaded:
            return
        targets = self._current_layer_records()
        if not targets and not self._records:
            return
        side = tr("top") if self._combo_layer.currentIndex() == 0 else tr("bottom")
        ret = QMessageBox.question(
            self, tr("Confirm"),
            tr("Flip {n} {side}-side components across the {axis} axis?",
               n=len(targets), side=side, axis=axis),
        )
        if ret != QMessageBox.Yes:
            return
        changed = self._apply_bulk_record_changes(
            targets, tr("Flipping components..."),
            lambda record, timestamp: self._flip_record(
                record, axis, timestamp),
        )
        if changed:
            self.status_message.emit(
                tr("Flipped {n} {side}-side components across the {axis} axis",
                   n=len(changed), side=side, axis=axis))
        else:
            self._lbl_status.setText(
                tr("Components are already at the flipped position."))

    @staticmethod
    def _flip_record(record: ReviewRecord, axis: str, timestamp: str) -> bool:
        base_x = record.new_x if record.new_x is not None else record.old_x
        base_y = record.new_y if record.new_y is not None else record.old_y
        new_x = round(-base_x, 4) if axis == "Y" else base_x
        new_y = round(-base_y, 4) if axis == "X" else base_y
        if new_x == 0.0:
            new_x = 0.0
        if new_y == 0.0:
            new_y = 0.0
        base_rot = (record.new_rotation
                    if record.new_rotation is not None
                    else record.old_rotation)
        new_rot = round((-base_rot) % 360.0, 4)
        # The base values are the values that are on the screen now,
        # so the record only changes when the target differs.
        if (abs(base_x - new_x) < 1e-9 and abs(base_y - new_y) < 1e-9
                and abs(base_rot - new_rot) < 1e-9):
            return False
        record.new_x = new_x
        record.new_y = new_y
        record.new_rotation = new_rot
        record.status = "Edited"
        record.review_time = timestamp
        return True

    @staticmethod
    def _process_events() -> None:
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def _start_bulk_progress(self, text: str) -> QProgressDialog:
        progress = QProgressDialog(text, "", 0, 100, self)
        progress.setWindowTitle(tr("Please wait"))
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        progress.raise_()
        self._process_events()
        return progress

    def _bulk_record_indices(self, records: List[ReviewRecord]) -> List[int]:
        index_by_id = {id(record): i for i, record in enumerate(self._records)}
        return [index_by_id[id(record)] for record in records
                if id(record) in index_by_id]

    def _apply_bulk_record_changes(
        self,
        targets: List[ReviewRecord],
        busy_text: str,
        mutate: Callable[[ReviewRecord, str], bool],
    ) -> List[ReviewRecord]:
        """Apply one edit to many records with progress over the whole job."""
        changed: List[ReviewRecord] = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total = len(targets)
        progress = self._start_bulk_progress(busy_text)
        try:
            for count, record in enumerate(targets, start=1):
                if mutate(record, timestamp):
                    changed.append(record)
                if total and (count == total or count % 50 == 0):
                    progress.setValue(int(count * 40 / total))
                    self._process_events()
            if not changed:
                progress.setValue(100)
                self._process_events()
                return changed

            progress.setLabelText(tr("Updating component table..."))
            progress.setValue(40)
            self._process_events()

            def table_progress(done: int, rows: int) -> None:
                progress.setValue(40 + int(25 * done / max(rows, 1)))
                if done >= rows or done % 100 == 0:
                    self._process_events()

            self._apply_layer(progress_cb=table_progress)

            progress.setLabelText(tr("Redrawing view..."))
            progress.setValue(70)
            self._process_events()
            self._redraw()
            self._fit_scene()

            progress.setLabelText(tr("Saving changes..."))
            progress.setValue(85)
            self._process_events()
            indices = self._bulk_record_indices(changed)
            if indices:
                self.records_edited.emit(indices)
            progress.setValue(100)
            self._process_events()
        finally:
            progress.close()
        return changed

    def _on_group_checked_action(self, row: int) -> None:
        if not self._group_by_mpn or not (0 <= row < len(self._group_rows)):
            return
        records = self._current_layer_records()
        group = self._group_rows[row]
        if not group:
            return
        if not all(0 <= i < len(records) for i in group):
            return
        all_checked = all(records[i].checked for i in group)
        if all_checked:
            ret = QMessageBox.question(
                self, tr("Confirm"),
                tr("Cancel the check for this component?") + "\n\n"
                + tr("MPN: {mpn}", mpn=records[group[0]].mpn or "-"),
            )
            if ret != QMessageBox.Yes:
                return
            new_checked = False
        else:
            ret = QMessageBox.question(
                self, tr("Confirm"),
                tr("Confirm component exists?") + "\n\n"
                + tr("MPN: {mpn}", mpn=records[group[0]].mpn or "-"),
            )
            if ret != QMessageBox.Yes:
                return
            new_checked = True
        changed = []
        for i in group:
            if records[i].checked != new_checked:
                records[i].checked = new_checked
                changed.append(i)
        if self._overlay is not None:
            self._overlay.set_checked_indices(self._checked_layer_indices())
        self._refresh_group_status_row(row)
        for i in changed:
            self.checked_changed.emit(self._record_index_in_records(records[i]))

    def _refresh_group_status_row(self, row: int) -> None:
        layer = self._current_layer_records()
        if not (0 <= row < len(self._group_rows)):
            return
        group = self._group_rows[row]
        col = self._table_components.columnCount() - 1
        item = self._table_components.item(row, col)
        if item is None:
            return
        checked = all(
            0 <= i < len(layer) and layer[i].checked for i in group
        ) and bool(group)
        item.setIcon(self._status_icon(checked))

    def _edit_rotation_for_row(self, row: int) -> None:
        if self._group_by_mpn or not (0 <= row < len(self._component_index)):
            return
        idx = self._component_index[row]
        records = self._current_layer_records()
        if not (0 <= idx < len(records)):
            return
        record = records[idx]
        x, y, cur_rot = _record_coord(record)
        # The mark of the part stands where the origin was put, so that
        # is where the view and the magnifier have to look.
        mx, my = self._marker_pos(record)

        # If a dialog is already open, close it first
        if self._rotation_dialog is not None:
            try:
                self._rotation_dialog.close()
            except RuntimeError:
                pass
            self._rotation_dialog = None

        # Auto-jump view to the component being edited
        self._center_view_on(mx, my)


        # Boost magnifier zoom for detailed inspection during rotation edit
        self._rot_mag_saved = self._mag_factor
        self._set_mag_factor(_ROT_EDIT_MAG_FACTOR)
        # Lock magnifier on this component while editing
        self._rotation_lock_xy = (mx, my)
        dlg = RotationEditDialog(record, parent=self,
                                 preview_cb=lambda v: self.show_rotation_preview(idx, v))
        dlg.accepted.connect(self._on_rotation_edit_accepted)
        dlg.finished.connect(self._on_rotation_edit_closed)
        self._rotation_ctx = (record, row, cur_rot)
        self._rotation_dialog = dlg
        dlg.show()

    def _center_view_on(self, x: float, y: float) -> None:
        """Center both main view and magnifier on the given coordinates."""
        try:
            self._view.centerOn(QPointF(x, y))
        except RuntimeError:
            pass
        try:
            if self._mag_view is not None:
                self._mag_view.centerOn(QPointF(x, y))
        except RuntimeError:
            pass
        self._mag_target = (x, y)

    def _on_rotation_edit_accepted(self) -> None:
        dlg = self._rotation_dialog
        if dlg is None:
            return
        record, row, cur_rot = self._rotation_ctx
        new_rot = float(dlg.new_rotation())
        ic_mode = dlg.is_ic_mode()
        changed_val = abs(new_rot - cur_rot) >= 1e-9
        changed_conv = bool(record.is_ic_rotation) != ic_mode
        if not changed_val and not changed_conv:
            return  # nothing numeric or direction-wise to persist
        record.is_ic_rotation = ic_mode
        record.status = "Edited"
        record.review_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if changed_val:
            record.new_rotation = new_rot
        rot_item = self._table_components.item(row, 4)
        if rot_item is not None:
            shown = float(
                record.new_rotation
                if record.new_rotation is not None
                else record.old_rotation
            )
            rot_item.setText(f"{shown:.0f}\u00b0")
        self._rebuild_marker_overlay()
        self.rotation_edited.emit(self._record_index_in_records(record))

    def _on_rotation_edit_closed(self) -> None:
        self.clear_rotation_preview()
        # Release magnifier lock and restore zoom level
        self._rotation_lock_xy = None
        if self._rot_mag_saved is not None:
            self._set_mag_factor(self._rot_mag_saved)
            self._rot_mag_saved = None
        self._rotation_dialog = None
        self._rotation_ctx = None

    def _render_layer(
        self,
        index: int,
        render_data: RenderData,
        angle: float,
        mirror: bool,
        off_x: float,
        off_y: float,
        mirror_x: bool = False,
    ) -> None:
        """Draw one layer, compositing the negative content when there is any.

        A layer without negative content is drawn with the plain scene
        items, which is the fast path.  A layer that removes artwork is
        drawn into an offscreen buffer so the clear objects really erase
        what is underneath them.

        The built artwork of the layer is taken from the path cache when
        this transform of the page was drawn before, so turning back to
        a familiar angle or coming back to one side of the board does
        not walk the artwork again.
        """
        key = (self._combo_layer.currentIndex() == 0, angle, mirror,
               mirror_x)
        cached = self._layer_path_cache.get(index, key)
        if cached is None:
            paths = build_layer_paths(
                render_data, angle, mirror, off_x, off_y, mirror_x,
                self._board_center,
            )
            aperture = ApertureIndex(
                render_data, mirror, angle, off_x, off_y,
                (self._board_center[0], self._board_center[1]), mirror_x)
            self._layer_path_cache.put(index, key, (paths, aperture))
        else:
            paths, aperture = cached
        # Every layer is drawn through the same item, so that the negative
        # content is composited the way the format means it and so that the
        # result can be kept as an image between two repaints.
        item = LayerItem(paths, self._layer_draw_color(index))
        self._scene.addItem(item)
        item.setZValue(self._layer_z(index))
        while len(self._layer_items) <= index:
            self._layer_items.append(None)
        self._layer_items[index] = item
        # The index finds the shape under the pointer; its grid is only
        # built when the pointer is used.
        self._aperture_indices[index] = aperture

    def _redraw(self, progress: bool = False) -> None:
        if not self._loaded:
            return

        angle = float(self._rotation)
        mirror = self._chk_flip.isChecked()
        mirror_x = self._chk_mirror_x.isChecked()
        is_top = self._combo_layer.currentIndex() == 0
        # The zoom is deliberately not part of the key: the geometry is
        # drawn in scene coordinates and the view transform scales it, so a
        # zoom does not have to rebuild the paths.
        key = (is_top, angle, mirror, mirror_x, 0.0, 0.0)

        if self._scene_key != key:
            self._scene_key = key
            self._rebuild_scene(angle, mirror, mirror_x, 0.0, 0.0, is_top,
                                progress=progress)
        else:
            self._apply_style(angle, mirror, mirror_x, 0.0, 0.0, is_top,
                              progress=progress)

        self._restore_highlight()
        self._refresh_magnifier()

    def _rebuild_scene(
        self, angle: float, mirror: bool, mirror_x: bool,
        off_x: float, off_y: float, is_top: bool,
        progress: bool = False,
    ) -> None:
        self._scene.clear()
        self._overlay = None
        self._goto_crosshair = None
        self._grid_item = None
        self._measure_preview = None
        self._measure_snap_item = None
        self._aperture_indices = {}
        self._layer_items = []
        self._apply_style(angle, mirror, mirror_x, off_x, off_y, is_top,
                          progress=progress)
        self._update_goto_crosshair()
        self._update_grid()
        self._rebuild_measurements()
        # The trace of a net is not part of the style; it comes back
        # after the scene was rebuilt, at the same place it stood.
        self._restore_trace_overlay()
        # The page may be scrolled anywhere, not only over the board.
        self._update_scene_rect()

    def _marker_pos(self, record: ReviewRecord) -> Tuple[float, float]:
        """Where the mark of a component stands on the board.

        The parts of the Pick&Place stand on the board, whose (0,0) is
        the point the origin was put on, so the mark is the origin plus
        the coordinates of the record.
        """
        x, y, _rotation = _record_coord(record)
        return x + self._origin_x, -(y + self._origin_y)

    def _marker_tuples(self) -> List[Tuple[float, float, float, float]]:
        """Build marker tuples (x, y, rotation, half) for current layer records.

        The parts of the Pick&Place stand on the board, whose (0,0) is
        the point the origin was put on.  Their position is therefore the
        origin plus the coordinates of the record.

        The Pick&Place stands in the coordinates of the board, so the
        marks do not follow the turn of the page: it is the layers of
        the Gerber that are turned, so that they come to the parts.

        IC-convention records draw at (rot + 45) so the arrow matches the knob
        needle direction used while editing; the live preview override (set
        from the dialog) always wins.
        """
        if not self._chk_pickplace.isChecked():
            return []
        grid = self._pad_grid(self._combo_layer.currentIndex() == 0)
        markers = []
        for i, record in enumerate(self._current_layer_records()):
            x, y, rotation = _record_coord(record)
            if getattr(record, "is_ic_rotation", False):
                rotation = (rotation + 45.0) % 360.0
            if self._rotation_preview is not None and self._rotation_preview[0] == i:
                rotation = self._rotation_preview[1]
            size = grid.nearest(x, y)
            half = _crosshair_half(size, self._cross_half) * self._crosshair_scale
            # The origin is where the board counts from; the parts of the
            # Pick&Place stand on the board, so they follow it.
            markers.append((x + self._origin_x, -(y + self._origin_y),
                            rotation, half))
        return markers

    def _rebuild_marker_overlay(self) -> None:
        markers = self._marker_tuples()
        if not markers:
            if self._overlay is not None:
                self._scene.removeItem(self._overlay)
                self._overlay = None
            return
        try:
            view_scale = abs(self._view.transform().m11())
        except Exception:
            view_scale = 1.0
        arrow_floor = (self._arrow_min_px / view_scale) if view_scale > 0 else 0.0
        if self._overlay is not None:
            self._scene.removeItem(self._overlay)
        self._overlay = MarkerOverlayItem(
            markers, show_unselected=self._chk_crosshair.isChecked(),
            arrow_floor=arrow_floor, arrow_min_px=self._arrow_min_px,
            cross_color=self._colors["cross"],
            highlight_color=self._colors["highlight"],
            checked_color=CHECKED_COLOR,
            checked_indices=self._checked_layer_indices(),
            flagged_indices=self._flagged_indices,
            show_frame=self._show_frame,
        )
        self._scene.addItem(self._overlay)
        self._restore_highlight()

    def show_rotation_preview(self, index: int, value: float) -> None:
        """Show live rotation preview for a marker at given layer index."""
        self._rotation_preview = (index, float(value))
        if self._overlay is not None:
            try:
                self._overlay.set_markers(self._marker_tuples())
            except RuntimeError:
                pass

    def clear_rotation_preview(self) -> None:
        """Clear any active rotation preview and restore markers."""
        if self._rotation_preview is not None:
            self._rotation_preview = None
            if self._overlay is not None:
                try:
                    self._overlay.set_markers(self._marker_tuples())
                except RuntimeError:
                    pass

    def set_flagged_indices(self, indices) -> None:
        flagged = set(indices)
        if flagged != self._flagged_indices:
            self._flagged_indices = flagged
            self._rebuild_marker_overlay()

    def _apply_style(
        self, angle: float, mirror: bool, mirror_x: bool,
        off_x: float, off_y: float, is_top: bool,
        progress: bool = False,
    ) -> None:
        """Draw every layer that is not hidden.

        The layers are drawn in the order of the list, and the layer that
        is active is drawn last, so that it lies on top of the others.

        With ``progress`` the status line names the layer at work and the
        event loop is let run between two layers, so a first appearance
        of a big board shows what happens instead of freezing.
        """
        work = [index for index in range(len(self._layers))
                if index < len(self._layer_data)
                and self._layer_data[index] is not None
                and self._layer_states[index] != LAYER_STATE_HIDDEN]
        total = len(work)
        step = 0
        for index in range(len(self._layers)):
            data = self._layer_data[index] if index < len(self._layer_data) else None
            if data is None:
                continue
            if self._layer_states[index] == LAYER_STATE_HIDDEN:
                self._hide_layer_item(index)
                continue
            step += 1
            if progress:
                self._lbl_status.setText(tr(
                    "Building layer {n}/{total}: {name}...",
                    n=step, total=total,
                    name=self._layers[index].name))
                QApplication.processEvents()
            if index >= len(self._layer_items) or self._layer_items[index] is None:
                self._render_layer(index, data, angle, mirror,
                                   off_x, off_y, mirror_x)
            else:
                self._update_layer_item(index)

        if self._chk_pickplace.isChecked():
            self._rebuild_marker_overlay()
        elif self._overlay is not None:
            self._scene.removeItem(self._overlay)
            self._overlay = None

        # The mark of the origin follows the turn of the page.
        self._update_origin_marker(angle, mirror, off_x, off_y, mirror_x)

    def _hide_layer_item(self, index: int) -> None:
        """Take one layer out of the picture."""
        if index >= len(self._layer_items):
            return
        item = self._layer_items[index]
        if item is None:
            return
        try:
            item.setVisible(False)
        except RuntimeError:
            pass

    def _layer_z(self, index: int) -> float:
        """The place of one layer in the stack, from its role.

        The copper sits at the bottom of the pile for good, so that the
        paste, the mask and the silk stay on top of it even when the
        copper is the active layer.
        """
        if index < 0 or index >= len(self._layers):
            return float(index)
        role = self._layers[index].role
        base = _LAYER_ROLE_BASE.get(role, _LAYER_ROLE_BASE[ROLE_OTHER])
        rank = sum(1 for other in self._layers[:index]
                   if other.role == role)
        return base + 0.1 * rank

    def _update_layer_item(self, index: int) -> None:
        """Give one layer its colour and its place in the picture.

        Work is skipped when nothing changed: setting the same colour and
        the same place onto the item again is harmless, but the repaint
        it asks for re-rasterizes a big layer for nothing.
        """
        if index >= len(self._layer_items):
            return
        item = self._layer_items[index]
        if item is None:
            return
        color = self._layer_draw_color(index)
        z = self._layer_z(index)
        if index == self._active_layer:
            role = self._layers[index].role if index < len(self._layers) \
                else ""
            if role != ROLE_COPPER:
                z += _LAYER_ACTIVE_BUMP
        try:
            if not item.isVisible():
                item.setVisible(True)
            if item.color().rgb() != color.rgb() or \
                    item.color().alpha() != color.alpha():
                item.set_color(color)
            if item.zValue() != z:
                item.setZValue(z)
        except RuntimeError:
            pass

    def _layer_draw_color(self, index: int) -> QColor:
        """The colour a layer is drawn with, dimmed when it is not active."""
        color = QColor(self._layer_colors[index])
        if self._layer_states[index] == LAYER_STATE_DIMMED:
            color.setAlpha(LAYER_DIMMED_ALPHA)
        return color


    def _pad_grid(self, is_top: bool) -> PadGrid:
        grid = self._pad_grid_cache.get(is_top)
        if grid is None:
            side = SIDE_TOP if is_top else SIDE_BOTTOM
            pads: List[Tuple[float, float, float]] = []
            # Paste first; the pad-shaped mask openings and copper flashes
            # serve as stand-ins when no paste layer is loaded.
            for role in _PAD_SNAP_ROLES:
                for data in self._role_datas(role, side):
                    pads += [(_flash_center(f)[0], _flash_center(f)[1], _flash_size(f))
                             for f in data.flashes]
                    if role == ROLE_PASTE:
                        pads += _paste_stroke_pads(data)
                if pads:
                    break
            grid = PadGrid(pads)
            self._pad_grid_cache[is_top] = grid
        return grid

    def _gerber_content_bbox(self) -> Tuple[float, float, float, float]:
        for data in self._layer_data:
            if data.lines or data.arcs or data.flashes:
                return data.bbox()
        return 0.0, 0.0, 0.0, 0.0

    def _gerber_scene_rect(self) -> QRectF:
        min_x, min_y, max_x, max_y = self._gerber_content_bbox()
        angle = float(self._rotation)
        mirror = self._chk_flip.isChecked()
        mirror_x = self._chk_mirror_x.isChecked()
        off_x = 0.0
        off_y = 0.0
        center_x, center_y = self._board_center
        xs, ys = [], []
        for px, py in ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)):
            tx, ty = apply_transform(px, py, mirror, angle, off_x, off_y, center_x, center_y, mirror_x)
            xs.append(tx)
            ys.append(-ty)
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def _markers_scene_rect(self) -> Optional[QRectF]:
        overlay = getattr(self, "_overlay", None)
        if overlay is None or not overlay._markers:
            return None
        rect = overlay._compute_rect()
        if rect.isNull() or not rect.isValid():
            return None
        return rect

    def _fit_scene(self) -> None:
        rect = self._gerber_scene_rect()
        markers = self._markers_scene_rect()
        if markers is not None and not rect.united(markers).isEmpty():
            if rect.isEmpty() or not rect.contains(markers) and not rect.intersects(markers):
                rect = rect.united(markers)
        if not rect.isEmpty():
            self._view.fit_to_rect(rect)
        else:
            self._view.fit()
        scale = self._view.transform().m11()
        if abs(scale - self._scene_scale) > 1e-6:
            self._scene_scale = scale
            self._redraw()
        self._grid_available = True
        self._chk_grid.setEnabled(True)
        if self._chk_grid.isChecked():
            self._on_grid_toggled(True)

    def _role_datas(self, role: str, side: str = "") -> List[RenderData]:
        """The geometry of the layers of one role.

        When no layer of that role is on that side of the board, the
        layers of the role itself are used, so that a job without a
        top and a bottom paste is still shown.
        """
        found = []
        for layer, data in zip(self._layers, self._layer_data):
            if layer.role != role:
                continue
            if side and layer.side and layer.side != side:
                continue
            found.append(data)
        if found or not side:
            return found
        return self._role_datas(role)

    def _layer_points(self) -> Tuple[List[float], List[float]]:
        """The places of every layer of the picture."""
        xs: List[float] = []
        ys: List[float] = []
        for data in self._layer_data:
            for ln in data.lines:
                xs += [ln.x1, ln.x2]
                ys += [ln.y1, ln.y2]
            for ar in data.arcs:
                xs += [ar.x1, ar.x2]
                ys += [ar.y1, ar.y2]
            for fl in data.flashes:
                xs.append(fl.cx)
                ys.append(fl.cy)
        return xs, ys

    def _compute_board_center(self) -> Tuple[float, float]:
        xs, ys = self._layer_points()
        if not xs:
            return 0.0, 0.0
        return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0

    def _board_size(self) -> float:
        xs, ys = self._layer_points()
        if not xs:
            return 1.0
        return max(max(xs) - min(xs), max(ys) - min(ys))

    def _outline_min_corner(self) -> Tuple[float, float]:
        for data in self._role_datas(ROLE_PROFILE) + self._role_datas(ROLE_PASTE):
            if data.lines or data.arcs or data.flashes:
                min_x, min_y, _max_x, _max_y = data.bbox()
                return min_x, min_y
        return 0.0, 0.0

    def _on_reload_records(self) -> None:
        """Re-sync the component table and markers from the live record list.

        The viewer shares the same list object with the main window, so any
        change made there (rotation edit, batch edit, delete, undo, ...)
        is reflected here immediately.
        """
        self._rotation_preview = None
        self.refresh_records(self._records)


def build_pads(render_data: RenderData) -> List[Tuple[float, float, float]]:
    return [(f.cx, f.cy, _flash_size(f)) for f in render_data.flashes]
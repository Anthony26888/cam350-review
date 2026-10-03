import math
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, QThread, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QPen, QPainter, QPainterPath, QPolygonF,
    QWheelEvent, QFont, QFontMetricsF, QTransform, QPixmap, QMouseEvent, QIcon,
    QCursor,
)
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPathItem,
    QGraphicsEllipseItem,
    QComboBox,
    QCheckBox, QGroupBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDoubleSpinBox, QSpinBox, QWidget, QDialog,
    QSizePolicy, QFrame, QColorDialog, QGridLayout, QMenu,
    QProgressBar, QApplication,
)

from models.review import ReviewRecord
from ui.i18n import tr
from ui.rotation_edit_dialog import RotationEditDialog
from services.gerber.gerber_render import (
    RenderData, LineShape, ArcShape, FlashShape, parse_render,
)
from services.gerber.gerber_render_lib import parse_layer
from services.gerber.gerber_transform import (
    apply_transform, apply_inverse_transform, transform_rot,
)
from utils.path_utils import resource_path

OUTLINE_COLOR = QColor("#F8FAFC")
TOP_PASTE_COLOR = QColor(34, 211, 238, 210)
BOTTOM_PASTE_COLOR = QColor(251, 191, 36, 210)
SILK_COLOR = QColor(240, 171, 252, 220)
CROSS_COLOR = QColor("#EF4444")
HIGHLIGHT_COLOR = QColor("#39FF14")
CHECKED_COLOR = QColor("#22C55E")
GRID_COLOR = QColor(100, 116, 139, 160)
BACKGROUND = QColor("#0B1220")
MEASURE_COLOR = QColor("#38BDF8")

_CROSS_BOARD_RATIO = 0.01
_MIN_ARROW_PX = 10.0
_MIN_ARROW_WING_RATIO = 0.3

_ICON_CHECKED: Optional[QIcon] = None
_ICON_UNCHECKED: Optional[QIcon] = None


def _build_status_icon(checked: bool) -> QIcon:
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    if checked:
        pen = QPen(QColor("#22C55E"), 2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(3.0, 8.5)
        path.lineTo(6.5, 12.0)
        path.lineTo(13.0, 4.0)
        p.drawPath(path)
    else:
        p.setBrush(QColor("#F97316"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(4.0, 4.0, 8.0, 8.0)
    p.end()
    return QIcon(pm)


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


def _crosshair_half(size: Optional[float], fallback: float) -> float:
    if size is None:
        return fallback
    return min(max(size * 1.15, 0.15), fallback)


_MAG_FACTOR = 6.0
_MAG_FACTORS = (3.0, 4.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 25.0)
_ROT_EDIT_MAG_FACTOR = 20.0   # zoom level while editing rotation
_MAG_MIN_SCALE = 1.0


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
) -> None:
    """Append one flash to `path` with the display transform applied.

    All geometry (position, polygon vertices, aperture-macro primitives) is
    transformed by the same mirror -> rotate -> offset pipeline used for
    stroked lines, so every layer rotates together.
    """
    def _t_abs(x: float, y: float) -> Tuple[float, float]:
        return apply_transform(x, y, mirror, angle, off_x, off_y, cx0, cy0, mirror_x)

    def _t_loc(x: float, y: float) -> Tuple[float, float]:
        return apply_transform(x, y, mirror, angle, 0.0, 0.0, 0.0, 0.0, mirror_x)

    rot = transform_rot(fl.rot, mirror, angle, mirror_x)

    if fl.kind == "circle":
        gx, gy = _t_abs(fl.cx, fl.cy)
        r = fl.w / 2.0
        path.addEllipse(gx - r, -gy - r, 2 * r, 2 * r)
        return

    if fl.kind == "rect":
        gx, gy = _t_abs(fl.cx, fl.cy)
        _add_rect_path(path, gx, gy, fl.w, fl.h, math.radians(rot))
        return

    if fl.kind == "oblong":
        gx, gy = _t_abs(fl.cx, fl.cy)
        if abs(rot) < 0.5 or abs(rot - 360.0) < 0.5:
            r = min(fl.w, fl.h) / 2.0
            path.addRoundedRect(
                QRectF(gx - fl.w / 2, -gy - fl.h / 2, fl.w, fl.h), r, r
            )
        else:
            _add_capsule_path(path, gx, gy, fl.w, fl.h, math.radians(rot))
        return

    if fl.kind == "polygon" and fl.pts:
        if abs(fl.cx) < 1e-9 and abs(fl.cy) < 1e-9:
            # Absolute points (G36/G37 regions).
            pts = [QPointF(x, -y) for x, y in (_t_abs(px, py) for px, py in fl.pts)]
        else:
            # Local points relative to a flash position.
            gx, gy = _t_abs(fl.cx, fl.cy)
            pts = [
                QPointF(gx + lx, -gy - ly)
                for lx, ly in (_t_loc(px, py) for px, py in fl.pts)
            ]
        path.addPolygon(QPolygonF(_normalize_winding(pts)))
        return

    if fl.kind == "macro" and fl.macro:
        gx, gy = _t_abs(fl.cx, fl.cy)
        m = fl.macro
        for mx, my, r in m.circles:
            lx, ly = _t_loc(mx, my)
            path.addEllipse(gx + lx - r, -gy - ly - r, 2 * r, 2 * r)
        for poly_pts in m.polygons:
            pts = [
                QPointF(gx + lx, -gy - ly)
                for lx, ly in (_t_loc(px, py) for px, py in poly_pts)
            ]
            path.addPolygon(QPolygonF(_normalize_winding(pts)))
        for x1, y1, x2, y2, width in m.segments:
            lx1, ly1 = _t_loc(x1, y1)
            lx2, ly2 = _t_loc(x2, y2)
            ang = math.atan2(ly2 - ly1, lx2 - lx1)
            n2 = width / 2.0
            dx, dy = -math.sin(ang) * n2, math.cos(ang) * n2
            quad = [
                QPointF(gx + lx1 + dx, -gy - ly1 - dy),
                QPointF(gx + lx1 - dx, -gy - ly1 + dy),
                QPointF(gx + lx2 - dx, -gy - ly2 + dy),
                QPointF(gx + lx2 + dx, -gy - ly2 - dy),
            ]
            path.addPolygon(QPolygonF(_normalize_winding(quad)))


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


def _add_rect_path(path: QPainterPath, gx, gy, w, h, rot):
    hw, hh = w / 2.0, h / 2.0
    c, s = math.cos(rot), math.sin(rot)
    pts = []
    for cx0, cy0 in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
        rx = cx0 * c - cy0 * s
        ry = cx0 * s + cy0 * c
        pts.append(QPointF(gx + rx, -gy - ry))
    path.addPolygon(QPolygonF(_normalize_winding(pts)))


def _add_capsule_path(path: QPainterPath, cx, cy, w, h, rot):
    r = max(0.0, min(w, h) / 2.0)
    a = max(0.0, w / 2.0 - r)
    pts = []
    n_line = 10
    n_arc = 20
    for i in range(n_line + 1):
        t = i / n_line
        pts.append((-a + 2 * a * t, h / 2.0))
    for i in range(n_arc + 1):
        t = -math.pi / 2.0 + math.pi * i / n_arc
        pts.append((a + r * math.cos(t), r * math.sin(t)))
    for i in range(n_line + 1):
        t = i / n_line
        pts.append((a - 2 * a * t, -h / 2.0))
    for i in range(n_arc + 1):
        t = math.pi / 2.0 + math.pi * i / n_arc
        pts.append((-a + r * math.cos(t), r * math.sin(t)))
    c, s = math.cos(rot), math.sin(rot)
    out = []
    for gx, gy in pts:
        out.append(QPointF(cx + gx * c - gy * s, -cy - gx * s - gy * c))
    path.addPolygon(QPolygonF(_normalize_winding(out)))


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
        self.setZValue(80)
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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(BACKGROUND)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setMouseTracking(True)
        # Large-gerber smoothness: cheaper rasterization paths
        self.setOptimizationFlags(
            QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing
            | QGraphicsView.OptimizationFlag.DontSavePainterState
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)

        self._panning = False
        self._grid_active = False
        self._measure_mode = False

        self._full_cross_enabled = False
        self._full_cross_pos: Optional[QPointF] = None

        self._fast_render = False
        self._fast_timer: Optional[QTimer] = None

        self._zoom_pixmap: Optional[QPixmap] = None
        self._zoom_ratio: float = 1.0
        self._zoom_anchor: QPoint = QPoint(0, 0)
        self._zoom_active = False

        # Pan gesture: blit a frozen snapshot instead of scrolling the scene
        self._pan_pixmap: Optional[QPixmap] = None
        self._pan_offset = QPoint(0, 0)

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
            self.scale(self._zoom_ratio, self._zoom_ratio)
        self._zoom_pixmap = None
        self._zoom_ratio = 1.0
        self._zoom_active = False
        self.zoom_end.emit()
        self.viewport().update()

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
        self._set_fast_render()
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
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
        self.setDragMode(
            QGraphicsView.NoDrag if active else QGraphicsView.ScrollHandDrag
        )
        self.setFocusPolicy(Qt.StrongFocus if active else Qt.WheelFocus)
        self.viewport().update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._grid_active:
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
        sp = self.mapToScene(event.position().toPoint())
        self.cursor_moved.emit(sp.x(), sp.y())
        self._full_cross_pos = event.position()
        if self._full_cross_enabled:
            self.viewport().update()
        if self._panning and self._pan_pixmap is not None:
            self._pan_offset = event.position().toPoint() - self._pan_press
            self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.cursor_left.emit()
        self._full_cross_pos = None
        if self._full_cross_enabled:
            self.viewport().update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._grid_active:
            if event.button() == Qt.LeftButton:
                sp = self.mapToScene(event.position().toPoint())
                self.grid_cell_clicked.emit(sp.x(), sp.y())
                event.accept()
            return
        if self._measure_mode:
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
        if self._measure_mode and event.key() == Qt.Key_Escape:
            self.measure_cancel.emit()
            event.accept()
            return
        super().keyPressEvent(event)

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
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, gko: str, gtp: str, gbp: str, gto: str, gbo: str, parent=None) -> None:
        super().__init__(parent)
        self._gko = gko
        self._gtp = gtp
        self._gbp = gbp
        self._gto = gto
        self._gbo = gbo

    def run(self) -> None:
        try:
            data: Dict[str, RenderData] = {}
            self.progress.emit(tr("Reading GKO (outline)..."), 12)
            data["outline"] = parse_layer(self._gko)

            data["top"] = RenderData()
            data["bottom"] = RenderData()
            data["silk"] = RenderData()
            data["silk_bottom"] = RenderData()

            if self._gtp and os.path.exists(self._gtp):
                self.progress.emit(tr("Reading GTP (Top Paste)..."), 30)
                data["top"] = parse_layer(self._gtp)
            if self._gbp and os.path.exists(self._gbp):
                self.progress.emit(tr("Reading GBP (Bottom Paste)..."), 45)
                data["bottom"] = parse_layer(self._gbp)
            if self._gto and os.path.exists(self._gto):
                self.progress.emit(tr("Reading GTO (Silkscreen)..."), 60)
                data["silk"] = parse_layer(self._gto)
            if self._gbo and os.path.exists(self._gbo):
                self.progress.emit(tr("Reading GBO (Silkscreen)..."), 75)
                data["silk_bottom"] = parse_layer(self._gbo)

            self.progress.emit(tr("Done."), 100)
            self.finished.emit(data)
        except Exception as e:
            self.failed.emit(str(e))


class MagnifierView(QGraphicsView):
    clicked = Signal(float, float)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            sp = self.mapToScene(event.position().toPoint())
            self.clicked.emit(sp.x(), sp.y())
            event.accept()
            return
        super().mouseReleaseEvent(event)
class GerberViewer(QWidget):

    settings_saved = Signal(dict)

    checked_changed = Signal(int)

    rotation_edited = Signal(int)

    def __init__(
        self,
        records: List[ReviewRecord],
        gko_path: str,
        gtp_path: str = "",
        gbp_path: str = "",
        gto_path: str = "",
        gbo_path: str = "",
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
        self._gko_path = gko_path
        self._gtp_path = gtp_path
        self._gbp_path = gbp_path
        self._gto_path = gto_path
        self._gbo_path = gbo_path

        self._outline: RenderData = RenderData()
        self._top: RenderData = RenderData()
        self._bottom: RenderData = RenderData()
        self._silk: RenderData = RenderData()
        self._silk_bottom: RenderData = RenderData()
        self._loaded = False
        self._pads: List[Tuple[float, float, float]] = []
        self._pad_grid_cache: Dict[bool, PadGrid] = {}
        self._scene_key: Optional[tuple] = None
        self._line_items: Dict[str, List] = {}
        self._fill_items: Dict[str, Optional[object]] = {}
        self._overlay: Optional[MarkerOverlayItem] = None
        self._goto_pos: Optional[Tuple[float, float]] = None
        self._goto_crosshair: Optional[QGraphicsPathItem] = None
        self._grid_active = False
        self._grid_available = False
        self._grid_opacity = 255
        self._grid_width = 2.0
        self._grid_item: Optional[QGraphicsPathItem] = None
        self._grid_rect: Optional[QRectF] = None
        self._measure_mode = False
        self._measure_start: Optional[Tuple[float, float]] = None
        self._measure_preview: Optional[QGraphicsPathItem] = None
        self._measure_snap_item: Optional[QGraphicsEllipseItem] = None
        self._snap_enabled = True
        self._snap_tol = 1.0
        self._compact_hidden = False
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
        self._show_frame = True
        self._colors: Dict[str, QColor] = {
            "outline": OUTLINE_COLOR,
            "paste_top": TOP_PASTE_COLOR,
            "paste_bottom": BOTTOM_PASTE_COLOR,
            "silk": SILK_COLOR,
            "cross": CROSS_COLOR,
            "highlight": HIGHLIGHT_COLOR,
        }
        self._color_buttons: Dict[str, QPushButton] = {}
        self._color_pending: Dict[str, str] = {}

        self._build_ui()
        self._apply_layer()
        self.apply_display_settings(display_settings or {})
        self._start_load()

    def display_settings(self) -> Dict[str, Any]:
        settings = {
            "layer": self._combo_layer.currentIndex(),
            "rotation": self._combo_rot.currentData() or 0,
            "invert_rot": self._chk_invert_rot.isChecked(),
            "flip": self._chk_flip.isChecked(),
            "mirror_x": self._chk_mirror_x.isChecked(),
            "offset_x": self._spin_off_x.value(),
            "offset_y": self._spin_off_y.value(),
            "outline": self._chk_outline.isChecked(),
            "paste": self._chk_paste.isChecked(),
            "silk": self._chk_silk.isChecked(),
            "pickplace": self._chk_pickplace.isChecked(),
            "crosshair": self._chk_crosshair.isChecked(),
            "frame": self._chk_frame.isChecked(),
            "mag_factor": self._mag_factor,
            "arrow_min_px": self._spin_arrow_px.value(),
            "crosshair_scale": self._spin_cross_scale.value(),
            "grid_opacity": self._grid_opacity,
            "grid_width": self._grid_width,
            "snap": self._chk_snap.isChecked(),
            "snap_tol": self._spin_snap_tol.value(),
            "compact": self._btn_compact.isChecked(),
            "full_crosshair": self._chk_full_cross.isChecked(),
        }
        for key in ("outline", "paste_top", "paste_bottom", "silk", "cross", "highlight"):
            settings[f"{key}_color"] = self._current_color(key).name(QColor.HexArgb)
        return settings

    def apply_display_settings(self, settings: Dict[str, Any]) -> None:
        if not isinstance(settings, dict) or not settings:
            return
        if "layer" in settings:
            idx = int(settings.get("layer", 0))
            if 0 <= idx < self._combo_layer.count():
                self._combo_layer.setCurrentIndex(idx)
        if "rotation" in settings:
            rot = settings.get("rotation")
            for i in range(self._combo_rot.count()):
                if self._combo_rot.itemData(i) == rot:
                    self._combo_rot.setCurrentIndex(i)
                    break
        self._chk_invert_rot.setChecked(bool(settings.get("invert_rot", False)))
        self._chk_flip.setChecked(bool(settings.get("flip", False)))
        self._chk_mirror_x.setChecked(bool(settings.get("mirror_x", False)))
        self._spin_off_x.setValue(float(settings.get("offset_x", 0.0)))
        self._spin_off_y.setValue(float(settings.get("offset_y", 0.0)))
        self._chk_outline.setChecked(bool(settings.get("outline", True)))
        self._chk_paste.setChecked(bool(settings.get("paste", True)))
        self._chk_silk.setChecked(bool(settings.get("silk", True)))
        self._chk_pickplace.setChecked(bool(settings.get("pickplace", True)))
        self._chk_crosshair.setChecked(bool(settings.get("crosshair", True)))
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
        self._btn_compact.setChecked(bool(settings.get("compact", True)))
        self._chk_full_cross.setChecked(bool(settings.get("full_crosshair", False)))
        for key in ("outline", "paste_top", "paste_bottom", "silk", "cross", "highlight"):
            hex_val = settings.get(f"{key}_color")
            if isinstance(hex_val, str):
                color = QColor(hex_val)
                if color.isValid():
                    self._colors[key] = color
        self._sync_color_buttons()

    def _save_display_settings(self) -> None:
        self._btn_save_disp.setEnabled(False)
        self._progress_save.setVisible(True)
        self._lbl_saving.setVisible(True)
        for key, hex_val in self._color_pending.items():
            color = QColor(hex_val)
            if color.isValid():
                self._colors[key] = color
        self._color_pending.clear()
        self._sync_color_buttons()
        self._redraw()
        self.settings_saved.emit(self.display_settings())
        self._lbl_status.setText(tr("Display settings saved to session."))
        self._display_dialog.accept()

    def _on_display_rejected(self) -> None:
        snapshot = getattr(self, "_display_snapshot", None)
        if snapshot is not None:
            self._color_pending.clear()
            self.apply_display_settings(snapshot)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        _logo_pm = QPixmap(resource_path("assets/icon.ico"))
        if not _logo_pm.isNull():
            _logo = QLabel()
            _logo.setPixmap(_logo_pm.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            top_bar.addWidget(_logo)
        self._lbl_title = QLabel(tr("Reading Gerber file..."))
        self._lbl_title.setStyleSheet("font-size: 13px; font-weight: bold;")
        top_bar.addWidget(self._lbl_title)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        body = QHBoxLayout()
        body.setSpacing(10)

        self._view = GerberView()
        self._scene = QGraphicsScene(self)
        self._view.setScene(self._scene)
        body.addWidget(self._view, 1)

        panel = QVBoxLayout()
        panel.setSpacing(8)

        self._options_widget = QWidget()
        self._options_layout = QVBoxLayout(self._options_widget)
        self._options_layout.setSpacing(8)
        self._options_layout.setContentsMargins(0, 0, 0, 0)

        btn_row = QHBoxLayout()
        btn_disp = QPushButton(tr("Display..."))
        btn_disp.clicked.connect(self._open_display_dialog)
        btn_fit = QPushButton(tr("Fit View"))
        btn_fit.clicked.connect(self._fit_scene)
        btn_reload = QPushButton(tr("Reload"))
        btn_reload.setToolTip(tr("Reload latest component data from the main window"))
        btn_reload.clicked.connect(self._on_reload_records)
        btn_row.addWidget(btn_disp)
        btn_row.addWidget(btn_fit)
        btn_row.addWidget(btn_reload)
        self._options_layout.addLayout(btn_row)

        layer_row = QHBoxLayout()
        layer_row.addWidget(QLabel(tr("Layer:")))
        self._combo_layer = QComboBox()
        self._combo_layer.addItem(tr("Top layer (GKO + GTP)"))
        self._combo_layer.addItem(tr("Bottom layer (GKO + GBP)"))
        self._combo_layer.currentIndexChanged.connect(self._on_layer_changed)
        layer_row.addWidget(self._combo_layer, 1)
        self._options_layout.addLayout(layer_row)

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

        panel.addWidget(self._options_widget)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(tr("Search designator or MPN..."))
        self._search_input.setClearButtonEnabled(True)
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(150)
        self._search_debounce.timeout.connect(self._apply_layer)
        self._search_input.textChanged.connect(self._on_search_changed)
        panel.addWidget(self._search_input)

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
        panel.addWidget(self._table_components, 1)

        self._lbl_status = QLabel(tr("No data yet."))
        self._lbl_status.setWordWrap(True)
        panel.addWidget(self._lbl_status)

        self._mag_group = QGroupBox(tr("Details (Zoom {f:g}x)", f=_MAG_FACTOR))
        self._mag_group.setStyleSheet("""
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
""")
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
        self._mag_view.setMinimumSize(380, 300)
        self._mag_view.setMaximumHeight(360)
        self._mag_view.setScene(self._scene)
        mag_layout.addWidget(self._mag_view, 1)
        self._lbl_mag_hint = QLabel(tr("Hover the drawing / select a component to see details."))
        self._lbl_mag_hint.setWordWrap(True)
        mag_layout.addWidget(self._lbl_mag_hint)
        panel.addWidget(self._mag_group)

        self._view.cursor_moved.connect(self._update_magnifier)
        self._view.cursor_moved.connect(self._update_coord_label)
        self._view.cursor_left.connect(self._clear_coord_label)
        self._view.cursor_left.connect(self._refresh_magnifier)
        self._view.zoom_end.connect(self._refresh_magnifier)
        self._view.grid_cell_clicked.connect(self._on_grid_cell_clicked)
        self._view.measure_clicked.connect(self._on_measure_clicked)
        self._view.measure_cancel.connect(self._on_measure_cancel)
        self._view.cursor_moved.connect(self._on_measure_move)
        self._view.crosshair_right_clicked.connect(self._on_crosshair_right_clicked)
        self._mag_view.clicked.connect(self._on_mag_clicked)

        self._display_dialog = QDialog(self)
        self._display_dialog.setWindowTitle(tr("Display settings"))
        display_layout = QVBoxLayout(self._display_dialog)
        display_layout.addWidget(self._build_display_group())
        self._progress_save = QProgressBar()
        self._progress_save.setRange(0, 0)
        self._progress_save.setVisible(False)
        display_layout.addWidget(self._progress_save)
        self._lbl_saving = QLabel(tr("Saving..."))
        self._lbl_saving.setVisible(False)
        display_layout.addWidget(self._lbl_saving)
        self._btn_save_disp = QPushButton(tr("Save display settings"))
        self._btn_save_disp.clicked.connect(self._save_display_settings)
        display_layout.addWidget(self._btn_save_disp)
        self._display_dialog.rejected.connect(self._on_display_rejected)

        panel_widget = QWidget()
        panel_widget.setLayout(panel)
        panel_widget.setFixedWidth(400)
        body.addWidget(panel_widget)

        layout.addLayout(body, 1)

        coord_bar = QHBoxLayout()
        self._lbl_coord = QLabel(tr("X: --  Y: --"))
        coord_bar.addWidget(self._lbl_coord)
        coord_bar.addStretch(1)
        self._btn_measure = QPushButton(tr("Measure"))
        self._btn_measure.setCheckable(True)
        self._btn_measure.setEnabled(False)
        self._btn_measure.setToolTip(
            tr("Click two points to measure the distance. "
               "Right-click or Esc cancels the current measurement.")
        )
        self._btn_measure.toggled.connect(self._on_measure_toggled)
        coord_bar.addWidget(self._btn_measure)
        self._btn_clear_measure = QPushButton(tr("Clear"))
        self._btn_clear_measure.setEnabled(False)
        self._btn_clear_measure.clicked.connect(self._clear_measurements)
        coord_bar.addWidget(self._btn_clear_measure)
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
        self._btn_compact = QPushButton(tr("Compact"))
        self._btn_compact.setCheckable(True)
        self._btn_compact.setChecked(True)
        self._btn_compact.setToolTip(
            tr("Show/hide the options bar and file stats "
               "(Outline/Top/Bottom/Silk) to give the component table more space.")
        )
        self._btn_compact.toggled.connect(self._on_compact_toggled)
        coord_bar.addWidget(self._btn_compact)
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
        layout.addLayout(coord_bar)

    def _build_display_group(self) -> QGroupBox:
        group = QGroupBox(tr("Display"))
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        # --- Gerber Transform & Offset ---
        transform_group = QGroupBox(tr("Gerber Transform & Offset"))
        transform_layout = QVBoxLayout(transform_group)
        transform_layout.setSpacing(4)

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel(tr("Rotate Gerber:")))
        self._combo_rot = QComboBox()
        for angle in (0, 90, 180, 270):
            self._combo_rot.addItem(f"{angle}°", angle)
        rot_row.addWidget(self._combo_rot, 1)
        transform_layout.addLayout(rot_row)

        self._chk_invert_rot = QCheckBox(tr("Invert Gerber rotation"))
        transform_layout.addWidget(self._chk_invert_rot)

        self._chk_flip = QCheckBox(tr("Flip Gerber (Mirror Y)"))
        transform_layout.addWidget(self._chk_flip)

        self._chk_mirror_x = QCheckBox(tr("Flip Gerber (Mirror X)"))
        transform_layout.addWidget(self._chk_mirror_x)

        off_row = QHBoxLayout()
        off_row.addWidget(QLabel(tr("Offset X:")))
        self._spin_off_x = QDoubleSpinBox()
        self._spin_off_x.setRange(-100000.0, 100000.0)
        self._spin_off_x.setSingleStep(0.05)
        self._spin_off_x.setDecimals(2)
        self._spin_off_x.setValue(0.0)
        off_row.addWidget(self._spin_off_x, 1)
        off_row.addWidget(QLabel(tr("Y:")))
        self._spin_off_y = QDoubleSpinBox()
        self._spin_off_y.setRange(-100000.0, 100000.0)
        self._spin_off_y.setSingleStep(0.05)
        self._spin_off_y.setDecimals(2)
        self._spin_off_y.setValue(0.0)
        off_row.addWidget(self._spin_off_y, 1)
        btn_zero = QPushButton("0")
        btn_zero.clicked.connect(self._reset_offset)
        off_row.addWidget(btn_zero)
        btn_origin = QPushButton(tr("To Origin (0,0)"))
        btn_origin.clicked.connect(self._bring_gerber_to_origin)
        off_row.addWidget(btn_origin)
        transform_layout.addLayout(off_row)

        layout.addWidget(transform_group)

        # --- Visibility ---
        visibility_group = QGroupBox(tr("Visibility"))
        visibility_layout = QGridLayout(visibility_group)
        visibility_layout.setSpacing(6)

        self._chk_outline = QCheckBox(tr("Show GKO outline"))
        self._chk_outline.setChecked(True)
        self._chk_paste = QCheckBox(tr("Show Paste (GTP / GBP)"))
        self._chk_paste.setChecked(True)
        self._chk_silk = QCheckBox(tr("Show Silkscreen (GTO / GBO)"))
        self._chk_silk.setChecked(True)
        self._chk_pickplace = QCheckBox(tr("Show PickPlace (aligned)"))
        self._chk_pickplace.setChecked(True)
        self._chk_crosshair = QCheckBox(tr("Show crosshair"))
        self._chk_crosshair.setChecked(True)
        self._chk_frame = QCheckBox(tr("Show frame"))
        self._chk_frame.setChecked(True)
        self._chk_frame.toggled.connect(self._on_frame_toggled)

        visibility_layout.addWidget(self._chk_outline, 0, 0)
        visibility_layout.addWidget(self._make_color_swatch("outline"), 0, 1)
        visibility_layout.addWidget(self._chk_paste, 0, 3)
        visibility_layout.addWidget(self._make_color_swatch("paste_top"), 0, 4)
        visibility_layout.addWidget(self._make_color_swatch("paste_bottom"), 0, 5)
        visibility_layout.addWidget(self._chk_silk, 1, 0)
        visibility_layout.addWidget(self._make_color_swatch("silk"), 1, 1)
        visibility_layout.addWidget(self._chk_pickplace, 1, 3)
        visibility_layout.addWidget(self._make_color_swatch("cross"), 1, 4)
        visibility_layout.addWidget(self._chk_crosshair, 2, 0)
        visibility_layout.addWidget(self._chk_frame, 2, 3)
        visibility_layout.addWidget(self._make_color_swatch("highlight"), 2, 4)
        visibility_layout.setColumnStretch(2, 1)
        visibility_layout.setColumnStretch(5, 1)

        layout.addWidget(visibility_group)

        # --- PickPlace markers ---
        markers_group = QGroupBox(tr("PickPlace markers"))
        markers_layout = QVBoxLayout(markers_group)
        markers_layout.setSpacing(4)

        arrow_row = QHBoxLayout()
        arrow_row.addWidget(QLabel(tr("Arrow size:")))
        self._spin_arrow_px = QSpinBox()
        self._spin_arrow_px.setRange(5, 100)
        self._spin_arrow_px.setSingleStep(5)
        self._spin_arrow_px.setValue(int(_MIN_ARROW_PX))
        self._spin_arrow_px.setSuffix(" px")
        self._spin_arrow_px.valueChanged.connect(self._on_arrow_size_changed)
        arrow_row.addWidget(self._spin_arrow_px, 1)
        markers_layout.addLayout(arrow_row)

        cross_row = QHBoxLayout()
        cross_row.addWidget(QLabel(tr("Crosshair scale:")))
        self._spin_cross_scale = QDoubleSpinBox()
        self._spin_cross_scale.setRange(0.5, 5.0)
        self._spin_cross_scale.setSingleStep(0.1)
        self._spin_cross_scale.setDecimals(1)
        self._spin_cross_scale.setValue(1.0)
        self._spin_cross_scale.valueChanged.connect(self._on_crosshair_scale_changed)
        cross_row.addWidget(self._spin_cross_scale, 1)
        markers_layout.addLayout(cross_row)

        self._chk_full_cross = QCheckBox(tr("Crosshair full screen"))
        self._chk_full_cross.setToolTip(tr("Show a crosshair across the whole view while hovering"))
        self._chk_full_cross.toggled.connect(self._on_full_cross_toggled)
        markers_layout.addWidget(self._chk_full_cross)

        layout.addWidget(markers_group)

        # --- Snapping ---
        snap_group = QGroupBox(tr("Snapping"))
        snap_layout = QVBoxLayout(snap_group)
        snap_layout.setSpacing(4)

        snap_row = QHBoxLayout()
        self._chk_snap = QCheckBox(tr("Snap to pad center when measuring"))
        self._chk_snap.setChecked(True)
        self._chk_snap.setToolTip(
            tr("Snap tolerance is in mm and applies to the nearest pad center within the radius."))
        self._chk_snap.toggled.connect(self._on_snap_toggled)
        snap_row.addWidget(self._chk_snap, 1)
        snap_row.addWidget(QLabel(tr("Tolerance:")))
        self._spin_snap_tol = QDoubleSpinBox()
        self._spin_snap_tol.setRange(0.1, 5.0)
        self._spin_snap_tol.setSingleStep(0.1)
        self._spin_snap_tol.setDecimals(1)
        self._spin_snap_tol.setValue(1.0)
        self._spin_snap_tol.setSuffix(" mm")
        self._spin_snap_tol.setToolTip(
            tr("Snap tolerance is in mm and applies to the nearest pad center within the radius."))
        self._spin_snap_tol.valueChanged.connect(self._on_snap_tol_changed)
        snap_row.addWidget(self._spin_snap_tol)
        snap_layout.addLayout(snap_row)

        layout.addWidget(snap_group)

        # --- Grid ---
        grid_group = QGroupBox(tr("Grid"))
        grid_layout = QVBoxLayout(grid_group)
        grid_layout.setSpacing(4)

        grid_row = QHBoxLayout()
        self._chk_grid = QCheckBox(tr("Show grid"))
        self._chk_grid.setEnabled(False)
        self._chk_grid.toggled.connect(self._on_grid_toggled)
        grid_row.addWidget(self._chk_grid)
        grid_row.addWidget(QLabel(tr("Col:")))
        self._spin_grid_cols = QSpinBox()
        self._spin_grid_cols.setRange(1, 50)
        self._spin_grid_cols.setValue(3)
        self._spin_grid_cols.valueChanged.connect(self._on_grid_params_changed)
        grid_row.addWidget(self._spin_grid_cols)
        grid_row.addWidget(QLabel(tr("Row:")))
        self._spin_grid_rows = QSpinBox()
        self._spin_grid_rows.setRange(1, 50)
        self._spin_grid_rows.setValue(3)
        self._spin_grid_rows.valueChanged.connect(self._on_grid_params_changed)
        grid_row.addWidget(self._spin_grid_rows)
        grid_row.addStretch(1)
        grid_layout.addLayout(grid_row)

        grid_style_row = QHBoxLayout()
        grid_style_row.addWidget(QLabel(tr("Grid opacity:")))
        self._spin_grid_opacity = QSpinBox()
        self._spin_grid_opacity.setRange(20, 255)
        self._spin_grid_opacity.setValue(self._grid_opacity)
        self._spin_grid_opacity.setSingleStep(5)
        self._spin_grid_opacity.valueChanged.connect(self._on_grid_style_changed)
        grid_style_row.addWidget(self._spin_grid_opacity)
        grid_style_row.addWidget(QLabel(tr("Grid width:")))
        self._spin_grid_width = QDoubleSpinBox()
        self._spin_grid_width.setRange(1.0, 4.0)
        self._spin_grid_width.setValue(self._grid_width)
        self._spin_grid_width.setSingleStep(0.5)
        self._spin_grid_width.setDecimals(1)
        self._spin_grid_width.valueChanged.connect(self._on_grid_style_changed)
        grid_style_row.addWidget(self._spin_grid_width)
        grid_style_row.addStretch(1)
        grid_layout.addLayout(grid_style_row)

        layout.addWidget(grid_group)

        return group

    def _make_color_swatch(self, key: str) -> QPushButton:
        button = QPushButton()
        button.setFixedSize(40, 22)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(self._color_swatch_tooltip(key))
        button.clicked.connect(lambda: self._pick_color(key))
        self._color_buttons[key] = button
        self._update_swatch(key)
        return button

    def _color_swatch_tooltip(self, key: str) -> str:
        color = self._current_color(key)
        return f"{tr('Color')}: {color.name(QColor.HexArgb)}"

    def _current_color(self, key: str) -> QColor:
        hex_val = self._color_pending.get(key)
        if hex_val:
            color = QColor(hex_val)
            if color.isValid():
                return color
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
        initial = self._current_color(key)
        color = QColorDialog.getColor(
            initial, self, tr("Choose {0} color").format(self._color_label(key)),
            QColorDialog.ShowAlphaChannel,
        )
        if color.isValid():
            self._color_pending[key] = color.name(QColor.HexArgb)
            self._update_swatch(key)

    def _color_label(self, key: str) -> str:
        labels = {
            "outline": tr("Outline"),
            "paste_top": tr("Paste Top"),
            "paste_bottom": tr("Paste Bottom"),
            "silk": tr("Silkscreen"),
            "cross": tr("Crosshair"),
            "highlight": tr("Highlight"),
        }
        return labels.get(key, key)

    def _open_display_dialog(self) -> None:
        self._display_snapshot = self.display_settings()
        self._btn_save_disp.setEnabled(True)
        self._progress_save.setVisible(False)
        self._lbl_saving.setVisible(False)
        self._display_dialog.exec()

    def _on_arrow_size_changed(self, value: int) -> None:
        self._arrow_min_px = float(value)

    def _on_crosshair_scale_changed(self, value: float) -> None:
        self._crosshair_scale = float(value)

    def _on_frame_toggled(self, checked: bool) -> None:
        self._show_frame = bool(checked)

    def _start_load(self) -> None:
        if not self._gko_path or not os.path.exists(self._gko_path):
            QMessageBox.critical(self, tr("Error"), tr("No valid GKO file."))
            self.close()
            return
        self._worker = GerberLoadWorker(
            self._gko_path, self._gtp_path, self._gbp_path,
            self._gto_path, self._gbo_path, self,
        )
        self._worker.progress.connect(self._on_load_progress)
        self._worker.finished.connect(self._on_load_finished)
        self._worker.failed.connect(self._on_load_failed)
        self._worker.start()

    def _on_load_progress(self, message: str, _pct: int) -> None:
        self._lbl_title.setText(message)

    def _on_load_finished(self, data: dict) -> None:
        self._outline = data.get("outline", RenderData())
        self._top = data.get("top", RenderData())
        self._bottom = data.get("bottom", RenderData())
        self._silk = data.get("silk", RenderData())
        self._silk_bottom = data.get("silk_bottom", RenderData())
        self._loaded = True
        self._board_center = self._compute_board_center()
        self._cross_half = self._board_size() * _CROSS_BOARD_RATIO
        self._apply_layer()
        self._redraw()
        self._fit_scene()
        self._lbl_title.setText(tr("Gerber View - Overlay PickPlace"))
        self._lbl_status.setText(
            tr("Outline: {ol} lines, {of} pads | Top: {tf} pads | Bottom: {bf} pads | "
               "Silk Top: {st} lines | Silk Bottom: {sb} lines",
               ol=len(self._outline.lines), of=len(self._outline.flashes),
               tf=len(self._top.flashes), bf=len(self._bottom.flashes),
               st=len(self._silk.lines), sb=len(self._silk_bottom.lines))
        )
        self._btn_measure.setEnabled(True)
        self._btn_snap.setEnabled(True)

    def _on_load_failed(self, message: str) -> None:
        self._lbl_title.setText(tr("Error reading Gerber file"))
        QMessageBox.critical(self, tr("Error"), tr("Cannot read Gerber:\n{message}", message=message))

    def _on_layer_changed(self) -> None:
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

    def _apply_layer(self) -> None:
        records = self._current_layer_records()
        search_text = self._search_input.text().strip().lower()
        self._table_components.setUpdatesEnabled(False)
        try:
            self._table_components.setRowCount(0)
            self._component_index = []
            self._group_rows = []
            if self._group_by_mpn:
                self._fill_grouped_table(records, search_text)
                self._table_components.setColumnCount(5)
                self._table_components.setHorizontalHeaderLabels([
                    tr("#"), tr("MPN"), tr("Designator"), tr("Qty"), tr("Status"),
                ])
                self._table_components.horizontalHeader().setSectionResizeMode(
                    2, QHeaderView.Interactive
                )
                self._table_components.setColumnWidth(2, 200)
            else:
                self._table_components.setColumnCount(6)
                self._table_components.setHorizontalHeaderLabels([
                    tr("#"), tr("Designator"), tr("X"), tr("Y"), tr("Rot"), tr("Status"),
                ])
                self._table_components.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeToContents
                )
                for i, record in enumerate(records):
                    if not self._record_matches_search(record, search_text):
                        continue
                    x, y, rotation = _record_coord(record)
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
        finally:
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

    def _on_full_cross_toggled(self, checked: bool) -> None:
        self._view.set_full_crosshair_enabled(bool(checked))

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

    @staticmethod
    def _component_info_text(record: ReviewRecord) -> str:
        return tr(
            "Designator: {des}\nMPN: {mpn}\nRemark: {remark}",
            des=record.designator or "-",
            mpn=record.mpn or "-",
            remark=record.remark or "-",
        )

    @staticmethod
    def _status_icon(checked: bool) -> QIcon:
        global _ICON_CHECKED, _ICON_UNCHECKED
        if _ICON_CHECKED is None:
            _ICON_CHECKED = _build_status_icon(True)
        if _ICON_UNCHECKED is None:
            _ICON_UNCHECKED = _build_status_icon(False)
        return _ICON_CHECKED if checked else _ICON_UNCHECKED

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

    def _current_paste(self) -> RenderData:
        return self._top if self._combo_layer.currentIndex() == 0 else self._bottom

    def _update_coord_label(self, x: float, y: float) -> None:
        if not self._loaded:
            return
        self._lbl_coord.setText(tr("X: {gx:.2f}  Y: {gy:.2f}", gx=x, gy=-y))

    def _clear_coord_label(self) -> None:
        self._lbl_coord.setText(tr("X: --  Y: --"))

    def _goto_coord(self) -> None:
        if not self._loaded:
            return
        gx = self._spin_goto_x.value()
        gy = self._spin_goto_y.value()
        self._goto_pos = (gx, -gy)
        self._update_goto_crosshair()
        self._view.centerOn(gx, -gy)
        self._update_magnifier(gx, -gy)

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
        self._goto_crosshair.setZValue(100)

    def _on_grid_toggled(self, checked: bool) -> None:
        if checked and not self._grid_available:
            self._chk_grid.setChecked(False)
            return
        self._grid_active = checked
        self._view._grid_active = checked
        self._view.setDragMode(
            QGraphicsView.NoDrag if checked else QGraphicsView.ScrollHandDrag
        )
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
        self._grid_item.setZValue(60)
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
        angle = self._combo_rot.currentData() or 0
        if self._chk_invert_rot.isChecked():
            angle = (360 - angle) % 360
        return (
            angle,
            self._chk_flip.isChecked(),
            self._chk_mirror_x.isChecked(),
            self._spin_off_x.value(),
            self._spin_off_y.value(),
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

    def _on_measure_toggled(self, checked: bool) -> None:
        if not self._loaded and checked:
            self._btn_measure.blockSignals(True)
            self._btn_measure.setChecked(False)
            self._btn_measure.blockSignals(False)
            return
        self._measure_mode = bool(checked)
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

    def _on_compact_toggled(self, checked: bool) -> None:
        self._compact_hidden = not bool(checked)
        widget = getattr(self, "_options_widget", None)
        if widget is not None:
            widget.setVisible(checked)
        lbl = getattr(self, "_lbl_status", None)
        if lbl is not None:
            lbl.setVisible(checked)

    def _snap_info(self, gx: float, gy: float) -> Optional[Tuple[float, float, float]]:
        if not getattr(self, "_snap_enabled", True):
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
            self._measure_preview.setZValue(79)
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
            self._measure_snap_item.setZValue(78)
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
        self._btn_clear_measure.setEnabled(True)
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
        self._btn_clear_measure.setEnabled(False)
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
        self._btn_clear_measure.setEnabled(bool(self._measurements))

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
                x, y, _rot = _record_coord(records[self._selected_marker_index])
                self._update_magnifier(x, -y)

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
        x, y, _rotation = _record_coord(records[idx])
        self._update_magnifier(x, -y)

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

        # If a dialog is already open, close it first
        if self._rotation_dialog is not None:
            try:
                self._rotation_dialog.close()
            except RuntimeError:
                pass
            self._rotation_dialog = None

        # Auto-jump view to the component being edited
        self._center_view_on(x, -y)

        # Boost magnifier zoom for detailed inspection during rotation edit
        self._rot_mag_saved = self._mag_factor
        self._set_mag_factor(_ROT_EDIT_MAG_FACTOR)
        # Lock magnifier on this component while editing
        self._rotation_lock_xy = (x, -y)

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

    def _render_lines(
        self,
        render_data: RenderData,
        color: QColor,
        angle: float,
        mirror: bool,
        off_x: float,
        off_y: float,
        mirror_x: bool = False,
        key: str = "",
    ) -> List[QGraphicsPathItem]:
        if not render_data.lines and not render_data.arcs:
            self._line_items[key] = []
            return []
        center_x, center_y = self._board_center
        try:
            scale = abs(self._view.transform().m11())
        except Exception:
            scale = self._scene_scale
        min_w = (1.0 / scale) if scale > 0 else 1.05
        buckets: Dict[float, QPainterPath] = {}
        for ln in render_data.lines:
            w = round(max(ln.width, min_w), 3)
            path = buckets.get(w)
            if path is None:
                path = QPainterPath()
                buckets[w] = path
            x1, y1, x2, y2 = ln.x1, ln.y1, ln.x2, ln.y2
            x1, y1 = apply_transform(x1, y1, mirror, angle, off_x, off_y, center_x, center_y, mirror_x)
            x2, y2 = apply_transform(x2, y2, mirror, angle, off_x, off_y, center_x, center_y, mirror_x)
            path.moveTo(x1, -y1)
            path.lineTo(x2, -y2)
        for ar in render_data.arcs:
            w = round(max(ar.width, min_w), 3)
            path = buckets.get(w)
            if path is None:
                path = QPainterPath()
                buckets[w] = path
            _append_arc_path(path, ar, mirror, angle, off_x, off_y, center_x, center_y, mirror_x)
        items: List[QGraphicsPathItem] = []
        for w, path in buckets.items():
            pen = QPen(color, w)
            pen.setCosmetic(False)
            items.append(self._scene.addPath(path, pen))
        self._line_items[key] = items
        return items

    def _render_fills(
        self,
        render_data: RenderData,
        color: QColor,
        angle: float,
        mirror: bool,
        off_x: float,
        off_y: float,
        mirror_x: bool = False,
        key: str = "",
    ) -> Optional[QGraphicsPathItem]:
        if not render_data.flashes:
            self._fill_items[key] = None
            return None
        center_x, center_y = self._board_center
        final = _build_fill_path(
            render_data.flashes, mirror, angle, off_x, off_y,
            center_x, center_y, mirror_x,
        )
        item = self._scene.addPath(final, QPen(Qt.NoPen), QBrush(color))
        self._fill_items[key] = item
        return item

    def _redraw(self) -> None:
        if not self._loaded:
            return

        angle = self._combo_rot.currentData() or 0
        if self._chk_invert_rot.isChecked():
            angle = (360 - angle) % 360
        mirror = self._chk_flip.isChecked()
        mirror_x = self._chk_mirror_x.isChecked()
        off_x = self._spin_off_x.value()
        off_y = self._spin_off_y.value()
        is_top = self._combo_layer.currentIndex() == 0
        try:
            key_scale = round(abs(self._view.transform().m11()), 4)
        except Exception:
            key_scale = self._scene_scale
        key = (is_top, angle, mirror, mirror_x, round(off_x, 4), round(off_y, 4), key_scale)

        if self._scene_key != key:
            self._scene_key = key
            self._rebuild_scene(angle, mirror, mirror_x, off_x, off_y, is_top)
        else:
            self._apply_style(angle, mirror, mirror_x, off_x, off_y, is_top)

        self._restore_highlight()
        self._refresh_magnifier()

    def _rebuild_scene(
        self, angle: float, mirror: bool, mirror_x: bool,
        off_x: float, off_y: float, is_top: bool,
    ) -> None:
        self._scene.clear()
        self._overlay = None
        self._goto_crosshair = None
        self._grid_item = None
        self._measure_preview = None
        self._measure_snap_item = None
        self._line_items = {}
        self._fill_items = {}
        self._apply_style(angle, mirror, mirror_x, off_x, off_y, is_top)
        self._update_goto_crosshair()
        self._update_grid()
        self._rebuild_measurements()

    def _marker_tuples(self) -> List[Tuple[float, float, float, float]]:
        """Build marker tuples (x, -y, rotation, half) for current layer records.

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
            markers.append((x, -y, rotation, half))
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
    ) -> None:
        paste = self._top if is_top else self._bottom
        silk = self._silk if is_top else self._silk_bottom

        if self._chk_outline.isChecked():
            if "outline" not in self._line_items:
                self._render_lines(
                    self._outline, self._colors["outline"], angle, mirror,
                    off_x, off_y, mirror_x, "outline",
                )
        if self._chk_silk.isChecked():
            if "silk" not in self._line_items:
                self._render_lines(
                    silk, self._colors["silk"], angle, mirror,
                    off_x, off_y, mirror_x, "silk",
                )
            if "silk" not in self._fill_items:
                self._render_fills(
                    silk, self._colors["silk"], angle, mirror,
                    off_x, off_y, mirror_x, "silk",
                )
        if self._chk_paste.isChecked():
            paste_color = self._colors["paste_top"] if is_top else self._colors["paste_bottom"]
            if "paste" not in self._line_items:
                self._render_lines(
                    paste, paste_color, angle, mirror,
                    off_x, off_y, mirror_x, "paste",
                )
            if "paste" not in self._fill_items:
                self._render_fills(
                    paste, paste_color, angle, mirror,
                    off_x, off_y, mirror_x, "paste",
                )

        self._update_layer_visibility("outline", self._chk_outline.isChecked(), self._colors["outline"])
        self._update_layer_visibility("silk", self._chk_silk.isChecked(), self._colors["silk"])
        self._update_fill_visibility("silk", self._chk_silk.isChecked(), self._colors["silk"])
        paste_color = self._colors["paste_top"] if is_top else self._colors["paste_bottom"]
        self._update_layer_visibility("paste", self._chk_paste.isChecked(), paste_color)
        self._update_fill_visibility("paste", self._chk_paste.isChecked(), paste_color)

        if self._chk_pickplace.isChecked():
            self._rebuild_marker_overlay()
        elif self._overlay is not None:
            self._scene.removeItem(self._overlay)
            self._overlay = None

    def _update_layer_visibility(self, key: str, visible: bool, color: QColor) -> None:
        items = self._line_items.get(key)
        if not items:
            return
        valid_items = []
        for item in items:
            try:
                item.setVisible(visible)
                pen = item.pen()
                pen.setColor(color)
                item.setPen(pen)
                valid_items.append(item)
            except RuntimeError:
                pass
        if len(valid_items) != len(items):
            self._line_items[key] = valid_items

    def _update_fill_visibility(self, key: str, visible: bool, color: QColor) -> None:
        item = self._fill_items.get(key)
        if item is None:
            return
        try:
            item.setVisible(visible)
            item.setBrush(QBrush(color))
        except RuntimeError:
            self._fill_items[key] = None

    def _pad_grid(self, is_top: bool) -> PadGrid:
        grid = self._pad_grid_cache.get(is_top)
        if grid is None:
            paste = self._top if is_top else self._bottom
            pads = [(f.cx, f.cy, _flash_size(f)) for f in paste.flashes]
            grid = PadGrid(pads)
            self._pad_grid_cache[is_top] = grid
        return grid

    def _gerber_content_bbox(self) -> Tuple[float, float, float, float]:
        for data in (self._outline, self._top, self._bottom):
            if data.lines or data.arcs or data.flashes:
                return data.bbox()
        return 0.0, 0.0, 0.0, 0.0

    def _gerber_scene_rect(self) -> QRectF:
        min_x, min_y, max_x, max_y = self._gerber_content_bbox()
        angle = self._combo_rot.currentData() or 0
        if self._chk_invert_rot.isChecked():
            angle = (360 - angle) % 360
        mirror = self._chk_flip.isChecked()
        mirror_x = self._chk_mirror_x.isChecked()
        off_x = self._spin_off_x.value()
        off_y = self._spin_off_y.value()
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

    def _compute_board_center(self) -> Tuple[float, float]:
        xs, ys = [], []
        for ln in self._outline.lines:
            xs += [ln.x1, ln.x2]
            ys += [ln.y1, ln.y2]
        for ar in self._outline.arcs:
            xs += [ar.x1, ar.x2]
            ys += [ar.y1, ar.y2]
        for fl in self._outline.flashes:
            xs.append(fl.cx)
            ys.append(fl.cy)
        if not xs:
            for fl in self._top.flashes + self._bottom.flashes:
                xs.append(fl.cx)
                ys.append(fl.cy)
        if not xs:
            return 0.0, 0.0
        return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0

    def _board_size(self) -> float:
        xs, ys = [], []
        for ln in self._outline.lines:
            xs += [ln.x1, ln.x2]
            ys += [ln.y1, ln.y2]
        for ar in self._outline.arcs:
            xs += [ar.x1, ar.x2]
            ys += [ar.y1, ar.y2]
        for fl in self._outline.flashes:
            xs.append(fl.cx)
            ys.append(fl.cy)
        if not xs:
            for fl in self._top.flashes + self._bottom.flashes:
                xs.append(fl.cx)
                ys.append(fl.cy)
        if not xs:
            return 1.0
        return max(max(xs) - min(xs), max(ys) - min(ys))

    def _reset_offset(self) -> None:
        self._spin_off_x.setValue(0.0)
        self._spin_off_y.setValue(0.0)
        self._chk_flip.setChecked(False)
        self._chk_mirror_x.setChecked(False)

    def _outline_min_corner(self) -> Tuple[float, float]:
        if self._outline.lines or self._outline.arcs or self._outline.flashes:
            min_x, min_y, _max_x, _max_y = self._outline.bbox()
            return min_x, min_y
        for data in (self._top, self._bottom):
            if data.lines or data.arcs or data.flashes:
                min_x, min_y, _max_x, _max_y = data.bbox()
                return min_x, min_y
        return 0.0, 0.0

    def _bring_gerber_to_origin(self) -> None:
        if not self._loaded:
            return
        angle = self._combo_rot.currentData() or 0
        if self._chk_invert_rot.isChecked():
            angle = (360 - angle) % 360
        mirror = self._chk_flip.isChecked()
        mirror_x = self._chk_mirror_x.isChecked()
        center_x, center_y = self._board_center
        min_x, min_y = self._outline_min_corner()
        tx, ty = apply_transform(min_x, min_y, mirror, angle, 0.0, 0.0, center_x, center_y, mirror_x)
        self._spin_off_x.setValue(-tx)
        self._spin_off_y.setValue(-ty)

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
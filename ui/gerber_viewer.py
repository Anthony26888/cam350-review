import math
import os
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, QThread, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QPen, QPainter, QPainterPath, QPolygonF,
    QWheelEvent, QFont, QTransform, QPixmap, QMouseEvent, QIcon,
)
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QComboBox,
    QCheckBox, QGroupBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDoubleSpinBox, QWidget, QDialog,
)

from models.review import ReviewRecord
from services.gerber.gerber_render import (
    RenderData, LineShape, FlashShape, parse_render,
)
from services.gerber.gerber_transform import apply_transform, transform_rot
from utils.path_utils import resource_path

OUTLINE_COLOR = QColor("#F8FAFC")
TOP_PASTE_COLOR = QColor(34, 211, 238, 210)
BOTTOM_PASTE_COLOR = QColor(251, 191, 36, 210)
SILK_COLOR = QColor(240, 171, 252, 220)
CROSS_COLOR = QColor("#EF4444")
HIGHLIGHT_COLOR = QColor("#39FF14")
BACKGROUND = QColor("#0B1220")

_CROSS_BOARD_RATIO = 0.01


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


def _crosshair_half(size: Optional[float], fallback: float) -> float:
    if size is None:
        return fallback
    return min(max(size * 1.15, 0.15), fallback)


_MAG_FACTOR = 5.0
_MAG_MIN_SCALE = 24.0


def _magnifier_scale(board_size: float, vw: int, vh: int) -> float:
    base = min(float(vw), float(vh)) / max(board_size, 1.0)
    return max(base * _MAG_FACTOR, _MAG_MIN_SCALE)


def _add_flash(
    path: QPainterPath,
    fl: FlashShape,
    mirror: bool = False,
    angle: float = 0.0,
    off_x: float = 0.0,
    off_y: float = 0.0,
    cx0: float = 0.0,
    cy0: float = 0.0,
) -> None:
    """Append one flash to `path` with the display transform applied.

    All geometry (position, polygon vertices, aperture-macro primitives) is
    transformed by the same mirror -> rotate -> offset pipeline used for
    stroked lines, so every layer rotates together.
    """
    def _t_abs(x: float, y: float) -> Tuple[float, float]:
        return apply_transform(x, y, mirror, angle, off_x, off_y, cx0, cy0)

    def _t_loc(x: float, y: float) -> Tuple[float, float]:
        return apply_transform(x, y, mirror, angle, 0.0, 0.0, 0.0, 0.0)

    rot = transform_rot(fl.rot, mirror, angle)

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
        path.addPolygon(QPolygonF(pts))
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
            path.addPolygon(QPolygonF(pts))
        for x1, y1, x2, y2, width in m.segments:
            lx1, ly1 = _t_loc(x1, y1)
            lx2, ly2 = _t_loc(x2, y2)
            ang = math.atan2(ly2 - ly1, lx2 - lx1)
            n2 = width / 2.0
            dx, dy = math.cos(ang) * n2, math.sin(ang) * n2
            quad = [
                QPointF(gx + lx1 + dx, -gy - ly1 - dy),
                QPointF(gx + lx1 - dx, -gy - ly1 + dy),
                QPointF(gx + lx2 - dx, -gy - ly2 + dy),
                QPointF(gx + lx2 + dx, -gy - ly2 - dy),
            ]
            path.addPolygon(QPolygonF(quad))


def _add_rect_path(path: QPainterPath, gx, gy, w, h, rot):
    hw, hh = w / 2.0, h / 2.0
    c, s = math.cos(rot), math.sin(rot)
    pts = []
    for cx0, cy0 in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
        rx = cx0 * c - cy0 * s
        ry = cx0 * s + cy0 * c
        pts.append(QPointF(gx + rx, -gy - ry))
    path.addPolygon(QPolygonF(pts))


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
    path.addPolygon(QPolygonF(out))


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
                 show_unselected: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._markers = markers  # (x, -y, rot_deg, half)
        self._show_unselected = show_unselected
        self._selected = -1
        self._rect = self._compute_rect()
        self._build_geom()

    def _compute_rect(self) -> QRectF:
        if not self._markers:
            return QRectF()
        pad = max(m[3] for m in self._markers) * 1.8
        xs = [m[0] for m in self._markers]
        ys = [m[1] for m in self._markers]
        return QRectF(min(xs) - pad, min(ys) - pad,
                      max(xs) - min(xs) + 2 * pad,
                      max(ys) - min(ys) + 2 * pad)

    def _build_geom(self) -> None:
        self._cross: Dict[float, QPainterPath] = {}
        self._arrow: Dict[float, QPolygonF] = {}
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
            self._arrow[h] = QPolygonF([
                QPointF(-1.4 * h, 0.0),
                QPointF(-h, -0.25 * h),
                QPointF(-h, 0.25 * h),
            ])

    def set_selected(self, index: int) -> None:
        if index != self._selected:
            self._selected = index
            self.update()

    def set_markers(self, markers: List[Tuple[float, float, float, float]]) -> None:
        self._markers = markers
        self._rect = self._compute_rect()
        self._build_geom()
        self.update()

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option=None, widget=None) -> None:
        if not self._markers:
            return
        pen = QPen(QColor(Qt.black), 2.5)
        pen.setCosmetic(True)
        selected = self._selected
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        for i, (mx, my, rot, half) in enumerate(self._markers):
            is_selected = (i == selected)
            if not self._show_unselected and not is_selected:
                continue
            color = HIGHLIGHT_COLOR if is_selected else CROSS_COLOR
            painter.save()
            painter.translate(mx, my)
            if is_selected:
                hal = half * 1.8
                painter.setBrush(Qt.NoBrush)
                frame_pen = QPen(HIGHLIGHT_COLOR, 1.5)
                frame_pen.setCosmetic(True)
                painter.setPen(frame_pen)
                painter.drawRect(QRectF(-hal, -hal, 2 * hal, 2 * hal))
                painter.rotate(-rot)
                pen.setColor(color)
                pen.setWidthF(3.0)
                painter.setPen(pen)
                painter.drawPath(self._cross[half])
                painter.setBrush(color)
                painter.setPen(Qt.NoPen)
                painter.drawPolygon(self._arrow[half])
                painter.setBrush(Qt.NoBrush)
            else:
                painter.rotate(-rot)
                pen.setColor(color)
                pen.setWidthF(2.5)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(self._cross[half])
                painter.setBrush(color)
                painter.setPen(Qt.NoPen)
                painter.drawPolygon(self._arrow[half])
            painter.restore()
        painter.restore()


class GerberView(QGraphicsView):
    cursor_moved = Signal(float, float)
    cursor_left = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(BACKGROUND)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)

        self._drag_pixmap: Optional[QPixmap] = None
        self._drag_start: Optional[QPoint] = None
        self._drag_delta: QPoint = QPoint(0, 0)

        self._fast_render = False
        self._fast_timer: Optional[QTimer] = None

    def _set_fast_render(self) -> None:
        if self._fast_render:
            return
        self._fast_render = True
        self.setRenderHint(QPainter.SmoothPixmapTransform, False)

    def _restore_smooth_render(self) -> None:
        if not self._fast_render:
            return
        self._fast_render = False
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
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
        self._set_fast_render()
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)
        self._schedule_smooth_restore()

    def fit(self) -> None:
        rect = self.scene().itemsBoundingRect()
        if not rect.isNull():
            self.fitInView(rect, Qt.KeepAspectRatio)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pixmap = self.viewport().grab()
            self._drag_start = event.position().toPoint()
            self._drag_delta = QPoint(0, 0)
            self._set_fast_render()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        sp = self.mapToScene(event.position().toPoint())
        self.cursor_moved.emit(sp.x(), sp.y())
        if self._drag_start is not None:
            pos = event.position().toPoint()
            self._drag_delta = pos - self._drag_start
            self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.cursor_left.emit()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is not None and event.button() == Qt.LeftButton:
            self._finish_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _finish_drag(self) -> None:
        dx = self._drag_delta.x()
        dy = self._drag_delta.y()
        self._drag_pixmap = None
        self._drag_start = None
        self._drag_delta = QPoint(0, 0)
        self.unsetCursor()
        if dx == 0 and dy == 0:
            return
        hbar = self.horizontalScrollBar()
        vbar = self.verticalScrollBar()
        hbar.setValue(hbar.value() - dx)
        vbar.setValue(vbar.value() - dy)
        self._restore_smooth_render()
        self.viewport().update()

    def paintEvent(self, event: object) -> None:
        if self._drag_pixmap is not None and self._drag_start is not None:
            painter = QPainter(self.viewport())
            painter.fillRect(self.viewport().rect(), self.backgroundBrush())
            painter.drawPixmap(self._drag_start + self._drag_delta, self._drag_pixmap)
            painter.end()
            event.accept()
            return
        super().paintEvent(event)


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
            self.progress.emit("Đang đọc GKO (outline)...", 12)
            data["outline"] = parse_render(self._gko)

            data["top"] = RenderData()
            data["bottom"] = RenderData()
            data["silk"] = RenderData()
            data["silk_bottom"] = RenderData()

            if self._gtp and os.path.exists(self._gtp):
                self.progress.emit("Đang đọc GTP (Top Paste)...", 30)
                data["top"] = parse_render(self._gtp)
            if self._gbp and os.path.exists(self._gbp):
                self.progress.emit("Đang đọc GBP (Bottom Paste)...", 45)
                data["bottom"] = parse_render(self._gbp)
            if self._gto and os.path.exists(self._gto):
                self.progress.emit("Đang đọc GTO (Silkscreen)...", 60)
                data["silk"] = parse_render(self._gto)
            if self._gbo and os.path.exists(self._gbo):
                self.progress.emit("Đang đọc GBO (Silkscreen)...", 75)
                data["silk_bottom"] = parse_render(self._gbo)

            self.progress.emit("Hoàn tất.", 100)
            self.finished.emit(data)
        except Exception as e:
            self.failed.emit(str(e))


class GerberViewer(QWidget):
    settings_saved = Signal(dict)

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
        self.setWindowTitle("Gerber View — Overlay PickPlace")
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
        self._overlay: Optional[MarkerOverlayItem] = None
        self._board_center: Tuple[float, float] = (0.0, 0.0)
        self._cross_half = _CROSS_BOARD_RATIO
        self._selected_marker_index = -1
        self._component_index: List[int] = []
        self._scene_scale = 1.0
        self._mag_target: Optional[Tuple[float, float]] = None

        self._build_ui()
        self._apply_layer()
        self.apply_display_settings(display_settings or {})
        self._start_load()

    def display_settings(self) -> Dict[str, Any]:
        return {
            "layer": self._combo_layer.currentIndex(),
            "rotation": self._combo_rot.currentData() or 0,
            "invert_rot": self._chk_invert_rot.isChecked(),
            "flip": self._chk_flip.isChecked(),
            "offset_x": self._spin_off_x.value(),
            "offset_y": self._spin_off_y.value(),
            "outline": self._chk_outline.isChecked(),
            "paste": self._chk_paste.isChecked(),
            "silk": self._chk_silk.isChecked(),
            "pickplace": self._chk_pickplace.isChecked(),
            "crosshair": self._chk_crosshair.isChecked(),
        }

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
        self._spin_off_x.setValue(float(settings.get("offset_x", 0.0)))
        self._spin_off_y.setValue(float(settings.get("offset_y", 0.0)))
        self._chk_outline.setChecked(bool(settings.get("outline", True)))
        self._chk_paste.setChecked(bool(settings.get("paste", True)))
        self._chk_silk.setChecked(bool(settings.get("silk", True)))
        self._chk_pickplace.setChecked(bool(settings.get("pickplace", True)))
        self._chk_crosshair.setChecked(bool(settings.get("crosshair", True)))

    def _save_display_settings(self) -> None:
        self.settings_saved.emit(self.display_settings())
        self._lbl_status.setText("Đã lưu thông số hiển thị vào session.")
        self._display_dialog.accept()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        _logo_pm = QPixmap(resource_path("assets/icon.ico"))
        if not _logo_pm.isNull():
            _logo = QLabel()
            _logo.setPixmap(_logo_pm.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            top_bar.addWidget(_logo)
        self._lbl_title = QLabel("Đang đọc file Gerber...")
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

        btn_row = QHBoxLayout()
        btn_disp = QPushButton("Hiển thị…")
        btn_disp.clicked.connect(self._open_display_dialog)
        btn_fit = QPushButton("Fit View")
        btn_fit.clicked.connect(self._fit_scene)
        btn_reset = QPushButton("Reset")
        btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(btn_disp)
        btn_row.addWidget(btn_fit)
        btn_row.addWidget(btn_reset)
        panel.addLayout(btn_row)

        layer_row = QHBoxLayout()
        layer_row.addWidget(QLabel("Layer:"))
        self._combo_layer = QComboBox()
        self._combo_layer.addItem("Top layer (GKO + GTP)")
        self._combo_layer.addItem("Bottom layer (GKO + GBP)")
        self._combo_layer.currentIndexChanged.connect(self._on_layer_changed)
        layer_row.addWidget(self._combo_layer, 1)
        panel.addLayout(layer_row)

        panel.addWidget(QLabel("Components:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Tìm component...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._apply_layer)
        panel.addWidget(self._search_input)

        self._table_components = QTableWidget()
        self._table_components.setColumnCount(4)
        self._table_components.setHorizontalHeaderLabels(["Designator", "X", "Y", "Rot"])
        self._table_components.setSelectionBehavior(QTableWidget.SelectRows)
        self._table_components.setSelectionMode(QTableWidget.SingleSelection)
        self._table_components.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table_components.verticalHeader().setVisible(False)
        self._table_components.horizontalHeader().setStretchLastSection(True)
        self._table_components.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table_components.currentCellChanged.connect(self._on_row_changed)
        self._table_components.cellDoubleClicked.connect(self._on_component_double_clicked)
        panel.addWidget(self._table_components, 1)

        self._lbl_status = QLabel("Chưa có dữ liệu.")
        self._lbl_status.setWordWrap(True)
        panel.addWidget(self._lbl_status)

        mag_group = QGroupBox("Chi tiết (Zoom 5x)")
        mag_layout = QVBoxLayout(mag_group)
        mag_layout.setSpacing(4)
        self._mag_view = QGraphicsView()
        self._mag_view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self._mag_view.setBackgroundBrush(BACKGROUND)
        self._mag_view.setInteractive(False)
        self._mag_view.setDragMode(QGraphicsView.NoDrag)
        self._mag_view.setTransformationAnchor(QGraphicsView.NoAnchor)
        self._mag_view.setResizeAnchor(QGraphicsView.NoAnchor)
        self._mag_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._mag_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._mag_view.setMinimumSize(300, 220)
        self._mag_view.setMaximumHeight(260)
        self._mag_view.setScene(self._scene)
        mag_layout.addWidget(self._mag_view)
        self._lbl_mag_hint = QLabel("Rê chuột trên bản vẽ / chọn linh kiện để xem chi tiết.")
        self._lbl_mag_hint.setWordWrap(True)
        mag_layout.addWidget(self._lbl_mag_hint)
        panel.addWidget(mag_group)

        self._view.cursor_moved.connect(self._update_magnifier)
        self._view.cursor_left.connect(self._refresh_magnifier)

        self._display_dialog = QDialog(self)
        self._display_dialog.setWindowTitle("Tùy chỉnh hiển thị")
        display_layout = QVBoxLayout(self._display_dialog)
        display_layout.addWidget(self._build_display_group())
        btn_save_disp = QPushButton("Lưu thông số hiển thị")
        btn_save_disp.clicked.connect(self._save_display_settings)
        display_layout.addWidget(btn_save_disp)

        panel_widget = QWidget()
        panel_widget.setLayout(panel)
        panel_widget.setFixedWidth(320)
        body.addWidget(panel_widget)

        layout.addLayout(body, 1)

    def _build_display_group(self) -> QGroupBox:
        group = QGroupBox("Hiển thị")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Xoay Gerber:"))
        self._combo_rot = QComboBox()
        for angle in (0, 90, 180, 270):
            self._combo_rot.addItem(f"{angle}°", angle)
        self._combo_rot.currentIndexChanged.connect(self._redraw)
        rot_row.addWidget(self._combo_rot, 1)
        layout.addLayout(rot_row)

        self._chk_invert_rot = QCheckBox("Đảo chiều xoay gerber")
        self._chk_invert_rot.toggled.connect(self._redraw)
        layout.addWidget(self._chk_invert_rot)

        self._chk_flip = QCheckBox("Lật Gerber (Mirror Y)")
        self._chk_flip.toggled.connect(self._redraw)
        layout.addWidget(self._chk_flip)

        off_row = QHBoxLayout()
        off_row.addWidget(QLabel("Offset X:"))
        self._spin_off_x = QDoubleSpinBox()
        self._spin_off_x.setRange(-100.0, 100.0)
        self._spin_off_x.setSingleStep(0.05)
        self._spin_off_x.setDecimals(2)
        self._spin_off_x.setValue(0.0)
        self._spin_off_x.valueChanged.connect(self._redraw)
        off_row.addWidget(self._spin_off_x, 1)
        off_row.addWidget(QLabel("Y:"))
        self._spin_off_y = QDoubleSpinBox()
        self._spin_off_y.setRange(-100.0, 100.0)
        self._spin_off_y.setSingleStep(0.05)
        self._spin_off_y.setDecimals(2)
        self._spin_off_y.setValue(0.0)
        self._spin_off_y.valueChanged.connect(self._redraw)
        off_row.addWidget(self._spin_off_y, 1)
        btn_zero = QPushButton("0")
        btn_zero.clicked.connect(self._reset_offset)
        off_row.addWidget(btn_zero)
        layout.addLayout(off_row)

        self._chk_outline = QCheckBox("Hiện Outline GKO")
        self._chk_outline.setChecked(True)
        self._chk_outline.toggled.connect(self._redraw)
        layout.addWidget(self._chk_outline)

        self._chk_paste = QCheckBox("Hiện Paste (GTP / GBP)")
        self._chk_paste.setChecked(True)
        self._chk_paste.toggled.connect(self._redraw)
        layout.addWidget(self._chk_paste)

        self._chk_silk = QCheckBox("Hiện Silkscreen (GTO / GBO)")
        self._chk_silk.setChecked(True)
        self._chk_silk.toggled.connect(self._redraw)
        layout.addWidget(self._chk_silk)

        self._chk_pickplace = QCheckBox("Hiện PickPlace (đã align)")
        self._chk_pickplace.setChecked(True)
        self._chk_pickplace.toggled.connect(self._redraw)
        layout.addWidget(self._chk_pickplace)

        self._chk_crosshair = QCheckBox("Hiện Crosshair")
        self._chk_crosshair.setChecked(True)
        self._chk_crosshair.toggled.connect(self._redraw)
        layout.addWidget(self._chk_crosshair)

        return group

    def _open_display_dialog(self) -> None:
        self._display_dialog.exec()

    def _start_load(self) -> None:
        if not self._gko_path or not os.path.exists(self._gko_path):
            QMessageBox.critical(self, "Error", "Không có file GKO hợp lệ.")
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
        self._lbl_title.setText("Gerber View — Overlay PickPlace")
        self._lbl_status.setText(
            f"Outline: {len(self._outline.lines)} nét, {len(self._outline.flashes)} pad | "
            f"Top: {len(self._top.flashes)} pad | Bottom: {len(self._bottom.flashes)} pad | "
            f"Silk Top: {len(self._silk.lines)} nét | Silk Bottom: {len(self._silk_bottom.lines)} nét"
        )

    def _on_load_failed(self, message: str) -> None:
        self._lbl_title.setText("Lỗi đọc file Gerber")
        QMessageBox.critical(self, "Error", f"Không thể đọc Gerber:\n{message}")

    def _on_layer_changed(self) -> None:
        self._apply_layer()
        self._redraw()

    def _apply_layer(self) -> None:
        records = self._current_layer_records()
        search_text = self._search_input.text().strip().lower()
        self._table_components.setRowCount(0)
        self._component_index = []
        for i, record in enumerate(records):
            if search_text and search_text not in record.designator.lower():
                continue
            x, y, rotation = _record_coord(record)
            values = [
                record.designator,
                f"{x:.3f}",
                f"{y:.3f}",
                f"{rotation:.0f}°",
            ]
            row = self._table_components.rowCount()
            self._table_components.insertRow(row)
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table_components.setItem(row, col, item)
            self._component_index.append(i)
        self._restore_highlight()

    def _current_layer_records(self) -> List[ReviewRecord]:
        layer = "top" if self._combo_layer.currentIndex() == 0 else "bottom"
        return [r for r in self._records if _layer_key(r.layer) == layer]

    def _restore_highlight(self) -> None:
        overlay = getattr(self, "_overlay", None)
        if overlay is not None:
            overlay.set_selected(self._selected_marker_index)

    def _current_paste(self) -> RenderData:
        return self._top if self._combo_layer.currentIndex() == 0 else self._bottom

    def _update_magnifier(self, x: float, y: float) -> None:
        if not self._loaded:
            return
        self._mag_target = (x, y)
        self._refresh_magnifier()

    def _refresh_magnifier(self) -> None:
        if not self._loaded or self._mag_target is None:
            return
        vp = self._mag_view.viewport()
        vw = max(vp.width(), 1)
        vh = max(vp.height(), 1)
        scale = _magnifier_scale(self._board_size(), vw, vh)
        x, y = self._mag_target
        self._mag_view.setTransform(QTransform().fromScale(scale, scale))
        self._mag_view.centerOn(x, y)

    def _on_row_changed(self, current_row: int, _col: int = 0,
                        _prev_row: int = -1, _prev_col: int = -1) -> None:
        if 0 <= current_row < len(self._component_index):
            self._selected_marker_index = self._component_index[current_row]
        else:
            self._selected_marker_index = -1
        self._restore_highlight()
        if self._selected_marker_index >= 0:
            records = self._current_layer_records()
            if self._selected_marker_index < len(records):
                x, y, _rot = _record_coord(records[self._selected_marker_index])
                self._update_magnifier(x, -y)

    def _on_component_double_clicked(self, row: int, _col: int) -> None:
        if not (0 <= row < len(self._component_index)):
            return
        idx = self._component_index[row]
        records = self._current_layer_records()
        if not (0 <= idx < len(records)):
            return
        x, y, _rotation = _record_coord(records[idx])
        self._update_magnifier(x, -y)

    def _render_lines(
        self,
        render_data: RenderData,
        color: QColor,
        angle: float,
        mirror: bool,
        off_x: float,
        off_y: float,
    ) -> None:
        if not render_data.lines:
            return
        center_x, center_y = self._board_center
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
            x1, y1 = apply_transform(x1, y1, mirror, angle, off_x, off_y, center_x, center_y)
            x2, y2 = apply_transform(x2, y2, mirror, angle, off_x, off_y, center_x, center_y)
            path.moveTo(x1, -y1)
            path.lineTo(x2, -y2)
        for w, path in buckets.items():
            pen = QPen(color, w)
            pen.setCosmetic(False)
            self._scene.addPath(path, pen)

    def _render_fills(
        self,
        render_data: RenderData,
        color: QColor,
        angle: float,
        mirror: bool,
        off_x: float,
        off_y: float,
    ) -> None:
        if not render_data.flashes:
            return
        center_x, center_y = self._board_center
        path = QPainterPath()
        for fl in render_data.flashes:
            _add_flash(path, fl, mirror, angle, off_x, off_y, center_x, center_y)
        self._scene.addPath(path, QPen(Qt.NoPen), QBrush(color))

    def _redraw(self) -> None:
        if not self._loaded:
            return
        self._scene.clear()
        self._overlay = None

        angle = self._combo_rot.currentData() or 0
        if self._chk_invert_rot.isChecked():
            angle = (360 - angle) % 360
        mirror = self._chk_flip.isChecked()
        off_x = self._spin_off_x.value()
        off_y = self._spin_off_y.value()

        is_top = self._combo_layer.currentIndex() == 0
        paste = self._top if is_top else self._bottom
        silk = self._silk if is_top else self._silk_bottom

        if self._chk_outline.isChecked():
            self._render_lines(self._outline, OUTLINE_COLOR, angle, mirror, off_x, off_y)
        if self._chk_silk.isChecked():
            self._render_lines(silk, SILK_COLOR, angle, mirror, off_x, off_y)
            self._render_fills(silk, SILK_COLOR, angle, mirror, off_x, off_y)
        if self._chk_paste.isChecked():
            self._render_fills(paste, TOP_PASTE_COLOR if is_top else BOTTOM_PASTE_COLOR, angle, mirror, off_x, off_y)

        if self._chk_pickplace.isChecked():
            center_x, center_y = self._board_center
            pads_raw = [
                (f.cx, f.cy, _flash_size(f))
                for f in paste.flashes
            ]
            self._pads = [
                (
                    *apply_transform(px, py, mirror, angle, off_x, off_y, center_x, center_y),
                    size,
                )
                for px, py, size in pads_raw
            ]
            markers = []
            for record in self._current_layer_records():
                x, y, rotation = _record_coord(record)
                size = _nearest_pad_size(pads_raw, x, y)
                half = _crosshair_half(size, self._cross_half)
                markers.append((x, -y, rotation, half))
            self._overlay = MarkerOverlayItem(
                markers, show_unselected=self._chk_crosshair.isChecked()
            )
            self._scene.addItem(self._overlay)

        self._restore_highlight()
        self._refresh_magnifier()

    def _fit_scene(self) -> None:
        self._view.fit()
        scale = self._view.transform().m11()
        if abs(scale - self._scene_scale) > 1e-6:
            self._scene_scale = scale
            self._redraw()

    def _compute_board_center(self) -> Tuple[float, float]:
        xs, ys = [], []
        for ln in self._outline.lines:
            xs += [ln.x1, ln.x2]
            ys += [ln.y1, ln.y2]
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

    def _on_reset(self) -> None:
        self._combo_rot.setCurrentIndex(0)
        self._chk_invert_rot.setChecked(False)
        self._chk_outline.setChecked(True)
        self._chk_paste.setChecked(True)
        self._chk_silk.setChecked(True)
        self._chk_pickplace.setChecked(True)
        self._chk_crosshair.setChecked(True)
        self._search_input.clear()
        self._reset_offset()
        self._fit_scene()


def build_pads(render_data: RenderData) -> List[Tuple[float, float, float]]:
    return [(f.cx, f.cy, _flash_size(f)) for f in render_data.flashes]
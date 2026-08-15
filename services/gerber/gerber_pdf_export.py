"""Export the Gerber View content to a single A4 landscape PDF page (vector).

Reuses the exact geometry helpers from ``ui.gerber_viewer`` (``_append_arc_path``,
``_build_fill_path``) so the exported page matches what is currently shown,
honouring the selected layer and the display settings (rotation, flip, mirror X,
offsets, and per-layer visibility toggles).

All gerber layers (outline/paste/silk) are drawn in black; the pickplace
crosshair and direction arrows are drawn in red. Uses ``QPdfWriter`` from
PySide6 so no extra dependency is required. The page is A4 landscape, white
background, content scaled (aspect-preserving) to fit with a 10 mm margin,
centred.
"""

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPageLayout,
    QPageSize,
    QPainter,
    QPainterPath,
    QPen,
    QPdfWriter,
    QPolygonF,
    QTransform,
)

from services.gerber.gerber_render import RenderData
from services.gerber.gerber_transform import apply_transform
from ui.gerber_viewer import (
    _append_arc_path,
    _build_fill_path,
)

# Scene coordinate convention: y is flipped (gerber y -> -y). RenderData lines
# already carry gerber coords; we flip on draw exactly like gerber_viewer.

# PDF export uses black for all gerber layers (white background) and red for the
# pickplace crosshair/arrow overlay.
GERBER_COLOR = QColor("#000000")
CROSSHAIR_COLOR = QColor("#EF4444")

_LINE_MIN_WIDTH = 0.1

# Overlay sizing. The crosshair stroke and the arrow minima are defined in
# *paper* millimetres (so they stay readable regardless of the board size) and
# converted to scene units via the fit scale. Arrow proportions mirror the
# on-screen MarkerOverlayItem (0.4 * half arm length, 0.25 * half wing).
_PAPER_CROSS_LINE_MM = 0.2
_PAPER_ARROW_MIN_LEN_MM = 1.5
_PAPER_ARROW_MIN_WING_MM = 0.6
_ARROW_SCALE = 0.4
_ARROW_WING_SCALE = 0.25


class _OverlayGeometry:
    """Mirror of MarkerOverlayItem.paint geometry (crosshair + direction arrow)."""

    @staticmethod
    def cross_path(half: float) -> QPainterPath:
        p = QPainterPath()
        p.moveTo(-half, 0.0)
        p.lineTo(half, 0.0)
        p.moveTo(0.0, -half)
        p.lineTo(0.0, half)
        return p

    @staticmethod
    def arrow_polygon(half: float, tip: float, wing: float) -> QPolygonF:
        return QPolygonF([
            QPointF(-tip, 0.0),
            QPointF(-half, -wing),
            QPointF(-half, wing),
        ])


def _build_lines_paths(
    render_data: RenderData,
    angle: float,
    mirror: bool,
    off_x: float,
    off_y: float,
    center_x: float,
    center_y: float,
    mirror_x: bool,
) -> Dict[float, QPainterPath]:
    """Batch lines/arcs into one path per stroke width (like _render_lines)."""
    buckets: Dict[float, QPainterPath] = {}
    for ln in render_data.lines:
        w = round(max(ln.width, _LINE_MIN_WIDTH), 3)
        path = buckets.get(w)
        if path is None:
            path = QPainterPath()
            buckets[w] = path
        x1, y1 = apply_transform(ln.x1, ln.y1, mirror, angle, off_x, off_y, center_x, center_y, mirror_x)
        x2, y2 = apply_transform(ln.x2, ln.y2, mirror, angle, off_x, off_y, center_x, center_y, mirror_x)
        path.moveTo(x1, -y1)
        path.lineTo(x2, -y2)
    for ar in render_data.arcs:
        w = round(max(ar.width, _LINE_MIN_WIDTH), 3)
        path = buckets.get(w)
        if path is None:
            path = QPainterPath()
            buckets[w] = path
        _append_arc_path(path, ar, mirror, angle, off_x, off_y, center_x, center_y, mirror_x)
    return buckets


def _build_fill_geometry(
    render_data: RenderData,
    angle: float,
    mirror: bool,
    off_x: float,
    off_y: float,
    center_x: float,
    center_y: float,
    mirror_x: bool,
) -> Optional[QPainterPath]:
    if not render_data.flashes:
        return None
    return _build_fill_path(
        render_data.flashes, mirror, angle, off_x, off_y, center_x, center_y, mirror_x
    )


def _arrow_geometry(half: float, scene_per_paper_mm: float) -> Tuple[float, float, float]:
    """Return (alen, tip, wing) in scene units for a marker's direction arrow.

    Mirrors MarkerOverlayItem.paint: alen is 0.4*half but at least a fixed
    on-paper minimum; the wing is 0.25*half with an on-paper minimum, capped
    by the arm length.
    """
    alen = max(_ARROW_SCALE * half, _PAPER_ARROW_MIN_LEN_MM / scene_per_paper_mm)
    wing = min(max(_ARROW_WING_SCALE * half, _PAPER_ARROW_MIN_WING_MM / scene_per_paper_mm), alen)
    return alen, half + alen, wing


def _markers_bbox(
    markers: List[Tuple[float, float, float, float]],
    scene_per_paper_mm: float,
) -> Optional[QRectF]:
    if not markers:
        return None
    pad = 0.0
    for m in markers:
        _alen, tip, _wing = _arrow_geometry(m[3], scene_per_paper_mm)
        pad = max(pad, tip + 0.5)
    xs = [m[0] for m in markers]
    ys = [m[1] for m in markers]
    return QRectF(
        min(xs) - pad, min(ys) - pad,
        (max(xs) - min(xs)) + 2 * pad,
        (max(ys) - min(ys)) + 2 * pad,
    )


def _union_bbox(rects: List[QRectF]) -> Optional[QRectF]:
    valid = [r for r in rects if r is not None and not r.isNull() and r.isValid()]
    if not valid:
        return None
    x0 = min(r.left() for r in valid)
    y0 = min(r.top() for r in valid)
    x1 = max(r.right() for r in valid)
    y1 = max(r.bottom() for r in valid)
    return QRectF(x0, y0, x1 - x0, y1 - y0)


def _build_overlay_path(
    markers: List[Tuple[float, float, float, float]],
    scene_per_paper_mm: float,
) -> Tuple[QPainterPath, QPainterPath]:
    """Return (crosshair_path, arrow_fill_path) for all markers (scene coords).

    Crosshairs are translated to their marker; arrows are also rotated by
    ``-rot`` around the marker (matching MarkerOverlayItem.paint).
    """
    crosses = QPainterPath()
    arrows = QPainterPath()
    for mx, my, rot, half in markers:
        crosses.addPath(_OverlayGeometry.cross_path(half).translated(mx, my))
        _alen, tip, wing = _arrow_geometry(half, scene_per_paper_mm)
        poly = _OverlayGeometry.arrow_polygon(half, tip, wing)
        t = QTransform()
        t.translate(mx, my)
        t.rotate(-rot)
        arrows.addPolygon(t.map(poly))
    return crosses, arrows


def export_gerber_pdf(
    path: str,
    outline: RenderData,
    paste: RenderData,
    silk: RenderData,
    markers: List[Tuple[float, float, float, float]],
    angle: float = 0.0,
    invert_rot: bool = False,
    flip: bool = False,
    mirror_x: bool = False,
    off_x: float = 0.0,
    off_y: float = 0.0,
    show_outline: bool = True,
    show_paste: bool = True,
    show_silk: bool = True,
    show_pickplace: bool = True,
    show_crosshair: bool = True,
    board_center: Tuple[float, float] = (0.0, 0.0),
    is_top: bool = True,
) -> str:
    """Render the Gerber View state to a single A4 PDF page.

    Returns the output path on success. Raises RuntimeError if there is nothing
    to draw.
    """
    if invert_rot:
        angle = (360.0 - angle) % 360.0
    center_x, center_y = board_center

    # --- Pass 1: union bounding box of the gerber content only. ---------------
    gerber_bboxes: List[QRectF] = []
    if show_outline:
        for path_ in _build_lines_paths(
            outline, angle, flip, off_x, off_y, center_x, center_y, mirror_x
        ).values():
            gerber_bboxes.append(path_.boundingRect())
    if show_paste:
        f = _build_fill_geometry(paste, angle, flip, off_x, off_y, center_x, center_y, mirror_x)
        if f is not None:
            gerber_bboxes.append(f.boundingRect())
    if show_silk:
        for path_ in _build_lines_paths(
            silk, angle, flip, off_x, off_y, center_x, center_y, mirror_x
        ).values():
            gerber_bboxes.append(path_.boundingRect())
        f = _build_fill_geometry(silk, angle, flip, off_x, off_y, center_x, center_y, mirror_x)
        if f is not None:
            gerber_bboxes.append(f.boundingRect())

    has_marker_content = show_pickplace and bool(markers)
    if not gerber_bboxes and not has_marker_content:
        raise RuntimeError("Nothing to export: no visible geometry.")

    content_rect = _union_bbox(gerber_bboxes)

    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    layout = QPageLayout(
        QPageSize(QPageSize.A4),
        QPageLayout.Landscape,
        QMarginsF(0, 0, 0, 0),
        QPageLayout.Millimeter,
    )
    writer.setPageLayout(layout)

    painter = QPainter(writer)
    painter.setRenderHint(QPainter.Antialiasing, True)

    # White background.
    page_rect = layout.paintRectPixels(writer.resolution())
    painter.fillRect(page_rect, QColor(Qt.white))

    # Aspect-preserving fit with a margin.
    margin_mm = 10.0
    margin_px = margin_mm / 25.4 * writer.resolution()
    usable_w = max(page_rect.width() - 2 * margin_px, 1.0)
    usable_h = max(page_rect.height() - 2 * margin_px, 1.0)
    px_per_mm = writer.resolution() / 25.4

    def fit_scale(rect: Optional[QRectF]) -> float:
        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            return 1.0
        s = min(usable_w / rect.width(), usable_h / rect.height())
        return s if s > 0 else 1.0

    # --- Pass 1 fit from gerber content. ---------------------------------------
    scale = fit_scale(content_rect)
    scene_per_paper_mm = scale / px_per_mm

    # --- Overlay bbox (needs scene_per_paper_mm for arrow minima). ------------
    overlay_crosses = QPainterPath()
    overlay_arrows = QPainterPath()
    if has_marker_content:
        overlay_crosses, overlay_arrows = _build_overlay_path(markers, scene_per_paper_mm)
        mb = _markers_bbox(markers, scene_per_paper_mm)
        if mb is not None:
            content_rect = _union_bbox(gerber_bboxes + [mb])

    # --- Final fit (overlay bbox may have grown the content). -----------------
    scale = fit_scale(content_rect)
    scene_per_paper_mm = scale / px_per_mm
    if has_marker_content:
        overlay_crosses, overlay_arrows = _build_overlay_path(markers, scene_per_paper_mm)

    if content_rect is None or content_rect.width() <= 0 or content_rect.height() <= 0:
        raise RuntimeError("Nothing to export: empty bounding box.")

    offset_x = margin_px + (usable_w - content_rect.width() * scale) / 2.0
    offset_y = margin_px + (usable_h - content_rect.height() * scale) / 2.0

    painter.translate(offset_x, offset_y)
    painter.scale(scale, scale)

    # Lines (stroked) with non-cosmetic width in scene units (mm).
    # NOTE: pen width is scaled by the painter transform, so passing the raw
    # mm width is correct (dividing by scale would collapse strokes to
    # sub-pixel hairlines and make them disappear).
    if show_outline:
        for w, path_ in _build_lines_paths(
            outline, angle, flip, off_x, off_y, center_x, center_y, mirror_x
        ).items():
            pen = QPen(GERBER_COLOR, w)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path_.translated(-content_rect.left(), -content_rect.top()))
    if show_silk:
        for w, path_ in _build_lines_paths(
            silk, angle, flip, off_x, off_y, center_x, center_y, mirror_x
        ).items():
            pen = QPen(GERBER_COLOR, w)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path_.translated(-content_rect.left(), -content_rect.top()))

    # Fills.
    painter.setPen(Qt.NoPen)
    if show_paste:
        f = _build_fill_geometry(paste, angle, flip, off_x, off_y, center_x, center_y, mirror_x)
        if f is not None:
            painter.setBrush(QBrush(GERBER_COLOR))
            painter.drawPath(f.translated(-content_rect.left(), -content_rect.top()))
    if show_silk:
        f = _build_fill_geometry(silk, angle, flip, off_x, off_y, center_x, center_y, mirror_x)
        if f is not None:
            painter.setBrush(QBrush(GERBER_COLOR))
            painter.drawPath(f.translated(-content_rect.left(), -content_rect.top()))

    # Overlay: crosshair + direction arrows (red).
    if has_marker_content:
        if show_crosshair:
            pen = QPen(CROSSHAIR_COLOR, _PAPER_CROSS_LINE_MM / scene_per_paper_mm)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(overlay_crosses.translated(-content_rect.left(), -content_rect.top()))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(CROSSHAIR_COLOR))
        painter.drawPath(overlay_arrows.translated(-content_rect.left(), -content_rect.top()))

    painter.end()
    return path

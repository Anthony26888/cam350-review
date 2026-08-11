import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QBrush
from PySide6.QtWidgets import QApplication, QGraphicsScene

from services.gerber.gerber_render import RenderData
from services.gerber.gerber_render_lib import parse_layer
from ui import gerber_viewer as gv

COLOR = QColor("#F8FAFC")


def build_scene(rd: RenderData) -> QGraphicsScene:
    scene = QGraphicsScene()
    buckets: dict = {}
    for ln in rd.lines:
        w = round(ln.width, 3)
        path = buckets.get(w)
        if path is None:
            path = QPainterPath()
            buckets[w] = path
        path.moveTo(ln.x1, -ln.y1)
        path.lineTo(ln.x2, -ln.y2)
    for ar in rd.arcs:
        w = round(ar.width, 3)
        path = buckets.get(w)
        if path is None:
            path = QPainterPath()
            buckets[w] = path
        _append_arc_path(path, ar, False, 0.0, 0.0, 0.0, 0.0, 0.0)
    for w, path in buckets.items():
        pen = QPen(COLOR, w)
        pen.setCosmetic(False)
        scene.addPath(path, pen)
    if rd.flashes:
        dark = QPainterPath()
        clear = QPainterPath()
        for fl in rd.flashes:
            target = clear if fl.negative else dark
            gv._add_flash(target, fl)
        final = dark
        if not clear.isEmpty():
            final = QPainterPath(dark.subtracted(clear))
        scene.addPath(final, QPen(Qt.PenStyle.NoPen), QBrush(COLOR))
    return scene


def render_timed(scene: QGraphicsScene, img_w: int, img_h: int, scale: float, aa: bool = True) -> float:
    brect = scene.itemsBoundingRect()
    cx, cy = brect.center().x(), brect.center().y()
    img = QImage(img_w, img_h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#0B1220"))
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing, aa)
    painter.translate(img_w / 2.0, img_h / 2.0)
    painter.scale(scale, scale)
    painter.translate(-cx, -cy)
    t0 = time.perf_counter()
    scene.render(painter)
    dt = time.perf_counter() - t0
    painter.end()
    return dt


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def main():
    QApplication(sys.argv)
    root = sys.argv[1] if len(sys.argv) > 1 else r"D:\Test\data21\PSU_PCB wf"
    img_w, img_h = 1920, 1080
    candidates = [os.path.join(root, f) for f in os.listdir(root)]
    rows = []
    for fp in sorted(candidates):
        try:
            rd = parse_layer(fp)
        except Exception:
            continue
        if not (rd.lines or rd.arcs or rd.flashes):
            continue
        scene = build_scene(rd)
        brect = scene.itemsBoundingRect()
        if brect.isNull() or brect.width() <= 0 or brect.height() <= 0:
            continue
        fit_scale = min(img_w / brect.width(), img_h / brect.height()) * 0.98
        d_fit = median([render_timed(scene, img_w, img_h, fit_scale) for _ in range(3)])
        d_z2 = median([render_timed(scene, img_w, img_h, fit_scale * 2) for _ in range(3)])
        d_z8 = median([render_timed(scene, img_w, img_h, fit_scale * 8) for _ in range(3)])
        rows.append(
            (len(rd.lines) + len(rd.arcs), len(rd.flashes),
             os.path.basename(fp), d_fit * 1000, d_z2 * 1000, d_z8 * 1000)
        )
    print(f"{'file':<44} {'strokes':>8} {'flashes':>8} {'fit(ms)':>9} {'z2(ms)':>9} {'z8(ms)':>9}")
    for n, k, name, f, z2, z8 in sorted(rows, reverse=True):
        print(f"{name:<44} {n:>8} {k:>8} {f:>9.1f} {z2:>9.1f} {z8:>9.1f}")

    combined = _build_combined(root)
    if combined is not None:
        scene, desc = combined
        brect = scene.itemsBoundingRect()
        fit_scale = min(img_w / brect.width(), img_h / brect.height()) * 0.98
        d_fit = median([render_timed(scene, img_w, img_h, fit_scale) for _ in range(3)])
        d_z2 = median([render_timed(scene, img_w, img_h, fit_scale * 2) for _ in range(3)])
        d_noaa = median([render_timed(scene, img_w, img_h, fit_scale, aa=False) for _ in range(3)])
        print(f"\nCOMBINED [{desc}]  fit={d_fit*1000:.1f}ms  z2={d_z2*1000:.1f}ms  fit_noAA={d_noaa*1000:.1f}ms")


def _build_combined(root: str):
    def find(exts, keys):
        for f in sorted(os.listdir(root)):
            low = f.lower()
            if any(low.endswith(e) for e in exts) or any(k in low for k in keys):
                return os.path.join(root, f)
        return None

    def parse(fpath):
        if not fpath:
            return RenderData()
        try:
            return parse_layer(fpath)
        except Exception:
            return RenderData()

    gko = find((".gko",), ("rout", "gko", "outline"))
    gto = find((".gto",), ("to", "gto", "silk", "overlay"))
    gtp = find((".gtp",), ("tp", "gtp", "paste", "pst"))
    gko = parse(gko)
    gto = parse(gto)
    gtp = parse(gtp)
    scene = QGraphicsScene()
    for rd in (gko, gto):
        buckets: dict = {}
        for ln in rd.lines:
            w = round(ln.width, 3)
            path = buckets.get(w)
            if path is None:
                path = QPainterPath()
                buckets[w] = path
            path.moveTo(ln.x1, -ln.y1)
            path.lineTo(ln.x2, -ln.y2)
        for ar in rd.arcs:
            w = round(ar.width, 3)
            path = buckets.get(w)
            if path is None:
                path = QPainterPath()
                buckets[w] = path
            _append_arc_path(path, ar, False, 0.0, 0.0, 0.0, 0.0, 0.0)
        for w, path in buckets.items():
            pen = QPen(COLOR, w)
            pen.setCosmetic(False)
            scene.addPath(path, pen)
    for rd in (gto, gtp):
        if not rd.flashes:
            continue
        dark = QPainterPath()
        clear = QPainterPath()
        for fl in rd.flashes:
            target = clear if fl.negative else dark
            gv._add_flash(target, fl)
        final = dark
        if not clear.isEmpty():
            final = QPainterPath(dark.subtracted(clear))
        scene.addPath(final, QPen(Qt.PenStyle.NoPen), QBrush(COLOR))
    desc = (f"strokes={len(gko.lines)+len(gko.arcs)+len(gto.lines)+len(gto.arcs)} "
            f"flashes={len(gto.flashes)+len(gtp.flashes)}")
    return scene, desc


if __name__ == "__main__":
    main()
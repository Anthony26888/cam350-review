"""Benchmark the Gerber parse / scene-build / paint pipeline.

Measures the three stages that dominate the Gerber View frame budget:

* ``parse``  - text -> in-memory geometry (``services.gerber.gerber_render``)
* ``build``  - geometry -> QGraphicsScene items (QPainterPath bucketing)
* ``draw``   - scene -> QImage at a given scale (what a paint costs)

Usage::

    python scripts/bench_gerber_paint.py                 # default sample dir
    python scripts/bench_gerber_paint.py "D:\\Test\\data21\\PSU_PCB wf"
    python scripts/bench_gerber_paint.py --scan "D:\\Test" # every data* folder
    python scripts/bench_gerber_paint.py --json out.json   # machine readable

The numbers printed here are the baseline recorded in ``docs/gerber_bench.md``.
Re-run this script after touching the parser or the renderer and diff the
output to catch regressions before they reach a customer.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QGraphicsScene

from services.gerber.gerber_render import RenderData
from services.gerber.gerber_render_lib import load_layer
from ui import gerber_viewer as gv

COLOR = QColor("#F8FAFC")
BACKGROUND = QColor("#0B1220")
IMG_W, IMG_H = 1920, 1080


def _append_arc_path(path: QPainterPath, ar, mirror, angle, off_x, off_y, cx0, cy0, mirror_x=False):
    """Append an arc stroke to `path` with the display transform + y-flip.

    Thin wrapper over the viewer's helper so the benchmark exercises exactly
    the same arc tessellation the viewer uses.
    """
    return gv._append_arc_path(path, ar, mirror, angle, off_x, off_y, cx0, cy0, mirror_x)


def build_scene(rd: RenderData) -> QGraphicsScene:
    """Build the same scene layout the viewer builds for one layer."""
    from services.gerber.render.layer import LayerItem, build_layer_paths

    scene = QGraphicsScene()
    paths = build_layer_paths(rd, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
    scene.addItem(LayerItem(paths, COLOR))
    return scene


def render_timed(scene: QGraphicsScene, img_w: int, img_h: int, scale: float, aa: bool = True) -> float:
    """Draw the scene the way the viewer does.

    ``QGraphicsScene.render()`` ignores the transform of the painter and
    fits the scene into the device rectangle on its own, which would measure
    a completely different zoom level.  The items are therefore painted
    directly with the transform of the view.
    """
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
    for item in scene.items():
        item.paint(painter, None, None)
    dt = time.perf_counter() - t0
    painter.end()
    return dt


def render_cached(scene: QGraphicsScene, img_w: int, img_h: int, scale: float) -> float:
    """The time of a repaint when the layer image is already in the cache."""
    render_timed(scene, img_w, img_h, scale)
    return render_timed(scene, img_w, img_h, scale)


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def _fit_scale(scene: QGraphicsScene) -> float:
    brect = scene.itemsBoundingRect()
    if brect.isNull() or brect.width() <= 0 or brect.height() <= 0:
        return 1.0
    return min(IMG_W / brect.width(), IMG_H / brect.height()) * 0.98


def bench_file(fp: str, repeats: int = 3) -> dict:
    """Parse, build and draw one Gerber file; return a metrics row."""
    row = {
        "file": os.path.basename(fp),
        "bytes": os.path.getsize(fp),
        "parse_ms": 0.0,
        "build_ms": 0.0,
        "draw_fit_ms": 0.0,
        "draw_z2_ms": 0.0,
        "draw_z8_ms": 0.0,
        "lines": 0,
        "arcs": 0,
        "flashes": 0,
        "error": None,
    }
    t0 = time.perf_counter()
    try:
        rd, info = load_layer(fp)
        if info.degraded:
            row["degraded"] = info.parser
    except Exception as exc:  # noqa: BLE001 - the benchmark reports, never raises
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row
    row["parse_ms"] = (time.perf_counter() - t0) * 1000.0
    row["lines"] = len(rd.lines)
    row["arcs"] = len(rd.arcs)
    row["flashes"] = len(rd.flashes)
    if not (rd.lines or rd.arcs or rd.flashes):
        row["error"] = "empty"
        return row

    t0 = time.perf_counter()
    scene = build_scene(rd)
    row["build_ms"] = (time.perf_counter() - t0) * 1000.0

    fit = _fit_scale(scene)
    # Every scale is a different cache entry, so the first draw of each of
    # them is the cold one; the following ones reuse the image.
    row["draw_fit_ms"] = render_timed(scene, IMG_W, IMG_H, fit) * 1000.0
    row["draw_cached_ms"] = median(
        [render_timed(scene, IMG_W, IMG_H, fit) for _ in range(repeats)]) * 1000.0
    row["draw_z2_ms"] = render_timed(scene, IMG_W, IMG_H, fit * 2) * 1000.0
    row["draw_z8_ms"] = render_timed(scene, IMG_W, IMG_H, fit * 8) * 1000.0
    return row


def _find_files(root: str):
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            out.append(os.path.join(dirpath, name))
    return out


def _scan_roots(scan_root: str):
    """Every ``data*`` folder under `scan_root` that contains Gerber-ish files."""
    roots = []
    if os.path.isdir(scan_root):
        for name in sorted(os.listdir(scan_root)):
            p = os.path.join(scan_root, name)
            if os.path.isdir(p):
                roots.append(p)
    if not roots:
        roots = [scan_root]
    return roots


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default=r"D:\Test\data21\PSU_PCB wf")
    ap.add_argument("--scan", help="scan every sub-directory of this path instead")
    ap.add_argument("--json", help="also write the rows to this JSON file")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--max-mb", type=float, default=0.0,
                    help="skip files larger than this (0 = no limit)")
    args = ap.parse_args()

    QApplication(sys.argv[:1])

    if args.scan:
        roots = _scan_roots(args.scan)
    else:
        roots = [args.root]

    rows = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for fp in _find_files(root):
            if args.max_mb and os.path.getsize(fp) > args.max_mb * 1024 * 1024:
                continue
            row = bench_file(fp, repeats=args.repeats)
            row["root"] = root
            rows.append(row)

    rows.sort(key=lambda r: -(r["lines"] + r["arcs"]))
    print(f"{'file':<46} {'MB':>6} {'strokes':>8} {'flashes':>8} "
          f"{'parse':>8} {'build':>8} {'fit':>8} {'cached':>8} {'z2':>8} {'z8':>8}  (ms)")
    print("-" * 126)
    for r in rows:
        if r["error"] and r["error"] != "empty":
            print(f"{r['file'][:45]:<46} {r['bytes']/1048576:>6.2f} "
                  f"{'--':>8} {'--':>8} {'--':>8} {'--':>8} {'--':>8} {'--':>8} {'--':>8} {'--':>8}  "
                  f"ERR {r['error'][:40]}")
            continue
        if r["error"] == "empty":
            continue
        print(f"{r['file'][:45]:<46} {r['bytes']/1048576:>6.2f} "
              f"{r['lines']+r['arcs']:>8} {r['flashes']:>8} "
              f"{r['parse_ms']:>8.1f} {r['build_ms']:>8.1f} "
              f"{r['draw_fit_ms']:>8.1f} {r['draw_cached_ms']:>8.1f} "
              f"{r['draw_z2_ms']:>8.1f} {r['draw_z8_ms']:>8.1f}")

    ok = [r for r in rows if not r["error"] or r["error"] == "empty"]
    if ok:
        tot_parse = sum(r["parse_ms"] for r in ok)
        tot_build = sum(r["build_ms"] for r in ok)
        tot_fit = sum(r["draw_fit_ms"] for r in ok)
        tot_cached = sum(r["draw_cached_ms"] for r in ok)
        print("-" * 126)
        print(f"TOTAL over {len(ok)} file(s): parse={tot_parse:.0f}ms  "
              f"build={tot_build:.0f}ms  fit-paint={tot_fit:.0f}ms  "
              f"cached-paint={tot_cached:.0f}ms")

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2, sort_keys=True)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

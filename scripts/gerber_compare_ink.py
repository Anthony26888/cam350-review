"""Compare our renderer with the reference library, pixel by pixel.

The reference is `gerbonara`, the library the reference viewer (KiCad) uses
to read the files.  Both renderers draw the same file onto the same
rectangle of the page, and the two pictures are compared: how much ink
each of them puts down, and how much of it lies on the same place.

The comparison is a check of the geometry and of the polarity, not of the
picture: the two renderers antialias differently, so the border of every
shape never matches exactly.  The numbers that have to agree are the
amount of dark ink and the amount of ink that both renderers put on the
same place.

Usage::

    python scripts/gerber_compare_ink.py "D:\\Test\\data0\\PCB ... gerber"
    python scripts/gerber_compare_ink.py <file.gtl> --scale 0.05
"""

from __future__ import annotations

import argparse
import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from PySide6.QtCore import QByteArray, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor, QImage, QPainter, QTransform,
)
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

from services.gerber.gerber_render_lib import load_layer  # noqa: E402
from services.gerber.render.layer import build_layer_paths  # noqa: E402

#: The extensions of the files of a board.
EXTENSIONS = (".gtl", ".gbl", ".gto", ".gtp", ".gko", ".gts", ".gbs",
              ".gbp", ".gbo")


#: The way the reference drawing is turned around: the file has the y
#: upwards, the drawing has it downwards.
_FLIP_RE = re.compile(
    r'transform="translate\(([-\d.eE]+) ([-\d.eE]+)\) '
    r'scale\(1 -1\) translate\(([-\d.eE]+) ([-\d.eE]+)\)"'
)


def _viewbox_of(svg: str) -> tuple[float, float, float, float]:
    """The rectangle of the page the reference drawing covers, in mm."""
    match = re.search(r'viewBox="([-\d.eE]+) ([-\d.eE]+) ([-\d.eE]+) ([-\d.eE]+)"',
                      svg)
    if match is None:
        return 0.0, 0.0, 0.0, 0.0
    x, y, width, height = (float(value) for value in match.groups())
    return x, y, width, height


def _origin_of(svg: str, viewbox) -> tuple[float, float]:
    """The point of the file that the reference drawing starts at.

    The drawing of the reference library is turned around: the file has
    the y upwards, the page has it downwards.  The two pictures can only
    be laid on top of each other when the turn is undone.
    """
    x0, y0, _width, _height = viewbox
    match = _FLIP_RE.search(svg)
    if match is None:
        return x0, y0
    first_x, first_y, second_x, second_y = (float(v) for v in match.groups())
    return x0 - (first_x + second_x), y0 - (first_y - second_y)


def _reference_image(path: str, scale: float):
    """The picture of the reference renderer, and the page it covers."""
    import gerbonara

    gerber = gerbonara.GerberFile.open(path)
    svg = str(gerber.to_svg())
    x0, y0, width_mm, height_mm = _viewbox_of(svg)
    if width_mm <= 0.0 or height_mm <= 0.0:
        return None, (0.0, 0.0, 0.0, 0.0)
    width = max(1, int(round(width_mm * scale)))
    height = max(1, int(round(height_mm * scale)))
    image = QImage(width, height, QImage.Format_Grayscale8)
    image.fill(255)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    # The bytes of the image are copied: the buffer of the picture is
    # gone when the picture is.
    array = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(
        height, image.bytesPerLine())[:, :width].copy()
    origin = _origin_of(svg, (x0, y0, width_mm, height_mm))
    return array, (origin[0], origin[1], width_mm, height_mm)


def _our_image(path: str, scale: float, page: tuple[float, float, float, float]):
    """Our picture of the same file, on the same page."""
    data, _info = load_layer(path)
    paths = build_layer_paths(data, 0.0, False, 0.0, 0.0, False, (0.0, 0.0))
    x0, y0, width_mm, height_mm = page
    width = max(1, int(round(width_mm * scale)))
    height = max(1, int(round(height_mm * scale)))
    image = QImage(width, height, QImage.Format_Grayscale8)
    image.fill(255)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    # The origin of the page is given in the world of the viewer, where
    # the y already points downwards, so the two pictures lie on the same
    # rectangle of the page.
    transform = QTransform()
    transform.translate(-x0, -y0)
    transform.scale(scale, scale)
    painter.setTransform(transform)
    for op in paths.ops:
        if op.fill:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0))
        else:
            pen = painter.pen()
            pen.setWidthF(op.width)
            pen.setColor(QColor(0, 0, 0))
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
        painter.setCompositionMode(
            QPainter.CompositionMode_Clear if op.clear
            else QPainter.CompositionMode_SourceOver)
        painter.drawPath(op.path)
    painter.end()
    return np.frombuffer(image.constBits(), dtype=np.uint8).reshape(
        height, image.bytesPerLine())[:, :width].copy()


def _aligned(ours: np.ndarray, reference: np.ndarray):
    """Put our picture on the same place as the reference one.

    The two renderers do not put the page of the file on the same spot
    of the picture, and a fraction of a millimetre is a few pixels when
    the page is looked at closely.  The pictures are therefore moved so
    that the ink of the two of them starts at the same pixel.
    """
    height = max(ours.shape[0], reference.shape[0])
    width = max(ours.shape[1], reference.shape[1])
    ours_full = np.full((height, width), 255, dtype=np.uint8)
    reference_full = np.full((height, width), 255, dtype=np.uint8)
    ours_full[:ours.shape[0], :ours.shape[1]] = ours
    reference_full[:reference.shape[0], :reference.shape[1]] = reference

    def _start(mask):
        cols = np.flatnonzero(mask.any(axis=0))
        rows = np.flatnonzero(mask.any(axis=1))
        if cols.size == 0 or rows.size == 0:
            return None
        return int(cols[0]), int(rows[0])

    ours_start = _start(ours_full < 250)
    reference_start = _start(reference_full < 250)
    if ours_start is not None and reference_start is not None:
        dx = reference_start[0] - ours_start[0]
        dy = reference_start[1] - ours_start[1]
        if dx or dy:
            ours_full = np.roll(np.roll(ours_full, dy, axis=0), dx, axis=1)
    return ours_full, reference_full


def compare(path: str, scale: float) -> dict:
    """Compare one file and report the numbers of both renderers."""
    reference, page = _reference_image(path, scale)
    if reference is None:
        return {"file": os.path.basename(path), "error": "empty page"}
    ours = _our_image(path, scale, page)
    ours, reference = _aligned(ours, reference)
    ref_dark = reference < 128
    our_dark = ours < 128
    both = int(np.count_nonzero(ref_dark & our_dark))
    union = int(np.count_nonzero(ref_dark | our_dark))
    # Any ink at all: a line that is thinner than a pixel is spread over
    # it by the two renderers in a different way, and only the area it
    # covers is the same.
    ref_any = reference < 250
    our_any = ours < 250
    any_both = int(np.count_nonzero(ref_any & our_any))
    any_union = int(np.count_nonzero(ref_any | our_any))
    return {
        "file": os.path.basename(path),
        "ref_dark": int(np.count_nonzero(ref_dark)),
        "our_dark": int(np.count_nonzero(our_dark)),
        "both": both,
        "iou": (both / union) if union else 0.0,
        "area_iou": (any_both / any_union) if any_union else 0.0,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="a Gerber file or a folder of files")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="pixels per millimetre")
    args = parser.parse_args(argv)

    target = args.target
    if os.path.isdir(target):
        files = sorted(
            os.path.join(target, name) for name in os.listdir(target)
            if name.lower().endswith(EXTENSIONS))
    else:
        files = [target]
    if not files:
        print("khong co file nao trong", target)
        return 1

    print(f"{'file':<40} {'g.den':>9} {'ta':>9} {'trung':>9} {'IoU':>7} {'vung':>7}")
    print("-" * 88)
    worst = 1.0
    for path in files:
        try:
            row = compare(path, args.scale)
        except Exception as exc:  # noqa: BLE001 - a report, not a test
            print(f"{os.path.basename(path):<40}  khong doc duoc: {exc}")
            continue
        if "error" in row:
            print(f"{row['file']:<40}  {row['error']}")
            continue
        print(f"{row['file']:<40} {row['ref_dark']:>9} {row['our_dark']:>9} "
              f"{row['both']:>9} {row['iou']:>7.3f} {row['area_iou']:>7.3f}")
        worst = min(worst, row["iou"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

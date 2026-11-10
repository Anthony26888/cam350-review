"""Generate assets/icon.ico (+ icon.png) for the FIDUX brand.

Design: Layout C monogram — rounded square with cyan→indigo gradient,
white crosshair X in the center, four fiducial dots at the corners
(mirroring PCB fiducial marks).

Rendering: every shape is drawn on a 4x supersampled canvas and
downscaled with LANCZOS so edges stay crisp/anti-aliased. Small sizes
use bolder stroke/dot ratios so the mark does not turn to mush at 16px.
"""
from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ICO_PATH = ROOT / "assets" / "icon.ico"
PNG_PATH = ROOT / "assets" / "icon.png"

CANVAS = 1024
SS = 4  # supersample factor
GRADIENT_FROM = (14, 165, 233)  # #0EA5E9 sky-500
GRADIENT_TO = (99, 102, 241)  # #6366F1 indigo-500

RADIUS_RATIO = 180 / 1024

# Design coords on the 1024 grid (>=48px).
DOT_POS = 248 / 1024
DOT_POS_FAR = 776 / 1024
DOT_R = 56 / 1024
X_START = 348 / 1024
X_END = 676 / 1024
STROKE = 64 / 1024

# Bold variant for <48px: thicker strokes, slightly tighter X, bigger dots.
DOT_R_SMALL = 78 / 1024
X_START_SMALL = 356 / 1024
X_END_SMALL = 668 / 1024
STROKE_SMALL = 96 / 1024


def _lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def _gradient(size: int) -> Image.Image:
    n = 512
    small = Image.new("RGB", (n, n))
    px = small.load()
    denom = 2 * (n - 1)
    for y in range(n):
        for x in range(n):
            t = (x + y) / denom
            px[x, y] = (
                _lerp(GRADIENT_FROM[0], GRADIENT_TO[0], t),
                _lerp(GRADIENT_FROM[1], GRADIENT_TO[1], t),
                _lerp(GRADIENT_FROM[2], GRADIENT_TO[2], t),
            )
    return small.resize((size, size), Image.Resampling.BICUBIC)


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def render(size: int) -> Image.Image:
    """Render one icon frame at `size`, anti-aliased via 4x supersampling."""
    ss_size = size * SS
    small = size < 48

    dot_r = DOT_R_SMALL if small else DOT_R
    x0 = X_START_SMALL if small else X_START
    x1 = X_END_SMALL if small else X_END
    stroke = STROKE_SMALL if small else STROKE

    layer = Image.new("RGBA", (ss_size, ss_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    white = (255, 255, 255, 255)

    dot_px = max(2, int(round(dot_r * ss_size)))
    dot_a = int(round(DOT_POS * ss_size))
    dot_b = int(round(DOT_POS_FAR * ss_size))
    for cx, cy in ((dot_a, dot_a), (dot_b, dot_a), (dot_a, dot_b), (dot_b, dot_b)):
        draw.ellipse(
            (cx - dot_px, cy - dot_px, cx + dot_px, cy + dot_px), fill=white
        )

    a = int(round(x0 * ss_size))
    b = int(round(x1 * ss_size))
    line_w = max(2, int(round(stroke * ss_size)))
    cap_r = line_w // 2
    for p1, p2 in (((a, a), (b, b)), ((b, a), (a, b))):
        draw.line((p1, p2), fill=white, width=line_w)
        for p in (p1, p2):
            draw.ellipse(
                (p[0] - cap_r, p[1] - cap_r, p[0] + cap_r, p[1] + cap_r),
                fill=white,
            )

    bg = _gradient(ss_size)
    out = Image.new("RGBA", (ss_size, ss_size), (0, 0, 0, 0))
    out.paste(bg, (0, 0), _rounded_mask(ss_size, int(round(RADIUS_RATIO * ss_size))))
    out.alpha_composite(layer)
    return out.resize((size, size), Image.Resampling.LANCZOS)


def write_ico(path: Path, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """Pack per-size renders into an ICO (PNG-compressed entries).

    Pillow's ICO saver resizes one source image for every entry, which
    would discard the adaptive small-size geometry, so the container is
    written by hand here.
    """
    from io import BytesIO

    entries = []
    for sz in sizes:
        buf = BytesIO()
        render(sz).save(buf, format="PNG")
        entries.append((sz, buf.getvalue()))

    count = len(entries)
    offset = 6 + 16 * count
    out = bytearray()
    out += struct.pack("<HHH", 0, 1, count)
    for sz, data in entries:
        dim = 0 if sz >= 256 else sz
        out += struct.pack(
            "<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
    for _, data in entries:
        out += data
    path.write_bytes(bytes(out))


def main() -> None:
    write_ico(ICO_PATH)
    render(CANVAS).save(PNG_PATH, format="PNG")
    print(f"wrote {ICO_PATH}")
    print(f"wrote {PNG_PATH}")


if __name__ == "__main__":
    main()

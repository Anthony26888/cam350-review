"""Alignment of a drill file to the Gerber artwork.

An NC drill file is written in the coordinate system of the CAM job, which
is usually not the system the Gerber files of the same board use.  The
holes of the board are in the pads, so the offset between the two systems
can be found by matching the holes against the paste.

The matching uses the machinery of
:mod:`services.gerber.origin_aligner`, which solves for the offset that
puts the most points of one set onto the points of the other one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from services.gerber.origin_aligner import estimate_offset_bbox, solve_offset_median


@dataclass
class DrillAlignResult:
    """The outcome of the alignment."""

    offset_x: float = 0.0
    offset_y: float = 0.0
    n_matched: int = 0
    n_total: int = 0
    median_residual: float = -1.0
    method: str = "none"

    @property
    def applied(self) -> bool:
        """True when an offset was found."""
        return self.method != "none" and self.n_matched > 0

    def summary(self) -> str:
        if not self.applied:
            return "Drill: no alignment"
        return ("Drill: offset {x:+.3f} / {y:+.3f} mm, "
                "{m}/{t} holes matched, residual {r:.3f} mm").format(
                    x=self.offset_x, y=self.offset_y, m=self.n_matched,
                    t=self.n_total, r=self.median_residual)


def align_drill(
    drill_points: Sequence[Tuple[float, float]],
    reference_points: Sequence[Tuple[float, float]],
    board_bbox: Optional[Tuple[float, float, float, float]] = None,
    distance_threshold: Optional[float] = None,
) -> DrillAlignResult:
    """Find the offset that puts the drill holes onto the reference points.

    ``drill_points`` are the holes in the coordinate system of the drill
    file, ``reference_points`` the pads of the board in the coordinate
    system of the Gerber files.  The returned offset is the shift that has
    to be applied to the drill points.

    When there are no reference points the board outline is used instead:
    the drill is then only moved so that the middle of the drill matches
    the middle of the board.
    """
    result = DrillAlignResult(n_total=len(drill_points))
    if not drill_points:
        return result

    drill = np.asarray(drill_points, dtype=np.float64)

    if not reference_points:
        # Only the board outline is known: line the middle of the drill up
        # with the middle of the board.
        if board_bbox is None:
            return result
        origin_x, origin_y, width, height = board_bbox
        offset0 = estimate_offset_bbox(
            drill[:, 0].tolist(), drill[:, 1].tolist(),
            (origin_x, origin_y), width, height,
        )
        result.offset_x = float(offset0[0])
        result.offset_y = float(offset0[1])
        result.method = "outline"
        return result

    reference = np.asarray(reference_points, dtype=np.float64)

    if board_bbox is not None:
        origin_x, origin_y, width, height = board_bbox
        offset0 = estimate_offset_bbox(
            drill[:, 0].tolist(), drill[:, 1].tolist(),
            (origin_x, origin_y), width, height,
        )
    else:
        offset0 = np.zeros(2, dtype=np.float64)

    solved = solve_offset_median(
        reference, drill, offset0, dist_threshold=distance_threshold,
    )
    if solved is None:
        return result

    offset, n_matched, residual = solved
    result.offset_x = float(offset[0])
    result.offset_y = float(offset[1])
    result.n_matched = int(n_matched)
    result.median_residual = float(residual)
    result.method = "paste"
    return result


def points_bbox(points: Sequence[Tuple[float, float]]) -> Optional[Tuple[float, float, float, float]]:
    """The bounding box of a list of points."""
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def shift_render_data(render_data, offset_x: float, offset_y: float) -> None:
    """Move every flashed shape of a render model."""
    if not offset_x and not offset_y:
        return
    for flash in getattr(render_data, "flashes", []):
        flash.cx += offset_x
        flash.cy += offset_y
    for line in getattr(render_data, "lines", []):
        line.x1 += offset_x
        line.y1 += offset_y
        line.x2 += offset_x
        line.y2 += offset_y
    for arc in getattr(render_data, "arcs", []):
        arc.x1 += offset_x
        arc.y1 += offset_y
        arc.x2 += offset_x
        arc.y2 += offset_y
        arc.cx += offset_x
        arc.cy += offset_y


def shift_points(points: Sequence[Tuple[float, float]],
                 offset_x: float, offset_y: float) -> List[Tuple[float, float]]:
    """Move a list of points by the given offset."""
    return [(x + offset_x, y + offset_y) for x, y in points]

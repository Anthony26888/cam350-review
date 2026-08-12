import math
from typing import Tuple


def mirror_y(x: float, y: float, center_x: float) -> Tuple[float, float]:
    """Mirror a point across the vertical axis passing through center_x."""
    return 2.0 * center_x - x, y


def mirror_x(x: float, y: float, center_y: float) -> Tuple[float, float]:
    """Mirror a point across the horizontal axis passing through center_y."""
    return x, 2.0 * center_y - y


def _rotate(x: float, y: float, angle: float) -> Tuple[float, float]:
    theta = math.radians(angle)
    c, s = math.cos(theta), math.sin(theta)
    return x * c - y * s, x * s + y * c


def apply_transform(
    x: float,
    y: float,
    mirror: bool,
    angle: float,
    off_x: float,
    off_y: float,
    center_x: float = 0.0,
    center_y: float = 0.0,
    mirror_x: bool = False,
) -> Tuple[float, float]:
    """Apply flip -> rotate -> offset pipeline in gerber space.

    `mirror` mirrors across the Y axis (left-right, x -> 2*center_x - x);
    `mirror_x` mirrors across the X axis (top-bottom, y -> 2*center_y - y).
    """
    if mirror:
        x = 2.0 * center_x - x
    if mirror_x:
        y = 2.0 * center_y - y
    x, y = _rotate(x, y, angle)
    return x + off_x, y + off_y


def transform_rot(rot: float, mirror: bool, angle: float, mirror_x: bool = False) -> float:
    """Return the effective aperture rotation after flips + rotate.

    Each mirror reverses angular direction, so with an odd number of mirrors
    the aperture rotation becomes angle - rot; with none (or two) it is
    angle + rot.
    """
    if mirror != mirror_x:
        return (angle - rot) % 360.0
    return (angle + rot) % 360.0

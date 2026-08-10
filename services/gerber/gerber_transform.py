import math
from typing import Tuple


def mirror_y(x: float, y: float, center_x: float) -> Tuple[float, float]:
    """Mirror a point across the vertical axis passing through center_x."""
    return 2.0 * center_x - x, y


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
) -> Tuple[float, float]:
    """Apply flip -> rotate -> offset pipeline in gerber space."""
    if mirror:
        x = 2.0 * center_x - x
    x, y = _rotate(x, y, angle)
    return x + off_x, y + off_y


def transform_rot(rot: float, mirror: bool, angle: float) -> float:
    """Return the effective aperture rotation after flip + rotate.

    Mirroring reverses angular direction, so with flip the aperture rotation
    becomes angle - rot; without flip it is angle + rot.
    """
    if mirror:
        return (angle - rot) % 360.0
    return (angle + rot) % 360.0
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


class AffineTransform:
    """The display transform, prepared once for many points.

    The pipeline of :func:`apply_transform` is affine, so it can be written
    as a single matrix.  Preparing it once and applying it to a whole layer
    avoids a function call and a trigonometry per point, which is what
    dominates the building of the paths of a large layer.
    """

    __slots__ = ("a11", "a12", "a21", "a22", "bx", "by", "identity")

    def __init__(self, mirror: bool = False, angle: float = 0.0,
                 off_x: float = 0.0, off_y: float = 0.0,
                 center_x: float = 0.0, center_y: float = 0.0,
                 mirror_x: bool = False):
        sx = -1.0 if mirror else 1.0
        sy = -1.0 if mirror_x else 1.0
        theta = math.radians(angle)
        c, s = math.cos(theta), math.sin(theta)
        self.a11 = c * sx
        self.a12 = -s * sy
        self.a21 = s * sx
        self.a22 = c * sy
        mx = 2.0 * center_x if mirror else 0.0
        my = 2.0 * center_y if mirror_x else 0.0
        self.bx = mx * c - my * s + off_x
        self.by = mx * s + my * c + off_y
        self.identity = (self.a11 == 1.0 and self.a12 == 0.0
                         and self.a21 == 0.0 and self.a22 == 1.0
                         and self.bx == 0.0 and self.by == 0.0)

    def apply(self, x: float, y: float) -> Tuple[float, float]:
        """Transform one point."""
        return (self.a11 * x + self.a12 * y + self.bx,
                self.a21 * x + self.a22 * y + self.by)

    def apply_local(self, x: float, y: float) -> Tuple[float, float]:
        """Transform a point that is relative to a flash position.

        The offset and the centre of the board do not apply to it, only the
        mirror and the rotation do.
        """
        return (self.a11 * x + self.a12 * y,
                self.a21 * x + self.a22 * y)


def apply_inverse_transform(
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
    """Invert apply_transform: offset -> rotate back -> flip back.

    Given a point already in display (transformed) gerber space, recover the
    original gerber coordinate. Mirrors are self-inverse and rotation is
    reversed. Used to store measurement anchors in source coordinates so they
    stay glued to the board when the display transform changes.
    """
    x -= off_x
    y -= off_y
    theta = math.radians(-angle)
    c, s = math.cos(theta), math.sin(theta)
    rx = x * c - y * s
    ry = x * s + y * c
    if mirror:
        rx = 2.0 * center_x - rx
    if mirror_x:
        ry = 2.0 * center_y - ry
    return rx, ry


def transform_rot(rot: float, mirror: bool, angle: float, mirror_x: bool = False) -> float:
    """Return the effective aperture rotation after flips + rotate.

    Each mirror reverses angular direction, so with an odd number of mirrors
    the aperture rotation becomes angle - rot; with none (or two) it is
    angle + rot.
    """
    if mirror != mirror_x:
        return (angle - rot) % 360.0
    return (angle + rot) % 360.0

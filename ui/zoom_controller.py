"""Zoom behaviour of the Gerber viewer.

The zoom of the viewer follows the behaviour of the reference EDA tool so
that the muscle memory transfers:

* the mouse wheel changes the zoom by a fixed factor per notch, and the
  factor is larger when the wheel is spun quickly,
* the zoom is anchored at the pointer, so the point under the cursor stays
  where it is,
* the zoom is limited, and the view offers a list of preset levels,
* the keyboard has the same shortcuts.

The zoom factor is the same number the reference tool uses: it is the
number of pixels per millimetre divided by the number of pixels a
millimetre covers on a screen with the reference resolution.
"""

from __future__ import annotations

import time

#: Pixels a millimetre covers on a screen with the reference resolution
#: (91 dots per inch).  A zoom factor of 1.0 is therefore "as big as the
#: artwork really is".
REFERENCE_PX_PER_MM = 91.0 / 25.4

#: Magic scale factors of the reference implementation, one per platform.
MSW_SCALE = 0.005
MAC_SCALE = 0.01
GTK3_SCALE = 0.002

#: Multiplier for the manual scale setting.
MANUAL_SCALE_FACTOR = 0.001

#: Scale of the accelerating zoom controller.
DEFAULT_ACCELERATION_SCALE = 5.0

#: How long the accelerating controller waits before it slows down again.
DEFAULT_ACCELERATION_TIMEOUT_MS = 500

#: The smallest step of the accelerating controller.
MINIMUM_STEP = 1.05

#: Zoom limits of the reference implementation.
ZOOM_FACTOR_MIN = 0.02
ZOOM_FACTOR_MAX = 5000.0

#: The preset zoom levels of the reference implementation.
ZOOM_PRESETS = (
    0.022, 0.035, 0.05, 0.08, 0.13, 0.22, 0.35, 0.6, 1.0,
    2.2, 3.5, 5.0, 8.0, 13.0, 22.0, 35.0, 50.0, 80.0, 130.0, 220.0,
)

#: The zoom step of the keyboard shortcuts snaps to the next preset.
KEYBOARD_STEP = 1.3


def zoom_factor_from_scale(scale_px_per_mm: float) -> float:
    """Convert a scale in pixels per millimetre into a zoom factor."""
    if scale_px_per_mm <= 0:
        return ZOOM_FACTOR_MIN
    return scale_px_per_mm / REFERENCE_PX_PER_MM


def scale_from_zoom_factor(factor: float) -> float:
    """Convert a zoom factor into a scale in pixels per millimetre."""
    return factor * REFERENCE_PX_PER_MM


def clamp_zoom_factor(factor: float) -> float:
    """Limit a zoom factor to the range the reference implementation uses."""
    return min(ZOOM_FACTOR_MAX, max(ZOOM_FACTOR_MIN, factor))


class ConstantZoomController:
    """A fixed zoom step per wheel notch."""

    def __init__(self, scale: float = MSW_SCALE):
        self._scale = scale

    @property
    def scale(self) -> float:
        return self._scale

    def scale_for_rotation(self, rotation: int) -> float:
        """The factor the zoom changes by for one wheel event."""
        rotation = min(100, max(-100, rotation))
        delta = rotation * self._scale
        if rotation > 0:
            return 1.0 + delta
        return 1.0 / (1.0 - delta)


class AcceleratingZoomController:
    """A zoom step that grows while the wheel is spun quickly."""

    def __init__(self, scale: float = DEFAULT_ACCELERATION_SCALE,
                 timeout_ms: int = DEFAULT_ACCELERATION_TIMEOUT_MS,
                 clock=None):
        self._scale = scale
        self._timeout_ms = timeout_ms
        self._clock = clock or (lambda: time.monotonic() * 1000.0)
        self._previous_timestamp = 0.0
        self._previous_positive = True

    @property
    def scale(self) -> float:
        return self._scale

    def scale_for_rotation(self, rotation: int) -> float:
        timestamp = self._clock()
        elapsed = timestamp - self._previous_timestamp
        self._previous_timestamp = timestamp

        if elapsed < self._timeout_ms and ((rotation > 0) == self._previous_positive):
            factor = (2.05 * self._scale / 5.0) - elapsed / self._timeout_ms
            factor = max(factor, MINIMUM_STEP)
            if rotation < 0:
                factor = 1.0 / factor
        else:
            factor = MINIMUM_STEP if rotation > 0 else 1.0 / MINIMUM_STEP
        self._previous_positive = rotation > 0
        return factor

    def reset(self) -> None:
        """Forget the timing, so the next event starts from the slow step."""
        self._previous_timestamp = 0.0


def create_zoom_controller(accelerate: bool = False, manual_scale: float | None = None,
                           platform: str = "msw") -> ConstantZoomController | AcceleratingZoomController:
    """Build the zoom controller the settings ask for."""
    if accelerate:
        return AcceleratingZoomController()
    if manual_scale is not None:
        return ConstantZoomController(MANUAL_SCALE_FACTOR * manual_scale)
    if platform == "mac":
        return ConstantZoomController(MAC_SCALE)
    if platform == "gtk3":
        return ConstantZoomController(GTK3_SCALE)
    return ConstantZoomController(MSW_SCALE)


def next_preset(factor: float, direction: int) -> float:
    """The preset that follows the given zoom factor.

    The keyboard shortcut multiplies the zoom by a fixed step and then
    snaps to the closest preset, exactly like the reference implementation.
    """
    if direction > 0:
        wanted = factor * KEYBOARD_STEP
        for preset in ZOOM_PRESETS:
            if preset >= wanted:
                return preset
        return ZOOM_PRESETS[-1]
    wanted = factor / KEYBOARD_STEP
    for preset in reversed(ZOOM_PRESETS):
        if preset <= wanted:
            return preset
    return ZOOM_PRESETS[0]

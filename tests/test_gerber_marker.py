import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from ui.gerber_viewer import (
    _CROSS_BOARD_RATIO, PickPlaceMarker, MarkerOverlayItem,
    _nearest_pad_size, _crosshair_half, _flash_size,
)
from services.gerber.gerber_render import FlashShape, ApertureMacro

_SCALE = 10.0


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _render(marker: PickPlaceMarker) -> QImage:
    half = marker._half
    span = int(4 * half * _SCALE) + 16
    img = QImage(span, span, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.translate(span / 2.0, span / 2.0)
    p.scale(_SCALE, _SCALE)
    marker.paint(p, None)
    p.end()
    return img


def _red_pix(marker: PickPlaceMarker) -> int:
    img = _render(marker)
    count = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.red() > 150 and c.green() < 100:
                count += 1
    return count


def test_marker_uses_given_half():
    m = PickPlaceMarker(0.0, "R1", "", 3.0)
    assert m._half == 3.0


def test_cross_board_ratio_positive():
    assert _CROSS_BOARD_RATIO > 0
    assert _CROSS_BOARD_RATIO < 0.1


def test_arrow_visible_at_each_rotation():
    for rot in (0, 90, 180, 270):
        m = PickPlaceMarker(rot, "R1", "", 3.0)
        assert _red_pix(m) > 50, f"arrow barely visible at rot={rot}"


def test_arrow_direction_matches_rotation():
    m0 = PickPlaceMarker(0.0, "R", "", 3.0)
    assert m0._rad == pytest.approx(0.0)
    # direction uses -cos/-sin: 0 deg points along -x
    dx, dy = -math.cos(0.0), -math.sin(0.0)
    assert dx == pytest.approx(-1.0)
    assert dy == pytest.approx(0.0)


def test_size_scales_with_half():
    small = PickPlaceMarker(0.0, "R", "", 1.0)
    big = PickPlaceMarker(0.0, "R", "", 4.0)
    assert _red_pix(big) > _red_pix(small)


def test_macro_flash_size_bbox():
    macro = ApertureMacro()
    macro.polygons.append([
        (0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0),
    ])
    fl = FlashShape(0.0, 0.0, kind="macro", macro=macro)
    assert _flash_size(fl) == pytest.approx(2.0)


def test_nearest_pad_size_finds_pad():
    pads = [(0.0, 0.0, 1.0), (10.0, 10.0, 2.0)]
    assert _nearest_pad_size(pads, 0.0, 0.0) == pytest.approx(1.0)
    # within tolerance of the 2.0 pad
    assert _nearest_pad_size(pads, 9.5, 9.5) == pytest.approx(2.0)


def test_nearest_pad_size_none_far_away():
    pads = [(0.0, 0.0, 1.0)]
    assert _nearest_pad_size(pads, 20.0, 20.0) is None


def test_crosshair_half_scaling():
    assert _crosshair_half(0.5, 2.0) == pytest.approx(0.575)
    assert _crosshair_half(0.05, 2.0) == pytest.approx(0.15)  # min clamp
    assert _crosshair_half(3.0, 2.0) == pytest.approx(2.0)    # max = fallback
    assert _crosshair_half(None, 2.0) == pytest.approx(2.0)   # no pad


def _render_overlay(overlay: MarkerOverlayItem) -> QImage:
    half = max(3.0, max(m[3] for m in overlay._markers))
    span = int(4 * half * _SCALE) + 16
    img = QImage(span, span, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.translate(span / 2.0, span / 2.0)
    p.scale(_SCALE, _SCALE)
    overlay.paint(p, None)
    p.end()
    return img


def _overlay_red_pix(overlay: MarkerOverlayItem) -> int:
    img = _render_overlay(overlay)
    count = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.red() > 150 and c.green() < 100:
                count += 1
    return count


def _overlay_green_pix(overlay: MarkerOverlayItem) -> int:
    img = _render_overlay(overlay)
    count = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.red() < 100 and c.green() > 150:
                count += 1
    return count


def test_overlay_show_unselected_true_draws_markers():
    overlay = MarkerOverlayItem([(0.0, 0.0, 0.0, 3.0)], show_unselected=True)
    assert _overlay_red_pix(overlay) > 0


def test_overlay_hidden_when_unselected_and_not_selected():
    overlay = MarkerOverlayItem([(0.0, 0.0, 0.0, 3.0)], show_unselected=False)
    assert _overlay_red_pix(overlay) == 0


def test_overlay_selected_still_visible_when_unselected_hidden():
    overlay = MarkerOverlayItem([(0.0, 0.0, 0.0, 3.0)], show_unselected=False)
    overlay.set_selected(0)
    assert _overlay_green_pix(overlay) > 0
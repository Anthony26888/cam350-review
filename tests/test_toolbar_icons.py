import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import (
    _board_icon,
    _doc_icon,
    _ok_checked_icon,
    _sheet_icon,
    _wrench_icon,
)


def _pixels(pm):
    from PySide6.QtGui import QColor
    img = pm.toImage()
    out = []
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor(img.pixel(x, y))
            out.append((c.red(), c.green(), c.blue(), c.alpha()))
    return img.width(), img.height(), out


def _opaque_pixels(pm):
    return [(r, g, b) for r, g, b, a in _pixels(pm)[2] if a > 16]


def _assert_gray(pixels, saturation_limit=2):
    assert pixels, "icon rendered nothing"
    # skip near-transparent/black antialiasing fringes
    visible = [(r, g, b) for r, g, b in pixels if max(r, g, b) >= 32]
    assert visible, "icon rendered nothing visible"
    for r, g, b in visible:
        spread = max(r, g, b) - min(r, g, b)
        assert spread <= saturation_limit, f"not gray: {(r, g, b)}"


def _assert_has_color(pixels):
    assert any(
        abs(r - g) > 30 or abs(g - b) > 30 or abs(r - b) > 30
        for r, g, b in pixels
    ), "expected at least one saturated (colored) pixel"


def _pix(icon, mode, size=26):
    pm = icon.pixmap(size, size, mode)
    assert not pm.isNull()
    return pm


def test_colored_icons_gray_when_disabled():
    QApplication.instance() or QApplication([])
    for factory in (_board_icon, _ok_checked_icon, _sheet_icon):
        icon = factory()
        for mode, want_color in (
            (QIcon.Mode.Normal, True),
            (QIcon.Mode.Disabled, False),
        ):
            pm = _pix(icon, mode)
            w, h, px = _pixels(pm)
            # Offscreen QPixmap has no real alpha channel (transparent fill
            # reads back opaque), so only assert transparency where the
            # platform actually preserves it (e.g. Windows runtime).
            supports_alpha = any(a == 0 for _, _, _, a in px)
            if supports_alpha:
                # transparency preserved: corners stay fully transparent,
                # no solid black background block (regression test for the
                # black-background bug from pixel-based grayscaling)
                corners = [px[0], px[w - 1], px[(h - 1) * w], px[h * w - 1]]
                assert all(a == 0 for _, _, _, a in corners), \
                    f"{factory.__name__} {mode}: corner lost transparency"
                opaque_black = sum(
                    1 for r, g, b, a in px if a > 16 and max(r, g, b) < 16
                )
                assert opaque_black <= 4, \
                    f"{factory.__name__} {mode}: {opaque_black} opaque black pixels"
            opaque = [(r, g, b) for r, g, b, a in px if a > 16]
            if want_color:
                _assert_has_color(opaque)   # accent kept when enabled
            else:
                # disabled is re-rendered with the theme gray (#94A3B8 family),
                # same ceiling as the other toolbar icons
                _assert_gray(opaque, saturation_limit=40)


def test_mono_icon_still_gray_when_disabled():
    QApplication.instance() or QApplication([])
    for factory in (_doc_icon, _wrench_icon):
        icon = factory()
        # theme disabled stroke itself is #94A3B8 (spread 36); allow one
        # point of rounding from Qt's offscreen pixmap scaling
        _assert_gray(_opaque_pixels(_pix(icon, QIcon.Mode.Disabled)),
                     saturation_limit=40)


def test_sheet_icon_has_green_accent_when_enabled():
    QApplication.instance() or QApplication([])
    opaque = _opaque_pixels(_pix(_sheet_icon(), QIcon.Mode.Normal))
    assert any(g > r + 30 and g > b + 30 for r, g, b in opaque), \
        "sheet icon lost its green Excel accent"

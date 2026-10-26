import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from lucide import get_icon_list

from ui.icons import clear_icon_cache, lucide_qicon, status_icon


def test_lucide_icon_names_exist():
    available = set(get_icon_list())
    used = [
        "file-plus", "folder-open", "save", "file-spreadsheet", "table-2",
        "crosshair", "search-check", "circuit-board", "file-text", "download",
        "clipboard-list", "cpu", "check-check", "trash", "settings",
        "target", "route", "rotate-cw",
        "triangles-centerline-dashed-horizontal",
        "triangles-centerline-dashed-vertical",
        "component", "grid-3x3", "check", "undo-2", "list-x",
        "rotate-cw-square", "scan", "image-down", "refresh-cw", "ruler",
        "panel-left-close", "panel-left-open", "circle", "funnel-x",
    ]
    for name in used:
        assert name in available, f"Icon '{name}' is not in Lucide library"


def test_lucide_qicon_renders_valid_pixmaps():
    app = QApplication.instance() or QApplication([])
    icon = lucide_qicon("settings", size=24)
    assert not icon.isNull()

    pm_normal = icon.pixmap(24, 24, QIcon.Mode.Normal)
    assert not pm_normal.isNull()
    assert pm_normal.width() == 24

    pm_disabled = icon.pixmap(24, 24, QIcon.Mode.Disabled)
    assert not pm_disabled.isNull()


def test_status_icon_cached():
    app = QApplication.instance() or QApplication([])
    s1 = status_icon(True)
    s2 = status_icon(True)
    assert s1 is s2

    u1 = status_icon(False)
    u2 = status_icon(False)
    assert u1 is u2
    assert s1 is not u1


def test_clear_icon_cache_rebuilds_theme_icons():
    app = QApplication.instance() or QApplication([])
    first = lucide_qicon("settings", size=24)
    checked = status_icon(True)

    clear_icon_cache()

    second = lucide_qicon("settings", size=24)
    assert second is not first
    assert status_icon(True) is not checked

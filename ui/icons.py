from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from lucide import lucide_icon

from ui.style import icon_color, icon_disabled_color

_STATUS_CHECKED_ICON: Optional[QIcon] = None
_STATUS_UNCHECKED_ICON: Optional[QIcon] = None


@lru_cache(maxsize=512)
def _render_pixmap(
    name: str,
    size: int,
    stroke: str,
    stroke_width: float,
    fill: str,
) -> QPixmap:
    svg = lucide_icon(
        name,
        width=size,
        height=size,
        stroke=stroke,
        stroke_width=stroke_width,
        fill=fill,
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pixmap


@lru_cache(maxsize=256)
def lucide_qicon(
    name: str,
    *,
    accent: Optional[str] = None,
    color: Optional[str] = None,
    disabled_color: Optional[str] = None,
    size: int = 24,
    stroke_width: float = 1.75,
    fill: str = "none",
) -> QIcon:
    normal_stroke = accent or color or icon_color()
    disabled_stroke = disabled_color or icon_disabled_color()
    icon = QIcon()
    for mode, stroke in (
        (QIcon.Mode.Normal, normal_stroke),
        (QIcon.Mode.Disabled, disabled_stroke),
    ):
        for ratio in (1, 2):
            px_size = int(size * ratio)
            pm = _render_pixmap(name, px_size, stroke, stroke_width, fill)
            icon.addPixmap(pm, mode)
    return icon


def clear_icon_cache() -> None:
    global _STATUS_CHECKED_ICON, _STATUS_UNCHECKED_ICON
    lucide_qicon.cache_clear()
    _render_pixmap.cache_clear()
    _STATUS_CHECKED_ICON = None
    _STATUS_UNCHECKED_ICON = None


def status_icon(checked: bool) -> QIcon:
    global _STATUS_CHECKED_ICON, _STATUS_UNCHECKED_ICON
    if checked:
        if _STATUS_CHECKED_ICON is None:
            _STATUS_CHECKED_ICON = lucide_qicon(
                "check",
                accent="#22C55E",
                disabled_color="#22C55E",
                size=16,
                stroke_width=2.4,
            )
        return _STATUS_CHECKED_ICON
    if _STATUS_UNCHECKED_ICON is None:
        _STATUS_UNCHECKED_ICON = lucide_qicon(
            "circle",
            accent="#F97316",
            disabled_color="#F97316",
            size=16,
            stroke_width=2.4,
        )
    return _STATUS_UNCHECKED_ICON

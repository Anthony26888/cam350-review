"""The in-memory model of one parsed Gerber file."""

from __future__ import annotations

from dataclasses import dataclass, field

from .am_primitive import ApertureMacro
from .dcode import DCode
from .draw_item import DrawItem, bounding_box
from .units import IU_PER_MM, CoordinateFormat


@dataclass
class LayerParams:
    """Parameters that apply to one layer of a file."""

    name: str = ""
    negative: bool = False
    x_repeat: int = 1
    y_repeat: int = 1
    step_x: float = 0.0
    step_y: float = 0.0


@dataclass
class FileImage:
    """Everything the parser extracted from one Gerber file."""

    items: list[DrawItem] = field(default_factory=list)
    apertures: dict[int, DCode] = field(default_factory=dict)
    macros: dict[str, ApertureMacro] = field(default_factory=dict)
    layer: LayerParams = field(default_factory=LayerParams)
    format: CoordinateFormat | None = None
    unit_scale: float = 1.0  # millimetres per file unit
    image_negative: bool = False
    attributes: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False

    @property
    def bbox(self) -> tuple[int, int, int, int] | None:
        """Bounding box in internal units."""
        return bounding_box(self.items)

    @property
    def bbox_mm(self) -> tuple[float, float, float, float] | None:
        """Bounding box in millimetres."""
        box = self.bbox
        if box is None:
            return None
        return (box[0] / IU_PER_MM, box[1] / IU_PER_MM,
                box[2] / IU_PER_MM, box[3] / IU_PER_MM)

    @property
    def stroke_count(self) -> int:
        return sum(1 for item in self.items if item.kind in ("segment", "arc"))

    @property
    def flash_count(self) -> int:
        return sum(1 for item in self.items if item.filled)

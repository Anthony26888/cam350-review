from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models.review import ReviewRecord
from services.gerber.offset_applier import rotate_point


class PanelError(Exception):
    """Raised when a panelize operation cannot run."""


@dataclass
class PanelBlock:
    index: int = 0
    origin_x: float = 0.0
    origin_y: float = 0.0
    rotation: int = 0
    designator: str = ""

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "origin_x": self.origin_x,
            "origin_y": self.origin_y,
            "rotation": self.rotation,
            "designator": self.designator or "",
        }

    @staticmethod
    def from_dict(data: dict) -> "PanelBlock":
        return PanelBlock(
            index=int(data.get("index", 0)),
            origin_x=float(data.get("origin_x", 0.0)),
            origin_y=float(data.get("origin_y", 0.0)),
            rotation=int(data.get("rotation", 0)),
            designator=data.get("designator") or "",
        )


@dataclass
class PanelConfig:
    nx: int = 1
    ny: int = 1
    dx: float = 0.0
    dy: float = 0.0
    panel_origin_x: float = 0.0
    panel_origin_y: float = 0.0
    board_w: float = 0.0
    board_h: float = 0.0
    kind: str = "S"
    rename_designators: bool = True
    blocks: List[PanelBlock] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.blocks)

    @property
    def base_block(self) -> Optional[PanelBlock]:
        for b in self.blocks:
            if b.index == 0:
                return b
        return None

    def block_by_index(self, index: int) -> Optional[PanelBlock]:
        for b in self.blocks:
            if b.index == index:
                return b
        return None

    def rebuild_grid(self) -> "PanelConfig":
        """Rebuild block origins from the raster grid, keeping rotation per block."""
        old_rot = {b.index: b.rotation for b in self.blocks}
        old_names = {b.index: b.designator for b in self.blocks}
        new_blocks: List[PanelBlock] = []
        for ky in range(max(self.ny, 1)):
            for kx in range(max(self.nx, 1)):
                k = ky * self.nx + kx
                new_blocks.append(PanelBlock(
                    index=k,
                    origin_x=round(self.panel_origin_x + kx * self.dx, 6),
                    origin_y=round(self.panel_origin_y + ky * self.dy, 6),
                    rotation=old_rot.get(k, 0),
                    designator=old_names.get(k, ""),
                ))
        self.nx = max(self.nx, 1)
        self.ny = max(self.ny, 1)
        self.blocks = new_blocks
        return self

    def to_dict(self) -> dict:
        return {
            "nx": self.nx,
            "ny": self.ny,
            "dx": self.dx,
            "dy": self.dy,
            "panel_origin_x": self.panel_origin_x,
            "panel_origin_y": self.panel_origin_y,
            "board_w": self.board_w,
            "board_h": self.board_h,
            "kind": self.kind,
            "rename_designators": self.rename_designators,
            "blocks": [b.to_dict() for b in self.blocks],
        }

    @staticmethod
    def from_dict(data: dict) -> "PanelConfig":
        return PanelConfig(
            nx=int(data.get("nx", 1)),
            ny=int(data.get("ny", 1)),
            dx=float(data.get("dx", 0.0)),
            dy=float(data.get("dy", 0.0)),
            panel_origin_x=float(data.get("panel_origin_x", 0.0)),
            panel_origin_y=float(data.get("panel_origin_y", 0.0)),
            board_w=float(data.get("board_w", 0.0)),
            board_h=float(data.get("board_h", 0.0)),
            kind=data.get("kind", "S"),
            rename_designators=bool(data.get("rename_designators", True)),
            blocks=[PanelBlock.from_dict(b) for b in (data.get("blocks") or [])],
        )

def transform_point(
    x: float,
    y: float,
    cfg: PanelConfig,
    block: Optional[PanelBlock] = None,
) -> Tuple[float, float]:
    """Place a local board coordinate onto a panel board position.

    Local coordinates are referenced to the base board origin (block 0).
    A block's data point is rotated around the block origin and placed at the
    block's own origin on the panel, so the origin entered for a flipped
    (180°) block must be its top-right panel corner, while a normal block
    uses its bottom-left corner.
    """
    if block is None:
        return round(x, 6), round(y, 6)
    base = cfg.base_block
    if base is None:
        return round(x, 6), round(y, 6)
    ox, oy = base.origin_x, base.origin_y
    rx, ry = rotate_point(x - ox, y - oy, block.rotation)
    return round(block.origin_x + rx, 6), round(block.origin_y + ry, 6)


def is_panelized(records: List[ReviewRecord]) -> bool:
    return any(getattr(r, "block", 0) != 0 for r in records)


def base_records(records: List[ReviewRecord]) -> List[ReviewRecord]:
    return [r for r in records if getattr(r, "block", 0) == 0]


def panelize_records(
    records: List[ReviewRecord],
    cfg: PanelConfig,
) -> List[ReviewRecord]:
    if not cfg.blocks:
        raise PanelError("Panel config has no boards.")
    if is_panelized(records):
        raise PanelError(
            "Dữ liệu đã được panelize. Hãy xóa panelize trước "
            "(Tools > Clear Panelize)."
        )
    if not records:
        return []

    base = cfg.base_block

    result: List[ReviewRecord] = []
    for block in cfg.blocks:
        for rec in records:
            result.append(_clone_for_block(rec, cfg, block, base))
    return result


def _clone_for_block(
    rec: ReviewRecord,
    cfg: PanelConfig,
    block: PanelBlock,
    base: Optional[PanelBlock],
) -> ReviewRecord:
    eff_x = rec.new_x if rec.new_x is not None else rec.old_x
    eff_y = rec.new_y if rec.new_y is not None else rec.old_y
    eff_rot = rec.new_rotation if rec.new_rotation is not None else rec.old_rotation

    if base is not None and block.index == base.index and block.rotation == 0:
        px, py = rec.old_x, rec.old_y
        pr = eff_rot
        old_rotation = rec.old_rotation
    else:
        px, py = transform_point(eff_x, eff_y, cfg, block)
        pr = round((eff_rot + block.rotation) % 360, 6)
        old_rotation = round((rec.old_rotation + block.rotation) % 360, 6)

    base_designator = rec.base_designator or rec.designator
    designator = rec.designator
    if cfg.rename_designators and block.index != 0:
        designator = f"{base_designator}_{block.index + 1}"

    new_rec = ReviewRecord(
        designator=designator,
        mpn=rec.mpn,
        layer=rec.layer,
        old_x=px,
        old_y=py,
        old_rotation=old_rotation,
        status=rec.status,
        remark=rec.remark,
        review_time=rec.review_time,
        datasheet=rec.datasheet,
        checked=rec.checked,
        row_index=rec.row_index,
        prescreen_flags=list(rec.prescreen_flags),
        is_ic_rotation=rec.is_ic_rotation,
        block=block.index,
        block_rotation=block.rotation,
        base_designator=base_designator,
    )
    if base is not None and block.index == base.index and block.rotation == 0:
        new_rec.new_x = rec.new_x
        new_rec.new_y = rec.new_y
        new_rec.new_rotation = rec.new_rotation
    elif rec.has_modifications:
        new_rec.new_x = px
        new_rec.new_y = py
        new_rec.new_rotation = pr
    return new_rec
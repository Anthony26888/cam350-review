from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class EcoAdded:
    designator: str = ""
    mpn: str = ""
    layer: str = ""
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0


@dataclass
class EcoRemoved:
    designator: str = ""
    mpn: str = ""
    layer: str = ""
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0


@dataclass
class EcoMoved:
    designator: str = ""
    old_x: float = 0.0
    old_y: float = 0.0
    old_rotation: float = 0.0
    new_x: float = 0.0
    new_y: float = 0.0
    new_rotation: float = 0.0
    dx: float = 0.0
    dy: float = 0.0
    drot: float = 0.0


@dataclass
class EcoMpnChanged:
    designator: str = ""
    old_mpn: str = ""
    new_mpn: str = ""


@dataclass
class EcoDuplicate:
    designator: str = ""
    side: str = ""  # "old" or "new"
    count: int = 0


@dataclass
class EcoDiff:
    added: List[EcoAdded] = field(default_factory=list)
    removed: List[EcoRemoved] = field(default_factory=list)
    moved: List[EcoMoved] = field(default_factory=list)
    mpn_changed: List[EcoMpnChanged] = field(default_factory=list)
    old_duplicates: List[EcoDuplicate] = field(default_factory=list)
    new_duplicates: List[EcoDuplicate] = field(default_factory=list)
    old_unique: int = 0
    new_unique: int = 0

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.moved or self.mpn_changed
                    or self.old_duplicates or self.new_duplicates)

    @property
    def counts(self) -> Tuple[int, int, int, int]:
        return (len(self.added), len(self.removed),
                len(self.moved), len(self.mpn_changed))

    @property
    def duplicate_count(self) -> int:
        return len(self.old_duplicates) + len(self.new_duplicates)


def _norm(des: str) -> str:
    return (des or "").strip().upper()


def _circ_dist(a: float, b: float) -> float:
    d = abs((a or 0.0) - (b or 0.0)) % 360.0
    return min(d, 360.0 - d)


def _eff(rec) -> Tuple[float, float, float]:
    x = rec.new_x if rec.new_x is not None else rec.old_x
    y = rec.new_y if rec.new_y is not None else rec.old_y
    r = rec.new_rotation if rec.new_rotation is not None else rec.old_rotation
    return float(x or 0.0), float(y or 0.0), float(r or 0.0)


def compare_revisions(
    old_records,
    new_components,
    move_tol_mm: float = 0.01,
    rot_tol_deg: float = 1.0,
) -> EcoDiff:
    """Compare current session records (old) against a new PickPlace file.

    old_records: ReviewRecord list (effective values win).
    new_components: PickPlaceComponent list from the new file.
    Only block-0 records participate (panelize clones are derived data).
    """
    diff = EcoDiff()
    move_tol = max(float(move_tol_mm), 0.0)
    rot_tol = max(float(rot_tol_deg), 0.0)

    old_map: Dict[str, object] = {}
    old_seen: Dict[str, int] = {}
    old_rep: Dict[str, str] = {}
    for r in old_records or []:
        if getattr(r, "block", 0):
            continue
        key = _norm(r.designator)
        if not key:
            continue
        old_seen[key] = old_seen.get(key, 0) + 1
        if key not in old_map:
            old_map[key] = r
            old_rep[key] = r.designator
    for key in sorted(old_seen):
        if old_seen[key] > 1:
            diff.old_duplicates.append(EcoDuplicate(
                designator=old_rep[key], side="old", count=old_seen[key]))

    new_map: Dict[str, object] = {}
    new_seen: Dict[str, int] = {}
    new_rep: Dict[str, str] = {}
    for c in new_components or []:
        key = _norm(c.designator)
        if not key:
            continue
        new_seen[key] = new_seen.get(key, 0) + 1
        if key not in new_map:
            new_map[key] = c
            new_rep[key] = c.designator
    for key in sorted(new_seen):
        if new_seen[key] > 1:
            diff.new_duplicates.append(EcoDuplicate(
                designator=new_rep[key], side="new", count=new_seen[key]))

    diff.old_unique = len(old_map)
    diff.new_unique = len(new_map)

    for key in sorted(set(new_map) - set(old_map)):
        c = new_map[key]
        diff.added.append(EcoAdded(
            designator=c.designator, mpn=c.mpn or "", layer=c.layer or "",
            x=float(c.x or 0.0), y=float(c.y or 0.0),
            rotation=float(c.rotation or 0.0)))

    for key in sorted(set(old_map) - set(new_map)):
        r = old_map[key]
        ox, oy, orot = _eff(r)
        diff.removed.append(EcoRemoved(
            designator=r.designator, mpn=r.mpn or "", layer=r.layer or "",
            x=ox, y=oy, rotation=orot))

    for key in sorted(set(old_map) & set(new_map)):
        r = old_map[key]
        c = new_map[key]
        ox, oy, orot = _eff(r)
        nx, ny, nrot = (float(c.x or 0.0), float(c.y or 0.0),
                        float(c.rotation or 0.0))
        dx, dy, drot = nx - ox, ny - oy, _circ_dist(nrot, orot)
        if abs(dx) > move_tol or abs(dy) > move_tol or drot > rot_tol:
            diff.moved.append(EcoMoved(
                designator=r.designator, old_x=ox, old_y=oy, old_rotation=orot,
                new_x=nx, new_y=ny, new_rotation=nrot,
                dx=round(dx, 4), dy=round(dy, 4), drot=round(drot, 4)))
        old_mpn = (r.mpn or "").strip()
        new_mpn = (c.mpn or "").strip()
        if old_mpn and new_mpn and old_mpn.upper() != new_mpn.upper():
            diff.mpn_changed.append(EcoMpnChanged(
                designator=r.designator, old_mpn=old_mpn, new_mpn=new_mpn))
    return diff

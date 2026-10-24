from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models.bom import BomRow


@dataclass
class BomDiff:
    """Two-way compare between BOM rows and PickPlace designators."""
    missing: List[Tuple[BomRow, List[str]]] = field(default_factory=list)
    extra: List[str] = field(default_factory=list)
    mpn_mismatch: List[Tuple[str, str, str, int]] = field(default_factory=list)
    mpn_fillable: List[Tuple[str, str, int]] = field(default_factory=list)
    qty_notes: List[Tuple[BomRow, int]] = field(default_factory=list)
    conflicts: List[Tuple[str, List[Tuple[str, int]]]] = field(default_factory=list)
    bom_map: Dict[str, Tuple[str, int]] = field(default_factory=dict)


def _norm(des: str) -> str:
    return (des or "").strip().upper()


def compare(
    bom_rows: List[BomRow],
    pickplace: List[Tuple[str, str, str]],
) -> BomDiff:
    """Compare BOM against PickPlace.

    pickplace: list of (designator, mpn, layer) from review records.
    First BOM row wins on duplicate designators; later ones are conflicts.
    """
    diff = BomDiff()
    bom_map: Dict[str, Tuple[str, int]] = {}
    seen_claims: Dict[str, List[Tuple[str, int]]] = {}
    for row in bom_rows:
        for d in row.designators:
            key = _norm(d)
            if not key:
                continue
            seen_claims.setdefault(key, []).append((row.mpn, row.stt))
            if key not in bom_map:
                bom_map[key] = (row.mpn, row.stt)
    for key, claims in seen_claims.items():
        mpns = {(m or "").strip().upper() for m, _ in claims}
        if len(mpns) > 1:
            diff.conflicts.append((key, claims))
    diff.bom_map = bom_map

    pp_mpn: Dict[str, str] = {}
    pp_layer: Dict[str, str] = {}
    for des, mpn, layer in pickplace:
        key = _norm(des)
        if not key:
            continue
        pp_mpn.setdefault(key, mpn or "")
        if layer:
            pp_layer.setdefault(key, layer)

    bom_keys = set()
    for row in bom_rows:
        row_missing: List[str] = []
        for d in row.designators:
            key = _norm(d)
            bom_keys.add(key)
            if key not in pp_mpn:
                row_missing.append(d)
        if row_missing:
            diff.missing.append((row, row_missing))
        if row.quantity and row.quantity != len(row.designators):
            diff.qty_notes.append((row, len(row.designators)))

    for key in sorted(set(pp_mpn) - bom_keys):
        diff.extra.append(key)

    for key in sorted(set(pp_mpn) & bom_keys):
        b_mpn, b_stt = bom_map.get(key, ("", 0))
        p_mpn = (pp_mpn.get(key) or "").strip()
        b_mpn_s = (b_mpn or "").strip()
        if not p_mpn and b_mpn_s:
            diff.mpn_fillable.append((key, b_mpn_s, b_stt))
        elif p_mpn and b_mpn_s and p_mpn.upper() != b_mpn_s.upper():
            diff.mpn_mismatch.append((key, p_mpn, b_mpn_s, b_stt))
    return diff


def bottom_layers() -> set:
    return {"bot", "bottom", "bottomlayer", "b", "bottom layer", "bot layer"}


def is_bottom_layer(layer: Optional[str]) -> bool:
    return (layer or "").strip().lower() in bottom_layers()


@dataclass
class BomRowSummary:
    stt: int = 0
    mpn: str = ""
    quantity: int = 0
    top: List[str] = field(default_factory=list)
    bottom: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    mixed_layers: List[str] = field(default_factory=list)


def summarize_bom_row(row: BomRow,
                      layers_of: Dict[str, set],
                      pickplace_keys: set) -> BomRowSummary:
    """Partition a BOM row's designators by PickPlace layer.

    layers_of: UPPER designator -> set of raw layer strings across all
    blocks (panelize duplicates may span Top and Bottom).
    pickplace_keys: UPPER designators present in PickPlace (any block).
    Returns top/bottom/missing/mixed lists preserving BOM order.
    """
    summary = BomRowSummary(stt=row.stt, mpn=row.mpn, quantity=row.quantity)
    seen: set = set()
    for d in row.designators:
        name = (d or "").strip()
        key = name.upper()
        if not key or key in seen:
            continue
        seen.add(key)
        if key not in pickplace_keys:
            summary.missing.append(name)
            continue
        layers = {str(v or "").strip() for v in (layers_of.get(key) or set())}
        layers.discard("")
        if not layers:
            summary.mixed_layers.append(name)
        elif all(is_bottom_layer(v) for v in layers):
            summary.bottom.append(name)
        elif any(is_bottom_layer(v) for v in layers):
            summary.mixed_layers.append(name)
        else:
            summary.top.append(name)
    return summary

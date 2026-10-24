"""Build the Gerber/Excellon sample manifest used as a regression oracle.

For every Gerber-ish file under a sample tree this records what each parser
managed to do with it.  The manifest is the reference the new spec parser
(``services/gerber/spec``) is validated against:

* ``gerbonara`` succeeds -> the spec parser must match its primitive counts
  and bounding box.
* ``gerbonara`` fails but the legacy parser succeeds -> the file uses a
  dialect gerbonara does not implement (aperture macro primitive 22 in
  practice); the spec parser must handle it and must not regress against the
  legacy numbers.

Usage::

    python scripts/gerber_manifest.py                 # D:\\Test
    python scripts/gerber_manifest.py --root "D:\\Test" --out tests/fixtures/gerber_manifest.json
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Extensions that may hold Gerber/Excellon payloads, plus extension-less CAM
# outputs (Altium/CAM350 style names such as "to", "tl", "drl").
_EXT_HINTS = (
    ".gbr", ".ger", ".gko", ".gto", ".gbo", ".gtp", ".gbp", ".gts", ".gbs",
    ".gts", ".gbs", ".gm1", ".gko", ".gbr", ".pho", ".art", ".drl", ".xln",
    ".exc", ".nc", ".txt", ".ncd", ".drd",
)

# Files that are obviously not artwork even though they carry a text
# extension (reports, BOM exports, job files...).
_SKIP_EXT = (".pdf", ".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg", ".zip",
             ".rar", ".7z", ".exe", ".dwg", ".dxf", ".step", ".stp", ".json")


def _is_candidate(path: str) -> bool:
    name = os.path.basename(path).lower()
    if name.endswith(_SKIP_EXT):
        return False
    ext = os.path.splitext(name)[1]
    if ext in _EXT_HINTS:
        return True
    # extension-less CAM outputs: keep short names without a dot
    return "." not in name and len(name) <= 12


def sniff_kind(path: str) -> str:
    """Classify a file by its first meaningful bytes."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return "unreadable"
    text = head.decode("utf-8", errors="replace")
    if text.startswith("M48"):
        return "excellon"
    upper = text.upper()
    for token in ("%FS", "%MO", "%ADD", "G04", "D01", "D03", "%AM"):
        if token in upper:
            return "gerber"
    if upper.lstrip().startswith(("M95", "M30", ";")):
        return "excellon"
    if "M48" in upper:
        return "excellon"
    return "unknown"


def _bbox_of(rd):
    try:
        minx, miny, maxx, maxy = rd.bbox()
    except Exception:  # noqa: BLE001
        return None
    return [round(v, 6) for v in (minx, miny, maxx, maxy)]


def probe_gerbonara(path: str) -> dict:
    out = {"ok": False, "error": None, "primitives": 0, "bbox": None, "ms": 0.0}
    try:
        import gerbonara
    except ImportError:
        out["error"] = "gerbonara not installed"
        return out
    t0 = time.perf_counter()
    try:
        gf = gerbonara.GerberFile.open(path)
        counts = {}
        for obj in gf.objects:
            for prim in obj.to_primitives("mm"):
                counts[type(prim).__name__] = counts.get(type(prim).__name__, 0) + 1
        out["ok"] = True
        out["primitives"] = sum(counts.values())
        out["kinds"] = dict(sorted(counts.items()))
        try:
            bb = gf.bounding_box()
            out["bbox"] = [round(float(v), 6) for v in (bb[0][0], bb[0][1], bb[1][0], bb[1][1])]
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    out["ms"] = (time.perf_counter() - t0) * 1000.0
    return out


def probe_legacy(path: str) -> dict:
    out = {"ok": False, "error": None, "primitives": 0, "bbox": None, "ms": 0.0}
    try:
        from services.gerber.gerber_render import parse_render
    except ImportError:
        out["error"] = "legacy parser unavailable"
        return out
    t0 = time.perf_counter()
    try:
        rd = parse_render(path)
        out["ok"] = True
        out["primitives"] = len(rd.lines) + len(rd.arcs) + len(rd.flashes)
        out["kinds"] = {
            "lines": len(rd.lines),
            "arcs": len(rd.arcs),
            "flashes": len(rd.flashes),
        }
        out["bbox"] = _bbox_of(rd)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    out["ms"] = (time.perf_counter() - t0) * 1000.0
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=r"D:\Test")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "fixtures", "gerber_manifest.json"))
    ap.add_argument("--max-mb", type=float, default=0.0)
    args = ap.parse_args()

    entries = []
    for dirpath, _dirnames, filenames in os.walk(args.root):
        for name in sorted(filenames):
            fp = os.path.join(dirpath, name)
            if not _is_candidate(fp):
                continue
            size = os.path.getsize(fp)
            if args.max_mb and size > args.max_mb * 1024 * 1024:
                continue
            kind = sniff_kind(fp)
            entry = {
                "path": os.path.relpath(fp, args.root).replace("\\", "/"),
                "bytes": size,
                "kind": kind,
            }
            if kind == "excellon":
                entry["note"] = "excellon payload"
                entries.append(entry)
                continue
            if kind != "gerber":
                entry["note"] = "not a gerber payload"
                entries.append(entry)
                continue
            entry["gerbonara"] = probe_gerbonara(fp)
            entry["legacy"] = probe_legacy(fp)
            entries.append(entry)

    entries.sort(key=lambda e: e["path"])
    payload = {
        "root": os.path.abspath(args.root),
        "count": len(entries),
        "entries": entries,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")

    gerber = [e for e in entries if e.get("kind") == "gerber"]
    gb_ok = [e for e in gerber if e.get("gerbonara", {}).get("ok")]
    lg_ok = [e for e in gerber if e.get("legacy", {}).get("ok")]
    print(f"wrote {args.out}")
    print(f"  files scanned          : {len(entries)}")
    print(f"  gerber payloads        : {len(gerber)}")
    print(f"  gerbonara can parse    : {len(gb_ok)}")
    print(f"  legacy parser can parse: {len(lg_ok)}")
    only_legacy = [e for e in gerber
                   if e.get("legacy", {}).get("ok") and not e.get("gerbonara", {}).get("ok")]
    print(f"  legacy-only (need spec parser): {len(only_legacy)}")
    for e in only_legacy[:12]:
        err = e.get("gerbonara", {}).get("error", "")
        print(f"    - {e['path']}  [{err[:70]}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

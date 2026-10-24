"""Read every Gerber and Excellon file of a folder with the new parser.

The script answers one question: does the spec parser read the real files?
A file that is read without an error and that produces artwork is a file
the viewer can show.  A file that is read without an error but that has no
artwork is reported apart, because an empty layer is a valid file.

    python scripts/gerber_corpus_check.py --root D:\\Test
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.gerber.spec.loader import detect_kind, load  # noqa: E402

#: The extensions of the files that may hold Gerber or Excellon data.
EXTENSIONS = {
    ".gbr", ".gtp", ".gto", ".gbo", ".gts", ".gbs", ".gko", ".gbp", ".gbl",
    ".gml", ".gms", ".gm1", ".g1", ".g2", ".pho", ".art", ".drl", ".exc",
    ".xln", ".nc", ".ngc", ".txt", ".drd", ".drdr",
}


def collect(root: str) -> list[str]:
    """Every candidate file of the folder, in a stable order."""
    found: list[str] = []
    for directory, _sub, names in os.walk(root):
        for name in names:
            if os.path.splitext(name)[1].lower() in EXTENSIONS:
                found.append(os.path.join(directory, name))
    found.sort()
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=r"D:\Test", help="folder to read")
    parser.add_argument("--quiet", action="store_true",
                        help="only print the summary")
    args = parser.parse_args()

    warnings.simplefilter("ignore")
    files = collect(args.root)
    kinds: dict[str, int] = {}
    read = 0
    artwork = 0
    empty: list[str] = []
    failed: list[tuple[str, str]] = []
    items = 0
    degraded = 0

    started = time.perf_counter()
    for path in files:
        try:
            kind = detect_kind(path)
        except Exception:
            kind = "unknown"
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "unknown":
            continue
        result = load(path)
        if result.error:
            failed.append((path, result.error))
            continue
        read += 1
        if result.degraded:
            degraded += 1
        count = len(result.image.items) if result.image is not None else 0
        if result.drill is not None:
            count = len(result.drill.holes) + len(result.drill.slots)
        items += count
        if count:
            artwork += 1
        else:
            empty.append(path)
    elapsed = time.perf_counter() - started

    print("folder               : %s" % args.root)
    print("candidate files      : %d" % len(files))
    for kind in sorted(kinds):
        print("  %-18s: %d" % (kind, kinds[kind]))
    print("read without an error: %d" % read)
    print("  with artwork       : %d" % artwork)
    print("  empty              : %d" % len(empty))
    print("  degraded           : %d" % degraded)
    print("failed               : %d" % len(failed))
    print("items                : %d" % items)
    print("elapsed              : %.1f s" % elapsed)

    if not args.quiet:
        for path in empty:
            print("  EMPTY %s" % path)
        for path, reason in failed:
            print("  FAIL  %s -> %s" % (path, reason))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

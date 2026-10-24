"""Write the golden summary of the spec parser.

The summary contains the number of items, the bounding box and a hash of
the geometry of every sampled file.  ``tests/test_gerber_spec_golden.py``
re-parses the same files and compares, so an optimisation that changes the
result in any way is caught.

Usage::

    python scripts/gerber_spec_golden.py            # write the fixture
    python scripts/gerber_spec_golden.py --check    # only report differences
"""

import argparse
import hashlib
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.gerber.spec import parse_file

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "gerber_spec_golden.json")

#: The files of the sample set that are used for the golden summary.
SAMPLE = [
    "data0/PCB ETRIGGER_CTRL_3.0-working gerber/ETRIGGER_CTRL_3.0.gto",
    "data0/PCB ETRIGGER_CTRL_3.0-working gerber/ETRIGGER_CTRL_3.0.gtp",
    "data0/PCB ETRIGGER_CTRL_3.0-working gerber/ETRIGGER_CTRL_3.0.gko",
    "data0/PCB ETRIGGER_CTRL_3.0-working gerber/ETRIGGER_CTRL_3.0.drl",
    "data0/NC Drill/GS.DSP-4.0_NC Drill Files_2026-02-27.TXT",
    "data09/2nd-PCB FFC.MAIN-4.0-working gerber/PCB FFC.MAIN-4.0.gtp",
    "data12/Stencil BFS MAIN TOP-BOT/working gerber/wf.gto",
    "data12/Stencil BFS MAIN TOP-BOT/working gerber/wf.gtl",
    "data12/Stencil BFS MAIN TOP-BOT/working gerber/wf.drl",
    "data21/PSU_PCB wf/tl",
    "data21/PSU_PCB wf/bl",
    "data21/PSU_PCB wf/ts",
    "data21/PSU_PCB wf/tp.gtp",
    "data21/PSU_PCB wf/rout.gko",
    "data21/PSU_PCB wf/drl",
    "data21/PSU_PCB wf/bs",
    "data21/PSU_PCB wf/2rd",
    "data23/Headset_Flexi-Rigid_PCB_A_170826-working gerber/"
    "PCB_LUC1_09_3000_Headset_Flexi-Rigid_PCB_A_170826.gbs",
    "data13/stencil GDT.PC + TRX91 (0.1mm)/TLSX GDT.PC V2.1-working gerber/"
    "GDT.PC V2.1.gbs",
    # A file with a polygon aperture and with macros whose name starts with
    # the letter of a standard template.
    "data17/data/Gerber+drill/MRFBC_Ver03.5_1W_Copper_Signal_Top.gbr",
    # A drill file that writes the slots as a move between M15 and M16.
    "data13/GDT.PC_V2.1 PCB Documents 04072025/NC Drill/GDT.PC.V2.1-SlotHoles.TXT",
]


def geometry_hash(image) -> str:
    """A hash over the geometry of the parsed file."""
    digest = hashlib.sha256()
    for item in image.items:
        digest.update(item.kind.encode()[:8].ljust(8, b"\0"))
        digest.update(struct.pack("<iiiiii", item.x, item.y, item.x2, item.y2,
                                  item.cx, item.cy))
        digest.update(b"\x01" if item.negative else b"\x00")
        for px, py in item.points:
            digest.update(struct.pack("<ii", px, py))
    return digest.hexdigest()


def summarise(path: str):
    image = parse_file(path)
    box = image.bbox_mm
    return {
        "items": len(image.items),
        "bbox": [round(v, 6) for v in box] if box else None,
        "hash": geometry_hash(image),
        "warnings": len(image.warnings),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=r"D:\Test")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    entries = {}
    missing = 0
    for relative in SAMPLE:
        path = os.path.join(args.root, relative.replace("/", os.sep))
        if not os.path.exists(path):
            missing += 1
            continue
        entries[relative] = summarise(path)
    if missing:
        print(f"{missing} sample file(s) are missing, they are skipped")

    if args.check:
        with open(FIXTURE, encoding="utf-8") as fh:
            golden = json.load(fh)["entries"]
        bad = 0
        for name, expected in golden.items():
            got = entries.get(name)
            if got != expected:
                bad += 1
                print(f"DIFFERS {name}\n  expected {expected}\n  got      {got}")
        print(f"{len(golden) - bad}/{len(golden)} files unchanged")
        return 1 if bad else 0

    payload = {"root": os.path.abspath(args.root), "entries": entries}
    os.makedirs(os.path.dirname(FIXTURE), exist_ok=True)
    with open(FIXTURE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {FIXTURE} with {len(entries)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

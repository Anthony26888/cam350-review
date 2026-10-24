"""The spec parser has to keep producing exactly the same geometry.

The golden summary in ``tests/fixtures/gerber_spec_golden.json`` holds the
number of items, the bounding box and a hash of the geometry of a sample of
real files.  Re-parsing them has to give the same result, so an optimisation
of the parser can never change what is drawn.

The sample files live outside the repository.  When they are not there the
test is skipped; the fixture is regenerated with
``python scripts/gerber_spec_golden.py``.
"""

import json
import os

import pytest

from services.gerber.spec import parse_file

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "gerber_spec_golden.json")


def _geometry_hash(image) -> str:
    import hashlib
    import struct

    digest = hashlib.sha256()
    for item in image.items:
        digest.update(item.kind.encode()[:8].ljust(8, b"\0"))
        digest.update(struct.pack("<iiiiii", item.x, item.y, item.x2, item.y2,
                                  item.cx, item.cy))
        digest.update(b"\x01" if item.negative else b"\x00")
        for px, py in item.points:
            digest.update(struct.pack("<ii", px, py))
    return digest.hexdigest()


def _load():
    if not os.path.exists(FIXTURE):
        return None
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def test_the_golden_summary_matches_the_parser():
    golden = _load()
    if golden is None:
        pytest.skip("golden summary not generated")
    root = golden["root"]
    if not os.path.isdir(root):
        pytest.skip("the sample tree is not available")
    checked = 0
    for relative, expected in golden["entries"].items():
        path = os.path.join(root, relative.replace("/", os.sep))
        if not os.path.exists(path):
            continue
        image = parse_file(path)
        box = image.bbox_mm
        assert len(image.items) == expected["items"], relative
        if expected["bbox"] is None:
            assert box is None, relative
        else:
            assert [round(v, 6) for v in box] == expected["bbox"], relative
        assert _geometry_hash(image) == expected["hash"], relative
        checked += 1
    if checked == 0:
        pytest.skip("none of the sample files is available")
    assert checked >= 5

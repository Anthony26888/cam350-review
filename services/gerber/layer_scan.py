"""Find the Gerber and NC drill files of a folder and name their layers.

A CAM job usually puts every layer of a board in one folder, with the
name of the layer in the name of the file and, when the X2 format is
used, in the attributes of the file.  This module looks at a folder, finds
the files that hold artwork and works out what each one is.

The layer is named the way the reference viewer names it: the value of the
``%TF.FileFunction`` attribute when the file has one, and a name built
from the role of the file when it has not.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

#: The role of a layer: what the file shows.
ROLE_PROFILE = "profile"
ROLE_COPPER = "copper"
ROLE_MASK = "mask"
ROLE_PASTE = "paste"
ROLE_SILK = "silk"
ROLE_DRILL = "drill"
ROLE_OTHER = "other"

#: The side of the board a layer belongs to.
SIDE_TOP = "top"
SIDE_BOTTOM = "bottom"
SIDE_NONE = "none"

#: The order the layers are drawn in.  The first one is at the bottom, the
#: drill holes are on top of everything.
ROLE_ORDER = (
    ROLE_PROFILE, ROLE_COPPER, ROLE_MASK, ROLE_PASTE, ROLE_SILK,
    ROLE_DRILL, ROLE_OTHER,
)

#: How many bytes of a file are read to find its attributes.  The
#: attributes of a file are written in its head.
HEADER_BYTES = 65536

#: The name of a layer when the file does not say what it is.
ROLE_NAMES = {
    ROLE_PROFILE: "Board Outline",
    ROLE_COPPER: "Copper",
    ROLE_MASK: "Solder Mask",
    ROLE_PASTE: "Paste",
    ROLE_SILK: "Silkscreen",
    ROLE_DRILL: "NC Drill",
    ROLE_OTHER: "Gerber",
}

#: The extensions that tell what a file is, when it has no attributes.
EXTENSION_ROLES: Dict[str, Tuple[str, str]] = {
    ".gko": (ROLE_PROFILE, SIDE_NONE),
    ".gm1": (ROLE_PROFILE, SIDE_NONE),
    ".gml": (ROLE_PROFILE, SIDE_NONE),
    ".gtp": (ROLE_PASTE, SIDE_TOP),
    ".gbp": (ROLE_PASTE, SIDE_BOTTOM),
    ".gmp": (ROLE_PASTE, SIDE_TOP),
    ".gto": (ROLE_SILK, SIDE_TOP),
    ".gtl": (ROLE_COPPER, SIDE_TOP),
    ".gts": (ROLE_MASK, SIDE_TOP),
    ".gms": (ROLE_MASK, SIDE_TOP),
    ".gbo": (ROLE_SILK, SIDE_BOTTOM),
    ".gbl": (ROLE_COPPER, SIDE_BOTTOM),
    ".gbs": (ROLE_MASK, SIDE_BOTTOM),
    ".gbm": (ROLE_MASK, SIDE_BOTTOM),
    ".gt1": (ROLE_COPPER, SIDE_TOP),
    ".g1": (ROLE_COPPER, SIDE_TOP),
    ".gb1": (ROLE_COPPER, SIDE_BOTTOM),
    ".g2": (ROLE_COPPER, SIDE_BOTTOM),
    ".gbr": (ROLE_COPPER, SIDE_NONE),
    ".gcu": (ROLE_COPPER, SIDE_NONE),
    ".ger": (ROLE_COPPER, SIDE_NONE),
    ".drl": (ROLE_DRILL, SIDE_NONE),
    ".xln": (ROLE_DRILL, SIDE_NONE),
    ".exc": (ROLE_DRILL, SIDE_NONE),
    ".nc": (ROLE_DRILL, SIDE_NONE),
    ".ngc": (ROLE_DRILL, SIDE_NONE),
    ".drd": (ROLE_DRILL, SIDE_NONE),
}

#: The extensions of the files that may hold artwork.
CANDIDATE_EXTENSIONS = set(EXTENSION_ROLES) | {".txt", ".ger"}

#: The names the reference tool gives to the layers of a job.  A CAM job
#: often names its files like that, and a file without a name that says
#: what it is would be of no use.
NAME_ROLES: Dict[str, Tuple[str, str]] = {
    "rout": (ROLE_PROFILE, SIDE_NONE),
    "profile": (ROLE_PROFILE, SIDE_NONE),
    "edge": (ROLE_PROFILE, SIDE_NONE),
    "gko": (ROLE_PROFILE, SIDE_NONE),
    "drl": (ROLE_DRILL, SIDE_NONE),
    "xln": (ROLE_DRILL, SIDE_NONE),
    "ncd": (ROLE_DRILL, SIDE_NONE),
    "to": (ROLE_SILK, SIDE_TOP),
    "gto": (ROLE_SILK, SIDE_TOP),
    "bo": (ROLE_SILK, SIDE_BOTTOM),
    "gbo": (ROLE_SILK, SIDE_BOTTOM),
    "tp": (ROLE_PASTE, SIDE_TOP),
    "gtp": (ROLE_PASTE, SIDE_TOP),
    "bp": (ROLE_PASTE, SIDE_BOTTOM),
    "gbp": (ROLE_PASTE, SIDE_BOTTOM),
    "ts": (ROLE_MASK, SIDE_TOP),
    "gts": (ROLE_MASK, SIDE_TOP),
    "bs": (ROLE_MASK, SIDE_BOTTOM),
    "gbs": (ROLE_MASK, SIDE_BOTTOM),
    "tu": (ROLE_COPPER, SIDE_TOP),
    "tl": (ROLE_COPPER, SIDE_TOP),
    "gtl": (ROLE_COPPER, SIDE_TOP),
    "g1": (ROLE_COPPER, SIDE_TOP),
    "bl": (ROLE_COPPER, SIDE_BOTTOM),
    "gb": (ROLE_COPPER, SIDE_BOTTOM),
    "gbl": (ROLE_COPPER, SIDE_BOTTOM),
    "g2": (ROLE_COPPER, SIDE_BOTTOM),
}

_X2_FILE_RE = re.compile(r"%TF\.([A-Za-z0-9_.]+),([^*]*)\*%", re.IGNORECASE)
_X2_FILE_RE_SPACE = re.compile(r"%TF\.([A-Za-z0-9_.]+)\*%", re.IGNORECASE)
_LOAD_POLARITY_RE = re.compile(r"%LP([CD])\*%", re.IGNORECASE)


@dataclass
class LayerInfo:
    """One layer of the picture."""

    #: Where the file is.
    path: str = ""
    #: The name of the layer, the way the reference viewer names it.
    name: str = ""
    #: The name of the file.
    file_name: str = ""
    #: What the layer shows: profile, copper, mask, paste, silk, drill.
    role: str = ROLE_OTHER
    #: The side of the board: top, bottom or none.
    side: str = SIDE_NONE
    #: The polarity of the file: positive, negative or none.
    polarity: str = "none"
    #: The value of the X2 file function attribute.
    file_function: str = ""
    #: True when the file holds drill holes.
    is_drill: bool = False

    def key(self) -> str:
        """The key the layer is remembered with."""
        return os.path.normcase(os.path.abspath(self.path)) if self.path else self.name

    def describe(self) -> str:
        """The text of the layer in a list."""
        return "%s  (%s)" % (self.name, self.file_name) if self.file_name else self.name


def read_x2_header(path: str) -> Dict[str, str]:
    """The file attributes of a Gerber file, from its head.

    Only the head of the file is read: the attributes of a file are
    written there, and reading the whole file of a big board just to know
    its name would be a waste of time.
    """
    attributes: Dict[str, str] = {}
    try:
        with open(path, "rb") as fh:
            head = fh.read(HEADER_BYTES)
    except OSError:
        return attributes
    text = head.decode("utf-8", errors="replace")
    for match in _X2_FILE_RE.finditer(text):
        attributes[match.group(1)] = match.group(2).strip()
    for match in _X2_FILE_RE_SPACE.finditer(text):
        attributes.setdefault(match.group(1), "")
    return attributes


def role_from_file_function(file_function: str) -> Tuple[str, str]:
    """The role and the side of a layer, from its file function.

    The value of the attribute looks like ``Copper,L1,Top,Signal``: the
    first part says what the layer shows, the second where it is.
    """
    if not file_function:
        return ROLE_OTHER, SIDE_NONE
    parts = [part.strip() for part in file_function.split(",")]
    what = parts[0].lower() if parts else ""
    side = SIDE_NONE
    for part in parts[1:]:
        low = part.lower()
        if low in ("top", "front"):
            side = SIDE_TOP
            break
        if low in ("bottom", "bot", "back"):
            side = SIDE_BOTTOM
            break
    if what in ("copper",):
        return ROLE_COPPER, side
    if what in ("soldermask", "mask", "solder mask"):
        return ROLE_MASK, side
    if what in ("legend", "silkscreen", "silk screen", "legend,top"):
        return ROLE_SILK, side
    if what in ("paste",):
        return ROLE_PASTE, side
    if what in ("profile",):
        return ROLE_PROFILE, SIDE_NONE
    if what in ("drill", "other"):
        # A drill file has no file function; the file type says so.
        return ROLE_DRILL, SIDE_NONE
    return ROLE_OTHER, side


def role_from_extension(path: str) -> Tuple[str, str]:
    """The role and the side of a layer, from the name of its file."""
    ext = os.path.splitext(path)[1].lower()
    return EXTENSION_ROLES.get(ext, (ROLE_OTHER, SIDE_NONE))


def role_from_name(path: str) -> Tuple[str, str]:
    """The role and the side of a layer, from the name of its file.

    A job often names its files ``to``, ``tl``, ``bl`` and so on; the
    meaning of those names is the one the reference tool uses.
    """
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    return NAME_ROLES.get(stem, (ROLE_OTHER, SIDE_NONE))


def layer_name(role: str, side: str, file_function: str) -> str:
    """The name of a layer, the way the reference viewer names it."""
    if file_function:
        return file_function
    base = ROLE_NAMES.get(role, ROLE_NAMES[ROLE_OTHER])
    if side == SIDE_TOP:
        return "Top " + base
    if side == SIDE_BOTTOM:
        return "Bottom " + base
    return base


def layer_from_file(path: str) -> Optional[LayerInfo]:
    """What one file is, or None when it holds no artwork.

    What the file holds is decided by its content, not by its name: a file
    that is called ``drl`` may hold a picture and a file without a name
    may hold drill holes.
    """
    from services.gerber.spec.loader import detect_kind

    if not os.path.isfile(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext and ext not in CANDIDATE_EXTENSIONS:
        return None
    try:
        kind = detect_kind(path)
    except OSError:
        return None
    if kind not in ("gerber", "excellon"):
        return None

    file_name = os.path.basename(path)
    if kind == "excellon":
        return LayerInfo(path=path, name=ROLE_NAMES[ROLE_DRILL],
                         file_name=file_name, role=ROLE_DRILL,
                         side=SIDE_NONE, polarity="none", is_drill=True)

    attributes = read_x2_header(path)
    file_function = attributes.get("FileFunction", "")
    role, side = role_from_file_function(file_function)
    if role == ROLE_OTHER:
        role, side = role_from_name(path)
    if role == ROLE_OTHER:
        role, side = role_from_extension(path)
    if role == ROLE_DRILL:
        # The file holds a picture, so it is not a drill file whatever
        # its name says.
        role, side = ROLE_OTHER, SIDE_NONE
    polarity = attributes.get("FilePolarity", "").strip().lower() or "none"
    return LayerInfo(path=path, name=layer_name(role, side, file_function),
                     file_name=file_name, role=role, side=side,
                     polarity=polarity, file_function=file_function)


def _sort_key(layer: LayerInfo) -> Tuple[int, str]:
    try:
        order = ROLE_ORDER.index(layer.role)
    except ValueError:
        order = len(ROLE_ORDER)
    return (order, layer.file_name.lower())


def scan_folder(folder: str) -> List[LayerInfo]:
    """Every file of a folder that holds artwork, as layers.

    The files of the folder itself are looked at; the folders below it
    are not.
    """
    layers: List[LayerInfo] = []
    if not folder or not os.path.isdir(folder):
        return layers
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return layers
    for name in names:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        layer = layer_from_file(path)
        if layer is not None:
            layers.append(layer)
    layers.sort(key=_sort_key)
    return layers

"""A clean-room Gerber / Excellon engine.

The modules in this package implement the Gerber (RS-274X / X2) and Excellon
formats from the published specifications, with the tolerances needed for the
dialects that appear in real CAM output.

Layout::

    units.py        internal units (10 nm) and the %FS coordinate formats
    rs274x.py       the X2 statement identifiers
    rs274d.py       the parser itself
    am_primitive.py aperture macro primitives
    dcode.py        aperture definitions
    draw_item.py    the drawable primitive model
    file_image.py   the parsed file
    excellon.py     the Excellon / NC drill parser
    loader.py       file type detection and the public load entry points
"""

from .am_primitive import ApertureMacro, MacroShape
from .dcode import DCode
from .draw_item import DrawItem
from .file_image import FileImage, LayerParams
from .rs274d import GerberParser, GerberParseError, parse_file
from .units import IU_PER_MM, MM_PER_INCH, CoordinateFormat, mm_to_iu, iu_to_mm

__all__ = [
    "ApertureMacro",
    "CoordinateFormat",
    "DCode",
    "DrawItem",
    "FileImage",
    "GerberParseError",
    "GerberParser",
    "IU_PER_MM",
    "LayerParams",
    "MM_PER_INCH",
    "MacroShape",
    "iu_to_mm",
    "mm_to_iu",
    "parse_file",
]

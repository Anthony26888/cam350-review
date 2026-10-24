"""RS-274X / X2 extended command handling.

The Gerber X2 format adds a family of ``%XX...%`` statements next to the
classic ``%FS``/``%MO``/``%AD``/``%AM`` ones.  This module holds the
identifiers and a small splitter so the parser itself stays readable.
"""

from __future__ import annotations

# Statement identifiers.
FS = "FS"  # format specification
MO = "MO"  # mode of units
AD = "AD"  # aperture definition
AM = "AM"  # aperture macro
LP = "LP"  # load polarity
SR = "SR"  # step and repeat
TF = "TF"  # file attribute
TA = "TA"  # aperture attribute
TO = "TO"  # net attribute
TD = "TD"  # delete attribute
LN = "LN"  # load name (deprecated)
IP = "IP"  # image polarity
MI = "MI"  # mirror image
OF = "OF"  # offset
SF = "SF"  # scale factor
AS = "AS"  # axis select
KO = "KO"  # knockout
RO = "RO"  # rotate
IN = "IN"  # image name
IO = "IO"  # image offset
IR = "IR"  # image rotation
IJ = "IJ"  # image justification

#: Every identifier the parser knows about.
KNOWN = frozenset({
    FS, MO, AD, AM, LP, SR, TF, TA, TO, TD, LN, IP, MI, OF, SF, AS, KO, RO,
    IN, IO, IR, IJ,
})


def split_x2_statements(body: str) -> list[str]:
    """Split the content of a ``%...%`` block into its statements.

    The content of an extended command block is a sequence of statements
    separated by ``*``::

        %FSLAX36Y36*%
        %AMD646*<macro body>*%

    For an aperture macro the first statement carries the macro name and every
    following statement is one line of the macro body.
    """
    parts = body.split("*")
    statements = [p.strip() for p in parts]
    while statements and not statements[-1]:
        statements.pop()
    return statements


def statement_id(statement: str) -> str:
    """Two letter identifier of an X2 statement."""
    return statement[:2].upper()

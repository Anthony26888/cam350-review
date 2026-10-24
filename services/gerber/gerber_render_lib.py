"""Loading a Gerber file for the viewer.

The viewer draws with the ``RenderData`` model of
:mod:`services.gerber.gerber_render`.  This module turns a file into that
model.

Two parsers can do the job:

``spec``
    The clean-room engine in :mod:`services.gerber.spec`.  It follows the
    Gerber specification, implements the aperture macro dialects that real
    CAM output uses, and is the one that is used by default.
``legacy``
    The parser this application used before the spec engine existed.  It is
    the last resort.

A fallback is never silent: the result carries the name of the parser that
was used and the reasons why the preferred one was skipped, so the user
interface can tell the operator that the artwork was read by a reduced
parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.gerber.gerber_render import RenderData

PARSER_SPEC = "spec"
PARSER_LEGACY = "legacy"
PARSER_NONE = "none"


@dataclass
class LoadInfo:
    """How a file was read."""

    path: str = ""
    parser: str = PARSER_NONE
    degraded: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def summary(self) -> str:
        """A short human readable description of the load result."""
        if self.error:
            return f"{self.path}: {self.error}"
        if self.degraded:
            detail = self.warnings[0] if self.warnings else "reduced parser used"
            return f"{self.path}: read with the {self.parser} parser ({detail})"
        return ""


def load_layer(path: str) -> tuple[RenderData, LoadInfo]:
    """Load a Gerber file and report how it was read."""
    info = LoadInfo(path=path)

    from .spec.loader import load

    result = load(path)
    if result.ok and result.image is not None:
        from .spec.adapter import to_render_data

        info.parser = PARSER_SPEC
        info.warnings = list(result.warnings)
        info.degraded = result.degraded
        return to_render_data(result.image), info

    info.error = result.error
    info.warnings = list(result.warnings)

    # Last resort: the parser this application used before the spec engine
    # existed.  It reads fewer dialects but it never gives up.
    try:
        from .gerber_render import parse_render

        data = parse_render(path)
    except Exception as exc:  # noqa: BLE001 - the file is simply unreadable
        info.warnings.append(f"legacy parser failed: {exc}")
        return RenderData(), info
    info.parser = PARSER_LEGACY
    info.degraded = True
    info.warnings.append("read with the reduced legacy parser")
    return data, info


def load_drill(path: str) -> tuple[RenderData, LoadInfo]:
    """Load a drill file and report how it was read.

    A drill file comes in two flavours: a real Excellon file, and a Gerber
    file with circle apertures.  Both are accepted.
    """
    info = LoadInfo(path=path)

    from .spec.loader import load

    result = load(path)
    if result.ok and result.drill is not None:
        from .spec.adapter import drill_to_render_data

        info.parser = PARSER_SPEC
        info.warnings = list(result.warnings)
        info.degraded = result.degraded
        return drill_to_render_data(result.drill), info
    if result.ok and result.image is not None:
        # A drill file written as Gerber: the holes are flashed circles.
        from .spec.adapter import to_render_data

        info.parser = PARSER_SPEC
        info.warnings = list(result.warnings)
        info.degraded = result.degraded
        return to_render_data(result.image), info

    info.error = result.error
    info.warnings = list(result.warnings)
    return RenderData(), info


def parse_layer(path: str) -> RenderData:
    """Load a Gerber file into the render model."""
    data, _info = load_layer(path)
    return data

"""File type detection and the public load entry points.

The loader is the only place that decides which parser handles a file.  It
never falls back silently: when the preferred parser cannot read a file the
result is marked ``degraded`` and carries the reason, so the user interface
can tell the operator that the artwork was read by a reduced parser.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .excellon import ExcellonImage, ExcellonParser
from .file_image import FileImage
from .rs274d import GerberParser

KIND_GERBER = "gerber"
KIND_EXCELLON = "excellon"
KIND_UNKNOWN = "unknown"

#: Parser identifiers reported in the load result.
PARSER_SPEC = "spec"
PARSER_EXCELLON = "spec-excellon"
PARSER_LEGACY = "legacy"
PARSER_NONE = "none"


@dataclass
class LoadResult:
    """The outcome of loading one artwork file."""

    path: str
    kind: str = KIND_UNKNOWN
    parser: str = PARSER_NONE
    image: FileImage | None = None
    drill: ExcellonImage | None = None
    degraded: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and (self.image is not None or self.drill is not None)

    @property
    def item_count(self) -> int:
        if self.image is not None:
            return len(self.image.items)
        if self.drill is not None:
            return len(self.drill.holes) + len(self.drill.slots)
        return 0

    @property
    def bbox_mm(self):
        if self.image is not None:
            return self.image.bbox_mm
        if self.drill is not None:
            return self.drill.bbox_mm
        return None


def detect_kind(path: str) -> str:
    """Classify a file by its content: Gerber, Excellon or unknown."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8192)
    except OSError:
        return KIND_UNKNOWN
    text = head.decode("utf-8", errors="replace")
    stripped = text.lstrip(" \t\r\n")
    if stripped.startswith("M48"):
        return KIND_EXCELLON
    upper = text.upper()
    for token in ("%FS", "%MO", "%ADD", "G04", "D01", "D03", "%AM", "G54D", "G75", "G74"):
        if token in upper:
            return KIND_GERBER
    if "M48" in upper or upper.lstrip().startswith(("M95", "M30")):
        return KIND_EXCELLON
    return KIND_UNKNOWN


def load(path: str) -> LoadResult:
    """Load one artwork file with the spec engine."""
    result = LoadResult(path=path)
    kind = detect_kind(path)
    result.kind = kind

    if kind == KIND_EXCELLON:
        result.parser = PARSER_EXCELLON
        try:
            image = ExcellonParser.from_path(path).parse()
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            result.error = f"{type(exc).__name__}: {exc}"
            return result
        result.drill = image
        result.warnings.extend(image.warnings)
        result.degraded = image.degraded
        return result

    if kind == KIND_GERBER:
        result.parser = PARSER_SPEC
        try:
            image = GerberParser.from_path(path).parse()
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            result.error = f"{type(exc).__name__}: {exc}"
            return result
        result.image = image
        result.warnings.extend(image.warnings)
        result.degraded = image.degraded
        return result

    result.error = "unrecognised file format"
    return result


def load_gerber(path: str) -> FileImage | None:
    """Convenience wrapper returning only the Gerber image."""
    result = load(path)
    return result.image

# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Text region model for PyRaya.

A *text region* is a span of the document tagged with a semantic
:class:`RegionType` and rendered with a subtle, type-specific background
color. Region state is stored as character formats on the document itself,
so spans survive edits and undo/redo without manual bookkeeping.
"""

from dataclasses import dataclass
from enum import Enum

from PySide6.QtGui import QColor

__all__ = ["REGION_COLORS", "RegionType", "TextRegion"]


# ******************************************************************************
class RegionType(Enum):
    """Semantic region types for tagged text spans.

    Members:
        LATIN: Latin-script text that is not Roman Urdu (e.g. English); no
            Urdu-specific processing.
        ROMAN_URDU: Roman-script Urdu — Urdu semantics written in the Latin
            script. Future per-type processing (spell-check, Roman Urdu to
            Nastaliq) will be hooked to these regions.
    """

    LATIN = "latin"
    ROMAN_URDU = "roman_urdu"


# ******************************************************************************
@dataclass(frozen=True, slots=True)
class TextRegion:
    """A half-open character range ``[start, end)`` tagged with a region kind.

    Args:
        start: The first character offset of the region.
        end: One past the last character offset of the region.
        kind: The semantic region type of the span.
    """

    start: int
    end: int
    kind: RegionType


# ******************************************************************************
REGION_COLORS: dict[RegionType, QColor] = {
    RegionType.LATIN: QColor(0x60, 0xA5, 0xFA, 30),
    RegionType.ROMAN_URDU: QColor(0xF5, 0x9E, 0x0B, 30),
}


# ******************************************************************************

# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Text region model for PyRaya.

A region kind is a semantic tag stored as a custom integer property on the
document's **character formats** — nothing else stores region data, so spans
survive edits and undo/redo without manual bookkeeping.

Resolution is two steps: a character whose format carries the
:data:`RegionKindProperty` resolves to that stored kind (a stored tag always
wins, even when it equals the seed — tags record intent), and untagged
characters resolve to the widget's :data:`SeedRegionKind` copy. Kinds are a
closed enum; the palette is view-only: it colours the kinds that have a tint
and never feeds back into identity.
"""

from dataclasses import dataclass
from enum import IntEnum

from PySide6.QtGui import QColor, QTextCharFormat, QTextFormat

from .theme import LightStop

__all__ = [
    "RegionColors",
    "RegionKindProperty",
    "RegionSubstitutions",
    "RegionType",
    "SeedRegionKind",
    "TextRegion",
    "resolveRegionKind",
    "substituteChar",
    "substituteText",
]


# ******************************************************************************
class RegionType(IntEnum):
    """Semantic region kinds for tagged text spans.

    The enum is closed — these two members never grow — and its values are
    one-based because int ``0`` is the **unset sentinel**
    :meth:`QTextFormat.intProperty` reports when the property is missing, so
    a stored kind can never be ``0``.

    Members:
        Native: Text the user explicitly took out of the Roman-Urdu
            world (e.g. ordinary Latin words). Native has no behaviour and
            no colour: it only exempts its stretch from Roman-Urdu
            processing (the roman-input gate types through it and the
            spell-check underline skips it).
        RomanUrdu: Roman-script Urdu — Urdu semantics written in the Latin
            script, the seed kind every widget starts with. It is the only
            kind that arms processing: the roman-input overlay and the
            spell-check underline apply to RomanUrdu words.
    """

    Native = 1
    RomanUrdu = 2


# ******************************************************************************
#: The character-format property a region kind is stored under.
#:
#: The first custom property slot past Qt's own ``UserProperty`` range, so
#: the property can never collide with a Qt-defined format key.
RegionKindProperty: int = int(QTextFormat.Property.UserProperty) + 1


# ******************************************************************************
#: The region kind untagged text resolves to.
#:
#: This module-level value is the **initial seed**: every ``PyRaya`` widget
#: copies it at construction and keeps its copy read-only afterwards —
#: there is no setter and no constructor parameter.
SeedRegionKind: RegionType = RegionType.RomanUrdu


# ******************************************************************************
@dataclass(frozen=True, slots=True)
class TextRegion:
    """A half-open character range ``[start, end)`` of one resolved kind.

    Args:
        start: The first character offset of the region.
        end: One past the last character offset of the region.
        kind: The resolved region kind of the span.
    """

    start: int
    end: int
    kind: RegionType


# ******************************************************************************
#: View tint colors for the colourable region kinds.
#:
#: This module-level mapping is the **default palette**: every ``PyRaya``
#: widget copies it at construction and each widget owns its own mapping,
#: so one widget's ``PyRaya.setRegionColor`` never touches another's. The
#: palette is view-only — colours never identify kinds — and contains only
#: the kinds that carry a tint; :attr:`RegionType.Native` is colourless and
#: stays out of the map. The tint is the light stop's value, from
#: :mod:`pyraya.theme`: a widget under a dark palette starts from the
#: dark stop's tint instead, and a palette change repoints it unless
#: :meth:`PyRaya.setRegionColor` has pinned it.
RegionColors: dict[RegionType, QColor] = {
    RegionType.RomanUrdu: QColor(LightStop.regionTint),
}


# ******************************************************************************
def resolveRegionKind(charFormat: QTextCharFormat, seed: RegionType) -> RegionType:
    """Resolve a character format's region kind in two steps.

    A stored tag wins — even when it equals ``seed`` — because tags record
    intent; untagged characters take ``seed``. The unset sentinel ``0``,
    which :meth:`QTextFormat.intProperty` reports for a missing property,
    and any value outside the closed enum fall back to ``seed``.

    Args:
        charFormat: The document's character format to read.
        seed: The kind untagged text resolves to.

    Returns:
        The stored kind, or ``seed`` when nothing valid is stored.
    """
    stored = charFormat.intProperty(RegionKindProperty)
    try:
        return RegionType(stored)
    except ValueError:
        return seed


# ******************************************************************************
#: The fixed per-region-kind 1:1 character substitution table.
#:
#: A region kind's entry maps typed Latin characters to their Urdu /
#: Arabic-script equivalents — the four punctuation marks (full stop, comma,
#: question mark, semicolon) and the ten Eastern Arabic-Indic digits — so a
#: character typed in that region's span lands in the document in its Urdu
#: form. :attr:`RegionType.Native` is empty: its characters pass through
#: untouched. The table is fixed (no host API) — part of the region model,
#: not a per-widget setting. The colon is deliberately absent: Urdu has no
#: dedicated colon codepoint and conventionally keeps the Latin ``:``.
RegionSubstitutions: dict[RegionType, dict[str, str]] = {
    RegionType.RomanUrdu: {
        ".": "\u06d4",  # ۔ Arabic full stop
        ",": "\u060c",  # ، Arabic comma
        "?": "\u061f",  # ؟ Arabic question mark
        ";": "\u061b",  # ؛ Arabic semicolon
        "0": "\u06f0",  # ۰
        "1": "\u06f1",  # ۱
        "2": "\u06f2",  # ۲
        "3": "\u06f3",  # ۳
        "4": "\u06f4",  # ۴
        "5": "\u06f5",  # ۵
        "6": "\u06f6",  # ۶
        "7": "\u06f7",  # ۷
        "8": "\u06f8",  # ۸
        "9": "\u06f9",  # ۹
    },
    RegionType.Native: {},
}


# ******************************************************************************
def substituteChar(char: str, kind: RegionType) -> str | None:
    """The ``kind``'s substitution for ``char``, or ``None`` when unmapped.

    Args:
        char: The single character to substitute.
        kind: The region kind whose :data:`RegionSubstitutions` entry is
            consulted.

    Returns:
        The substituted character when ``char`` is in ``kind``'s table, else
        ``None`` — the character passes through unchanged.
    """
    table = RegionSubstitutions.get(kind)
    return table.get(char) if table is not None else None


# ******************************************************************************
def substituteText(text: str, kind: RegionType) -> str:
    """Apply ``kind``'s substitution to every character of ``text``.

    Each character is looked up in ``kind``'s :data:`RegionSubstitutions`
    entry; a mapped character is replaced by its substitution, an unmapped
    character passes through unchanged.

    Args:
        text: The text to substitute.
        kind: The region kind whose table is applied.

    Returns:
        ``text`` with every mapped character replaced by its substitution.
    """
    return "".join(substituteChar(char, kind) or char for char in text)

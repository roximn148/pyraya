# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""The palette-derived theme token set.

Every colour PyRaya paints — the highlighter's ink rules, the spell-check
underline, the region tint, and the roman-input overlay's tier tints and
panel — lives in this module: one :class:`ThemeTokens` bundle per stop
(:data:`LightStop` and :data:`DarkStop`), no hard-coded styling in the
components. :func:`resolveTheme` picks the stop from the palette's ``Base``
role's lightness and re-derives the panel background from that role, so
the opaque suggestion panel matches the document it floats over under any
palette. The light stop is the package's historic palette: a light theme
renders exactly as before.
"""

from dataclasses import dataclass, replace

from PySide6.QtGui import QColor, QPalette

# ******************************************************************************
#: The number of edit-distance tiers the suggestion tiers distinguish:
#: exact (0), edit distance 1, and edit distance 2.
TierCount: int = 3


# ******************************************************************************
@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """The full set of colours one stop paints.

    Args:
        ink: The default Arabic-script ink (the highlighter's first rule).
        diacritics: The diacritical marks rule's colour (italic).
        arabicDigits: The Arabic-Indic digits rule's colour.
        latin: The Latin (ASCII letters) rule's colour.
        asciiDigits: The ASCII digits rule's colour.
        punctuation: The punctuation rule's colour.
        whitespace: The whitespace rule's colour (the visible-space dot).
        spellUnderline: The spell-check underline colour.
        regionTint: The RomanUrdu region tint (the Native kind is
            colourless).
        tiers: The three edit-distance tier tints, exact first.
        selectedAlpha: The selected suggestion row's highlight alpha.
        accentBorder: The selected suggestion row's accent border.
        undefinedWord: The undefined-word (Learn) row's dashed underline.
        listBackground: The suggestion panel's opaque background.
        listBorder: The suggestion panel's border.
        listText: The suggestion rows' text colour.
    """

    ink: QColor
    diacritics: QColor
    arabicDigits: QColor
    latin: QColor
    asciiDigits: QColor
    punctuation: QColor
    whitespace: QColor
    spellUnderline: QColor
    regionTint: QColor
    tiers: tuple[QColor, QColor, QColor]
    selectedAlpha: int
    accentBorder: QColor
    undefinedWord: QColor
    listBackground: QColor
    listBorder: QColor
    listText: QColor


# ******************************************************************************
#: The light stop: the package's historic palette.
#:
#: Every colour the highlighter rules, the spell-check underline, the
#: region tint, and the roman-input overlay have always painted, so a light
#: theme renders exactly as before.
LightStop: ThemeTokens = ThemeTokens(
    ink=QColor("#1F2937"),
    diacritics=QColor("#BE185D"),
    arabicDigits=QColor("#B45309"),
    latin=QColor("#1D4ED8"),
    asciiDigits=QColor("#6D28D9"),
    punctuation=QColor("#6B7280"),
    whitespace=QColor("#E0E3FF"),
    spellUnderline=QColor("#B22222"),
    regionTint=QColor(0x3B, 0x82, 0xF6, 30),
    tiers=(
        QColor(0x4F, 0x9D, 0x4F, 30),
        QColor(0xE8, 0x8A, 0x1A, 30),
        QColor(0xC4, 0x3B, 0x3B, 30),
    ),
    selectedAlpha=90,
    accentBorder=QColor(0x1D, 0x4E, 0x89),
    undefinedWord=QColor(0x8A, 0x8F, 0x98, 30),
    listBackground=QColor(0xFF, 0xFF, 0xFF),
    listBorder=QColor(0xD0, 0xD5, 0xDD),
    listText=QColor(0x00, 0x00, 0x00),
)


# ******************************************************************************
#: The dark stop: the dark-theme values for every token.
#:
#: A reasonable first guess from the light stop's values, tuned for a
#: standard Fusion dark palette; one table edit fine-tunes them.
DarkStop: ThemeTokens = ThemeTokens(
    ink=QColor("#E5E7EB"),
    diacritics=QColor("#F472B6"),
    arabicDigits=QColor("#FBBF24"),
    latin=QColor("#60A5FA"),
    asciiDigits=QColor("#A78BFA"),
    punctuation=QColor("#9CA3AF"),
    whitespace=QColor("#3A4159"),
    spellUnderline=QColor("#F87171"),
    regionTint=QColor(0x60, 0xA5, 0xFA, 30),
    tiers=(
        QColor(0x4A, 0xDE, 0x80, 30),
        QColor(0xFB, 0x92, 0x3C, 30),
        QColor(0xF8, 0x71, 0x71, 30),
    ),
    selectedAlpha=90,
    accentBorder=QColor(0x30, 0x8C, 0xC6),
    undefinedWord=QColor(0xB0, 0xB4, 0xBC, 30),
    listBackground=QColor(0x23, 0x23, 0x23),
    listBorder=QColor(0x3A, 0x3F, 0x4B),
    listText=QColor(0xDF, 0xDF, 0xDF),
)


# ******************************************************************************
#: The spell-check underline colour, a copy of the light stop's value.
#:
#: Kept at this import path for the spell-check pass and its tests; the
#: widget module re-exports it. A copy (not the stop's own ``QColor``), so
#: mutating this constant in place cannot reach the stop's value.
SpellCheckUnderlineColor: QColor = QColor(LightStop.spellUnderline)


# ******************************************************************************
def resolveTheme(palette: QPalette) -> ThemeTokens:
    """The theme tokens for a palette.

    The stop is picked by the ``Base`` role's lightness: below 0.5 the
    dark stop, at exactly 0.5 (and above) the light stop. Only the panel
    background is re-derived — from the palette's own ``Base``, so the
    opaque panel matches the document it floats over under any palette;
    every other token comes from the chosen stop unchanged.

    Args:
        palette: The palette to resolve.

    Returns:
        The :class:`ThemeTokens` for the palette's stop, with the panel
        background re-derived from its ``Base``.
    """
    base = palette.color(QPalette.ColorRole.Base)
    stop = DarkStop if base.lightnessF() < 0.5 else LightStop
    return replace(stop, listBackground=QColor(base))

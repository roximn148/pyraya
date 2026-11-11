# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the palette-derived theme token set.

The theme module owns every colour the package paints: the highlighter's
ink rules, the spell-check underline, the region tint, and the roman-input
overlay's tier tints and panel. ``resolveTheme`` picks the light or dark
stop from the palette's ``Base`` role and re-derives the panel background
from that role. Runs headless via the offscreen Qt platform.
"""

import os
from collections.abc import Generator
from dataclasses import replace

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from pyraya.theme import (
    DarkStop,
    LightStop,
    SpellCheckUnderlineColor,
    TierCount,
    resolveTheme,
)


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
def testLightStopHoldsTheHistoricPalette(app: QApplication) -> None:
    """The light stop reproduces every colour the package has always painted.

    The light stop is the package's historic palette — every highlighter
    rule colour, the spell-check underline, the region tint, and the
    overlay's tints and panel — so a light theme renders exactly as before.
    """
    assert LightStop.ink == QColor("#1F2937")
    assert LightStop.diacritics == QColor("#BE185D")
    assert LightStop.arabicDigits == QColor("#B45309")
    assert LightStop.latin == QColor("#1D4ED8")
    assert LightStop.asciiDigits == QColor("#6D28D9")
    assert LightStop.punctuation == QColor("#6B7280")
    assert LightStop.whitespace == QColor("#E0E3FF")
    assert LightStop.spellUnderline == QColor("#B22222")
    assert LightStop.regionTint == QColor(0x3B, 0x82, 0xF6, 30)
    assert LightStop.tiers == (
        QColor(0x4F, 0x9D, 0x4F, 30),
        QColor(0xE8, 0x8A, 0x1A, 30),
        QColor(0xC4, 0x3B, 0x3B, 30),
    )
    assert LightStop.selectedAlpha == 90
    assert LightStop.accentBorder == QColor(0x1D, 0x4E, 0x89)
    assert LightStop.undefinedWord == QColor(0x8A, 0x8F, 0x98, 30)
    assert LightStop.listBackground == QColor(0xFF, 0xFF, 0xFF)
    assert LightStop.listBorder == QColor(0xD0, 0xD5, 0xDD)
    assert LightStop.listText == QColor(0x00, 0x00, 0x00)


# ******************************************************************************
def testDarkStopHoldsTheDarkPalette(app: QApplication) -> None:
    """The dark stop carries the dark-theme values for every token."""
    assert DarkStop.ink == QColor("#E5E7EB")
    assert DarkStop.diacritics == QColor("#F472B6")
    assert DarkStop.arabicDigits == QColor("#FBBF24")
    assert DarkStop.latin == QColor("#60A5FA")
    assert DarkStop.asciiDigits == QColor("#A78BFA")
    assert DarkStop.punctuation == QColor("#9CA3AF")
    assert DarkStop.whitespace == QColor("#3A4159")
    assert DarkStop.spellUnderline == QColor("#F87171")
    assert DarkStop.regionTint == QColor(0x60, 0xA5, 0xFA, 30)
    assert DarkStop.tiers == (
        QColor(0x4A, 0xDE, 0x80, 30),
        QColor(0xFB, 0x92, 0x3C, 30),
        QColor(0xF8, 0x71, 0x71, 30),
    )
    assert DarkStop.selectedAlpha == 90
    assert DarkStop.accentBorder == QColor(0x30, 0x8C, 0xC6)
    assert DarkStop.undefinedWord == QColor(0xB0, 0xB4, 0xBC, 30)
    assert DarkStop.listBackground == QColor(0x23, 0x23, 0x23)
    assert DarkStop.listBorder == QColor(0x3A, 0x3F, 0x4B)
    assert DarkStop.listText == QColor(0xDF, 0xDF, 0xDF)


# ******************************************************************************
def testTierCountCoversEveryTier(app: QApplication) -> None:
    """TierCount covers every tier both stops define."""
    assert TierCount == 3
    assert TierCount == len(LightStop.tiers) == len(DarkStop.tiers)


# ******************************************************************************
def testSpellCheckUnderlineColorIsTheLightValue(app: QApplication) -> None:
    """The exported constant keeps the light underline colour."""
    assert SpellCheckUnderlineColor == LightStop.spellUnderline
    assert SpellCheckUnderlineColor == QColor("#B22222")


# ******************************************************************************
def testResolveThemeFollowsTheBase(app: QApplication) -> None:
    """resolveTheme re-derives only the panel background from the Base.

    Every other token comes from the chosen stop; the panel background
    follows the palette's own Base, so the opaque panel matches the
    document it floats over under any palette.
    """
    light = QPalette()
    light.setColor(QPalette.ColorRole.Base, QColor(0xFA, 0xFA, 0xFA))
    tokens = resolveTheme(light)
    assert tokens == replace(LightStop, listBackground=QColor(0xFA, 0xFA, 0xFA))

    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Base, QColor(0x1A, 0x1A, 0x1A))
    tokens = resolveTheme(dark)
    assert tokens == replace(DarkStop, listBackground=QColor(0x1A, 0x1A, 0x1A))


# ******************************************************************************
def testStopChoiceTurnsOnBaseLightness(app: QApplication) -> None:
    """The stop is chosen by the Base role's lightness, at 0.5 the light stop.

    A mid-grey Base at exactly 0.5 lightness stays light; one step darker
    crosses into the dark stop.
    """
    atThreshold = QPalette()
    atThreshold.setColor(QPalette.ColorRole.Base, QColor(0x80, 0x80, 0x80))
    assert resolveTheme(atThreshold) == replace(LightStop, listBackground=QColor(0x80, 0x80, 0x80))

    below = QPalette()
    below.setColor(QPalette.ColorRole.Base, QColor(0x7F, 0x7F, 0x7F))
    assert resolveTheme(below) == replace(DarkStop, listBackground=QColor(0x7F, 0x7F, 0x7F))

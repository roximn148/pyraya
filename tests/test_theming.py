# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for palette-driven theming of the document and the overlay.

The widget and its highlighter resolve their colours from the effective
``QPalette``: a ``setPalette`` (or an application palette swap) repoints the
highlighter's tokens, the default rules' foregrounds, and the region tint —
all view-only, edit-free. A host-installed rule survives a theme change; a
``setRegionColor`` pin outlives it. Runs headless via the offscreen Qt
platform.
"""

import os
from collections.abc import Generator
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication, QRegularExpression
from PySide6.QtGui import QBrush, QColor, QPalette, QTextCharFormat, QTextDocument
from PySide6.QtWidgets import QApplication

from pyraya import PyRaya, PyRayaHighlighter, RegionType
from pyraya.theme import DarkStop, LightStop, resolveTheme


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
def _darkPalette() -> QPalette:
    """The standard Fusion dark palette."""
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Window, QColor(0x31, 0x31, 0x31))
    dark.setColor(QPalette.ColorRole.WindowText, QColor(0xDF, 0xDF, 0xDF))
    dark.setColor(QPalette.ColorRole.Base, QColor(0x23, 0x23, 0x23))
    dark.setColor(QPalette.ColorRole.AlternateBase, QColor(0x2C, 0x2C, 0x2C))
    dark.setColor(QPalette.ColorRole.Text, QColor(0xDF, 0xDF, 0xDF))
    dark.setColor(QPalette.ColorRole.Button, QColor(0x31, 0x31, 0x31))
    dark.setColor(QPalette.ColorRole.ButtonText, QColor(0xDF, 0xDF, 0xDF))
    dark.setColor(QPalette.ColorRole.Highlight, QColor(0x29, 0x7D, 0xC6))
    dark.setColor(QPalette.ColorRole.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
    return dark


# ******************************************************************************
def _layoutForegrounds(widget: PyRaya) -> list[tuple[int, int, QColor | None]]:
    """Per-character layout foregrounds as ``(start, end, fg)`` ranges.

    Read from the per-block text layouts' format ranges — the authoritative
    observation point for layout-only formats — with each attribute cast to
    its documented runtime type and copied to a plain value immediately.
    """
    ranges: list[tuple[int, int, QColor | None]] = []
    block = widget.document().begin()
    while block.isValid():
        base = block.position()
        for r in block.layout().formats():
            rformat = cast(QTextCharFormat, r.format)
            fg = (
                rformat.foreground().color()
                if rformat.hasProperty(QTextCharFormat.Property.ForegroundBrush)
                else None
            )
            ranges.append(
                (
                    base + cast(int, r.start),
                    base + cast(int, r.start) + cast(int, r.length),
                    fg,
                )
            )
        block = block.next()
    return ranges


# ******************************************************************************
def _underlinedColor(widget: PyRaya) -> list[tuple[int, int, QColor]]:
    """Underlined runs of the document layout as ``(start, end, color)``.

    Read from the per-block text layouts' format ranges (the
    authoritative observation point for layout-only formats), with the
    colour copied to a plain ``QColor`` immediately: a ``FormatRange``'s
    format borrows its C++ object, which PySide6 deletes with the range
    wrapper, so holding the wrapper would use-after-free.
    """
    ranges: list[tuple[int, int, QColor]] = []
    block = widget.document().begin()
    while block.isValid():
        base = block.position()
        for r in block.layout().formats():
            rformat = cast(QTextCharFormat, r.format)
            if rformat.underlineStyle() == QTextCharFormat.UnderlineStyle.NoUnderline:
                continue
            ranges.append(
                (
                    base + cast(int, r.start),
                    base + cast(int, r.start) + cast(int, r.length),
                    rformat.underlineColor(),
                )
            )
        block = block.next()
    return ranges


# ******************************************************************************
def testPaletteChangeRecolorsTheDocument(app: QApplication) -> None:
    """A setPalette to a dark palette recolors the document view-only.

    The region tint and the highlighter's tokens follow the new palette,
    the document text takes the dark stop's ink, and the change is
    edit-free: no undo step is recorded and ``regionsChanged`` is not
    emitted.
    """
    widget = PyRaya()
    widget.setPlainText("کلام")
    fired = []
    widget.regionsChanged.connect(fired.append)
    widget.setPalette(_darkPalette())
    app.processEvents()
    assert widget.regionColors()[RegionType.RomanUrdu] == DarkStop.regionTint
    assert widget.highlighter.tokens == resolveTheme(widget.palette())
    for start, end, fg in _layoutForegrounds(widget):
        for idx in range(start, end):
            assert fg is not None and fg == DarkStop.ink, idx
    assert widget.document().availableUndoSteps() == 0
    assert not fired


# ******************************************************************************
def testPinnedRegionColorSurvivesAPaletteChange(app: QApplication) -> None:
    """A setRegionColor pin outlives a palette change.

    The pinned tint stays in the widget's palette and in the layout, while
    the highlighter's tokens still follow the new palette.
    """
    widget = PyRaya()
    pinned = QColor("#34D399")
    assert widget.setRegionColor(RegionType.RomanUrdu, pinned) is True
    widget.setPlainText("کلام")
    widget.setPalette(_darkPalette())
    app.processEvents()
    assert widget.regionColors()[RegionType.RomanUrdu] == pinned
    assert widget.highlighter.tokens == resolveTheme(widget.palette())
    block = widget.document().begin()
    while block.isValid():
        for r in block.layout().formats():
            rformat = cast(QTextCharFormat, r.format)
            if rformat.hasProperty(QTextCharFormat.Property.BackgroundBrush):
                assert rformat.background().color() == pinned
        block = block.next()


# ******************************************************************************
def testHostRulesStayPutOnAPaletteChange(app: QApplication) -> None:
    """Host-installed rules survive a palette change; the tint still follows.

    ``setRules`` replaces the highlighter's default rules, so a theme
    change must not rebuild them — the host's rule keeps its format —
    while the region tint, which the widget owns, still follows the
    palette.
    """
    widget = PyRaya()
    widget.setPlainText("hello")
    hostColor = QColor("#123456")
    hostFormat = QTextCharFormat()
    hostFormat.setForeground(QBrush(hostColor))
    widget.highlighter.setRules([(QRegularExpression("[a-z]+"), hostFormat)])
    widget.setPalette(_darkPalette())
    app.processEvents()
    rules = widget.highlighter.rules
    assert len(rules) == 1
    assert rules[0][1].foreground().color() == hostColor
    assert widget.regionColors()[RegionType.RomanUrdu] == DarkStop.regionTint


# ******************************************************************************
def testAddRuleSurvivesAPaletteChange(app: QApplication) -> None:
    """An addRule appends after the defaults and survives a theme change.

    The default rules are rebuilt from the new stop (the ink rule takes
    the dark stop's ink) while the host-appended rule keeps its format.
    """
    widget = PyRaya()
    widget.setPlainText("hello 42")
    appended = QColor("#654321")
    appendedFormat = QTextCharFormat()
    appendedFormat.setForeground(QBrush(appended))
    widget.highlighter.addRule(QRegularExpression("[0-9]+"), appendedFormat)
    widget.setPalette(_darkPalette())
    app.processEvents()
    rules = widget.highlighter.rules
    assert len(rules) == 9
    assert rules[0][1].foreground().color() == DarkStop.ink
    assert rules[8][1].foreground().color() == appended


# ******************************************************************************
def testNoOpPaletteChangeBumpsNothing(app: QApplication) -> None:
    """A no-op retheme leaves the document revision and undo stack alone.

    A palette change that keeps the stop (only moving the ``Base``) is a
    no-op retheme: it emits a ``PaletteChange`` but resolves to the same
    tokens the highlighter paints, so ``_applyTheme`` re-highlights
    nothing and bumps neither the document's revision nor the undo stack.
    """
    widget = PyRaya()
    widget.setPlainText("کلام")
    document = widget.document()
    revision = document.revision()
    undo = document.availableUndoSteps()
    # A palette change that keeps the stop (only moving the Base) is a
    # no-op retheme: it emits a PaletteChange but resolves to the same
    # tokens, so _applyTheme re-highlights nothing.
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Base, QColor(0xF0, 0xF0, 0xF0))
    widget.setPalette(palette)
    app.processEvents()
    assert document.revision() == revision
    assert document.availableUndoSteps() == undo


# ******************************************************************************
def testSpellCheckUnderlineFollowsTheDarkStop(app: QApplication) -> None:
    """The spell-check underline colour follows the palette's stop.

    Under a dark palette the unknown word's underline is the dark stop's
    spell-check colour, not the light stop's (the exported
    ``SpellCheckUnderlineColor`` stays the light value).
    """
    widget = PyRaya()
    widget.setPlainText("خلمق")
    widget.setPalette(_darkPalette())
    app.processEvents()
    ranges = _underlinedColor(widget)
    assert ranges == [(0, 4, DarkStop.spellUnderline)]


# ******************************************************************************
def testWidgetCreatedUnderADarkPaletteStartsDark(app: QApplication) -> None:
    """A widget constructed under a dark application palette starts dark.

    The construction-time seed reads the widget's own effective palette,
    so a widget created while the application is dark starts with the
    dark stop's tint and tokens.
    """
    light = app.palette()
    app.setPalette(_darkPalette())
    app.processEvents()
    try:
        widget = PyRaya()
        assert widget.regionColors()[RegionType.RomanUrdu] == DarkStop.regionTint
        assert widget.highlighter.tokens == resolveTheme(widget.palette())
    finally:
        app.setPalette(light)
        app.processEvents()


# ******************************************************************************
def testLightDarkLightRoundTripRestoresTheLightPalette(app: QApplication) -> None:
    """A dark-then-light round trip restores every light value.

    After the second switch the region tint, the highlighter's tokens,
    and the document ink are all the light stop's values again.
    """
    widget = PyRaya()
    widget.setPlainText("کلام")
    light = app.palette()
    widget.setPalette(_darkPalette())
    app.processEvents()
    assert widget.regionColors()[RegionType.RomanUrdu] == DarkStop.regionTint
    widget.setPalette(light)
    app.processEvents()
    assert widget.regionColors()[RegionType.RomanUrdu] == LightStop.regionTint
    assert widget.highlighter.tokens == resolveTheme(app.palette())
    for start, end, fg in _layoutForegrounds(widget):
        for idx in range(start, end):
            assert fg is not None and fg == LightStop.ink, idx


# ******************************************************************************
def testStandaloneHighlighterRethemeIsRevisionFree(app: QApplication) -> None:
    """A standalone highlighter's retheme is a no-op on equal tokens.

    Re-theming with the same palette the constructor resolved does not
    re-highlight (no revision bump); a real change re-highlights, and the
    default rules follow the new stop.
    """
    document = QTextDocument()
    highlighter = PyRayaHighlighter(document)
    revision = document.revision()
    assert highlighter.retheme(app.palette()) is False
    assert document.revision() == revision
    assert highlighter.retheme(_darkPalette()) is True
    assert highlighter.rules[0][1].foreground().color() == DarkStop.ink
    assert highlighter.tokens == resolveTheme(_darkPalette())

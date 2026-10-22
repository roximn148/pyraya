# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the spell-check underline in the PyRaya highlighter.

Runs headless via the offscreen Qt platform so no window is opened. The
underline is a display-only layout format (wavy `SpellCheckUnderline` in
`SpellCheckUnderlineColor`) painted over `roman urdu` words the romanalfaz
dictionary does not know, behind a `setSpellCheckEnabled` switch that is
independent of the roman-input feature.
"""

import os
from collections.abc import Generator
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication
from romanalfaz import DictionaryNotFoundError

from pyraya import (
    PyRaya,
    RegionType,
    SpellCheckUnderlineColor,
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
def _underlinedRanges(widget: PyRaya) -> list[tuple[int, int, object, object]]:
    """Every underlined run of the document layout, in reading order.

    Returns ``(start, end, underlineStyle, underlineColor)`` triples with
    document character offsets, from the per-block text layouts' format
    ranges (the authoritative observation point for layout-only formats).
    The style and color are copied to plain Python values immediately:
    the ``QTextCharFormat`` a ``FormatRange`` reports borrows its C++
    object, which PySide6 deletes with the range wrapper, so holding the
    wrapper itself would use-after-free.
    """
    ranges: list[tuple[int, int, object, object]] = []
    block = widget.document().begin()
    while block.isValid():
        base = block.position()
        for r in block.layout().formats():
            # The venv stub declares FormatRange's attributes as `...` with
            # `# type:` comments pyrefly does not read; the runtime types are
            # the ones the comments name, so cast them here.
            rformat = cast(QTextCharFormat, r.format)
            if rformat.underlineStyle() == QTextCharFormat.UnderlineStyle.NoUnderline:
                continue
            ranges.append(
                (
                    base + cast(int, r.start),
                    base + cast(int, r.start) + cast(int, r.length),
                    rformat.underlineStyle(),
                    rformat.underlineColor(),
                )
            )
        block = block.next()
    return ranges


def _documentCharFormat(widget: PyRaya, position: int) -> QTextCharFormat:
    """The document's character format at an offset (layout formats excluded)."""
    cursor = QTextCursor(widget.document())
    cursor.setPosition(position + 1)
    return cursor.charFormat()


# ******************************************************************************
def testDefaultSwitches(app: QApplication) -> None:
    """Spell check is on by default, alongside the roman-input defaults."""
    widget = PyRaya()
    assert widget.isSpellCheckEnabled() is True
    assert widget.isRomanInputEnabled() is True


# ******************************************************************************
def testUnknownRomanUrduWordUnderlined(app: QApplication) -> None:
    """An untagged (default-kind, RomanUrdu) unknown word is underlined only.

    The document's character formats carry no underline (layout-only
    guarantee), and the known word is left untouched.
    """
    widget = PyRaya()
    engine = widget.romanEngine()
    assert engine is not None
    # Pin the dictionary so an ambient dictionary change fails loudly.
    assert engine.hasWord("کتاب") is True
    assert engine.hasWord("خلمق") is False
    widget.setPlainText("کتاب خلمق")
    ranges = _underlinedRanges(widget)
    assert [(start, end) for start, end, _, _ in ranges] == [(5, 9)]
    start, end, style, color = ranges[0]
    assert (start, end) == (5, 9)
    assert style == QTextCharFormat.UnderlineStyle.SpellCheckUnderline
    assert color == SpellCheckUnderlineColor
    # Document formats stay untouched: no underline at the known word (0)
    # or the unknown word (5).
    assert _documentCharFormat(widget, 0).underlineStyle() == (
        QTextCharFormat.UnderlineStyle.NoUnderline
    )
    assert _documentCharFormat(widget, 5).underlineStyle() == (
        QTextCharFormat.UnderlineStyle.NoUnderline
    )


# ******************************************************************************
def testNativeRegionNotUnderlined(app: QApplication) -> None:
    """An Arabic run tagged Native is never checked: RomanUrdu is the only
    kind the spell pass arms, and a Native tag wins over the seed."""
    widget = PyRaya()
    widget.setPlainText("hello خلمق")
    widget.setRegionType(RegionType.Native, 6, 10)
    assert _underlinedRanges(widget) == []


# ******************************************************************************
def testTaggedRomanUrduRegionChecked(app: QApplication) -> None:
    """A run explicitly tagged RomanUrdu is checked and underlined if unknown."""
    widget = PyRaya()
    engine = widget.romanEngine()
    assert engine is not None
    assert engine.hasWord("خلمق") is False
    widget.setPlainText("دوست خلمق")
    widget.setRegionType(RegionType.Native, 0, 4)
    widget.setRegionType(RegionType.RomanUrdu, 5, 9)
    ranges = _underlinedRanges(widget)
    assert [(start, end) for start, end, _, _ in ranges] == [(5, 9)]


# ******************************************************************************
def testSetSpellCheckDisabledRemovesUnderline(app: QApplication) -> None:
    """Toggling the switch off removes the underline; on restores it."""
    widget = PyRaya()
    widget.setPlainText("خلمق")
    assert [(start, end) for start, end, _, _ in _underlinedRanges(widget)] == [(0, 4)]
    widget.setSpellCheckEnabled(False)
    assert widget.isSpellCheckEnabled() is False
    assert _underlinedRanges(widget) == []
    widget.setSpellCheckEnabled(True)
    assert widget.isSpellCheckEnabled() is True
    assert [(start, end) for start, end, _, _ in _underlinedRanges(widget)] == [(0, 4)]


# ******************************************************************************
def testSpellCheckIndependentOfRomanInput(app: QApplication) -> None:
    """Spell check keeps working with roman input disabled; the engine
    accessors keep their contracts; with both flags off the underline is
    absent too (all four flag combinations)."""
    widget = PyRaya()
    widget.setRomanInputEnabled(False)
    assert widget.isRomanInputEnabled() is False
    assert widget.romanEngine() is None
    widget.setPlainText("خلمق")
    assert [(start, end) for start, end, _, _ in _underlinedRanges(widget)] == [(0, 4)]
    assert widget.isSpellCheckEnabled() is True
    assert widget.isRomanInputEnabled() is False
    # The fourth combination: both flags off — no underline, no overlay
    # machinery, and the accessors keep their contracts.
    widget.setSpellCheckEnabled(False)
    assert _underlinedRanges(widget) == []
    assert widget.isSpellCheckEnabled() is False
    assert widget.romanEngine() is None


# ******************************************************************************
def testEngineUnavailableNoUnderline(app: QApplication, monkeypatch) -> None:
    """A dictionary-less engine is an underline no-op, never a crash."""

    def _missing(self=None):
        raise DictionaryNotFoundError("missing")

    class _Missing:
        __init__ = _missing

    monkeypatch.setattr("pyraya.roman_input.RomanAlfaz", _Missing)
    widget = PyRaya()
    widget.setPlainText("خلمق")
    assert _underlinedRanges(widget) == []
    assert widget.isSpellCheckEnabled() is True
    engine = widget.romanEngine()
    assert engine is not None
    assert engine.available is False


# ******************************************************************************
def testHighlightingNotUndoable(app: QApplication) -> None:
    """Setting text with underlined words leaves no undo command behind."""
    widget = PyRaya()
    widget.setPlainText("کتاب خلمق")
    assert _underlinedRanges(widget)
    assert widget.document().availableUndoSteps() == 0

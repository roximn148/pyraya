# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the Urdu word-run segmentation.

Runs headless via the offscreen Qt platform so no window is opened.

The word class is derived from Unicode general categories over the
Arabic-script ranges: a run is a maximal span of letters and combining
marks, with invisible joiners (ZWNJ, ZWJ, LRM, RLM, ALM) transparent inside
it. Digits, punctuation, and symbols are boundaries, and a joiner never
starts or ends a run.
"""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from pyraya import (
    ArabicScriptRanges,
    ArabicScriptSeparators,
    ArabicScriptWordChars,
    PyRaya,
)
from pyraya.pyraya_widget import _isArabicChar, _wordRunAround

#: A presentation-form spelling of ``کام`` (initial kaf, final alef, final meem).
PresentationFormWord = "\ufedb\ufe8e\ufee2"


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
def _moveCursor(widget: PyRaya, position: int) -> None:
    """Move the widget's document cursor to a character offset."""
    cursor = widget.textCursor()
    cursor.setPosition(position)
    widget.setTextCursor(cursor)


# ******************************************************************************
def testArabicScriptRangesCoverTheScript() -> None:
    """The ranges carry the block, its supplement, Extended-A, and the forms."""
    for char in ("\u06a9", "\u0750", "\u08a0", "\ufedb", "\ufe8e"):
        assert any(start <= char <= end for start, end in ArabicScriptRanges), char


# ******************************************************************************
def testWordMatterIsLetterOrMark() -> None:
    """Letters and combining marks are word matter; digits and marks are not."""
    for char in ("\u06a9", "\u0679", "\u06c1", "\ufedb", "\ufe8e", "\u064e", "\u0640"):
        assert _isArabicChar(char), char
    for char in ("\u06f5", "\u0660", "\u06d4", "\u060c", "\u066a", "5", " ", "\u200f"):
        assert not _isArabicChar(char), char


# ******************************************************************************
def testSeparatorsAreEveryArabicScriptPunctuationMark() -> None:
    """The separator set is derived, so it holds the marks a hand list missed."""
    for char in (
        "\u060c",  # ، Arabic comma
        "\u060d",  # ؜ Arabic date separator
        "\u061b",  # ؛ Arabic semicolon
        "\u061f",  # ؟ Arabic question mark
        "\u066b",  # ٫ Arabic decimal separator
        "\u066c",  # ٬ Arabic thousands separator
        "\u06d4",  # ۔ full stop
        "\u0609",  # ؉ per mille sign
        "\u060a",  # ؊ per ten thousand sign
        "\u061e",  # ؞ triple dot punctuation
        "\u066a",  # ٪ percent sign
        "\u066d",  # ٭ five pointed star
    ):
        assert char in ArabicScriptSeparators, hex(ord(char))
    assert ArabicScriptSeparators.isdisjoint(ArabicScriptWordChars)


# ******************************************************************************
def testWordRunStopsAtEasternArabicIndicDigit() -> None:
    """A digit is a boundary, so the substituted digit does not join the word."""
    text = "دوست" + "\u06f5"
    assert _wordRunAround(text, 0) == (0, 4)


# ******************************************************************************
def testArabicIndicDigitsAreNoWord() -> None:
    """A run of digits is no word at all."""
    assert _wordRunAround("\u06f1\u06f2", 0) is None
    assert _wordRunAround("\u0661\u0662", 0) is None


# ******************************************************************************
def testJoinerIsTransparentInsideAWord() -> None:
    """A ZWNJ inside a word neither splits it nor becomes the word."""
    text = "\u06a9" + "\u200c" + "\u0627\u0645"
    assert _wordRunAround(text, 0) == (0, len(text))
    assert _wordRunAround(text, 1) == (0, len(text))


# ******************************************************************************
def testJoinerNeverStartsOrEndsARun() -> None:
    """An RLM before the word and an LRM after it are trimmed off the run."""
    text = "\u200f" + "\u06a9\u0627\u0645" + "\u200e"
    assert _wordRunAround(text, 1) == (1, 4)


# ******************************************************************************
def testJoinersAloneAreNoWord() -> None:
    """A run of only joiners is not a word."""
    assert _wordRunAround("\u200c\u200d", 0) is None


# ******************************************************************************
def testWordUnderCursorStopsBeforeTheDigit(app: QApplication) -> None:
    """The widget's word under the cursor ends at the substituted digit."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("دوست" + "\u06f5")
    _moveCursor(widget, 2)
    assert widget._activeWord == (0, 4)


# ******************************************************************************
def testPresentationFormWordIsAWord(app: QApplication) -> None:
    """A presentation-form word pasted from a PDF is still one word."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText(PresentationFormWord)
    _moveCursor(widget, 1)
    assert widget._activeWord == (0, len(PresentationFormWord))


# ******************************************************************************
def testArabicScriptInkRuleCoversEveryRange(app: QApplication) -> None:
    """The default ink rule matches the presentation forms and the supplement."""
    widget = PyRaya()
    inkRule = widget._highlighter.rules[0][0]
    for char in ("\u06a9", "\u0750", "\u08a0", "\ufedb", "\ufe8e"):
        assert inkRule.match(char).hasMatch(), hex(ord(char))
    assert not inkRule.match("a").hasMatch()


# ******************************************************************************
def testPresentationFormWordDoesNotBreakTheSuggestionPath(app: QApplication) -> None:
    """A presentation-form word reaches the overlay without raising."""
    widget = PyRaya()
    engine = widget.romanEngine()
    assert engine is not None
    roman = engine.romanizeArabic(PresentationFormWord)
    assert isinstance(engine.suggestTiers(roman), list)

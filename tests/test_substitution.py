# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the region-scoped 1:1 character substitution.

Runs headless via the offscreen Qt platform so no window is opened.

The substitution is a fixed per-region-kind table: a Latin character typed
into a RomanUrdu span lands in the document in its Urdu form (the four
punctuation marks and the Eastern Arabic-Indic digits), tagged RomanUrdu.
It is region-scoped — it holds regardless of the roman-input feature or
assist mode, and regardless of whether the overlay is active.
"""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from pyraya import (
    PyRaya,
    RegionSubstitutions,
    RegionType,
    RomanOverlay,
    substituteChar,
    substituteText,
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
def _moveCursor(widget: PyRaya, position: int) -> None:
    """Move the widget's document cursor to a character offset."""
    cursor = widget.textCursor()
    cursor.setPosition(position)
    widget.setTextCursor(cursor)


# ******************************************************************************
def _keyPress(widget: PyRaya, key: int, text: str = "") -> None:
    """Send a key-press event to the widget (the document)."""
    QCoreApplication.sendEvent(
        widget, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)
    )


# ******************************************************************************
def _sendKey(
    widget: QWidget,
    key: int,
    text: str = "",
) -> None:
    """Send a key-press event to a widget (e.g. the overlay line edit)."""
    QCoreApplication.sendEvent(
        widget, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)
    )


# ******************************************************************************
def testRegionSubstitutionsTable(app: QApplication) -> None:
    """The table maps the four marks and ten digits; Native is empty."""
    roman = RegionSubstitutions[RegionType.RomanUrdu]
    assert roman["."] == "\u06d4"
    assert roman[","] == "\u060c"
    assert roman["?"] == "\u061f"
    assert roman[";"] == "\u061b"
    for digit in range(10):
        assert roman[str(digit)] == chr(0x06F0 + digit)
    # The colon is a deliberate no-op: not in the table.
    assert ":" not in roman
    # Native passes every character through.
    assert RegionSubstitutions[RegionType.Native] == {}


# ******************************************************************************
def testSubstituteChar(app: QApplication) -> None:
    """substituteChar returns the mapped character or None."""
    assert substituteChar(".", RegionType.RomanUrdu) == "\u06d4"
    assert substituteChar("5", RegionType.RomanUrdu) == "\u06f5"
    assert substituteChar("k", RegionType.RomanUrdu) is None
    assert substituteChar(":", RegionType.RomanUrdu) is None
    assert substituteChar(".", RegionType.Native) is None


# ******************************************************************************
def testSubstituteText(app: QApplication) -> None:
    """substituteText replaces every mapped character, passes the rest through."""
    # 'a' and 'b' pass through; '5' and '.' are substituted.
    assert substituteText("a5.b", RegionType.RomanUrdu) == "a\u06f5\u06d4b"
    # Native passes every character through unchanged.
    assert substituteText("a5.b", RegionType.Native) == "a5.b"


# ******************************************************************************
def testPunctuationSubstitutedDirectWrite(app: QApplication) -> None:
    """A typed full stop in a RomanUrdu span lands as its Urdu form."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("word")
    _moveCursor(widget, 4)  # the cursor at the end, past the word
    _keyPress(widget, Qt.Key.Key_Period, ".")
    assert widget.toPlainText() == "word\u06d4"
    assert widget._regionKindAt(4) == RegionType.RomanUrdu


# ******************************************************************************
def testDigitSubstitutedDirectWrite(app: QApplication) -> None:
    """A typed digit in a RomanUrdu span lands as its Urdu form."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("word")
    _moveCursor(widget, 4)
    _keyPress(widget, Qt.Key.Key_5, "5")
    assert widget.toPlainText() == "word\u06f5"
    assert widget._regionKindAt(4) == RegionType.RomanUrdu


# ******************************************************************************
def testDigitDoesNotSeedOverlay(app: QApplication) -> None:
    """A typed digit in a RomanUrdu span no longer seeds the overlay."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("word")
    _moveCursor(widget, 4)
    _keyPress(widget, Qt.Key.Key_5, "5")
    assert widget._overlay is None or not widget._overlay.isVisible()
    assert widget.toPlainText() == "word\u06f5"


# ******************************************************************************
def testLetterStillSeedsOverlay(app: QApplication) -> None:
    """A typed letter in a RomanUrdu span still seeds the overlay."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("word")
    _moveCursor(widget, 4)
    _keyPress(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "k"
    # The letter never reaches the document (it seeds the overlay).
    assert widget.toPlainText() == "word"


# ******************************************************************************
def testNativeMappedCharPassesThrough(app: QApplication) -> None:
    """A mapped character in a Native span passes through unchanged."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("word")
    widget.setRegionType(RegionType.Native, 0, 4)
    _moveCursor(widget, 4)
    _keyPress(widget, Qt.Key.Key_Period, ".")
    # The Native table is empty: the Latin period lands as-is, tagged Native.
    assert widget.toPlainText() == "word."
    assert widget._regionKindAt(4) == RegionType.Native


# ******************************************************************************
def testSubstitutionIndependentOfFeatureFlag(app: QApplication) -> None:
    """The substitution holds with the roman-input feature off.

    It is region-scoped, not feature-scoped: it is a property of the region
    kind, not of the roman-input overlay.
    """
    widget = PyRaya()
    widget.show()
    widget.setPlainText("word")
    widget.setRomanInputEnabled(False)
    _moveCursor(widget, 4)
    _keyPress(widget, Qt.Key.Key_Period, ".")
    assert widget.toPlainText() == "word\u06d4"
    assert widget._regionKindAt(4) == RegionType.RomanUrdu


# ******************************************************************************
def _commitSetup() -> tuple[PyRaya, RomanOverlay]:
    """A widget with the overlay active over a RomanUrdu word."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 10)
    _moveCursor(widget, 7)  # inside دوست: activates the overlay over it
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    return widget, overlay


# ******************************************************************************
def testCommitDigitSubstitutedSeparator(app: QApplication) -> None:
    """A digit over an active overlay commits the word; the digit substitutes.

    Digits are committing keys (like punctuation): the digit terminates the
    word and commits, and it lands in the document in its Urdu form as the
    separator.
    """
    widget, overlay = _commitSetup()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_5, "5")
    # The word span is replaced by the committed word plus the digit.
    assert widget.toPlainText() == "hello دوست\u06f5"
    assert widget._regionKindAt(len(widget.toPlainText()) - 1) == RegionType.RomanUrdu
    assert not overlay.isVisible()


# ******************************************************************************
def testCommitPunctuationSubstitutedSeparator(app: QApplication) -> None:
    """A typed mark over an active overlay commits; the mark substitutes.

    The typed Latin mark is the separator, and it lands in the document in
    its Urdu form, tagged RomanUrdu with the word.
    """
    widget, overlay = _commitSetup()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Period, ".")
    assert widget.toPlainText() == "hello دوست\u06d4"
    assert widget._regionKindAt(len(widget.toPlainText()) - 1) == RegionType.RomanUrdu
    assert not overlay.isVisible()

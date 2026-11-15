# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for selection enveloping (auto-wrap).

Runs headless via the offscreen Qt platform so no window is opened.

Selection enveloping wraps a selected range in a bracket or quote pair
when the user presses one of the pair's trigger characters over it: the
key is consumed, the opening mark lands at the selection's start and the
closing mark at its end, each tagged with the region kind its landing
position carries. Without a selection every trigger types as-is, and
the feature and the enabled pair set are host-configurable.
"""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication

from pyraya import (
    DefaultWrapPairs,
    PyRaya,
    RegionType,
    WrapPair,
    WrapPairs,
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
def _select(widget: PyRaya, start: int, end: int) -> None:
    """Select the character range [start, end) in the widget."""
    cursor = widget.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    widget.setTextCursor(cursor)


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
def testWrapPairsTableHoldsEveryEnumeratedPair(app: QApplication) -> None:
    """The table carries the fifteen enumerated pairs; the default is five."""
    assert set(WrapPairs) == {
        "parentheses",
        "square",
        "curly",
        "guillemets",
        "single-guillemets",
        "angle-brackets",
        "floor-brackets",
        "ceiling-brackets",
        "black-brackets",
        "fullwidth-parentheses",
        "double-quote",
        "single-quote",
        "low-double-quote",
        "mixed-double-quote",
        "low-single-quote",
    }
    assert DefaultWrapPairs == frozenset(
        {"parentheses", "square", "curly", "double-quote", "single-quote"}
    )


# ******************************************************************************
def testWrapPairRecordsAreSelfDescribing(app: QApplication) -> None:
    """Each pair names itself and carries its marks and trigger characters."""
    parentheses = WrapPairs["parentheses"]
    assert isinstance(parentheses, WrapPair)
    assert parentheses.name == "parentheses"
    assert parentheses.opening == "("
    assert parentheses.closing == ")"
    assert parentheses.triggers == ("(", ")")
    doubleQuote = WrapPairs["double-quote"]
    assert doubleQuote.opening == "\u201c"
    assert doubleQuote.closing == "\u201d"
    assert doubleQuote.triggers == ('"',)
    singleQuote = WrapPairs["single-quote"]
    assert singleQuote.opening == "\u2018"
    assert singleQuote.closing == "\u2019"
    assert singleQuote.triggers == ("'",)


# ******************************************************************************
def testDefaultTriggerSetIsTheNineKeyboardCharacters(app: QApplication) -> None:
    """The default pairs' triggers are ( ) [ ] { } and the straight quotes."""
    triggers = frozenset(c for name in DefaultWrapPairs for c in WrapPairs[name].triggers)
    assert triggers == frozenset("()[]{}\"'")


# ******************************************************************************
def testTriggerOverSelectionEnvelopsIt(app: QApplication) -> None:
    """A trigger key over a selection is consumed and envelops it."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "a(bc)d"
    cursor = widget.textCursor()
    assert not cursor.hasSelection()
    assert cursor.position() == 5


# ******************************************************************************
def testEitherBracketMemberTriggers(app: QApplication) -> None:
    """Typing the closing member envelops with the same pair."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_ParenRight, ")")
    assert widget.toPlainText() == "a(bc)d"


# ******************************************************************************
def testSquareAndCurlyPairsEnvelop(app: QApplication) -> None:
    """The square and curly pairs envelop over a selection."""
    square = PyRaya()
    square.setPlainText("abcd")
    _select(square, 1, 3)
    _keyPress(square, Qt.Key.Key_BracketLeft, "[")
    assert square.toPlainText() == "a[bc]d"
    curly = PyRaya()
    curly.setPlainText("abcd")
    _select(curly, 1, 3)
    _keyPress(curly, Qt.Key.Key_BraceRight, "}")
    assert curly.toPlainText() == "a{bc}d"


# ******************************************************************************
def testStraightDoubleQuoteEnvelopsInCurlyPair(app: QApplication) -> None:
    """The straight double quote envelops in the Urdu curly pair."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_QuoteDbl, '"')
    assert widget.toPlainText() == "a\u201cbc\u201dd"
    assert '"' not in widget.toPlainText()


# ******************************************************************************
def testStraightApostropheEnvelopsInSinglePair(app: QApplication) -> None:
    """The straight apostrophe envelops in the Urdu single pair."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_Apostrophe, "'")
    assert widget.toPlainText() == "a\u2018bc\u2019d"
    assert "'" not in widget.toPlainText()


# ******************************************************************************
def testCurlyQuotesAreNotTriggers(app: QApplication) -> None:
    """The curly forms have no keyboard mapping and pass through untouched."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_unknown, "\u201c")
    assert widget.toPlainText() == "a\u201cd"


# ******************************************************************************
def testNoSelectionTypesTriggerAsIs(app: QApplication) -> None:
    """Without a selection a trigger types its own character, as before."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _moveCursor(widget, 2)
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "ab(cd"
    assert widget.textCursor().position() == 3


# ******************************************************************************
def testNoSelectionTypesStraightQuoteAsIs(app: QApplication) -> None:
    """Without a selection the straight quote inserts as the straight form."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _moveCursor(widget, 2)
    _keyPress(widget, Qt.Key.Key_QuoteDbl, '"')
    assert widget.toPlainText() == 'ab"cd'


# ******************************************************************************
def testEnvelopIsOneUndoStep(app: QApplication) -> None:
    """The envelop is one logical edit: one undo restores the selection.

    ``availableUndoSteps`` counts the write as three commands (Qt's
    accounting for the two mark inserts beside the selection), but one
    ``undo()`` restores the pre-wrap text — the span-replacement-commit
    precedent, counted larger than its logical edit.
    """
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    baseline = widget.document().availableUndoSteps()
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.document().availableUndoSteps() > baseline
    widget.undo()
    assert widget.toPlainText() == "abcd"
    widget.redo()
    assert widget.toPlainText() == "a(bc)d"


# ******************************************************************************
def testEnvelopEmitsNoSignals(app: QApplication) -> None:
    """The envelop write is signal-cost-free, like typing."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    emitted: list[bool] = []
    widget.regionsChanged.connect(lambda: emitted.append(True))
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "a(bc)d"
    assert not emitted


# ******************************************************************************
def testMismatchedEndsDoNotEnvelop(app: QApplication) -> None:
    """A selection whose ends resolve to different kinds does not envelope."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 0, 2)
    widget.setRegionType(RegionType.Native)  # "ab" Native
    _select(widget, 2, 4)  # ends: opening kind Native, closing kind RomanUrdu
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    # The gate rejects it: the trigger replaces the selection as a plain
    # keystroke (no selection is consumed by the envelop).
    assert widget.toPlainText() == "ab("
    assert widget.textCursor().position() == 3


# ******************************************************************************
def testMarksCarryTheKindOfTheirLandingPosition(app: QApplication) -> None:
    """Each mark is tagged with the kind resolved at its own landing.

    Pinned directly on ``_envelopSelection`` (bypassing the gate), so the
    per-edge tagging holds even for a mismatched-ends selection that the
    same-kind gate no longer reaches.
    """
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 0, 2)
    widget.setRegionType(RegionType.Native)
    _select(widget, 2, 4)
    widget._envelopSelection(WrapPairs["parentheses"])
    assert widget.toPlainText() == "ab(cd)"
    # The opening mark lands beside the Native 'b' before the selection.
    assert widget._regionKindAt(2) is RegionType.Native
    # The closing mark lands after the selection's seed-resolved 'd'.
    assert widget._regionKindAt(5) is RegionType.RomanUrdu
    assert widget._regionKindAt(4) is RegionType.RomanUrdu


# ******************************************************************************
def testNativeTaggedSelectionIsPreserved(app: QApplication) -> None:
    """The envelop never replaces the selection: text and tags ride along.

    The selection spans a RomanUrdu end, so the same-kind gate accepts it
    even though the inner sub-run is Native: the marks resolve RomanUrdu at
    both ends and the Native sub-run rides along untouched.
    """
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    widget.setRegionType(RegionType.Native)  # tag "bc" Native
    _select(widget, 1, 4)  # select "bcd": ends both resolve RomanUrdu
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "a(bcd)"
    assert widget._regionKindAt(1) is RegionType.RomanUrdu  # opening mark
    assert widget._regionKindAt(2) is RegionType.Native  # 'b'
    assert widget._regionKindAt(3) is RegionType.Native  # 'c'
    assert widget._regionKindAt(4) is RegionType.RomanUrdu  # 'd'
    assert widget._regionKindAt(5) is RegionType.RomanUrdu  # closing mark


# ******************************************************************************
def testEnvelopWorksInNativeRegion(app: QApplication) -> None:
    """Enveloping is region-agnostic: a Native span wraps in Native marks."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 0, 4)
    widget.setRegionType(RegionType.Native)
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "a(bc)d"
    assert widget._regionKindAt(1) is RegionType.Native
    assert widget._regionKindAt(4) is RegionType.Native


# ******************************************************************************
def testFeatureOffTypesTriggerAsUsual(app: QApplication) -> None:
    """With the feature off, a trigger replaces the selection as Qt types."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setAutoWrapEnabled(False)
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "a(d"
    assert widget.textCursor().position() == 2


# ******************************************************************************
def testFeatureReEnableRestoresEnveloping(app: QApplication) -> None:
    """Re-enabling the feature restores the enveloping."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setAutoWrapEnabled(False)
    widget.setAutoWrapEnabled(True)
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "a(bc)d"


# ******************************************************************************
def testSetWrapPairsReconfiguresTheEnabledSet(app: QApplication) -> None:
    """The runtime pair setter swaps the trigger set for the next keys."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setWrapPairs(["guillemets"])
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "a(d"
    guillemets = PyRaya()
    guillemets.setPlainText("abcd")
    guillemets.setWrapPairs(["guillemets"])
    _select(guillemets, 1, 3)
    _keyPress(guillemets, Qt.Key.Key_unknown, "\u00ab")
    assert guillemets.toPlainText() == "a\u00abbc\u00bbd"


# ******************************************************************************
def testSetWrapPairsRejectsUnknownNames(app: QApplication) -> None:
    """An unknown pair name is a ValueError."""
    widget = PyRaya()
    with pytest.raises(ValueError):
        widget.setWrapPairs(["nonexistent"])


# ******************************************************************************
def testMultiLineSelectionGetsASinglePair(app: QApplication) -> None:
    """A block-spanning selection is enveloped once at its edges."""
    widget = PyRaya()
    widget.setPlainText("ab\ncd")
    _select(widget, 0, 5)
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "(ab\ncd)"
    assert widget.textCursor().position() == 7


# ******************************************************************************
def testLandingAtBoundaryKeepsTheOverlayClosed(app: QApplication) -> None:
    """A landing beside a boundary mark stays quiet: no overlay appears."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("\u06a9\u0627\u0645 \u0644\u0645")
    _select(widget, 0, 3)
    # The setPlainText sync auto-activates the overlay over the word under
    # the cursor; a real selection comes from a mouse press, which
    # deactivates it — mirror that before the key.
    widget._deactivateOverlay()
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "(\u06a9\u0627\u0645) \u0644\u0645"
    assert widget.textCursor().position() == 5
    assert widget._overlay is None or not widget._overlay.isVisible()
    assert widget._wordUnderCursor() is None


# ******************************************************************************
def testLandingOnWordStartActivatesTheOverlay(app: QApplication) -> None:
    """A landing on a following word activates the overlay, as a cursor move."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("\u06a9\u0627\u0645\u0644\u0645")
    _select(widget, 0, 3)
    # Mirror the real flow: the selection's mouse press deactivates the
    # overlay the setPlainText sync activated.
    widget._deactivateOverlay()
    _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
    assert widget.toPlainText() == "(\u06a9\u0627\u0645)\u0644\u0645"
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()

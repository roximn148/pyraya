# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the roman-input overlay subsystem.

Runs headless via the offscreen Qt platform so no window is opened.
"""

import os
from collections.abc import Generator
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor, QWheelEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget
from romanalfaz import DictionaryNotFoundError
from romanalfaz.engine import Suggestion, Vocabulary

from pyraya import PyRaya
from pyraya.regions import RegionType
from pyraya.roman_input import RomanInputEngine, RomanOverlay

# Verified zero-match roman strings (no suggestions at distance 0..2).
ZERO_MATCH_WORDS = ["xqwzrty", "qzxv", "kzqwxv", "zxrqvz", "qwzxq"]


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
@pytest.fixture()
def engine() -> RomanInputEngine:
    """Provide an available RomanInputEngine (cold loads the default wordlist)."""
    return RomanInputEngine()


# ******************************************************************************
def testRomanizeArabicKnownWords(engine: RomanInputEngine) -> None:
    """romanizeArabic lowercases the encoded roman for known words."""
    assert engine.romanizeArabic("خوش") == "khosh"
    assert engine.romanizeArabic("میری") == "myry"
    assert engine.romanizeArabic("دوست") == "dost"


# ******************************************************************************
def testSuggestTierOrderAndDedup(engine: RomanInputEngine) -> None:
    """suggest merges tiers in order and globally dedupes by Arabic word."""
    exact = engine.suggest("khosh")
    assert len(exact) > 0
    assert exact[0].arabic == "خوش"  # exact tier leads
    seen = set()
    for suggestion in exact:
        assert suggestion.arabic not in seen
        seen.add(suggestion.arabic)

    d1 = engine.suggest("khos")
    assert len(d1) > 0


# ******************************************************************************
def testSuggestCap(engine: RomanInputEngine) -> None:
    """suggest caps the merged list at maxSuggestions."""
    assert len(engine.suggest("khosh")) <= 10
    strict = RomanInputEngine(maxSuggestions=3)
    assert len(strict.suggest("khosh")) <= 3


# ******************************************************************************
def testSuggestNoMatches(engine: RomanInputEngine) -> None:
    """suggest returns an empty list for words with no matches."""
    for word in ZERO_MATCH_WORDS:
        assert engine.suggest(word) == []


# ******************************************************************************
def testSuggestTiers(engine: RomanInputEngine) -> None:
    """suggestTiers tags each suggestion with its tier; earlier tier wins dedup."""
    tiers = engine.suggestTiers("khosh")
    assert len(tiers) > 0
    assert tiers[0][1] == 0
    top = tiers[0][0]
    assert top.arabic == "خوش"

    d1 = engine.suggestTiers("khos")
    assert len(d1) > 0
    assert all(tier == 1 for _, tier in d1)
    seen = set()
    for suggestion, _ in d1:
        assert suggestion.arabic not in seen
        seen.add(suggestion.arabic)


# ******************************************************************************
def testSuggestDistanceConfig(engine: RomanInputEngine) -> None:
    """The distance parameter is passed through to RomanAlfaz.suggest."""
    d1 = RomanInputEngine(distance=1)
    assert len(d1.suggest("khosh")) > 0  # exact tier still found at distance 1


# ******************************************************************************
def testLearnRomanWordNoOp(engine: RomanInputEngine) -> None:
    """learnRomanWord returns the same word as-is for this session."""
    for word in ZERO_MATCH_WORDS:
        assert engine.learnRomanWord(word) == word
    assert engine.learnRomanWord("") == ""


# ******************************************************************************
def testEngineUnavailable(monkeypatch) -> None:
    """A DictionaryNotFoundError yields an unavailable, non-crashing engine."""

    class _Missing:
        def __init__(self) -> None:
            raise DictionaryNotFoundError("missing")

    monkeypatch.setattr("pyraya.roman_input.RomanAlfaz", _Missing)
    engine = RomanInputEngine()
    assert engine.available is False
    assert engine.suggest("khosh") == []
    assert engine.suggestTiers("khosh") == []
    assert engine.learnRomanWord("xqwzrty") == "xqwzrty"


# ******************************************************************************
def testAddVocabularyAttached(app: QApplication) -> None:
    """The local vocabulary is attached alongside the default wordlist."""
    local = Vocabulary()
    engine = RomanInputEngine(local)
    assert engine.available is True
    assert engine.suggest("khosh")[0].arabic == "خوش"


# ******************************************************************************
def _sendKey(widget: QWidget, key: int, text: str = "") -> None:
    """Send a key-press event to a widget."""
    QCoreApplication.sendEvent(
        widget,
        QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text),
    )


# ******************************************************************************
class _WheelSpy(QPlainTextEdit):
    """A scroll area that records the wheel events it receives."""

    def __init__(self) -> None:
        super().__init__()
        self.forwarded: list[QWheelEvent] = []

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.forwarded.append(event)
        super().wheelEvent(event)


# ******************************************************************************
def _makeOverlay(app: QApplication, engine: RomanInputEngine) -> tuple[RomanOverlay, _WheelSpy]:
    """Build a RomanOverlay inside a scroll-area host viewport."""
    host = _WheelSpy()
    host.show()
    overlay = RomanOverlay(engine, host.font(), host.viewport())
    overlay.show()
    return overlay, host


# ******************************************************************************
def testOverlaySeparatorCommits(app: QApplication, engine: RomanInputEngine) -> None:
    """Space / Enter / punctuation commit the selected suggestion plus the char."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khosh")
    captured: list[tuple[str, Suggestion | None, bool, str]] = []
    overlay.committed.connect(
        lambda roman, selected, placeholder, separator: captured.append(
            (roman, selected, placeholder, separator),
        ),
    )

    lineEdit = overlay.lineEdit()
    _sendKey(lineEdit, Qt.Key.Key_Space, " ")
    assert len(captured) == 1
    roman, selected, placeholder, separator = captured[0]
    assert roman == "khosh"
    assert placeholder is False
    assert separator == " "
    assert selected is not None and selected.arabic == "خوش"

    captured.clear()
    _sendKey(lineEdit, Qt.Key.Key_Return, "\n")
    assert len(captured) == 1
    assert captured[0][3] == "\n"

    captured.clear()
    _sendKey(lineEdit, Qt.Key.Key_Comma, ",")
    assert len(captured) == 1
    assert captured[0][3] == ","


# ******************************************************************************
def testOverlayEdgeCommits(app: QApplication, engine: RomanInputEngine) -> None:
    """Left at the start / Right at the end commit without a separator."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khosh")
    captured: list[tuple[str, Suggestion | None, bool, str]] = []
    overlay.committed.connect(
        lambda roman, selected, placeholder, separator: captured.append(
            (roman, selected, placeholder, separator),
        ),
    )

    lineEdit = overlay.lineEdit()
    lineEdit.setCursorPosition(0)
    _sendKey(lineEdit, Qt.Key.Key_Left)
    assert len(captured) == 1
    assert captured[0][3] == ""

    lineEdit.setCursorPosition(len("khosh"))
    _sendKey(lineEdit, Qt.Key.Key_Right)
    assert len(captured) == 2
    assert captured[1][3] == ""


# ******************************************************************************
def testOverlayEscCancels(app: QApplication, engine: RomanInputEngine) -> None:
    """Esc emits canceled and never commits."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khosh")
    committed = []
    overlay.committed.connect(lambda *args: committed.append(args))
    canceled = []
    overlay.canceled.connect(lambda: canceled.append(None))

    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert len(canceled) == 1
    assert committed == []


# ******************************************************************************
def testOverlayUpDownWrapsSelection(app: QApplication, engine: RomanInputEngine) -> None:
    """Up / Down move the highlighted suggestion with wraparound."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khos")  # six distance-1 suggestions
    suggestionList = overlay.suggestionList()
    count = suggestionList.rowCount()
    assert count > 1
    assert suggestionList.selectedIndex() == 0

    overlay.moveSelection(1)
    assert suggestionList.selectedIndex() == 1
    overlay.moveSelection(-1)
    assert suggestionList.selectedIndex() == 0

    suggestionList.select(count - 1)
    overlay.moveSelection(1)
    assert suggestionList.selectedIndex() == 0  # wraps
    overlay.moveSelection(-1)
    assert suggestionList.selectedIndex() == count - 1  # wraps


# ******************************************************************************
def testOverlayEmptyTextHidesList(app: QApplication, engine: RomanInputEngine) -> None:
    """Empty overlay text shows no rows and no placeholder."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("")
    suggestionList = overlay.suggestionList()
    assert suggestionList.rowCount() == 0
    assert suggestionList.selectedSuggestion() is None


# ******************************************************************************
def testOverlayZeroMatchesShowsPlaceholder(
    app: QApplication,
    engine: RomanInputEngine,
) -> None:
    """A non-empty typed word with zero matches shows the Learn placeholder."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText(ZERO_MATCH_WORDS[0])
    suggestionList = overlay.suggestionList()
    assert suggestionList.rowCount() == 1
    row = suggestionList.selectedRow()
    assert row is not None and row.isPlaceholder
    assert suggestionList.selectedSuggestion() is None
    assert suggestionList.isPlaceholderSelected() is True

    captured: list[tuple[str, Suggestion | None, bool, str]] = []
    overlay.committed.connect(
        lambda roman, selected, placeholder, separator: captured.append(
            (roman, selected, placeholder, separator),
        ),
    )
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert len(captured) == 1
    roman, selected, placeholder, separator = captured[0]
    assert roman == ZERO_MATCH_WORDS[0]
    assert selected is None
    assert placeholder is True
    assert separator == " "


# ******************************************************************************
def testOverlayUnavailableOffersNothing(app: QApplication, monkeypatch) -> None:
    """An unavailable engine offers no rows, no placeholder, and no crash."""

    class _Missing:
        def __init__(self) -> None:
            raise DictionaryNotFoundError("missing")

    monkeypatch.setattr("pyraya.roman_input.RomanAlfaz", _Missing)
    engine = RomanInputEngine()
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khosh")
    suggestionList = overlay.suggestionList()
    assert suggestionList.rowCount() == 0
    assert suggestionList.isPlaceholderSelected() is False

    captured: list[tuple[str, Suggestion | None, bool, str]] = []
    overlay.committed.connect(
        lambda roman, selected, placeholder, separator: captured.append(
            (roman, selected, placeholder, separator),
        ),
    )
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert len(captured) == 1
    roman, selected, placeholder, separator = captured[0]
    assert roman == "khosh"
    assert selected is None
    assert placeholder is False
    assert separator == " "


# ******************************************************************************
def testOverlayRefreshesOnEdit(app: QApplication, engine: RomanInputEngine) -> None:
    """Typing in the overlay edits the roman text and refreshes synchronously."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khosh")
    lineEdit = overlay.lineEdit()
    _sendKey(lineEdit, Qt.Key.Key_B, "b")
    assert lineEdit.text() == "khoshb"
    tiers = engine.suggestTiers("khoshb")
    expected = len(tiers) if tiers else 1
    assert overlay.suggestionList().rowCount() == expected


# ******************************************************************************
def testOverlayWheelForwardsToScrollArea(
    app: QApplication,
    engine: RomanInputEngine,
) -> None:
    """Wheel events in the overlay forward into the host scroll area."""
    overlay, host = _makeOverlay(app, engine)
    host.setPlainText("\n".join(f"line{i}" for i in range(40)))
    host.verticalScrollBar().setValue(0)
    event = QWheelEvent(
        QPoint(10, 10),
        QPoint(10, 10),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QCoreApplication.sendEvent(overlay.lineEdit(), event)
    assert len(host.forwarded) == 1
    assert host.forwarded[0].angleDelta() == QPoint(0, -120)
    # inverted vbar: a -120 notch from 0 scrolls three lines down.
    assert host.verticalScrollBar().value() == 3


# ******************************************************************************
def testRomanInputFeatureOffByDefault(app: QApplication) -> None:
    """The feature is off by default and roman keystrokes type into the document."""
    widget = PyRaya()
    assert widget.isRomanInputEnabled() is False
    _sendKey(widget, Qt.Key.Key_K, "k")
    assert widget.toPlainText() == "k"
    _sendKey(widget, Qt.Key.Key_O, "o")
    assert widget.toPlainText() == "ko"


# ******************************************************************************
def testRomanInputFeatureSwitch(app: QApplication) -> None:
    """setRomanInputEnabled toggles the feature; romanEngine is None while off."""
    widget = PyRaya()
    widget.setRomanInputEnabled(True)
    assert widget.isRomanInputEnabled() is True
    engine = widget.romanEngine()
    assert isinstance(engine, RomanInputEngine)
    widget.setRomanInputEnabled(False)
    assert widget.isRomanInputEnabled() is False
    assert widget.romanEngine() is None


# ******************************************************************************
def testRomanEngineLazyAndStable(app: QApplication) -> None:
    """romanEngine returns the same lazily-created engine across calls."""
    widget = PyRaya()
    widget.setRomanInputEnabled(True)
    engine = widget.romanEngine()
    assert isinstance(engine, RomanInputEngine)
    assert widget.romanEngine() is engine


# ******************************************************************************
def testLocalDictionaryStableAndRoundTrips(app: QApplication, tmp_path) -> None:
    """localDictionary returns the same Vocabulary and save/load round-trips."""
    widget = PyRaya()
    first = widget.localDictionary()
    assert widget.localDictionary() is first
    first.add("khosh", 1)
    first.setCompleted("khosh", True)
    path = str(tmp_path / "vocab.txt")
    first.save(path)
    loaded = Vocabulary.load(path)
    assert loaded.counter["khosh"] == 1


# ******************************************************************************
def testNoPhantomUndoWithFeatureEnabled(app: QApplication) -> None:
    """Enabling the feature performs no document work (no phantom undo)."""
    widget = PyRaya()
    widget.setRomanInputEnabled(True)
    assert widget.document().isUndoAvailable() is False


# ******************************************************************************
def _moveCursor(widget: PyRaya, position: int) -> None:
    """Move the widget's document cursor to a character offset."""
    cursor = widget.textCursor()
    cursor.setPosition(position)
    widget.setTextCursor(cursor)


# ******************************************************************************
def _assertNoOverlay(widget: PyRaya) -> None:
    """The overlay is absent or hidden."""
    assert widget._overlay is None or not widget._overlay.isVisible()


# ******************************************************************************
def testActivatesOnArabicWordInRomanUrduSpan(app: QApplication) -> None:
    """The cursor inside a RomanUrdu-tagged Arabic word activates the overlay."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None
    assert overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"


# ******************************************************************************
def testNoOverlayOnWhitespaceDigitsLatin(app: QApplication) -> None:
    """No overlay on whitespace, digits, a Latin-region word, or feature off."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello 123 خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 10, 13)
    _moveCursor(widget, 5)  # whitespace
    _assertNoOverlay(widget)
    _moveCursor(widget, 7)  # digits
    _assertNoOverlay(widget)
    _moveCursor(widget, 11)  # inside the Arabic word
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()

    widget.setPlainText("hello خوش world")
    widget.setRegionType(RegionType.Latin, 6, 9)
    _moveCursor(widget, 7)  # Arabic word inside a Latin region
    _assertNoOverlay(widget)

    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    widget.setRomanInputEnabled(False)
    _moveCursor(widget, 7)  # feature off
    _assertNoOverlay(widget)


# ******************************************************************************
def testNoOverlayOnPartialContainment(app: QApplication) -> None:
    """A word not fully contained in a RomanUrdu span does not activate."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 7, 9)  # only part of the word
    _moveCursor(widget, 8)
    _assertNoOverlay(widget)


# ******************************************************************************
def testNoOverlayAtTrailingTerminator(app: QApplication) -> None:
    """A cursor on the trailing terminator never activates the overlay."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 9)  # the trailing terminator position
    _assertNoOverlay(widget)
    _moveCursor(widget, 0)  # back to a valid position: still no crash
    _assertNoOverlay(widget)


# ******************************************************************************
def testGeometryBounds(app: QApplication) -> None:
    """The overlay is anchored to the word rect and stays inside the viewport."""
    widget = PyRaya()
    widget.resize(640, 480)
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None
    geom = overlay.geometry()
    assert geom.width() > 0 and geom.height() > 0
    cursor = QTextCursor(widget.document())
    cursor.setPosition(6)
    line = cursor.block().layout().lineForTextPosition(6)
    offset = widget.contentOffset()
    rightPoint = cast("tuple[float, float]", line.cursorToX(9))
    wordRight = round(rightPoint[0] + offset.x())
    wordTop = round(line.rect().top() + offset.y())
    # QRect.right() is inclusive; the exclusive right edge is +1.
    assert geom.right() + 1 == wordRight  # right edge anchored to the word
    assert geom.top() == wordTop
    assert geom.left() >= 0
    assert geom.bottom() <= widget.viewport().height()


# ******************************************************************************
def testDeactivatesWhenCursorLeaves(app: QApplication) -> None:
    """Leaving the word hides the overlay; the document is untouched."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _moveCursor(widget, 1)  # off the word, into "hello"
    assert not overlay.isVisible()
    assert widget.toPlainText() == "hello خوش world دوست"


# ******************************************************************************
def testRomanKeystrokeInterceptedInSpan(app: QApplication) -> None:
    """A roman keystroke inside a RomanUrdu span seeds the overlay, not the doc."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 10)  # word plus trailing space
    _moveCursor(widget, 9)  # the space inside the span (a non-word position)
    _assertNoOverlay(widget)
    _sendKey(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "k"
    assert widget.toPlainText() == "hello خوش world"  # the char was not inserted


# ******************************************************************************
def testLatinKeystrokeNotIntercepted(app: QApplication) -> None:
    """Outside a RomanUrdu span (or feature off), roman keys type normally."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    widget.setRomanInputEnabled(True)
    _moveCursor(widget, 0)
    _sendKey(widget, Qt.Key.Key_K, "k")
    assert widget.toPlainText() == "khello world"
    _assertNoOverlay(widget)

    widget2 = PyRaya()
    widget2.show()
    widget2.setPlainText("hello خوش world")
    widget2.setRomanInputEnabled(False)
    widget2.setRegionType(RegionType.RomanUrdu, 6, 11)  # word plus trailing space
    _moveCursor(widget2, 9)  # the space inside the span
    _sendKey(widget2, Qt.Key.Key_K, "k")
    assert widget2.toPlainText() == "hello خوشk world"
    _assertNoOverlay(widget2)
    # punctuation is never intercepted, even inside the span with feature on
    widget2.setRomanInputEnabled(True)
    _moveCursor(widget2, 10)  # the space inside the span, after the "k"
    _sendKey(widget2, Qt.Key.Key_Comma, ",")
    assert widget2.toPlainText() == "hello خوشk, world"
    _assertNoOverlay(widget2)


# ******************************************************************************
def testReactivationAfterCommit(app: QApplication) -> None:
    """Once the overlay deactivates, the next roman keystroke re-activates it."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 10)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    # simulate the post-commit state: cursor inside the span, no active word
    _moveCursor(widget, 9)
    _assertNoOverlay(widget)
    _sendKey(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "k"
    assert widget.toPlainText() == "hello خوش world"

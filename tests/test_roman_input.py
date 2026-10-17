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
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QKeyEvent,
    QPixmap,
    QTextCursor,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget
from romanalfaz import DictionaryNotFoundError
from romanalfaz.engine import Suggestion, Vocabulary

from pyraya import PyRaya
from pyraya.regions import RegionType
from pyraya.roman_input import (
    RomanInputEngine,
    RomanOverlay,
    SuggestionList,
    _SuggestionRow,
)

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
class _StubEngine(RomanInputEngine):
    """An engine offering a fixed number of suggestions for the scroll tests."""

    def __init__(self, count: int) -> None:
        super().__init__()
        self._count = count

    def suggestTiers(self, romanWord: str) -> list[tuple[Suggestion, int]]:
        return [
            (Suggestion(arabic=f"word{i}", encodedRoman=f"word{i}", frequency=i), 0)
            for i in range(self._count)
        ]


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
    """Left at the start / Right at the end commit without a separator.

    The roman text renders in left-to-right character order, so the text
    start is the visually left edge and the text end the visually right
    edge; in-text Left/Right move the cursor visually left/right and never
    commit.
    """
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khosh")
    captured: list[tuple[str, Suggestion | None, bool, str]] = []
    overlay.committed.connect(
        lambda roman, selected, placeholder, separator: captured.append(
            (roman, selected, placeholder, separator),
        ),
    )

    lineEdit = overlay.lineEdit()
    # In-text movement: one position visually left, then one back right.
    lineEdit.setCursorPosition(3)
    _sendKey(lineEdit, Qt.Key.Key_Left)
    assert lineEdit.cursorPosition() == 2
    _sendKey(lineEdit, Qt.Key.Key_Right)
    assert lineEdit.cursorPosition() == 3
    assert captured == []

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
def testSuggestionListCappedSizeHint(app: QApplication) -> None:
    """The list's size hint caps at the visible-row limit, not the row count."""
    overlay, _ = _makeOverlay(app, _StubEngine(12))
    overlay.setText("x")
    suggestionList = overlay.suggestionList()
    assert suggestionList.rowCount() == 12
    rowHeight = QFontMetrics(overlay.font()).height() + 6
    assert suggestionList.sizeHint().height() == 5 * rowHeight


# ******************************************************************************
def _stubRows() -> list[_SuggestionRow]:
    """Two stub rows of different widths for the sizing and paint tests."""
    return [
        _SuggestionRow(
            Suggestion(arabic="word", encodedRoman="word", frequency=0),
            "word",
            0,
            False,
        ),
        _SuggestionRow(
            Suggestion(arabic="wordlonger", encodedRoman="wordlonger", frequency=1),
            "wordlonger",
            1,
            False,
        ),
    ]


# ******************************************************************************
def testSuggestionListSizeHintIncludesDefaultMargin(app: QApplication) -> None:
    """The hint width covers the widest row plus the default margin on both sides."""
    overlay, _ = _makeOverlay(app, _StubEngine(3))
    overlay.setText("x")
    suggestionList = overlay.suggestionList()
    metrics = QFontMetrics(overlay.font())
    widest = max(metrics.horizontalAdvance(f"word{i}") for i in range(3))
    assert suggestionList.sizeHint().width() == widest + 2 * 6


# ******************************************************************************
def testSuggestionListSizeHintWithCustomMargin(app: QApplication) -> None:
    """The hint width adds the configurable margin to both sides of the widest row."""
    font = QFont()
    listWidget = SuggestionList(font, margin=12)
    rows = _stubRows()
    listWidget.setRows(rows)
    metrics = QFontMetrics(font)
    widest = max(metrics.horizontalAdvance(row.arabic) for row in rows)
    assert listWidget.sizeHint().width() == widest + 24


# ******************************************************************************
def testSuggestionListTextStaysInsideMargin(app: QApplication) -> None:
    """At the hint width, the right-aligned text never crosses the left edge."""
    font = QFont()
    listWidget = SuggestionList(font)
    listWidget.setRows(_stubRows())
    hint = listWidget.sizeHint()
    listWidget.resize(hint.width(), hint.height())
    pixmap = QPixmap(hint.width(), hint.height())
    pixmap.fill(Qt.GlobalColor.white)
    listWidget.render(pixmap)
    image = pixmap.toImage()
    for x in range(6):  # default margin
        for y in range(hint.height()):
            assert image.pixelColor(x, y) != QColor(0, 0, 0)


# ******************************************************************************
def _inkSpan(image: QImage, width: int, yStart: int, yEnd: int) -> tuple[int | None, int | None]:
    """The topmost and bottommost dark pixels (text ink) inside a row band.

    The tier tints and placeholder borders stay above the darkness
    threshold, so only the black text ink is measured.
    """
    top: int | None = None
    bottom: int | None = None
    for y in range(yStart, yEnd):
        for x in range(width):
            color = image.pixelColor(x, y)
            if min(color.red(), color.green(), color.blue()) < 200:
                top = y if top is None else top
                bottom = y
    return top, bottom


# ******************************************************************************
def testSuggestionListTextVerticallyCenteredInRows(
    app: QApplication, engine: RomanInputEngine
) -> None:
    """Each unselected row draws its Arabic-script text centered in its band.

    The text ink must not spill past the row's top edge into the row above,
    nor past the bottom edge into the row below: each word stays inside its
    own row instead of being pushed up into the one above.
    """
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khos")  # six distance-1 suggestions
    suggestionList = overlay.suggestionList()
    assert suggestionList.rowCount() >= 3
    rowHeight = QFontMetrics(overlay.font()).height() + 6
    hint = suggestionList.sizeHint()
    suggestionList.resize(hint.width(), hint.height())
    pixmap = QPixmap(hint.width(), hint.height())
    pixmap.fill(Qt.GlobalColor.white)
    suggestionList.render(pixmap)
    image = pixmap.toImage()
    visible = min(suggestionList.rowCount(), suggestionList.visibleRowCount())
    for row in range(1, visible):  # row 0 carries the selected-row accent
        top, bottom = _inkSpan(image, hint.width(), row * rowHeight, (row + 1) * rowHeight)
        assert top is not None and bottom is not None
        assert top >= row * rowHeight + 2  # not pushed into the row above
        assert bottom <= (row + 1) * rowHeight - 2  # not pushed into the row below


# ******************************************************************************
def testSelectKeepsSelectedRowVisible(app: QApplication) -> None:
    """select keeps the highlighted row inside the visible window."""
    overlay, _ = _makeOverlay(app, _StubEngine(12))
    overlay.setText("x")
    suggestionList = overlay.suggestionList()
    for index in range(suggestionList.rowCount()):
        suggestionList.select(index)
        first = suggestionList.firstRow()
        assert first <= index < first + suggestionList.visibleRowCount()
    # the last row is pinned to the bottom of the window
    assert suggestionList.firstRow() == (
        suggestionList.rowCount() - suggestionList.visibleRowCount()
    )
    suggestionList.select(0)
    assert suggestionList.firstRow() == 0


# ******************************************************************************
def testMoveSelectionWrapsAndScrollsBackToTop(app: QApplication) -> None:
    """Wraparound navigation scrolls the list back to the top row."""
    overlay, _ = _makeOverlay(app, _StubEngine(12))
    overlay.setText("x")
    suggestionList = overlay.suggestionList()
    suggestionList.select(suggestionList.rowCount() - 1)
    overlay.moveSelection(1)
    assert suggestionList.selectedIndex() == 0
    assert suggestionList.firstRow() == 0


# ******************************************************************************
def testResizeKeepsSelectedRowVisible(app: QApplication) -> None:
    """Resizing the list re-clamps the scroll so the selected row stays visible."""
    overlay, _ = _makeOverlay(app, _StubEngine(12))
    overlay.setText("x")
    suggestionList = overlay.suggestionList()
    suggestionList.select(suggestionList.rowCount() - 1)
    rowHeight = QFontMetrics(overlay.font()).height() + 6
    suggestionList.resize(suggestionList.width(), 2 * rowHeight)
    index = suggestionList.selectedIndex()
    first = suggestionList.firstRow()
    assert first <= index < first + suggestionList.visibleRowCount()
    assert suggestionList.firstRow() == suggestionList.rowCount() - 2


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
def testRomanInputFeatureOnByDefault(app: QApplication) -> None:
    """The feature is on by default; the first keystroke on a fresh widget
    seeds the overlay and never reaches the document."""
    widget = PyRaya()
    widget.show()
    assert widget.isRomanInputEnabled() is True
    _sendKey(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "k"
    assert widget.toPlainText() == ""
    assert widget.textCursor().position() == 0


# ******************************************************************************
def testFirstKeystrokeOnEmptyDocumentSeedsOverlay(app: QApplication) -> None:
    """The first keystroke on an empty document seeds the overlay; the letter
    never reaches the document."""
    widget = PyRaya()
    widget.show()
    _sendKey(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "k"
    assert widget.toPlainText() == ""
    assert widget.textCursor().position() == 0


# ******************************************************************************
def testKeystrokeAtEndOfUntaggedDocumentSeedsOverlay(app: QApplication) -> None:
    """Typing at the end of a non-empty untagged document seeds the overlay."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello")
    widget.setRomanInputEnabled(True)
    _moveCursor(widget, 5)  # the document end
    _sendKey(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "k"
    assert widget.toPlainText() == "hello"  # the char was not inserted
    assert widget.textCursor().position() == 5


# ******************************************************************************
def testKeystrokeAtEndAfterLatinRegionNotIntercepted(app: QApplication) -> None:
    """Typing at the end with the last character in a Latin region does not
    seed the overlay; the key types into the document."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.Latin, 6, 11)
    _moveCursor(widget, 11)  # the document end, after the Latin region
    _sendKey(widget, Qt.Key.Key_K, "k")
    assert widget.toPlainText() == "hello worldk"
    _assertNoOverlay(widget)


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
    widget.setRegionType(RegionType.Latin, 6, 8)  # only part of the word
    _moveCursor(widget, 7)
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
def testOverlayStaysPinnedWhileEditing(app: QApplication) -> None:
    """The overlay and its line edit keep their activation geometry while the
    suggestion list's height changes during editing.

    The overlay is sized once at activation; typing, backspacing, and emptying
    the text change the list's row count and visibility (many rows, one row,
    hidden). Neither the overlay nor its line edit may move: the line edit
    stays pinned to the top of the overlay regardless of the list height.
    """
    widget = PyRaya()
    widget.resize(800, 600)
    widget.show()
    widget.setPlainText("hello خوش ")
    widget.setRegionType(RegionType.RomanUrdu, 0, 10)
    _moveCursor(widget, 9)  # a bare cursor in a RomanUrdu region
    _sendKey(widget, Qt.Key.Key_D, "d")  # seeds the overlay; several rows
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    line = overlay.lineEdit()
    app.processEvents()
    overlayGeom = overlay.geometry()
    lineGeom = line.geometry()
    steps = (
        (Qt.Key.Key_O, "o"),
        (Qt.Key.Key_S, "s"),
        (Qt.Key.Key_T, "t"),
        (Qt.Key.Key_Backspace, ""),
        (Qt.Key.Key_Backspace, ""),
        (Qt.Key.Key_Backspace, ""),
        (Qt.Key.Key_Backspace, ""),  # back to the empty text
    )
    for key, text in steps:
        _sendKey(line, key, text)
        app.processEvents()
        assert overlay.geometry() == overlayGeom
        assert line.geometry() == lineGeom


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
    widget.setRegionType(RegionType.Latin, 0, 11)
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


# ******************************************************************************
def testScenario2ReplacementCommit(app: QApplication) -> None:
    """Committing over an existing word replaces the span; one undo reverts it."""
    widget = PyRaya()
    widget.show()
    original = "hello خوش world"
    widget.setPlainText(original)
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()

    committed: list[tuple[str, str]] = []
    widget.romanWordCommitted.connect(lambda w, r: committed.append((w, r)))
    baseline = widget.document().availableUndoSteps()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    # the top suggestion for "khosh" is the exact word خوش; the span is
    # replaced by the word plus the separator (the surrounding space stays)
    assert widget.toPlainText() == "hello خوش  world"
    assert committed == [("خوش", "khosh")]
    assert not overlay.isVisible()
    # the word span is still RomanUrdu
    assert widget._regionKindAt(6) == RegionType.RomanUrdu
    assert widget._regionKindAt(8) == RegionType.RomanUrdu
    # the span replacement is counted as two undo steps (delete + insert),
    # but a single undo reverts the whole commit to the original text
    assert widget.document().availableUndoSteps() == baseline + 2
    widget.undo()
    assert widget.toPlainText() == original
    assert widget.document().availableUndoSteps() == baseline
    # redoing takes the tag step and the commit step, no ping-pong
    widget.redo()
    widget.redo()
    assert widget.toPlainText() == "hello خوش  world"
    assert widget.document().isUndoAvailable()


# ******************************************************************************
def testSeparatorCommits(app: QApplication) -> None:
    """Space, Enter, and typed punctuation commit the word plus separator."""

    def setup() -> tuple[PyRaya, RomanOverlay]:
        widget = PyRaya()
        widget.show()
        widget.setPlainText("hello خوش world")
        widget.setRomanInputEnabled(True)
        widget.setRegionType(RegionType.RomanUrdu, 6, 9)
        _moveCursor(widget, 7)
        overlay = widget._overlay
        assert overlay is not None and overlay.isVisible()
        return widget, overlay

    # Space
    widget, overlay = setup()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert widget.toPlainText() == "hello خوش  world"
    assert widget.textCursor().position() == 10  # cursor after the separator
    assert widget._regionKindAt(9) == RegionType.RomanUrdu  # separator colored
    assert not overlay.isVisible()

    # Enter
    widget, overlay = setup()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Return, "\n")
    assert widget.toPlainText() == "hello خوش\n world"
    assert widget.textCursor().position() == 10
    # a block-terminator character cannot carry a character format, so the
    # newline stays untagged; the committed word characters are RomanUrdu
    assert widget._regionKindAt(8) == RegionType.RomanUrdu
    assert not overlay.isVisible()

    # Comma
    widget, overlay = setup()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Comma, ",")
    assert widget.toPlainText() == "hello خوش, world"
    assert widget.textCursor().position() == 10
    assert widget._regionKindAt(9) == RegionType.RomanUrdu
    assert not overlay.isVisible()


# ******************************************************************************
def testEdgeCommits(app: QApplication) -> None:
    """Edge commits insert nothing and jump in visual (screen) order.

    Right at the overlay's visually right edge (the text end) commits to the
    previous word; Left at its visually left edge (the text start) commits to
    the next word. With no adjacent word, the overlay hides and the cursor
    lands at the word's visually left edge.
    """
    widget = PyRaya()
    widget.show()
    text = "hello خوش world دوست"
    widget.setPlainText(text)
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 20)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"
    assert overlay.lineEdit().cursorPosition() == 5  # at the word's right edge

    # Right at the visually right edge: no word before خوش -> the overlay
    # hides and the cursor lands at the word's visually left edge (9).
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Right, "")
    assert widget.toPlainText() == text  # nothing inserted
    assert widget.textCursor().position() == 9
    _assertNoOverlay(widget)

    # Holding Left walks visually leftward through the Latin word and the
    # space, then into دوست, where the overlay activates.
    for _ in range(7):
        _sendKey(widget, Qt.Key.Key_Left, "")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "dost"

    # Continuing Left traverses the roman word and overflows at the visually
    # left edge; no next word exists, so the overlay hides at the line's
    # visually left edge (position 20).
    for _ in range(5):
        _sendKey(overlay.lineEdit(), Qt.Key.Key_Left, "")
    assert widget.toPlainText() == text
    assert widget.textCursor().position() == 20
    _assertNoOverlay(widget)

    # Mirror: Right from دوست reaches خوش, then Right at its visually right
    # edge hides the overlay at position 9.
    widget3 = PyRaya()
    widget3.show()
    widget3.setPlainText(text)
    widget3.setRomanInputEnabled(True)
    widget3.setRegionType(RegionType.RomanUrdu, 6, 20)
    _moveCursor(widget3, 17)
    overlay3 = widget3._overlay
    assert overlay3 is not None and overlay3.isVisible()
    assert overlay3.lineEdit().text() == "dost"
    _sendKey(overlay3.lineEdit(), Qt.Key.Key_Right, "")
    overlay3 = widget3._overlay
    assert overlay3 is not None and overlay3.isVisible()
    assert overlay3.lineEdit().text() == "khosh"
    _sendKey(overlay3.lineEdit(), Qt.Key.Key_Right, "")
    assert widget3.toPlainText() == text
    assert widget3.textCursor().position() == 9
    _assertNoOverlay(widget3)

    # A single-word document: Left from the visually right edge overflows
    # with no next word -> the overlay hides at the visually left edge.
    widget2 = PyRaya()
    widget2.show()
    widget2.setPlainText("world خوش")
    widget2.setRomanInputEnabled(True)
    widget2.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget2, 7)
    overlay2 = widget2._overlay
    assert overlay2 is not None and overlay2.isVisible()
    for _ in range(5):
        _sendKey(overlay2.lineEdit(), Qt.Key.Key_Left, "")
    assert overlay2.lineEdit().cursorPosition() == 0
    _sendKey(overlay2.lineEdit(), Qt.Key.Key_Left, "")
    assert widget2.toPlainText() == "world خوش"
    assert widget2.textCursor().position() == 9
    _assertNoOverlay(widget2)


# ******************************************************************************
def testDocumentVisualArrowKeys(app: QApplication) -> None:
    """Plain Left/Right move the document cursor in visual (screen) order."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(False)
    _moveCursor(widget, 7)
    _sendKey(widget, Qt.Key.Key_Left, "")
    assert widget.textCursor().position() == 8  # visually left
    _sendKey(widget, Qt.Key.Key_Right, "")
    assert widget.textCursor().position() == 7  # visually right
    _moveCursor(widget, 0)
    _sendKey(widget, Qt.Key.Key_Right, "")
    assert widget.textCursor().position() == 0  # clamped at the start
    _moveCursor(widget, 20)
    _sendKey(widget, Qt.Key.Key_Left, "")
    assert widget.textCursor().position() == 20  # clamped at the end


# ******************************************************************************
def testEmptyTextCommitDeletesSpan(app: QApplication) -> None:
    """An empty overlay text deletes the span and emits regionsChanged."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    overlay.setText("")  # clear the overlay text

    changed = []
    widget.regionsChanged.connect(lambda: changed.append(1))
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    # span deleted, the separator takes its place (the surrounding spaces stay)
    assert widget.toPlainText() == "hello   world"
    assert changed == [1]  # regionsChanged emitted for the span-deleting commit
    assert widget.textCursor().position() == 7  # cursor after the separator
    _assertNoOverlay(widget)

    # a normal (non-empty) text-replacing commit does not emit regionsChanged
    widget2 = PyRaya()
    widget2.show()
    widget2.setPlainText("hello خوش world")
    widget2.setRomanInputEnabled(True)
    widget2.setRegionType(RegionType.RomanUrdu, 6, 9)
    changed2 = []
    widget2.regionsChanged.connect(lambda: changed2.append(1))
    _moveCursor(widget2, 7)
    overlay2 = widget2._overlay
    assert overlay2 is not None and overlay2.isVisible()
    _sendKey(overlay2.lineEdit(), Qt.Key.Key_Space, " ")
    assert widget2.toPlainText() == "hello خوش  world"
    assert changed2 == []


# ******************************************************************************
def testEmptyDocumentScenario1Commit(app: QApplication) -> None:
    """A scenario-1 commit on an empty document inserts at position zero."""
    widget = PyRaya()
    widget.show()
    committed: list[tuple[str, str]] = []
    changed: list[int] = []
    widget.romanWordCommitted.connect(lambda w, r: committed.append((w, r)))
    widget.regionsChanged.connect(lambda: changed.append(1))
    baseline = widget.document().availableUndoSteps()
    _sendKey(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    row = overlay.suggestionList().selectedRow()
    assert row is not None
    suggestion = row.suggestion
    assert suggestion is not None
    word = suggestion.arabic
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert widget.toPlainText() == word + " "
    assert committed == [(word, "k")]
    assert changed == []
    assert not widget.textCursor().hasSelection()
    assert widget.textCursor().position() == len(word) + 1
    assert widget._regionKindAt(0) == RegionType.RomanUrdu
    assert widget._regionKindAt(len(word)) == RegionType.RomanUrdu  # separator
    _assertNoOverlay(widget)
    assert widget.document().availableUndoSteps() == baseline + 1
    widget.undo()
    assert widget.toPlainText() == ""
    assert widget.document().availableUndoSteps() == baseline
    widget.redo()
    assert widget.toPlainText() == word + " "
    assert widget.document().isUndoAvailable()


# ******************************************************************************
def testPlaceholderCommitScenario1And2(app: QApplication) -> None:
    """Committing the placeholder learns and commits the typed roman word."""
    # scenario 1: typed at the cursor inside the span
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 10)
    committed: list[tuple[str, str]] = []
    widget.romanWordCommitted.connect(lambda w, r: committed.append((w, r)))
    _moveCursor(widget, 9)  # the space inside the span
    _sendKey(widget, Qt.Key.Key_X, "x")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    overlay.setText("xqwzrty")  # zero matches -> placeholder row
    row = overlay.suggestionList().selectedRow()
    assert row is not None and row.isPlaceholder
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert widget.toPlainText() == "hello خوشxqwzrty  world"
    assert committed == [("xqwzrty", "xqwzrty")]
    assert widget.textCursor().position() == 17
    _assertNoOverlay(widget)
    # localDictionary is unchanged (learnRomanWord is a no-op this session)
    assert list(widget.localDictionary().counter) == []

    # scenario 2: the span is replaced by the learned word
    widget2 = PyRaya()
    widget2.show()
    widget2.setPlainText("hello خوش world")
    widget2.setRomanInputEnabled(True)
    widget2.setRegionType(RegionType.RomanUrdu, 6, 9)
    committed2: list[tuple[str, str]] = []
    widget2.romanWordCommitted.connect(lambda w, r: committed2.append((w, r)))
    _moveCursor(widget2, 7)
    overlay2 = widget2._overlay
    assert overlay2 is not None and overlay2.isVisible()
    overlay2.setText("xqwzrty")  # zero matches -> placeholder row
    row2 = overlay2.suggestionList().selectedRow()
    assert row2 is not None and row2.isPlaceholder
    _sendKey(overlay2.lineEdit(), Qt.Key.Key_Space, " ")
    assert widget2.toPlainText() == "hello xqwzrty  world"
    assert committed2 == [("xqwzrty", "xqwzrty")]
    _assertNoOverlay(widget2)


# ******************************************************************************
def testUnavailableEngineCommitIsNoOp(app: QApplication) -> None:
    """With an unavailable engine, committing does not touch the document."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    engine = widget.romanEngine()
    assert engine is not None
    engine.available = False  # simulate DictionaryNotFoundError
    committed: list[tuple[str, str]] = []
    widget.romanWordCommitted.connect(lambda w, r: committed.append((w, r)))
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.suggestionList().rowCount() == 0  # no rows, no placeholder
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert widget.toPlainText() == "hello خوش world"
    assert committed == []
    _assertNoOverlay(widget)


# ******************************************************************************
def testUpAndDownSelectionThenCommit(app: QApplication) -> None:
    """Up/Down moves the selection, and the committed word follows it."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    overlay.setText("khos")  # six distance-1 suggestions
    first = overlay.suggestionList().selectedRow()
    assert first is not None
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Down, "")
    second = overlay.suggestionList().selectedRow()
    assert second is not None
    assert second.arabic != first.arabic
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert widget.toPlainText() == "hello " + second.arabic + "  world"
    _assertNoOverlay(widget)

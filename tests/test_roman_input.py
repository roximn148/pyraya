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
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QKeyEvent,
    QMouseEvent,
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
    _LIST_BORDER,
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
def _sendKey(
    widget: QWidget,
    key: int,
    text: str = "",
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    """Send a key-press event to a widget."""
    QCoreApplication.sendEvent(
        widget,
        QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text),
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
def testSuggestionListRendersOpaquePanel(
    app: QApplication,
) -> None:
    """The list paints an opaque panel with a border and rounded corners.

    Rendered onto a dark fill distinct from the panel base: if the
    backing were still translucent, the tier tints would composite with
    that fill instead of with the opaque base, and the rounded corners
    would let the fill through at the widget's corners.
    """
    font = QFont()
    listWidget = SuggestionList(font)
    listWidget.setRows(_stubRows())
    hint = listWidget.sizeHint()
    listWidget.resize(hint.width(), hint.height())
    behind = QColor(0x30, 0x60, 0xA0)
    pixmap = QPixmap(hint.width(), hint.height())
    pixmap.fill(behind)
    listWidget.render(pixmap)
    image = pixmap.toImage()
    rowHeight = QFontMetrics(font).height() + 6

    # A text-free point inside row 1 (tier 1, unselected): the text is
    # right-aligned and the margin keeps the left margin columns clear.
    color = image.pixelColor(3, rowHeight + rowHeight // 2)
    # The tier-1 tint (alpha 30) over the opaque white base; a translucent
    # backing would composite with the dark fill behind and read
    # (70, 101, 144) instead.
    assert abs(color.red() - 252) <= 12
    assert abs(color.green() - 241) <= 12
    assert abs(color.blue() - 228) <= 12

    # The panel border along the left edge and along the top edge past
    # the corner radius.
    border = _LIST_BORDER
    left = image.pixelColor(0, hint.height() // 2)
    assert abs(left.red() - border.red()) <= 3
    assert abs(left.green() - border.green()) <= 3
    assert abs(left.blue() - border.blue()) <= 3
    top = image.pixelColor(10, 0)
    assert abs(top.red() - border.red()) <= 3
    assert abs(top.green() - border.green()) <= 3
    assert abs(top.blue() - border.blue()) <= 3

    # Rounded corner: the widget's own corner is transparent, so the
    # fill behind shows through untouched.
    corner = image.pixelColor(0, 0)
    assert abs(corner.red() - behind.red()) <= 3
    assert abs(corner.green() - behind.green()) <= 3
    assert abs(corner.blue() - behind.blue()) <= 3


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
def _sendMouse(
    widget: PyRaya,
    kind: str,
    x: int,
    y: int,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    """Send a synthesized mouse event at viewport coordinates (x, y).

    The event is hit-tested to the topmost widget at the global point —
    the document viewport, since the overlay is mouse-transparent — so the
    widget's own mouse handlers (press ownership, release resync) run
    exactly as for a real mouse.

    Args:
        widget: The host widget the coordinates refer to.
        kind: One of "press", "move", "release", or "dbclick".
        x: The x coordinate in viewport coordinates.
        y: The y coordinate in viewport coordinates.
        modifiers: The keyboard modifiers carried by the event.
    """
    globalPos = widget.viewport().mapToGlobal(QPoint(x, y))
    top = QApplication.widgetAt(globalPos.x(), globalPos.y())
    assert top is not None
    local = top.mapFromGlobal(globalPos)
    if kind == "move":
        etype = QEvent.Type.MouseMove
        button = Qt.MouseButton.NoButton
    else:
        etype = {
            "press": QEvent.Type.MouseButtonPress,
            "release": QEvent.Type.MouseButtonRelease,
            "dbclick": QEvent.Type.MouseButtonDblClick,
        }[kind]
        button = Qt.MouseButton.LeftButton
    QCoreApplication.sendEvent(
        top,
        QMouseEvent(
            etype,
            QPointF(local.x(), local.y()),
            button,
            Qt.MouseButton.LeftButton,
            modifiers,
        ),
    )


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
def testTypingInSecondParagraphAfterEnterCommit(app: QApplication) -> None:
    """Typing in the second paragraph after an Enter commit does not crash.

    The Enter commit moves the cursor into the second block, so the seeded
    overlay's anchor — and every subsequent keystroke — resolves line
    geometry in that block's own layout. ``lineForTextPosition`` and
    ``cursorToX`` take block-local positions; the absolute position overflowed
    the block's layout (a non-None invalid line whose calls segfaulted), and
    the anchor's top must include the block's content-coordinates origin.
    """
    widget = PyRaya()
    widget.resize(640, 480)
    widget.show()
    _sendKey(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    for key, letter in ((Qt.Key.Key_O, "o"), (Qt.Key.Key_S, "s"), (Qt.Key.Key_T, "t")):
        _sendKey(overlay.lineEdit(), key, letter)
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Return, "\n")
    assert widget.toPlainText() == "دوست\n"
    # paragraph 2: typing seeds the overlay in the second block
    _sendKey(widget, Qt.Key.Key_H, "h")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "h"
    assert widget.toPlainText() == "دوست\n"  # the character never written
    # the seeded anchor sits on the second block's line, at Qt's own top
    cursor = QTextCursor(widget.document())
    cursor.setPosition(5)
    assert overlay.geometry().top() == widget._cursorAnchor(5)[1]
    assert widget._cursorAnchor(5)[1] == widget.cursorRect(cursor).top()
    for key, letter in ((Qt.Key.Key_O, "o"), (Qt.Key.Key_S, "s")):
        _sendKey(overlay.lineEdit(), key, letter)
    assert overlay.lineEdit().text() == "hos"
    assert widget.toPlainText() == "دوست\n"


# ******************************************************************************
def testWordRectInSecondBlock(app: QApplication) -> None:
    """The word rect and the overlay anchor resolve in the second block.

    The word rect is computed from block-local positions translated by the
    block's content-coordinates origin; both it and the cursor anchor must
    agree with Qt's own cursor-rectangle mapping (viewport coordinates) for
    words past block 0, and a mouse release over the word re-activates the
    overlay over it (scenario 2) with the line edit's text romanized.
    """
    widget = PyRaya()
    widget.resize(640, 480)
    widget.show()
    widget.setPlainText("دوست\nمنتظم")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 5, 10)
    _moveCursor(widget, 6)  # inside the block-1 word: activates the overlay
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    wordRect = widget._wordRect(5, 10)
    assert overlay.geometry().top() == wordRect.top()
    # cross-check against Qt's own cursor geometry (viewport coordinates)
    cursorStart = QTextCursor(widget.document())
    cursorStart.setPosition(5)
    cursorEnd = QTextCursor(widget.document())
    cursorEnd.setPosition(10)
    assert wordRect.top() == widget.cursorRect(cursorStart).top()
    assert wordRect.left() == widget.cursorRect(cursorEnd).left()
    # QRect.right() is inclusive; the exclusive right edge is +1.
    assert wordRect.right() + 1 == widget.cursorRect(cursorStart).left()
    # mouse release over the block-1 word re-activates (scenario 2)
    point = (wordRect.right(), wordRect.top() + 5)
    _sendMouse(widget, "press", point[0], point[1])
    _sendMouse(widget, "release", point[0], point[1])
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    engine = widget.romanEngine()
    assert engine is not None
    assert overlay.lineEdit().text() == engine.romanizeArabic("منتظم")


# ******************************************************************************
def testOverlayWidthFitsContentAtActivation(app: QApplication) -> None:
    """At activation the overlay covers the word and the typed text only.

    The line edit's size hint is the typed text's advance plus margin per
    side, not the generic ``QLineEdit`` default width, and the overlay's
    width is the wider of that content size and the word's rect width, so a
    short word does not stretch the overlay across the document.
    """
    widget = PyRaya()
    widget.resize(640, 480)
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None
    metrics = overlay.lineEdit().fontMetrics()
    lineHint = metrics.horizontalAdvance(overlay.lineEdit().text()) + 2 * 6
    assert overlay.lineEdit().sizeHint().width() == lineHint
    expected = max(overlay.sizeHint().width(), widget._wordRect(6, 9).width())
    assert overlay.geometry().width() == expected


# ******************************************************************************
def testOverlayGrowsLeftwardWhileTyping(app: QApplication) -> None:
    """Typing grows the overlay leftward; the right edge and top stay pinned.

    Each typed character widens the overlay to the new content size — the
    wider of the line edit's text advance plus margin, the suggestion
    list's hint, and the word's width — so the left edge walks leftward with
    the text while the right edge stays on the word's right edge.
    """
    widget = PyRaya()
    widget.resize(800, 600)
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    floor = widget._wordRect(6, 9).width()
    right = overlay.geometry().right()
    top = overlay.geometry().top()
    for key, char in ((Qt.Key.Key_H, "h"), (Qt.Key.Key_T, "t")):
        _sendKey(overlay.lineEdit(), key, char)
        app.processEvents()
        metrics = overlay.lineEdit().fontMetrics()
        lineHint = metrics.horizontalAdvance(overlay.lineEdit().text()) + 2 * 6
        listHint = overlay.suggestionList().sizeHint().width()
        expected = max(lineHint, listHint, floor)
        geom = overlay.geometry()
        assert geom.right() == right
        assert geom.top() == top
        assert geom.width() == expected


# ******************************************************************************
def testSeededOverlayBaselinesAtFourRomanChars(app: QApplication) -> None:
    """A seeded overlay (no pre-existing word) baselines at four roman chars.

    With no word to cover, the width floor is the advance of four roman
    characters, so backspacing the seeded text to empty leaves the overlay
    at the baseline width rather than collapsing to the line edit's margin.
    """
    widget = PyRaya()
    widget.resize(800, 600)
    widget.show()
    widget.setPlainText("hello world ")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 12)
    _moveCursor(widget, 11)
    _sendKey(widget, Qt.Key.Key_D, "d")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    line = overlay.lineEdit()
    app.processEvents()
    baseline = 4 * line.fontMetrics().averageCharWidth()
    right = overlay.geometry().right()
    top = overlay.geometry().top()
    _sendKey(line, Qt.Key.Key_Backspace, "")
    app.processEvents()
    geom = overlay.geometry()
    assert geom.width() == baseline
    assert geom.right() == right
    assert geom.top() == top


# ******************************************************************************
def testOverlayStaysPinnedWhileEditing(app: QApplication) -> None:
    """The overlay's right edge and top stay pinned while its text changes.

    Typing, backspacing, and emptying the text change the line edit's content
    width, so the overlay's width tracks the text at each keystroke: the left
    edge walks leftward as the text grows and back as it shrinks, never below
    the activation floor, while the right edge stays on the anchor and the top
    stays put.
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
    baseline = 4 * line.fontMetrics().averageCharWidth()
    right = overlay.geometry().right()
    top = overlay.geometry().top()
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
        geom = overlay.geometry()
        assert geom.right() == right
        assert geom.top() == top
        assert geom.width() == max(overlay.sizeHint().width(), baseline)


# ******************************************************************************
def testOverlayReanchorsOnResize(app: QApplication) -> None:
    """Resizing the widget reflows the document; the overlay follows the word.

    The overlay is placed in viewport coordinates at activation, and a
    resize moves the right-aligned word without a cursor move or document
    edit, so the resize handler must re-place the overlay from the stored
    anchor: the right edge stays on the reflowed word's exclusive right
    edge and the top follows the line.
    """
    widget = PyRaya()
    widget.resize(640, 480)
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    app.processEvents()
    widget.resize(300, 480)
    app.processEvents()
    assert overlay.isVisible()
    wordRect = widget._wordRect(6, 9)
    geom = overlay.geometry()
    assert geom.right() == wordRect.right()  # right edge anchored to the word
    assert geom.top() == wordRect.top()
    assert geom.left() >= 0
    assert geom.bottom() <= widget.viewport().height()


# ******************************************************************************
def testSeededOverlayReanchorsOnResize(app: QApplication) -> None:
    """A seeded overlay survives a resize: re-anchored, typed text preserved.

    The seeded overlay has no word to cover, so the resize handler must
    only re-place it from the stored anchor — not re-evaluate activation,
    which would deactivate the overlay or clobber the typed text.
    """
    widget = PyRaya()
    widget.resize(800, 600)
    widget.show()
    widget.setPlainText("hello world ")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 12)
    _moveCursor(widget, 11)
    _sendKey(widget, Qt.Key.Key_D, "d")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    app.processEvents()
    widget.resize(400, 600)
    app.processEvents()
    assert overlay.isVisible()
    assert overlay.lineEdit().text() == "d"  # typed text preserved
    anchor = widget._anchorPosition
    assert anchor is not None
    rightX, top = widget._cursorAnchor(anchor)
    geom = overlay.geometry()
    assert geom.right() + 1 == rightX  # right edge anchored to the cursor
    assert geom.top() == top
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
def testScenario1CommitReplacesSelection(app: QApplication) -> None:
    """A scenario-1 commit over a selection replaces it, plain typing
    semantics: the committed word plus the separator take its place."""
    widget = PyRaya()
    widget.show()
    original = "hello world"
    widget.setPlainText(original)
    widget.setRomanInputEnabled(True)
    cursor = widget.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)  # select "world"
    widget.setTextCursor(cursor)
    committed: list[tuple[str, str]] = []
    changed: list[int] = []
    widget.romanWordCommitted.connect(lambda w, r: committed.append((w, r)))
    widget.regionsChanged.connect(lambda: changed.append(1))
    baseline = widget.document().availableUndoSteps()
    _sendKey(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "k"
    assert widget.textCursor().hasSelection()  # the selection stays visible
    row = overlay.suggestionList().selectedRow()
    assert row is not None
    suggestion = row.suggestion
    assert suggestion is not None
    word = suggestion.arabic
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert widget.toPlainText() == "hello " + word + " "
    assert committed == [(word, "k")]
    assert changed == []
    assert not widget.textCursor().hasSelection()
    assert widget.textCursor().position() == 6 + len(word) + 1
    assert widget._regionKindAt(6) == RegionType.RomanUrdu
    assert widget._regionKindAt(6 + len(word) - 1) == RegionType.RomanUrdu
    assert widget._regionKindAt(6 + len(word)) == RegionType.RomanUrdu  # separator
    _assertNoOverlay(widget)
    # the selection replacement is counted as two undo steps (delete +
    # insert), but a single undo reverts the whole commit
    assert widget.document().availableUndoSteps() == baseline + 2
    widget.undo()
    assert widget.toPlainText() == original
    assert widget.document().availableUndoSteps() == baseline
    widget.redo()
    widget.redo()
    assert widget.toPlainText() == "hello " + word + " "
    assert widget.document().isUndoAvailable()

    # Enter commits the word plus the newline over the same selection
    widget2 = PyRaya()
    widget2.show()
    widget2.setPlainText(original)
    widget2.setRomanInputEnabled(True)
    cursor2 = widget2.textCursor()
    cursor2.setPosition(6)
    cursor2.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
    widget2.setTextCursor(cursor2)
    _sendKey(widget2, Qt.Key.Key_K, "k")
    overlay2 = widget2._overlay
    assert overlay2 is not None and overlay2.isVisible()
    row2 = overlay2.suggestionList().selectedRow()
    assert row2 is not None
    suggestion2 = row2.suggestion
    assert suggestion2 is not None
    word2 = suggestion2.arabic
    _sendKey(overlay2.lineEdit(), Qt.Key.Key_Return, "\n")
    # a block-terminator character cannot carry a character format, so the
    # newline stays untagged; the committed word characters are RomanUrdu
    assert widget2.toPlainText() == "hello " + word2 + "\n"
    assert not widget2.textCursor().hasSelection()
    assert widget2.textCursor().position() == 6 + len(word2) + 1
    assert widget2._regionKindAt(6) == RegionType.RomanUrdu
    assert widget2._regionKindAt(6 + len(word2) - 1) == RegionType.RomanUrdu
    _assertNoOverlay(widget2)


# ******************************************************************************
def testOverlayIsMouseTransparent(app: QApplication, engine: RomanInputEngine) -> None:
    """Both the overlay container and its line edit are mouse-transparent."""
    overlay, _ = _makeOverlay(app, engine)
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert overlay.lineEdit().testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


# ******************************************************************************
def testPressDeactivatesAndReleaseReactivatesOverlay(app: QApplication) -> None:
    """A press in the document takes ownership and hides the overlay; the
    release resyncs, re-activating it on the word with focus in the line edit.

    The press point is one pixel inside the word's exclusive right edge
    (``_wordRect``'s ``right()``), which lands the cursor inside the word.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(600, 200)
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()

    rect = widget._wordRect(6, 9)
    _sendMouse(widget, "press", rect.right(), rect.center().y())
    assert not widget._overlayActive()  # the press took ownership
    assert widget._mouseActive
    assert 6 <= widget.textCursor().position() < 9
    assert not widget.textCursor().hasSelection()

    _sendMouse(widget, "release", rect.right(), rect.center().y())
    app.processEvents()
    assert not widget._mouseActive
    assert widget._overlayActive()  # the release resync re-activated it
    assert widget._activeWord == (6, 9)
    assert overlay.lineEdit().hasFocus()
    assert not widget.hasFocus()
    assert overlay.lineEdit().text() == "khosh"


# ******************************************************************************
def testDragAcrossWordCreatesSelection(app: QApplication) -> None:
    """A press-drag-release across the word selects exactly the word."""
    widget = PyRaya()
    widget.show()
    widget.resize(600, 200)
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()

    rect = widget._wordRect(6, 9)
    _sendMouse(widget, "press", rect.right(), rect.center().y())
    for x in (rect.right() - 3, rect.center().x()):
        _sendMouse(widget, "move", x, rect.center().y())
    _sendMouse(widget, "release", rect.left() + 1, rect.center().y())
    cursor = widget.textCursor()
    assert cursor.hasSelection()
    assert (cursor.selectionStart(), cursor.selectionEnd()) == (6, 9)
    # The cursor settled on the word's trailing space, so no overlay.
    assert not widget._overlayActive()
    assert not widget._mouseActive


# ******************************************************************************
def testShiftDragExtendsSelection(app: QApplication) -> None:
    """A shift+drag from the cursor extends the selection to the release point."""
    widget = PyRaya()
    widget.show()
    widget.resize(600, 200)
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()

    rect = widget._wordRect(6, 9)
    shift = Qt.KeyboardModifier.ShiftModifier
    _sendMouse(widget, "press", rect.right() - 1, rect.center().y(), shift)
    for x in (rect.right() - 3, rect.center().x()):
        _sendMouse(widget, "move", x, rect.center().y(), shift)
    _sendMouse(widget, "release", rect.left() + 1, rect.center().y(), shift)
    cursor = widget.textCursor()
    assert cursor.hasSelection()
    # The shift press anchored the original cursor position (7); the drag
    # extended the selection to the release point (the word's end).
    assert (cursor.selectionStart(), cursor.selectionEnd()) == (7, 9)
    assert not widget._overlayActive()
    assert not widget._mouseActive


# ******************************************************************************
def testDoubleClickSelectsWord(app: QApplication) -> None:
    """A double click on the word selects the whole word."""
    widget = PyRaya()
    widget.show()
    widget.resize(600, 200)
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()

    rect = widget._wordRect(6, 9)
    _sendMouse(widget, "press", rect.right(), rect.center().y())
    _sendMouse(widget, "release", rect.right(), rect.center().y())
    _sendMouse(widget, "dbclick", rect.right(), rect.center().y())
    _sendMouse(widget, "release", rect.right(), rect.center().y())
    cursor = widget.textCursor()
    assert cursor.hasSelection()
    assert cursor.selectionStart() == 6
    assert cursor.selectionEnd() >= 9


# ******************************************************************************
def testSyncOverlaySuppressedWhileMouseActive(app: QApplication) -> None:
    """A cursor move while the mouse flag is set leaves the overlay untouched;
    clearing the flag and moving again lets the resync hide it.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(600, 200)
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert widget._activeWord == (6, 9)
    app.processEvents()

    widget._mouseActive = True
    _moveCursor(widget, 1)
    assert widget._activeWord == (6, 9)
    assert overlay.isVisible()
    assert overlay.lineEdit().hasFocus()

    widget._mouseActive = False
    _moveCursor(widget, 3)
    assert not widget._overlayActive()
    assert widget._activeWord is None


# ******************************************************************************
def testPostCommitResyncBypassesMouseFlag(app: QApplication) -> None:
    """The post-commit resync runs even while the mouse flag is set.

    A press at the word's edge would leave ``_mouseActive`` set until the
    release; the commit's resync must still reconcile the overlay, so it
    bypasses the flag.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(600, 200)
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"

    widget._mouseActive = True
    overlay.lineEdit().setCursorPosition(0)
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Left, "Left")
    # the edge commit moved the cursor to the next word; the resync ran
    # despite the mouse flag and re-activated the overlay on that word
    assert widget._activeWord == (16, 20)
    assert overlay.lineEdit().text() == "dost"
    assert widget.textCursor().position() == 16
    assert widget._mouseActive
    assert widget.toPlainText() == "hello خوش world دوست"


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

    Activation places the line edit cursor at the position corresponding to
    the document cursor, so arrow keys move in visual order and edge commits
    fire only at the actual edges: Right at the overlay's visually right edge
    (the text end) commits to the previous word, and Left at its visually left
    edge (the text start) commits to the next word. With no adjacent word, the
    overlay hides and the cursor lands at the word's visually left edge.
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
    # The document cursor sits inside the word (after its first character),
    # so the line edit cursor is placed at the corresponding interior
    # position, not at the text end.
    assert overlay.lineEdit().cursorPosition() == 1

    # Walking Right reaches the visually right edge (the text end), where the
    # next Right edge-commits: no Arabic word before خوش -> the overlay hides
    # and the cursor lands at the word's visually left edge (9).
    for _ in range(4):
        _sendKey(overlay.lineEdit(), Qt.Key.Key_Right, "")
    assert overlay.lineEdit().cursorPosition() == 5
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
    # The document cursor lands at the word's start, so the line edit cursor
    # is placed at the text start (the visually left edge).
    assert overlay.lineEdit().cursorPosition() == 0

    # Left at the visually left edge overflows immediately; no next word
    # exists, so the overlay hides at the line's visually left edge
    # (position 20).
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Left, "")
    assert widget.textCursor().position() == 20
    _assertNoOverlay(widget)

    # Mirror: Right from دوست walks to its visually right edge, then
    # edge-commits to خوش, whose visually right edge is reached and
    # edge-committed again with no previous word -> the overlay hides at 9.
    widget3 = PyRaya()
    widget3.show()
    widget3.setPlainText(text)
    widget3.setRomanInputEnabled(True)
    widget3.setRegionType(RegionType.RomanUrdu, 6, 20)
    _moveCursor(widget3, 17)
    overlay3 = widget3._overlay
    assert overlay3 is not None and overlay3.isVisible()
    assert overlay3.lineEdit().text() == "dost"
    assert overlay3.lineEdit().cursorPosition() == 1
    # Walk to the visually right edge (the text end).
    for _ in range(3):
        _sendKey(overlay3.lineEdit(), Qt.Key.Key_Right, "")
    assert overlay3.lineEdit().cursorPosition() == 4
    # Right at the end edge-commits to the previous word (خوش), whose line
    # edit cursor is placed at the text start.
    _sendKey(overlay3.lineEdit(), Qt.Key.Key_Right, "")
    overlay3 = widget3._overlay
    assert overlay3 is not None and overlay3.isVisible()
    assert overlay3.lineEdit().text() == "khosh"
    assert overlay3.lineEdit().cursorPosition() == 0
    # Walk to the end again; Right edge-commits with no previous word, so the
    # overlay hides at the word's visually left edge (9).
    for _ in range(5):
        _sendKey(overlay3.lineEdit(), Qt.Key.Key_Right, "")
    assert overlay3.lineEdit().cursorPosition() == 5
    _sendKey(overlay3.lineEdit(), Qt.Key.Key_Right, "")
    assert widget3.toPlainText() == text
    assert widget3.textCursor().position() == 9
    _assertNoOverlay(widget3)

    # A single-word document: Left from the interior reaches the visually
    # left edge, where the next Left overflows with no next word -> the
    # overlay hides at the word's visually left edge.
    widget2 = PyRaya()
    widget2.show()
    widget2.setPlainText("world خوش")
    widget2.setRomanInputEnabled(True)
    widget2.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget2, 7)
    overlay2 = widget2._overlay
    assert overlay2 is not None and overlay2.isVisible()
    assert overlay2.lineEdit().text() == "khosh"
    assert overlay2.lineEdit().cursorPosition() == 1
    # Walk to the visually left edge (the text start).
    _sendKey(overlay2.lineEdit(), Qt.Key.Key_Left, "")
    assert overlay2.lineEdit().cursorPosition() == 0
    # Left at the start overflows with no next word -> the overlay hides at
    # the word's visually left edge (9).
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


# ******************************************************************************
def testAssistModeOnByDefault(app: QApplication) -> None:
    """Assist mode is on by default, like the roman-input feature itself."""
    widget = PyRaya()
    assert widget.isAssistEnabled() is True


# ******************************************************************************
def testEscOnActiveOverlayTurnsAssistModeOff(app: QApplication) -> None:
    """Esc on the active overlay dismisses it and turns assist mode off."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is False
    _assertNoOverlay(widget)


# ******************************************************************************
def testTypingReachesDocumentWhenAssistModeOff(app: QApplication) -> None:
    """With assist mode off, a roman keystroke types into the document and
    does not seed the overlay."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is False
    _sendKey(widget, Qt.Key.Key_K, "k")
    assert widget.toPlainText() == "hello خkوش world دوست"
    assert widget.textCursor().position() == 8
    _assertNoOverlay(widget)


# ******************************************************************************
def testMouseReleaseDoesNotReactivateWhenAssistModeOff(app: QApplication) -> None:
    """With assist mode off, a press and release over a word do not
    activate the overlay."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is False
    rect = widget._wordRect(6, 9)
    _sendMouse(widget, "press", rect.right(), rect.center().y())
    _assertNoOverlay(widget)
    _sendMouse(widget, "release", rect.right(), rect.center().y())
    _assertNoOverlay(widget)


# ******************************************************************************
def testCtrlSpaceOnWordReentersAssistMode(app: QApplication) -> None:
    """Ctrl+Space over a word turns assist mode back on and activates the
    overlay over the word; the key never reaches the document."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is False
    _sendKey(
        widget,
        Qt.Key.Key_Space,
        "\u00a0",
        Qt.KeyboardModifier.ControlModifier,
    )
    assert widget.isAssistEnabled() is True
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"
    assert widget.toPlainText() == "hello خوش world دوست"


# ******************************************************************************
def testCtrlSpaceWithoutWordShowsEmptyOverlay(app: QApplication) -> None:
    """Ctrl+Space with no word under the cursor shows an empty overlay at
    the cursor; the key never reaches the document."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    _moveCursor(widget, 1)
    _sendKey(
        widget,
        Qt.Key.Key_Space,
        "\u00a0",
        Qt.KeyboardModifier.ControlModifier,
    )
    app.processEvents()
    assert widget.isAssistEnabled() is True
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == ""
    assert overlay.lineEdit().hasFocus()
    assert widget.toPlainText() == "hello world"


# ******************************************************************************
def testCommitLeavesAssistModeOn(app: QApplication) -> None:
    """Committing leaves assist mode on: only Esc on the overlay turns it off."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    _assertNoOverlay(widget)
    assert widget.isAssistEnabled() is True


# ******************************************************************************
def testEscInDocumentDoesNotFlipAssistMode(app: QApplication) -> None:
    """Esc in the document (overlay inactive) never flips assist mode."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    _moveCursor(widget, 1)
    _sendKey(widget, Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is True
    _assertNoOverlay(widget)

    widget.setPlainText("hello خوش world دوست")
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is False
    _sendKey(widget, Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is False


# ******************************************************************************
def testSetAssistEnabledTogglesOverlay(app: QApplication) -> None:
    """setAssistEnabled(False) hides a shown overlay; setAssistEnabled(True)
    only marks the mode ready and does not show the overlay."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    widget.setAssistEnabled(False)
    assert widget.isAssistEnabled() is False
    _assertNoOverlay(widget)
    widget.setAssistEnabled(True)
    assert widget.isAssistEnabled() is True
    _assertNoOverlay(widget)


# ******************************************************************************
def testReEnablingFeatureResetsAssistMode(app: QApplication) -> None:
    """Re-enabling the roman-input feature resets assist mode to on."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is False
    widget.setRomanInputEnabled(False)
    widget.setRomanInputEnabled(True)
    assert widget.isAssistEnabled() is True

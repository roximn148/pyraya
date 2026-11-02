# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the roman-input overlay subsystem.

Runs headless via the offscreen Qt platform so no window is opened.
"""

import os
from collections.abc import Generator
from pathlib import Path
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
from romanalfaz.algorithm import tafseerUrduAr2Rm
from romanalfaz.engine import Suggestion, Vocabulary

from pyraya import PyRaya
from pyraya.regions import RegionType, TextRegion
from pyraya.roman_input import (
    RomanInputEngine,
    RomanOverlay,
    SuggestionList,
    _DefaultVocabulary,
    _ListBorder,
    _sharedEngine,
    _SuggestionRow,
)

# Verified zero-match roman strings (no suggestions at distance 0..2).
ZERO_MATCH_WORDS = ["xqwzrty", "qzxvr", "kzqwxv", "zxqvw", "zxrqvz"]


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
def testLearnRomanWordRaisesWithoutAttachedVocabulary(engine: RomanInputEngine) -> None:
    """learnRomanWord raises AssertionError without an attached Vocabulary."""
    for word in ZERO_MATCH_WORDS:
        with pytest.raises(AssertionError):
            engine.learnRomanWord(word)
    with pytest.raises(AssertionError):
        engine.learnRomanWord("")


# ******************************************************************************
def testEngineUnavailable(monkeypatch) -> None:
    """A DictionaryNotFoundError yields an unavailable, non-crashing engine."""

    class _Missing:
        def __init__(self, vocabularies=None) -> None:
            raise DictionaryNotFoundError("missing")

    monkeypatch.setattr("pyraya.roman_input.RomanAlfaz", _Missing)
    engine = RomanInputEngine()
    assert engine.available is False
    assert engine.suggest("khosh") == []
    assert engine.suggestTiers("khosh") == []
    with pytest.raises(AssertionError):
        engine.learnRomanWord("xqwzrty")


# ******************************************************************************
def testDefaultWordlistIsQamoos() -> None:
    """The engine's default Vocabulary is the package's qamoos wordlist.

    qamoos.sym is passed as a starter vocabulary, so RomanAlfaz's bundled
    UrduWords5k.sym fallback is skipped: exactly one Vocabulary is
    attached, and it is qamoos's — whose top word leads an exact lookup.
    """
    engine = RomanInputEngine()
    assert engine.available is True
    alfaz = engine._alfaz
    assert alfaz is not None
    assert len(alfaz.vocabularies) == 1
    assert alfaz.vocabularies[0].counter == Vocabulary.load(str(_DefaultVocabulary)).counter
    assert engine.hasWord("کے")
    assert engine.suggest("ke")[0].arabic == "کے"


# ******************************************************************************
def testEngineUnavailableOnMissingDefaultWordlist(monkeypatch) -> None:
    """A missing qamoos.sym yields an unavailable, non-crashing engine."""
    monkeypatch.setattr("pyraya.roman_input._DefaultVocabulary", Path("nonexistent.sym"))
    engine = RomanInputEngine()
    assert engine.available is False
    assert engine.suggest("khosh") == []


# ******************************************************************************
def testAddVocabularyAttached(app: QApplication) -> None:
    """The local vocabulary is attached alongside the default wordlist."""
    local = Vocabulary()
    engine = RomanInputEngine(local)
    assert engine.available is True
    assert engine.suggest("khosh")[0].arabic == "خوش"


# ******************************************************************************
def _longArabicWord() -> tuple[str, int]:
    """A mappable Arabic word whose roman form exceeds the bundled max.

    Takes qamoos' longest word (12 roman chars) and appends two 'ba'
    consonants (each encoding to 'B'), yielding a 14-char roman form.
    """
    longest_ar, longest_roman = "", 0
    with open(_DefaultVocabulary, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            w = line.split("$")[0]
            enc, undef = tafseerUrduAr2Rm(w)
            if undef == 0 and len(enc) > longest_roman:
                longest_roman, longest_ar = len(enc), w
    extended = longest_ar + "\u0628\u0628"
    enc, undef = tafseerUrduAr2Rm(extended)
    assert undef == 0
    return extended, len(enc)


# ******************************************************************************
def testMaxInputLengthBundledIndex(engine: RomanInputEngine) -> None:
    """maxInputLength is the bundled index's longest word plus depth plus margin.

    qamoos' longest roman word is 12 chars; with distance 2 and the margin of
    2, the cap is 16. The stat is pinned alongside the cap so a change to
    qamoos.sym fails here (the dictionary) rather than at the cap (the
    formula), keeping the coupling to the bundled wordlist explicit.
    """
    alfaz = engine._alfaz
    assert alfaz is not None
    assert alfaz.maxRomanWordLength == 12  # pin the bundled max
    assert engine.maxInputLength == 16


# ******************************************************************************
def testMaxInputLengthTracksHostVocabulary() -> None:
    """The cap tracks the collective vocabulary live, with no re-creation.

    A learned word longer than the bundled max raises the cap in place; the
    cap is read fresh from the engine's stat, so it never goes stale.
    """
    word, romanLen = _longArabicWord()
    assert romanLen > 12
    host = Vocabulary()
    engine = RomanInputEngine(host)
    assert engine.maxInputLength == 16  # host empty -> qamoos' 12
    host.add(word)  # live mutation -> recompile -> cap updates in place
    assert engine.maxInputLength == romanLen + 2 + 2


# ******************************************************************************
def testMaxInputLengthReplaceVocabularyRecomputes() -> None:
    """replaceVocabulary discards the engine; the new engine's cap is fresh.

    The shared holder swaps the Vocabulary and drops the cached engine, so
    the next engine() call re-creates it on the new Vocabulary and its cap
    reflects that Vocabulary.
    """
    word, romanLen = _longArabicWord()
    engine = _sharedEngine.engine()
    assert engine.maxInputLength == 16  # shared Vocabulary empty -> qamoos' 12
    newVocab = Vocabulary()
    newVocab.add(word)
    _sharedEngine.replaceVocabulary(newVocab)
    fresh = _sharedEngine.engine()
    assert fresh is not engine  # a new engine instance
    assert fresh.maxInputLength == romanLen + 2 + 2


# ******************************************************************************
def testMaxInputLengthUnavailable(monkeypatch) -> None:
    """An unavailable engine's maxInputLength is distance plus margin."""

    class _Missing:
        def __init__(self, vocabularies=None) -> None:
            raise DictionaryNotFoundError("missing")

    monkeypatch.setattr("pyraya.roman_input.RomanAlfaz", _Missing)
    engine = RomanInputEngine()
    assert engine.maxInputLength == 4  # distance 2 + margin 2


# ******************************************************************************
def testSuggestTiersTruncatesToCap(engine: RomanInputEngine, monkeypatch) -> None:
    """A word past the cap is searched as its cap-length prefix."""
    captured: list[str] = []
    alfaz = engine._alfaz
    assert alfaz is not None
    realSuggest = alfaz.suggest

    def spy(
        romanWord: str,
        distance: int,
        maxPredictions: int | None,
    ) -> tuple[list[Suggestion], list[Suggestion], list[Suggestion]]:
        captured.append(romanWord)
        return realSuggest(romanWord, distance=distance, maxPredictions=maxPredictions)

    monkeypatch.setattr(alfaz, "suggest", spy)
    cap = engine.maxInputLength
    word = "khosh" + "x" * (cap + 1 - len("khosh"))
    assert len(word) == cap + 1
    engine.suggestTiers(word)
    assert captured == [word[:cap]]


# ******************************************************************************
def testOverlayCommitsFullWord(app: QApplication, engine: RomanInputEngine) -> None:
    """The cap is internal: a word past the cap commits in full, untruncated."""
    overlay, _ = _makeOverlay(app, engine)
    longWord = "khosh" + "x" * 12  # 17 chars, past the bundled cap of 16
    assert len(longWord) == 17
    captured: list[tuple[str, object, int, str, int]] = []
    overlay.committed.connect(
        lambda roman, selected, key, keyText, modifiers: captured.append(
            (roman, selected, key, keyText, modifiers),
        ),
    )
    overlay.lineEdit().setCursorPosition(0)
    overlay.setText(longWord)
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Return, "\n")
    assert len(captured) == 1
    roman, selected, key, keyText, modifiers = captured[0]
    assert roman == longWord  # the full word, not its cap-length prefix
    assert key == Qt.Key.Key_Return


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
    captured: list[tuple[str, object, int, str, int]] = []
    overlay.committed.connect(
        lambda roman, selected, key, keyText, modifiers: captured.append(
            (roman, selected, key, keyText, modifiers),
        ),
    )

    lineEdit = overlay.lineEdit()
    _sendKey(lineEdit, Qt.Key.Key_Space, " ")
    assert len(captured) == 1
    roman, selected, key, keyText, modifiers = captured[0]
    assert roman == "khosh"
    assert key == Qt.Key.Key_Space
    assert keyText == " "
    assert modifiers == Qt.KeyboardModifier.NoModifier.value
    assert isinstance(selected, Suggestion) and selected.arabic == "خوش"

    captured.clear()
    _sendKey(lineEdit, Qt.Key.Key_Return, "\n")
    assert len(captured) == 1
    roman, selected, key, keyText, modifiers = captured[0]
    # Enter's keyText is platform-dependent, so assert the key and modifiers.
    assert key == Qt.Key.Key_Return
    assert modifiers == Qt.KeyboardModifier.NoModifier.value

    captured.clear()
    _sendKey(lineEdit, Qt.Key.Key_Comma, ",")
    assert len(captured) == 1
    roman, selected, key, keyText, modifiers = captured[0]
    assert key == Qt.Key.Key_Comma
    assert keyText == ","
    assert modifiers == Qt.KeyboardModifier.NoModifier.value


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
    captured: list[tuple[str, object, int, str, int]] = []
    overlay.committed.connect(
        lambda roman, selected, key, keyText, modifiers: captured.append(
            (roman, selected, key, keyText, modifiers),
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
    roman, selected, key, keyText, modifiers = captured[0]
    assert key == Qt.Key.Key_Left
    assert keyText == ""
    assert modifiers == Qt.KeyboardModifier.NoModifier.value

    lineEdit.setCursorPosition(len("khosh"))
    _sendKey(lineEdit, Qt.Key.Key_Right)
    assert len(captured) == 2
    roman, selected, key, keyText, modifiers = captured[1]
    assert key == Qt.Key.Key_Right
    assert keyText == ""
    assert modifiers == Qt.KeyboardModifier.NoModifier.value


# ******************************************************************************
def testOverlayEscCancels(app: QApplication, engine: RomanInputEngine) -> None:
    """Esc emits canceled with the key's modifiers and never commits."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khosh")
    committed = []
    overlay.committed.connect(lambda *args: committed.append(args))
    canceled: list[int] = []
    overlay.canceled.connect(lambda modifiers: canceled.append(modifiers))

    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert canceled == [Qt.KeyboardModifier.NoModifier.value]
    assert committed == []

    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
    assert canceled == [
        Qt.KeyboardModifier.NoModifier.value,
        Qt.KeyboardModifier.ControlModifier.value,
    ]
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
def testInTextCursorKeysKeepTheSelection(app: QApplication) -> None:
    """In-text cursor keys keep the highlighted row and the typed text.

    A cursor-only key (an in-text Left / Right / Home) must not rebuild
    the suggestion rows: every rebuild re-runs the fuzzy search and
    resets the highlighted suggestion to the top row.
    """
    overlay, _ = _makeOverlay(app, _StubEngine(12))
    overlay.setText("kalam")
    suggestionList = overlay.suggestionList()
    suggestionList.select(2)
    lineEdit = overlay.lineEdit()

    _sendKey(lineEdit, Qt.Key.Key_Left, "")
    assert suggestionList.selectedIndex() == 2
    assert lineEdit.text() == "kalam"

    _sendKey(lineEdit, Qt.Key.Key_Home, "")
    assert suggestionList.selectedIndex() == 2

    _sendKey(lineEdit, Qt.Key.Key_End, "")
    assert suggestionList.selectedIndex() == 2


# ******************************************************************************
class _TierThreeEngine(RomanInputEngine):
    """An engine whose only suggestion sits in the deep tier 3."""

    def __init__(self) -> None:
        self._localVocabulary = None
        self._distance = 3
        self._maxPredictions = 5
        self._maxSuggestions = 10
        self._alfaz = None
        self.available = True

    def suggestTiers(self, romanWord: str) -> list[tuple[Suggestion, int]]:
        return [(Suggestion(arabic="کلم", encodedRoman=romanWord, frequency=1), 3)]


# ******************************************************************************
def testDeepTierSuggestionClampsToThePalette(app: QApplication) -> None:
    """A suggestion from a deep tier renders with the deepest palette tint.

    The suggestion list's palette stops at distance 2 while the engine's
    ``distance`` parameter accepts deeper tiers; the row's tier is clamped
    at build time so the paint never asks the palette for a missing tint.
    """
    overlay, _ = _makeOverlay(app, _TierThreeEngine())
    overlay.setText("kam")
    suggestionList = overlay.suggestionList()
    row = suggestionList.selectedRow()
    assert row is not None
    assert row.tier == 2
    suggestionList.grab()  # exercises the paint event


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
        ),
        _SuggestionRow(
            Suggestion(arabic="wordlonger", encodedRoman="wordlonger", frequency=1),
            "wordlonger",
            1,
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

    The tier tints and undefined-word borders stay above the darkness
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
    border = _ListBorder
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
    """Empty overlay text shows no rows and no undefined-word row."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("")
    suggestionList = overlay.suggestionList()
    assert suggestionList.rowCount() == 0
    assert suggestionList.selectedSuggestion() is None


# ******************************************************************************
def testOverlayZeroMatchesShowsUndefinedWord(
    app: QApplication,
    engine: RomanInputEngine,
) -> None:
    """A non-empty typed word with zero matches shows the undefined-word (Learn) row."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText(ZERO_MATCH_WORDS[0])
    suggestionList = overlay.suggestionList()
    assert suggestionList.rowCount() == 1
    row = suggestionList.selectedRow()
    assert row is not None and row.suggestion.isUndefined()
    assert suggestionList.selectedSuggestion() == Suggestion("", ZERO_MATCH_WORDS[0], 0)
    assert suggestionList.isUndefinedWordSelected() is True

    captured: list[tuple[str, object, int, str, int]] = []
    overlay.committed.connect(
        lambda roman, selected, key, keyText, modifiers: captured.append(
            (roman, selected, key, keyText, modifiers),
        ),
    )
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert len(captured) == 1
    roman, selected, key, keyText, modifiers = captured[0]
    assert roman == ZERO_MATCH_WORDS[0]
    assert selected == Suggestion("", ZERO_MATCH_WORDS[0], 0)
    assert isinstance(selected, Suggestion) and selected.isUndefined()
    assert key == Qt.Key.Key_Space
    assert keyText == " "
    assert modifiers == Qt.KeyboardModifier.NoModifier.value


# ******************************************************************************
def testOverlayFuzzyNoExactAppendsLearnRow(
    app: QApplication,
    engine: RomanInputEngine,
) -> None:
    """A typed word with fuzzy matches but no exact match appends a Learn row.

    The undefined-word row is offered whenever there is no exact (tier-0)
    match, appended after any fuzzy-match rows, and its label is the
    bracketed typed roman.
    """
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khos")  # fuzzy matches, no exact match
    suggestionList = overlay.suggestionList()
    fuzzyCount = len(engine.suggestTiers("khos"))
    assert suggestionList.rowCount() == fuzzyCount + 1  # fuzzy rows + Learn row
    suggestionList.select(suggestionList.rowCount() - 1)
    row = suggestionList.selectedRow()
    assert row is not None and row.suggestion.isUndefined()
    assert row.arabic == "+ [khos]"


# ******************************************************************************
def testOverlayLearnRowElidesLongInput(app: QApplication, engine: RomanInputEngine) -> None:
    """The undefined-word row elides typed input above 8 characters.

    A 9-character word displays its first and last 4 characters with
    ``..`` between, capping the label at 14 Latin characters; an
    8-character word displays in full. Display-only: the row's suggestion
    carries the full typed roman, so a commit writes the complete word.
    """
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("abcdefghi")
    suggestionList = overlay.suggestionList()
    suggestionList.select(suggestionList.rowCount() - 1)
    row = suggestionList.selectedRow()
    assert row is not None and row.suggestion.isUndefined()
    assert row.arabic == "+ [abcd..fghi]"
    assert row.suggestion.encodedRoman == "abcdefghi"

    overlay.setText("abcdefgh")
    suggestionList = overlay.suggestionList()
    suggestionList.select(suggestionList.rowCount() - 1)
    row = suggestionList.selectedRow()
    assert row is not None and row.suggestion.isUndefined()
    assert row.arabic == "+ [abcdefgh]"


# ******************************************************************************
def testOverlayUnavailableOffersNothing(app: QApplication, monkeypatch) -> None:
    """An unavailable engine offers no rows, no undefined-word row, and no crash."""

    class _Missing:
        def __init__(self, vocabularies=None) -> None:
            raise DictionaryNotFoundError("missing")

    monkeypatch.setattr("pyraya.roman_input.RomanAlfaz", _Missing)
    engine = RomanInputEngine()
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khosh")
    suggestionList = overlay.suggestionList()
    assert suggestionList.rowCount() == 0
    assert suggestionList.isUndefinedWordSelected() is False

    captured: list[tuple[str, object, int, str, int]] = []
    overlay.committed.connect(
        lambda roman, selected, key, keyText, modifiers: captured.append(
            (roman, selected, key, keyText, modifiers),
        ),
    )
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert len(captured) == 1
    roman, selected, key, keyText, modifiers = captured[0]
    assert roman == "khosh"
    assert selected is None
    assert key == Qt.Key.Key_Space
    assert keyText == " "
    assert modifiers == Qt.KeyboardModifier.NoModifier.value


# ******************************************************************************
def testOverlayRefreshesOnEdit(app: QApplication, engine: RomanInputEngine) -> None:
    """Typing in the overlay edits the roman text and refreshes synchronously."""
    overlay, _ = _makeOverlay(app, engine)
    overlay.setText("khosh")
    lineEdit = overlay.lineEdit()
    _sendKey(lineEdit, Qt.Key.Key_B, "b")
    assert lineEdit.text() == "khoshb"
    tiers = engine.suggestTiers("khoshb")
    noExact = not any(t == 0 for _, t in tiers)
    expected = len(tiers) + (1 if noExact else 0)
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
def testEdgeCommitFromMidRunSeedLandsOnTheRunEdge(app: QApplication) -> None:
    """An edge commit from a seed anchored inside a run lands on its facing edge.

    The ASCII typing gate is region-kind-only, so an untagged cursor
    inside an Arabic word seeds a scenario-1 overlay with the anchor
    mid-run (the review ruling on B2 — the walk returns the containing
    run of the found character). The edge commit follows the
    adjacent-word convention instead of the old stay-put half-run
    landing: the cursor rests on the containing run's edge facing the
    walk direction, and the resync re-activates the overlay over that
    same word (a run's edge position is over the word).
    """
    widget = PyRaya()
    widget.show()
    widget.setPlainText("سلام علیکم")  # سلام 0..4, علیکم 5..10
    widget.setRomanInputEnabled(True)
    _moveCursor(widget, 1)  # inside سلام — this activates the overlay over it
    # Deactivate (a user-style decision that moves nothing) so the gate
    # can seed: the cursor rests mid-run with no overlay.
    widget._deactivateOverlay()
    _assertNoOverlay(widget)
    _sendKey(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "k"
    assert widget.textCursor().position() == 1  # the seed's anchor, mid-run
    # Right at the text end edge-commits: backwards from the mid-run
    # anchor the walk finds سلام's start character and lands on the run's
    # facing edge (its end, 4); the resync re-activates over سلام.
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Right, "")
    assert widget.toPlainText() == "سلام علیکم"  # nothing written
    assert widget.textCursor().position() == 4
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "slam"
    # Left from the same seed shapes the mirror landing: the walk finds
    # the run's end character and lands on its facing edge (the run's
    # start).
    widget2 = PyRaya()
    widget2.show()
    widget2.setPlainText("سلام علیکم")
    widget2.setRomanInputEnabled(True)
    _moveCursor(widget2, 1)
    widget2._deactivateOverlay()
    _assertNoOverlay(widget2)
    _sendKey(widget2, Qt.Key.Key_K, "k")
    overlay2 = widget2._overlay
    assert overlay2 is not None and overlay2.isVisible()
    assert overlay2.lineEdit().text() == "k"
    # Left walks to the text start, then the next Left edge-commits:
    # forwards from the mid-run anchor the walk finds سلام's end
    # character and lands on the run's facing edge (its start, 0); the
    # resync re-activates overسلام.
    _sendKey(overlay2.lineEdit(), Qt.Key.Key_Left, "")
    assert overlay2.lineEdit().cursorPosition() == 0
    _sendKey(overlay2.lineEdit(), Qt.Key.Key_Left, "")
    assert widget2.textCursor().position() == 0
    overlay2 = widget2._overlay
    assert overlay2 is not None and overlay2.isVisible()
    assert overlay2.lineEdit().text() == "slam"


# ******************************************************************************
def testKeystrokeAtEndAfterLatinRegionNotIntercepted(app: QApplication) -> None:
    """Typing at the end with the last character in a Latin region does not
    seed the overlay; the key types into the document."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.Native, 6, 11)
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
    widget.setRegionType(RegionType.Native, 6, 9)
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
    widget.setRegionType(RegionType.Native, 6, 8)  # only part of the word
    _moveCursor(widget, 7)
    _assertNoOverlay(widget)


# ******************************************************************************
def testWordEndActivatesOverlay(app: QApplication) -> None:
    """A cursor at a word's end is over the word and activates the overlay.

    The containment includes the run's end: a cursor after the word's last
    character — mid-document, or at the trailing terminator — activates the
    overlay over the word, with the line edit cursor mirror-mapped to the
    text start; a cursor with no word run behind it does not activate.
    """
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 9)  # the word end, before the space
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"
    assert overlay.lineEdit().cursorPosition() == 0  # mirror-mapped to the text start
    # the trailing terminator position: the last word's end
    widget.setPlainText("hello خوش")
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 9)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"
    _moveCursor(widget, 0)  # no word run behind the cursor
    _assertNoOverlay(widget)


# ******************************************************************************
def testOverlayStaysActiveAtWordEnd(app: QApplication) -> None:
    """Walking to the word end keeps the overlay active; leaving the word hides it."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _moveCursor(widget, 8)  # still inside
    assert overlay.isVisible()
    _moveCursor(widget, 9)  # the word end: still over the word, no re-activation
    assert overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"
    _moveCursor(widget, 10)  # past the word
    _assertNoOverlay(widget)


# ******************************************************************************
def testMouseReleaseAtWordEndReactivates(app: QApplication) -> None:
    """A mouse release at the word end re-activates the overlay (scenario 2).

    A release at the word's visually left edge lands the cursor at the word
    end, which is over the word, so the release resync re-activates the
    overlay with the romanized word.
    """
    widget = PyRaya()
    widget.resize(640, 480)
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    wordRect = widget._wordRect(6, 9)
    point = (wordRect.left() + 1, wordRect.top() + 5)  # one pixel inside the left edge
    _sendMouse(widget, "press", point[0], point[1])
    _sendMouse(widget, "release", point[0], point[1])
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    engine = widget.romanEngine()
    assert engine is not None
    assert overlay.lineEdit().text() == engine.romanizeArabic("خوش")


# ******************************************************************************
def testCtrlSpaceAtWordEndActivatesOverlay(app: QApplication) -> None:
    """Ctrl+Space at the word end activates the overlay over the word."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 9)  # the word end: the cursor move activates the overlay
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )  # dismiss it (assist mode off)
    _assertNoOverlay(widget)
    _sendKey(widget, Qt.Key.Key_Space, " ", Qt.KeyboardModifier.ControlModifier)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"  # the word, not an empty seed


# ******************************************************************************
def testDocumentKeystrokeSyncsOverlayOnce(app: QApplication) -> None:
    """One keystroke that edits the document runs the overlay sync once.

    Typing into the document fires both ``contentsChanged`` and the
    widget-level ``cursorPositionChanged``; both funnel into
    ``_syncOverlay``, which coalesces them to one word lookup when the
    cursor position and the document revision are unchanged between the
    two signals — while a real cursor move still syncs.
    """
    widget = PyRaya()
    widget.show()
    widget.setPlainText("سلام علیکم")
    widget.romanEngine()  # warm the dictionary outside the measurement
    cursor = widget.textCursor()
    cursor.setPosition(2)  # inside "سلام"
    widget.setTextCursor(cursor)
    original = widget._wordUnderCursor
    calls: list[int] = []

    def counting() -> tuple[int, int] | None:
        calls.append(1)
        return original()

    widget._wordUnderCursor = counting
    baseline = len(calls)  # the setTextCursor sync
    _sendKey(widget, Qt.Key.Key_S.value, "س")  # Arabic: types into the document
    assert len(calls) == baseline + 1
    cursor.setPosition(6)  # a real cursor move must still sync
    widget.setTextCursor(cursor)
    assert len(calls) == baseline + 2


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
    """Typing in the second paragraph after a Ctrl+Enter commit does not crash.

    The Ctrl+Enter commit moves the cursor into the second block, so the
    seeded overlay's anchor — and every subsequent keystroke — resolves line
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
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Return,
        "\n",
        Qt.KeyboardModifier.ControlModifier,
    )
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
    _moveCursor(widget, 10)  # the document end (a bare cursor position)
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
def _lineTopInView(overlay: RomanOverlay, viewport: QWidget) -> int:
    """The overlay's line edit top edge in viewport coordinates.

    The overlay's own top edge moves when the suggestion list flips
    above or below the line edit, but the line edit itself must always
    sit over the word it edits: mapping the line edit's origin into the
    viewport is the orientation-independent observation point of the
    pinning.
    """
    return overlay.lineEdit().mapTo(viewport, QPoint(0, 0)).y()


# ******************************************************************************
def _listAbove(overlay: RomanOverlay) -> bool:
    """Whether the overlay's suggestion list is laid out above the line edit."""
    return bool(getattr(overlay, "listAbove", lambda: False)())


# ******************************************************************************
def _wordSpanOnLine(widget: PyRaya, word: str, which: str) -> tuple[int, int] | None:
    """The span of a word occurrence on the first or the lowest line.

    Scans the word's occurrences in the document and returns the span on
    the first line the word occurs on (``"first"``) or on the lowest such
    line (``"lowest"``), reading the line's top from the block layout's
    own geometry so the result tracks the font actually in use.
    """
    offset = widget.contentOffset()
    best: tuple[int, int, int] | None = None  # (top, start, end) of the lowest line
    first: tuple[int, int] | None = None
    block = widget.document().begin()
    while block.isValid():
        local = 0
        while (local := block.text().find(word, local)) >= 0:
            start = block.position() + local
            top = round(
                block.layout().boundingRect().top()
                + widget.blockBoundingGeometry(block).y()
                + offset.y()
            )
            if which == "lowest":
                if best is None or top > best[0]:
                    best = (top, start, start + len(word))
            elif first is None:
                first = (start, start + len(word))
            local += len(word)
        block = block.next()
    if which == "lowest":
        return (best[1], best[2]) if best is not None else None
    return first


# ******************************************************************************
def _wordSpanOnBlock(widget: PyRaya, word: str, blockIndex: int) -> tuple[int, int]:
    """The span of ``word`` inside the block at ``blockIndex``.

    Reads the block position and the in-block offset directly, so the
    result tracks the document layout. Raises ``ValueError`` when the
    word does not occur in that block.
    """
    block = widget.document().begin()
    for _ in range(blockIndex):
        block = block.next()
    local = block.text().index(word)
    start = block.position() + local
    return (start, start + len(word))


# ******************************************************************************
def _setSizeToViewport(app: QApplication, widget: PyRaya, width: int, target: int) -> None:
    """Resize the widget until its viewport is exactly ``target`` tall.

    The viewport is the widget's height minus the frame (and any
    scrollbars), so each iteration adds back the shortfall read after the
    previous resize; the frame is stable, so the fixed point is reached in
    a couple of iterations.
    """
    height = widget.height()
    for _ in range(4):
        widget.resize(width, height)
        app.processEvents()
        if widget.viewport().height() == target:
            break
        height += target - widget.viewport().height()
    assert widget.viewport().height() == target


# ******************************************************************************
def testOverlayFlipsListAboveOnLowWord(app: QApplication) -> None:
    """The line edit stays over a low word; only the list flips above it.

    The overlay is activated in a viewport tall enough for the list to
    sit below the word; the viewport is then shrunk to one pixel short of
    the word's line plus the overlay's own footprint, so the list can no
    longer fit below. The overlay flips only the list above the line edit
    — the line edit itself never moves off the word it covers — and the
    flipped overlay still fits the viewport.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(640, 600)
    widget.setPlainText("due\nteen\nhello خوش")
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnLine(widget, "خوش", "lowest")
    assert span is not None
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    # The overlay's actual footprint over this word: the line edit plus the
    # list the engine offers for it, read from the widget's own geometry so
    # the test tracks the font actually in use.
    top = widget._wordRect(*span).top()
    assert top > 0  # the word is not on the first line
    height = overlay.sizeHint().height()
    # One pixel short of the word's line plus the footprint: the list can
    # no longer fit below the word, so the flip is forced.
    _setSizeToViewport(app, widget, 640, top + height - 1)
    assert top + height > widget.viewport().height()
    wordRect = widget._wordRect(*span)
    assert wordRect.top() == top  # the width is unchanged; the line did not reflow
    lineTop = _lineTopInView(overlay, widget.viewport())
    assert lineTop == wordRect.top()  # the line edit still sits over the word
    assert lineTop + overlay.lineEdit().sizeHint().height() >= wordRect.bottom() + 1
    assert _listAbove(overlay)  # the list flipped above the line edit
    listTop = overlay.suggestionList().mapTo(widget.viewport(), QPoint(0, 0)).y()
    assert 0 <= listTop < lineTop  # the list sits above the line edit
    assert listTop + overlay.suggestionList().height() <= lineTop  # no overlap
    geom = overlay.geometry()
    assert geom.right() == wordRect.right()  # the right edge stays on the word
    assert 0 <= geom.top() < lineTop
    assert geom.bottom() <= widget.viewport().height()  # the flipped overlay fits


# ******************************************************************************
def testOverlayDoesNotFlipWithRoomBelow(app: QApplication) -> None:
    """With room below, the list stays below the line edit (no flip).

    A word on a line with enough room for the full list keeps the
    default orientation: the overlay's top is the line edit's top (the
    word's top) and the list sits below the line edit.
    """
    widget = PyRaya()
    widget.resize(640, 480)
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnLine(widget, "خوش", "first")
    assert span is not None
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    wordRect = widget._wordRect(*span)
    assert not _listAbove(overlay)  # the default orientation holds
    lineTop = _lineTopInView(overlay, widget.viewport())
    assert lineTop == wordRect.top()
    assert overlay.geometry().top() == lineTop  # the overlay's top is the line edit's
    listTop = overlay.suggestionList().mapTo(widget.viewport(), QPoint(0, 0)).y()
    assert listTop > lineTop
    geom = overlay.geometry()
    assert 0 <= geom.top()
    assert geom.bottom() <= widget.viewport().height()


# ******************************************************************************
def testOverlayUnflipsOnTallerResize(app: QApplication) -> None:
    """A resize that restores room below flips the list back under the line edit.

    The flip follows the available space on every re-placement: the
    overlay flipped at a short viewport goes back to the list-below
    orientation when a taller resize leaves room below the word again,
    and the line edit sits over the word in both orientations.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(640, 600)
    widget.setPlainText("due\nteen\nhello خوش")
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnLine(widget, "خوش", "lowest")
    assert span is not None
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    top = widget._wordRect(*span).top()
    height = overlay.sizeHint().height()
    _setSizeToViewport(app, widget, 640, top + height - 1)
    assert _listAbove(overlay)  # flipped at the short viewport
    # The taller resize restores room below the word: the list flips back down.
    widget.resize(640, widget.height() + 200)
    app.processEvents()
    wordRect = widget._wordRect(*span)
    assert wordRect.top() == top  # the width is unchanged; the line did not reflow
    lineTop = _lineTopInView(overlay, widget.viewport())
    assert not _listAbove(overlay)
    assert lineTop == wordRect.top()  # the line edit stayed over the word
    assert overlay.geometry().top() == lineTop  # the list is below again
    listTop = overlay.suggestionList().mapTo(widget.viewport(), QPoint(0, 0)).y()
    assert listTop > lineTop
    assert overlay.geometry().bottom() <= widget.viewport().height()


# ******************************************************************************
def testSeededOverlayFlipsListAboveAtLowCursor(app: QApplication) -> None:
    """A seeded overlay at a low cursor flips the list above the line edit.

    Scenario 1 (no word to cover) anchors the line edit to the cursor's
    line: the overlay is seeded in a tall viewport, then the viewport is
    shrunk until the space above the anchor exceeds the space below —
    both too small for the full list — so the flip picks the larger
    space and the line edit stays pinned to the anchor's line.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(640, 600)
    widget.setPlainText("due\nteen\nhello world ")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 9, 21)  # the last line
    _moveCursor(widget, 20)  # the end of the last line's text
    _sendKey(widget, Qt.Key.Key_D, "d")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_A, "a")  # "da" fills several rows
    anchor = widget._anchorPosition
    assert anchor is not None
    rightX, top = widget._cursorAnchor(anchor)
    assert top > 0  # the cursor is not on the first line
    height = overlay.sizeHint().height()
    listHint = overlay.suggestionList().sizeHint().height()
    # One pixel short of equalizing the two spaces: the room below the
    # line edit (top + height leaves the deficit) falls one pixel under
    # the gap above the anchor, and both leave the list short — the
    # flip now has strictly more room above than below.
    _setSizeToViewport(app, widget, 640, top + (top - 4) + height - listHint - 1)
    belowRoom = widget.viewport().height() - top - height + listHint
    assert belowRoom < top - 4  # the above space is strictly larger
    assert listHint > belowRoom  # and the list does not fit below either
    rightX, top = widget._cursorAnchor(anchor)  # the width is unchanged; no reflow
    assert overlay.isVisible()
    assert overlay.lineEdit().text() == "da"  # the typed text survived the resize
    lineTop = _lineTopInView(overlay, widget.viewport())
    assert lineTop == top  # the line edit sits on the anchor's line
    assert _listAbove(overlay)
    listTop = overlay.suggestionList().mapTo(widget.viewport(), QPoint(0, 0)).y()
    assert 0 <= listTop < lineTop
    assert listTop + overlay.suggestionList().height() <= lineTop  # no overlap
    geom = overlay.geometry()
    assert geom.right() + 1 == rightX  # the right edge stays on the cursor
    assert 0 <= geom.top()
    assert geom.bottom() <= widget.viewport().height()  # the flipped overlay fits


# ******************************************************************************
def testClickActivationPinsLineEditOverFlippedList(app: QApplication) -> None:
    """A click-activated overlay's line edit sits exactly on the word.

    The press deactivates and hides the overlay, so the release places a
    hidden widget whose layout has not run for the size about to be set:
    the previous word's list height is baked into the widget's slots, and
    this word's suggestions have a different height. Reading the line
    edit's slot back therefore answers with the previous word's value and
    drags the whole overlay off the word by the slot difference; the pin
    must come from the same numbers the geometry is built from.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(640, 800)
    widget.setPlainText("due\nteen\nhello دوست ژنگز")
    widget.setRomanInputEnabled(True)
    spanShort = _wordSpanOnLine(widget, "دوست", "lowest")
    spanLong = _wordSpanOnLine(widget, "ژنگز", "lowest")
    assert spanShort is not None
    assert spanLong is not None
    widget.setRegionType(RegionType.RomanUrdu, *spanShort)
    widget.setRegionType(RegionType.RomanUrdu, *spanLong)
    _moveCursor(widget, spanShort[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    top = widget._wordRect(*spanShort).top()
    assert top > 0  # the words are not on the first line
    height = overlay.sizeHint().height()
    # Deactivate first, then shrink: an inactive overlay is not re-placed
    # on resize, so the click re-activates it with only this word
    # Whereas the settled layout still holds this word's slots.
    widget._deactivateOverlay()
    app.processEvents()
    assert not overlay.isVisible()
    # One pixel short of the short-list word's footprint: the click will
    # flip the list above the line edit.
    _setSizeToViewport(app, widget, 640, top + height - 1)
    wordRect = widget._wordRect(*spanLong)
    assert wordRect.top() == top  # the width is unchanged; no reflow
    point = (wordRect.right(), wordRect.top() + 5)
    _sendMouse(widget, "press", point[0], point[1])
    _sendMouse(widget, "release", point[0], point[1])
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    app.processEvents()
    assert _listAbove(overlay)
    assert _lineTopInView(overlay, widget.viewport()) == wordRect.top()


# ******************************************************************************
def testFlippedPlacementIsIdempotent(app: QApplication) -> None:
    """Placement from identical arguments yields identical geometry.

    A click-path placement runs while the overlay is hidden, so its
    layout has not run for the size being set; a second identical call
    — after the overlay is shown and the layout has settled — must
    reproduce the exact geometry. The placement is a pure function of
    the anchor and the viewport, not of whatever slots the layout
    happened to hold when it was called.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(640, 800)
    widget.setPlainText("due\nteen\nhello دوست ژنگز")
    widget.setRomanInputEnabled(True)
    spanShort = _wordSpanOnLine(widget, "دوست", "lowest")
    spanLong = _wordSpanOnLine(widget, "ژنگز", "lowest")
    assert spanShort is not None
    assert spanLong is not None
    widget.setRegionType(RegionType.RomanUrdu, *spanShort)
    widget.setRegionType(RegionType.RomanUrdu, *spanLong)
    _moveCursor(widget, spanShort[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    top = widget._wordRect(*spanShort).top()
    assert top > 0  # the words are not on the first line
    height = overlay.sizeHint().height()
    widget._deactivateOverlay()
    app.processEvents()
    _setSizeToViewport(app, widget, 640, top + height - 1)
    wordRect = widget._wordRect(*spanLong)
    rightX = wordRect.right() + 1
    # Place the long-list word while the overlay is hidden, let the layout
    # settle under the placed size, then place again from the same
    # arguments: a pure placement must reproduce the same geometry.
    widget._placeOverlay(rightX, wordRect.top())  # hidden: called on a stale layout
    overlay.show()
    app.processEvents()
    first = overlay.geometry()
    widget._placeOverlay(rightX, wordRect.top())  # identical arguments, settled
    second = overlay.geometry()
    widget._placeOverlay(rightX, wordRect.top())  # and once more, for good measure
    app.processEvents()
    assert overlay.geometry() == second
    assert second == first


# ******************************************************************************
def testRightEdgeHugPinsOverlayRight(app: QApplication) -> None:
    """A word hugging the viewport's right edge keeps the overlay pinned.

    Placement pins the overlay's right edge to the word's right edge in
    both orientations: a viewport too narrow to show the whole overlay
    clips it on the left instead of pulling the right edge off the word.
    The overlay input staying over the trigger word is the invariant — a
    viewport that cannot show the overlay is adjusted (resized or
    scrolled) by the user, never worked around by moving the overlay.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(200, 400)
    widget.setPlainText("due\nteen\nhello دوست")
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnLine(widget, "دوست", "lowest")
    assert span is not None
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    wordRect = widget._wordRect(*span)
    assert wordRect.right() >= widget.viewport().width() - 30  # hugging the edge
    # Typed text wider than everything left of the viewport's edge: the
    # placement width floor no longer fits.
    overlay.setText(ZERO_MATCH_WORDS[0] * 6)
    app.processEvents()
    assert overlay.width() > wordRect.right() + 1  # the case bites at all
    assert overlay.geometry().right() == wordRect.right()
    assert _lineTopInView(overlay, widget.viewport()) == wordRect.top()


# ******************************************************************************
def testScrollReanchorsActiveOverlay(app: QApplication) -> None:
    """Scrolling keeps the overlay over its word while the word is visible.

    The overlay is a viewport child and never scrolls by itself: a scroll
    moves the document under it, so an active overlay must be re-placed
    over its word. Small scrolls pass through Qt's viewport blit (which
    shifts child widgets with the painted content); large jumps repaint
    without moving children — the placement must be re-derived in both
    cases, accumulating no drift. The off/on-screen decision is made on
    the WORD's rect, never on the overlay widget: a word scrolled
    partially out of the viewport keeps the overlay active and pinned,
    and a word scrolled fully out of it deactivates the overlay even
    though the overlay's own box would still overlap the viewport.
    Scrolling back resumes the suspension: view events (scroll, resize,
    reflow) suspend and resume the overlay both ways, while user
    decisions (a mouse press, Esc, a new activation) and document edits
    drop it.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(400, 240)
    widget.setPlainText("\n".join(["hello دوست"] * 24))
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnBlock(widget, "دوست", 3)  # a mid-document word
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    app.processEvents()
    assert _lineTopInView(overlay, widget.viewport()) == widget._wordRect(*span).top()
    scrollbar = widget.verticalScrollBar()
    assert scrollbar.maximum() >= 5  # headroom for the whole-line scrolls
    # Fully visible: the +3 whole-line jump (large scroll, repaint path)
    # re-places the overlay over the word, accumulating no drift.
    scrollbar.setValue(3)
    app.processEvents()
    wordRect = widget._wordRect(*span)
    assert 0 <= wordRect.top() and wordRect.bottom() <= widget.viewport().height()
    assert widget._overlayActive()
    assert _lineTopInView(overlay, widget.viewport()) == wordRect.top()
    # Fully out: a further whole-line scroll leaves no visible edge of the
    # word, and the overlay is deactivated — the hit test is on the word
    # rect, never the overlay widget, which reaches further than its word.
    scrollbar.setValue(5)
    app.processEvents()
    assert widget._wordRect(*span).bottom() < 0  # the word fully above
    assert not widget._overlayActive()
    # Scrolling back re-activates the view-suspended overlay over the
    # word — view events (scroll, resize, reflow) suspend and resume the
    # overlay both ways, with no manual trigger. The resumption is the
    # standard activation: the word's full romanization, line-edit
    # focus, exact pinning.
    scrollbar.setValue(3)
    app.processEvents()
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert widget._activeWord == span
    assert _lineTopInView(overlay, widget.viewport()) == widget._wordRect(*span).top()
    # Partially visible: shrinking the viewport until its bottom edge
    # falls inside the word's rect keeps the overlay active and pinned
    # over the word (only one visible edge matters — the word's, never
    # the overlay's).
    scrollbar.setValue(2)
    app.processEvents()
    wordRect = widget._wordRect(*span)
    assert wordRect.top() > 0
    _setSizeToViewport(app, widget, 400, wordRect.top() + 6)
    assert widget._wordRect(*span).bottom() > widget.viewport().height()  # clipped below
    assert widget._overlayActive()
    assert _lineTopInView(overlay, widget.viewport()) == widget._wordRect(*span).top()
    # Fully out of the reflowed viewport (the word's top edge is no less
    # visible than any overlay pixel): the overlay deactivates.
    _setSizeToViewport(app, widget, 400, wordRect.top())
    assert widget._wordRect(*span).top() >= widget.viewport().height()
    assert not widget._overlayActive()
    # Granting room back resumes the suspended overlay over the word —
    # the reflow-caused hiding is a view suspension, not a user decision.
    _setSizeToViewport(app, widget, 400, 240)
    app.processEvents()
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert widget._activeWord == span
    assert _lineTopInView(overlay, widget.viewport()) == widget._wordRect(*span).top()


# ******************************************************************************
def testScrollOutDeactivatesOnWordRectLeavingViewport(app: QApplication) -> None:
    """A word scrolled fully below the viewport deactivates the overlay.

    The decision is on the WORD's rect, never the overlay widget: the
    word is activated in the viewport's bottom band with its tall
    suggestion list flipped above it, so when the word slides out at the
    viewport's bottom edge the flipped list would still hang far up
    inside the viewport — an overlay-based hit test would keep the popup
    alive over nothing. Scrolling back restores the suspension.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(640, 600)
    widget.setPlainText("\n".join(["hello ژنگز"] * 90))
    widget.setRomanInputEnabled(True)
    blockIndex = 46  # a word with plenty of document below it
    span = _wordSpanOnBlock(widget, "ژنگز", blockIndex)
    widget.setRegionType(RegionType.RomanUrdu, *span)
    lineHeight = round(widget.blockBoundingGeometry(widget.document().begin()).height())
    # Scroll the word into the viewport's bottom band, leaving room below
    # for less than the tall list: the list flips above the anchor.
    scrollbar = widget.verticalScrollBar()
    value = blockIndex - ((widget.viewport().height() - 4 * lineHeight - 4) // lineHeight)
    scrollbar.setValue(max(0, value))
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    app.processEvents()
    wordRect = widget._wordRect(*span)
    assert wordRect.top() > 0 and wordRect.bottom() <= widget.viewport().height()
    assert _listAbove(overlay)  # flipped above the near-bottom anchor
    # Scroll toward the document's start: the word leaves the viewport at
    # its bottom edge, and the overlay is deactivated on the word rect.
    scrollbar.setValue(0)
    app.processEvents()
    assert widget._wordRect(*span).top() >= widget.viewport().height()
    assert not widget._overlayActive()
    # Scrolling back restores the suspended overlay over the word — the
    # bottom-edge hiding is the same view suspension as any other.
    scrollbar.setValue(max(0, value))
    app.processEvents()
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert widget._activeWord == span
    assert _lineTopInView(overlay, widget.viewport()) == widget._wordRect(*span).top()


# ******************************************************************************
def testSeededAnchorOutOfViewportDeactivates(app: QApplication) -> None:
    """A seeded overlay deactivates when its anchor line scrolls off.

    The scenario 1 (seeded, no word) equivalent of the word-rect hit
    test: the anchor's cursor line. The overlay is seeded mid-document,
    typed further, and then scrolled fully out of the viewport; the
    overlay suspends, and scrolling back resumes it at the anchor with
    the typed text intact.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(400, 240)
    widget.setPlainText("\n".join(["hello world"] * 24))
    widget.setRomanInputEnabled(True)
    block = widget.document().begin()
    for _ in range(4):
        block = block.next()
    position = block.position() + 4
    _moveCursor(widget, position)
    _sendKey(widget, Qt.Key.Key_D, "d")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_O, "o")  # typed text survives
    app.processEvents()
    scrollbar = widget.verticalScrollBar()
    assert scrollbar.maximum() >= 5  # the anchor can be scrolled fully out
    scrollbar.setValue(scrollbar.maximum())
    app.processEvents()
    assert not widget._overlayActive()  # the anchor line is above the viewport
    # Scrolling back resumes the suspended seeded overlay at the anchor
    # with the typed text intact — no manual trigger needed.
    scrollbar.setValue(0)
    app.processEvents()
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert widget._activeWord is None
    assert widget._anchorPosition == position
    assert overlay.lineEdit().text() == "do"


# ******************************************************************************
def testUserDeactivationSuppressesRestore(app: QApplication) -> None:
    """User decisions drop the suspension; view events never override them.

    The word-rect hit test's hiding is a view suspension that resumes
    when the word returns. A user decision — a mouse press anywhere, or
    Ctrl+Esc turning assist mode off — is an explicit active/inactive
    state: once the user walked away, scrolling back must not resurrect
    the overlay over them.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(400, 240)
    widget.setPlainText("\n".join(["hello دوست"] * 24))
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnBlock(widget, "دوست", 3)
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    app.processEvents()
    scrollbar = widget.verticalScrollBar()
    scrollbar.setValue(5)  # the word leaves the viewport: suspended
    app.processEvents()
    assert not widget._overlayActive()
    # A mouse press is a user decision: the suspension is dropped and
    # scrolling back stays quiet.
    _sendMouse(widget, "press", 50, 200)
    _sendMouse(widget, "release", 50, 200)
    scrollbar.setValue(3)
    app.processEvents()
    assert not widget._overlayActive()
    # Ctrl+Esc on an active overlay turns assist mode off; the user is
    # left alone — no suspension outlives the assist-off state.
    widget2 = PyRaya()
    widget2.show()
    widget2.resize(400, 240)
    widget2.setPlainText("\n".join(["hello دوست"] * 24))
    widget2.setRomanInputEnabled(True)
    span2 = _wordSpanOnBlock(widget2, "دوست", 3)
    widget2.setRegionType(RegionType.RomanUrdu, *span2)
    _moveCursor(widget2, span2[0] + 1)
    overlay2 = widget2._overlay
    assert overlay2 is not None and overlay2.isVisible()
    _sendKey(
        overlay2.lineEdit(),
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )  # assist mode off
    app.processEvents()
    assert not widget2._assistMode
    scrollbar2 = widget2.verticalScrollBar()
    scrollbar2.setValue(scrollbar2.maximum())
    app.processEvents()
    scrollbar2.setValue(0)
    app.processEvents()
    assert not widget2._overlayActive()  # never suspended: nothing to resume


# ******************************************************************************
def testDocumentEditWhileSuspendedDropsRestore(app: QApplication) -> None:
    """A document edit while suspended makes the suspension stale.

    The suspension remembers the anchor for the document as it was: an
    edit bumps the document revision, so the suspension is dropped
    rather than re-activating over text that no longer matches.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(400, 240)
    widget.setPlainText("\n".join(["hello دوست"] * 24))
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnBlock(widget, "دوست", 3)
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    app.processEvents()
    scrollbar = widget.verticalScrollBar()
    scrollbar.setValue(5)
    app.processEvents()
    assert not widget._overlayActive()  # suspended
    before = widget.document().toPlainText()
    _sendKey(widget, Qt.Key.Key_Backspace, "")  # the document regained focus
    after = widget.document().toPlainText()
    assert after != before  # the edit really happened while suspended
    scrollbar.setValue(3)
    app.processEvents()
    assert not widget._overlayActive()  # the stale suspension is dropped
    assert widget._suspendedOverlay is None


# ******************************************************************************
def testAssistOffWhileSuspendedDropsRestore(app: QApplication) -> None:
    """Assist mode turning off while suspended drops the suspension.

    ``setAssistEnabled(False)`` is a user decision (the user is left
    alone); the suspension it voids stays dropped even after assist mode
    is marked ready again.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(400, 240)
    widget.setPlainText("\n".join(["hello دوست"] * 24))
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnBlock(widget, "دوست", 3)
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    app.processEvents()
    scrollbar = widget.verticalScrollBar()
    scrollbar.setValue(5)
    app.processEvents()
    assert not widget._overlayActive()  # suspended
    widget.setAssistEnabled(False)  # the user is left alone
    widget.setAssistEnabled(True)  # ready again — the suspension stays gone
    scrollbar.setValue(3)
    app.processEvents()
    assert not widget._overlayActive()
    assert widget._suspendedOverlay is None


# ******************************************************************************
def testFlippedClampedListHeightIsIntegralRows(app: QApplication) -> None:
    """A clamped flipped list is an exact number of rows tall.

    A click-path placement gives the clamped list whatever fraction of a
    row the viewport leaves above the anchor: the panel's unpainted
    remainder between the last row and the list's bottom edge shows as a
    blank strip of list background. The list's height is snapped down to
    an integral multiple of the row height (the same rows stay visible;
    only the blank strip goes away).
    """
    widget = PyRaya()
    widget.show()
    widget.resize(640, 800)
    widget.setPlainText("due\nteen\nhello دوست ژنگز")
    widget.setRomanInputEnabled(True)
    spanShort = _wordSpanOnLine(widget, "دوست", "lowest")
    spanLong = _wordSpanOnLine(widget, "ژنگز", "lowest")
    assert spanShort is not None
    assert spanLong is not None
    widget.setRegionType(RegionType.RomanUrdu, *spanShort)
    widget.setRegionType(RegionType.RomanUrdu, *spanLong)
    _moveCursor(widget, spanShort[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    top = widget._wordRect(*spanShort).top()
    assert top > 0
    height = overlay.sizeHint().height()
    widget._deactivateOverlay()
    app.processEvents()
    _setSizeToViewport(app, widget, 640, top + height - 1)
    # Click path: the release re-activates over the long-list word.
    wordRect = widget._wordRect(*spanLong)
    point = (wordRect.right(), wordRect.top() + 5)
    _sendMouse(widget, "press", point[0], point[1])
    _sendMouse(widget, "release", point[0], point[1])
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    app.processEvents()
    sugList = overlay.suggestionList()
    assert _listAbove(overlay)  # the flipped orientation, clamped
    assert sugList.rowCount() >= 2  # the clamp leaves less than all rows
    assert sugList.height() < sugList.sizeHint().height()  # the clamp engaged
    rowHeight = sugList.rowHeight()
    assert rowHeight > 0
    assert sugList.height() % rowHeight == 0  # no blank strip above the edge
    assert sugList.height() > 0  # some rows remain visible


# ******************************************************************************
def testTruncatedListHeightIsIntegralRows(app: QApplication) -> None:
    """A bottom-truncated list is an exact number of rows tall.

    A first-line anchor with a tall suggestion list stays in the default
    orientation (the viewport's top can never hold the list), so the list
    is truncated at the viewport's bottom edge — from an arbitrary pixel
    height, whose remainder is the blank panel strip below the last row.
    The height snaps down to an integral multiple of the row height.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(400, 120)
    widget.setPlainText("hello ژنگز")
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnLine(widget, "ژنگز", "first")
    assert span is not None
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    app.processEvents()
    sugList = overlay.suggestionList()
    assert not _listAbove(overlay)  # the default orientation, truncated
    assert sugList.rowCount() >= 2
    assert sugList.height() < sugList.sizeHint().height()  # the truncation engaged
    rowHeight = sugList.rowHeight()
    assert rowHeight > 0
    assert sugList.height() % rowHeight == 0  # no blank strip below the last row
    assert sugList.height() > 0  # some rows remain visible


# ******************************************************************************
def testSeededOverlayStaysBelowWithRoom(app: QApplication) -> None:
    """A seeded overlay with room below keeps the list below the line edit."""
    widget = PyRaya()
    widget.resize(800, 600)
    widget.show()
    widget.setPlainText("hello world ")
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnLine(widget, "world", "first")
    assert span is not None
    widget.setRegionType(RegionType.RomanUrdu, 6, 12)
    _moveCursor(widget, 11)
    _sendKey(widget, Qt.Key.Key_D, "d")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert not _listAbove(overlay)
    anchor = widget._anchorPosition
    assert anchor is not None
    rightX, top = widget._cursorAnchor(anchor)
    lineTop = _lineTopInView(overlay, widget.viewport())
    assert lineTop == top
    assert overlay.geometry().top() == lineTop  # the list is below the line edit
    assert overlay.geometry().bottom() <= widget.viewport().height()


# ******************************************************************************
def testOverlayStaysBelowWhenAboveSpaceIsSmaller(app: QApplication) -> None:
    """The list stays below when the space above is smaller than the below.

    A word on the document's first line has almost no space above it, so
    when the list no longer fits below the anchor line the overlay does
    NOT flip: the smaller space (above) would clip the list to nothing,
    while the too-small-below space still holds most of it. The overlay
    keeps the default orientation, the line edit stays pinned over the
    word, and the list is truncated at the viewport's bottom edge instead
    of painting out of bounds above the viewport's top edge.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(640, 600)
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnLine(widget, "خوش", "first")
    assert span is not None
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    top = widget._wordRect(*span).top()
    hint = overlay.sizeHint().height()
    listHint = overlay.suggestionList().sizeHint().height()
    # One pixel short of the overlay's below footprint: the list cannot
    # fully fit below — the space above is the smaller of the two.
    _setSizeToViewport(app, widget, 640, top + hint - 1)
    top = widget._wordRect(*span).top()
    # The width is unchanged; the line did not reflow, and the budget
    # relation that makes this the "above is smaller" case still holds:
    # below the line edit the list's bottom edge is the overlay's bottom
    # (top + hint), above it the flipped list is clamped to top - 4.
    belowRoom = widget.viewport().height() - top - hint + listHint
    aboveRoom = top - 4
    assert belowRoom == listHint - 1
    assert aboveRoom < belowRoom
    assert not _listAbove(overlay)  # the smaller space above loses
    lineTop = _lineTopInView(overlay, widget.viewport())
    assert lineTop == top  # the line edit stays pinned over the word
    assert overlay.geometry().top() == lineTop  # nothing is placed above
    listTop = overlay.suggestionList().mapTo(widget.viewport(), QPoint(0, 0)).y()
    assert listTop > lineTop  # the list is below the line edit
    # The truncated overlay fits the viewport and ends flush at the bottom
    # edge of its last visible row — the list is truncated in whole rows,
    # so no blank strip of list background is painted below the rows.
    assert overlay.geometry().y() + overlay.geometry().height() <= widget.viewport().height()
    rowHeight = overlay.suggestionList().rowHeight()
    assert rowHeight > 0
    assert overlay.suggestionList().height() % rowHeight == 0
    assert overlay.lineEdit().sizeHint().height() <= widget.viewport().height() - lineTop


# ******************************************************************************
def testOverlayFavorsBelowWhenSpacesAreEqual(app: QApplication) -> None:
    """Equal spaces above and below favor the lower (default) orientation.

    A word on the second line leaves a small gap above it; the viewport
    is sized so the gap above equals the room below the line edit, both
    too small for the full list. The tie stays below: the overlay keeps
    the default orientation, the line edit stays pinned over the word,
    and the list is truncated at the viewport's bottom edge.
    """
    widget = PyRaya()
    widget.show()
    widget.resize(640, 600)
    widget.setPlainText("due\nhello خوش")
    widget.setRomanInputEnabled(True)
    span = _wordSpanOnLine(widget, "خوش", "lowest")
    assert span is not None
    widget.setRegionType(RegionType.RomanUrdu, *span)
    _moveCursor(widget, span[0] + 1)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    top = widget._wordRect(*span).top()
    hint = overlay.sizeHint().height()
    listHint = overlay.suggestionList().sizeHint().height()
    assert 0 < top - 4 < listHint  # the tie is decisive: both spaces too small
    # Size the viewport so the room below the line edit equals the gap
    # above the anchor: belowRoom == aboveRoom == top - 4.
    _setSizeToViewport(app, widget, 640, top + (top - 4) + hint - listHint)
    top = widget._wordRect(*span).top()  # the width is unchanged; no reflow
    belowRoom = widget.viewport().height() - top - hint + listHint
    assert belowRoom == top - 4  # the tie holds after the resize
    assert not _listAbove(overlay)  # the tie favors below
    lineTop = _lineTopInView(overlay, widget.viewport())
    assert lineTop == top  # the line edit stays pinned over the word
    assert overlay.geometry().top() == lineTop  # nothing is placed above
    listTop = overlay.suggestionList().mapTo(widget.viewport(), QPoint(0, 0)).y()
    assert listTop > lineTop  # the list is below the line edit
    # The truncated overlay fits the viewport and ends flush at the bottom
    # edge of its last visible row — the list is truncated in whole rows,
    # so no blank strip of list background is painted below the rows.
    assert overlay.geometry().y() + overlay.geometry().height() <= widget.viewport().height()
    rowHeight = overlay.suggestionList().rowHeight()
    assert rowHeight > 0
    assert overlay.suggestionList().height() % rowHeight == 0


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
    widget.setRegionType(RegionType.RomanUrdu, 6, 11)  # word, space, and the Latin word
    _moveCursor(widget, 10)  # the start of the Latin word (a non-word position)
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
    widget.setRegionType(RegionType.Native, 0, 11)
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
    # punctuation is never intercepted by the overlay, even inside the span
    # with the feature on — but the region-scoped substitution rewrites the
    # typed Latin mark to its Urdu form before it lands in the document.
    widget2.setRomanInputEnabled(True)
    _moveCursor(widget2, 10)  # the space inside the span, after the "k"
    _sendKey(widget2, Qt.Key.Key_Comma, ",")
    assert widget2.toPlainText() == "hello خوشk\u060c world"
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
    # simulate the post-commit state: cursor at a non-word position, no active word
    _moveCursor(widget, 10)
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
    assert changed == [1]  # a writing commit signals the region change
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

    # Ctrl+Enter commits the word plus the newline over the same selection
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
    _sendKey(
        overlay2.lineEdit(),
        Qt.Key.Key_Return,
        "\n",
        Qt.KeyboardModifier.ControlModifier,
    )
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
    # The cursor settled on the word's end, which is over the word, so the
    # release resync re-activates the overlay over it (line edit cursor at
    # the text start, mirroring the word's end).
    assert widget._overlayActive()
    assert widget._activeWord == (6, 9)
    assert overlay.lineEdit().text() == "khosh"
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
    # extended the selection to the release point (the word's end), which is
    # over the word, so the release resync re-activates the overlay over it.
    assert (cursor.selectionStart(), cursor.selectionEnd()) == (7, 9)
    assert widget._overlayActive()
    assert widget._activeWord == (6, 9)
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
    # the edge commit moved the cursor to the next word's start (16, inside
    # the word); the resync ran despite the mouse flag and jumped the overlay
    # to the next word
    assert widget._activeWord == (16, 20)
    assert widget.textCursor().position() == 16
    assert widget._mouseActive
    assert widget.toPlainText() == "hello خوش world دوست"
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "dost"
    assert overlay.lineEdit().cursorPosition() == 4


# ******************************************************************************
def testSeparatorCommits(app: QApplication) -> None:
    """Space and typed punctuation commit the word plus separator; a plain
    Enter commits the bare word."""

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

    # Enter: the bare word, no separator, the resync suppressed (the
    # cursor rests at the committed word's end, over the word)
    widget, overlay = setup()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Return, "\n")
    assert widget.toPlainText() == "hello خوش world"
    assert widget.textCursor().position() == 9
    assert widget._regionKindAt(8) == RegionType.RomanUrdu
    assert not overlay.isVisible()

    # Comma: the typed Latin mark lands as its Urdu form (region-scoped
    # substitution), tagged RomanUrdu with the word.
    widget, overlay = setup()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Comma, ",")
    assert widget.toPlainText() == "hello خوش\u060c world"
    assert widget.textCursor().position() == 10
    assert widget._regionKindAt(9) == RegionType.RomanUrdu
    assert not overlay.isVisible()


# ******************************************************************************
def testArabicSeparatorsCommitAsSeparatorKeys(app: QApplication) -> None:
    """The Arabic script's own separator marks commit like ASCII ones.

    A typed Arabic separator — the Arabic question mark, comma,
    semicolon, the Urdu full stop, and the Arabic date, decimal, and
    thousands separators — commits the selected word plus the separator
    character: the mark is written out and tagged as ``roman urdu``
    together with the word, and the overlay stays deactivated
    afterwards, ready for the next word.
    """
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 10)
    marks = (
        "\u061f",  # ؟ Arabic question mark
        "\u060c",  # ، Arabic comma
        "\u061b",  # ؛ Arabic semicolon
        "\u06d4",  # ۔ full stop
        "\u066b",  # ٫ Arabic decimal separator
        "\u066c",  # ٬ Arabic thousands separator
        "\u060d",  # ؜ Arabic date separator
    )
    keys = (
        Qt.Key.Key_Question,
        Qt.Key.Key_Comma,
        Qt.Key.Key_Semicolon,
        Qt.Key.Key_Period,
        Qt.Key.Key_Comma,
        Qt.Key.Key_Comma,
        Qt.Key.Key_Period,
    )
    for index, (mark, key) in enumerate(zip(marks, keys, strict=True)):
        _moveCursor(widget, 7)  # re-activate the overlay over the word
        overlay = widget._overlay
        assert overlay is not None and overlay.isVisible()
        _sendKey(overlay.lineEdit(), key, mark)  # type the Arabic separator
        # Each commit replaces the word span (never the earlier marks), so
        # its separator lands directly after the word and earlier marks
        # drift right — the accumulated marks appear in reverse order.
        assert widget.toPlainText() == ("hello دوست" + "".join(reversed(marks[: index + 1])))
        assert widget.textCursor().position() == 11  # after word + separator
        assert not overlay.isVisible()
    text = widget.toPlainText()
    assert widget._regionKindAt(len(text) - 1) == RegionType.RomanUrdu


# ******************************************************************************
def testArabicSeparatorsAreWordBoundaries(app: QApplication) -> None:
    """The Arabic separator marks terminate a word run like Latin ones.

    ``ArabicScriptSeparators`` is every Arabic-script punctuation mark
    (``P*`` in the script's ranges) and ``_isArabicChar`` excludes them, so
    ``کام۔`` is the word ``کام`` followed by the separator ``۔``, never one
    word. The word under the cursor inside ``کام`` is ``کام`` alone, and the
    word after the separator starts behind it.
    """
    widget = PyRaya()
    widget.show()
    widget.setPlainText("کام۔ دوست")
    widget.setRomanInputEnabled(True)
    # Untagged text belongs to the default (RomanUrdu) kind, so the run
    # scan accepts it.
    _moveCursor(widget, 2)  # inside کام
    assert widget._activeWord == (0, 3)  # the full stop ends the run
    _moveCursor(widget, 6)  # inside دوست
    assert widget._activeWord == (5, 9)  # and the next word starts past it


# ******************************************************************************
def testReturnCommitsWithoutNewline(app: QApplication) -> None:
    """Plain Enter commits the word without a newline; the resync is
    suppressed, and the next trigger re-activates the overlay."""

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

    # Plain Enter: the committed word replaces the span with no newline,
    # the cursor rests at the word's end, and the resync is suppressed.
    widget, overlay = setup()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Return, "\n")
    assert widget.toPlainText() == "hello خوش world"
    assert widget.document().blockCount() == 1
    assert widget.textCursor().position() == 9  # no newline after the word
    assert widget._regionKindAt(8) == RegionType.RomanUrdu
    _assertNoOverlay(widget)
    # the resync was skipped: the cursor rests at the committed word's end,
    # over the word, but the overlay the user just dismissed is not shown;
    # Ctrl+Space re-triggers it over the word
    _sendKey(widget, Qt.Key.Key_Space, " ", Qt.KeyboardModifier.ControlModifier)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"


# ******************************************************************************
def testCtrlReturnCommitsWithNewline(app: QApplication) -> None:
    """Ctrl+Enter commits the word plus a newline, opening the second block.

    The resync runs: the cursor lands at the new block's start, a bare
    position, so the overlay stays quiet until the next trigger.
    """
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Return,
        "\n",
        Qt.KeyboardModifier.ControlModifier,
    )
    assert widget.toPlainText() == "hello خوش\n world"
    assert widget.document().blockCount() == 2
    assert widget.textCursor().position() == 10  # start of the second block
    # a block-terminator character cannot carry a character format, so the
    # newline stays untagged; the committed word characters are RomanUrdu
    assert widget._regionKindAt(8) == RegionType.RomanUrdu
    _assertNoOverlay(widget)


# ******************************************************************************
def testCtrlUpCommitsBareAndMovesOneLineUp(app: QApplication) -> None:
    """Ctrl+Up commits the selected word bare and moves the cursor up one line.

    The commit runs through the normal write path (RomanUrdu tag,
    ``regionsChanged`` and ``romanWordCommitted`` emitted, one logical undo
    step), the overlay is closed, assist mode stays on, and the line move
    lands exactly one line up: the document behaves as if Up had been pressed
    in it.
    """
    widget = PyRaya()
    widget.show()
    original = "hello\nخوش\nworld"
    widget.setPlainText(original)
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    committed: list[tuple[str, str]] = []
    changed: list[int] = []
    widget.romanWordCommitted.connect(lambda w, r: committed.append((w, r)))
    widget.regionsChanged.connect(lambda: changed.append(1))
    baseline = widget.document().availableUndoSteps()
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Up,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
    # the word commits bare: no separator character, the text is unchanged
    assert widget.toPlainText() == original
    # the cursor moved exactly one line up: from block 1 to block 0, over
    # the last character of the Latin word hello (position 4)
    assert widget.textCursor().blockNumber() == 0
    assert widget.textCursor().position() == 4
    assert committed == [("خوش", "khosh")]
    assert changed == [1]
    _assertNoOverlay(widget)
    assert widget.isAssistEnabled() is True
    # the span replacement is counted as two undo steps (delete + insert),
    # but a single undo reverts the whole commit
    assert widget.document().availableUndoSteps() == baseline + 2
    widget.undo()
    assert widget.toPlainText() == original
    assert widget.document().availableUndoSteps() == baseline
    # redoing takes the tag step and the commit step, no ping-pong
    widget.redo()
    widget.redo()
    assert widget.toPlainText() == original
    assert widget.document().isUndoAvailable()


# ******************************************************************************
def testCtrlDownCommitsBareAndMovesOneLineDown(app: QApplication) -> None:
    """Ctrl+Down commits the selected word bare and moves the cursor down one
    line: the Ctrl+Up contract's symmetric half."""
    widget = PyRaya()
    widget.show()
    original = "hello\nخوش\nworld"
    widget.setPlainText(original)
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Down,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
    assert widget.toPlainText() == original
    # the cursor moved exactly one line down: from block 1 to block 2,
    # over the last character of the Latin word world (position 14)
    assert widget.textCursor().blockNumber() == 2
    assert widget.textCursor().position() == 14
    _assertNoOverlay(widget)
    assert widget.isAssistEnabled() is True


# ******************************************************************************
def testCtrlUpLandingOnRomanUrduWordReactivatesOverlay(app: QApplication) -> None:
    """Ctrl+Up landing on a line whose word sits under the cursor re-activates
    the overlay: the line move passes through the document's normal assist
    rules."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("دوست\nخوش\nworld")
    widget.setRomanInputEnabled(True)
    _moveCursor(widget, 6)  # inside block 1's word خوش (5..8)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Up,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
    # the line move lands at block 0's word's end, over the word دوست
    assert widget.textCursor().position() == 4
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert widget._activeWord == (0, 4)
    assert overlay.lineEdit().text() == "dost"


# ******************************************************************************
def testCtrlUpLandingWithoutWordStaysQuiet(app: QApplication) -> None:
    """Ctrl+Up landing where no word sits under the cursor leaves no overlay:
    the line move passes through, and the document stays quiet."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello\nخوش\nworld")
    widget.setRomanInputEnabled(True)
    _moveCursor(widget, 7)  # inside block 1's word خوش (6..9)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Up,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
    # the line move lands over the Latin word hello, whose characters are
    # not an Arabic word run, so no overlay activates
    assert widget.textCursor().position() == 4
    _assertNoOverlay(widget)


# ******************************************************************************
def testCtrlShiftUpDownStayListNavigation(app: QApplication) -> None:
    """Ctrl+Shift+Up/Down on the active overlay move only the list highlight:
    the exact-Ctrl mask excludes Shift, so they keep the plain Up/Down list
    navigation — the document is untouched and the overlay stays active."""
    widget = PyRaya()
    widget.show()
    original = "hello خوش world"
    widget.setPlainText(original)
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    overlay.setText("khos")  # six distance-1 suggestions
    suggestionList = overlay.suggestionList()
    assert suggestionList.rowCount() > 1
    assert suggestionList.selectedIndex() == 0
    shift = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Down, "", shift)
    assert suggestionList.selectedIndex() == 1
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Up, "", shift)
    assert suggestionList.selectedIndex() == 0
    # no commit: the document, the cursor, and the overlay are all untouched
    assert widget.toPlainText() == original
    assert widget.textCursor().position() == 7
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "khos"


# ******************************************************************************
def testCtrlUpEmptyTextCommitRemovesSpan(app: QApplication) -> None:
    """An empty-overlay commit via Ctrl+Up follows the empty-commit contract
    (span removal) plus the line move: the span is deleted, no separator is
    written, and the cursor lands one line up."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello\nخوش\nworld")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    overlay.setText("")  # clear the overlay text
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Up,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
    # span deleted (the surrounding newlines stay), no separator takes its
    # place, the cursor one line up, over the last character of hello
    assert widget.toPlainText() == "hello\n\nworld"
    assert widget.textCursor().blockNumber() == 0
    assert widget.textCursor().position() == 5
    _assertNoOverlay(widget)


# ******************************************************************************
def testEdgeCommits(app: QApplication) -> None:
    """Edge commits insert nothing and jump in visual (screen) order.

    Activation places the line edit cursor at the position that
    proportionally mirror-maps the document cursor across the word, so arrow
    keys move in visual order and edge commits fire only at the actual edges:
    Right at the overlay's visually right edge (the text end) commits to the
    previous word, and Left at its visually left edge (the text start) commits
    to the next word. When that word exists, the cursor lands at its edge
    facing the active word — Right at its end, Left at its start — and the
    resync re-activates the overlay over the landed word (a cursor at the
    word's end is over the word). With no adjacent word — the commit lands on
    a boundary word, whose far side is only whitespace — the overlay is
    closed and the resync skipped, so the deactivation sticks and the cursor
    rests at the boundary edge (Right at the word's start, Left at its end).
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
    # The document cursor sits one third of the way from the word's visually
    # right edge, so the proportional mirror map places the line edit cursor
    # the same fraction from the text end (position 3 of "khosh"), not at
    # the text end.
    assert overlay.lineEdit().cursorPosition() == 3

    # Walking Right reaches the visually right edge (the text end), where the
    # next Right edge-commits: no Arabic word before خوش (only the
    # paragraph's leading whitespace) -> the cursor lands at the word's
    # visually right edge (its start, 6), and the deactivation sticks: the
    # overlay is closed at the boundary word and stays closed.
    for _ in range(2):
        _sendKey(overlay.lineEdit(), Qt.Key.Key_Right, "")
    assert overlay.lineEdit().cursorPosition() == 5
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Right, "")
    assert widget.toPlainText() == text  # nothing inserted
    assert widget.textCursor().position() == 6
    _assertNoOverlay(widget)

    # Holding Left walks visually leftward through the rest of خوش, the
    # Latin word, and the space, then into دوست, where the overlay
    # activates.
    for _ in range(10):
        _sendKey(widget, Qt.Key.Key_Left, "")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "dost"
    # The document cursor lands at the word's start (its visually right
    # edge), so the mirror map places the line edit cursor at the text end
    # (the visually right edge).
    assert overlay.lineEdit().cursorPosition() == 4

    # Walking Left reaches the visually left edge (the text start), where
    # the next Left edge-commits; no next word exists (only the paragraph's
    # trailing whitespace) -> the cursor lands at the word's end (position
    # 20) and the deactivation sticks: the overlay is closed at the
    # boundary word and stays closed — the mirror of the Right commit over
    # the first word.
    for _ in range(4):
        _sendKey(overlay.lineEdit(), Qt.Key.Key_Left, "")
    assert overlay.lineEdit().cursorPosition() == 0
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Left, "")
    assert widget.textCursor().position() == 20
    _assertNoOverlay(widget)

    # Right from دوست walks to its visually right edge, then edge-commits to
    # the previous word (خوش): the cursor lands at that word's edge facing
    # the active word (its end, 9), and the resync re-activates the overlay
    # over it.
    widget3 = PyRaya()
    widget3.show()
    widget3.setPlainText(text)
    widget3.setRomanInputEnabled(True)
    widget3.setRegionType(RegionType.RomanUrdu, 6, 20)
    _moveCursor(widget3, 17)
    overlay3 = widget3._overlay
    assert overlay3 is not None and overlay3.isVisible()
    assert overlay3.lineEdit().text() == "dost"
    # The document cursor sits one quarter of the way from the word's
    # visually right edge, so the mirror map places the line edit cursor the
    # same fraction from the text end (position 3 of "dost").
    assert overlay3.lineEdit().cursorPosition() == 3
    # Walk to the visually right edge (the text end).
    _sendKey(overlay3.lineEdit(), Qt.Key.Key_Right, "")
    assert overlay3.lineEdit().cursorPosition() == 4
    # Right at the end edge-commits to the previous word (خوش): the cursor
    # lands at that word's edge facing the active word (its end, 9), and the
    # resync re-activates the overlay over it (line edit cursor at the text
    # start, mirroring the word's end).
    _sendKey(overlay3.lineEdit(), Qt.Key.Key_Right, "")
    assert widget3.toPlainText() == text
    assert widget3.textCursor().position() == 9
    overlay3 = widget3._overlay
    assert overlay3 is not None and overlay3.isVisible()
    assert overlay3.lineEdit().text() == "khosh"
    assert overlay3.lineEdit().cursorPosition() == 0

    # Left from خوش walks to its visually left edge, then edge-commits to
    # the next word (دوست): the cursor lands at that word's edge facing the
    # active word (its start, 16, inside the word), and the resync jumps the
    # overlay to it.
    widget4 = PyRaya()
    widget4.show()
    widget4.setPlainText(text)
    widget4.setRomanInputEnabled(True)
    widget4.setRegionType(RegionType.RomanUrdu, 6, 20)
    _moveCursor(widget4, 7)
    overlay4 = widget4._overlay
    assert overlay4 is not None and overlay4.isVisible()
    assert overlay4.lineEdit().text() == "khosh"
    # The document cursor sits one third of the way from the word's visually
    # right edge, so the mirror map places the line edit cursor the same
    # fraction from the text end (position 3 of "khosh").
    assert overlay4.lineEdit().cursorPosition() == 3
    # Walk to the visually left edge (the text start).
    for _ in range(3):
        _sendKey(overlay4.lineEdit(), Qt.Key.Key_Left, "")
    assert overlay4.lineEdit().cursorPosition() == 0
    # Left at the start edge-commits to the next word (دوست): the cursor
    # lands at that word's edge facing the active word (its start, 16,
    # inside the word), and the resync jumps the overlay to it (line edit
    # cursor at the text end, mirroring the word's start).
    _sendKey(overlay4.lineEdit(), Qt.Key.Key_Left, "")
    assert widget4.toPlainText() == text
    assert widget4.textCursor().position() == 16
    overlay4 = widget4._overlay
    assert overlay4 is not None and overlay4.isVisible()
    assert overlay4.lineEdit().text() == "dost"
    assert overlay4.lineEdit().cursorPosition() == 4

    # A single-word document: Left from the interior reaches the visually
    # left edge, where the next Left overflows with no next word -> the
    # cursor lands at the word's end (9) and the deactivation sticks: the
    # overlay is closed at the boundary word.
    widget2 = PyRaya()
    widget2.show()
    widget2.setPlainText("world خوش")
    widget2.setRomanInputEnabled(True)
    widget2.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget2, 7)
    overlay2 = widget2._overlay
    assert overlay2 is not None and overlay2.isVisible()
    assert overlay2.lineEdit().text() == "khosh"
    # The document cursor sits one third of the way from the word's visually
    # right edge, so the mirror map places the line edit cursor the same
    # fraction from the text end (position 3 of "khosh").
    assert overlay2.lineEdit().cursorPosition() == 3
    # Walk to the visually left edge (the text start).
    for _ in range(3):
        _sendKey(overlay2.lineEdit(), Qt.Key.Key_Left, "")
    assert overlay2.lineEdit().cursorPosition() == 0
    # Left at the start overflows with no next word (only the document's
    # leading whitespace) -> the cursor lands at the word's end (9) and the
    # deactivation sticks: the overlay is closed at the boundary word.
    _sendKey(overlay2.lineEdit(), Qt.Key.Key_Left, "")
    assert widget2.toPlainText() == "world خوش"
    assert widget2.textCursor().position() == 9
    _assertNoOverlay(widget2)


# ******************************************************************************
def testEdgeCommitsAtBoundaryWordsWithWhitespace(app: QApplication) -> None:
    """Edge commits over a paragraph's boundary words close the overlay.

    A paragraph padded with leading and trailing whitespace has no word on
    the far side of its first or last word: a Right edge commit over the
    first word and a Left edge commit over the last word both find no
    adjacent word, close the overlay (the resync is skipped), and free the
    cursor at the boundary edge — the overlay stays closed until the next
    trigger.
    """
    widget = PyRaya()
    widget.show()
    text = "  خوش دوست "
    widget.setPlainText(text)
    widget.setRomanInputEnabled(True)

    # Right over the first word: no word on its far side (only the leading
    # whitespace) -> the commit closes the overlay and the cursor rests at
    # the word's start (2).
    _moveCursor(widget, 3)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"
    # The document cursor sits one third of the way from the word's visually
    # right edge, so the mirror map places the line edit cursor the same
    # fraction from the text end (position 3 of "khosh").
    assert overlay.lineEdit().cursorPosition() == 3
    # Walk to the visually right edge (the text end), then edge-commit.
    for _ in range(2):
        _sendKey(overlay.lineEdit(), Qt.Key.Key_Right, "")
    assert overlay.lineEdit().cursorPosition() == 5
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Right, "")
    assert widget.toPlainText() == text  # nothing inserted
    assert widget.textCursor().position() == 2
    _assertNoOverlay(widget)

    # Left over the last word: no word on its far side (only the trailing
    # whitespace) -> the commit closes the overlay and the cursor rests at
    # the word's end (10).
    _moveCursor(widget, 10)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "dost"
    # The document cursor is at the word's end (its visually left edge), so
    # the mirror map places the line edit cursor at the text start (the
    # visually left edge) — the commit edge, no walking needed.
    assert overlay.lineEdit().cursorPosition() == 0
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Left, "")
    assert widget.toPlainText() == text
    assert widget.textCursor().position() == 10
    _assertNoOverlay(widget)


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

    # every writing commit signals the region change; this one replaces
    # the tagged word with the committed word tagged the same way
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
    assert changed2 == [1]


# ******************************************************************************
def testRetaggingCommitEmitsRegionsChanged(app: QApplication) -> None:
    """A write commit that destroyed a region signals the region change.

    The commit replaces the user's selection (a Native island inside the
    RomanUrdu run) with the committed word: the region map changes, so
    ``regionsChanged`` fires for the writing commit.
    """
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.Native, 2, 4)  # "ll" is a Native island
    # The island exists as its own span in the resolved map: the untagged
    # surroundings resolve to the seed, and only the stored Native tag
    # breaks out of it.
    assert widget.regions() == [
        TextRegion(0, 2, RegionType.RomanUrdu),
        TextRegion(2, 4, RegionType.Native),
        TextRegion(4, 15, RegionType.RomanUrdu),
    ]
    cursor = widget.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(6, QTextCursor.MoveMode.KeepAnchor)
    widget.setTextCursor(cursor)
    _sendKey(widget, Qt.Key.Key_K, "k")  # seeds the overlay over the selection
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()

    changed = []
    widget.regionsChanged.connect(lambda: changed.append(1))
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    assert changed == [1]
    assert RegionType.Native not in [span.kind for span in widget.regions()]


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
    assert changed == [1]  # a writing commit signals the region change
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
def testUndefinedWordCommitScenario1And2(app: QApplication) -> None:
    """Committing the + [..] row goes through the dialog decision.

    The dialog decision happens in ``_onOverlayCommitted``: a canceling
    handler (``None``) commits the typed roman as-is — the session no-op:
    the word is written, nothing is learned — and an accepting handler
    (the chosen Arabic word) commits the learned word and emits
    ``wordAdded`` once (the handler path learns internally, so the counter
    lands at one, never two).
    """
    # scenario 1: typed at a bare cursor position past the span
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 10)
    committed: list[tuple[str, str]] = []
    emitted: list[str] = []
    widget.romanWordCommitted.connect(lambda w, r: committed.append((w, r)))
    widget.wordAdded.connect(lambda word: emitted.append(word))
    widget.setAddWordHandler(lambda _trigger: None)
    _moveCursor(widget, 10)  # the start of the Latin word (a bare position)
    _sendKey(widget, Qt.Key.Key_X, "x")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    overlay.setText("xqwzrty")  # zero matches -> undefined-word row
    row = overlay.suggestionList().selectedRow()
    assert row is not None and row.suggestion.isUndefined()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Space, " ")
    # The canceling handler: the typed roman commits as-is, nothing learned
    assert widget.toPlainText() == "hello خوش xqwzrty world"
    assert committed == [("xqwzrty", "xqwzrty")]
    assert emitted == []
    # localDictionary is unchanged (the handler canceled)
    assert list(widget.localDictionary().counter) == []
    widget.setAddWordHandler(None)  # restore the built-in dialog

    # scenario 2: the span-replacement commit learns through the handler
    widget2 = PyRaya()
    widget2.show()
    widget2.setPlainText("hello خوش world")
    widget2.setRomanInputEnabled(True)
    widget2.setRegionType(RegionType.RomanUrdu, 6, 9)
    committed2: list[tuple[str, str]] = []
    emitted2: list[str] = []
    widget2.romanWordCommitted.connect(lambda w, r: committed2.append((w, r)))
    widget2.wordAdded.connect(lambda word: emitted2.append(word))
    widget2.setAddWordHandler(lambda _trigger: "خلمق")
    _moveCursor(widget2, 7)
    overlay2 = widget2._overlay
    assert overlay2 is not None and overlay2.isVisible()
    overlay2.setText("xqwzrty")  # zero matches -> undefined-word row
    row2 = overlay2.suggestionList().selectedRow()
    assert row2 is not None and row2.suggestion.isUndefined()
    _sendKey(overlay2.lineEdit(), Qt.Key.Key_Space, " ")
    # The accepting handler: the span is replaced with the learned word
    # (tagged RomanUrdu), the typed roman is not written, and the learn
    # emits once. The Space separator lands beside the word's own trailing
    # space, so the two spaces both stay.
    assert widget2.toPlainText() == "hello خلمق  world"
    assert widget2._regionKindAt(6) == RegionType.RomanUrdu
    assert committed2 == [("خلمق", "xqwzrty")]
    assert emitted2 == ["خلمق"]
    assert widget2.localDictionary().counter["خلمق"] == 1
    assert widget2.localDictionary().isModified() is True
    widget2.setAddWordHandler(None)  # restore the built-in dialog


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
    assert overlay.suggestionList().rowCount() == 0  # no rows, no undefined-word row
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
def testEscOnActiveOverlayDismissesOnly(app: QApplication) -> None:
    """Esc on the active overlay dismisses it; assist mode stays on."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is True
    _assertNoOverlay(widget)


# ******************************************************************************
def testCtrlEscOnActiveOverlayTurnsAssistModeOff(app: QApplication) -> None:
    """Ctrl+Esc on the active overlay dismisses it and turns assist mode off:
    the user is left alone until Ctrl+Space or setAssistEnabled."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
    assert widget.isAssistEnabled() is False
    _assertNoOverlay(widget)


# ******************************************************************************
def testCtrlEscInDocumentTurnsAssistModeOff(app: QApplication) -> None:
    """Ctrl+Esc in the document turns assist mode off directly, balancing
    Ctrl+Space's re-entry; the overlay is already inactive, so no other
    visible effect."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is True  # plain Esc dismisses only
    _assertNoOverlay(widget)
    _sendKey(
        widget,
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
    assert widget.isAssistEnabled() is False
    _assertNoOverlay(widget)
    # Shift+Ctrl+Esc does not turn assist off (the exact-Ctrl gate).
    widget.setAssistEnabled(True)
    _sendKey(
        widget,
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert widget.isAssistEnabled() is True


# ******************************************************************************
def testTypingReactivatesOverlayAfterEscDismissal(app: QApplication) -> None:
    """A plain-Esc dismissal leaves assist on: a roman keystroke at the
    cursor seeds the overlay again by the normal assist rules."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is True
    _assertNoOverlay(widget)
    _sendKey(widget, Qt.Key.Key_K, "k")
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "k"


# ******************************************************************************
def testCursorMovementReactivatesOverlayAfterEscDismissal(app: QApplication) -> None:
    """A plain-Esc dismissal leaves assist on: moving the cursor back over
    a word re-activates the overlay by the normal assist rules."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is True
    _assertNoOverlay(widget)
    # Plain Left/Right move in visual (screen) order: Right retreats the
    # position, Left advances it. At 6 the cursor is still over the word
    # (a run start counts), so the overlay re-activates on the move.
    _sendKey(widget, Qt.Key.Key_Right)  # 7 -> 6, over the word: re-activates
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(widget, Qt.Key.Key_Right)  # 6 -> 5, past the word: dismisses
    _assertNoOverlay(widget)
    _sendKey(widget, Qt.Key.Key_Left)  # 5 -> 6, back over the word
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    assert overlay.lineEdit().text() == "khosh"


# ******************************************************************************
def testShiftEscOnActiveOverlayDismissesOnly(app: QApplication) -> None:
    """Shift+Esc on the active overlay dismisses it; assist mode stays on:
    the exact-Ctrl gate makes Ctrl+Esc the only dismiss-and-off key."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ShiftModifier,
    )
    assert widget.isAssistEnabled() is True
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
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
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
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
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
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
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
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
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
    _sendKey(
        overlay.lineEdit(),
        Qt.Key.Key_Escape,
        "",
        Qt.KeyboardModifier.ControlModifier,
    )
    assert widget.isAssistEnabled() is False
    widget.setRomanInputEnabled(False)
    widget.setRomanInputEnabled(True)
    assert widget.isAssistEnabled() is True


# ******************************************************************************
class _FakeMonotonic:
    """A controllable monotonic clock for deterministic double-tap tests.

    The double-tap rule keys off ``time.monotonic()``; the tests advance the
    clock explicitly rather than rely on wall-clock timing.
    """

    def __init__(self) -> None:
        self._t = 0.0

    def __call__(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt


# ******************************************************************************
def testDoubleEscInDocumentTurnsAssistModeOff(app: QApplication, monkeypatch) -> None:
    """Two quick Esc in the document (overlay inactive) turn assist mode off:
    the rule holds irrespective of overlay display."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    widget.setRomanInputEnabled(True)
    _moveCursor(widget, 1)
    clock = _FakeMonotonic()
    monkeypatch.setattr("pyraya.pyraya_widget.monotonic", clock)
    _sendKey(widget, Qt.Key.Key_Escape)  # first tap, at t=0.0
    assert widget.isAssistEnabled() is True  # a single Esc does not turn off
    clock.advance(0.1)  # within the 0.3 s interval
    _sendKey(widget, Qt.Key.Key_Escape)  # second tap, at t=0.1
    assert widget.isAssistEnabled() is False  # the double tap turns it off
    _assertNoOverlay(widget)


# ******************************************************************************
def testDoubleEscWithActiveOverlayTurnsAssistModeOff(app: QApplication, monkeypatch) -> None:
    """Two quick Esc starting from an active overlay turn assist mode off: the
    first Esc dismisses the overlay, the second Esc (in the document)
    completes the double tap."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    clock = _FakeMonotonic()
    monkeypatch.setattr("pyraya.pyraya_widget.monotonic", clock)
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape)  # first tap: dismiss, t=0.0
    assert widget.isAssistEnabled() is True  # a single Esc does not turn off
    _assertNoOverlay(widget)
    clock.advance(0.1)  # within the 0.3 s interval
    _sendKey(widget, Qt.Key.Key_Escape)  # second tap: in the document, t=0.1
    assert widget.isAssistEnabled() is False  # the double tap turns it off
    _assertNoOverlay(widget)


# ******************************************************************************
def testSingleEscDoesNotTurnAssistModeOff(app: QApplication, monkeypatch) -> None:
    """A single Esc records the tap but does not turn assist mode off."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    widget.setRomanInputEnabled(True)
    _moveCursor(widget, 1)
    clock = _FakeMonotonic()
    monkeypatch.setattr("pyraya.pyraya_widget.monotonic", clock)
    _sendKey(widget, Qt.Key.Key_Escape)
    assert widget.isAssistEnabled() is True
    _assertNoOverlay(widget)


# ******************************************************************************
def testSlowEscDoesNotTurnAssistModeOff(app: QApplication, monkeypatch) -> None:
    """A second Esc out of the double-tap interval does not turn assist mode
    off: only two quick Esc count as a double tap."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    widget.setRomanInputEnabled(True)
    _moveCursor(widget, 1)
    clock = _FakeMonotonic()
    monkeypatch.setattr("pyraya.pyraya_widget.monotonic", clock)
    _sendKey(widget, Qt.Key.Key_Escape)  # first tap, at t=0.0
    clock.advance(0.5)  # out of the 0.3 s interval
    _sendKey(widget, Qt.Key.Key_Escape)  # second tap, at t=0.5 (too slow)
    assert widget.isAssistEnabled() is True
    _assertNoOverlay(widget)

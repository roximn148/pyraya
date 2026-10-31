# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the application-wide shared engine holder.

Runs headless via the offscreen Qt platform so no window is opened.
"""

import os
from collections.abc import Generator
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QWidget
from romanalfaz.algorithm import tafseerUrduAr2Rm
from romanalfaz.engine import Vocabulary

from pyraya import AddWordDialog, PyRaya, RegionType
from pyraya.roman_input import RomanInputEngine, _sharedEngine


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
def testReplaceVocabularyInvalidatesCachedEngine(app: QApplication) -> None:
    """replaceVocabulary discards the cached engine and attaches the new Vocabulary."""
    engine_before = _sharedEngine.engine()
    newVocabulary = Vocabulary()
    _sharedEngine.replaceVocabulary(newVocabulary)
    engine_after = _sharedEngine.engine()
    assert engine_after is not engine_before
    # The new engine attaches the new Vocabulary, not the old one.
    assert engine_after._localVocabulary is newVocabulary
    assert engine_before._localVocabulary is not newVocabulary
    assert _sharedEngine.vocabulary is newVocabulary


# ******************************************************************************
def testResetRestoresFreshState(app: QApplication) -> None:
    """reset restores a fresh empty Vocabulary and discards the cached engine."""
    _sharedEngine.engine()
    _sharedEngine.reset()
    assert dict(_sharedEngine.vocabulary.counter) == {}
    assert _sharedEngine._engine is None


# ******************************************************************************
def testSharedVocabularyIsApplicationWide(app: QApplication) -> None:
    """Every widget borrows the same application-wide shared Vocabulary."""
    first = PyRaya()
    second = PyRaya()
    assert first.localDictionary() is second.localDictionary()
    word = "خلمق"
    first.localDictionary().add(word, isCompleted=True)
    assert second.localDictionary().counter[word] == 1


# ******************************************************************************
def testOneLearnTriggersOneNotification(app: QApplication) -> None:
    """One Vocabulary mutation triggers exactly one change callback."""
    widget = PyRaya()
    assert widget.localDictionary() is _sharedEngine.vocabulary
    notifications = 0

    def observe() -> None:
        nonlocal notifications
        notifications += 1

    callbacks = _sharedEngine.vocabulary.onChangeCallbacks
    callbacks.append(observe)
    try:
        word = "خلمق"
        widget.localDictionary().add(word, isCompleted=True)
    finally:
        callbacks.remove(observe)
    assert notifications == 1
    assert word in widget.localDictionary().completed


# ******************************************************************************
def testSharedEngineIsCreatedOnce(app: QApplication) -> None:
    """Both widgets borrow one lazily-created shared engine."""
    widget = PyRaya()
    other = PyRaya()
    assert _sharedEngine._engine is None
    assert widget.romanEngine() is other.romanEngine()
    assert _sharedEngine._engine is not None


# ******************************************************************************
def testLearnRomanWordMappabilityGate(app: QApplication) -> None:
    """An unmappable word raises AssertionError and mutates nothing."""
    vocabulary = Vocabulary()
    engine = RomanInputEngine(localVocabulary=vocabulary)
    notifications = 0

    def observe() -> None:
        nonlocal notifications
        notifications += 1

    callbacks = vocabulary.onChangeCallbacks
    callbacks.append(observe)
    try:
        with pytest.raises(AssertionError):
            engine.learnRomanWord("کA")
    finally:
        callbacks.remove(observe)
    assert dict(vocabulary.counter) == {}
    assert notifications == 0


# ******************************************************************************
def testLearnRomanWordSuccess(app: QApplication) -> None:
    """A mappable word is learned with one add(isCompleted=True) mutation."""
    vocabulary = Vocabulary()
    engine = RomanInputEngine(localVocabulary=vocabulary)
    notifications = 0

    def observe() -> None:
        nonlocal notifications
        notifications += 1

    callbacks = vocabulary.onChangeCallbacks
    callbacks.append(observe)
    try:
        result = engine.learnRomanWord("خلمق")
    finally:
        callbacks.remove(observe)
    assert result == "خلمق"
    assert dict(vocabulary.counter) == {"خلمق": 1}
    assert "خلمق" in vocabulary.completed
    assert notifications == 1
    assert vocabulary.isModified() is True


# ******************************************************************************
def testLearnRomanWordIdempotentRetry(app: QApplication) -> None:
    """A second learn increments the count and never duplicates the entry."""
    vocabulary = Vocabulary()
    engine = RomanInputEngine(localVocabulary=vocabulary)
    notifications = 0

    def observe() -> None:
        nonlocal notifications
        notifications += 1

    callbacks = vocabulary.onChangeCallbacks
    callbacks.append(observe)
    try:
        engine.learnRomanWord("خلمق")
        engine.learnRomanWord("خلمق")
    finally:
        callbacks.remove(observe)
    assert dict(vocabulary.counter) == {"خلمق": 2}
    assert len(vocabulary.counter) == 1
    assert notifications == 2


# ******************************************************************************
def testLearnRomanWordRequiresVocabulary(app: QApplication) -> None:
    """A bare engine (no localVocabulary) raises AssertionError."""
    engine = RomanInputEngine()
    with pytest.raises(AssertionError):
        engine.learnRomanWord("خلمق")


# ******************************************************************************
def testAddWordDialogPrefillsAndReturnsWord(app: QApplication) -> None:
    """The dialog prefills its field and returns the word after accept."""
    dialog = AddWordDialog(prefill="خلمق")
    assert dialog._field.text() == "خلمق"
    dialog.accept()
    assert dialog.word() == "خلمق"


# ******************************************************************************
def testAddWordDialogPreviewTracksMappability(app: QApplication) -> None:
    """The preview tracks mappability and the OK button follows it."""
    dialog = AddWordDialog()
    okButton = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    # A mappable word: the preview shows the lowercased roman form, OK enabled.
    dialog._field.setText("خلمق")
    encoded, undef = tafseerUrduAr2Rm("خلمق")
    assert undef == 0
    assert dialog._preview.text() == encoded.lower()
    assert okButton.isEnabled() is True
    # An unmappable word: the preview names the unmappable count, OK disabled.
    dialog._field.setText("کA")
    assert dialog._preview.text() == "unmappable: 1 character"
    assert okButton.isEnabled() is False
    # Clearing the field disables OK again.
    dialog._field.clear()
    assert okButton.isEnabled() is False


# ******************************************************************************
def testAddWordDialogEmptyFieldDisablesOk(app: QApplication) -> None:
    """A fresh dialog with an empty field has a disabled OK button."""
    dialog = AddWordDialog()
    assert dialog._field.text() == ""
    assert dialog.word() == ""
    okButton = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert okButton.isEnabled() is False
    # An empty field with no hint shows the placeholder; a hint shows instead.
    assert dialog._preview.text() == "\u2014"
    hinted = AddWordDialog(hint="khlmq")
    assert hinted._preview.text() == "khlmq"


# ******************************************************************************
def testSetAddWordHandlerLearnsViaHandler(app: QApplication) -> None:
    """An installed handler replaces the built-in dialog and learns its pick."""
    widget = PyRaya()
    widget.setAddWordHandler(lambda _trigger: "خلمق")
    learned = widget._learnDialog("xqm")
    assert learned == "خلمق"
    assert widget.localDictionary().counter["خلمق"] == 1
    assert widget.localDictionary().isModified() is True


# ******************************************************************************
def testLearnDialogBuiltInAccepted(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """The built-in dialog path learns the accepted word into the shared Vocabulary."""
    widget = PyRaya()
    monkeypatch.setattr(AddWordDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    assert widget._learnDialog("قلم", prefill="قلم") == "قلم"
    assert widget.localDictionary().counter["قلم"] == 1
    assert widget.localDictionary().isModified() is True


# ******************************************************************************
def testLearnDialogBuiltInRejected(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejected built-in dialog returns None and mutates nothing."""
    widget = PyRaya()
    monkeypatch.setattr(AddWordDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    assert widget._learnDialog("xqm") is None
    assert dict(widget.localDictionary().counter) == {}


# ******************************************************************************
def testLearnWordEmitsWordAddedOnce(app: QApplication) -> None:
    """_learnWord emits wordAdded exactly once and touches no document state."""
    widget = PyRaya()
    emitted: list[str] = []
    widget.wordAdded.connect(lambda word: emitted.append(word))
    widget._learnWord("خلمق")
    assert emitted == ["خلمق"]
    assert widget.localDictionary().isModified() is True
    assert widget.document().availableUndoSteps() == 0


# ******************************************************************************
def testDialogPathAddsNoUndoSteps(app: QApplication) -> None:
    """The handler-OK dialog path adds no undo steps to a non-empty document."""
    widget = PyRaya()
    widget.setPlainText("hello")
    baseline = widget.document().availableUndoSteps()
    widget.setAddWordHandler(lambda _trigger: "خلمق")
    assert widget._learnDialog("xqm") == "خلمق"
    assert widget.document().availableUndoSteps() == baseline


# ******************************************************************************
def _moveCursor(widget: PyRaya, position: int) -> None:
    """Move the widget's document cursor to a character offset."""
    cursor = widget.textCursor()
    cursor.setPosition(position)
    widget.setTextCursor(cursor)


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


# ******************************************************************************
def testAddToDictionaryActionAppearsOverUnknownWord(app: QApplication) -> None:
    """The context menu offers "Add to dictionary" over an unknown word.

    Both the untagged (seed-resolved) and the explicitly tagged run offer
    the action.
    """
    widget = PyRaya()
    widget.setSpellCheckEnabled(False)
    widget.setPlainText("کتاب خلمق")
    assert widget._ensureEngine().hasWord("خلمق") is False
    _moveCursor(widget, 6)  # inside خلمق
    menu = widget.createPopupMenu()
    byText = {action.text(): action for action in menu.actions()}
    assert "Add to dictionary" in byText
    # Repeat with an explicitly tagged RomanUrdu run over the same word.
    widget.setRegionType(RegionType.RomanUrdu, 5, 9)
    menu = widget.createPopupMenu()
    byText = {action.text(): action for action in menu.actions()}
    assert "Add to dictionary" in byText


# ******************************************************************************
def testAddToDictionaryActionHiddenOverKnownWord(app: QApplication) -> None:
    """A word the dictionary already knows offers no learn action."""
    widget = PyRaya()
    widget.setPlainText("کتاب خلمق")
    assert widget._ensureEngine().hasWord("کتاب") is True
    _moveCursor(widget, 1)  # inside کتاب
    menu = widget.createPopupMenu()
    assert "Add to dictionary" not in {action.text() for action in menu.actions()}


# ******************************************************************************
def testAddToDictionaryActionHiddenOverNativeRegion(app: QApplication) -> None:
    """A run tagged Native offers no learn action: only RomanUrdu words
    are candidates, the stored tag wins over the seed."""
    widget = PyRaya()
    widget.setPlainText("کتاب خلمق")
    widget.setRegionType(RegionType.Native, 5, 9)
    _moveCursor(widget, 6)  # inside the Native-tagged خلمق
    menu = widget.createPopupMenu()
    assert "Add to dictionary" not in {action.text() for action in menu.actions()}


# ******************************************************************************
def testAddToDictionaryActionHiddenOverWhitespaceLatin(app: QApplication) -> None:
    """A cursor over whitespace or a Latin word offers no learn action."""
    widget = PyRaya()
    widget.setPlainText("hello world خلمق")
    _moveCursor(widget, 5)  # the space after "hello"
    menu = widget.createPopupMenu()
    assert "Add to dictionary" not in {action.text() for action in menu.actions()}
    _moveCursor(widget, 7)  # inside "world"
    menu = widget.createPopupMenu()
    assert "Add to dictionary" not in {action.text() for action in menu.actions()}


# ******************************************************************************
def testAddToDictionaryActionHiddenWithSelection(app: QApplication) -> None:
    """A selection spanning the unknown word offers no learn action."""
    widget = PyRaya()
    widget.setPlainText("کتاب خلمق")
    cursor = widget.textCursor()
    cursor.setPosition(5)
    cursor.setPosition(9, QTextCursor.MoveMode.KeepAnchor)
    widget.setTextCursor(cursor)
    menu = widget.createPopupMenu()
    assert "Add to dictionary" not in {action.text() for action in menu.actions()}


# ******************************************************************************
def testAddToDictionaryLearnsAndClearsUnderline(app: QApplication) -> None:
    """The learn action learns the word and its underline clears.

    The menu-trigger path is the same callable; the handler accepts the
    prefilled word, ``wordAdded`` fires once, and the spell-check underline
    for the word is gone from the text layouts.
    """
    widget = PyRaya()
    widget.setPlainText("کتاب خلمق")
    assert [(start, end) for start, end, _, _ in _underlinedRanges(widget)] == [(5, 9)]
    emitted: list[str] = []
    widget.wordAdded.connect(lambda word: emitted.append(word))
    widget.setAddWordHandler(lambda _trigger: "خلمق")
    widget._addToDictionary("خلمق")
    assert emitted == ["خلمق"]
    assert widget.localDictionary().counter["خلمق"] == 1
    assert _underlinedRanges(widget) == []


# ******************************************************************************
def testAddToDictionaryCancelLearnsNothing(app: QApplication) -> None:
    """A canceling handler leaves the Vocabulary untouched and emits nothing."""
    widget = PyRaya()
    widget.setPlainText("کتاب خلمق")
    emitted: list[str] = []
    widget.wordAdded.connect(lambda word: emitted.append(word))
    widget.setAddWordHandler(lambda _trigger: None)
    widget._addToDictionary("خلمق")
    assert emitted == []
    assert dict(widget.localDictionary().counter) == {}


# ******************************************************************************
def testLearnRowEdgeCommitSkipsDialog(app: QApplication) -> None:
    """A Left edge commit over the + Learn row moves without a dialog.

    Edge commits write nothing and move in visual order, so they stay
    dialog-free: the handler spy is never called and the Vocabulary stays
    untouched.
    """
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world")
    widget.setRomanInputEnabled(True)
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    calls: list[str] = []

    def handler(trigger: str) -> str | None:
        calls.append(trigger)
        return None

    widget.setAddWordHandler(handler)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    overlay.setText("xqwzrty")  # zero matches -> undefined-word row
    row = overlay.suggestionList().selectedRow()
    assert row is not None and row.suggestion.isUndefined()
    # Walk to the visually left edge (the text start); the next Left
    # edge-commits.
    for _ in range(7):
        _sendKey(overlay.lineEdit(), Qt.Key.Key_Left, "")
    assert overlay.lineEdit().cursorPosition() == 0
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Left, "")
    # Nothing is written: no adjacent Arabic word past the boundary, so the
    # cursor rests at the word's end and the deactivation sticks.
    assert widget.toPlainText() == "hello خوش world"
    assert widget.textCursor().position() == 9
    assert widget._overlay is None or not widget._overlay.isVisible()
    assert calls == []
    assert dict(widget.localDictionary().counter) == {}

# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Smoke test for the PyRaya widget.

Runs headless via the offscreen Qt platform so no window is opened.
"""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QKeyEvent,
    QMouseEvent,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import QApplication, QMenu, QPlainTextEdit

from pyraya import (
    PyRaya,
    PyRayaHighlighter,
    RegionColors,
    RegionType,
    TextRegion,
    defaultRegionKind,
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
def testPyrayaInstantiates(app: QApplication) -> None:
    """A PyRaya widget can be created under an offscreen QApplication."""
    widget = PyRaya()
    assert isinstance(widget, PyRaya)


# ******************************************************************************
def testPyrayaIsPlainTextEdit(app: QApplication) -> None:
    """PyRaya derives from QPlainTextEdit."""
    widget = PyRaya()
    assert isinstance(widget, QPlainTextEdit)


# ******************************************************************************
def testPyrayaRtlDirection(app: QApplication) -> None:
    """PyRaya sets the widget layout direction to right-to-left."""
    widget = PyRaya()
    assert widget.layoutDirection() == Qt.LayoutDirection.RightToLeft


# ******************************************************************************
def testPyrayaRightAlignment(app: QApplication) -> None:
    """PyRaya right-aligns its text blocks by default."""
    widget = PyRaya()
    block = widget.document().begin()
    assert block.blockFormat().alignment() == Qt.AlignmentFlag.AlignRight


# ******************************************************************************
def testPyrayaShowWhitespace(app: QApplication) -> None:
    """PyRaya enables the ShowTabsAndSpaces text option by default."""
    widget = PyRaya()
    option = widget.document().defaultTextOption()
    assert option.flags() & QTextOption.Flag.ShowTabsAndSpaces


# ******************************************************************************
def testPyrayaHighlighterAttached(app: QApplication) -> None:
    """PyRaya owns a dedicated formatting highlighter with default rules."""
    widget = PyRaya()
    assert isinstance(widget.highlighter, PyRayaHighlighter)
    assert len(widget.highlighter.rules) > 0


# ******************************************************************************
def _select(widget: PyRaya, start: int, end: int) -> None:
    """Select a character range on the widget's text cursor."""
    cursor = widget.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    widget.setTextCursor(cursor)


# ******************************************************************************
def _keyPress(widget: PyRaya, key: int, modifiers: Qt.KeyboardModifier, text: str = "") -> None:
    """Send a key-press event to the widget."""
    QCoreApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text))


# ******************************************************************************
def testRegionTypesDefined() -> None:
    """Exactly the two initial region types exist."""
    assert set(RegionType) == {RegionType.Latin, RegionType.RomanUrdu}


# ******************************************************************************
def testRegionColorsAreDistinctAndSubtle() -> None:
    """Default region colors are distinct from each other and semi-transparent."""
    latin = RegionColors[RegionType.Latin]
    roman = RegionColors[RegionType.RomanUrdu]
    assert latin != roman
    assert 0 < latin.alpha() < 255
    assert 0 < roman.alpha() < 255


# ******************************************************************************
def testRegionsStartEmpty(app: QApplication) -> None:
    """A fresh PyRaya widget has no text regions."""
    widget = PyRaya()
    assert widget.regions() == []


# ******************************************************************************
def testSetRegionTypeFromSelection(app: QApplication) -> None:
    """Tagging the current selection retags it; the surrounding text
    belongs to the default kind."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    widget.setRegionType(RegionType.Latin)
    assert widget.regions() == [
        TextRegion(0, 1, defaultRegionKind),
        TextRegion(1, 3, RegionType.Latin),
        TextRegion(3, 4, defaultRegionKind),
    ]


# ******************************************************************************
def testSetRegionTypeExplicitRange(app: QApplication) -> None:
    """Tagging an explicit range with the default kind leaves one default
    span covering the whole text."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.setRegionType(RegionType.RomanUrdu, 2, 5)
    assert widget.regions() == [TextRegion(0, 10, defaultRegionKind)]


# ******************************************************************************
def testSetRegionTypeNoSelectionIsNoop(app: QApplication) -> None:
    """Tagging without a selection or explicit range is a no-op; the text
    still belongs to the default kind."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin)
    assert widget.regions() == [TextRegion(0, 4, defaultRegionKind)]


# ******************************************************************************
def testSetRegionTypeSplitsAndRetags(app: QApplication) -> None:
    """Retagging part of the text splits it; the surrounding text belongs
    to the default kind."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.setRegionType(RegionType.Latin, 2, 7)
    assert widget.regions() == [
        TextRegion(0, 2, defaultRegionKind),
        TextRegion(2, 7, RegionType.Latin),
        TextRegion(7, 10, defaultRegionKind),
    ]


# ******************************************************************************
def testSetRegionTypeMergesAdjacent(app: QApplication) -> None:
    """Adjacent same-type spans merge into one region; the surrounding
    text belongs to the default kind."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.setRegionType(RegionType.Latin, 0, 3)
    widget.setRegionType(RegionType.Latin, 3, 6)
    assert widget.regions() == [
        TextRegion(0, 6, RegionType.Latin),
        TextRegion(6, 10, defaultRegionKind),
    ]


# ******************************************************************************
def testRegionSpansBlocks(app: QApplication) -> None:
    """A region may span multiple text blocks; the surrounding text
    belongs to the default kind."""
    widget = PyRaya()
    widget.setPlainText("ab\ncd")
    widget.setRegionType(RegionType.Latin, 1, 4)
    assert widget.regions() == [
        TextRegion(0, 1, defaultRegionKind),
        TextRegion(1, 4, RegionType.Latin),
        TextRegion(4, 5, defaultRegionKind),
    ]


# ******************************************************************************
def testRegionPersistsThroughInsertion(app: QApplication) -> None:
    """Inserting text before a region shifts the span; the inserted text
    belongs to the default kind."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(0)
    cursor.insertText("X")
    assert widget.regions() == [
        TextRegion(0, 2, defaultRegionKind),
        TextRegion(2, 4, RegionType.Latin),
        TextRegion(4, 5, defaultRegionKind),
    ]


# ******************************************************************************
def testRegionPersistsThroughDeletion(app: QApplication) -> None:
    """Deleting text before a region shifts the span; the remaining text
    belongs to the default kind."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(0)
    cursor.deleteChar()
    assert widget.regions() == [
        TextRegion(0, 2, RegionType.Latin),
        TextRegion(2, 3, defaultRegionKind),
    ]


# ******************************************************************************
def testRegionPersistsThroughUndoRedo(app: QApplication) -> None:
    """Region state survives undo and redo because it lives in the
    document."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(4)
    cursor.insertText("e")
    assert widget.regions() == [
        TextRegion(0, 1, defaultRegionKind),
        TextRegion(1, 3, RegionType.Latin),
        TextRegion(3, 5, defaultRegionKind),
    ]
    widget.undo()
    assert widget.regions() == [
        TextRegion(0, 1, defaultRegionKind),
        TextRegion(1, 3, RegionType.Latin),
        TextRegion(3, 4, defaultRegionKind),
    ]
    widget.redo()
    assert widget.regions() == [
        TextRegion(0, 1, defaultRegionKind),
        TextRegion(1, 3, RegionType.Latin),
        TextRegion(3, 5, defaultRegionKind),
    ]


# ******************************************************************************
def testSetTextRetagsAsDefault(app: QApplication) -> None:
    """Replacing the document text retags all text with the default kind."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 0, 4)
    widget.setPlainText("efgh")
    assert widget.regions() == [TextRegion(0, 4, defaultRegionKind)]


# ******************************************************************************
def testRegionTypeAt(app: QApplication) -> None:
    """regionTypeAt reports the kind covering each offset; untagged text
    reports the default kind."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 1, 3)
    assert widget.regionTypeAt(0) is defaultRegionKind
    assert widget.regionTypeAt(1) is RegionType.RomanUrdu
    assert widget.regionTypeAt(2) is RegionType.RomanUrdu
    assert widget.regionTypeAt(3) is defaultRegionKind


# ******************************************************************************
def testClearRegionsResetsToDefault(app: QApplication) -> None:
    """clearRegions resets all text to the default kind."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 1, 3)
    widget.clearRegions()
    assert widget.regions() == [TextRegion(0, 4, defaultRegionKind)]


# ******************************************************************************
def testSetRegionColorRecolours(app: QApplication) -> None:
    """setRegionColor recolors existing regions and updates the default."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 0, 4)
    original = RegionColors[RegionType.Latin]
    newColor = QColor("#34D399")
    try:
        widget.setRegionColor(RegionType.Latin, newColor)
        assert widget.regionTypeAt(1) is RegionType.Latin
        assert RegionColors[RegionType.Latin].name() == newColor.name()
    finally:
        RegionColors[RegionType.Latin] = original


# ******************************************************************************
def testPopupMenuRegionActions(app: QApplication) -> None:
    """The context menu exposes enabled region actions and clears regions."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    widget.setRegionType(RegionType.Latin)

    menu = widget.createPopupMenu()
    byText = {action.text(): action for action in menu.actions()}
    assert "Region: Latin" in byText
    assert "Region: Roman Urdu" in byText
    assert "Clear region under cursor" in byText
    assert "Clear all regions" in byText
    assert byText["Region: Latin"].isEnabled()
    assert byText["Clear region under cursor"].isEnabled()
    assert byText["Clear all regions"].isEnabled()

    byText["Clear region under cursor"].trigger()
    assert widget.regions() == [TextRegion(0, 4, defaultRegionKind)]


# ******************************************************************************
def testPopupMenuDisabledWithoutSelection(app: QApplication) -> None:
    """Region actions are disabled without a selection; clearing resets the
    text to the default kind, so clear-all stays enabled for non-empty
    text."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 1, 3)

    menu = widget.createPopupMenu()
    byText = {action.text(): action for action in menu.actions()}
    assert not byText["Region: Latin"].isEnabled()
    assert not byText["Region: Roman Urdu"].isEnabled()
    assert byText["Clear all regions"].isEnabled()

    widget.clearRegions()
    assert widget.regions() == [TextRegion(0, 4, defaultRegionKind)]
    menu2 = widget.createPopupMenu()
    byText2 = {action.text(): action for action in menu2.actions()}
    assert byText2["Clear all regions"].isEnabled()


# ******************************************************************************
def testRegionsChangedSignal(app: QApplication) -> None:
    """regionsChanged emits when regions are added or cleared."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    fired: list[int] = []
    widget.regionsChanged.connect(lambda: fired.append(1))
    widget.setRegionType(RegionType.Latin, 0, 4)
    widget.clearRegions()
    assert len(fired) == 2


# ******************************************************************************
def testContextMenuPolicyIsCustom(app: QApplication) -> None:
    """PyRaya suppresses Qt's automatic popup via CustomContextMenu."""
    widget = PyRaya()
    assert widget.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


# ******************************************************************************
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def testCustomContextMenuRequestedShowsPopup(app: QApplication) -> None:
    """A context menu request received by the widget shows the popup menu.

    The platform delivers the context menu event to the widget's viewport
    (the scroll area's viewport event filter then emits
    ``customContextMenuRequested``), so the test sends it there. The
    synthetic ``QContextMenuEvent`` constructor is deprecated in Qt 6 and
    only exists for tests like this one.
    """
    shown: list[tuple[QMenu, QPoint]] = []

    class Probe(PyRaya):
        def _showPopup(self, menu: QMenu, position: QPoint) -> None:
            shown.append((menu, position))

    widget = Probe()
    widget.setPlainText("abcd")
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10))
    QCoreApplication.sendEvent(widget.viewport(), event)
    assert len(shown) == 1
    assert shown[0][1] == widget.viewport().mapToGlobal(QPoint(10, 10))

    # A mouse event does not trigger the popup.
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPoint(5, 5),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QCoreApplication.sendEvent(widget, move)
    assert len(shown) == 1


# ******************************************************************************
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def testContextMenuAtTextEdgesNoOutOfRangeCursor(app: QApplication, capfd) -> None:
    """Right-clicking an empty widget, or with the cursor at the end of the
    text, builds the popup without requesting an out-of-range cursor.

    The document keeps an implicit trailing terminator character, so a
    cursor at the end of the text sits at ``characterCount() - 1``. Region
    lookups from the popup must guard that offset; Qt builds that warn on
    out-of-range ``QTextCursor::setPosition`` calls report
    ``Position 'N' out of range``.
    """
    shown: list[QMenu] = []

    class Probe(PyRaya):
        def _showPopup(self, menu: QMenu, position: QPoint) -> None:
            shown.append(menu)

    widget = Probe()
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10))
    QCoreApplication.sendEvent(widget.viewport(), event)
    assert len(shown) == 1

    widget.setPlainText("0123456789abcdef")
    widget.setRegionType(RegionType.Latin, 14, 16)
    cursor = widget.textCursor()
    cursor.setPosition(widget.document().characterCount() - 1)
    widget.setTextCursor(cursor)
    QCoreApplication.sendEvent(widget.viewport(), event)
    assert len(shown) == 2
    assert "out of range" not in capfd.readouterr().err.lower()


# ******************************************************************************
def testRegionTypeAtTerminatorOffsetIsNone(app: QApplication) -> None:
    """regionTypeAt returns None at the trailing terminator offset."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 0, 4)
    assert widget.regionTypeAt(4) is None


# ******************************************************************************
def testKeyboardShortcutsAssignRegions(app: QApplication) -> None:
    """Ctrl+1 tags the selection as Latin and Ctrl+2 as Roman Urdu (the
    default kind), so Ctrl+2 on a Latin region resets it to the
    default."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == [
        TextRegion(0, 1, defaultRegionKind),
        TextRegion(1, 3, RegionType.Latin),
        TextRegion(3, 10, defaultRegionKind),
    ]
    assert widget.toPlainText() == "abcdefghij"

    _keyPress(widget, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == [TextRegion(0, 10, defaultRegionKind)]
    assert widget.toPlainText() == "abcdefghij"


# ******************************************************************************
def testKeyboardShortcutsIgnoredWithoutSelection(app: QApplication) -> None:
    """Ctrl+1 / Ctrl+2 do nothing without a selection; typing a
    non-roman character is unaffected and belongs to the default kind."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _keyPress(widget, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == [TextRegion(0, 4, defaultRegionKind)]

    _keyPress(widget, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, " ")
    assert widget.toPlainText() == " abcd"
    assert widget.regions() == [TextRegion(0, 5, defaultRegionKind)]


# ******************************************************************************
def testDefaultRegionKindIsDefined() -> None:
    """defaultRegionKind is a RegionType member."""
    assert defaultRegionKind in set(RegionType)
    assert defaultRegionKind is RegionType.RomanUrdu


# ******************************************************************************
def testSetPlainTextTagsAllTextAsDefault(app: QApplication) -> None:
    """Text set on the widget belongs to the default kind immediately."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    assert widget.regions() == [TextRegion(0, 4, defaultRegionKind)]
    assert all(widget.regionTypeAt(p) is defaultRegionKind for p in range(4))


# ******************************************************************************
def testFirstTypedCharacterGetsDefaultKind(app: QApplication) -> None:
    """A first character typed into an empty document belongs to the
    default kind."""
    widget = PyRaya()
    cursor = widget.textCursor()
    cursor.insertText("a")
    assert widget.regions() == [TextRegion(0, 1, defaultRegionKind)]


# ******************************************************************************
def testRegionsChangedFiresForDefaultRepaint(app: QApplication) -> None:
    """regionsChanged fires when a document change requires the default-kind
    repaint, and not when the text already carries region backgrounds."""
    widget = PyRaya()
    fired: list[int] = []
    widget.regionsChanged.connect(lambda: fired.append(1))
    widget.setPlainText("abcd")
    assert len(fired) == 1
    widget.setPlainText("efgh")
    assert len(fired) == 2


# ******************************************************************************
def testFreshWidgetHasNoUndoHistory(app: QApplication) -> None:
    """A fresh PyRaya widget has no undoable commands behind it."""
    widget = PyRaya()
    assert not widget.document().isUndoAvailable()


# ******************************************************************************
def testUndoOfTypedTextIsClean(app: QApplication) -> None:
    """Undoing a typed character restores the previous text; the
    maintenance repaint does not leave an undo command that buries the edit
    (undo/redo ping-pong)."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    cursor = widget.textCursor()
    cursor.setPosition(4)
    cursor.insertText("e")
    assert widget.document().isUndoAvailable()
    widget.undo()
    assert widget.toPlainText() == "abcd"
    assert not widget.document().isUndoAvailable()
    widget.redo()
    assert widget.toPlainText() == "abcde"


# ******************************************************************************
def testUndoOfFirstTypedCharacterDeletesIt(app: QApplication) -> None:
    """Undoing the first character typed into an empty document deletes it."""
    widget = PyRaya()
    cursor = widget.textCursor()
    cursor.insertText("a")
    widget.undo()
    assert widget.toPlainText() == ""
    assert not widget.document().isUndoAvailable()
    widget.redo()
    assert widget.toPlainText() == "a"


# ******************************************************************************
def testSetRegionColorRejectsDuplicateColor(app: QApplication) -> None:
    """setRegionColor rejects a color equal to another kind's color,
    including the alpha channel, and leaves the state unchanged."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 2, 4)
    originalRoman = RegionColors[RegionType.RomanUrdu]
    try:
        assert widget.setRegionColor(RegionType.RomanUrdu, QColor(0x60, 0xA5, 0xFA, 30)) is False
        assert widget.regions() == [TextRegion(0, 4, defaultRegionKind)]
    finally:
        RegionColors[RegionType.RomanUrdu] = originalRoman


# ******************************************************************************
def testSetRegionColorAlphaIsIdentity(app: QApplication) -> None:
    """Colors are unique identities including the alpha channel: two kinds
    may share RGB values when their alpha values differ."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 2, 4)
    originalRoman = RegionColors[RegionType.RomanUrdu]
    try:
        assert widget.setRegionColor(RegionType.RomanUrdu, QColor(0x60, 0xA5, 0xFA, 100)) is True
        assert widget.regions() == [TextRegion(0, 4, defaultRegionKind)]
        assert widget.regionTypeAt(3) is RegionType.RomanUrdu
        assert widget.regionTypeAt(1) is defaultRegionKind
    finally:
        RegionColors[RegionType.RomanUrdu] = originalRoman


# ******************************************************************************

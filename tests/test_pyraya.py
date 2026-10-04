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

from pyraya import PyRaya, PyRayaHighlighter, RegionType, TextRegion, RegionColors


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
    """Tagging the current selection creates a region span."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    widget.setRegionType(RegionType.RomanUrdu)
    assert widget.regions() == [TextRegion(1, 3, RegionType.RomanUrdu)]


# ******************************************************************************
def testSetRegionTypeExplicitRange(app: QApplication) -> None:
    """Tagging an explicit character range creates a region span."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.setRegionType(RegionType.Latin, 2, 5)
    assert widget.regions() == [TextRegion(2, 5, RegionType.Latin)]


# ******************************************************************************
def testSetRegionTypeNoSelectionIsNoop(app: QApplication) -> None:
    """Tagging without a selection or explicit range is a no-op."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin)
    assert widget.regions() == []


# ******************************************************************************
def testSetRegionTypeSplitsAndRetags(app: QApplication) -> None:
    """Retagging part of a region splits it and merges around the new span."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.setRegionType(RegionType.Latin, 0, 5)
    widget.setRegionType(RegionType.RomanUrdu, 2, 7)
    assert widget.regions() == [
        TextRegion(0, 2, RegionType.Latin),
        TextRegion(2, 7, RegionType.RomanUrdu),
    ]


# ******************************************************************************
def testSetRegionTypeMergesAdjacent(app: QApplication) -> None:
    """Adjacent same-type spans merge into one region."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.setRegionType(RegionType.Latin, 0, 3)
    widget.setRegionType(RegionType.Latin, 3, 6)
    assert widget.regions() == [TextRegion(0, 6, RegionType.Latin)]


# ******************************************************************************
def testRegionSpansBlocks(app: QApplication) -> None:
    """A region may span multiple text blocks."""
    widget = PyRaya()
    widget.setPlainText("ab\ncd")
    widget.setRegionType(RegionType.RomanUrdu, 1, 4)
    assert widget.regions() == [TextRegion(1, 4, RegionType.RomanUrdu)]


# ******************************************************************************
def testRegionPersistsThroughInsertion(app: QApplication) -> None:
    """Inserting text before a region shifts the span."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(0)
    cursor.insertText("X")
    assert widget.regions() == [TextRegion(2, 4, RegionType.Latin)]


# ******************************************************************************
def testRegionPersistsThroughDeletion(app: QApplication) -> None:
    """Deleting text before a region shifts the span."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(0)
    cursor.deleteChar()
    assert widget.regions() == [TextRegion(0, 2, RegionType.Latin)]


# ******************************************************************************
def testRegionPersistsThroughUndoRedo(app: QApplication) -> None:
    """Region state survives undo and redo because it lives in the document."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(4)
    cursor.insertText("e")
    assert widget.regions() == [TextRegion(1, 3, RegionType.Latin)]
    widget.undo()
    assert widget.regions() == [TextRegion(1, 3, RegionType.Latin)]
    widget.redo()
    assert widget.regions() == [TextRegion(1, 3, RegionType.Latin)]


# ******************************************************************************
def testSetTextClearsRegions(app: QApplication) -> None:
    """Replacing the document text removes its region state."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 0, 4)
    widget.setPlainText("efgh")
    assert widget.regions() == []


# ******************************************************************************
def testRegionTypeAt(app: QApplication) -> None:
    """regionTypeAt reports the kind covering each offset."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 1, 3)
    assert widget.regionTypeAt(0) is None
    assert widget.regionTypeAt(1) is RegionType.RomanUrdu
    assert widget.regionTypeAt(2) is RegionType.RomanUrdu
    assert widget.regionTypeAt(3) is None


# ******************************************************************************
def testClearRegions(app: QApplication) -> None:
    """clearRegions removes every region."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 0, 4)
    widget.clearRegions()
    assert widget.regions() == []


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
    assert widget.regions() == []


# ******************************************************************************
def testPopupMenuDisabledWithoutSelection(app: QApplication) -> None:
    """Region actions are disabled without a selection; clearing tracks state."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Latin, 0, 4)

    menu = widget.createPopupMenu()
    byText = {action.text(): action for action in menu.actions()}
    assert not byText["Region: Latin"].isEnabled()
    assert not byText["Region: Roman Urdu"].isEnabled()
    assert byText["Clear all regions"].isEnabled()

    widget.clearRegions()
    menu2 = widget.createPopupMenu()
    byText2 = {action.text(): action for action in menu2.actions()}
    assert not byText2["Clear all regions"].isEnabled()


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
    """Ctrl+1 and Ctrl+2 tag the current selection as Latin or Roman Urdu."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == [TextRegion(1, 3, RegionType.Latin)]
    assert widget.toPlainText() == "abcdefghij"

    _select(widget, 4, 6)
    _keyPress(widget, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == [
        TextRegion(1, 3, RegionType.Latin),
        TextRegion(4, 6, RegionType.RomanUrdu),
    ]
    assert widget.toPlainText() == "abcdefghij"


# ******************************************************************************
def testKeyboardShortcutsIgnoredWithoutSelection(app: QApplication) -> None:
    """Ctrl+1 / Ctrl+2 do nothing without a selection; typing is unaffected."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _keyPress(widget, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == []

    _keyPress(widget, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier, "1")
    assert widget.toPlainText() == "1abcd"


# ******************************************************************************

# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Smoke test for the PyRaya widget.

Runs headless via the offscreen Qt platform so no window is opened.
"""

import os
from collections.abc import Generator
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QKeyEvent,
    QMouseEvent,
    QTextCharFormat,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import QApplication, QMenu, QPlainTextEdit

from pyraya import (
    PyRaya,
    PyRayaHighlighter,
    RegionColors,
    RegionKindProperty,
    RegionType,
    SeedRegionKind,
    TextRegion,
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
def testSetAlignmentLeavesTheCursorAlone(app: QApplication) -> None:
    """setAlignment applies alignment without touching the cursor or text.

    A populated document plus ``setAlignment`` must not leave a
    document-wide selection behind: the next typed character would
    replace the whole document.
    """
    widget = PyRaya()
    widget.setPlainText("سلام دنیا")
    cursor = widget.textCursor()
    cursor.setPosition(len("سلام دنیا"))
    widget.setTextCursor(cursor)
    widget.setAlignment(Qt.AlignmentFlag.AlignRight)
    after = widget.textCursor()
    assert not after.hasSelection()
    assert after.position() == cursor.position()
    after.insertText("x")
    assert widget.toPlainText() == "سلام دنیاx"


# ******************************************************************************
def testSetAlignmentPreservesASelection(app: QApplication) -> None:
    """setAlignment keeps the user's own selection intact."""
    widget = PyRaya()
    widget.setPlainText("سلام دنیا")
    cursor = widget.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    widget.setTextCursor(cursor)
    widget.setAlignment(Qt.AlignmentFlag.AlignRight)
    after = widget.textCursor()
    assert after.hasSelection()
    assert (after.selectionStart(), after.selectionEnd()) == (0, 4)


# ******************************************************************************
def testSetAlignmentReachesEveryParagraph(app: QApplication) -> None:
    """setAlignment applies the alignment to all existing paragraphs.

    The throwaway cursor selects the whole document before the block-format
    merge: without the selection the merge only touches the block under the
    cursor (block 0) and later paragraphs keep their old alignment.
    """
    widget = PyRaya()
    widget.setPlainText("alpha\nbeta\ngamma")
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    block = widget.document().begin()
    while block.isValid():
        assert block.blockFormat().alignment() == Qt.AlignmentFlag.AlignCenter
        block = block.next()


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
def _layoutColorRanges(widget: PyRaya) -> list[tuple[int, int, QColor | None, QColor | None]]:
    """Per-character layout colors as ``(start, end, fg, bg)`` ranges.

    fg/bg are the range's foreground/background colors, or ``None`` when
    the property is not set in the layout format. Read from the
    per-block text layouts' format ranges — the authoritative observation
    point for layout-only formats — with each attribute cast to its
    documented runtime type and copied to plain values immediately (the
    format borrows its C++ object, deleted with the range wrapper).
    """
    ranges: list[tuple[int, int, QColor | None, QColor | None]] = []
    block = widget.document().begin()
    while block.isValid():
        base = block.position()
        for r in block.layout().formats():
            # The venv stub declares FormatRange's attributes as `...` with
            # `# type:` comments pyrefly does not read; the runtime types are
            # the ones the comments name, so cast them here.
            rformat = cast(QTextCharFormat, r.format)
            fg = (
                rformat.foreground().color()
                if rformat.hasProperty(QTextCharFormat.Property.ForegroundBrush)
                else None
            )
            bg = (
                rformat.background().color()
                if rformat.hasProperty(QTextCharFormat.Property.BackgroundBrush)
                else None
            )
            ranges.append(
                (
                    base + cast(int, r.start),
                    base + cast(int, r.start) + cast(int, r.length),
                    fg,
                    bg,
                )
            )
        block = block.next()
    return ranges


# ******************************************************************************
def testUntaggedLatinKeepsRuleForegroundUnderKindTint(app: QApplication) -> None:
    """The kind tint merges over the rules, never replaces them.

    ``QSyntaxHighlighter.setFormat`` replaces the whole per-character
    layout format, so painting a background-only kind format over the
    runs would wipe the rule-set foregrounds: untagged Latin letters
    (which resolve to the seed) fall back to the default black ink
    instead of the Latin rule blue, and with visible whitespace the
    space's designed light-gray dot (#e0e3ff) renders as a heavy black
    mark at whitespace.
    """
    widget = PyRaya()
    widget.setPlainText("ab c")
    latin = QColor("#1d4ed8")  # the default rules' Latin foreground
    wash = widget.regionColors()[RegionType.RomanUrdu]
    for start, end, fg, bg in _layoutColorRanges(widget):
        assert bg is not None and bg == wash  # untagged resolves to the seed tint
        for idx in range(start, end):
            char = widget.document().characterAt(idx)
            if char.isspace():
                continue
            assert fg is not None and fg == latin, f"char {char!r} fg {fg}"


# ******************************************************************************
def testUntaggedWhitespaceKeepsDesignedDotColor(app: QApplication) -> None:
    """The visible-space dot keeps its light gray over the seed tint.

    Spaces of untagged runs render through the whitespace rule's
    ``#e0e3ff`` foreground; the seed tint must not erase it —
    otherwise the space shows the default (black) ink instead of the
    light gray the widget's visible-whitespace design intends.
    """
    widget = PyRaya()
    widget.setPlainText("ab c")
    gray = QColor("#e0e3ff")  # the default rules' whitespace foreground
    wash = widget.regionColors()[RegionType.RomanUrdu]
    seen = False
    for start, end, fg, bg in _layoutColorRanges(widget):
        chars = [widget.document().characterAt(idx) for idx in range(start, end)]
        if not all(c.isspace() for c in chars):
            continue
        seen = True
        assert fg is not None and fg == gray, f"space range [{start},{end}) fg {fg}"
        assert bg is not None and bg == wash
    assert seen  # the single space was actually rendered somewhere


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
def testRegionTypesDefined(app: QApplication) -> None:  # noqa: ARG001
    """Exactly the two closed region kinds exist."""
    assert set(RegionType) == {RegionType.Native, RegionType.RomanUrdu}


# ******************************************************************************
def testRegionColorsAreDistinctAndSubtle(app: QApplication) -> None:  # noqa: ARG001
    """The module default palette colours the one colourable kind and is
    semi-transparent."""
    assert set(RegionColors) == {RegionType.RomanUrdu}
    roman = RegionColors[RegionType.RomanUrdu]
    assert 0 < roman.alpha() < 255


# ******************************************************************************
def testRegionsStartEmpty(app: QApplication) -> None:
    """A fresh PyRaya widget has no text regions."""
    widget = PyRaya()
    assert widget.regions() == []


# ******************************************************************************
def testSetRegionTypeFromSelection(app: QApplication) -> None:
    """Tagging the current selection retags it; the surrounding untagged
    text resolves to the seed."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    widget.setRegionType(RegionType.Native)
    assert widget.regions() == [
        TextRegion(0, 1, RegionType.RomanUrdu),
        TextRegion(1, 3, RegionType.Native),
        TextRegion(3, 4, RegionType.RomanUrdu),
    ]


# ******************************************************************************
def testSetRegionTypeExplicitRange(app: QApplication) -> None:
    """Tagging an explicit range with the seed kind leaves one seed span
    covering the whole text: untagged text already resolves to the seed,
    and adjacent spans of one kind merge."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.setRegionType(RegionType.RomanUrdu, 2, 5)
    assert widget.regions() == [TextRegion(0, 10, RegionType.RomanUrdu)]


# ******************************************************************************
def testSetRegionTypeNoSelectionIsNoop(app: QApplication) -> None:
    """Tagging without a selection or explicit range is a no-op; the text
    still resolves to the seed."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Native)
    assert widget.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]


# ******************************************************************************
def testSetRegionTypeSplitsAndRetags(app: QApplication) -> None:
    """Retagging part of the text splits it; the surrounding untagged text
    resolves to the seed."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.setRegionType(RegionType.Native, 2, 7)
    assert widget.regions() == [
        TextRegion(0, 2, RegionType.RomanUrdu),
        TextRegion(2, 7, RegionType.Native),
        TextRegion(7, 10, RegionType.RomanUrdu),
    ]


# ******************************************************************************
def testSetRegionTypeMergesAdjacent(app: QApplication) -> None:
    """Adjacent same-kind spans merge into one region; the surrounding
    untagged text resolves to the seed."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.setRegionType(RegionType.Native, 0, 3)
    widget.setRegionType(RegionType.Native, 3, 6)
    assert widget.regions() == [
        TextRegion(0, 6, RegionType.Native),
        TextRegion(6, 10, RegionType.RomanUrdu),
    ]


# ******************************************************************************
def testRegionSpansBlocks(app: QApplication) -> None:
    """A region may span multiple text blocks; the surrounding untagged
    text resolves to the seed."""
    widget = PyRaya()
    widget.setPlainText("ab\ncd")
    widget.setRegionType(RegionType.Native, 1, 4)
    assert widget.regions() == [
        TextRegion(0, 1, RegionType.RomanUrdu),
        TextRegion(1, 4, RegionType.Native),
        TextRegion(4, 5, RegionType.RomanUrdu),
    ]


# ******************************************************************************
def testRegionPersistsThroughInsertion(app: QApplication) -> None:
    """Inserting text before a region shifts the span; the inserted text
    resolves to the seed."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Native, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(0)
    cursor.insertText("X")
    assert widget.regions() == [
        TextRegion(0, 2, RegionType.RomanUrdu),
        TextRegion(2, 4, RegionType.Native),
        TextRegion(4, 5, RegionType.RomanUrdu),
    ]


# ******************************************************************************
def testRegionPersistsThroughDeletion(app: QApplication) -> None:
    """Deleting text before a region shifts the span; the remaining text
    resolves to the seed."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Native, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(0)
    cursor.deleteChar()
    assert widget.regions() == [
        TextRegion(0, 2, RegionType.Native),
        TextRegion(2, 3, RegionType.RomanUrdu),
    ]


# ******************************************************************************
def testRegionPersistsThroughUndoRedo(app: QApplication) -> None:
    """Region state survives undo and redo because it lives in the
    document."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Native, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(4)
    cursor.insertText("e")
    assert widget.regions() == [
        TextRegion(0, 1, RegionType.RomanUrdu),
        TextRegion(1, 3, RegionType.Native),
        TextRegion(3, 5, RegionType.RomanUrdu),
    ]
    widget.undo()
    assert widget.regions() == [
        TextRegion(0, 1, RegionType.RomanUrdu),
        TextRegion(1, 3, RegionType.Native),
        TextRegion(3, 4, RegionType.RomanUrdu),
    ]
    widget.redo()
    assert widget.regions() == [
        TextRegion(0, 1, RegionType.RomanUrdu),
        TextRegion(1, 3, RegionType.Native),
        TextRegion(3, 5, RegionType.RomanUrdu),
    ]


# ******************************************************************************
def testSetTextResolvesToSeed(app: QApplication) -> None:
    """Replacing the document text leaves no stored tags: the fresh text
    resolves to the seed."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 0, 4)
    widget.setPlainText("efgh")
    assert widget.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]


# ******************************************************************************
def testRegionTypeAt(app: QApplication) -> None:
    """regionTypeAt reports the resolved kind at each offset: a stored
    Native tag wins inside its range, and the untagged text around it
    resolves to the seed."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Native, 1, 3)
    assert widget.regionTypeAt(0) is RegionType.RomanUrdu
    assert widget.regionTypeAt(1) is RegionType.Native
    assert widget.regionTypeAt(2) is RegionType.Native
    assert widget.regionTypeAt(3) is RegionType.RomanUrdu


# ******************************************************************************
def testClearRegionsRemovesTagIntent(app: QApplication) -> None:
    """clearRegions removes the stored tag intent: no character format
    keeps the kind property afterwards, and the resolved map shows the
    seed partition."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 1, 3)
    widget.clearRegions()
    for position in range(widget.document().characterCount() - 1):
        assert not widget._charFormatAt(position).hasProperty(RegionKindProperty)
    assert widget.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]


# ******************************************************************************
def testSetRegionColorRecolours(app: QApplication) -> None:
    """setRegionColor updates the widget's palette only.

    The module-level default palette stays untouched: the recolour is a
    widget-local change, and the region map is not re-derived from the
    palette, so it stays untouched too.
    """
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 0, 4)
    newColor = QColor("#34D399")
    assert widget.setRegionColor(RegionType.RomanUrdu, newColor) is True
    assert widget.regionColors()[RegionType.RomanUrdu].name() == "#34d399"
    assert RegionColors[RegionType.RomanUrdu].name() == "#3b82f6"
    assert widget.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]


# ******************************************************************************
def testRegionColorPaletteIsPerWidget(app: QApplication) -> None:
    """Each widget owns its palette: recolouring one leaves another alone.

    The palette is a view-only map, so a recolour in one widget cannot
    break another widget's document or its own palette copy.
    """
    w1 = PyRaya()
    w1.setPlainText("abcd")
    w2 = PyRaya()
    w2.setPlainText("abcd")
    w2.setRegionType(RegionType.RomanUrdu, 0, 4)

    assert w1.setRegionColor(RegionType.RomanUrdu, QColor("#34D399")) is True

    assert w2.regionColors()[RegionType.RomanUrdu].name() == "#3b82f6"
    assert w2.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]


# ******************************************************************************
def testRegionColorsReturnsAnIndependentCopy(app: QApplication) -> None:
    """A returned palette copy is deep: mutating a returned QColor cannot
    leak into the module default palette or any widget (the cross-instance
    corruption class the per-widget palette exists to close)."""
    w1 = PyRaya()
    palette = w1.regionColors()
    palette[RegionType.RomanUrdu].setGreen(1)
    assert RegionColors[RegionType.RomanUrdu].green() != 1
    w2 = PyRaya()
    assert (
        w2.regionColors()[RegionType.RomanUrdu].green()
        == RegionColors[RegionType.RomanUrdu].green()
    )


# ******************************************************************************
def testPopupMenuRegionActions(app: QApplication) -> None:
    """The context menu exposes enabled region actions and clears regions."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    widget.setRegionType(RegionType.Native)

    menu = widget.createPopupMenu()
    byText = {action.text(): action for action in menu.actions()}
    assert "Region: Native" in byText
    assert "Region: Roman Urdu" in byText
    assert "Clear region under cursor" in byText
    assert "Clear all regions" in byText
    assert byText["Region: Native"].isEnabled()
    assert byText["Clear region under cursor"].isEnabled()
    assert byText["Clear all regions"].isEnabled()

    byText["Clear region under cursor"].trigger()
    assert widget.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]


# ******************************************************************************
def testPopupMenuDisabledWithoutSelection(app: QApplication) -> None:
    """Region actions are disabled without a selection; clearing removes
    tag intent, so clear-all stays enabled for non-empty text."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 1, 3)

    menu = widget.createPopupMenu()
    byText = {action.text(): action for action in menu.actions()}
    assert not byText["Region: Native"].isEnabled()
    assert not byText["Region: Roman Urdu"].isEnabled()
    assert byText["Clear all regions"].isEnabled()

    widget.clearRegions()
    assert widget.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]
    menu2 = widget.createPopupMenu()
    byText2 = {action.text(): action for action in menu2.actions()}
    assert byText2["Clear all regions"].isEnabled()


# ******************************************************************************
def testSetRegionColorRehighlightsTheTint(app: QApplication) -> None:
    """Recolouring repaints the layout tint immediately and touches no
    document state.

    The kind tint lives in the text layout, which only refreshes at a
    re-highlight; without one the screen keeps the old color until an
    unrelated event repaints the layout. The recolour is view-only: the
    document revision never moves.
    """
    widget = PyRaya()
    widget.setPlainText("عربي")
    roman = widget.regionColors()[RegionType.RomanUrdu]
    oldAtom = roman.name(QColor.NameFormat.HexArgb)
    formats = widget.document().firstBlock().layout().formats()
    assert oldAtom in [
        cast(QTextCharFormat, r.format).background().color().name(QColor.NameFormat.HexArgb)
        for r in formats
    ]

    newColor = QColor(0xAB, 0xCD, 0xEF, 30)
    revision = widget.document().revision()
    assert widget.setRegionColor(RegionType.RomanUrdu, newColor) is True
    assert widget.document().revision() == revision
    newAtom = newColor.name(QColor.NameFormat.HexArgb)
    formats = widget.document().firstBlock().layout().formats()
    assert newAtom in [
        cast(QTextCharFormat, r.format).background().color().name(QColor.NameFormat.HexArgb)
        for r in formats
    ]


# ******************************************************************************
def testRegionsChangedSignal(app: QApplication) -> None:
    """regionsChanged emits when a region write is made or cleared."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    fired: list[int] = []
    widget.regionsChanged.connect(lambda: fired.append(1))
    widget.setRegionType(RegionType.Native, 0, 4)
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
        widget.mapToGlobal(QPoint(5, 5)),
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
    widget.setRegionType(RegionType.Native, 14, 16)
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
    widget.setRegionType(RegionType.Native, 0, 4)
    assert widget.regionTypeAt(4) is None


# ******************************************************************************
def testKeyboardShortcutsAssignRegions(app: QApplication) -> None:
    """Ctrl+1 tags the selection Native and Ctrl+2 Roman Urdu (the seed
    kind), so Ctrl+2 over a Native region resets the resolution to the
    seed everywhere."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    _select(widget, 1, 3)
    _keyPress(widget, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == [
        TextRegion(0, 1, RegionType.RomanUrdu),
        TextRegion(1, 3, RegionType.Native),
        TextRegion(3, 10, RegionType.RomanUrdu),
    ]
    assert widget.toPlainText() == "abcdefghij"

    _keyPress(widget, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == [TextRegion(0, 10, RegionType.RomanUrdu)]
    assert widget.toPlainText() == "abcdefghij"


# ******************************************************************************
def testKeyboardShortcutsIgnoredWithoutSelection(app: QApplication) -> None:
    """Ctrl+1 / Ctrl+2 do nothing without a selection; typing a
    non-roman character is unaffected and resolves to the seed."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _keyPress(widget, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]

    _keyPress(widget, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, " ")
    assert widget.toPlainText() == " abcd"
    assert widget.regions() == [TextRegion(0, 5, RegionType.RomanUrdu)]


# ******************************************************************************
def testSetPlainTextResolvesToSeed(app: QApplication) -> None:
    """Text set on the widget resolves to the seed immediately."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    assert widget.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]
    assert all(widget.regionTypeAt(p) is RegionType.RomanUrdu for p in range(4))


# ******************************************************************************
def testFirstTypedCharacterResolvesToSeed(app: QApplication) -> None:
    """A first character typed into an empty document resolves to the
    seed."""
    widget = PyRaya()
    cursor = widget.textCursor()
    cursor.insertText("a")
    assert widget.regions() == [TextRegion(0, 1, RegionType.RomanUrdu)]


# ******************************************************************************
def testRegionsChangedFiresForDefaultRepaint(app: QApplication) -> None:
    """regionsChanged fires for a non-empty setPlainText (a document-wide
    write that retags the text), and not for an empty replacement."""
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
def testEnterAtEndOfTaggedParagraphContinuesItsKind(app: QApplication) -> None:
    """Enter at a tagged paragraph's end continues its kind with no hook
    and no write — provided the tag covers the paragraph's trailing
    whitespace.

    The new block's block format carries the stored kind, so the first
    character typed there inherits it; a Native tag makes that typing go
    straight through the roman-input gate with no overlay.
    """
    widget = PyRaya()
    widget.setPlainText("سلام ")
    widget.setRegionType(RegionType.Native, 0, len("سلام "))
    cursor = widget.textCursor()
    cursor.setPosition(len("سلام "))
    widget.setTextCursor(cursor)
    _keyPress(widget, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    newBlock = widget.document().begin().next()
    assert newBlock.isValid()
    blockFormat = newBlock.charFormat()
    assert blockFormat.hasProperty(RegionKindProperty)
    assert blockFormat.intProperty(RegionKindProperty) == int(RegionType.Native)

    _keyPress(widget, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")
    assert widget.toPlainText() == "سلام \na"
    assert widget.regionTypeAt(widget.document().characterCount() - 2) is RegionType.Native
    assert widget._overlay is None


# ******************************************************************************
def testStoredTagWinsOverIdenticalSeed(app: QApplication) -> None:
    """A stored tag that equals the seed is still stored, and still wins.

    Tags record intent: the write stores it and admission reads it back
    from the property. Storage is verified through the character format,
    not through resolution — here the two are identical by construction.
    """
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 0, 4)
    for position in range(4):
        fmt = widget._charFormatAt(position)
        assert fmt.hasProperty(RegionKindProperty)
        assert fmt.intProperty(RegionKindProperty) == int(RegionType.RomanUrdu)
    assert widget.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]


# ******************************************************************************
def testRegionColorTouchesNoDocument(app: QApplication) -> None:
    """Recolouring the palette touches no document state and signals
    nothing: the palette is view-only."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.RomanUrdu, 0, 4)
    revision = widget.document().revision()
    fired: list[int] = []
    widget.regionsChanged.connect(lambda: fired.append(1))
    assert widget.setRegionColor(RegionType.RomanUrdu, QColor("#34D399")) is True
    assert widget.document().revision() == revision
    assert fired == []
    assert widget.regions() == [TextRegion(0, 4, RegionType.RomanUrdu)]


# ******************************************************************************
def testBatchClearIsOneUndoStepAndUndoRestoresEverySpan(app: QApplication) -> None:
    """clearRegions replays every stored span as one batch apply: no
    stored property survives, and one undo restores all of them."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.setRegionType(RegionType.Native, 0, 2)
    widget.setRegionType(RegionType.Native, 4, 6)
    widget.setRegionType(RegionType.RomanUrdu, 8, 10)
    widget.clearRegions()
    for position in range(widget.document().characterCount() - 1):
        assert not widget._charFormatAt(position).hasProperty(RegionKindProperty)
    assert widget.regions() == [TextRegion(0, 10, RegionType.RomanUrdu)]

    widget.undo()
    assert widget.regions() == [
        TextRegion(0, 2, RegionType.Native),
        TextRegion(2, 4, RegionType.RomanUrdu),
        TextRegion(4, 6, RegionType.Native),
        TextRegion(6, 10, RegionType.RomanUrdu),
    ]
    assert widget.regionTypeAt(0) is RegionType.Native
    assert widget.regionTypeAt(4) is RegionType.Native
    assert widget.regionTypeAt(8) is RegionType.RomanUrdu


# ******************************************************************************
def testUndoOfRegionWriteRepaintsTheLayout(app: QApplication) -> None:
    """Undoing a region write repaints the layout tint immediately.

    Undoing a format-only tag write must present the resolved kinds
    without any other event: while the Native tag stands its (colourless)
    stretch shows no background, and the undo restores the seed tint over
    it within the same call.
    """
    widget = PyRaya()
    widget.setPlainText("abcd")
    wash = widget.regionColors()[RegionType.RomanUrdu]

    def readBackgrounds() -> dict[int, QColor | None]:
        read: dict[int, QColor | None] = {}
        for start, end, _, bg in _layoutColorRanges(widget):
            for idx in range(start, end):
                read[idx] = bg
        return read

    widget.setRegionType(RegionType.Native, 1, 3)
    assert readBackgrounds() == {0: wash, 1: None, 2: None, 3: wash}

    widget.undo()
    backgrounds = readBackgrounds()
    assert set(backgrounds) == {0, 1, 2, 3}
    assert all(bg == wash for bg in backgrounds.values())

    # The redo restores both the property and the tint in the same call.
    widget.redo()
    assert readBackgrounds() == {0: wash, 1: None, 2: None, 3: wash}
    for position in (1, 2):
        assert widget._charFormatAt(position).hasProperty(RegionKindProperty)
        assert widget.regionTypeAt(position) is RegionType.Native


# ******************************************************************************
def testSeedIsReadOnlyAfterConstruction(app: QApplication) -> None:
    """The widget's seed is a fixed construction-time copy with no setter."""
    widget = PyRaya()
    assert widget.seedRegionKind() is SeedRegionKind
    seedNames = [n for n in dir(PyRaya) if "seed" in n.lower()]
    assert all(not n.startswith("set") for n in seedNames)


# ******************************************************************************
def testNativeKeystrokesTypeThroughTheGate(app: QApplication) -> None:
    """ASCII typing inside a Native span types through the roman-input
    gate: the character lands in the document and no overlay is created."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.setRegionType(RegionType.Native, 0, 4)
    cursor = widget.textCursor()
    cursor.setPosition(2)
    widget.setTextCursor(cursor)
    _keyPress(widget, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")
    assert widget.toPlainText() == "abacd"
    assert widget.regionTypeAt(2) is RegionType.Native
    assert widget._overlay is None


# ******************************************************************************
def testNativeHoleInsideTintedParagraph(app: QApplication) -> None:
    """Native is colourless: a Native tag inside untagged (seed-tinted)
    text leaves its stretch without a background while the surrounding
    text keeps the seed tint and the rule foregrounds."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    wash = widget.regionColors()[RegionType.RomanUrdu]
    widget.setRegionType(RegionType.Native, 2, 5)
    assert widget.regions() == [
        TextRegion(0, 2, RegionType.RomanUrdu),
        TextRegion(2, 5, RegionType.Native),
        TextRegion(5, 10, RegionType.RomanUrdu),
    ]
    backgrounds: dict[int, QColor | None] = {}
    foregrounds: dict[int, QColor | None] = {}
    for start, end, fg, bg in _layoutColorRanges(widget):
        for idx in range(start, end):
            backgrounds[idx] = bg
            foregrounds[idx] = fg
    for idx in range(2, 5):
        assert backgrounds[idx] is None, idx
        assert foregrounds[idx] == QColor("#1d4ed8"), idx
    for idx in (0, 1, 5, 6, 7, 8, 9):
        assert backgrounds[idx] == wash, idx
        assert foregrounds[idx] == QColor("#1d4ed8"), idx

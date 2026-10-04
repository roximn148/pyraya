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

from pyraya import REGION_COLORS, PyRaya, PyRayaHighlighter, RegionType, TextRegion


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
def test_pyraya_instantiates(app: QApplication) -> None:
    """A PyRaya widget can be created under an offscreen QApplication."""
    widget = PyRaya()
    assert isinstance(widget, PyRaya)


# ******************************************************************************
def test_pyraya_is_plain_text_edit(app: QApplication) -> None:
    """PyRaya derives from QPlainTextEdit."""
    widget = PyRaya()
    assert isinstance(widget, QPlainTextEdit)


# ******************************************************************************
def test_pyraya_rtl_direction(app: QApplication) -> None:
    """PyRaya sets the widget layout direction to right-to-left."""
    widget = PyRaya()
    assert widget.layoutDirection() == Qt.LayoutDirection.RightToLeft


# ******************************************************************************
def test_pyraya_right_alignment(app: QApplication) -> None:
    """PyRaya right-aligns its text blocks by default."""
    widget = PyRaya()
    block = widget.document().begin()
    assert block.blockFormat().alignment() == Qt.AlignmentFlag.AlignRight


# ******************************************************************************
def test_pyraya_show_whitespace(app: QApplication) -> None:
    """PyRaya enables the ShowTabsAndSpaces text option by default."""
    widget = PyRaya()
    option = widget.document().defaultTextOption()
    assert option.flags() & QTextOption.Flag.ShowTabsAndSpaces


# ******************************************************************************
def test_pyraya_highlighter_attached(app: QApplication) -> None:
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
def _key_press(widget: PyRaya, key: int, modifiers: Qt.KeyboardModifier, text: str = "") -> None:
    """Send a key-press event to the widget."""
    QCoreApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text))


# ******************************************************************************
def test_region_types_defined() -> None:
    """Exactly the two initial region types exist."""
    assert set(RegionType) == {RegionType.LATIN, RegionType.ROMAN_URDU}


# ******************************************************************************
def test_region_colors_are_distinct_and_subtle() -> None:
    """Default region colors are distinct from each other and semi-transparent."""
    latin = REGION_COLORS[RegionType.LATIN]
    roman = REGION_COLORS[RegionType.ROMAN_URDU]
    assert latin != roman
    assert 0 < latin.alpha() < 255
    assert 0 < roman.alpha() < 255


# ******************************************************************************
def test_regions_start_empty(app: QApplication) -> None:
    """A fresh PyRaya widget has no text regions."""
    widget = PyRaya()
    assert widget.regions() == []


# ******************************************************************************
def test_set_region_type_from_selection(app: QApplication) -> None:
    """Tagging the current selection creates a region span."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    widget.set_region_type(RegionType.ROMAN_URDU)
    assert widget.regions() == [TextRegion(1, 3, RegionType.ROMAN_URDU)]


# ******************************************************************************
def test_set_region_type_explicit_range(app: QApplication) -> None:
    """Tagging an explicit character range creates a region span."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.set_region_type(RegionType.LATIN, 2, 5)
    assert widget.regions() == [TextRegion(2, 5, RegionType.LATIN)]


# ******************************************************************************
def test_set_region_type_no_selection_is_noop(app: QApplication) -> None:
    """Tagging without a selection or explicit range is a no-op."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.set_region_type(RegionType.LATIN)
    assert widget.regions() == []


# ******************************************************************************
def test_set_region_type_splits_and_retags(app: QApplication) -> None:
    """Retagging part of a region splits it and merges around the new span."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.set_region_type(RegionType.LATIN, 0, 5)
    widget.set_region_type(RegionType.ROMAN_URDU, 2, 7)
    assert widget.regions() == [
        TextRegion(0, 2, RegionType.LATIN),
        TextRegion(2, 7, RegionType.ROMAN_URDU),
    ]


# ******************************************************************************
def test_set_region_type_merges_adjacent(app: QApplication) -> None:
    """Adjacent same-type spans merge into one region."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    widget.set_region_type(RegionType.LATIN, 0, 3)
    widget.set_region_type(RegionType.LATIN, 3, 6)
    assert widget.regions() == [TextRegion(0, 6, RegionType.LATIN)]


# ******************************************************************************
def test_region_spans_blocks(app: QApplication) -> None:
    """A region may span multiple text blocks."""
    widget = PyRaya()
    widget.setPlainText("ab\ncd")
    widget.set_region_type(RegionType.ROMAN_URDU, 1, 4)
    assert widget.regions() == [TextRegion(1, 4, RegionType.ROMAN_URDU)]


# ******************************************************************************
def test_region_persists_through_insertion(app: QApplication) -> None:
    """Inserting text before a region shifts the span."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.set_region_type(RegionType.LATIN, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(0)
    cursor.insertText("X")
    assert widget.regions() == [TextRegion(2, 4, RegionType.LATIN)]


# ******************************************************************************
def test_region_persists_through_deletion(app: QApplication) -> None:
    """Deleting text before a region shifts the span."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.set_region_type(RegionType.LATIN, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(0)
    cursor.deleteChar()
    assert widget.regions() == [TextRegion(0, 2, RegionType.LATIN)]


# ******************************************************************************
def test_region_persists_through_undo_redo(app: QApplication) -> None:
    """Region state survives undo and redo because it lives in the document."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.set_region_type(RegionType.LATIN, 1, 3)
    cursor = widget.textCursor()
    cursor.setPosition(4)
    cursor.insertText("e")
    assert widget.regions() == [TextRegion(1, 3, RegionType.LATIN)]
    widget.undo()
    assert widget.regions() == [TextRegion(1, 3, RegionType.LATIN)]
    widget.redo()
    assert widget.regions() == [TextRegion(1, 3, RegionType.LATIN)]


# ******************************************************************************
def test_set_text_clears_regions(app: QApplication) -> None:
    """Replacing the document text removes its region state."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.set_region_type(RegionType.LATIN, 0, 4)
    widget.setPlainText("efgh")
    assert widget.regions() == []


# ******************************************************************************
def test_region_type_at(app: QApplication) -> None:
    """region_type_at reports the kind covering each offset."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.set_region_type(RegionType.ROMAN_URDU, 1, 3)
    assert widget.region_type_at(0) is None
    assert widget.region_type_at(1) is RegionType.ROMAN_URDU
    assert widget.region_type_at(2) is RegionType.ROMAN_URDU
    assert widget.region_type_at(3) is None


# ******************************************************************************
def test_clear_regions(app: QApplication) -> None:
    """clear_regions removes every region."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.set_region_type(RegionType.LATIN, 0, 4)
    widget.clear_regions()
    assert widget.regions() == []


# ******************************************************************************
def test_set_region_color_recolours(app: QApplication) -> None:
    """set_region_color recolors existing regions and updates the default."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.set_region_type(RegionType.LATIN, 0, 4)
    original = REGION_COLORS[RegionType.LATIN]
    new_color = QColor("#34D399")
    try:
        widget.set_region_color(RegionType.LATIN, new_color)
        assert widget.region_type_at(1) is RegionType.LATIN
        assert REGION_COLORS[RegionType.LATIN].name() == new_color.name()
    finally:
        REGION_COLORS[RegionType.LATIN] = original


# ******************************************************************************
def test_popup_menu_region_actions(app: QApplication) -> None:
    """The context menu exposes enabled region actions and clears regions."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _select(widget, 1, 3)
    widget.set_region_type(RegionType.LATIN)

    menu = widget.createPopupMenu()
    by_text = {action.text(): action for action in menu.actions()}
    assert "Region: Latin" in by_text
    assert "Region: Roman Urdu" in by_text
    assert "Clear region under cursor" in by_text
    assert "Clear all regions" in by_text
    assert by_text["Region: Latin"].isEnabled()
    assert by_text["Clear region under cursor"].isEnabled()
    assert by_text["Clear all regions"].isEnabled()

    by_text["Clear region under cursor"].trigger()
    assert widget.regions() == []


# ******************************************************************************
def test_popup_menu_disabled_without_selection(app: QApplication) -> None:
    """Region actions are disabled without a selection; clearing tracks state."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.set_region_type(RegionType.LATIN, 0, 4)

    menu = widget.createPopupMenu()
    by_text = {action.text(): action for action in menu.actions()}
    assert not by_text["Region: Latin"].isEnabled()
    assert not by_text["Region: Roman Urdu"].isEnabled()
    assert by_text["Clear all regions"].isEnabled()

    widget.clear_regions()
    menu2 = widget.createPopupMenu()
    by_text2 = {action.text(): action for action in menu2.actions()}
    assert not by_text2["Clear all regions"].isEnabled()


# ******************************************************************************
def test_regions_changed_signal(app: QApplication) -> None:
    """regions_changed emits when regions are added or cleared."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    fired: list[int] = []
    widget.regions_changed.connect(lambda: fired.append(1))
    widget.set_region_type(RegionType.LATIN, 0, 4)
    widget.clear_regions()
    assert len(fired) == 2


# ******************************************************************************
def test_context_menu_policy_is_custom(app: QApplication) -> None:
    """PyRaya suppresses Qt's automatic popup via CustomContextMenu."""
    widget = PyRaya()
    assert widget.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


# ******************************************************************************
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_custom_context_menu_requested_shows_popup(app: QApplication) -> None:
    """A context menu request received by the widget shows the popup menu.

    The platform delivers the context menu event to the widget's viewport
    (the scroll area's viewport event filter then emits
    ``customContextMenuRequested``), so the test sends it there. The
    synthetic ``QContextMenuEvent`` constructor is deprecated in Qt 6 and
    only exists for tests like this one.
    """
    shown: list[tuple[QMenu, QPoint]] = []

    class Probe(PyRaya):
        def _show_popup(self, menu: QMenu, position: QPoint) -> None:
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
def test_context_menu_at_text_edges_no_out_of_range_cursor(app: QApplication, capfd) -> None:
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
        def _show_popup(self, menu: QMenu, position: QPoint) -> None:
            shown.append(menu)

    widget = Probe()
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10))
    QCoreApplication.sendEvent(widget.viewport(), event)
    assert len(shown) == 1

    widget.setPlainText("0123456789abcdef")
    widget.set_region_type(RegionType.LATIN, 14, 16)
    cursor = widget.textCursor()
    cursor.setPosition(widget.document().characterCount() - 1)
    widget.setTextCursor(cursor)
    QCoreApplication.sendEvent(widget.viewport(), event)
    assert len(shown) == 2
    assert "out of range" not in capfd.readouterr().err.lower()


# ******************************************************************************
def test_region_type_at_terminator_offset_is_none(app: QApplication) -> None:
    """region_type_at returns None at the trailing terminator offset."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    widget.set_region_type(RegionType.LATIN, 0, 4)
    assert widget.region_type_at(4) is None


# ******************************************************************************
def test_keyboard_shortcuts_assign_regions(app: QApplication) -> None:
    """Ctrl+1 and Ctrl+2 tag the current selection as Latin or Roman Urdu."""
    widget = PyRaya()
    widget.setPlainText("abcdefghij")
    _select(widget, 1, 3)
    _key_press(widget, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == [TextRegion(1, 3, RegionType.LATIN)]
    assert widget.toPlainText() == "abcdefghij"

    _select(widget, 4, 6)
    _key_press(widget, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == [
        TextRegion(1, 3, RegionType.LATIN),
        TextRegion(4, 6, RegionType.ROMAN_URDU),
    ]
    assert widget.toPlainText() == "abcdefghij"


# ******************************************************************************
def test_keyboard_shortcuts_ignored_without_selection(app: QApplication) -> None:
    """Ctrl+1 / Ctrl+2 do nothing without a selection; typing is unaffected."""
    widget = PyRaya()
    widget.setPlainText("abcd")
    _key_press(widget, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert widget.regions() == []

    _key_press(widget, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier, "1")
    assert widget.toPlainText() == "1abcd"


# ******************************************************************************

# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""PyRaya — a self-contained PySide6 (Qt) text editor widget for Urdu.

The public entry point is :class:`PyRaya`, a drop-in ``QPlainTextEdit`` for
right-to-left (Nastaliq) Urdu text in Qt applications — currently PySide6 only.

PyRaya ships with a configurable, dedicated :class:`PyRayaHighlighter` that
provides rule-based formatting for Urdu and mixed-script text, and supports
text regions: spans tagged with a :class:`~pyraya.regions.RegionType` and
rendered with a subtle, type-specific background color.
"""

from collections.abc import Sequence

from PySide6.QtCore import QPoint, QRegularExpression, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QWidget

from .regions import REGION_COLORS, RegionType, TextRegion

__all__ = ["PyRaya", "PyRayaHighlighter"]

# ******************************************************************************
#: Preferred font stack, in order of preference. The first entry is the default.
PYRAYA_FONTS: tuple[str, ...] = (
    "Noto Naskh Arabic",
    "Noto Nastaliq Urdu",
    "Noto Sans Arabic",
    "Amiri",
    "Scheherazade New",
    "Geeza Pro",
)

#: Default point size applied to the default font.
DEFAULT_FONT_SIZE: float = 14.0


# ******************************************************************************
class PyRayaHighlighter(QSyntaxHighlighter):
    """Rule-based formatting highlighter for Urdu and mixed-script text.

    Formatting is driven by an ordered list of ``(QRegularExpression,
    QTextCharFormat)`` rules. Rules are applied in order, and later rules
    override earlier ones for overlapping matches, so broad rules should
    precede specific ones.

    Args:
        document: The document to highlight.
    """

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self._install_default_rules()

    @property
    def rules(self) -> list[tuple[QRegularExpression, QTextCharFormat]]:
        """A copy of the current formatting rules."""
        return list(self._rules)

    def add_rule(self, pattern: QRegularExpression, char_format: QTextCharFormat) -> None:
        """Append a formatting rule and re-highlight the document.

        Args:
            pattern: The regular expression to match.
            char_format: The character format to apply to matches.
        """
        self._rules.append((pattern, char_format))
        self.rehighlight()

    def set_rules(self, rules: Sequence[tuple[QRegularExpression, QTextCharFormat]]) -> None:
        """Replace all formatting rules and re-highlight the document.

        Args:
            rules: An iterable of ``(pattern, char_format)`` tuples.
        """
        self._rules = list(rules)
        self.rehighlight()

    def clear_rules(self) -> None:
        """Remove all formatting rules and re-highlight the document."""
        self._rules = []
        self.rehighlight()

    def highlightBlock(self, block: str) -> None:
        """Apply the formatting rules to a single text block.

        Args:
            block: The text of the block to highlight.
        """
        for pattern, char_format in self._rules:
            iterator = pattern.globalMatch(block)
            while iterator.hasNext():
                match = iterator.next()
                start = match.capturedStart(0)
                length = match.capturedLength(0)
                self.setFormat(start, length, char_format)

    def _install_default_rules(self) -> None:
        """Install the default formatting rules for Urdu-mixed text."""
        ink = self._char_format(QColor("#1F2937"))
        rose = self._char_format(QColor("#BE185D"), italic=True)
        amber = self._char_format(QColor("#B45309"))
        blue = self._char_format(QColor("#1D4ED8"))
        purple = self._char_format(QColor("#6D28D9"))
        gray = self._char_format(QColor("#6B7280"))
        light_gray = self._char_format(QColor("#e0e3ff"))
        self.set_rules(
            [
                (QRegularExpression("[\u0600-\u06ff]+"), ink),
                (QRegularExpression("[\u064b-\u065f]"), rose),
                (QRegularExpression("[\u0660-\u0669]+"), amber),
                (QRegularExpression("[\u0000-\u007f]+"), blue),
                (QRegularExpression("[0-9]+"), purple),
                (QRegularExpression(r"\p{P}+"), gray),
                (QRegularExpression(r"\s+"), light_gray),
            ]
        )

    @staticmethod
    def _char_format(color: QColor, *, italic: bool = False) -> QTextCharFormat:
        """Build a character format from a color and optional italic flag.

        Args:
            color: The foreground color.
            italic: Whether the text should be italicized.

        Returns:
            A character format with the given color (and italic if requested).
        """
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(color))
        fmt.setFontItalic(italic)
        return fmt


# ******************************************************************************
class PyRaya(QPlainTextEdit):
    """Self-contained PySide6 text editor widget for Urdu/Nastaliq text.

    A drop-in ``QPlainTextEdit`` for embedding Urdu text editing in a Qt UI.
    Configures right-to-left layout, right-aligned paragraphs, a configurable
    Noto font stack (default ``Noto Naskh Arabic``), visible whitespace, a
    dedicated rule-based :class:`PyRayaHighlighter` for formatting, and text
    regions: spans tagged with a :class:`~pyraya.regions.RegionType` and
    rendered with a subtle, type-specific background color.
    """

    regions_changed = Signal()

    # ==========================================================================
    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the widget.

        Args:
            parent: Optional parent widget; defaults to a top-level window.
        """
        super().__init__(parent)
        self._font_family = self._resolve_default_font()
        self._font_size: float = DEFAULT_FONT_SIZE
        self._alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight
        self._apply_font()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.set_show_whitespace(True)
        self._highlighter = PyRayaHighlighter(self.document())
        self.set_alignment(Qt.AlignmentFlag.AlignRight)
        # PySide6 does not dispatch QWidget.createPopupMenu or
        # QWidget.contextMenuEvent to Python overrides on QPlainTextEdit
        # subclasses, so the context menu is handled via the
        # customContextMenuRequested signal below. This policy makes Qt
        # emit that signal (instead of an automatic empty popup) when the
        # context menu event reaches the widget's viewport.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_custom_context_menu_requested)

    @property
    def highlighter(self) -> PyRayaHighlighter:
        """The widget's dedicated formatting highlighter."""
        return self._highlighter

    def available_fonts(self) -> list[str]:
        """Return the font families installed on the system.

        Returns:
            A list of installed font family names.
        """
        return list(QFontDatabase.families())

    def set_font_family(self, family: str) -> bool:
        """Set the font family, falling back if the font is not installed.

        Args:
            family: The font family name to use.

        Returns:
            True if the family is installed and applied; False otherwise.
        """
        if family not in set(QFontDatabase.families()):
            return False
        self._font_family = family
        self._apply_font()
        return True

    def set_font_size(self, size: float) -> None:
        """Set the font point size.

        Args:
            size: The point size to apply. Must be greater than zero.
        """
        if size <= 0:
            return
        self._font_size = size
        self._apply_font()

    def set_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        """Set the paragraph alignment for all blocks, existing and new.

        Args:
            alignment: The alignment flag to apply to every text block.
        """
        doc = self.document()
        to = doc.defaultTextOption()
        to.setAlignment(alignment)
        doc.setDefaultTextOption(to)

        self._sync_block_alignment()

    def set_show_whitespace(self, enabled: bool) -> None:
        """Toggle visible whitespace (tabs and spaces).

        Args:
            enabled: Whether to render tabs and spaces as visible characters.
        """
        option = self.document().defaultTextOption()
        flags = option.flags()
        if enabled:
            flags |= QTextOption.Flag.ShowTabsAndSpaces
        else:
            flags &= ~QTextOption.Flag.ShowTabsAndSpaces
        option.setFlags(flags)
        self.document().setDefaultTextOption(option)

    def add_format_rule(self, pattern: QRegularExpression, char_format: QTextCharFormat) -> None:
        """Add a formatting rule to the highlighter.

        Args:
            pattern: The regular expression to match.
            char_format: The character format to apply to matches.
        """
        self._highlighter.add_rule(pattern, char_format)

    def set_format_rules(self, rules: Sequence[tuple[QRegularExpression, QTextCharFormat]]) -> None:
        """Replace the highlighter's formatting rules.

        Args:
            rules: An iterable of ``(pattern, char_format)`` tuples.
        """
        self._highlighter.set_rules(rules)

    def clear_format_rules(self) -> None:
        """Remove all formatting rules from the highlighter."""
        self._highlighter.clear_rules()

    def regions(self) -> list[TextRegion]:
        """Return the document's text regions as sorted, non-overlapping spans.

        Returns:
            A list of :class:`~pyraya.regions.TextRegion` spans ordered by
            start offset.
        """
        return self._region_spans()

    def set_region_type(
        self, kind: RegionType, start: int | None = None, end: int | None = None
    ) -> None:
        """Tag a character range (or the current selection) with a region type.

        Existing regions overlapping the range are split and the range is
        retagged; adjacent same-type regions merge.

        Args:
            kind: The region type to apply.
            start: Start offset; defaults to the selection start.
            end: End offset (exclusive); defaults to the selection end.
        """
        if start is None or end is None:
            cursor = self.textCursor()
            if not cursor.hasSelection():
                return
            start, end = cursor.selectionStart(), cursor.selectionEnd()
        start = max(0, start)
        end = min(end, self.document().characterCount())
        if start >= end:
            return
        self._apply_region_format(start, end, kind)
        self.regions_changed.emit()

    def region_type_at(self, position: int) -> RegionType | None:
        """Return the region kind covering a character offset.

        Args:
            position: The character offset to query.

        Returns:
            The :class:`~pyraya.regions.RegionType` of the region containing
            the offset, or None if the offset is outside any region.
        """
        if not 0 <= position < self.document().characterCount() - 1:
            return None
        return self._region_kind_at(position)

    def clear_regions(self) -> None:
        """Remove all region tags from the document."""
        if not self._region_spans():
            return
        self._clear_range(0, self.document().characterCount())
        self.regions_changed.emit()

    def set_region_color(self, kind: RegionType, color: QColor) -> None:
        """Change the background color used for a region type.

        Existing regions of that type are recoloured immediately.

        Args:
            kind: The region type to recolour.
            color: The new background color; its alpha controls subtlety.
        """
        old_color = REGION_COLORS[kind]
        if QColor(color) == old_color:
            return
        old_name = old_color.name()
        for position in range(self.document().characterCount() - 1):
            if self._char_format_at(position).background().color().name() == old_name:
                cursor = self.textCursor()
                cursor.setPosition(position)
                cursor.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setBackground(QBrush(color))
                cursor.mergeCharFormat(fmt)
        REGION_COLORS[kind] = QColor(color)
        self.regions_changed.emit()

    def createPopupMenu(self) -> QMenu:
        """Create the context menu with editing and region actions.

        Builds on Qt's standard text-editing context menu (Undo, Redo, Cut,
        Copy, Paste, Delete and Select All, with their usual enable states)
        and appends the region actions.

        Returns:
            The context menu with editing and region actions.
        """
        menu = self.createStandardContextMenu(QPoint())
        menu.addSeparator()

        cursor = self.textCursor()
        has_selection = cursor.hasSelection()

        for kind, label in (
            (RegionType.LATIN, "Region: Latin"),
            (RegionType.ROMAN_URDU, "Region: Roman Urdu"),
        ):
            action = QAction(label, self)
            action.setEnabled(has_selection)
            action.triggered.connect(lambda _checked, k=kind: self.set_region_type(k))
            menu.addAction(action)

        region = self._region_under_cursor()
        clear_one = QAction("Clear region under cursor", self)
        clear_one.setEnabled(region is not None)
        if region is not None:
            clear_one.triggered.connect(
                lambda _checked, s=region.start, e=region.end: self._clear_range(s, e)
            )
        menu.addAction(clear_one)

        clear_all = QAction("Clear all regions", self)
        clear_all.setEnabled(bool(self._region_spans()))
        clear_all.triggered.connect(self.clear_regions)
        menu.addAction(clear_all)
        return menu

    def _on_custom_context_menu_requested(self, position: QPoint) -> None:
        """Show the context menu where it was requested.

        Args:
            position: The request position in viewport coordinates.
        """
        self._show_popup(self.createPopupMenu(), self.viewport().mapToGlobal(position))

    def _show_popup(self, menu: QMenu, position: QPoint) -> None:
        """Show the widget's context menu at the given global position."""
        menu.exec(position)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Assign region types via keyboard shortcuts.

        ``Ctrl+1`` tags the current selection as Latin and ``Ctrl+2`` tags
        it as Roman Urdu. Without a selection the shortcuts are ignored and
        the event falls through to the default handler.

        Args:
            event: The key-press event.
        """
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_1 and self.textCursor().hasSelection():
                self.set_region_type(RegionType.LATIN)
                return
            if event.key() == Qt.Key.Key_2 and self.textCursor().hasSelection():
                self.set_region_type(RegionType.ROMAN_URDU)
                return
        super().keyPressEvent(event)

    def _apply_region_format(self, start: int, end: int, kind: RegionType) -> None:
        """Merge the region's background format over a character range."""
        start, end = self._clamp_range(start, end)
        if start >= end:
            return
        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setBackground(QBrush(REGION_COLORS[kind]))
        cursor.mergeCharFormat(fmt)
        self.viewport().update()

    def _clear_range(self, start: int, end: int) -> None:
        """Remove region backgrounds over a character range.

        Cleared characters are repainted with the widget's own background
        color, because a format merge cannot restore a ``NoBrush``
        background once one has been set.
        """
        start, end = self._clamp_range(start, end)
        if start >= end:
            return
        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setBackground(QBrush(self.palette().color(self.backgroundRole())))
        cursor.mergeCharFormat(fmt)
        self.viewport().update()

    def _clamp_range(self, start: int, end: int) -> tuple[int, int]:
        """Clamp a character range to the document's real text offsets.

        The document's trailing terminator character — which Qt keeps at the
        end of the last block and which ``characterCount()`` includes — must
        never be formatted: merges spanning it are silently dropped.
        """
        limit = self.document().characterCount() - 1
        return max(0, start), min(limit, end)

    def _region_spans(self) -> list[TextRegion]:
        """Reconstruct region spans from the document's character formats.

        The trailing terminator character of the last block is never part of
        a region, so the scan stops before it.
        """
        spans: list[TextRegion] = []
        limit = self.document().characterCount() - 1
        position = 0
        while position < limit:
            kind = self._region_kind_at(position)
            if kind is None:
                position += 1
                continue
            start = position
            while position < limit and self._region_kind_at(position) == kind:
                position += 1
            spans.append(TextRegion(start, position, kind))
        return spans

    def _region_kind_at(self, position: int) -> RegionType | None:
        """Return the region kind stored at a character offset, or None."""
        color = self._char_format_at(position).background().color()
        for kind, region_color in REGION_COLORS.items():
            if color == region_color:
                return kind
        return None

    def _region_at(self, position: int) -> TextRegion | None:
        """Return the full region span containing a character offset, or None.

        The document's trailing terminator character is never part of a
        region, so offsets at or past it return None instead of reading the
        terminator's format (``_char_format_at`` would otherwise place the
        cursor out of range).
        """
        if not 0 <= position < self.document().characterCount() - 1:
            return None
        if self._region_kind_at(position) is None:
            return None
        for span in self._region_spans():
            if span.start <= position < span.end:
                return span
        return None

    def _region_under_cursor(self) -> TextRegion | None:
        """Return the region span under the cursor, accounting for selection.

        When the cursor has a selection, the region overlapping the selection
        is returned; otherwise the region containing the cursor position.
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            for span in self._region_spans():
                if span.start < end and start < span.end:
                    return span
        return self._region_at(cursor.position())

    def _char_format_at(self, position: int) -> QTextCharFormat:
        """Return the character format stored at a document offset.

        ``QTextCursor.charFormat()`` reports the format of the character
        before the cursor, so the cursor is placed one offset past the
        target. The offset must therefore stay below
        ``characterCount() - 1`` so the cursor never lands past the trailing
        terminator; region lookups guard that boundary. A fresh,
        document-bound cursor is used because the widget cursor can report
        stale formats while it carries a selection.
        """
        cursor = QTextCursor(self.document())
        cursor.setPosition(position + 1)
        return cursor.charFormat()

    def _resolve_default_font(self) -> str:
        """Pick the first font in the stack that is installed on the system.

        Returns:
            The resolved font family; falls back to the default if none of the
            preferred fonts are installed.
        """
        available = set(QFontDatabase.families())
        for family in PYRAYA_FONTS:
            if family in available:
                return family
        return PYRAYA_FONTS[0]

    def _apply_font(self) -> None:
        """Apply the current font family and size to the widget."""
        font = QFont()
        font.setFamilies([self._font_family, "Noto Sans"])
        font.setPointSizeF(self._font_size)
        self.setFont(font)

    def _sync_block_alignment(self) -> None:
        """Apply the default alignment to the entire document.

        Uses the default block format alignment and ensures it is applied across
        the entire document, without triggering new signals.
        """
        self.blockSignals(True)

        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)

        doc = self.document()
        to = doc.defaultTextOption()

        block_format = QTextBlockFormat()
        block_format.setAlignment(to.alignment())

        cursor.mergeBlockFormat(block_format)

        self.setTextCursor(cursor)

        self.blockSignals(False)


# ******************************************************************************

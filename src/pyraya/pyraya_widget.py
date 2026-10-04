# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""PyRaya — a self-contained PySide6 (Qt) text editor widget for Urdu.

The public entry point is :class:`PyRaya`, a drop-in ``QPlainTextEdit`` for
right-to-left (Nastaliq) Urdu text in Qt applications — currently PySide6 only.

PyRaya ships with a configurable, dedicated :class:`PyRayaHighlighter` that
provides rule-based formatting for Urdu and mixed-script text, and supports
text regions: spans tagged with a :class:`~pyraya.regions.RegionType` and
rendered with a subtle, type-specific background color. Every character of
the document belongs to exactly one region kind at all times — text without
an explicit tag carries the background color of
:data:`~pyraya.regions.defaultRegionKind` — and each region kind is
identified by a unique background color, compared including its alpha
channel.
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

from .regions import RegionColors, RegionType, TextRegion, defaultRegionKind

__all__ = ["PyRaya", "PyRayaHighlighter"]

# ******************************************************************************
#: Preferred font stack, in order of preference. The first entry is the default.
pyrayaFonts: tuple[str, ...] = (
    "Noto Naskh Arabic",
    "Noto Nastaliq Urdu",
    "Noto Sans Arabic",
    "Amiri",
    "Scheherazade New",
    "Geeza Pro",
)

#: Default point size applied to the default font.
defaultFontSize: float = 14.0


# ******************************************************************************
class PyRayaHighlighter(QSyntaxHighlighter):
    """Rule-based formatting highlighter for Urdu and mixed-script text.

    Formatting is driven by an ordered list of ``(QRegularExpression,
    QTextCharFormat)`` rules. Rules are applied in order, and later rules
    override earlier ones for overlapping matches, so broad rules should
    precede specific ones.

    The highlighter also keeps the region invariant: on every re-highlight,
    runs whose background matches no region color are painted with the
    :data:`~pyraya.regions.defaultRegionKind` background in the text
    layout, which Qt merges with the document's character formats at
    display time. That maintenance paints the layout rather than editing
    the document, so it is not recorded in the document's undo stack and
    cannot bury user edits behind it.

    Args:
        document: The document to highlight.
    """

    # ==========================================================================
    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self._installDefaultRules()

    # ==========================================================================
    @property
    def rules(self) -> list[tuple[QRegularExpression, QTextCharFormat]]:
        """A copy of the current formatting rules."""
        return list(self._rules)

    # ==========================================================================
    def addRule(self, pattern: QRegularExpression, charFormat: QTextCharFormat) -> None:
        """Append a formatting rule and re-highlight the document.

        Args:
            pattern: The regular expression to match.
            charFormat: The character format to apply to matches.
        """
        self._rules.append((pattern, charFormat))
        self.rehighlight()

    # ==========================================================================
    def setRules(self, rules: Sequence[tuple[QRegularExpression, QTextCharFormat]]) -> None:
        """Replace all formatting rules and re-highlight the document.

        Args:
            rules: An iterable of ``(pattern, charFormat)`` tuples.
        """
        self._rules = list(rules)
        self.rehighlight()

    # ==========================================================================
    def clearRules(self) -> None:
        """Remove all formatting rules and re-highlight the document."""
        self._rules = []
        self.rehighlight()

    # ==========================================================================
    def highlightBlock(self, block: str) -> None:
        """Apply the formatting rules to a single text block.

        After the rules, runs of characters without a recognized region
        background are painted with the
        :data:`~pyraya.regions.defaultRegionKind` background in the text
        layout.

        Args:
            block: The text of the block to highlight.
        """
        for pattern, charFormat in self._rules:
            iterator = pattern.globalMatch(block)
            while iterator.hasNext():
                match = iterator.next()
                start = match.capturedStart(0)
                length = match.capturedLength(0)
                self.setFormat(start, length, charFormat)
        self._paintDefaultRegions(block)

    # ==========================================================================
    def _paintDefaultRegions(self, block: str) -> None:
        """Paint runs without a recognized region background.

        Runs are painted with the
        :data:`~pyraya.regions.defaultRegionKind` background in the text
        layout; the document's character formats are not modified.

        Args:
            block: The text of the block being highlighted.
        """
        current = self.currentBlock()
        base = current.position()
        limit = len(block)
        cursor = QTextCursor(self.document())
        position = 0
        while position < limit:
            cursor.setPosition(base + position + 1)
            if self._hasRegionBackground(cursor.charFormat()):
                position += 1
                continue
            start = position
            while position < limit:
                cursor.setPosition(base + position + 1)
                if not self._hasRegionBackground(cursor.charFormat()):
                    position += 1
                else:
                    break
            fmt = QTextCharFormat()
            fmt.setBackground(QBrush(RegionColors[defaultRegionKind]))
            self.setFormat(start, position - start, fmt)

    # ==========================================================================
    @staticmethod
    def _hasRegionBackground(charFormat: QTextCharFormat) -> bool:
        """Return True if the format carries a recognized region background."""
        color = charFormat.background().color()
        return any(color == regionColor for regionColor in RegionColors.values())

    # ==========================================================================
    def _installDefaultRules(self) -> None:
        """Install the default formatting rules for Urdu-mixed text."""
        ink = self._charFormat(QColor("#1F2937"))
        rose = self._charFormat(QColor("#BE185D"), italic=True)
        amber = self._charFormat(QColor("#B45309"))
        blue = self._charFormat(QColor("#1D4ED8"))
        purple = self._charFormat(QColor("#6D28D9"))
        gray = self._charFormat(QColor("#6B7280"))
        lightGray = self._charFormat(QColor("#e0e3ff"))
        self.setRules(
            [
                (QRegularExpression("[\u0600-\u06ff]+"), ink),
                (QRegularExpression("[\u064b-\u065f]"), rose),
                (QRegularExpression("[\u0660-\u0669]+"), amber),
                (QRegularExpression("[\u0000-\u007f]+"), blue),
                (QRegularExpression("[0-9]+"), purple),
                (QRegularExpression(r"\p{P}+"), gray),
                (QRegularExpression(r"\s+"), lightGray),
            ]
        )

    # ==========================================================================
    @staticmethod
    def _charFormat(color: QColor, *, italic: bool = False) -> QTextCharFormat:
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
    rendered with a subtle, type-specific background color. All text belongs
    to exactly one region kind at any time — untagged text is the
    :data:`~pyraya.regions.defaultRegionKind` kind — and clearing regions
    resets the text to that kind.
    """

    regionsChanged = Signal()

    # ==========================================================================
    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the widget.

        Args:
            parent: Optional parent widget; defaults to a top-level window.
        """
        super().__init__(parent)
        self._fontFamily = self._resolveDefaultFont()
        self._fontSize: float = defaultFontSize
        self._alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight
        self._applyFont()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setShowWhitespace(True)
        self._highlighter = PyRayaHighlighter(self.document())
        # Aligning the initial (empty) document records an undo command;
        # disable undo/redo around it so no phantom command is left behind.
        document = self.document()
        document.setUndoRedoEnabled(False)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        document.setUndoRedoEnabled(True)
        # PySide6 does not dispatch QWidget.createPopupMenu or
        # QWidget.contextMenuEvent to Python overrides on QPlainTextEdit
        # subclasses, so the context menu is handled via the
        # customContextMenuRequested signal below. This policy makes Qt
        # emit that signal (instead of an automatic empty popup) when the
        # context menu event reaches the widget's viewport.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._onCustomContextMenuRequested)

    # ==========================================================================
    @property
    def highlighter(self) -> PyRayaHighlighter:
        """The widget's dedicated formatting highlighter."""
        return self._highlighter

    # ==========================================================================
    def availableFonts(self) -> list[str]:
        """Return the font families installed on the system.

        Returns:
            A list of installed font family names.
        """
        return list(QFontDatabase.families())

    # ==========================================================================
    def setFontFamily(self, family: str) -> bool:
        """Set the font family, falling back if the font is not installed.

        Args:
            family: The font family name to use.

        Returns:
            True if the family is installed and applied; False otherwise.
        """
        if family not in set(QFontDatabase.families()):
            return False
        self._fontFamily = family
        self._applyFont()
        return True

    # ==========================================================================
    def setFontSize(self, size: float) -> None:
        """Set the font point size.

        Args:
            size: The point size to apply. Must be greater than zero.
        """
        if size <= 0:
            return
        self._fontSize = size
        self._applyFont()

    # ==========================================================================
    def setAlignment(self, alignment: Qt.AlignmentFlag) -> None:
        """Set the paragraph alignment for all blocks, existing and new.

        Args:
            alignment: The alignment flag to apply to every text block.
        """
        doc = self.document()
        to = doc.defaultTextOption()
        to.setAlignment(alignment)
        doc.setDefaultTextOption(to)

        self._syncBlockAlignment()

    # ==========================================================================
    def setShowWhitespace(self, enabled: bool) -> None:
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

    # ==========================================================================
    def setPlainText(self, text: str) -> None:
        """Replace the entire document text.

        The replacement text carries no region tags: all of it belongs to
        the :data:`~pyraya.regions.defaultRegionKind` kind (the
        highlighter paints untagged runs with the default background at
        display time), and ``regionsChanged`` is emitted for a non-empty
        replacement.

        Args:
            text: The new document text.
        """
        super().setPlainText(text)
        if self.document().characterCount() > 1:
            self.regionsChanged.emit()

    # ==========================================================================
    def addFormatRule(self, pattern: QRegularExpression, charFormat: QTextCharFormat) -> None:
        """Add a formatting rule to the highlighter.

        Args:
            pattern: The regular expression to match.
            charFormat: The character format to apply to matches.
        """
        self._highlighter.addRule(pattern, charFormat)

    # ==========================================================================
    def setFormatRules(self, rules: Sequence[tuple[QRegularExpression, QTextCharFormat]]) -> None:
        """Replace the highlighter's formatting rules.

        Args:
            rules: An iterable of ``(pattern, charFormat)`` tuples.
        """
        self._highlighter.setRules(rules)

    # ==========================================================================
    def clearFormatRules(self) -> None:
        """Remove all formatting rules from the highlighter."""
        self._highlighter.clearRules()

    # ==========================================================================
    def regions(self) -> list[TextRegion]:
        """Return the document's text regions as sorted, non-overlapping spans.

        The spans always partition the whole text: text without a
        non-default tag carries the background color of
        :data:`~pyraya.regions.defaultRegionKind` and is reported as a span
        of that kind.

        Returns:
            A list of :class:`~pyraya.regions.TextRegion` spans ordered by
            start offset.
        """
        return self._regionSpans()

    # ==========================================================================
    def setRegionType(
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
        self._applyRegionFormat(start, end, kind)
        self.regionsChanged.emit()

    # ==========================================================================
    def regionTypeAt(self, position: int) -> RegionType | None:
        """Return the region kind covering a character offset.

        Args:
            position: The character offset to query.

        Returns:
            The :class:`~pyraya.regions.RegionType` of the region containing
            the offset. Every text offset belongs to exactly one kind (text
            without a non-default tag belongs to
            :data:`~pyraya.regions.defaultRegionKind`), so None is returned
            only for offsets at or past the document's trailing terminator.
        """
        if not 0 <= position < self.document().characterCount() - 1:
            return None
        return self._regionKindAt(position)

    # ==========================================================================
    def clearRegions(self) -> None:
        """Reset all text to :data:`~pyraya.regions.defaultRegionKind`.

        Every region tag is removed and the text is repainted with the
        default kind's background color, so the whole document becomes a
        single default-kind region.
        """
        if not self._regionSpans():
            return
        self._clearRange(0, self.document().characterCount())
        self.regionsChanged.emit()

    # ==========================================================================
    def setRegionColor(self, kind: RegionType, color: QColor) -> bool:
        """Change the background color used for a region type.

        Existing regions of that type are recoloured immediately. Because a
        color is a kind's identity, colors are compared — and must remain
        unique — including the alpha channel; a color equal to another
        kind's color is rejected.

        Args:
            kind: The region type to recolour.
            color: The new background color; its alpha controls subtlety.

        Returns:
            True if the color was applied; False if it equals another
            kind's color (including its alpha channel).
        """
        color = QColor(color)
        for otherKind, otherColor in RegionColors.items():
            if otherKind == kind or color != otherColor:
                continue
            return False
        oldColor = RegionColors[kind]
        if color == oldColor:
            return True
        # Block the document signals while the characters are recoloured: a
        # re-highlight mid-loop would treat the new color as unrecognized (it
        # is not in RegionColors yet) and repaint the recoloured characters
        # back to the default kind.
        document = self.document()
        document.blockSignals(True)
        try:
            for position in range(document.characterCount() - 1):
                if self._charFormatAt(position).background().color() == oldColor:
                    cursor = self.textCursor()
                    cursor.setPosition(position)
                    cursor.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
                    fmt = QTextCharFormat()
                    fmt.setBackground(QBrush(color))
                    cursor.mergeCharFormat(fmt)
        finally:
            document.blockSignals(False)
        RegionColors[kind] = color
        self.viewport().update()
        self.regionsChanged.emit()
        return True

    # ==========================================================================
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
        hasSelection = cursor.hasSelection()

        for kind, label in (
            (RegionType.Latin, "Region: Latin"),
            (RegionType.RomanUrdu, "Region: Roman Urdu"),
        ):
            action = QAction(label, self)
            action.setEnabled(hasSelection)
            action.triggered.connect(lambda _checked, k=kind: self.setRegionType(k))
            menu.addAction(action)

        region = self._regionUnderCursor()
        clearOne = QAction("Clear region under cursor", self)
        clearOne.setEnabled(region is not None)
        if region is not None:
            clearOne.triggered.connect(
                lambda _checked, s=region.start, e=region.end: self._clearRange(s, e)
            )
        menu.addAction(clearOne)

        clearAll = QAction("Clear all regions", self)
        clearAll.setEnabled(bool(self._regionSpans()))
        clearAll.triggered.connect(self.clearRegions)
        menu.addAction(clearAll)
        return menu

    # ==========================================================================
    def _onCustomContextMenuRequested(self, position: QPoint) -> None:
        """Show the context menu where it was requested.

        Args:
            position: The request position in viewport coordinates.
        """
        self._showPopup(self.createPopupMenu(), self.viewport().mapToGlobal(position))

    # ==========================================================================
    def _showPopup(self, menu: QMenu, position: QPoint) -> None:
        """Show the widget's context menu at the given global position."""
        menu.exec(position)

    # ==========================================================================
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
                self.setRegionType(RegionType.Latin)
                return
            if event.key() == Qt.Key.Key_2 and self.textCursor().hasSelection():
                self.setRegionType(RegionType.RomanUrdu)
                return
        super().keyPressEvent(event)

    # ==========================================================================
    def _applyRegionFormat(self, start: int, end: int, kind: RegionType) -> None:
        """Merge the region's background format over a character range."""
        start, end = self._clampRange(start, end)
        if start >= end:
            return
        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setBackground(QBrush(RegionColors[kind]))
        cursor.mergeCharFormat(fmt)
        self.viewport().update()

    # ==========================================================================
    def _clearRange(self, start: int, end: int) -> None:
        """Reset a character range to :data:`~pyraya.regions.defaultRegionKind`.

        Cleared characters are repainted with the default kind's background
        color, because a format merge cannot restore a ``NoBrush`` background
        once one has been set and the document must never contain untagged
        text.
        """
        start, end = self._clampRange(start, end)
        if start >= end:
            return
        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setBackground(QBrush(RegionColors[defaultRegionKind]))
        cursor.mergeCharFormat(fmt)
        self.viewport().update()

    # ==========================================================================
    def _clampRange(self, start: int, end: int) -> tuple[int, int]:
        """Clamp a character range to the document's real text offsets.

        The document's trailing terminator character — which Qt keeps at the
        end of the last block and which ``characterCount()`` includes — must
        never be formatted: merges spanning it are silently dropped.
        """
        limit = self.document().characterCount() - 1
        return max(0, start), min(limit, end)

    # ==========================================================================
    def _regionSpans(self) -> list[TextRegion]:
        """Reconstruct region spans from the document's character formats.

        Every character belongs to exactly one region kind — text without a
        recognized region background counts as
        :data:`~pyraya.regions.defaultRegionKind` — so the spans partition
        the whole text. The trailing terminator character of the last block
        is never part of a region, so the scan stops before it.
        """
        spans: list[TextRegion] = []
        limit = self.document().characterCount() - 1
        position = 0
        while position < limit:
            kind = self._regionKindAt(position)
            start = position
            while position < limit and self._regionKindAt(position) == kind:
                position += 1
            spans.append(TextRegion(start, position, kind))
        return spans

    # ==========================================================================
    def _regionKindAt(self, position: int) -> RegionType:
        """Return the region kind stored at a character offset.

        A character whose background matches no region color belongs to
        :data:`~pyraya.regions.defaultRegionKind`, keeping the invariant
        that every character belongs to exactly one kind.
        """
        color = self._charFormatAt(position).background().color()
        for kind, regionColor in RegionColors.items():
            if color == regionColor:
                return kind
        return defaultRegionKind

    # ==========================================================================
    def _regionAt(self, position: int) -> TextRegion | None:
        """Return the full region span containing a character offset, or None.

        The document's trailing terminator character is never part of a
        region, so offsets at or past it return None instead of reading the
        terminator's format (``_charFormatAt`` would otherwise place the
        cursor out of range).
        """
        if not 0 <= position < self.document().characterCount() - 1:
            return None
        for span in self._regionSpans():
            if span.start <= position < span.end:
                return span
        return None

    # ==========================================================================
    def _regionUnderCursor(self) -> TextRegion | None:
        """Return the region span under the cursor, accounting for selection.

        When the cursor has a selection, the region overlapping the selection
        is returned; otherwise the region containing the cursor position.
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            for span in self._regionSpans():
                if span.start < end and start < span.end:
                    return span
        return self._regionAt(cursor.position())

    # ==========================================================================
    def _charFormatAt(self, position: int) -> QTextCharFormat:
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

    # ==========================================================================
    def _resolveDefaultFont(self) -> str:
        """Pick the first font in the stack that is installed on the system.

        Returns:
            The resolved font family; falls back to the default if none of the
            preferred fonts are installed.
        """
        available = set(QFontDatabase.families())
        for family in pyrayaFonts:
            if family in available:
                return family
        return pyrayaFonts[0]

    # ==========================================================================
    def _applyFont(self) -> None:
        """Apply the current font family and size to the widget."""
        font = QFont()
        font.setFamilies([self._fontFamily, "Noto Sans"])
        font.setPointSizeF(self._fontSize)
        self.setFont(font)

    # ==========================================================================
    def _syncBlockAlignment(self) -> None:
        """Apply the default alignment to the entire document.

        Uses the default block format alignment and ensures it is applied across
        the entire document, without triggering new signals.
        """
        self.blockSignals(True)

        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)

        doc = self.document()
        to = doc.defaultTextOption()

        blockFormat = QTextBlockFormat()
        blockFormat.setAlignment(to.alignment())

        cursor.mergeBlockFormat(blockFormat)

        self.setTextCursor(cursor)

        self.blockSignals(False)


# ******************************************************************************

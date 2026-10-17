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
from typing import cast

from PySide6.QtCore import QPoint, QRect, QRegularExpression, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QWidget
from romanalfaz.engine import Suggestion, Vocabulary

from .regions import RegionColors, RegionType, TextRegion, defaultRegionKind
from .roman_input import RomanInputEngine, RomanOverlay

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


def _isArabicChar(char: str) -> bool:
    """Whether a character belongs to the Arabic script block (U+0600–U+06FF)."""
    return "\u0600" <= char <= "\u06ff"


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

    #: Emitted when a roman-input commit writes a word to the document:
    #: ``(word, roman)`` — the word committed (the selected Arabic word, or
    #: the typed roman for a placeholder commit) and the typed roman.
    romanWordCommitted = Signal(str, str)

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
        # Roman-input overlay state: the feature is on by default so the
        # widget is ready for roman Urdu out of the box; the dictionary and
        # engine are owned by the widget (the engine is created lazily on
        # demand).
        self._romanInputEnabled = True
        self._localDictionary = Vocabulary()
        self._romanEngine: RomanInputEngine | None = None
        self._activeWord: tuple[int, int] | None = None
        self._anchorPosition: int | None = None
        self._selectionRange: tuple[int, int] | None = None
        self._committing = False
        self._mouseActive = False
        self._minOverlayWidth: int = 0
        self._overlay: RomanOverlay | None = None
        # PySide6 emits the widget's cursorPositionChanged without its
        # position argument to Python slots, so the sync handler must be
        # argument-free; the document's cursorPositionChanged is not emitted
        # at all by cursor moves, hence the widget-level signal.
        self.cursorPositionChanged.connect(self._syncOverlay)
        document.contentsChanged.connect(self._syncOverlay)

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
    def setRomanInputEnabled(self, enabled: bool) -> None:
        """Enable or disable the roman-script overlay input feature.

        Enabled by default so the widget is ready for roman Urdu out of the
        box. While disabled, roman keystrokes type into the document as
        before and no overlay machinery runs. Enabling the feature only marks
        it ready —
        the :class:`~pyraya.roman_input.RomanInputEngine` (and its dictionary
        load) happens on first overlay activation.

        Args:
            enabled: Whether the overlay input feature is active.
        """
        self._romanInputEnabled = enabled
        if not enabled:
            self._deactivateOverlay()

    # ==========================================================================
    def isRomanInputEnabled(self) -> bool:
        """Whether the roman-script overlay input feature is enabled."""
        return self._romanInputEnabled

    # ==========================================================================
    def localDictionary(self) -> Vocabulary:
        """The document-local in-memory :class:`romanalfaz.Vocabulary`.

        Owned by the widget and passed to the engine on lazy load. It is the
        hook for the future ``learnRomanWord`` update;
        ``Vocabulary.save``/``Vocabulary.load`` exist for persistence, and it
        is never mutated in this session.

        Returns:
            The same in-memory :class:`Vocabulary` instance, every time.
        """
        return self._localDictionary

    # ==========================================================================
    def romanEngine(self) -> RomanInputEngine | None:
        """The roman-input engine, or ``None`` while the feature is disabled.

        Lazily creates the engine (with its ~0.2 s dictionary cold load) on
        first call while the feature is enabled; subsequent calls return the
        same instance.

        Returns:
            The engine when the feature is enabled; ``None`` otherwise.
        """
        if not self._romanInputEnabled:
            return None
        if self._romanEngine is None:
            self._romanEngine = RomanInputEngine(self._localDictionary)
        return self._romanEngine

    # ==========================================================================
    def _syncOverlay(self, *, bypassMouse: bool = False) -> None:
        """Activate, reposition, or deactivate the overlay for the cursor.

        Returns early while the feature is disabled, a commit is in
        progress, or — unless ``bypassMouse`` — a mouse button is held down:
        a drag is moving the document cursor, and the overlay would
        reposition mid-drag, and, when it crosses the word boundary,
        deactivate and refocus the document. The explicit resync after a
        commit (:meth:`_onOverlayCommitted`) passes ``bypassMouse``: the
        commit has already reconciled the overlay state, and the button
        being held down is unrelated, so suppressing there would delay the
        reconciliation until the release.
        """
        if (
            not self._romanInputEnabled
            or self._committing
            or (self._mouseActive and not bypassMouse)
        ):
            return
        word = self._wordUnderCursor()
        if word is None:
            self._deactivateOverlay()
        elif self._overlay is None or self._activeWord != word:
            self._activateOverlay(word)
        else:
            self._positionOverlay(word)

    # ==========================================================================
    def _wordUnderCursor(self) -> tuple[int, int] | None:
        """The maximal Arabic-script word run containing the document cursor.

        The cursor must sit at the start of the run or inside it (``s <= p < e``);
        a cursor past the run's end — including the document's trailing
        terminator — belongs to no word. The run must be fully contained in a
        RomanUrdu region; otherwise no word is returned.
        """
        document = self.document()
        limit = document.characterCount() - 1
        position = min(self.textCursor().position(), limit)
        text = document.toPlainText()
        start = position
        while start > 0 and _isArabicChar(text[start - 1]):
            start -= 1
        end = position
        while end < len(text) and _isArabicChar(text[end]):
            end += 1
        if not (start <= position < end):
            return None
        if (
            self._regionKindAt(start) is not RegionType.RomanUrdu
            or self._regionKindAt(end - 1) is not RegionType.RomanUrdu
        ):
            return None
        return (start, end)

    # ==========================================================================
    def _wordRect(self, start: int, end: int) -> QRect:
        """The word's rectangle in viewport coordinates.

        Uses the text layout's line geometry — ``cursorToX`` at the word's
        start and end (translated by ``contentOffset()``) — with a
        ``QFontMetrics`` advance fallback when the layout cannot resolve the
        line.
        """
        document = self.document()
        offset = self.contentOffset()
        cursor = QTextCursor(document)
        cursor.setPosition(start)
        block = cursor.block()
        layout = block.layout()
        line = layout.lineForTextPosition(start)
        if line is None:
            rect = layout.boundingRect()
            metrics = QFontMetrics(self.font())
            width = metrics.horizontalAdvance(document.toPlainText()[start:end])
            return QRect(
                round(rect.left() + offset.x()),
                round(rect.top() + offset.y()),
                max(1, width),
                int(rect.height()),
            )
        # PySide6 types cursorToX as returning an untyped point, which is a
        # plain (x, y) tuple at runtime; cast to the actual shape.
        pointStart = cast("tuple[float, float]", line.cursorToX(start))
        pointEnd = cast("tuple[float, float]", line.cursorToX(end))
        left = min(pointStart[0], pointEnd[0])
        right = max(pointStart[0], pointEnd[0])
        return QRect(
            round(left + offset.x()),
            round(line.rect().top() + offset.y()),
            max(1, round(right - left)),
            int(line.rect().height()),
        )

    # ==========================================================================
    def _positionOverlay(self, word: tuple[int, int]) -> None:
        """Place and size the overlay over the word's rectangle.

        The overlay's right edge is anchored to the word's right edge (so the
        right-aligned line edit grows leftward, matching the document flow);
        the width floor is the word's rect width, so the overlay never
        narrows below the word it covers.
        """
        wordRect = self._wordRect(word[0], word[1])
        self._minOverlayWidth = wordRect.width()
        # QRect.right() is inclusive; the exclusive right edge is +1, so the
        # overlay's right border sits exactly on the word's right edge.
        self._placeOverlay(wordRect.right() + 1, wordRect.top())

    # ==========================================================================
    def _placeOverlay(self, rightX: int, top: int) -> None:
        """Place and size the overlay with its right edge at ``rightX``.

        The right-aligned line edit grows leftward from ``rightX``, matching
        the document flow; the width is the wider of the size hint and the
        activation width floor (``_minOverlayWidth``), so typed text that
        outgrows the anchor width still fits. The overlay is clamped to stay
        inside the viewport, flipping above the anchor when the suggestion
        list would overflow the bottom.
        """
        overlay = self._overlay
        if overlay is None:
            return
        hint = overlay.sizeHint()
        width = max(hint.width(), self._minOverlayWidth)
        viewport = self.viewport()
        x = rightX - width
        y = top
        if y + hint.height() > viewport.height():
            y = top - hint.height()
        x = max(0, min(x, viewport.width() - width))
        y = max(0, y)
        overlay.move(x, y)
        overlay.resize(width, hint.height())

    # ==========================================================================
    def _cursorAnchor(self, position: int) -> tuple[int, int]:
        """The cursor's (right x, line top) anchor in viewport coordinates.

        ``rightX`` is the exclusive right edge of the cursor position, so a
        right-aligned overlay anchored there grows leftward as the user
        types the new word.
        """
        document = self.document()
        offset = self.contentOffset()
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        block = cursor.block()
        layout = block.layout()
        line = layout.lineForTextPosition(position)
        if line is None:
            rect = layout.boundingRect()
            return (round(rect.right() + offset.x()), round(rect.top() + offset.y()))
        # PySide6 types cursorToX as returning an untyped point, which is a
        # plain (x, y) tuple at runtime; cast to the actual shape.
        point = cast("tuple[float, float]", line.cursorToX(position))
        return (round(point[0] + offset.x()), round(line.rect().top() + offset.y()))

    # ==========================================================================
    def _ensureOverlay(self, engine: RomanInputEngine) -> RomanOverlay:
        """Return the overlay, creating and wiring it lazily on demand.

        The overlay is created at most once, as a child of the viewport so it
        scrolls with the text automatically; its ``canceled`` and ``committed``
        signals, and the line edit's ``textChanged`` signal (the width
        re-placement hook), are wired at creation.
        """
        overlay = self._overlay
        if overlay is None:
            overlay = RomanOverlay(engine, self.font(), self.viewport())
            overlay.canceled.connect(self._deactivateOverlay)
            overlay.committed.connect(self._onOverlayCommitted)
            overlay.lineEdit().textChanged.connect(self._onOverlayTextChanged)
            self._overlay = overlay
        return overlay

    # ==========================================================================
    def _activateOverlay(self, word: tuple[int, int]) -> None:
        """Show the overlay over the word with its romanization as text.

        Focus moves into the overlay's line edit, where all subsequent typing
        happens; the document is left untouched until a commit.
        """
        engine = self.romanEngine()
        if engine is None:
            return
        overlay = self._ensureOverlay(engine)
        document = self.document()
        overlay.setText(engine.romanizeArabic(document.toPlainText()[word[0] : word[1]]))
        self._activeWord = word
        self._anchorPosition = word[0]
        self._positionOverlay(word)
        overlay.show()
        overlay.lineEdit().setFocus()

    # ==========================================================================
    def _activateOverlayAt(self, text: str, position: int) -> None:
        """Show the overlay at the cursor with ``text`` as its initial text.

        Scenario 1 (a new word): the typed character seeds the overlay and
        ``position`` is stored as the commit anchor; the character is never
        written to the document. If the cursor has a selection, the
        selection range is recorded so a commit replaces it; the selection
        is left visible while the user edits in the overlay.
        """
        engine = self.romanEngine()
        if engine is None:
            return
        overlay = self._ensureOverlay(engine)
        cursor = self.textCursor()
        self._selectionRange = (
            (cursor.selectionStart(), cursor.selectionEnd()) if cursor.hasSelection() else None
        )
        overlay.setText(text)
        self._activeWord = None
        self._anchorPosition = position
        # No word to cover: the width floor is the advance of four roman
        # characters, so the overlay does not collapse as the seeded text is
        # edited.
        self._minOverlayWidth = 4 * overlay.lineEdit().fontMetrics().averageCharWidth()
        rightX, top = self._cursorAnchor(position)
        self._placeOverlay(rightX, top)
        overlay.show()
        overlay.lineEdit().setFocus()

    # ==========================================================================
    def _deactivateOverlay(self) -> None:
        """Hide the overlay, clear the overlay state, and refocus the document."""
        if self._overlay is not None:
            self._overlay.hide()
        self._activeWord = None
        self._anchorPosition = None
        self._selectionRange = None
        self._minOverlayWidth = 0
        self.setFocus()

    # ==========================================================================
    def _overlayActive(self) -> bool:
        """Whether the overlay is currently shown over the document."""
        return self._overlay is not None and self._overlay.isVisible()

    # ==========================================================================
    def _onOverlayTextChanged(self, text: str) -> None:
        """Re-place the overlay so its width tracks the line edit's text.

        Typing in the overlay edits only the line edit (the document is
        untouched), so the overlay is re-placed from the activation anchor
        with the width floored at the activation minimum: over an existing
        word (scenario 2) the word rect, at a seeded cursor (scenario 1) the
        stored four-roman-character baseline. The signal also fires from the
        activation ``setText`` calls, which precede the initial placement;
        the visibility and commit guards skip those.
        """
        if not self._overlayActive() or self._committing:
            return
        if self._activeWord is not None:
            self._positionOverlay(self._activeWord)
        elif self._anchorPosition is not None:
            rightX, top = self._cursorAnchor(self._anchorPosition)
            self._placeOverlay(rightX, top)

    # ==========================================================================
    def _onOverlayCommitted(
        self, typedRoman: str, selected: object, isPlaceholder: bool, separator: str
    ) -> None:
        """Handle the overlay's commit and write to the document.

        A separator-key commit (Space, Enter, typed punctuation) inserts the
        committed word plus the separator character as a single undoable edit:
        over an existing word (scenario 2) the word's span is replaced, at a
        bare cursor (scenario 1) the text is inserted at the anchor position —
        or, if the cursor had a selection, that selection is replaced.
        The word and the separator both carry the :class:`RomanUrdu` region
        background. An edge commit writes nothing and moves the cursor to the
        adjacent Arabic word in visual order — Left at the visually left edge
        (the start of the overlay text) to the next word, Right at the
        visually right edge (the end) to the previous one — or, with no
        adjacent word, hides the overlay and leaves the cursor at the word's
        visually left edge.

        ``romanWordCommitted`` is emitted for a non-empty committed word, and
        ``regionsChanged`` only for an empty-text scenario-2 commit, which
        deletes the word's span.
        """
        engine = self.romanEngine()
        overlay = self._overlay
        if engine is None or not engine.available or overlay is None:
            self._deactivateOverlay()
            return
        self._committing = True
        resync = True
        try:
            word = ""
            if typedRoman:
                if isPlaceholder:
                    word = engine.learnRomanWord(typedRoman)
                elif isinstance(selected, Suggestion):
                    word = selected.arabic
            if separator == "":
                # Edge commit: nothing is written to the document. Left at the
                # visually left edge (the start of the overlay text) moves to
                # the next Arabic word; Right at the visually right edge (the
                # end) to the previous one. With no adjacent word the cursor
                # lands at the word's visually left edge, outside the word, so
                # the overlay does not re-activate on the next key press.
                atStart = overlay.lineEdit().cursorPosition() == 0
                if self._activeWord is not None:
                    reference = self._activeWord[1] if atStart else self._activeWord[0]
                else:
                    reference = self._anchorPosition or 0
                adjacent = self._adjacentWord(reference, not atStart)
                if adjacent is None:
                    if self._activeWord is not None:
                        cursor = self.textCursor()
                        cursor.setPosition(self._activeWord[1])
                        self.setTextCursor(cursor)
                    self._deactivateOverlay()
                else:
                    cursor = self.textCursor()
                    cursor.setPosition(adjacent[0])
                    self.setTextCursor(cursor)
            else:
                cursor = self.textCursor()
                fmt = QTextCharFormat()
                fmt.setBackground(QBrush(RegionColors[RegionType.RomanUrdu]))
                if self._activeWord is not None:
                    start, end = self._activeWord
                    cursor.setPosition(start)
                    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                    if word == "":
                        # The span is deleted; the region changed.
                        self.regionsChanged.emit()
                elif self._selectionRange is not None:
                    # Scenario 1 over a selection: replace the selection,
                    # plain QPlainTextEdit typing semantics.
                    start, end = self._selectionRange
                    cursor.setPosition(start)
                    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                else:
                    cursor.setPosition(self._anchorPosition or 0)
                cursor.insertText(word + separator, fmt)
                if word:
                    self.romanWordCommitted.emit(word, typedRoman)
                self.setTextCursor(cursor)
                self._deactivateOverlay()
        finally:
            self._committing = False
            if resync:
                # Explicit resync: bypasses the mouse flag, so the
                # reconciliation still runs even if a button happens to be
                # held down (see ``_syncOverlay``).
                self._syncOverlay(bypassMouse=True)

    # ==========================================================================
    def _adjacentWord(self, reference: int, atStart: bool) -> tuple[int, int] | None:
        """The nearest Arabic-script word run adjacent to ``reference``.

        When ``atStart`` is true the run is searched left of ``reference``
        (the previous word); otherwise right of it (the next word). Non-Arabic
        characters — whitespace, digits, Latin letters — are skipped.
        """
        text = self.document().toPlainText()
        if atStart:
            index = reference - 1
            while index >= 0 and not _isArabicChar(text[index]):
                index -= 1
            if index < 0:
                return None
            start = index
            while start > 0 and _isArabicChar(text[start - 1]):
                start -= 1
            return (start, index + 1)
        index = reference
        while index < len(text) and not _isArabicChar(text[index]):
            index += 1
        if index >= len(text):
            return None
        end = index
        while end < len(text) and _isArabicChar(text[end]):
            end += 1
        return (index, end)

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
        """Handle region shortcuts and intercept roman-input keystrokes.

        ``Ctrl+1`` tags the current selection as Latin and ``Ctrl+2`` tags
        it as Roman Urdu. While the roman-input feature is enabled and the
        overlay is inactive, an ASCII alphanumeric key pressed with the
        cursor inside a RomanUrdu region seeds the overlay with that
        character (scenario 1); the character never reaches the document.
        Plain Left/Right (no modifiers) move the cursor in visual (screen)
        order — Left to the next position, Right to the previous one —
        because Qt's default logical movement is flipped in this
        right-to-left document; modifier variants keep Qt's default logical
        behavior. Everything else falls through to the default handler.

        Args:
            event: The key-press event.
        """
        if (
            self._romanInputEnabled
            and not self._overlayActive()
            and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            text = event.text()
            if len(text) == 1 and text.isascii() and text.isalnum():
                if self._regionKindForTyping() is RegionType.RomanUrdu:
                    self._activateOverlayAt(text, self.textCursor().position())
                    return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_1 and self.textCursor().hasSelection():
                self.setRegionType(RegionType.Latin)
                return
            if event.key() == Qt.Key.Key_2 and self.textCursor().hasSelection():
                self.setRegionType(RegionType.RomanUrdu)
                return
        if event.modifiers() == Qt.KeyboardModifier.NoModifier and event.key() in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
        ):
            # Plain arrow keys move in visual (screen) order, not Qt's
            # default logical character order, which is flipped in this
            # right-to-left document: Left advances the position, Right
            # retreats it.
            position = self.textCursor().position()
            if event.key() == Qt.Key.Key_Left:
                position = min(position + 1, self.document().characterCount() - 1)
            else:
                position = max(position - 1, 0)
            cursor = QTextCursor(self.document())
            cursor.setPosition(position)
            self.setTextCursor(cursor)
            event.accept()
            return
        super().keyPressEvent(event)

    # ==========================================================================
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Take ownership of a mouse press: deactivate a shown overlay.

        The overlay is mouse-transparent, so a press in the document area
        reaches the document even while the overlay is shown; this handler
        makes the press deactivate the overlay before the default handling
        (which places the cursor and starts any selection), and marks the
        mouse as active so ``_syncOverlay`` is suppressed until the button
        is released (:meth:`mouseReleaseEvent`).

        Args:
            event: The mouse press event.
        """
        if self._overlayActive():
            self._deactivateOverlay()
        self._mouseActive = True
        super().mousePressEvent(event)

    # ==========================================================================
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Clear the mouse-active flag and resync the overlay.

        The press that set ``_mouseActive`` is complete: the document
        cursor has settled, so the overlay state is reconciled — a release
        on a RomanUrdu word re-activates the overlay over it (scenario 2),
        with focus in the line edit.

        Args:
            event: The mouse release event.
        """
        super().mouseReleaseEvent(event)
        if self._mouseActive:
            self._mouseActive = False
            self._syncOverlay()

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
    def _regionKindForTyping(self) -> RegionType | None:
        """The region kind for the scenario-1 typing gate at the cursor.

        A cursor with a selection resolves the region overlapping the
        selection. A bare cursor at the document end (``position ==
        characterCount() - 1``) resolves to the kind of the last real
        character before the cursor — the trailing terminator itself never
        belongs to a region — and an empty document to
        :data:`~pyraya.regions.defaultRegionKind`; any other position
        resolves the region containing it. Positions past the document end
        return None.
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            for span in self._regionSpans():
                if span.start < end and start < span.end:
                    return span.kind
        document = self.document()
        position = cursor.position()
        limit = document.characterCount() - 1
        if not 0 <= position <= limit:
            return None
        if position == limit:
            if document.characterCount() == 1:
                return defaultRegionKind
            return self._regionKindAt(position - 1)
        return self._regionKindAt(position)

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

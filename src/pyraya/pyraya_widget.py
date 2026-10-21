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
:data:`~pyraya.regions.DefaultRegionKind` — and each region kind is
identified by a unique background color, compared including its alpha
channel.
"""

from collections.abc import Callable, Sequence
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
    QResizeEvent,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import QLayout, QMenu, QPlainTextEdit, QWidget
from romanalfaz.engine import Suggestion, Vocabulary

from .regions import DefaultRegionKind, RegionColors, RegionType, TextRegion
from .roman_input import ArabicScriptSeparators, RomanInputEngine, RomanOverlay

__all__ = ["PyRaya", "PyRayaHighlighter"]

# ******************************************************************************
#: Preferred font stack, in order of preference. The first entry is the default.
PyRayaFonts: tuple[str, ...] = (
    "Baloo Bhaijaan 2",
    "Noto Naskh Arabic",
    "Noto Nastaliq Urdu",
    "Noto Sans Arabic",
    "Amiri",
    "Scheherazade New",
    "Geeza Pro",
)

#: Default point size applied to the default font.
DefaultFontSize: float = 14.0

#: Muted brick red used for the spell-check underline.
SpellCheckUnderlineColor: QColor = QColor("#B22222")


def _isArabicChar(char: str) -> bool:
    """Whether a character is Arabic-script word matter.

    The Arabic script block (U+0600-U+06FF) minus the Arabic script's own
    separator marks (:data:`ArabicScriptSeparators`): the marks terminate
    a word run exactly like the Latin marks do, so ``کام۔`` is the word
    ``کام`` followed by the separator ``۔`` — the separator commits as a
    separator key and is never scanned as part of a word.
    """
    return "\u0600" <= char <= "\u06ff" and char not in ArabicScriptSeparators


# ******************************************************************************
class PyRayaHighlighter(QSyntaxHighlighter):
    """Rule-based formatting highlighter for Urdu and mixed-script text.

    Formatting is driven by an ordered list of ``(QRegularExpression,
    QTextCharFormat)`` rules. Rules are applied in order, and later rules
    override earlier ones for overlapping matches, so broad rules should
    precede specific ones.

    The highlighter also keeps the region invariant: on every re-highlight,
    runs whose background matches no region color are painted with the
    :data:`~pyraya.regions.DefaultRegionKind` background in the text
    layout, which Qt merges with the document's character formats at
    display time. That maintenance paints the layout rather than editing
    the document, so it is not recorded in the document's undo stack and
    cannot bury user edits behind it.

    Args:
        document: The document to highlight.
        engineProvider: Optional callable returning the roman-input
            engine (or ``None``) that the spell-check pass queries for
            dictionary membership; ``None`` disables the pass. When
            provided, the pass is gated by the highlighter's own
            :meth:`isSpellCheckEnabled` flag.
    """

    # ==========================================================================
    def __init__(
        self,
        document: QTextDocument,
        engineProvider: Callable[[], RomanInputEngine | None] | None = None,
    ) -> None:
        super().__init__(document)
        self._engineProvider = engineProvider
        self._spellCheckEnabled = True
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

        After the rules, characters without a recognized region
        background get the
        :data:`~pyraya.regions.DefaultRegionKind` background merged into
        the text layout (:meth:`_paintDefaultRegions`). When spell
        check is enabled, RomanUrdu words the
        dictionary does not know additionally get the wavy spell-check
        underline, painted into the text layout only (see
        :meth:`setSpellCheckEnabled`).

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
        self._underlineUnknownWords(block)

    # ==========================================================================
    def _paintDefaultRegions(self, block: str) -> None:
        """Paint runs without a recognized region background.

        Runs are painted with the
        :data:`~pyraya.regions.DefaultRegionKind` background in the text
        layout; the document's character formats are not modified. The
        background is merged into each untagged character's current
        layout format (read back with :meth:`format`) rather than painted
        as a background-only format: ``QSyntaxHighlighter.setFormat``
        replaces the whole per-character format, so a background-only
        write would wipe the rules' foregrounds — untagged text would
        fall back to the default ink instead of the rule colors, and with
        visible whitespace the space's designed light-gray dot would
        render as a heavy black mark.

        Args:
            block: The text of the block being highlighted.
        """
        current = self.currentBlock()
        base = current.position()
        limit = len(block)
        cursor = QTextCursor(self.document())
        for position in range(limit):
            cursor.setPosition(base + position + 1)
            if self._hasRegionBackground(cursor.charFormat()):
                continue
            merged = self.format(position)
            merged.setBackground(QBrush(RegionColors[DefaultRegionKind]))
            self.setFormat(position, 1, merged)

    # ==========================================================================
    @staticmethod
    def _hasRegionBackground(charFormat: QTextCharFormat) -> bool:
        """Return True if the format carries a recognized region background."""
        color = charFormat.background().color()
        return any(color == regionColor for regionColor in RegionColors.values())

    # ==========================================================================
    def setSpellCheckEnabled(self, enabled: bool) -> None:
        """Enable or disable the spell-check underline, re-highlighting.

        While enabled, RomanUrdu words the dictionary does not know get
        the wavy :data:`SpellCheckUnderlineColor` underline in the text
        layout (display only — the document's character formats and the
        undo stack are never touched). Toggling re-highlights the whole
        document, so the underline is removed or restored immediately.

        Args:
            enabled: Whether unknown RomanUrdu words are underlined.
        """
        if self._spellCheckEnabled == enabled:
            return
        self._spellCheckEnabled = enabled
        self.rehighlight()

    # ==========================================================================
    def isSpellCheckEnabled(self) -> bool:
        """Whether the spell-check underline is active."""
        return self._spellCheckEnabled

    # ==========================================================================
    def _underlineUnknownWords(self, block: str) -> None:
        """Paint the wavy spell-check underline under unknown RomanUrdu words.

        The maximal Arabic-script runs whose ends both belong to RomanUrdu
        regions are collected as candidate words first; with no candidates
        the pass returns without touching the engine provider, so the
        engine (and its dictionary cold load) is created only the first
        time a block containing a candidate word is re-highlighted. Each
        candidate is then consulted against the engine, and a word the
        dictionary does not know is underlined with
        :data:`SpellCheckUnderlineColor` in the text layout, merged over
        the character's other layout formats. The document's character
        formats are never modified. The pass is also a no-op while spell
        check is disabled, or when the engine provider returns ``None`` or
        an unavailable engine (a missing dictionary must never underline
        every word).

        Args:
            block: The text of the block being highlighted.
        """
        if not self._spellCheckEnabled:
            return
        base = self.currentBlock().position()
        limit = len(block)
        candidates: list[tuple[int, int]] = []
        position = 0
        while position < limit:
            if not _isArabicChar(block[position]):
                position += 1
                continue
            start = position
            while position < limit and _isArabicChar(block[position]):
                position += 1
            end = position
            if (
                self._regionKindAt(base + start) is not RegionType.RomanUrdu
                or self._regionKindAt(base + end - 1) is not RegionType.RomanUrdu
            ):
                continue
            candidates.append((start, end))
        if not candidates:
            return
        provider = self._engineProvider
        engine = provider() if provider is not None else None
        if engine is None or not engine.available:
            return
        for start, end in candidates:
            if engine.hasWord(block[start:end]):
                continue
            for pos in range(start, end):
                merged = self.format(pos)
                merged.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
                merged.setUnderlineColor(SpellCheckUnderlineColor)
                self.setFormat(pos, 1, merged)

    # ==========================================================================
    def _regionKindAt(self, position: int) -> RegionType:
        """Return the region kind stored at a document character offset.

        A character whose background matches no region color belongs to
        :data:`~pyraya.regions.DefaultRegionKind`, keeping the invariant
        that every character belongs to exactly one kind.
        """
        cursor = QTextCursor(self.document())
        cursor.setPosition(position + 1)
        color = cursor.charFormat().background().color()
        for kind, regionColor in RegionColors.items():
            if color == regionColor:
                return kind
        return DefaultRegionKind

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
    :data:`~pyraya.regions.DefaultRegionKind` kind — and clearing regions
    resets the text to that kind.
    """

    regionsChanged = Signal()

    #: Emitted when a roman-input commit writes a word to the document:
    #: ``(word, roman)`` — the word committed (the selected Arabic word, or
    #: the typed roman for an undefined-word commit) and the typed roman.
    romanWordCommitted = Signal(str, str)

    # ==========================================================================
    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the widget.

        Args:
            parent: Optional parent widget; defaults to a top-level window.
        """
        super().__init__(parent)
        self._fontFamily = self._resolveDefaultFont()
        self._fontSize: float = DefaultFontSize
        self._alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight
        self._applyFont()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setShowWhitespace(True)
        # Roman-input overlay state: the feature and assist mode are on by
        # default so the widget is ready for roman Urdu out of the box; the
        # dictionary and engine are owned by the widget (the engine is
        # created lazily on demand). All of these fields must exist before
        # the highlighter is constructed: its constructor re-highlights
        # (even the empty) document, and the spell-check pass queries the
        # shared engine through the provider passed below.
        self._romanInputEnabled = True
        self._assistMode = True
        self._localDictionary = Vocabulary()
        self._romanEngine: RomanInputEngine | None = None
        self._activeWord: tuple[int, int] | None = None
        self._anchorPosition: int | None = None
        # A view-caused suspension of the overlay: the word-rect hit test
        # (scroll, resize, reflow) deactivated the overlay while its word
        # was fully outside the viewport, and remembered
        # ``(word, anchorPosition, typedText, documentRevision)`` so the
        # resumption on a view event that reveals the anchor is possible.
        # User decisions (a mouse press, Esc, a new activation) and
        # document edits drop it.
        self._suspendedOverlay: tuple[tuple[int, int] | None, int, str, int] | None = None
        self._selectionRange: tuple[int, int] | None = None
        self._committing = False
        self._mouseActive = False
        self._minOverlayWidth: int = 0
        self._overlay: RomanOverlay | None = None
        self._highlighter = PyRayaHighlighter(self.document(), engineProvider=self._spellEngine)
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
        # PySide6 emits the widget's cursorPositionChanged without its
        # position argument to Python slots, so the sync handler must be
        # argument-free; the document's cursorPositionChanged is not emitted
        # at all by cursor moves, hence the widget-level signal.
        self.cursorPositionChanged.connect(self._syncOverlay)
        document.contentsChanged.connect(self._syncOverlay)
        # The overlay is a viewport child and does not scroll by itself:
        # its position is re-derived from the document's geometry after
        # every scroll so it stays over the word it edits (argument-free
        # receiver like the cursor sync handler above).
        self.verticalScrollBar().valueChanged.connect(self._onScrollChanged)

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
        the :data:`~pyraya.regions.DefaultRegionKind` kind (the
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
        :data:`~pyraya.regions.DefaultRegionKind` and is reported as a span
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
            :data:`~pyraya.regions.DefaultRegionKind`), so None is returned
            only for offsets at or past the document's trailing terminator.
        """
        if not 0 <= position < self.document().characterCount() - 1:
            return None
        return self._regionKindAt(position)

    # ==========================================================================
    def clearRegions(self) -> None:
        """Reset all text to :data:`~pyraya.regions.DefaultRegionKind`.

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
        self._highlighter.rehighlight()
        self.regionsChanged.emit()
        return True

    # ==========================================================================
    def setRomanInputEnabled(self, enabled: bool) -> None:
        """Enable or disable the roman-script overlay input feature.

        Enabled by default so the widget is ready for roman Urdu out of the
        box. While disabled, roman keystrokes type into the document as
        before and no overlay machinery runs. Enabling the feature resets
        assist mode to on and only marks the feature ready — the
        :class:`~pyraya.roman_input.RomanInputEngine` (and its dictionary
        load) happens on first overlay activation.

        Args:
            enabled: Whether the overlay input feature is active.
        """
        self._romanInputEnabled = enabled
        if enabled:
            self._assistMode = True
        else:
            self._deactivateOverlay()

    # ==========================================================================
    def isRomanInputEnabled(self) -> bool:
        """Whether the roman-script overlay input feature is enabled."""
        return self._romanInputEnabled

    # ==========================================================================
    def setAssistEnabled(self, enabled: bool) -> None:
        """Enable or disable overlay assist mode.

        While assist mode is off, the user is left alone: typing and mouse
        presses never activate the overlay, and only Ctrl+Space in the
        document turns the mode back on. Disabling the mode hides a shown
        overlay; enabling it only marks the mode ready and does not show
        the overlay.

        Args:
            enabled: Whether assist mode is active.
        """
        self._assistMode = enabled
        if not enabled:
            self._deactivateOverlay()

    # ==========================================================================
    def isAssistEnabled(self) -> bool:
        """Whether overlay assist mode is enabled.

        While assist mode is off, the user is left alone: typing and mouse
        presses never activate the overlay, and only Ctrl+Space in the
        document turns the mode back on.
        """
        return self._assistMode

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
        return self._ensureEngine()

    # ==========================================================================
    def setSpellCheckEnabled(self, enabled: bool) -> None:
        """Enable or disable the spell-check underline.

        On by default, fully independent of the roman-input feature:
        RomanUrdu words the dictionary does not keep getting the wavy
        underline while roman input is disabled, and vice versa. Toggling
        re-highlights the whole document.

        Args:
            enabled: Whether unknown RomanUrdu words are underlined.
        """
        self._highlighter.setSpellCheckEnabled(enabled)

    # ==========================================================================
    def isSpellCheckEnabled(self) -> bool:
        """Whether the spell-check underline is active."""
        return self._highlighter.isSpellCheckEnabled()

    # ==========================================================================
    def _ensureEngine(self) -> RomanInputEngine:
        """The shared roman-input engine, created lazily when either feature
        needs it.

        Both the roman-input overlay and the spell-check pass consult the
        same engine instance, so the ~0.2 s dictionary cold load happens
        at most once per widget.

        Returns:
            The shared engine, creating it on first use.
        """
        if self._romanEngine is None:
            self._romanEngine = RomanInputEngine(self._localDictionary)
        return self._romanEngine

    # ==========================================================================
    def _spellEngine(self) -> RomanInputEngine:
        """The spell-check pass's engine provider.

        Returns the shared engine unconditionally: the highlighter gates
        the pass on its own switch, and the widget accessor must not
        depend on the roman-input flag or ``romanEngine()``'s
        None-while-disabled contract.
        """
        return self._ensureEngine()

    # ==========================================================================
    def _syncOverlay(self, *, bypassMouse: bool = False) -> None:
        """Activate, reposition, or deactivate the overlay for the cursor.

        Returns early while the feature is disabled, assist mode is off
        (the user is left alone until Ctrl+Space), a commit is in
        progress, or — unless ``bypassMouse`` — a mouse button is held
        down: a drag is moving the document cursor, and the overlay would
        reposition mid-drag, and, when it crosses the word boundary,
        deactivate and refocus the document. The explicit resync after a
        commit (:meth:`_onOverlayCommitted`) passes ``bypassMouse``: the
        commit has already reconciled the overlay state, and the button
        being held down is unrelated, so suppressing there would delay the
        reconciliation until the release.

        The activation is viewport-aware, like the rest of the off/on
        contract: a word the cursor is fully inside the viewport of is
        activated, while a cursor move or keyboard edit that lands the
        cursor on a word scrolled out of the viewport (e.g. a backspace
        inside a scrolled-out word) stays quiet — the cursor's position
        is not a view decision, and a popup over an invisible word would
        be. The same-word resync goes through
        :meth:`_repositionActiveOverlay`, so the word-rect hit test and
        its view-driven suspension apply to cursor moves as well.
        """
        if (
            not self._romanInputEnabled
            or not self._assistMode
            or self._committing
            or (self._mouseActive and not bypassMouse)
        ):
            return
        word = self._wordUnderCursor()
        if word is None:
            self._deactivateOverlay()
            return
        if self._activeWord == word:
            self._repositionActiveOverlay()
            return
        if self.viewport().rect().intersects(self._wordRect(*word)):
            self._activateOverlay(word)

    # ==========================================================================
    def _wordUnderCursor(self) -> tuple[int, int] | None:
        """The maximal Arabic-script word run containing or ending at the document cursor.

        The cursor may sit at the start of the run, inside it, or at its end
        (``s <= p <= e`` with a non-empty run) — including the document's
        trailing terminator position, which clamps to the last real
        character. A cursor with no word run behind it belongs to no word.
        The run must be fully contained in a RomanUrdu region; otherwise no
        word is returned.
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
        if not (start < end and start <= position <= end):
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
        # ``lineForTextPosition`` and ``cursorToX`` take block-local
        # positions: an absolute position overflows the block's own layout
        # past block 0 (yielding a non-None invalid line whose calls
        # segfault), so the block's document offset is subtracted, and the
        # block's content-coordinates origin is added so the line geometry
        # maps to the viewport.
        geometry = self.blockBoundingGeometry(block)
        layout = block.layout()
        local = start - block.position()
        line = layout.lineForTextPosition(local)
        if line is None or not line.isValid():
            rect = layout.boundingRect()
            metrics = QFontMetrics(self.font())
            width = metrics.horizontalAdvance(document.toPlainText()[start:end])
            return QRect(
                round(rect.left() + geometry.x() + offset.x()),
                round(rect.top() + geometry.y() + offset.y()),
                max(1, width),
                int(rect.height()),
            )
        # PySide6 types cursorToX as returning an untyped point, which is a
        # plain (x, y) tuple at runtime; cast to the actual shape.
        pointStart = cast("tuple[float, float]", line.cursorToX(local))
        pointEnd = cast("tuple[float, float]", line.cursorToX(end - block.position()))
        left = min(pointStart[0], pointEnd[0])
        right = max(pointStart[0], pointEnd[0])
        return QRect(
            round(left + geometry.x() + offset.x()),
            round(line.rect().top() + geometry.y() + offset.y()),
            max(1, round(right - left)),
            int(line.rect().height()),
        )

    # ==========================================================================
    def _positionOverlay(self, word: tuple[int, int]) -> None:
        """Place and size the overlay over the word's rectangle.

        The overlay's right edge is anchored to the word's right edge (so the
        right-aligned line edit grows leftward, matching the document flow);
        the width floor is the word's rect width, so the overlay never
        narrows below the word it covers. The line edit stays over the word
        in both orientations: when the list does not fit below the word, it
        flips above the line edit (see :meth:`_placeOverlay`).
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
        outgrows the anchor width still fits. The line edit is pinned to
        ``top`` in both orientations: the suggestion list flips above the
        line edit only when it does not fit below the anchor *and* the
        space above is the larger of the two, so the flipped list is
        clamped to strictly more room than the below orientation offered;
        on a tie — and for a word near the viewport's top, where the space
        above can never hold the list — the default (below) orientation
        wins and the list is truncated below instead of painting out of
        bounds at the viewport's top edge.
        """
        overlay = self._overlay
        if overlay is None:
            return
        hint = overlay.sizeHint()
        viewport = self.viewport()
        width = max(hint.width(), self._minOverlayWidth)
        # The line edit itself stays pinned to the anchor line in both
        # orientations; only the list's side is decided here. The space
        # budgets are the list's: below the line edit the list's bottom
        # edge is the overlay's bottom (``top + hint.height()``), and the
        # flipped list is clamped to the gap over the anchor (``top - 4``).
        listHint = overlay.suggestionList().sizeHint().height()
        belowRoom = viewport.height() - top - hint.height() + listHint
        aboveRoom = top - 4
        # Flip above only when below cannot hold the list AND the space
        # above is strictly larger: ties favor the default orientation,
        # so a first-line word's overlay stays below (clamped) rather
        # than flipping into a space that can never fit the list.
        flip = belowRoom < listHint and aboveRoom > belowRoom
        overlay.setListAbove(flip)
        if flip:
            # The flipped list is clamped to the space above the line
            # edit, which the flip decision guarantees is larger than the
            # space below the anchor would have left it. A hidden list
            # occupies no slot, so the line edit pins to ``top`` exactly.
            listSlot = min(listHint, max(0, aboveRoom))
            height = overlay.lineEdit().sizeHint().height() + 4 + listSlot
            y = top - 4 - listSlot
        else:
            y = top
            height = hint.height()
            # A viewport shorter than the overlay is clamped so the
            # overlay still fits: the line edit leads the layout, so the
            # truncation only squeezes the list against the bottom edge.
            if y + height > viewport.height():
                height = max(0, viewport.height() - y)
        x = rightX - width
        # The right edge is pinned to the anchor in both orientations; a
        # viewport too narrow to show the whole overlay lets it clip on
        # the left — the overlay input stays over the trigger word, and a
        # viewport that cannot show the overlay is adjusted (resized or
        # scrolled) by the user, never worked around by moving the
        # overlay off the word.
        overlay.move(x, y)
        overlay.resize(width, height)
        # A QBoxLayout only re-runs for a visible parent, so a placement
        # on a hidden overlay — a click hides it before the release
        # re-activates it over the word — cannot read the line edit's
        # slot straight back: it answers with the previous word's slots
        # and drags the whole overlay off the word by the slot
        # difference. Force the layout to resolve for the size just set
        # (activation runs while hidden), then read the settled slot and
        # shift the overlay so the pinning is exact in the viewport:
        # ``lineY <= top`` always, since the flipped list's slot is
        # clamped to the gap over the anchor. This is a plain geometry
        # correction: it never touches the document or its undo stack.
        # The overlay's box layout is installed in its constructor, but
        # Qt types ``QWidget.layout`` as nullable, so cast to the
        # concrete shape.
        layout = cast("QLayout", overlay.layout())
        layout.invalidate()
        layout.activate()
        # Snap the overlay's height so the list's allocation is an exact
        # number of rows: a clamped or truncated placement hands the
        # layout an arbitrary pixel height, and the squeezed remainder
        # would paint as a blank strip of list background below the last
        # row. Shrinking by the remainder takes the surplus out of the
        # list (its Maximum size policy absorbs the deficit), leaving the
        # same visible rows on an exact panel.
        sugList = overlay.suggestionList()
        if sugList.rowCount() > 0 and sugList.rowHeight() > 0:
            snapped = sugList.quantizedHeight(sugList.height())
            slack = sugList.height() - snapped
            if slack:
                overlay.resize(width, overlay.height() - slack)
                layout.invalidate()
                layout.activate()
        lineY = overlay.lineEdit().y()
        if y + lineY != top:
            y = max(0, top - lineY)
            overlay.move(x, y)

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
        # ``lineForTextPosition`` and ``cursorToX`` take block-local
        # positions: an absolute position overflows the block's own layout
        # past block 0 (yielding a non-None invalid line whose calls
        # segfault), so the block's document offset is subtracted, and the
        # block's content-coordinates origin is added so the line geometry
        # maps to the viewport.
        geometry = self.blockBoundingGeometry(block)
        layout = block.layout()
        local = position - block.position()
        line = layout.lineForTextPosition(local)
        if line is None or not line.isValid():
            rect = layout.boundingRect()
            return (
                round(rect.right() + geometry.x() + offset.x()),
                round(rect.top() + geometry.y() + offset.y()),
            )
        # PySide6 types cursorToX as returning an untyped point, which is a
        # plain (x, y) tuple at runtime; cast to the actual shape.
        point = cast("tuple[float, float]", line.cursorToX(local))
        return (
            round(point[0] + geometry.x() + offset.x()),
            round(line.rect().top() + geometry.y() + offset.y()),
        )

    # ==========================================================================
    def _ensureOverlay(self, engine: RomanInputEngine) -> RomanOverlay:
        """Return the overlay, creating and wiring it lazily on demand.

        The overlay is created at most once, as a child of the viewport:
        small scrolls shift it with Qt's viewport blit, and the scroll
        re-anchoring hook (:meth:`_onScrollChanged`) re-derives its
        placement after every scroll so it stays exactly over its word.
        Its ``canceled`` and ``committed`` signals, and the line edit's
        ``textChanged`` signal (the width re-placement hook), are wired
        at creation.
        """
        overlay = self._overlay
        if overlay is None:
            overlay = RomanOverlay(engine, self.font(), self.viewport())
            overlay.canceled.connect(self._onOverlayCanceled)
            overlay.committed.connect(self._onOverlayCommitted)
            overlay.lineEdit().textChanged.connect(self._onOverlayTextChanged)
            self._overlay = overlay
        return overlay

    # ==========================================================================
    def _activateOverlay(self, word: tuple[int, int]) -> None:
        """Show the overlay over the word with its romanization as text.

        Focus moves into the overlay's line edit, where all subsequent typing
        happens; the document is left untouched until a commit. The line
        edit's cursor is placed at the position that proportionally
        mirror-maps the document cursor position across the word
        (0..len(roman)) — the document cursor's fraction of the word's
        visual width, scaled to the roman word's length — so arrow keys start
        at the visually corresponding position in visual order.
        """
        engine = self.romanEngine()
        if engine is None:
            return
        overlay = self._ensureOverlay(engine)
        # An explicit activation is a user decision that outranks any
        # pending view suspension.
        self._suspendedOverlay = None
        document = self.document()
        roman = engine.romanizeArabic(document.toPlainText()[word[0] : word[1]])
        overlay.setText(roman)
        # Place the line edit cursor at the position that proportionally
        # mirror-maps the document cursor across the word, so arrow keys
        # move in visual order from the visually corresponding position.
        docPos = self.textCursor().position()
        # Mirror-map docPos (in the document word) into the roman word, 0..len(roman),
        # rounded to the nearest character
        L = word[1] - word[0]
        overlayPos = ((word[1] - docPos) * len(roman) + L // 2) // L
        overlay.lineEdit().setCursorPosition(overlayPos)
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
        # An explicit activation is a user decision that outranks any
        # pending view suspension.
        self._suspendedOverlay = None
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
        """Hide the overlay, clear the overlay state, and refocus the document.

        A view-caused suspension (:attr:`_suspendedOverlay`) is dropped
        too: every caller of this method is a user decision (a mouse
        press, Esc, a programmatic feature or assist switch, an edge
        commit over a boundary word) or an explicit re-evaluation, and
        the user's active/inactive state outranks the view's suspension.
        """
        if self._overlay is not None:
            self._overlay.hide()
        self._activeWord = None
        self._anchorPosition = None
        self._selectionRange = None
        self._minOverlayWidth = 0
        self._suspendedOverlay = None
        self.setFocus()

    # ==========================================================================
    def _overlayActive(self) -> bool:
        """Whether the overlay is currently shown over the document."""
        return self._overlay is not None and self._overlay.isVisible()

    # ==========================================================================
    def _onOverlayCanceled(self) -> None:
        """Handle the overlay's Esc: the user wants to be left alone.

        Turns assist mode off, then deactivates the overlay. This is the
        only path that flips assist mode off — commits and cursor-driven
        deactivation leave it on.
        """
        self._assistMode = False
        self._deactivateOverlay()

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
        self._repositionActiveOverlay()

    # ==========================================================================
    def _repositionActiveOverlay(self) -> None:
        """Re-place the active overlay over its stored anchor.

        The pinning invariant — the overlay input stays over the trigger
        word — holds everywhere and always: the placement is re-derived
        from the document's geometry (the word's rect, or at a seeded
        cursor the stored anchor) so document changes, resizes, and
        scrolls all leave the overlay exactly on its word. It is never
        moved off the word, and never clamped or squeezed out of the
        viewport: a viewport that cannot show the overlay is adjusted
        (resized or scrolled) by the user.

        The off/on-screen hit test is decided on the WORD's rect — the
        seeded anchor's cursor line in scenario 1 — never on the overlay
        widget: the overlay reaches further than its word (a flipped
        suggestion list hangs up into the viewport), so a box-based test
        would keep the popup alive after its word has already left. A
        word whose rect is fully outside the viewport suspends the
        overlay — a view event, remembered in ``_suspendedOverlay`` and
        resumed by the next view event that reveals the anchor — while a
        partially visible word keeps it pinned.
        """
        word = self._activeWord
        anchorPosition = self._anchorPosition
        if word is not None:
            anchorRect = self._wordRect(*word)
        elif anchorPosition is not None:
            cursor = QTextCursor(self.document())
            cursor.setPosition(anchorPosition)
            anchorRect = self.cursorRect(cursor)
        else:
            return
        if not self.viewport().rect().intersects(anchorRect):
            # A view event (scroll, resize, reflow) hid the word — not a
            # user decision. Suspend the overlay so the resumption is
            # keyed on the anchor returning into view: a view event that
            # reveals it (a scroll back, a resize grant, a reflow) can
            # resume without a manual trigger. The seeded overlay's
            # typed text is carried across; a scenario 2 resumption
            # re-derives the word's romanization like any re-activation.
            typedText = (
                "" if word is not None or self._overlay is None else self._overlay.lineEdit().text()
            )
            self._deactivateOverlay()
            self._suspendedOverlay = (
                word,
                anchorPosition or 0,
                typedText,
                self.document().revision(),
            )
            return
        if word is not None:
            self._positionOverlay(word)
        elif anchorPosition is not None:
            rightX, top = self._cursorAnchor(anchorPosition)
            self._placeOverlay(rightX, top)

    # ==========================================================================
    def _restoreSuspendedOverlay(self) -> None:
        """Resume the overlay suspended by its word leaving the viewport.

        The word-rect hit test's deactivation is a view event, not a user
        decision: :attr:`_suspendedOverlay` remembers the anchor, and a
        view event that reveals it — a scroll back, a resize grant, a
        reflow — resumes the overlay without a manual trigger. The
        resumption is the standard activation: scenario 2 re-activates
        over the (unchanged) word with its romanization, scenario 1
        resumes the seeded overlay at the anchor with its typed text.

        The suspension is dropped when it is no longer trustworthy: the
        user decided anything in between (a mouse press, Esc, a new
        activation, the feature or assist switch — all funnel
        :meth:`_deactivateOverlay`), or the document was edited while
        suspended (the remembered document revision no longer matches,
        so the anchor may no longer be the word it was). While a mouse
        button is down the resumption is deferred: starting a pop-up
        mid-drag would steal the gesture.
        """
        suspended = self._suspendedOverlay
        if suspended is None or self._overlayActive() or self._committing:
            return
        if not self._romanInputEnabled or not self._assistMode or self._mouseActive:
            self._suspendedOverlay = None
            return
        word, anchorPosition, typedText, revision = suspended
        if self.document().revision() != revision:
            self._suspendedOverlay = None
            return
        if word is not None:
            anchorRect = self._wordRect(*word)
        else:
            cursor = QTextCursor(self.document())
            cursor.setPosition(anchorPosition)
            anchorRect = self.cursorRect(cursor)
        if not self.viewport().rect().intersects(anchorRect):
            return  # still off-screen: stay suspended
        self._suspendedOverlay = None
        if word is not None:
            self._activateOverlay(word)
        else:
            self._activateOverlayAt(typedText, anchorPosition)

    # ==========================================================================
    def _onScrollChanged(self) -> None:
        """Re-place or resume the overlay after the document scrolled.

        The overlay follows its word on any scroll: small scrolls shift it
        through Qt's viewport blit (which moves viewport children with the
        painted content), but large jumps repaint without moving children
        — and incremental blits can still leave a drift of a whole line.
        Re-deriving the placement from the document's geometry after every
        scroll settles the overlay exactly on its word. The word's rect
        against the viewport also decides on/off-screen on every scroll,
        in both directions: a word scrolled fully out of the viewport
        suspends the overlay (the hit test is on the word rect, never the
        overlay widget, which reaches further than its word), and a
        suspended anchor scrolling back into the viewport resumes the
        overlay without a manual trigger.
        """
        if self._committing:
            return
        if self._overlayActive():
            self._repositionActiveOverlay()
        else:
            self._restoreSuspendedOverlay()

    # ==========================================================================
    def _onOverlayCommitted(
        self, typedRoman: str, selected: object, key: int, keyText: str, modifiers: int
    ) -> None:
        """Handle the overlay's commit and write to the document.

        Everything is derived from the signal arguments: the committed word
        from the selected row's :class:`Suggestion` — ``""`` when no row is
        selected, :meth:`RomanInputEngine.learnRomanWord` for the
        undefined-word row's blank ``Suggestion`` (``isUndefined()`` true),
        the row's ``arabic`` otherwise — and the separator from the
        committing keystroke: the literal ``"\\n"`` for a plain ``Key_Return``
        (whose ``keyText`` is platform-dependent), ``keyText`` for
        ``Key_Space`` and typed punctuation, and the empty string for
        ``Key_Return`` with ``ControlModifier`` (Ctrl+Enter commits the word
        without a newline) and for an edge commit (``Key_Left`` /
        ``Key_Right``).

        A separator-key commit inserts the committed word plus the separator
        as a single undoable edit: over an existing word (scenario 2) the
        word's span is replaced, at a bare cursor (scenario 1) the text is
        inserted at the anchor position — or, if the cursor had a selection,
        that selection is replaced. The word and the separator both carry the
        :class:`RomanUrdu` region background. An edge commit writes nothing
        and moves the cursor to the adjacent Arabic word in visual order —
        Left at the visually left edge (the start of the overlay text) to the
        next word, Right at the visually right edge (the end) to the previous
        one. When that word exists, the cursor lands at its edge facing the
        active word — Left at its start, Right at its end — and the post-commit
        resync re-activates the overlay over the landed word (a cursor at the
        word's end is over the word). With no adjacent word — the commit
        landed on a boundary word, whose far side is only whitespace — the
        overlay is closed and the resync skipped, so the deactivation sticks
        and the cursor rests at the boundary edge (Left at the word's end,
        Right at its start) until the next trigger (a cursor move, a click,
        or Ctrl+Space). A Ctrl+Enter
        commit skips the resync, so the dismissed overlay is not re-triggered
        and the cursor rests at the inserted word's end.

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
            if isinstance(selected, Suggestion):
                if selected.isUndefined():
                    word = engine.learnRomanWord(typedRoman)
                else:
                    word = selected.arabic
            edge = key in (Qt.Key.Key_Left, Qt.Key.Key_Right)
            if edge:
                separator = ""
            elif key == Qt.Key.Key_Return:
                # Enter's keyText is platform-dependent, so the newline is
                # literal; Ctrl+Enter commits without one and skips the
                # resync: the cursor rests at the committed word's end, which
                # is over the word, so the resync would only re-trigger the
                # overlay the user just dismissed.
                if modifiers & Qt.KeyboardModifier.ControlModifier.value:
                    separator = ""
                    resync = False
                else:
                    separator = "\n"
            else:
                separator = keyText
            if edge:
                # Edge commit: nothing is written to the document. Left at the
                # visually left edge (the start of the overlay text) moves to
                # the next Arabic word; Right at the visually right edge (the
                # end) to the previous one. When that word exists, the cursor
                # lands at its edge facing the active word — Left at its
                # start, Right at its end — and the resync re-activates the
                # overlay over the landed word (a cursor at the word's end is
                # over the word). With no adjacent word — the commit landed on
                # a boundary word, whose far side is only whitespace — the
                # overlay is closed and the resync skipped, so the
                # deactivation sticks and the cursor rests at the boundary
                # edge (Left at the word's end, Right at its start) until the
                # next trigger.
                moveLeft = key == Qt.Key.Key_Left
                if self._activeWord is not None:
                    reference = self._activeWord[1] if moveLeft else self._activeWord[0]
                else:
                    reference = self._anchorPosition or 0
                adjacent = self._adjacentWord(reference, backwards=not moveLeft)
                if adjacent is None:
                    # No adjacent word: the commit landed on a boundary
                    # word, whose far side is only whitespace (the cursor
                    # has walked off the paragraph's word run). The
                    # deactivation must stick, so the resync is skipped —
                    # the landing edge is over the active word and the
                    # resync would only re-trigger the overlay the user is
                    # leaving, pinning the cursor on the boundary word.
                    resync = False
                    if self._activeWord is not None:
                        cursor = self.textCursor()
                        cursor.setPosition(self._activeWord[1 if moveLeft else 0])
                        self.setTextCursor(cursor)
                    self._deactivateOverlay()
                else:
                    cursor = self.textCursor()
                    cursor.setPosition(adjacent[0 if moveLeft else 1])
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
    def _adjacentWord(self, reference: int, backwards: bool) -> tuple[int, int] | None:
        """The nearest Arabic-script word run adjacent to ``reference``.

        When ``backwards`` is true the run is searched at lower index values of ``reference``
        (the previous word); otherwise greater index values (the next word). Non-Arabic
        characters — whitespace, digits, Latin letters — are skipped.
        """
        text = self.document().toPlainText()
        if backwards:
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
        it as Roman Urdu. ``Ctrl+Space`` turns assist mode back on and
        activates the overlay — over the RomanUrdu word under the cursor
        with its romanized text, or, with no such word, an empty overlay
        at the cursor — and never reaches the document. While the
        roman-input feature is enabled, assist mode is on, and the
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
            and self._assistMode
            and not self._overlayActive()
            and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            text = event.text()
            if len(text) == 1 and text.isascii() and text.isalnum():
                if self._regionKindForTyping() is RegionType.RomanUrdu:
                    self._activateOverlayAt(text, self.textCursor().position())
                    return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Space:
                self._assistMode = True
                word = self._wordUnderCursor()
                if word is not None:
                    self._activateOverlay(word)
                else:
                    self._activateOverlayAt("", self.textCursor().position())
                return
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
        is released (:meth:`mouseReleaseEvent`). A view-caused suspension
        is dropped with it: the press is the user's explicit decision to
        walk away from the overlay, and scrolling the suspended anchor
        back must not resurrect it afterwards.

        Args:
            event: The mouse press event.
        """
        if self._overlayActive() or self._suspendedOverlay is not None:
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
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Re-anchor the active overlay when the widget is resized.

        A resize reflows the right-aligned document, moving the word
        (scenario 2) and the seeded cursor anchor (scenario 1) in
        viewport coordinates, without a cursor move or document edit —
        so the overlay, placed in viewport coordinates at activation,
        would otherwise keep its stale location. The base handler runs
        first, since it updates the viewport and the text layout; the
        overlay is then re-placed from its stored anchor, exactly as
        :meth:`_onOverlayTextChanged` does on text edits. Only the
        active overlay is re-placed, and activation is never
        re-evaluated for the ACTIVE overlay: doing so would clobber the
        typed text (scenario 1) or deactivate the overlay when the
        cursor is not inside a word. The list's orientation follows the
        room the reflow leaves below the anchor: a taller resize can
        flip a flipped list back below the line edit.

        The reflow's word-rect hit test applies in both directions as a
        view decision (never a user one): the reflow pushing the word
        fully out of the viewport suspends the overlay, and a resize
        grant that reveals a suspended anchor resumes it.

        Args:
            event: The resize event.
        """
        super().resizeEvent(event)
        if self._committing:
            return
        if self._overlayActive():
            self._repositionActiveOverlay()
        else:
            self._restoreSuspendedOverlay()

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
        """Reset a character range to :data:`~pyraya.regions.DefaultRegionKind`.

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
        fmt.setBackground(QBrush(RegionColors[DefaultRegionKind]))
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
        :data:`~pyraya.regions.DefaultRegionKind` — so the spans partition
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
        :data:`~pyraya.regions.DefaultRegionKind`, keeping the invariant
        that every character belongs to exactly one kind.
        """
        color = self._charFormatAt(position).background().color()
        for kind, regionColor in RegionColors.items():
            if color == regionColor:
                return kind
        return DefaultRegionKind

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
        :data:`~pyraya.regions.DefaultRegionKind`; any other position
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
                return DefaultRegionKind
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
        for family in PyRayaFonts:
            if family in available:
                return family
        return PyRayaFonts[0]

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
        the entire document, without triggering new signals. The merge runs on a
        throwaway document cursor: applying it through the widget's own cursor
        would leave the whole document selected and make the next typed
        character replace the text.
        """
        self.blockSignals(True)
        try:
            cursor = QTextCursor(self.document())

            to = self.document().defaultTextOption()

            blockFormat = QTextBlockFormat()
            blockFormat.setAlignment(to.alignment())

            cursor.mergeBlockFormat(blockFormat)
        finally:
            self.blockSignals(False)


# ******************************************************************************

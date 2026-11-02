# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""PyRaya — a self-contained PySide6 (Qt) text editor widget for Urdu.

The public entry point is :class:`PyRaya`, a drop-in ``QPlainTextEdit`` for
right-to-left (Nastaliq) Urdu text in Qt applications — currently PySide6 only.

PyRaya ships with a configurable, dedicated :class:`PyRayaHighlighter` that
provides rule-based formatting for Urdu and mixed-script text, and supports
text regions: spans tagged with a :class:`~pyraya.regions.RegionType` stored
as a custom integer property on the document's character formats. Resolution
is two steps — a stored tag wins, and untagged characters take the widget's
seed kind (:meth:`PyRaya.seedRegionKind`) — so every character of the
document reports exactly one region kind at any time. The palette is
view-only: it tints the resolved kinds in the text layout and never feeds
back into identity.
"""

from collections.abc import Callable, Generator, Iterable, Sequence
from time import monotonic
from typing import cast

from PySide6.QtCore import (
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QRegularExpression,
    Qt,
    Signal,
)
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
    QTextBlock,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextLayout,
    QTextLine,
    QTextOption,
)
from PySide6.QtWidgets import QDialog, QLayout, QMenu, QPlainTextEdit, QWidget
from romanalfaz.engine import Suggestion, Vocabulary

from .regions import (
    RegionColors,
    RegionKindProperty,
    RegionType,
    SeedRegionKind,
    TextRegion,
    resolveRegionKind,
    substituteChar,
    substituteText,
)
from .roman_input import (
    AddWordDialog,
    ArabicScriptRanges,
    ArabicScriptWordChars,
    OverlayLayoutSpacing,
    RomanInputEngine,
    RomanOverlay,
    _sharedEngine,
)

__all__ = [
    "PyRaya",
    "PyRayaHighlighter",
    "PyRayaFonts",
    "DefaultFontSize",
]

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

#: Maximum interval between two Esc presses that count as a double tap.
EscDoubleTapInterval: float = 0.3


#: Format characters that may sit inside an Arabic-script word: ZWNJ, ZWJ,
#: LRM, RLM, and the Arabic letter mark. They are transparent — they
#: continue a run but never start or end one — so ``ک‌ام`` is one word while
#: ``‏کام`` is the word ``کام``, and a run of only joiners is no word at all.
_WordJoiners: frozenset[str] = frozenset({"\u200c", "\u200d", "\u200e", "\u200f", "\u061c"})

#: The character class covering every Arabic-script range, for the
#: highlighter's default ink rule. Built from :data:`ArabicScriptRanges`, so
#: the formatting rule and the word-matter classification share one domain.
_ArabicScriptPattern: str = (
    "["
    + "".join(f"\\x{{{ord(start):04x}}}-\\x{{{ord(end):04x}}}" for start, end in ArabicScriptRanges)
    + "]+"
)


def _isArabicChar(char: str) -> bool:
    """Whether a character is Arabic-script word matter.

    A letter or combining mark in one of :data:`ArabicScriptRanges` — the
    derived table (:data:`ArabicScriptWordChars`) that every word-run
    consumer shares. Digits, punctuation, symbols, and format characters
    inside the same ranges are boundaries, so ``کام۔`` is the word ``کام``
    followed by the separator ``۔`` and ``دوست۵`` is ``دوست`` followed by
    the digit.
    """
    return char in ArabicScriptWordChars


def _continuesWordRun(char: str) -> bool:
    """Whether a character can sit inside a word run.

    Word matter, or one of the invisible :data:`_WordJoiners` a copied word
    may carry. Joiners never start or end a run: :func:`_wordRunAround`
    trims them from both edges.
    """
    return char in ArabicScriptWordChars or char in _WordJoiners


def _wordRunAround(text: str, local: int) -> tuple[int, int] | None:
    """The maximal block-local Arabic-script run containing or ending at ``local``.

    The one executable owner of the word-run scan (B2): a run is a
    maximal substring whose characters all pass :func:`_continuesWordRun`,
    trimmed of joiners at both edges — a joiner never forms a word, though
    it may sit inside one. The scan also encodes the Arabic-separator
    boundary rule (؟ ، ؛ ۔ ٫ ٬ ؜ terminate a word like the Latin marks do).
    A word run cannot cross a block — the block separator is not Arabic —
    so ``text`` is a block's text and the scan stops at its edges.

    ``local`` may sit at the run's start, inside it, or at its end
    (``start <= local <= end``): the end is a position past the last
    Arabic character, so a cursor parked on the whitespace or the
    separator after a word — or at the run's end itself — still belongs
    to that run: the run's end position is over the word.

    Args:
        text: The block text to scan (never includes a block separator).
        local: The block-local position, ``0 <= local <= len(text)``.

    Returns:
        ``(start, end)`` block-local bounds of the containing or
        ending run, or ``None`` when no run meets the position.
    """
    if local < 0 or local > len(text):
        return None
    start = local
    while start > 0 and _continuesWordRun(text[start - 1]):
        start -= 1
    end = local
    while end < len(text) and _continuesWordRun(text[end]):
        end += 1
    while start < end and text[start] in _WordJoiners:
        start += 1
    while end > start and text[end - 1] in _WordJoiners:
        end -= 1
    if start >= end:
        return None
    return (start, end)


def _charFormatAt(document: QTextDocument, position: int) -> QTextCharFormat:
    """Return the character format stored at a document offset.

    ``QTextCursor.charFormat()`` reports the format of the character
    before the cursor, so the cursor is placed one offset past the target.
    The offset must therefore stay below ``characterCount() - 1`` so the
    cursor never lands past the trailing terminator; region lookups guard
    that boundary. A fresh, document-bound cursor is used because the
    widget cursor can report stale formats while it carries a selection.

    Args:
        document: The document to read.
        position: The document character offset to observe.

    Returns:
        The :class:`~PySide6.QtGui.QTextCharFormat` stored at the offset.
    """
    cursor = QTextCursor(document)
    cursor.setPosition(position + 1)
    return cursor.charFormat()


# ******************************************************************************
class PyRayaHighlighter(QSyntaxHighlighter):
    """Rule-based formatting highlighter for Urdu and mixed-script text.

    Formatting is driven by an ordered list of ``(QRegularExpression,
    QTextCharFormat)`` rules. Rules are applied in order, and later rules
    override earlier ones for overlapping matches, so broad rules should
    precede specific ones.

    The highlighter also paints the resolved region kinds into the text
    layout: each character's kind — stored tag first, else the seed — is
    merged with its kind's tint, while tint-less (Native) stretches get
    their background explicitly removed. The pass derives *which* runs to
    paint from the block's format runs, so it is one document-format read
    per run; the writes are merged over the current per-character layout
    formats so the rule foregrounds survive. The paint touches the layout
    rather than the document, so it is not recorded in the undo stack and
    cannot bury user edits behind it.

    Args:
        document: The document to highlight.
        engineProvider: Optional callable returning the roman-input
            engine (or ``None``) that the spell-check pass queries for
            dictionary membership; ``None`` disables the pass. When
            provided, the pass is gated by the highlighter's own
            :meth:`isSpellCheckEnabled` flag.
        colors: The palette mapping each tintable
            :class:`~pyraya.regions.RegionType` to its view tint. A
            highlighter created by ``PyRaya`` shares the widget's own
            palette here; omitted, a copy of the module-level default
            palette is used.
        seed: The kind untagged characters resolve to. A highlighter
            created by ``PyRaya`` shares the widget's seed; omitted, the
            module-level :data:`~pyraya.regions.SeedRegionKind` is used.
    """

    # ==========================================================================
    def __init__(
        self,
        document: QTextDocument,
        engineProvider: Callable[[], RomanInputEngine | None] | None = None,
        colors: dict[RegionType, QColor] | None = None,
        seed: RegionType | None = None,
    ) -> None:
        super().__init__(document)
        self._engineProvider = engineProvider
        self._spellCheckEnabled = True
        self._regionColors: dict[RegionType, QColor] = (
            {kind: QColor(color) for kind, color in RegionColors.items()}
            if colors is None
            else colors
        )
        self._seed = SeedRegionKind if seed is None else seed
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

        After the rules, every character's resolved kind is painted into
        the text layout (:meth:`_paintResolvedKinds`). When spell
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
        self._paintResolvedKinds(block)
        self._underlineUnknownWords(block)

    # ==========================================================================
    def _uniformRuns(self, start: int, end: int) -> Generator[tuple[int, int, QTextCharFormat]]:
        """Yield maximal runs of equal current layout format within a range.

        Consecutive characters whose current layout formats compare equal
        by :class:`QTextCharFormat`'s property-orientated equality would
        otherwise be rewritten identically, one write per character: the
        caller can paint one merged write per yielded run instead. The
        yielded templates are per-run copies — mutating one does not
        affect the buffer.

        Args:
            start: The first block-local position of the range.
            end: The position one past the range.

        Yields:
            ``(start, length, format)`` triples covering the range in
            order.
        """
        if start >= end:
            return
        runStart = start
        runFormat = self.format(start)
        for position in range(start + 1, end):
            charFormat = self.format(position)
            if charFormat != runFormat:
                yield runStart, position - runStart, runFormat
                runStart = position
                runFormat = charFormat
        yield runStart, end - runStart, runFormat

    # ==========================================================================
    def _paintResolvedKinds(self, block: str) -> None:
        """Merge every character's resolved kind's tint into the layout.

        Each format run's kind is resolved in two steps (stored tag, else
        the seed — :func:`~pyraya.regions.resolveRegionKind`) and its
        kind's tint is merged into the text layout; the document's
        character formats are not modified. Kinds the palette does not
        colour (Native is colourless) are skipped — but explicitly: their
        stretch's background is **removed**, because leaving it alone
        would let the tint of a previous paint survive the re-tagging
        (the layout format of a long-lived document is the last paint's
        result, not a clean request). Only the background property is
        decided here: the merged writes read the current per-character
        layout format back (:meth:`format`) instead of painting as a
        background-only write, because ``QSyntaxHighlighter.setFormat``
        replaces the whole per-character format — a background-only
        write would wipe the rules' foregrounds: text would fall back to
        the default ink instead of the rule colors, and with visible
        whitespace the space's designed light-gray dot would render as a
        heavy black mark. The merged writes collapse to per uniform run
        (:meth:`_uniformRuns`): characters whose current layout formats
        compare equal are rewritten once.

        Args:
            block: The text of the block being highlighted.
        """
        current = self.currentBlock()
        base = current.position()
        limit = len(block)
        for it in cast("Iterable[QTextBlock.iterator]", current):
            fragment = it.fragment()
            start = fragment.position() - base
            end = min(start + fragment.length(), limit)
            tint = self._regionColors.get(resolveRegionKind(fragment.charFormat(), self._seed))
            for runStart, runLength, runFormat in self._uniformRuns(max(start, 0), end):
                if tint is None:
                    runFormat.clearProperty(QTextCharFormat.Property.BackgroundBrush)
                else:
                    runFormat.setBackground(QBrush(tint))
                self.setFormat(runStart, runLength, runFormat)

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
        (by the two-step resolution) are collected as candidate words
        first; with no candidates the pass returns without touching the
        engine provider, so the
        engine (and its dictionary cold load) is created only the first
        time a block containing a candidate word is re-highlighted. The
        ends' kinds are resolved from the block's format runs — one
        document-format read per run, replacing the per-candidate two
        ``QTextCursor`` queries the scan used to pay. Each candidate is
        then consulted against the engine, and a word the dictionary does
        not know is underlined with :data:`SpellCheckUnderlineColor` in
        the text layout, merged over the character's other layout
        formats. The document's character formats are never modified. The
        pass is also a no-op while spell check is disabled, or when the
        engine provider returns ``None`` or an unavailable engine (a
        missing dictionary must never underline every word).

        Args:
            block: The text of the block being highlighted.
        """
        if not self._spellCheckEnabled:
            return
        limit = len(block)
        candidates: list[tuple[int, int]] = []
        position = 0
        kindRuns: list[tuple[int, int, RegionType]] = []
        while position < limit:
            run = _wordRunAround(block, position)
            if run is None or run[1] <= position:
                # No run starts at this position (a non-Arabic character,
                # or a run that only ended here): the next candidate
                # begins with the following character.
                position += 1
                continue
            start, end = run
            position = end
            if not kindRuns:
                kindRuns = self._blockRegionRuns(limit)
            if (
                self._kindInRuns(kindRuns, start) is not RegionType.RomanUrdu
                or self._kindInRuns(kindRuns, end - 1) is not RegionType.RomanUrdu
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
            for runStart, runLength, runFormat in self._uniformRuns(start, end):
                runFormat.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
                runFormat.setUnderlineColor(SpellCheckUnderlineColor)
                self.setFormat(runStart, runLength, runFormat)

    # ==========================================================================
    def _blockRegionRuns(self, limit: int) -> list[tuple[int, int, RegionType]]:
        """The current block's (start, end, kind) runs, block-local.

        One document-format read per format run through
        :func:`~pyraya.regions.resolveRegionKind` (stored tag first, then
        the seed); runs cover the block's text positions exactly
        (fragments partition the real text), so a run-local kind lookup
        reproduces the per-character reads.
        """
        base = self.currentBlock().position()
        runs: list[tuple[int, int, RegionType]] = []
        for it in cast("Iterable[QTextBlock.iterator]", self.currentBlock()):
            fragment = it.fragment()
            start = fragment.position() - base
            end = min(start + fragment.length(), limit)
            if start < end:
                runs.append((start, end, resolveRegionKind(fragment.charFormat(), self._seed)))
        return runs

    # ==========================================================================
    def _kindInRuns(self, runs: list[tuple[int, int, RegionType]], position: int) -> RegionType:
        """The region kind covering a block-local position in the run list."""
        for start, end, kind in runs:
            if start <= position < end:
                return kind
        return self._seed

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
                (QRegularExpression(_ArabicScriptPattern), ink),
                (QRegularExpression("[\u064b-\u065f]"), rose),
                (QRegularExpression("[\u0660-\u0669]+"), amber),
                (QRegularExpression("[\u06f0-\u06f9]+"), amber),
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
    font stack (default ``Baloo Bhaijaan 2``, the first installed entry of
    :data:`PyRayaFonts` — the Naskh and Nastaliq Noto fonts follow it),
    visible whitespace, a dedicated rule-based :class:`PyRayaHighlighter`
    for formatting, and text regions: spans tagged with a
    :class:`~pyraya.regions.RegionType` stored as a custom character-format
    property. Every character resolves to exactly one kind — a stored tag
    wins, and untagged text takes this widget's
    :meth:`seedRegionKind` seed — and clearing regions removes the stored
    tag intent.
    """

    #: Emitted once when a region-touching operation invoked through the
    #: widget has completed: :meth:`setRegionType`, :meth:`clearRegions`,
    #: a non-empty :meth:`setPlainText`, and every roman-input commit that
    #: writes text (edge commits write nothing and do not emit; a
    #: recolouring :meth:`setRegionColor` is view-only and emits nothing).
    #: Document edits made outside these operations are never inspected
    #: for region changes and do not emit — this keeps the signal
    #: cost-free during typing.
    regionsChanged = Signal()

    #: Emitted when a roman-input commit writes a word to the document:
    #: ``(word, roman)`` — the word committed (the selected Arabic word, or
    #: the typed roman for an undefined-word commit) and the typed roman.
    romanWordCommitted = Signal(str, str)

    wordAdded = Signal(str)

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
        # dictionary and engine are borrowed from the application-wide
        # shared holder (the engine is created lazily on first use). All of
        # these fields must exist before the highlighter is constructed:
        # its constructor re-highlights (even the empty) document, and the
        # spell-check pass queries the shared engine through the provider
        # passed below.
        self._romanInputEnabled = True
        self._assistMode = True
        # The monotonic-clock timestamp of the last plain-Esc press, or
        # ``None``: a second plain Esc within :data:`EscDoubleTapInterval`
        # turns assist mode off, irrespective of whether the overlay is
        # shown.
        self._lastEscAt: float | None = None
        self._localDictionary = _sharedEngine.vocabulary
        # The host learn dialog handler: receives the trigger word and
        # returns the chosen Arabic word on accept, or ``None`` on cancel.
        # ``None`` restores the built-in :class:`AddWordDialog`.
        self._addWordHandler: Callable[[str], str | None] | None = None
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
        # Guarding :meth:`_syncOverlay` during :meth:`setPlainText`: the
        # replacement signals with the cursor already over the new text, and a
        # word under a RomanUrdu seed would seed the overlay over text that a
        # subsequent region write may tag differently — the replacement itself
        # is not a typing or cursor decision.
        self._replacingText = False
        self._mouseActive = False
        # The ``(cursor position, document revision)`` pair the last sync
        # ran for: both ``cursorPositionChanged`` and ``contentsChanged``
        # funnel into :meth:`_syncOverlay` per keystroke, and the second
        # signal with an unchanged pair coalesces to an early exit.
        # :meth:`_deactivateOverlay` invalidates the pair, so a
        # state-changing user decision forces the next signal to
        # re-examine. ``bypassMouse`` always proceeds.
        self._syncedOverlayInputs: tuple[int, int] | None = None
        self._minOverlayWidth: int = 0
        self._overlay: RomanOverlay | None = None
        # Per-widget region palette: the widget copies the module-level
        # default palette at construction and owns its colors (the palette
        # is view-only; the highlighter shares the same mapping so
        # recolours repaint). The seed — copied from the module initial
        # value — resolves untagged text; it is fixed at construction and
        # readable, never settable.
        self._regionColors: dict[RegionType, QColor] = {
            kind: QColor(color) for kind, color in RegionColors.items()
        }
        self._seedRegionKind: RegionType = SeedRegionKind
        # Set by every format-only region write (and by a batch tag
        # removal): format-only writes and their undo do not trigger a
        # re-highlight, so the undo()/redo() overrides consume this flag
        # to repaint the layout tint once.
        self._pendingTagRepaint: bool = False
        self._highlighter = PyRayaHighlighter(
            self.document(),
            engineProvider=self._spellEngine,
            colors=self._regionColors,
            seed=self._seedRegionKind,
        )
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

        The replacement text carries no region tags: all of it resolves to
        the widget's :meth:`seedRegionKind` seed (no stored property, so
        the resolved kinds are re-derived from the seed alone), and
        ``regionsChanged`` is emitted for a non-empty replacement.

        Args:
            text: The new document text.
        """
        # The replacement's signals fire with the cursor already over the new
        # text; the funnel stays inert for the whole write so a word under a
        # RomanUrdu seed is never seeded as an overlay over provisional text
        # (the same contract as the roman-input ``_committing`` guard).
        self._replacingText = True
        super().setPlainText(text)
        self._replacingText = False
        if self.document().characterCount() > 1:
            self.regionsChanged.emit()

    # ==========================================================================
    def undo(self) -> None:
        """Undo the last command, repainting a tag write's layout tint.

        A region write raises :attr:`_pendingTagRepaint` on its way into
        the history; when this undo made its layout stale, one
        re-highlight repairs it boundedly (at most one whole-document
        re-highlight per undo chain after a tag write). Measured: Qt
        also auto-re-highlights an undo on its own ``contentsChange``
        reactions, so this override is belt-and-braces — and it covers
        the *programmatic* path only (``widget.undo()``); the keyboard
        Ctrl+Z path goes through the widget control and Qt's own
        re-highlight, not through this override.
        """
        super().undo()
        if self._pendingTagRepaint:
            self._pendingTagRepaint = False
            self._highlighter.rehighlight()

    # ==========================================================================
    def redo(self) -> None:
        """Redo the last undone command, repainting a tag write's tint.

        Same bounded repair as :meth:`undo`: redoing a tag write
        re-highlights here instead of waiting for an unrelated event —
        programmatic redo only (the keyboard path is Qt's own
        re-highlight).
        """
        super().redo()
        if self._pendingTagRepaint:
            self._pendingTagRepaint = False
            self._highlighter.rehighlight()

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

        Every character reports exactly one **resolved** kind — a stored
        tag wins, and untagged text takes the widget's
        :meth:`seedRegionKind` seed — so the spans cover the real text
        (``[0, characterCount() - 1)``), adjacent same-kind stretches
        merged into one span.

        Returns:
            A list of :class:`~pyraya.regions.TextRegion` spans ordered by
            start offset.
        """
        return self._regionSpans()

    # ==========================================================================
    def seedRegionKind(self) -> RegionType:
        """The kind this widget's untagged text resolves to.

        Copied from the module-level
        :data:`~pyraya.regions.SeedRegionKind` initial value at
        construction and read-only afterwards — there is no setter and no
        constructor parameter.

        Returns:
            The fixed seed :class:`~pyraya.regions.RegionType`.
        """
        return self._seedRegionKind

    # ==========================================================================
    def setRegionType(
        self, kind: RegionType, start: int | None = None, end: int | None = None
    ) -> None:
        """Tag a character range (or the current selection) with a region kind.

        The kind is stored as the
        :data:`~pyraya.regions.RegionKindProperty` custom property on the
        character formats — a stored tag always wins over the seed, even
        when it equals it, because tags record intent. Existing regions
        overlapping the range are split and the range is retagged;
        adjacent same-kind spans merge in the resolved view. The write is
        one undo step, and the touched blocks are re-highlighted so the
        tint follows immediately.

        Args:
            kind: The region kind to apply.
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
        self._applyRegionTags(start, end, kind)
        self.regionsChanged.emit()

    # ==========================================================================
    def regionTypeAt(self, position: int) -> RegionType | None:
        """Return the resolved region kind at a character offset.

        Args:
            position: The character offset to query.

        Returns:
            The :class:`~pyraya.regions.RegionType` covering the offset as
            resolved from the stored tag or the seed. Every text offset
            resolves to exactly one kind, so None is returned only for
            offsets at or past the document's trailing terminator.
        """
        if not 0 <= position < self.document().characterCount() - 1:
            return None
        return self._regionKindAt(position)

    # ==========================================================================
    def clearRegions(self) -> None:
        """Remove every stored region tag from the document.

        The removal is one batch apply inside a single edit block — one
        undo step that replays every stored span, so one ``undo()``
        restores all of them. Where a tag equals the seed the removal is
        behaviourally invisible (the text still resolves to the seed);
        with no stored tags the call does nothing and ``regionsChanged``
        is not emitted.
        """
        matches = self._storedTagRuns()
        if not matches:
            return
        self._batchRemoveTags(matches)
        self.regionsChanged.emit()

    # ==========================================================================
    def setRegionColor(self, kind: RegionType, color: QColor) -> bool:
        """Change the widget's view tint for a region kind.

        The palette is per widget and view-only: the change recolours this
        widget's tint immediately (the highlighter repaints the layout),
        leaving the module-level
        :data:`~pyraya.regions.RegionColors` default and other widgets'
        palettes untouched. No document state is touched and
        ``regionsChanged`` is **not** emitted — the palette never feeds
        back into the region identity. Kinds the palette does not colour
        (Native is colourless) are rejected.

        Args:
            kind: The region kind to recolour.
            color: The new tint color; its alpha controls subtlety.

        Returns:
            True if the tint was applied; False when the kind carries no
            tint to recolour.
        """
        if kind not in self._regionColors:
            return False
        color = QColor(color)
        if self._regionColors[kind] == color:
            return True
        previous = self._regionColors[kind]
        self._regionColors[kind] = color
        # The tint repaint cannot go through the highlighter: even a no-op
        # ``rehighlightBlock`` bumps the document revision (probed
        # unconditional), and the palette is view-only — the document must
        # not move. The repaint is a direct layout re-write instead: a
        # recolour changes nothing but the background brush values.
        self._repaintLayoutTint(previous, color)
        self.viewport().update()
        return True

    # ==========================================================================
    def _repaintLayoutTint(self, previous: QColor, color: QColor) -> None:
        """Recolour the kind tint in the text layouts, revision-free.

        The layout is the only place a recolour shows, and it is
        revision-neutral when written directly
        (:meth:`QTextLayout.setFormats` with identical formats probes no
        revision bump, while ``QSyntaxHighlighter.rehighlightBlock`` bumps
        one unconditionally). Every block's current format ranges are
        read once, and the whole range list written back with the
        background brushes equal to ``previous`` replaced by ``color`` —
        the wash merged the kinds' brush values verbatim, so a
        value-swap reproduces exactly what a re-highlight would paint.
        A layout write is a display write: no undo command, no
        ``contentsChanged``, no ``regionsChanged``.
        """
        document = self.document()
        block = document.firstBlock()
        while block.isValid():
            layout = block.layout()
            rebuilt: list[QTextLayout.FormatRange] = []
            changed = False
            for r in layout.formats():
                rformat = cast(QTextCharFormat, r.format)
                brush = (
                    rformat.background()
                    if rformat.hasProperty(QTextCharFormat.Property.BackgroundBrush)
                    else None
                )
                if brush is not None and brush.color() == previous:
                    replacement = QTextCharFormat(rformat)
                    replacement.setBackground(QBrush(color))
                    rebuilt.append(self._copyFormatRange(r, replacement))
                    changed = True
                else:
                    rebuilt.append(self._copyFormatRange(r, rformat))
            if changed:
                layout.setFormats(rebuilt)
            block = block.next()

    @staticmethod
    def _copyFormatRange(
        r: QTextLayout.FormatRange, fmt: QTextCharFormat
    ) -> QTextLayout.FormatRange:  # noqa: E501
        """Copy a format range with one format replaced.

        The range wrapper borrows its C++ object, so every attribute is
        read back to plain values while the wrapper lives and written to
        a fresh range. The bundled stubs declare the attributes as
        ``...``, so the assignments carry a local suppression.
        """
        copy = QTextLayout.FormatRange()
        copy.start = cast(int, r.start)  # pyrefly: ignore [bad-assignment]
        copy.length = cast(int, r.length)  # pyrefly: ignore [bad-assignment]
        copy.format = fmt  # pyrefly: ignore [bad-assignment]
        return copy

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
        """The application-wide shared in-memory :class:`romanalfaz.Vocabulary`.

        Owned by the :class:`_SharedEngine` holder and borrowed by every
        widget. It is mutated by :meth:`RomanInputEngine.learnRomanWord`
        (the learn-word path); ``Vocabulary.save``/``Vocabulary.load`` exist
        for host persistence, and ``isModified()`` is the host's mutation
        flag.

        Returns:
            The same shared :class:`Vocabulary` instance, every time.
        """
        return self._localDictionary

    # ==========================================================================
    def regionColors(self) -> dict[RegionType, QColor]:
        """Return the widget's region palette as a copy.

        The palette maps every colourable
        :class:`~pyraya.regions.RegionType` to the view tint the layout
        paints its stretches with on this widget. It starts as a copy of
        the module-level :data:`~pyraya.regions.RegionColors` default;
        :meth:`setRegionColor` mutates the widget's own palette — never
        the module default, never another widget's palette, and never any
        document state (the palette is view-only).

        Returns:
            A deep copy of the per-widget ``kind -> color`` mapping: the
            returned colors are independent ``QColor`` values, so mutating
            a returned color cannot reach the widget's palette, the
            module default, or any other widget.
        """
        return {kind: QColor(color) for kind, color in self._regionColors.items()}

    # ==========================================================================
    def romanEngine(self) -> RomanInputEngine | None:
        """The shared roman-input engine, or ``None`` while disabled.

        Returns the application-wide shared engine, created lazily on first
        use (with its ~0.3 s dictionary cold load); every widget borrows
        the same instance.

        Returns:
            The shared engine when the feature is enabled; ``None``
            otherwise.
        """
        if not self._romanInputEnabled:
            return None
        return self._ensureEngine()

    # ==========================================================================
    def setAddWordHandler(self, handler: Callable[[str], str | None] | None) -> None:
        """Install a host learn dialog in place of the built-in AddWordDialog.

        The handler receives the trigger word (the Arabic word for the
        right-click trigger, the typed roman for the + [..] row) and returns
        the chosen Arabic word on accept, or ``None`` on cancel. ``None``
        restores the built-in dialog.

        Args:
            handler: The host callable, or ``None`` for the built-in dialog.
        """
        self._addWordHandler = handler

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
        """The application-wide shared roman-input engine, created lazily on
        first use.

        Both the roman-input overlay and the spell-check pass consult the
        same instance, and every widget borrows it, so the ~0.3 s dictionary
        cold load happens at most once per process.

        Returns:
            The shared engine, creating it on first use.
        """
        return _sharedEngine.engine()

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
    def _learnDialog(self, trigger: str, prefill: str = "") -> str | None:
        """Open the learn UI; the chosen Arabic word on accept, ``None`` on cancel.

        The handler path returns the handler's result. The built-in path
        re-opens the dialog on ``AssertionError`` (the mappability
        pre-validation is belt-and-braces behind the dialog's live feedback,
        so this stays open with the user's text until they accept or cancel),
        and treats an empty accepted field as a cancel.
        """
        if self._addWordHandler is not None:
            word = self._addWordHandler(trigger)
            if word:
                self._learnWord(word)
            return word or None
        arabic = prefill
        while True:
            dialog = AddWordDialog(arabic, hint=trigger)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            word = dialog.word()
            if not word:
                return None
            try:
                self._learnWord(word)
                return word
            except AssertionError:
                arabic = word  # stay open: re-open with the user's text

    # ==========================================================================
    def _learnWord(self, word: str) -> None:
        """Learn ``word`` into the shared Vocabulary and clear its underline.

        ``RomanInputEngine.learnRomanWord`` (one mutation, one recompile),
        then a whole-document re-highlight so the spell-check underline for
        the word clears immediately, then ``wordAdded``.
        """
        self._ensureEngine().learnRomanWord(word)
        self._highlighter.rehighlight()
        self.wordAdded.emit(word)

    # ==========================================================================
    def _learnCandidate(self) -> str | None:
        """The "Add to dictionary" candidate: the word under the cursor.

        ``None`` when the cursor has a selection, when there is no word run,
        or when the engine already knows the word. The word is the maximal
        Arabic run :meth:`_wordUnderCursor` returns — entirely
        RomanUrdu-resolved, so the same candidate logic the spell-check
        pass computes.
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            return None
        word = self._wordUnderCursor()
        if word is None:
            return None
        start, end = word
        block = self.document().findBlock(start)
        text = block.text()[start - block.position() : end - block.position()]
        if self._ensureEngine().hasWord(text):
            return None
        return text

    # ==========================================================================
    def _addToDictionary(self, word: str) -> None:
        """The "Add to dictionary" trigger: the dialog learns, and a cancel
        leaves the Vocabulary untouched.

        ``_learnDialog`` learns the accepted word internally on both paths
        (handler and built-in dialog), so nothing further follows its
        result; ``None`` (cancel) simply means the word was not learned.
        """
        self._learnDialog(word, prefill=word)

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

        A keystroke that edits the document fires both
        ``contentsChanged`` and the widget-level
        ``cursorPositionChanged``; the second signal with an unchanged
        ``(cursor position, document revision)`` pair coalesces to an
        early exit (:attr:`_syncedOverlayInputs`), while a commit's
        ``bypassMouse`` resync always proceeds and any
        :meth:`_deactivateOverlay` invalidates the pair so the next
        signal re-examines the state.
        """
        if (
            not self._romanInputEnabled
            or not self._assistMode
            or self._committing
            or self._replacingText
            or (self._mouseActive and not bypassMouse)
        ):
            return
        inputs = (self.textCursor().position(), self.document().revision())
        if not bypassMouse and inputs == self._syncedOverlayInputs:
            return
        self._syncedOverlayInputs = inputs
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
        The run must entirely resolve to RomanUrdu — stored tag or the
        seed — otherwise no word is returned.

        A word run cannot cross a block (the block separator is not
        Arabic), so the scan reads the cursor's own block text instead of
        copying the whole document (A3).
        """
        document = self.document()
        limit = document.characterCount() - 1
        position = min(self.textCursor().position(), limit)
        block = document.findBlock(position)
        # The document-level ``contentsChanged`` fires while a document
        # replacement (``setPlainText``) is mid-flight, when the cursor
        # position can read -1 and no valid block exists yet; both the
        # negative position and the empty text would otherwise slip into
        # Python's negative indexing and crash the scan.
        if position < 0 or not block.isValid():
            return None
        text = block.text()
        base = block.position()
        local = position - base
        if local < 0 or local > len(text):
            return None
        word = _wordRunAround(text, local)
        if word is None:
            return None
        start, end = word
        if (
            self._regionKindAt(base + start) is not RegionType.RomanUrdu
            or self._regionKindAt(base + end - 1) is not RegionType.RomanUrdu
        ):
            return None
        return (base + start, base + end)

    # ==========================================================================
    def _lineGeometry(
        self, block: QTextBlock, localPosition: int
    ) -> tuple[QTextLine | None, QRectF, QPointF]:
        """The block's line at a block-local position, with its content translate.

        The one executable owner of the block-local line resolution (B3):
        ``lineForTextPosition`` resolves the position's line in the
        block's own layout — the position is block-local, and an absolute
        position overflows the block's own layout past block 0 into an
        invalid line whose geometry calls segfault — and an invalid line
        is reported as ``None`` (PySide6 wraps invalid lines as
        non-``None`` objects). ``geometry`` and ``offset`` carry the
        content-coordinate translate (``blockBoundingGeometry`` +
        ``contentOffset``) that callers add to the line's layout-local
        geometry; the callers keep their own invalid-line fallback
        policy.

        Args:
            block: The block whose layout resolves the line.
            localPosition: The block-local position, at most ``len(block.text())``.

        Returns:
            ``(line, geometry, offset)`` — the resolved valid line, or
            ``None`` when Qt cannot resolve it, with the translate
            populated either way.
        """
        geometry = self.blockBoundingGeometry(block)
        offset = self.contentOffset()
        line = block.layout().lineForTextPosition(localPosition)
        if line is None or not line.isValid():
            return None, geometry, offset
        return line, geometry, offset

    # ==========================================================================
    def _wordRect(self, start: int, end: int) -> QRect:
        """The word's rectangle in viewport coordinates.

        Uses the text layout's line geometry — ``cursorToX`` at the word's
        start and end (translated by ``contentOffset()``) — with a
        ``QFontMetrics`` advance fallback when the layout cannot resolve the
        line.
        """
        document = self.document()
        cursor = QTextCursor(document)
        cursor.setPosition(start)
        block = cursor.block()
        local = start - block.position()
        line, geometry, offset = self._lineGeometry(block, local)
        if line is None:
            rect = block.layout().boundingRect()
            metrics = QFontMetrics(self.font())
            # A word cannot span blocks, so the advance reads the word's
            # own block text (A3) instead of copying the whole document.
            width = metrics.horizontalAdvance(block.text()[local : end - block.position()])
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
        # flipped list is clamped to the gap over the anchor
        # (``top - OverlayLayoutSpacing``).
        listHint = overlay.suggestionList().sizeHint().height()
        belowRoom = viewport.height() - top - hint.height() + listHint
        aboveRoom = top - OverlayLayoutSpacing
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
            height = overlay.lineEdit().sizeHint().height() + OverlayLayoutSpacing + listSlot
            y = top - OverlayLayoutSpacing - listSlot
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
        types the new word. The line resolution is the shared
        :meth:`_lineGeometry`; this anchor's own fallback policy degrades
        to the block layout's bounding rect edge.
        """
        document = self.document()
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        block = cursor.block()
        local = position - block.position()
        line, geometry, offset = self._lineGeometry(block, local)
        if line is None:
            rect = block.layout().boundingRect()
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
        wordBlock = document.findBlock(word[0])
        base = wordBlock.position()
        # A word cannot span blocks: the romanization reads the word's own
        # block text (A3) instead of copying the whole document.
        roman = engine.romanizeArabic(wordBlock.text()[word[0] - base : word[1] - base])
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

        A view-caused suspension (:attr:`_suspendedOverlay`) is dropped with
        the rest of the state: the callers are user decisions (a mouse
        press, Esc, a programmatic feature or assist switch, an edge commit
        over a boundary word), explicit re-evaluations, or the word-rect
        view suspension in :meth:`_repositionActiveOverlay` — which
        immediately re-records the suspension, so the view's resumable
        state survives; every other caller drops it for good, because the
        user's active/inactive state outranks the view's suspension.
        """
        if self._overlay is not None:
            self._overlay.hide()
        self._activeWord = None
        self._anchorPosition = None
        self._selectionRange = None
        self._minOverlayWidth = 0
        self._suspendedOverlay = None
        # The funnel deactivation is a state change the last sync did not
        # run for: invalidate the unchanged-inputs pair so the next
        # signal re-examines instead of coalescing to an early exit.
        self._syncedOverlayInputs = None
        self.setFocus()

    # ==========================================================================
    def _overlayActive(self) -> bool:
        """Whether the overlay is currently shown over the document."""
        return self._overlay is not None and self._overlay.isVisible()

    # ==========================================================================
    def _onOverlayCanceled(self, modifiers: int) -> None:
        """Handle the overlay's Esc: the user wants to be left alone.

        The overlay is always dismissed. A plain Esc (no modifiers) is the
        double-tap candidate: a second plain Esc within
        :data:`EscDoubleTapInterval` turns assist mode off, irrespective of
        whether the overlay was shown — otherwise the single Esc leaves
        assist on, so typing and cursor movement re-trigger the overlay by
        the normal assist rules. Ctrl+Esc (the exact Ctrl mask, no
        Shift/Alt/Meta) turns assist mode off directly, balancing Ctrl+Space
        re-entry. Either way the user is left alone until Ctrl+Space in the
        document or :meth:`setAssistEnabled` turns the mode back on; commits
        and cursor-driven deactivation leave assist on.
        """
        if modifiers == 0:
            # A plain Esc is the double-tap candidate: a second plain Esc
            # within the interval turns assist mode off.
            now = monotonic()
            if self._lastEscAt is not None and now - self._lastEscAt <= EscDoubleTapInterval:
                self._assistMode = False
                self._lastEscAt = None
            else:
                self._lastEscAt = now
        elif modifiers == Qt.KeyboardModifier.ControlModifier.value:
            # Ctrl+Esc (the exact Ctrl mask) turns assist mode off directly.
            self._assistMode = False
        self._deactivateOverlay()

    # ==========================================================================
    def _onOverlayTextChanged(self, text: str) -> None:
        """Re-place the overlay so its width tracks the line edit's text.

        Typing in the overlay edits only the line edit (the document is
        untouched), so the overlay is re-placed from the activation anchor
        with the width floored at the activation minimum: over an existing
        word (scenario 2) the word rect, at a seeded cursor (scenario 1) the
        stored four-roman-character baseline. The suggestion rows were
        already refreshed by the overlay's own ``textChanged`` handler,
        which runs before this hook (connected in the overlay's
        constructor): the placement's width derives from the suggestion
        list's hint, so a placement on the previous keystroke's rows would
        size the overlay for the previous text (F-6: a cursor-only key fires
        no ``textChanged``, so it rebuilds neither). The signal also fires
        from the activation ``setText`` calls, which precede the initial
        placement; the visibility and commit guards skip those.
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
        anchorRect = self._anchorRect(word, anchorPosition)
        if anchorRect is None:
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
    def _onViewChanged(self) -> None:
        """One funnel for the view-event dispatch (B7): re-place or resume.

        A scroll or resize must decide what the view event means for the
        overlay: an active overlay is re-placed over its anchor
        (:meth:`_repositionActiveOverlay` — the word-rect hit test decides
        on/off-screen on the way), and with no active overlay a suspended
        one's remembered anchor is re-tested for resumption
        (:meth:`_restoreSuspendedOverlay`). The dispatch is owned once and
        shared by :meth:`_onScrollChanged` and :meth:`resizeEvent`, so the
        two view events cannot drift.
        """
        if self._committing:
            return
        if self._overlayActive():
            self._repositionActiveOverlay()
        else:
            self._restoreSuspendedOverlay()

    # ==========================================================================
    def _anchorRect(self, word: tuple[int, int] | None, anchorPosition: int | None) -> QRect | None:
        """The overlay's anchor rect in viewport coordinates.

        The one owner of the anchor-rect resolution shared by the
        re-place (:meth:`_repositionActiveOverlay`) and resume
        (:meth:`_restoreSuspendedOverlay`) paths: the active word's rect
        (scenario 2, never the overlay widget's own — a flipped
        suggestion list hangs up into the viewport, so a box-based test
        would keep the popup alive after its word has left), or the
        seeded anchor position's cursor rect (`QPlainTextEdit.cursorRect`,
        scenario 1).

        Args:
            word: The active word's document bounds, or ``None``.
            anchorPosition: The seeded anchor's document position,
                or ``None``.

        Returns:
            The anchor's viewport rect, or ``None`` when the activation
            carries neither anchor.
        """
        if word is not None:
            return self._wordRect(*word)
        if anchorPosition is not None:
            cursor = QTextCursor(self.document())
            cursor.setPosition(anchorPosition)
            return self.cursorRect(cursor)
        return None

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
        anchorRect = self._anchorRect(word, anchorPosition)
        if anchorRect is None:
            return  # unreachable: a suspension always carries one anchor
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
        overlay without a manual trigger. The dispatch itself is
        :meth:`_onViewChanged` (B7): the funnel shared with
        :meth:`resizeEvent`, so the two view events make the same
        decision.
        """
        self._onViewChanged()

    # ==========================================================================
    def _onOverlayCommitted(
        self, typedRoman: str, selected: object, key: int, keyText: str, modifiers: int
    ) -> None:
        """Handle the overlay's commit and write to the document.

        Everything is derived from the signal arguments (B6): the committed
        word from the dialog decision for the undefined-word (Learn) row —
        ``_learnDialog`` decides the committed word for every writing
        commit (accept: the chosen Arabic word, learned inside it;
        cancel: the session no-op, the typed roman as-is), and edge
        commits (Left/Right) stay dialog-free —, else from the selected row
        (:meth:`_committedWord`); the separator and resync decision from
        the committing keystroke (:meth:`_commitSeparator`), and then one of
        the two commit decisions — the edge commit (:meth:`_edgeCommit`,
        writes nothing and moves in visual order) or the write
        (:meth:`_writeCommit`). One
        post-commit resync runs unless the decision suppressed it.

        ``romanWordCommitted`` is emitted for a non-empty committed word,
        and ``regionsChanged`` once for every writing commit (per the Q-2
        contract: :attr:`regionsChanged` means "a region-touching operation
        invoked through the widget has completed"). An edge commit writes
        nothing and emits neither.

        A Ctrl+Up / Ctrl+Down commit (``Key_Up`` / ``Key_Down``) additionally
        moves the document cursor one line up or down, in the ``finally``
        block after ``_committing`` clears: a cursor move during the commit
        is swallowed by the :meth:`_syncOverlay` funnel's early exit, and
        the resync is suppressed, so the ``setTextCursor`` there is the
        funnel's only chance to observe the move — the document must behave
        exactly as if Up/Down had been pressed in it (a roman-urdu word
        under the landing cursor re-activates the overlay by the normal
        assist rules; a bare position stays quiet).
        """
        engine = self.romanEngine()
        overlay = self._overlay
        if engine is None or not engine.available or overlay is None:
            self._deactivateOverlay()
            return
        self._committing = True
        resync = True
        try:
            if (
                isinstance(selected, Suggestion)
                and selected.isUndefined()
                and key
                not in (
                    Qt.Key.Key_Left,
                    Qt.Key.Key_Right,
                )
            ):
                # The undefined-word (Learn) row: the dialog decides the
                # committed word (accept: the chosen Arabic word, learned
                # inside ``_learnDialog``; cancel: the session no-op, the
                # typed roman as-is). Edge commits (Left/Right) write
                # nothing and move in visual order, so they stay
                # dialog-free.
                arabic = self._learnDialog(typedRoman)
                if arabic is not None:
                    word = arabic
                else:
                    word = typedRoman
            else:
                word = self._committedWord(typedRoman, selected)
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                resync = self._edgeCommit(key == Qt.Key.Key_Left)
            else:
                separator, resync = self._commitSeparator(key, keyText, modifiers)
                self._writeCommit(word, separator, typedRoman)
        finally:
            self._committing = False
            if resync:
                # Explicit resync: bypasses the mouse flag, so the
                # reconciliation still runs even if a button happens to be
                # held down (see ``_syncOverlay``).
                self._syncOverlay(bypassMouse=True)
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                # The Ctrl+Up / Ctrl+Down line move, after ``_committing``
                # clears and the resync runs: ``setTextCursor`` is the
                # funnel's only chance to observe the move, and the
                # document must behave exactly as if Up/Down had been
                # pressed in it.
                cursor = self.textCursor()
                cursor.movePosition(
                    QTextCursor.MoveOperation.Up
                    if key == Qt.Key.Key_Up
                    else QTextCursor.MoveOperation.Down
                )
                self.setTextCursor(cursor)

    # ==========================================================================
    def _committedWord(self, typedRoman: str, selected: object) -> str:
        """The committed word, derived from the selected row's suggestion.

        ``""`` when no row is selected, the typed roman for the
        undefined-word row's blank :class:`Suggestion` (``isUndefined()``
        true — the dialog decision happens in :meth:`_onOverlayCommitted`,
        and its write commits the typed roman as the session no-op), the
        row's ``arabic`` otherwise.

        Args:
            typedRoman: The roman text typed into the overlay line edit.
            selected: The committed row's suggestion, or ``None``.

        Returns:
            The committed word: the selected row's Arabic word, the typed
            roman for the undefined-word row, empty for a blank commit.
        """
        if isinstance(selected, Suggestion):
            if selected.isUndefined():
                return typedRoman
            return selected.arabic
        return ""

    # ==========================================================================
    def _commitSeparator(self, key: int, keyText: str, modifiers: int) -> tuple[str, bool]:
        """The separator a committing key delivers, and its resync decision.

        One place for the separator/edge/write decisions (B6). A plain
        ``Key_Return`` commits the empty separator — the cursor rests at
        the committed word's end, which is over the word, so the resync
        would only re-trigger the overlay the user just dismissed — and
        suppresses the resync; ``Key_Return`` with ``ControlModifier``
        commits the literal ``"\\n"`` (its ``keyText`` is
        platform-dependent) and resyncs; ``Key_Up`` / ``Key_Down`` (the
        Ctrl+Up / Ctrl+Down commit — the line edit's gate guarantees the
        exact Ctrl mask) commit the empty separator and suppress the
        resync, and the caller moves the document cursor one line
        (:meth:`_onOverlayCommitted`); every other committing key commits
        its ``keyText`` (``Key_Space``, typed punctuation — including the
        Arabic script's own separator marks) and resyncs. The edge keys
        (``Key_Left`` / ``Key_Right``) handle their own separator ("") and
        decision in :meth:`_edgeCommit`.

        Args:
            key: The committing Qt key.
            keyText: The key's text as Qt reports it.
            modifiers: The keyboard modifiers held with the key.

        Returns:
            ``(separator, resync)`` — the separator character committed
            with the word, and whether the caller may run the post-commit
            resync.
        """
        if key == Qt.Key.Key_Return:
            if modifiers & Qt.KeyboardModifier.ControlModifier.value:
                return "\n", True
            return "", False
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            return "", False
        if key in (
            Qt.Key.Key_0,
            Qt.Key.Key_1,
            Qt.Key.Key_2,
            Qt.Key.Key_3,
            Qt.Key.Key_4,
            Qt.Key.Key_5,
            Qt.Key.Key_6,
            Qt.Key.Key_7,
            Qt.Key.Key_8,
            Qt.Key.Key_9,
        ):
            # A digit commits like punctuation (its ``keyText`` is the
            # separator, substituted in :meth:`_writeCommit`), but
            # suppresses the resync: the digit is a boundary, not word
            # matter, so the cursor comes to rest just past the word's run
            # on the digit itself. A resync would find no word there and
            # deactivate the overlay anyway; suppressing it keeps the
            # commit quiet, exactly like a plain ``Key_Return`` commit,
            # whose resync is likewise suppressed.
            return keyText, False
        return keyText, True

    # ==========================================================================
    def _edgeCommit(self, moveLeft: bool) -> bool:
        """The edge decision: move in visual order, never write.

        Nothing is written to the document. Left at the visually left edge
        (the start of the overlay text) moves to the next Arabic word;
        Right at the visually right edge (the end) to the previous one.
        When that word exists, the cursor lands at its edge facing the
        active word — Left at its start, Right at its end — and the
        post-commit resync re-activates the overlay over the landed word
        (a cursor at the word's end is over the word). With no adjacent
        word — the commit landed on a boundary word, whose far side is
        only whitespace — the overlay is closed and the resync skipped, so
        the deactivation sticks and the cursor rests at the boundary edge
        (Left at the word's end, Right at its start) until the next
        trigger.

        Args:
            moveLeft: Whether the committing key was ``Key_Left``.

        Returns:
            Whether the caller may run the post-commit resync.
        """
        if self._activeWord is not None:
            reference = self._activeWord[1] if moveLeft else self._activeWord[0]
        else:
            reference = self._anchorPosition or 0
        adjacent = self._adjacentWord(reference, backwards=not moveLeft)
        if adjacent is None:
            # No adjacent word: the commit landed on a boundary word,
            # whose far side is only whitespace (the cursor has walked
            # off the paragraph's word run). The deactivation must stick,
            # so the resync is skipped — the landing edge is over the
            # active word and the resync would only re-trigger the
            # overlay the user is leaving, pinning the cursor on the
            # boundary word.
            if self._activeWord is not None:
                cursor = self.textCursor()
                cursor.setPosition(self._activeWord[1 if moveLeft else 0])
                self.setTextCursor(cursor)
            self._deactivateOverlay()
            return False
        cursor = self.textCursor()
        cursor.setPosition(adjacent[0 if moveLeft else 1])
        self.setTextCursor(cursor)
        return True

    # ==========================================================================
    def _writeCommit(self, word: str, separator: str, typedRoman: str) -> None:
        """The write: insert or replace the committed word, tagged RomanUrdu.

        A separator-key commit inserts the committed word plus the
        separator as a single undoable edit: over an existing word
        (scenario 2) the word's span is replaced, at a bare cursor
        (scenario 1) the text is inserted at the anchor position — or, if
        the cursor had a selection, that selection is replaced. The word
        and the separator both carry the stored
        :attr:`RegionType.RomanUrdu <pyraya.regions.RegionType>` tag (the
        text edit re-highlights the blocks for the tint). The writing
        commit signals :attr:`regionsChanged` once — every writing commit
        changes region state (word and separator land tagged RomanUrdu,
        replacing whatever tags the destination carried), and the emission
        is unconditional (no per-commit comparison, so the signal costs
        nothing per keystroke)
        — and a non-empty committed word also signals
        ``romanWordCommitted``. The widget cursor follows the
        document-cursor edit, and the overlay is deactivated.
        """
        cursor = self.textCursor()
        fmt = QTextCharFormat()
        fmt.setProperty(RegionKindProperty, int(RegionType.RomanUrdu))
        if self._activeWord is not None:
            start, end = self._activeWord
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        elif self._selectionRange is not None:
            # Scenario 1 over a selection: replace the selection,
            # plain QPlainTextEdit typing semantics.
            start, end = self._selectionRange
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        else:
            cursor.setPosition(self._anchorPosition or 0)
        # The committed string is run through the region-scoped substitution
        # before the write: the separator (punctuation or digit) and any
        # digit in an undefined-word commit land in their Urdu form; the
        # dictionary word is already Arabic and passes through.
        cursor.insertText(substituteText(word + separator, RegionType.RomanUrdu), fmt)
        self.regionsChanged.emit()
        if word:
            self.romanWordCommitted.emit(word, typedRoman)
        self.setTextCursor(cursor)
        self._deactivateOverlay()

    # ==========================================================================
    def _insertSubstitutedChar(self, char: str, kind: RegionType) -> None:
        """Insert a substituted character at the cursor, tagged with ``kind``.

        The region-scoped substitution's direct-write site: the character
        lands in the document in its Urdu form, carrying the stored
        :attr:`RegionKindProperty <pyraya.regions.RegionKindProperty>`
        (the text edit re-highlights the block for the tint). It is a plain
        document edit — not a roman-input commit — so it emits neither
        ``regionsChanged`` nor ``romanWordCommitted`` (the contract keeps the
        signal cost-free during typing). The widget cursor follows the edit.

        The write runs with :attr:`_committing` set, so the ``contentsChanged``
        and ``cursorPositionChanged`` signals it fires funnel into
        :meth:`_syncOverlay`'s early exit: the freshly written character is
        now Arabic-script matter with the cursor resting at its end, which is
        over the word, so without the guard the sync would re-activate the
        overlay over the digit itself, contradicting the "direct write, no
        overlay" contract.

        Args:
            char: The substituted character to insert.
            kind: The region kind the character is tagged with.
        """
        self._committing = True
        try:
            cursor = self.textCursor()
            fmt = QTextCharFormat()
            fmt.setProperty(RegionKindProperty, int(kind))
            cursor.insertText(char, fmt)
            self.setTextCursor(cursor)
        finally:
            self._committing = False

    # ==========================================================================
    def _adjacentWord(self, reference: int, backwards: bool) -> tuple[int, int] | None:
        """The nearest Arabic-script word run adjacent to ``reference``.

        When ``backwards`` is true the run is searched at lower index values of ``reference``
        (the previous word); otherwise greater index values (the next word). Non-Arabic
        characters — whitespace, digits, Latin letters — are skipped, so the walk
        crosses block separators the same way the whole-text walk did. The run found
        is returned whole (the containing run of the found character; B2) — whatever
        part of it the walk entered.

        A word run cannot cross a block (the block separator is not
        Arabic), so the walk runs block-local and moves to the neighbour
        block once a block's text is exhausted (A3: the whole-document
        copy is gone). A ``reference`` at the document's inclusive terminator
        end is clamped to the last real character.
        """
        document = self.document()
        limit = document.characterCount() - 1
        if backwards:
            index = min(reference - 1, limit - 1)
            position = index
            while position >= 0:
                block = document.findBlock(position)
                text = block.text()
                if text:
                    local = position - block.position()
                    if local >= len(text):
                        # The block's separator slot: the separator itself
                        # is non-Arabic, the walk resumes at the last real
                        # character of this block.
                        local = len(text) - 1
                    while local >= 0 and not _isArabicChar(text[local]):
                        local -= 1
                    if local >= 0:
                        # The run at the found character, whole (B2): the
                        # previous word, whatever part of it the walk
                        # entered.
                        word = _wordRunAround(text, local)
                        if word is None:
                            position = block.position() - 1
                            continue
                        return (block.position() + word[0], block.position() + word[1])
                position = block.position() - 1
            return None
        position = min(reference, limit)
        while position < limit:
            block = document.findBlock(position)
            text = block.text()
            if text:
                local = position - block.position()
                if local < len(text):
                    while local < len(text) and not _isArabicChar(text[local]):
                        local += 1
                    if local < len(text):
                        # The run at the found character, whole (B2): the
                        # next word, whatever part of it the walk entered.
                        word = _wordRunAround(text, local)
                        if word is None:
                            position = block.position() + block.length()
                            continue
                        return (block.position() + word[0], block.position() + word[1])
                # The separator slot or the block exhausted: skip past the
                # block's separator into the next block.
            position = block.position() + block.length()
        return None

    # ==========================================================================
    def createPopupMenu(self) -> QMenu:
        """Create the context menu with editing and region actions.

        Builds on Qt's standard text-editing context menu (Undo, Redo, Cut,
        Copy, Paste, Delete and Select All, with their usual enable states)
        and appends the region actions and, when the cursor rests on an
        unknown RomanUrdu word, the "Add to dictionary" action.

        Returns:
            The context menu with editing, region, and learn actions.
        """
        menu = self.createStandardContextMenu(QPoint())
        menu.addSeparator()

        cursor = self.textCursor()
        hasSelection = cursor.hasSelection()

        for kind, label in (
            (RegionType.Native, "Region: Native"),
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
                lambda _checked, s=region.start, e=region.end: self._clearTagsOver(s, e)
            )
        menu.addAction(clearOne)

        clearAll = QAction("Clear all regions", self)
        clearAll.setEnabled(bool(self._regionSpans()))
        clearAll.triggered.connect(self.clearRegions)
        menu.addAction(clearAll)

        candidate = self._learnCandidate()
        if candidate is not None:
            action = QAction("Add to dictionary", self)
            action.triggered.connect(lambda _checked, w=candidate: self._addToDictionary(w))
            menu.addAction(action)
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

        ``Ctrl+1`` tags the current selection Native and ``Ctrl+2`` tags
        it as Roman Urdu (the seed kind). ``Ctrl+Space`` turns assist mode
        back on and
        activates the overlay — over the RomanUrdu word under the cursor
        with its romanized text, or, with no such word, an empty overlay
        at the cursor — and never reaches the document. ``Ctrl+Esc`` (the
        exact Ctrl mask) turns assist mode off and deactivates the overlay
        — balancing ``Ctrl+Space``'s re-entry; the overlay is inactive
        here, since an active overlay holds focus in the line edit, so the
        key never reaches the document either. A plain ``Esc`` (no
        modifiers) is the double-tap candidate: a second plain ``Esc``
        within :data:`EscDoubleTapInterval` turns assist mode off,
        irrespective of whether the overlay is shown; a single press is a
        no-op here. While the
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
        if not self._overlayActive() and not (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            text = event.text()
            if len(text) == 1 and text.isascii():
                kind = self._regionKindForTyping()
                if kind is not None:
                    substituted = substituteChar(text, kind)
                    if substituted is not None:
                        # A mapped character (punctuation or digit) lands in
                        # the document in its Urdu form, tagged with the
                        # region kind, written directly with no overlay. This
                        # is region-scoped: it holds regardless of the
                        # roman-input feature or assist mode.
                        self._insertSubstitutedChar(substituted, kind)
                        event.accept()
                        return
                    if (
                        self._romanInputEnabled
                        and self._assistMode
                        and text.isalpha()
                        and kind is RegionType.RomanUrdu
                    ):
                        # A letter seeds the overlay (scenario 1); the
                        # character never reaches the document. Digits no
                        # longer seed — they take the substitution path.
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
            if (
                event.key() == Qt.Key.Key_Escape
                and event.modifiers().value == Qt.KeyboardModifier.ControlModifier.value
            ):
                # Ctrl+Esc (the exact Ctrl mask, no Shift/Alt/Meta) turns
                # assist mode off and deactivates the overlay — balancing
                # Ctrl+Space's re-entry. An active overlay holds focus in
                # the line edit, so the document never sees an Esc while
                # the overlay is active; the deactivation drops any view
                # suspension, like every other user decision.
                self._assistMode = False
                self._deactivateOverlay()
                event.accept()
                return
            if event.key() == Qt.Key.Key_1 and self.textCursor().hasSelection():
                self.setRegionType(RegionType.Native)
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
        if event.modifiers() == Qt.KeyboardModifier.NoModifier and (
            event.key() == Qt.Key.Key_Escape
        ):
            # A plain Esc in the document is the double-tap candidate: a
            # second plain Esc within the interval turns assist mode off,
            # irrespective of whether the overlay is shown; a single tap
            # only records the timestamp and falls through (a no-op here),
            # balancing Ctrl+Esc and Ctrl+Space.
            now = monotonic()
            if self._lastEscAt is not None and now - self._lastEscAt <= EscDoubleTapInterval:
                self._assistMode = False
                self._lastEscAt = None
                self._deactivateOverlay()
                event.accept()
                return
            self._lastEscAt = now
            super().keyPressEvent(event)
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
        grant that reveals a suspended anchor resumes it. The dispatch is
        :meth:`_onViewChanged` (B7): the funnel shared with
        :meth:`_onScrollChanged`, so the two view events make the same
        decision.

        Args:
            event: The resize event.
        """
        super().resizeEvent(event)
        self._onViewChanged()

    # ==========================================================================
    def _applyRegionTags(self, start: int, end: int, kind: RegionType) -> None:
        """Store the region-kind property over a character range.

        The range is clamped to the document's real text offsets
        (:meth:`_clampRange` — the trailing terminator never participates,
        merges across it are silently dropped) and the kind is written as
        the :data:`~pyraya.regions.RegionKindProperty` custom property
        merged over the selection on a throwaway document cursor (a
        widget-cursor copy would also work — its position writes do not
        move the widget cursor — but the fresh cursor is the one
        convention the module owns). Format changes are undoable (one
        step) and survive edits, and nothing else stores region data.
        The tint is driven explicitly: the affected blocks are
        re-highlighted here (:meth:`_rehighlightTags`) and
        :attr:`_pendingTagRepaint` is raised for the undo/redo repair —
        Qt also auto-re-highlights the write and its undo/redo with its
        own pass, making the explicit one belt-and-braces on top.
        """
        start, end = self._clampRange(start, end)
        if start >= end:
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setProperty(RegionKindProperty, int(kind))
        cursor.mergeCharFormat(fmt)
        self._rehighlightTags(start, end)
        self._pendingTagRepaint = True
        self.viewport().update()

    # ==========================================================================
    def _rehighlightTags(self, start: int, end: int) -> None:
        """Re-highlight the blocks a stored-tag write touched.

        One ``rehighlightBlock`` per block overlapping ``[start, end)``,
        bouncing over the same block span the property walk covers.
        Measured (probes): Qt auto-re-highlights a property-only
        ``mergeCharFormat`` write and its undo/redo on its own
        ``contentsChange`` reactions, so this explicit pass is
        belt-and-braces — kept because the widget's repair guarantee
        must not rest on an undocumented Qt reaction.
        """
        block = self.document().findBlock(start)
        while block.isValid() and block.position() < end:
            self._highlighter.rehighlightBlock(block)
            block = block.next()

    # ==========================================================================
    def _storedTagRuns(self) -> list[tuple[int, int, QTextCharFormat]]:
        """The document's stored-tag spans, one entry per format run.

        One read per format run — fragments partition the real text, and
        the block separators in between are read through
        :meth:`_charFormatAt` (a tag write carried over a selection
        reaches the separator too) — the same observable the resolved-kind
        walk (:meth:`_kindRuns`) uses. Only formats carrying the
        :data:`~pyraya.regions.RegionKindProperty` are reported; the
        trailing terminator never participates.

        Returns:
            ``(start, end, format)`` triples over the real text; the
            formats are value copies, free to mutate.
        """
        runs: list[tuple[int, int, QTextCharFormat]] = []
        document = self.document()
        limit = document.characterCount() - 1
        if limit <= 0:
            return runs
        block = document.firstBlock()
        while block.isValid():
            for it in cast("Iterable[QTextBlock.iterator]", block):
                fragment = it.fragment()
                start = fragment.position()
                end = min(start + fragment.length(), limit)
                if start < end:
                    fmt = fragment.charFormat()
                    if fmt.hasProperty(RegionKindProperty):
                        runs.append((start, end, fmt))
            separator = block.position() + block.length() - 1
            if separator < limit:
                fmt = self._charFormatAt(separator)
                if fmt.hasProperty(RegionKindProperty):
                    runs.append((separator, separator + 1, fmt))
            block = block.next()
        return runs

    # ==========================================================================
    def _batchRemoveTags(self, matches: list[tuple[int, int, QTextCharFormat]]) -> None:
        """Remove the property from the given stored-tag spans in one batch.

        Every span is replayed inside ONE edit block — the whole removal
        is one undo step. ``setCharFormat`` (not a merge) applies a copy
        of the span's own format minus the property, because a merge
        cannot remove a property. A format-only write does not re-highlight,
        so the whole document is re-highlighted and
        :attr:`_pendingTagRepaint` raised for the undo/redo repair.
        """
        document = self.document()
        # ``beginEditBlock`` lives on the cursor (PySide6 does not map it on
        # the document): one throwaway cursor owns the whole edit block, and
        # every span's ``setCharFormat`` runs through its own cursor inside
        # this block.
        blocker = QTextCursor(document)
        blocker.beginEditBlock()
        try:
            for start, end, fmt in matches:
                fmt.clearProperty(RegionKindProperty)
                cursor = QTextCursor(document)
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(fmt)
        finally:
            blocker.endEditBlock()
        self._highlighter.rehighlight()
        self._pendingTagRepaint = True
        self.viewport().update()

    # ==========================================================================
    def _clearTagsOver(self, start: int, end: int) -> bool:
        """Remove the stored tags overlapping a character range.

        Args:
            start: The first character offset to clear.
            end: One past the last character offset to clear.

        Returns:
            True when any stored tag was removed; False when the range
            holds no stored tags (the removal then writes nothing).
        """
        start, end = self._clampRange(start, end)
        if start >= end:
            return False
        matches = [
            (runStart, runEnd, fmt)
            for runStart, runEnd, fmt in self._storedTagRuns()
            if runStart < end and start < runEnd
        ]
        if not matches:
            return False
        self._batchRemoveTags(matches)
        return True

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
        """Reconstruct region spans from the document's resolved kinds.

        Every character resolves to exactly one kind — a stored tag wins,
        untagged text takes the widget's seed — so the spans cover the
        real text. The walk reads whole format runs (one fragment
        carries one char format, hence one resolved kind) instead of one
        char-format read per character, which keeps large-document scans
        orders of magnitude cheaper; block separators are not fragments,
        so each separator's format is read through :meth:`_charFormatAt`
        over the same two-step resolution — the same observable a
        per-character scan sees. Adjacent runs of one kind merge into one
        span exactly as a per-character kind scan merges. The trailing
        terminator character of the last block is never part of a
        region, so the walk stops before it.
        """
        spans: list[TextRegion] = []
        for start, end, kind in self._kindRuns():
            previous = spans[-1] if spans else None
            if previous is not None and previous.kind == kind and previous.end == start:
                spans[-1] = TextRegion(previous.start, end, kind)
            else:
                spans.append(TextRegion(start, end, kind))
        return spans

    # ==========================================================================
    def _kindRuns(self) -> list[tuple[int, int, RegionType]]:
        """Maximal character runs sharing one resolved kind.

        Returns ``(start, end, kind)`` triples covering the real text
        (``[0, characterCount() - 1)``) in document order, adjacent runs
        merged when their resolved kinds are equal. Real characters are
        read as format runs — one fragment carries one char format,
        hence one kind, resolved through
        :func:`~pyraya.regions.resolveRegionKind` (stored tag first,
        then the widget's seed) — while block separators are not
        fragments: each separator's format is read through
        :meth:`_charFormatAt` over the same resolution, the observable a
        per-character scan sees. The trailing terminator is excluded.
        """
        runs: list[tuple[int, int, RegionType]] = []
        document = self.document()
        limit = document.characterCount() - 1
        if limit <= 0:
            return runs
        seed = self._seedRegionKind

        def appendRun(start: int, end: int, kind: RegionType) -> None:
            previous = runs[-1] if runs else None
            if previous is not None and previous[1] == start and previous[2] == kind:
                runs[-1] = (previous[0], end, kind)
            else:
                runs.append((start, end, kind))

        block = document.firstBlock()
        while block.isValid():
            # PySide6 has no iterator-increment API; forward iteration is the
            # only way to walk a block's fragments, but the bundled stubs do
            # not declare QTextBlock.__iter__ — hence the cast.
            for it in cast("Iterable[QTextBlock.iterator]", block):
                fragment = it.fragment()
                start = fragment.position()
                end = min(start + fragment.length(), limit)
                if start < end:
                    appendRun(start, end, resolveRegionKind(fragment.charFormat(), seed))
            separator = block.position() + block.length() - 1
            if separator < limit:
                appendRun(
                    separator,
                    separator + 1,
                    resolveRegionKind(self._charFormatAt(separator), seed),
                )
            block = block.next()
        return runs

    # ==========================================================================
    def _regionKindAt(self, position: int) -> RegionType:
        """Return the region kind resolved at a character offset.

        The stored character format's kind property, else the widget's
        seed — resolution is owned once in
        :func:`~pyraya.regions.resolveRegionKind`; the method only
        resolves the widget's document and seed there.
        """
        return resolveRegionKind(self._charFormatAt(position), self._seedRegionKind)

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
    def _typingKindAt(self, position: int) -> RegionType:
        """The kind a character typed at ``position`` carries.

        The character format at or before the cursor governs the typed
        character. At a block start the block's own char format governs
        for blocks Qt seeded (``insertBlock`` inherits the creating
        cursor's char format, so an empty block types with it — the Enter
        continuation rides stored properties with no hook), but Qt never
        updates an existing block's char format when a later merge
        retags its characters, so a NON-empty block start answers the
        region-semantic kind of its first real character instead — the
        stretch the typing lands in. Past a block's real text (through
        the terminator slot) the last real character governs — block
        separators and the trailing terminator never belong to a region.

        Args:
            position: The document character offset to type at.

        Returns:
            The resolved :class:`~pyraya.regions.RegionType`.
        """
        document = self.document()
        block = document.findBlock(position)
        # The document-level ``contentsChanged`` fires while a document
        # replacement (``setPlainText``) is mid-flight, as in
        # ``_wordUnderCursor``: the invalid block resolves to the seed.
        if not block.isValid():
            return self._seedRegionKind
        local = position - block.position()
        if local <= 0:
            if block.text():
                # A non-empty block: its own char format is stale for the
                # kinds (never updated after creation), so the region the
                # typing lands in is its first real character's kind.
                return self._regionKindAt(position)
            return resolveRegionKind(block.charFormat(), self._seedRegionKind)
        # Inside or right after the block's real text: the character in
        # front of the cursor governs.
        return self._regionKindAt(min(position, block.position() + len(block.text())) - 1)

    # ==========================================================================
    def _regionKindForTyping(self) -> RegionType | None:
        """The region kind for the scenario-1 typing gate at the cursor.

        A cursor with a selection resolves at the selection start. A bare
        cursor resolves at its position: the stored tag, else the seed.
        Positions past the document end return None; an empty document
        resolves to the seed.

        Returns:
            The gate kind, or ``None`` past the document end.
        """
        cursor = self.textCursor()
        document = self.document()
        limit = document.characterCount() - 1
        if limit <= 0:
            return self._seedRegionKind
        if cursor.hasSelection():
            return self._typingKindAt(cursor.selectionStart())
        position = cursor.position()
        if not 0 <= position <= limit:
            return None
        return self._typingKindAt(position)

    # ==========================================================================
    def _charFormatAt(self, position: int) -> QTextCharFormat:
        """Return the character format stored at a document offset.

        The position-reading rule (cursor one offset past the target, a
        fresh document-bound cursor) is owned once at module level
        (:func:`_charFormatAt`); the method only resolves the widget's
        document there.
        """
        return _charFormatAt(self.document(), position)

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
            # The selection carries the merge to every existing block
            # (:meth:`mergeBlockFormat` otherwise only reaches the block
            # under the cursor). It lives on the throwaway cursor, so the
            # widget's own cursor keeps its position and selection.
            cursor.select(QTextCursor.SelectionType.Document)

            to = self.document().defaultTextOption()

            blockFormat = QTextBlockFormat()
            blockFormat.setAlignment(to.alignment())

            cursor.mergeBlockFormat(blockFormat)
        finally:
            self.blockSignals(False)


# ******************************************************************************

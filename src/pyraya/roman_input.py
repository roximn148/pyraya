# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Roman-script input engine for PyRaya.

A thin, lazily-loaded wrapper around a :class:`romanalfaz.RomanAlfaz`
dictionary engine. It merges the three edit-distance tiers (exact,
edit distance 1, edit distance 2) into a single ordered, globally
deduplicated list of :class:`Suggestion` objects, romanizes Arabic-script
words into the encoded roman form the lookup consumes, and exposes
:meth:`RomanInputEngine.learnRomanWord` — a no-op for this session that
simply returns the typed word as-is, and the hook for the future learning
feature.

The engine (and its ~0.2 s cold dictionary load) is created on first
overlay activation, never during widget construction. If the default
wordlist is missing (:class:`romanalfaz.DictionaryNotFoundError`), the
engine surfaces an unavailable state rather than raising: suggestions are
empty and :meth:`RomanInputEngine.learnRomanWord` still works.
"""

import string
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from romanalfaz import DictionaryNotFoundError, RomanAlfaz
from romanalfaz.algorithm import tafseerUrduAr2Rm
from romanalfaz.engine import Suggestion, Vocabulary

__all__ = ["RomanInputEngine", "RomanOverlay"]

#: Characters that trigger a separator-key commit: every punctuation mark,
#: plus space and newline.
_SEPARATORS = set(string.punctuation) | {" ", "\n"}

#: Subtle tier tints: green = exact, orange = edit distance 1, red = distance 2.
_TIER_COLORS = {
    0: QColor(0x4F, 0x9D, 0x4F, 30),
    1: QColor(0xE8, 0x8A, 0x1A, 30),
    2: QColor(0xC4, 0x3B, 0x3B, 30),
}

#: The stronger tint and accent border applied to the selected row.
_SELECTED_ALPHA = 90
_ACCENT_BORDER = QColor(0x1D, 0x4E, 0x89)

#: The dashed gray style of the placeholder (Learn) row.
_PLACEHOLDER_COLOR = QColor(0x8A, 0x8F, 0x98, 30)

#: The maximum number of suggestion rows shown at once; the list scrolls to
#: keep the selected row visible while navigating.
MAX_VISIBLE_ROWS: int = 5


# ******************************************************************************
@dataclass(frozen=True, slots=True)
class _SuggestionRow:
    """One rendered row of the passive suggestion list.

    Args:
        suggestion: The suggestion backing the row; ``None`` for the
            placeholder row.
        arabic: The Arabic-script text drawn in the document font; for the
            placeholder row this is the ``+ Learn <typed roman>`` label.
        tier: The edit-distance tier (0 = exact, 1, 2); -1 for the placeholder.
        isPlaceholder: True for the ``+ Learn`` placeholder row.
    """

    suggestion: Suggestion | None
    arabic: str
    tier: int
    isPlaceholder: bool


# ******************************************************************************
class RomanInputEngine:
    """Thin wrapper around a :class:`romanalfaz.RomanAlfaz` engine.

    The default romanalfaz wordlist is loaded on construction and the
    document-local in-memory :class:`Vocabulary` is attached to it via
    :meth:`RomanAlfaz.addVocabulary` (so local mutations automatically
    recompile the lookup index). The local vocabulary is never mutated in
    this session — :meth:`learnRomanWord` is a no-op and is the hook for the
    future learning feature.

    Args:
        localVocabulary: The document-local in-memory dictionary to attach;
            ``None`` for a default-wordlist-only engine.
        distance: The maximum edit distance searched (tiers: exact,
            distance 1, …, distance ``distance``).
        maxPredictions: The per-tier candidate cap.
        maxSuggestions: The cap on the merged, deduplicated suggestion list.
    """

    def __init__(
        self,
        localVocabulary: Vocabulary | None = None,
        *,
        distance: int = 2,
        maxPredictions: int = 5,
        maxSuggestions: int = 10,
    ) -> None:
        self._localVocabulary = localVocabulary
        self._distance = distance
        self._maxPredictions = maxPredictions
        self._maxSuggestions = maxSuggestions
        self._alfaz: RomanAlfaz | None = None
        self.available = False
        try:
            alfaz = RomanAlfaz()
            if localVocabulary is not None:
                alfaz.addVocabulary(localVocabulary)
            self._alfaz = alfaz
            self.available = True
        except DictionaryNotFoundError:
            self._alfaz = None
            self.available = False

    # ==========================================================================
    def suggest(self, romanWord: str) -> list[Suggestion]:
        """Suggest Arabic-script words for a roman word.

        Merges the three edit-distance tiers in tier order, deduplicates
        globally by Arabic word (the earlier tier wins), and caps the list
        at ``maxSuggestions``.

        Args:
            romanWord: The roman-script word to look up.

        Returns:
            The ordered, deduplicated, capped suggestion list; empty when the
            engine is unavailable or nothing matches.
        """
        return [suggestion for suggestion, _ in self.suggestTiers(romanWord)]

    # ==========================================================================
    def suggestTiers(self, romanWord: str) -> list[tuple[Suggestion, int]]:
        """Suggest Arabic-script words with each suggestion's tier index.

        Like :meth:`suggest`, but returns ``(suggestion, tier)`` pairs so the
        overlay can color-code rows by edit-distance tier (0 = exact,
        1 = distance 1, 2 = distance 2) without re-deriving the distance.

        Args:
            romanWord: The roman-script word to look up.

        Returns:
            The tiered, globally deduplicated, capped list; empty when the
            engine is unavailable or nothing matches.
        """
        alfaz = self._alfaz
        if not self.available or alfaz is None:
            return []
        tierLists = alfaz.suggest(
            romanWord,
            distance=self._distance,
            maxPredictions=self._maxPredictions,
        )
        merged: list[tuple[Suggestion, int]] = []
        seen: set[str] = set()
        for tier, tierList in enumerate(tierLists):
            for suggestion in tierList:
                if suggestion.arabic in seen:
                    continue
                seen.add(suggestion.arabic)
                merged.append((suggestion, tier))
                if len(merged) >= self._maxSuggestions:
                    return merged
        return merged

    # ==========================================================================
    def romanizeArabic(self, arabicWord: str) -> str:
        """Romanize an Arabic-script word into the encoded roman form.

        Uses ``tafseerUrduAr2Rm`` and lowercases the result, so the form
        round-trips exactly with the romanalfaz lookup (e.g. ``خوش`` →
        ``khosh``, ``میری`` → ``myry``, ``دوست`` → ``dost``). Vowel-like
        marks derived from ی/ہ/ے are kept when present and dropped
        otherwise.

        Args:
            arabicWord: The Arabic-script word to romanize.

        Returns:
            The lowercased encoded roman.
        """
        encoded, _undef = tafseerUrduAr2Rm(arabicWord)
        return encoded.lower()

    # ==========================================================================
    def learnRomanWord(self, word: str) -> str:
        """Learn a typed roman word.

        **No-op for this session**: simply returns the same word as-is (the
        typed roman). It is the hook the placeholder (Learn) commit maps
        to; in the future it will return the Arabic-script word for the
        typed roman and update the local vocabulary, guarded by full
        mappability.

        Args:
            word: The typed roman word.

        Returns:
            The same word, unchanged.
        """
        return word


# ******************************************************************************
class SuggestionList(QWidget):
    """Passive row display for roman-input suggestions.

    A lightweight widget that renders each row with only its Arabic-script
    text in the document font, color-coded by edit-distance tier (green =
    exact, orange = distance 1, red = distance 2). The selected row is
    emphasized with a stronger tint and an accent border; the placeholder
    (Learn) row is drawn in a distinct dashed gray style. At most
    ``maxVisibleRows`` rows are shown at once; the list scrolls so the
    selected row stays visible while navigating. The preferred width covers
    the widest rendered row with the configurable margin on both sides, so
    no row's text is clipped.

    This widget never takes focus — all key handling lives in the overlay's
    :class:`RomanLineEdit`.
    """

    def __init__(
        self,
        font: QFont,
        parent: QWidget | None = None,
        maxVisibleRows: int = MAX_VISIBLE_ROWS,
        margin: int = 6,
    ) -> None:
        """Create the suggestion list.

        Args:
            font: The document font used to render the Arabic words.
            parent: The parent widget (the overlay).
            maxVisibleRows: The maximum number of rows shown at once; the
                list scrolls to keep the selected row in view.
            margin: The horizontal margin (in pixels) left on both sides of
                the widest rendered row.
        """
        super().__init__(parent)
        self._font = font
        self._metrics = QFontMetrics(font)
        self._maxVisibleRows = maxVisibleRows
        self._margin = margin
        self._rows: list[_SuggestionRow] = []
        self._selectedIndex: int = -1
        self._firstRow: int = 0
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

    # ==========================================================================
    def setRows(self, rows: list[_SuggestionRow]) -> None:
        """Replace the rendered rows and reset the selection to row 0."""
        self._rows = list(rows)
        self._selectedIndex = 0 if self._rows else -1
        self._firstRow = 0
        self.setVisible(bool(self._rows))
        self.updateGeometry()
        self.update()

    # ==========================================================================
    def rowCount(self) -> int:
        """The number of rendered rows."""
        return len(self._rows)

    # ==========================================================================
    def selectedIndex(self) -> int:
        """The highlighted row index, or -1 when there are no rows."""
        return self._selectedIndex

    # ==========================================================================
    def firstRow(self) -> int:
        """The index of the topmost visible row."""
        return self._firstRow

    # ==========================================================================
    def visibleRowCount(self) -> int:
        """The number of rows that fit in the widget's current height."""
        return max(1, self.height() // self._rowHeight())

    # ==========================================================================
    def select(self, index: int) -> None:
        """Highlight the given row (ignored when out of range).

        The visible window is scrolled so the highlighted row stays in view.
        """
        if 0 <= index < len(self._rows):
            self._selectedIndex = index
            self._scrollToRow(index)
            self.update()

    # ==========================================================================
    def selectedRow(self) -> _SuggestionRow | None:
        """The highlighted row, or ``None`` when no row is highlighted."""
        if 0 <= self._selectedIndex < len(self._rows):
            return self._rows[self._selectedIndex]
        return None

    # ==========================================================================
    def selectedSuggestion(self) -> Suggestion | None:
        """The highlighted suggestion, or ``None`` for the placeholder row."""
        row = self.selectedRow()
        return row.suggestion if row is not None else None

    # ==========================================================================
    def isPlaceholderSelected(self) -> bool:
        """True when the highlighted row is the placeholder (Learn) row."""
        row = self.selectedRow()
        return row is not None and row.isPlaceholder

    # ==========================================================================
    def sizeHint(self) -> QSize:
        """The preferred size: the widest row plus margin, up to ``maxVisibleRows`` rows.

        The width covers the widest rendered row with the margin on both
        sides, so no row's text is clipped; the height is capped at the
        visible-row limit, so the list scrolls rather than growing with the
        full suggestion count.
        """
        if not self._rows:
            return QSize(0, 0)
        width = max(self._rowWidth(row) for row in self._rows)
        width += 2 * self._margin
        visible = min(len(self._rows), self._maxVisibleRows)
        return QSize(width, self._rowHeight() * visible)

    # ==========================================================================
    def _rowHeight(self) -> int:
        """One row's height: the font line height plus padding."""
        return self._metrics.height() + 6

    # ==========================================================================
    def _rowWidth(self, row: _SuggestionRow) -> int:
        """The row's text width in the document font."""
        return self._metrics.horizontalAdvance(row.arabic)

    # ==========================================================================
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Re-clamp the scroll window and repaint when the widget is resized."""
        super().resizeEvent(event)
        if self._selectedIndex >= 0:
            self._scrollToRow(self._selectedIndex)
        else:
            self._firstRow = 0
        self.update()

    # ==========================================================================
    def _scrollToRow(self, index: int) -> None:
        """Scroll the visible window so the row at ``index`` is in view."""
        count = len(self._rows)
        visible = self.visibleRowCount()
        if index < self._firstRow:
            self._firstRow = index
        elif index >= self._firstRow + visible:
            self._firstRow = index - visible + 1
        self._firstRow = max(0, min(self._firstRow, count - visible))

    # ==========================================================================
    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the visible rows: tier tints, the selected-row accent, text.

        Rows outside the visible window — above ``firstRow`` or below the
        widget's bottom — are not drawn.
        """
        if not self._rows:
            return
        last = min(len(self._rows), self._firstRow + self.visibleRowCount())
        painter = QPainter(self)
        rowHeight = self._rowHeight()
        baseline = self._metrics.ascent() + (rowHeight - self._metrics.height()) // 2
        for i in range(self._firstRow, last):
            y = (i - self._firstRow) * rowHeight
            row = self._rows[i]
            color = _PLACEHOLDER_COLOR if row.isPlaceholder else _TIER_COLORS[row.tier]
            if i == self._selectedIndex:
                color = QColor(color.red(), color.green(), color.blue(), _SELECTED_ALPHA)
            painter.fillRect(QRect(0, y, self.width(), rowHeight), QBrush(color))
            if i == self._selectedIndex:
                painter.setPen(QPen(_ACCENT_BORDER, 1))
            elif row.isPlaceholder:
                painter.setPen(QPen(_PLACEHOLDER_COLOR, 1, Qt.PenStyle.DashLine))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(0, y, self.width() - 1, rowHeight - 1)

            painter.setFont(self._font)
            painter.setPen(QPen(Qt.GlobalColor.black))
            arabicWidth = self._metrics.horizontalAdvance(row.arabic)
            x = self.width() - self._margin - arabicWidth
            painter.drawText(x, y + baseline, row.arabic)
        painter.end()


# ******************************************************************************
class RomanLineEdit(QLineEdit):
    """The overlay's roman line edit — all key handling lives here.

    Typing letters/digits edits the roman text and refreshes the suggestions
    synchronously. Space, Enter, and any typed punctuation character commit
    the selected suggestion together with the separator character. Left with
    the text cursor at the start of the text, or Right with it at the end,
    commits at the edge (no separator character). Up/Down move the highlighted
    suggestion with wraparound. Esc cancels. Wheel events are explicitly
    forwarded to the nearest scroll-area ancestor, because
    ``QCoreApplication.sendEvent`` does not bubble to parents.
    """

    def __init__(self, overlay: RomanOverlay, parent: QWidget | None = None) -> None:
        """Create the line edit bound to its overlay.

        Args:
            overlay: The owning :class:`RomanOverlay`.
            parent: The parent widget (the overlay).
        """
        super().__init__(parent)
        self._overlay = overlay

    # ==========================================================================
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Forward the wheel event into the nearest scroll-area ancestor.

        ``QCoreApplication.sendEvent`` neither bubbles wheel events to
        parents nor dispatches them onto a scroll area, so the ancestor's
        ``wheelEvent`` is invoked directly.
        """
        node: QObject | None = self._overlay.parent()
        while node is not None and not isinstance(node, QAbstractScrollArea):
            node = node.parent()
        if isinstance(node, QAbstractScrollArea):
            node.wheelEvent(event)
        event.accept()

    # ==========================================================================
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle the overlay key table (see the spec key-handling table)."""
        overlay = self._overlay
        key = event.key()
        if key == Qt.Key.Key_Escape:
            overlay.canceled.emit()
            event.accept()
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            overlay.moveSelection(-1 if key == Qt.Key.Key_Up else 1)
            event.accept()
            return
        text = event.text()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return) or (text and text in _SEPARATORS):
            overlay.commit(text)
            event.accept()
            return
        if key == Qt.Key.Key_Left and self.cursorPosition() == 0:
            overlay.commit("")
            event.accept()
            return
        if key == Qt.Key.Key_Right and self.cursorPosition() == len(self.text()):
            overlay.commit("")
            event.accept()
            return
        super().keyPressEvent(event)
        overlay.refreshSuggestions()


# ******************************************************************************
class RomanOverlay(QWidget):
    """Frameless, non-modal overlay for roman-script editing of an Arabic word.

    A small child widget (typically parented to the host widget's viewport,
    so it scrolls with the text automatically) containing a
    :class:`RomanLineEdit` — where all editing happens — and a passive
    :class:`SuggestionList` below it. The overlay uses a right-to-left layout
    direction with right-aligned text, so typed text grows leftward from the
    word's right edge, matching the document flow.

    The host widget positions and sizes the overlay over the word's rectangle
    and consumes the signals below.

    Signals:
        committed: ``(typedRoman: str, selected: Suggestion | None,
            isPlaceholder: bool, separator: str)`` — emitted on a separator-key
            commit (Space, Enter, typed punctuation) or an edge commit (Left at
            the start / Right at the end of the text); ``separator`` is the
            character written to the document alongside the committed word —
            the space, newline, or punctuation mark — and the empty string for
            an edge commit.
        canceled: emitted when Esc is pressed.
    """

    committed = Signal(str, object, bool, str)
    canceled = Signal()

    def __init__(
        self,
        engine: RomanInputEngine,
        font: QFont,
        parent: QWidget | None = None,
    ) -> None:
        """Create the overlay bound to a roman-input engine.

        Args:
            engine: The :class:`RomanInputEngine` used for suggestions.
            font: The document font, so suggested Arabic previews exactly as
                it will render in the document.
            parent: The parent widget (typically the host's viewport).
        """
        super().__init__(parent)
        self._engine = engine
        self.setFont(font)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._lineEdit = RomanLineEdit(self)
        self._lineEdit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._lineEdit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._list = SuggestionList(font, self)
        self._list.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._lineEdit)
        layout.addWidget(self._list)
        # A trailing stretch absorbs any leftover vertical space when the
        # suggestion list is shorter than the overlay (or hidden for empty
        # text). Without it, QBoxLayout splits the leftover across the layout
        # gaps, and the line edit drifts down away from its top anchor every
        # time the list's height changes during editing.
        layout.addStretch()

    # ==========================================================================
    def engine(self) -> RomanInputEngine:
        """The roman-input engine this overlay uses."""
        return self._engine

    # ==========================================================================
    def lineEdit(self) -> RomanLineEdit:
        """The overlay's roman line edit (all editing happens here)."""
        return self._lineEdit

    # ==========================================================================
    def suggestionList(self) -> SuggestionList:
        """The passive suggestion row display below the line edit."""
        return self._list

    # ==========================================================================
    def setText(self, roman: str) -> None:
        """Set the line edit's roman text and refresh the suggestions.

        Args:
            roman: The roman-script text to edit (e.g. the romanized form of
                the word under the cursor, or the first typed character).
        """
        self._lineEdit.setText(roman)
        self._lineEdit.setCursorPosition(len(roman))
        self.refreshSuggestions()

    # ==========================================================================
    def refreshSuggestions(self) -> None:
        """Rebuild the suggestion rows from the current line-edit text.

        Empty text hides the list. A non-empty text with zero matches shows a
        single placeholder row, ``+ Learn <typed roman>`` — unless the engine
        is unavailable, in which case no rows and no placeholder are offered.
        """
        text = self._lineEdit.text()
        if not text:
            self._list.setRows([])
            return
        rows: list[_SuggestionRow] = []
        for suggestion, tier in self._engine.suggestTiers(text):
            rows.append(
                _SuggestionRow(
                    suggestion=suggestion,
                    arabic=suggestion.arabic,
                    tier=tier,
                    isPlaceholder=False,
                ),
            )
        if not rows and self._engine.available:
            rows.append(
                _SuggestionRow(
                    suggestion=None,
                    arabic=f"+ Learn {text}",
                    tier=-1,
                    isPlaceholder=True,
                ),
            )
        self._list.setRows(rows)

    # ==========================================================================
    def moveSelection(self, delta: int) -> None:
        """Move the highlighted suggestion row by ``delta`` (wrapping)."""
        count = self._list.rowCount()
        if count == 0:
            return
        current = self._list.selectedIndex()
        if current < 0:
            self._list.select(0)
            return
        self._list.select((current + delta) % count)

    # ==========================================================================
    def commit(self, separator: str) -> None:
        """Emit :attr:`committed` for the current text and selection.

        Args:
            separator: The character written to the document alongside the
                committed word (space, newline, or punctuation); the empty
                string for an edge commit.
        """
        self.committed.emit(
            self._lineEdit.text(),
            self._list.selectedSuggestion(),
            self._list.isPlaceholderSelected(),
            separator,
        )

    # ==========================================================================
    def sizeHint(self) -> QSize:
        """Preferred size: the line edit plus the suggestion list below it."""
        line = self._lineEdit.sizeHint()
        listHint = self._list.sizeHint()
        width = max(line.width(), listHint.width())
        height = line.height() + 4 + listHint.height()
        return QSize(width, height)

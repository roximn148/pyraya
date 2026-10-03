# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""PyRaya — a self-contained PySide6 (Qt) text editor widget for Urdu.

The public entry point is :class:`PyRaya`, a drop-in ``QPlainTextEdit`` for
right-to-left (Nastaliq) Urdu text in Qt applications — currently PySide6 only.

PyRaya ships with a configurable, dedicated :class:`PyRayaHighlighter` that
provides rule-based formatting for Urdu and mixed-script text.
"""

from collections.abc import Sequence

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import QPlainTextEdit, QWidget

__all__ = ["PyRaya", "PyRayaHighlighter"]

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


class PyRaya(QPlainTextEdit):
    """Self-contained PySide6 text editor widget for Urdu/Nastaliq text.

    A drop-in ``QPlainTextEdit`` for embedding Urdu text editing in a Qt UI.
    Configures right-to-left layout, right-aligned paragraphs, a configurable
    Noto font stack (default ``Noto Naskh Arabic``), visible whitespace, and a
    dedicated rule-based :class:`PyRayaHighlighter` for formatting.
    """

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

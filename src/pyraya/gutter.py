# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""The line-number gutter module.

The gutter is a right-edge strip of line numbers, one per document line,
rendered in Eastern or Western digits. It is off by default; the host opts
in via :meth:`PyRaya.setGutterEnabled`.

The digit conversion reuses :func:`~pyraya.regions.substituteText` from
`regions.py` rather than defining a new digit table.
"""

from enum import IntEnum
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import (
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
    QTextBlock,
)
from PySide6.QtWidgets import QWidget

from .regions import RegionType, substituteText
from .theme import resolveTheme

if TYPE_CHECKING:
    from .pyraya_widget import PyRaya


# ******************************************************************************
class DigitSet(IntEnum):
    """The digit set the gutter renders line numbers in.

    A closed IntEnum mirroring :class:`~pyraya.regions.RegionType`.
    """

    Western = 0
    Eastern = 1


# ******************************************************************************
def formatLineNumber(number: int, digitSet: DigitSet) -> str:
    """Format a 1-based line number as a digit string.

    Eastern digits are produced by substituting each ASCII digit
    ``0-9`` with its Eastern Arabic-Indic equivalent via
    :func:`~pyraya.regions.substituteText` (the ``RomanUrdu`` table);
    Western digits pass through unchanged (identity).

    Args:
        number: The 1-based line number to format.
        digitSet: The digit set to render in.

    Returns:
        The formatted digit string.
    """
    text = str(number)
    if digitSet is DigitSet.Eastern:
        return substituteText(text, RegionType.RomanUrdu)
    return text


# ******************************************************************************
class GutterArea(QWidget):
    """The line-number strip: one number per visible document line.

    A child of :class:`~pyraya.PyRaya`, **sibling of the viewport**,
    placed at the right edge of ``contentsRect``. It paints the line
    numbers in Eastern or Western digits, coloured by the theme stop,
    with a 1 px border on the text-facing (left) edge and a configurable
    paint padding around the numbers (:meth:`setGutterPadding`, seeded
    4 px).

    The gutter is read-only over the document: painting never edits,
    never re-highlights, never bumps the revision, never touches the
    undo stack.
    """

    def __init__(self, parent: QWidget) -> None:
        """Initialize the gutter strip.

        Args:
            parent: The parent widget (the :class:`PyRaya` instance).
        """
        super().__init__(parent)
        self._digitSet: DigitSet = DigitSet.Eastern
        self._gutterFont: QFont = parent.font()
        self._gutterPadding: float = 4.0

    def setDigitSet(self, digitSet: DigitSet) -> None:
        """Set the digit set for line numbers.

        Args:
            digitSet: The digit set to render in.
        """
        self._digitSet = digitSet

    def setGutterFont(self, font: QFont) -> None:
        """Set the gutter font (independent of the document font).

        Args:
            font: The font to use for line numbers.
        """
        self._gutterFont = font

    def setGutterPadding(self, padding: float) -> None:
        """Set the paint padding around the line numbers.

        Insets the paint band on both sides of the centred numbers;
        the band is a paint-only concern and never enters the width
        formula.

        Args:
            padding: The padding in pixels. A negative padding is
                ignored.
        """
        if padding < 0:
            return
        self._gutterPadding = padding

    def gutterPadding(self) -> float:
        """The paint padding around the line numbers.

        Returns:
            The padding in pixels, seeded at 4.0.
        """
        return self._gutterPadding

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the line numbers for visible blocks only.

        Walks visible blocks only (bounded to the dirty rect —
        load-bearing for the 200 k latency budget), draws each 1-based
        number with the converted digit string, centred horizontally and
        vertically on the block's first line, and inset by the gutter
        padding on both sides, then a 1 px border on the text-facing
        (left) edge.
        Colours are resolved **per paint** from
        ``resolveTheme(self.palette())``.
        """
        parent = self.parent()
        if parent is None:
            return
        # parent is PyRaya (a QPlainTextEdit)
        editor = cast("PyRaya", parent)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tokens = resolveTheme(self.palette())
        painter.fillRect(self.rect(), tokens.gutterBackground)

        # 1 px border on the text-facing (left) edge
        pen = QPen(tokens.gutterBorder)
        painter.setPen(pen)
        painter.drawLine(0, self.rect().top(), 0, self.rect().bottom())

        # Walk visible blocks only: the first visible block bounds the
        # walk below, the document's last block bounds it above.
        first = editor.firstVisibleBlock()
        if not first.isValid():
            painter.end()
            return
        last = editor.document().lastBlock()

        # The dirty rect bounds the paint
        dirty = event.rect()

        painter.setFont(self._gutterFont)
        painter.setPen(tokens.gutterText)
        for block, top, _height in self._iterVisibleBlocks(editor, first, last, dirty):
            line = block.layout().lineAt(0)
            if not line.isValid():
                continue
            number = block.blockNumber() + 1  # 1-based
            text = formatLineNumber(number, self._digitSet)
            # Paint the number into its block's first-line band, centred
            # horizontally and vertically on that line, and inset by the
            # gutter padding on both sides. The band is in
            # GutterArea-local coordinates: the geometry is in PyRaya
            # content coordinates, so shift by the gutter's own y (the
            # gutter sits at the contents rect's top edge).
            painter.drawText(
                QRectF(
                    self._gutterPadding,
                    float(top - self.y()),
                    float(self.width()) - 2.0 * self._gutterPadding,
                    float(line.rect().height()),
                ),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter),
                text,
            )
        painter.end()

    def _iterVisibleBlocks(
        self,
        editor: "PyRaya",
        first: QTextBlock,
        last: QTextBlock,
        dirty: QRect,
    ) -> list[tuple[QTextBlock, int, int]]:
        """The visible blocks within the dirty rect, with geometry.

        Walks forward from the first visible block, bounded above by the
        last visible block and clipped by the dirty rect: a block is
        yielded when its top edge is not past the dirty rect's bottom and
        its extent reaches the dirty rect's top.

        Args:
            editor: The parent PyRaya widget (a QPlainTextEdit).
            first: The first visible block.
            last: The last visible block (the document's last block).
            dirty: The dirty rect to bound the walk.

        Returns:
            The (block, top, height) triples to paint, in document
            order.
        """
        visible: list[tuple[QTextBlock, int, int]] = []
        block = first
        # Walk forward from the first visible block
        while block.isValid():
            geometry = editor.blockBoundingGeometry(block).translated(editor.contentOffset())
            top = int(geometry.top())
            height = int(geometry.height())
            if top > dirty.bottom():
                break
            if top + height >= dirty.top():
                visible.append((block, top, height))
            if block == last:
                break
            block = block.next()
        return visible

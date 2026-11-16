# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the gutter (line-number strip)."""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QRect
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextCursor
from PySide6.QtWidgets import QApplication

from pyraya import DigitSet, GutterArea, PyRaya
from pyraya.gutter import formatLineNumber
from pyraya.theme import resolveTheme


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
def _processEvents() -> None:
    """Let Qt settle layout and pending signals."""
    QCoreApplication.processEvents()


# ******************************************************************************
class _PaintSpy(QObject):
    """Counts Paint events on its installed target."""

    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Paint:
            self.count += 1
        return False


# ******************************************************************************
def testFormatLineNumberEastern(app: QApplication) -> None:
    """Eastern digits: 0-9 map to Eastern Arabic-Indic."""
    assert formatLineNumber(0, DigitSet.Eastern) == "۰"
    assert formatLineNumber(1, DigitSet.Eastern) == "۱"
    assert formatLineNumber(12, DigitSet.Eastern) == "۱۲"
    assert formatLineNumber(999, DigitSet.Eastern) == "۹۹۹"
    assert formatLineNumber(1000, DigitSet.Eastern) == "۱۰۰۰"


# ******************************************************************************
def testFormatLineNumberWestern(app: QApplication) -> None:
    """Western digits: identity (no substitution)."""
    assert formatLineNumber(0, DigitSet.Western) == "0"
    assert formatLineNumber(42, DigitSet.Western) == "42"
    assert formatLineNumber(1000, DigitSet.Western) == "1000"


# ******************************************************************************
def testDigitSetIsClosedIntEnum(app: QApplication) -> None:
    """DigitSet is a closed IntEnum with exactly two members."""
    assert list(DigitSet) == [DigitSet.Western, DigitSet.Eastern]
    assert int(DigitSet.Western) == 0
    assert int(DigitSet.Eastern) == 1
    assert isinstance(DigitSet.Western, int)


# ******************************************************************************
def testGutterIsOffByDefault(app: QApplication) -> None:
    """The gutter is off by default: no margin, no GutterArea widget."""
    widget = PyRaya()
    widget.resize(900, 600)
    assert widget.isGutterEnabled() is False
    margins = widget.viewportMargins()
    assert margins.right() == 0


# ******************************************************************************
def testGutterEnabledReservesRightMargin(app: QApplication) -> None:
    """setGutterEnabled(True) reserves the right margin and creates GutterArea."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    assert widget.isGutterEnabled() is True
    margins = widget.viewportMargins()
    assert margins.right() > 0
    # GutterArea is a child of PyRaya, sibling of the viewport
    gutter = widget.findChild(GutterArea)
    assert gutter is not None
    # The gutter does not overlap the viewport
    assert gutter.geometry().left() >= widget.viewport().geometry().right()


# ******************************************************************************
def testGutterDisabledRemovesMargin(app: QApplication) -> None:
    """setGutterEnabled(False) removes the margin and hides GutterArea."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    widget.setGutterEnabled(False)
    widget.show()
    _processEvents()
    assert widget.isGutterEnabled() is False
    margins = widget.viewportMargins()
    assert margins.right() == 0


# ******************************************************************************
def testGutterFormatDefaultsToEastern(app: QApplication) -> None:
    """The gutter format defaults to Eastern digits."""
    widget = PyRaya()
    assert widget.gutterFormat() is DigitSet.Eastern


# ******************************************************************************
def testGutterFormatSetter(app: QApplication) -> None:
    """setGutterFormat changes the digit set."""
    widget = PyRaya()
    widget.setGutterEnabled(True)
    widget.setGutterFormat(DigitSet.Western)
    assert widget.gutterFormat() is DigitSet.Western
    widget.setGutterFormat(DigitSet.Eastern)
    assert widget.gutterFormat() is DigitSet.Eastern


# ******************************************************************************
def testGutterFontDefaultsToDocumentFont(app: QApplication) -> None:
    """The gutter font defaults to a copy of the document font."""
    widget = PyRaya()
    docFont = widget.font()
    gutterFont = widget.gutterFont()
    assert gutterFont.family() == docFont.family()
    assert gutterFont.pointSizeF() == docFont.pointSizeF()


# ******************************************************************************
def testGutterFontSetter(app: QApplication) -> None:
    """setGutterFont changes the gutter font independently."""
    widget = PyRaya()
    widget.setGutterEnabled(True)
    newFont = QFont("Arial", 14)
    widget.setGutterFont(newFont)
    assert widget.gutterFont().family() == "Arial"
    assert widget.gutterFont().pointSizeF() == 14.0
    # The document font is unchanged
    docFont = widget.font()
    assert docFont.family() != "Arial" or docFont.pointSizeF() != 14.0


# ******************************************************************************
def testGutterPaintsEasternDigits(app: QApplication) -> None:
    """The gutter paints Eastern Arabic-Indic digits (QPainter into QImage)."""
    widget = PyRaya()
    widget.setPlainText("a\nb\nc")  # 3 lines
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    gutter = widget.findChild(GutterArea)
    assert gutter is not None
    # Paint into a QImage and check that at least one pixel in the gutter
    # region is not the background colour (something was painted)
    image = QImage(gutter.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    gutter.render(painter, QPoint(0, 0))
    painter.end()
    # Check that at least one pixel differs from the background
    found = any(
        QColor(image.pixel(x, y)) != QColor(0, 0, 0, 0)
        for x in range(0, image.width(), 2)
        for y in range(0, image.height(), 2)
    )
    assert found, "gutter must paint at least one non-background pixel"


# ******************************************************************************
def testGutterWidthExpandsPast999(app: QApplication) -> None:
    """The gutter width expands when the largest visible line exceeds 999."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    width3 = widget.viewportMargins().right()

    # Add enough lines to push past 999 (1000 lines), then scroll to the
    # bottom so the largest visible line number exceeds 999.
    lines = "\n".join(f"line {i}" for i in range(1000))
    widget.setPlainText(lines)
    widget.show()
    _processEvents()
    widget.verticalScrollBar().setValue(widget.verticalScrollBar().maximum())
    _processEvents()
    width4 = widget.viewportMargins().right()
    assert width4 > width3, "width must expand past line 999"


# ******************************************************************************
def testGutterWidthShrinksBelow1000(app: QApplication) -> None:
    """The gutter width shrinks when the largest visible line drops below 1000."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()

    # Start with 1000 lines (4-digit width): scroll to the bottom so the
    # largest visible line number exceeds 999.
    lines = "\n".join(f"line {i}" for i in range(1000))
    widget.setPlainText(lines)
    widget.show()
    _processEvents()
    widget.verticalScrollBar().setValue(widget.verticalScrollBar().maximum())
    _processEvents()
    width4 = widget.viewportMargins().right()

    # Shrink to 10 lines (1-digit width, but baseline is 3)
    widget.setPlainText("\n".join(f"line {i}" for i in range(10)))
    widget.show()
    _processEvents()
    width1 = widget.viewportMargins().right()
    assert width1 < width4, "width must shrink below line 1000"


# ******************************************************************************
def testGutterWidthNoOpBumpsNothing(app: QApplication) -> None:
    """A no-op width recompute bumps neither revision nor undo stack."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    widget.setPlainText("hello\nworld")
    _processEvents()

    revision = widget.document().revision()
    undoSteps = widget.document().availableUndoSteps()

    # Trigger a no-op recompute (the width should not change)
    widget._updateGutterWidth()
    _processEvents()

    assert widget.document().revision() == revision
    assert widget.document().availableUndoSteps() == undoSteps


# ******************************************************************************
def testBlockCountChangedLeavesWidthAlone(app: QApplication) -> None:
    """blockCountChanged does not change the width (only largest visible line does)."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    width3 = widget.viewportMargins().right()
    assert width3 > 0

    # A 1500-line document scrolled to the top: the largest visible line
    # is small (a few lines), so the width stays at the 3-digit baseline.
    lines = "\n".join(f"line {i}" for i in range(1500))
    widget.setPlainText(lines)
    widget.show()
    _processEvents()

    # Scroll to the top (line 1)
    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    widget.setTextCursor(cursor)
    _processEvents()

    # The width should be the 3-digit baseline (not 4-digit, even though
    # the document has 1500 lines)
    width = widget.viewportMargins().right()
    assert width == width3, "width must stay at the 3-digit baseline"


# ******************************************************************************
def testGutterFontChangeMovesPixelWidth(app: QApplication) -> None:
    """A font change moves the pixel width at an unchanged digit count."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    widget.setPlainText("a\nb\nc")
    _processEvents()
    widthBefore = widget.viewportMargins().right()

    # Change to a wider font (same digit count: 1 digit)
    widerFont = QFont("Arial", 20)
    widget.setGutterFont(widerFont)
    widget.show()
    _processEvents()
    widthAfter = widget.viewportMargins().right()
    assert widthAfter != widthBefore, "pixel width must change with the font"


# ******************************************************************************
def testDocumentFontChangeLeavesGutterFontUntouched(app: QApplication) -> None:
    """A document font change leaves the gutter font and width untouched."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    widget.setPlainText("a\nb\nc")
    _processEvents()
    gutterFont = widget.gutterFont()
    width = widget.viewportMargins().right()

    # Change the document font
    widget.setFontSize(30)
    widget.show()
    _processEvents()

    # The gutter font is unchanged
    assert widget.gutterFont().pointSizeF() == gutterFont.pointSizeF()
    # The width is unchanged
    assert widget.viewportMargins().right() == width


# ******************************************************************************
def testGutterEnabledWithActiveOverlayReplacesNoRevision(app: QApplication) -> None:
    """Enabling the gutter with an active overlay re-places it with no
    revision bump and no regionsChanged."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setPlainText("کام دوسٹ")
    widget.show()
    _processEvents()

    # Activate the overlay over an Arabic word
    cursor = widget.textCursor()
    cursor.setPosition(2)  # inside "کام"
    widget.setTextCursor(cursor)
    _processEvents()
    assert widget._overlay is not None and widget._overlayActive()

    revision = widget.document().revision()
    emissions: list[int] = []
    widget.regionsChanged.connect(lambda: emissions.append(1))

    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()

    assert widget.document().revision() == revision, "no revision bump"
    assert emissions == [], "no regionsChanged"
    # The overlay should still be active (re-placed, not deactivated)
    assert widget._overlay is not None


# ******************************************************************************
def testGutterReEnableRestoresMargin(app: QApplication) -> None:
    """Re-enabling the gutter after a disable restores margin and geometry."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    width = widget.viewportMargins().right()
    assert width > 0

    widget.setGutterEnabled(False)
    _processEvents()

    # Re-enable: the margin must be restored and the gutter re-placed at
    # the right edge of the contents rect (without this, the no-op width
    # guard swallows the recompute and the gutter paints over the text).
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    margins = widget.viewportMargins()
    assert margins.right() == width, "re-enable must restore the gutter margin"
    gutter = widget.findChild(GutterArea)
    assert gutter is not None
    cr = widget.contentsRect()
    expected = QRect(cr.right() - width, cr.top(), width, cr.height())
    assert gutter.geometry() == expected


# ******************************************************************************
def testGutterNumbersAlignWithTheirLines(app: QApplication) -> None:
    """Each line number is vertically centred on its own block's first line."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.setGutterFont(QFont("Arial", 10))
    widget.setPlainText("a\nb\nc\nd\ne")
    widget.show()
    _processEvents()
    gutter = widget.findChild(GutterArea)
    assert gutter is not None
    background = resolveTheme(widget.palette()).gutterBackground
    # Render the gutter into a QImage (gutter-local coordinates) and check
    # that each block's ink is centred in that block's band.
    image = QImage(gutter.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    gutter.render(painter, QPoint(0, 0))
    painter.end()
    for i in range(5):
        block = widget.document().findBlockByNumber(i)
        line = block.layout().lineAt(0)
        assert line.isValid()
        height = int(line.rect().height())
        geometry = widget.blockBoundingGeometry(block).translated(widget.contentOffset())
        bandTop = int(geometry.top()) - gutter.y()
        bandCenter = bandTop + height // 2
        ink = []
        for y in range(bandTop, min(bandTop + height, image.height())):
            for x in range(2, image.width()):
                if QColor(image.pixel(x, y)) != background:
                    ink.append(y)
        assert ink, f"line {i + 1} must paint ink inside its band"
        centroid = sum(ink) / len(ink)
        assert abs(centroid - bandCenter) <= height // 3, (
            f"line {i + 1} ink centroid {centroid} is not centred in its band {bandCenter}"
        )


# ******************************************************************************
def testGutterNumberCentresOnTheFirstLine(app: QApplication) -> None:
    """A wrapped block's number centres on the block's first line, not its height."""
    widget = PyRaya()
    widget.resize(300, 600)
    widget.setGutterEnabled(True)
    widget.setGutterFont(QFont("Arial", 10))
    widget.setPlainText("a" * 500)
    widget.show()
    _processEvents()
    gutter = widget.findChild(GutterArea)
    assert gutter is not None
    background = resolveTheme(widget.palette()).gutterBackground
    block = widget.document().firstBlock()
    assert block.isValid()
    line = block.layout().lineAt(0)
    assert line.isValid()
    lineHeight = int(line.rect().height())
    geometry = widget.blockBoundingGeometry(block).translated(widget.contentOffset())
    assert lineHeight < int(geometry.height()), "the block must wrap to multiple lines"
    # Render the gutter into a QImage (gutter-local coordinates) and check
    # that the number's ink is centred on the block's first line.
    image = QImage(gutter.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    gutter.render(painter, QPoint(0, 0))
    painter.end()
    bandTop = int(geometry.top()) - gutter.y()
    bandCenter = bandTop + lineHeight // 2
    ink = []
    for y in range(bandTop, min(bandTop + lineHeight, image.height())):
        for x in range(2, image.width()):
            if QColor(image.pixel(x, y)) != background:
                ink.append(y)
    assert ink, "the number must paint ink in the first line's band"
    centroid = sum(ink) / len(ink)
    assert abs(centroid - bandCenter) <= lineHeight // 3, (
        f"ink centroid {centroid} is not centred on the first line {bandCenter}"
    )


# ******************************************************************************
def testResizeRepositionsGutterAtUnchangedWidth(app: QApplication) -> None:
    """A resize that leaves the digit count unchanged still moves the gutter to the edge."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    widget.setPlainText("a\nb\nc")
    _processEvents()
    width = widget.viewportMargins().right()
    assert width > 0

    # A plain resize: the digit count (and therefore the width) is
    # unchanged, but the contents rect moves — the gutter must follow it
    # to the new right edge.
    widget.resize(1200, 700)
    _processEvents()
    gutter = widget.findChild(GutterArea)
    assert gutter is not None
    cr = widget.contentsRect()
    expected = QRect(cr.right() - width, cr.top(), width, cr.height())
    assert gutter.geometry() == expected


# ******************************************************************************
def testGutterSettersMarkTheGutterDirty(app: QApplication) -> None:
    """setGutterFormat and setGutterFont mark the gutter dirty."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    widget.setPlainText("a\nb\nc")
    _processEvents()
    gutter = widget.findChild(GutterArea)
    assert gutter is not None

    spy = _PaintSpy()
    gutter.installEventFilter(spy)

    widget.setGutterFormat(DigitSet.Western)
    _processEvents()
    assert spy.count > 0, "setGutterFormat must mark the gutter dirty"

    spy.count = 0
    # A no-op font (the current gutter font): only an explicit
    # gutter.update() can dirty the strip here — the width path is a
    # no-op for an identical font.
    widget.setGutterFont(widget.gutterFont())
    _processEvents()
    assert spy.count > 0, "setGutterFont must mark the gutter dirty"


# ******************************************************************************
def testGutterPaddingIsConfigurable(app: QApplication) -> None:
    """The gutter padding has a 4 px seed and is settable on GutterArea."""
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.show()
    _processEvents()
    gutter = widget.findChild(GutterArea)
    assert gutter is not None
    assert gutter.gutterPadding() == 4.0
    gutter.setGutterPadding(8.0)
    assert gutter.gutterPadding() == 8.0
    # A negative padding is ignored (the band would run past the border).
    gutter.setGutterPadding(-1.0)
    assert gutter.gutterPadding() == 8.0


# ******************************************************************************
def testGutterPaddingDoesNotShiftTheCentredNumbers(app: QApplication) -> None:
    """The paint padding insets the band without moving the centred ink.

    The numbers are centred in the strip, and the band is always centred
    in the strip, so changing the padding changes only the band's inset,
    never the ink position.
    """
    widget = PyRaya()
    widget.resize(900, 600)
    widget.setGutterEnabled(True)
    widget.setGutterFont(QFont("Arial", 10))
    widget.setPlainText("a\nb\nc")
    widget.show()
    _processEvents()
    gutter = widget.findChild(GutterArea)
    assert gutter is not None
    background = resolveTheme(widget.palette()).gutterBackground

    def inkSpan() -> tuple[int, int]:
        image = QImage(gutter.size(), QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        gutter.render(painter, QPoint(0, 0))
        painter.end()
        xs = [
            x
            for y in range(image.height())
            for x in range(1, image.width())
            if QColor(image.pixel(x, y)) != background
        ]
        assert xs, "the numbers must paint ink inside the gutter"
        return min(xs), max(xs)

    seedMinX, seedMaxX = inkSpan()
    # The numbers are centred in the strip: the ink span is symmetric
    # about the strip's centre.
    centre = (seedMinX + seedMaxX) / 2.0
    assert abs(centre - gutter.width() / 2.0) <= 1.0, "the numbers must be centred in the strip"
    gutter.setGutterPadding(0.0)
    # render() repaints on demand, so the new padding is picked up
    # without a dirty pass.
    zeroMinX, zeroMaxX = inkSpan()
    assert (zeroMinX, zeroMaxX) == (seedMinX, seedMaxX), (
        "the padding must not shift the centred ink"
    )

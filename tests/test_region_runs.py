# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Differential guard: run-based observation reproduces the per-character scan.

Phase A1 replaced the per-character ``_regionSpans`` walk (one char-format
read per character) with a format-run walk, and Phase A2 derived the
highlighter's default-region wash from the same run map. This suite replayed
documents through both — the run-based implementation under test and an
inline per-character reference implementing the pre-A1/pre-A2 rules — and
asserts identical results: region maps, and the wash's merged layout
formats. Kept for one round per plan §7, then to be retired.

The reference walks read kinds exactly as the old code did:
``charFormat()``'s background, mapped through the palette with
:data:`~pyraya.regions.DefaultRegionKind` as the fallback.
"""

import os
import random
from collections.abc import Generator
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QBrush, QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication

from pyraya import (
    DefaultRegionKind,
    PyRaya,
    PyRayaHighlighter,
    RegionType,
    TextRegion,
)
from pyraya.pyraya_widget import _isArabicChar


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
def _referenceKindAt(widget: PyRaya, position: int) -> RegionType:
    """The pre-A1 per-character kind read: one format read per position."""
    color = widget._charFormatAt(position).background().color()
    for kind, regionColor in widget._regionColors.items():
        if color == regionColor:
            return kind
    return DefaultRegionKind


def _referenceSpans(widget: PyRaya) -> list[TextRegion]:
    """The pre-A1 per-character span walk, reimplemented from its rule."""
    spans: list[TextRegion] = []
    limit = widget.document().characterCount() - 1
    position = 0
    while position < limit:
        kind = _referenceKindAt(widget, position)
        start = position
        while position < limit and _referenceKindAt(widget, position) == kind:
            position += 1
        spans.append(TextRegion(start, position, kind))
    return spans


# ******************************************************************************
def _paintReferencePerCharacter(highlighter: PyRayaHighlighter, block: str) -> None:
    """The pre-A2 per-character wash idiom, re-attached as the reference."""
    current = highlighter.currentBlock()
    base = current.position()
    cursor = QTextCursor(highlighter.document())
    for position in range(len(block)):
        cursor.setPosition(base + position + 1)
        color = cursor.charFormat().background().color()
        # Pre-B1 membership rule: a background equal to any palette entry's
        # color marks the character as already carrying a region identity.
        if any(color == rc for rc in highlighter._regionColors.values()):
            continue
        merged = highlighter.format(position)
        merged.setBackground(QBrush(highlighter._regionColors[DefaultRegionKind]))
        highlighter.setFormat(position, 1, merged)


def _washSignatures(widget: PyRaya) -> list[list[tuple[int, int, str, str, object]]]:
    """Every block's merged layout formats as comparable plain values."""
    signatures: list[list[tuple[int, int, str, str, object]]] = []
    block = widget.document().begin()
    while block.isValid():
        blockSignatures: list[tuple[int, int, str, str, object]] = []
        for r in block.layout().formats():
            charFormat = cast(QTextCharFormat, r.format)
            blockSignatures.append(
                (
                    cast(int, r.start),
                    cast(int, r.length),
                    charFormat.background().color().name(QColor.NameFormat.HexArgb),
                    charFormat.foreground().color().name(QColor.NameFormat.HexArgb),
                    cast("QTextCharFormat.UnderlineStyle", charFormat.underlineStyle()),
                )
            )
        signatures.append(blockSignatures)
        block = block.next()
    return signatures


# ******************************************************************************
_Pools = [
    "اردو",  # Arabic script
    "roman urdu",
    "012345",
    " ",
    "،؛؟",  # Arabic-script separators
    "Latin",
    "کام۔",  # word + trailing Arabic separator
    "\n",
    "Zeuge",
]


def _assertSameMap(widget: PyRaya) -> None:
    """The widget's spans must equal the per-character reference walk."""
    assert widget.regions() == _referenceSpans(widget)


def testRunBasedMatchesPerCharacterScan(app) -> None:  # noqa: ARG001
    """Randomized documents: both walks produce the same region maps."""
    rng = random.Random(20261021)
    for _ in range(12):
        widget = PyRaya()
        widget.setPlainText("".join(rng.choice(_Pools) for _ in range(rng.randint(1, 40))))
        for _ in range(rng.randint(0, 8)):
            kind = rng.choice([RegionType.Latin, RegionType.RomanUrdu])
            start = rng.randint(0, max(0, widget.document().characterCount() - 1))
            end = rng.randint(start, widget.document().characterCount())
            widget.setRegionType(kind, start, end)
        _assertSameMap(widget)

        # A raw edit (outside the region API) perturbs the format runs.
        cursor = widget.textCursor()
        cursor.setPosition(rng.randint(0, max(0, cursor.position() - 1)))
        cursor.insertText(rng.choice(_Pools))
        _assertSameMap(widget)

        # A recolour must keep the maps equal through the run-based recolour.
        assert widget.setRegionColor(RegionType.Latin, QColor(0x10, 0x20, 0x30, 40))
        _assertSameMap(widget)

        widget.clearRegions()
        _assertSameMap(widget)


# ******************************************************************************
@pytest.mark.parametrize(
    "text",
    ["", "a", "ab", "ab\ncd", "a\n\nb", "کام۔", "\n", "a\r\nb", "\ufeffاردو"],
)
def testRunBasedEdgeDocuments(app, text: str) -> None:  # noqa: ARG001
    """Hand-picked edges: empty, terminator-adjacent, separator boundaries."""
    widget = PyRaya()
    widget.setPlainText(text)
    _assertSameMap(widget)
    widget.setRegionType(RegionType.Latin, 0, widget.document().characterCount())
    _assertSameMap(widget)
    widget.setRegionType(RegionType.RomanUrdu, 0, widget.document().characterCount() - 1)
    _assertSameMap(widget)


# ******************************************************************************
def testWashLayoutFormatsMatchPerCharacterPaint(app) -> None:  # noqa: ARG001
    """The run-derived wash equals the per-character idiom's layout output."""
    rng = random.Random(20261021)
    for _ in range(8):
        text = "".join(rng.choice(_Pools) for _ in range(rng.randint(1, 25)))
        tagRanges = [
            (
                rng.choice([RegionType.Latin, RegionType.RomanUrdu]),
                rng.randint(0, max(0, len(text))),
                rng.randint(0, len(text)),
            )
            for _ in range(rng.randint(0, 5))
        ]
        widgets: list[PyRaya] = []
        for reference in (False, True):
            widget = PyRaya()
            widget.setPlainText(text)
            widget.highlighter.setSpellCheckEnabled(False)
            for kind, start, end in tagRanges:
                if start < end:
                    widget.setRegionType(kind, start, end)
            if reference:
                highlighter = widget.highlighter

                def _paintReference(block: str, h: PyRayaHighlighter = highlighter) -> None:
                    _paintReferencePerCharacter(h, block)

                highlighter._paintDefaultRegions = _paintReference
            widget.highlighter.rehighlight()
            widgets.append(widget)
        assert _washSignatures(widgets[0]) == _washSignatures(widgets[1])


# ******************************************************************************
def _referenceWordUnderCursor(widget: PyRaya, position: int) -> tuple[int, int] | None:
    """The pre-A3 whole-document word walk, reimplemented from its rule."""
    document = widget.document()
    limit = document.characterCount() - 1
    clamped = min(position, limit)
    text = document.toPlainText()
    start = clamped
    while start > 0 and _isArabicChar(text[start - 1]):
        start -= 1
    end = clamped
    while end < len(text) and _isArabicChar(text[end]):
        end += 1
    if not (start < end and start <= clamped <= end):
        return None
    if (
        _referenceKindAt(widget, start) == RegionType.RomanUrdu
        and _referenceKindAt(widget, end - 1) == RegionType.RomanUrdu
    ):
        return (start, end)
    return None


def _referenceAdjacentWord(
    widget: PyRaya, reference: int, backwards: bool
) -> tuple[int, int] | None:
    """The whole-document adjacent-word walk, reimplemented from its rule.

    B2 ruled the walk to return the containing run of the found
    character whole; the directional skip (first Arabic character at or
    below / above the reference) is the rule the widget's callers see.
    """  # noqa: D205
    text = widget.document().toPlainText()
    if backwards:
        index = min(reference - 1, len(text) - 1)
        while index >= 0 and not _isArabicChar(text[index]):
            index -= 1
    else:
        index = reference
        while index < len(text) and not _isArabicChar(text[index]):
            index += 1
        if index >= len(text):
            return None
    run = _referenceWordRunAround(text, index) if 0 <= index < len(text) else None
    return run


def _referenceWordRunAround(text: str, local: int) -> tuple[int, int] | None:
    """The pre-B2 whole-document containing-run scan, from its rule."""
    if local < 0 or local > len(text):
        return None
    start = local
    while start > 0 and _isArabicChar(text[start - 1]):
        start -= 1
    end = local
    while end < len(text) and _isArabicChar(text[end]):
        end += 1
    if start >= end:
        return None
    return (start, end)


def testWordWalksMatchWholeTextReference(app) -> None:  # noqa: ARG001
    """The block-local word walks equal the whole-document copy walks.

    `_wordUnderCursor` and `_adjacentWord` cannot cross a block (the
    block separator is not Arabic), so A3 reads the cursor's or the
    reference's own block — and walks neighbour blocks for the
    adjacent-word search — instead of copying the whole document. This
    guard replays both walks over every position of randomized
    multi-block documents (separators, Latin text, whitespace, empty
    blocks) against the whole-document reference.
    """
    rng = random.Random(97531)
    for _ in range(8):
        text = "".join(rng.choice(_Pools) for _ in range(rng.randint(1, 30)))
        widget = PyRaya()
        widget.setPlainText(text)
        widget.highlighter.setSpellCheckEnabled(False)
        for _ in range(rng.randint(0, 4)):
            kind = rng.choice([RegionType.Latin, RegionType.RomanUrdu])
            start = rng.randint(0, max(0, len(text)))
            end = rng.randint(0, len(text))
            if start < end:
                widget.setRegionType(kind, start, end)
        limit = widget.document().characterCount() - 1
        for reference in range(0, limit + 2):
            cursor = widget.textCursor()
            cursor.setPosition(min(reference, limit))
            widget.setTextCursor(cursor)
            label = f"text={text!r} reference={reference}"
            assert widget._wordUnderCursor() == _referenceWordUnderCursor(widget, reference), label
            assert widget._adjacentWord(reference, True) == _referenceAdjacentWord(
                widget, reference, True
            ), label
            assert widget._adjacentWord(reference, False) == _referenceAdjacentWord(
                widget, reference, False
            ), label


# ******************************************************************************
def testAdjacentWordInsideARunReturnsTheContainingRun(app) -> None:  # noqa: ARG001
    """The adjacent-word walk returns the containing run of the found character.

    B2 unified the word-run scan into one helper; the walk's directional
    skip (first Arabic character at or below / above the reference,
    crossing neighbour blocks) is kept, and the run it lands on is
    returned whole. A reference landing inside a run — which the
    widget's own callers never produce (an edge commit passes the
    active word's edge, a commit seed passes an anchor outside any
    run) — previously returned only the walk-direction's half-run.
    """
    text = "کلام کتاب"  # کلام at 0..3, space at 4, کتاب at 5..8
    widget = PyRaya()
    widget.highlighter.setSpellCheckEnabled(False)
    widget.setPlainText(text)
    for reference in (6, 7):
        label = f"reference={reference}"
        assert widget._adjacentWord(reference, True) == (5, 9), label
        assert widget._adjacentWord(reference, False) == (5, 9), label
    # The directional skip stays: a reference on the space or outside the
    # runs still walks to the nearest run's whole length.
    assert widget._adjacentWord(4, True) == (0, 4)
    assert widget._adjacentWord(4, False) == (5, 9)
    assert widget._adjacentWord(0, True) is None

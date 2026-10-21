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
        if highlighter._hasRegionBackground(cursor.charFormat()):
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

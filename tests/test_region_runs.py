# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Differential guard: run-based span reconstruction == per-character scan.

Phase A1 replaced the per-character ``_regionSpans`` walk (one char-format
read per character) with a format-run walk. This suite replays randomized
documents through both — the run-based reconstruction under test and an
inline per-character reference implementing the pre-A1 rule — and asserts
identical region maps, including after recolours, clears, and raw edits.
Kept for one round per plan §7, then to be retired.

The reference walk reads kinds exactly as the old code did:
``_charFormatAt(position)``'s background, mapped through the widget's
palette with :data:`~pyraya.regions.DefaultRegionKind` as the fallback.
"""

import os
import random
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from pyraya import (
    DefaultRegionKind,
    PyRaya,
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

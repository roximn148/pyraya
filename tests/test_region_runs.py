# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Run-based edge-document guard and the ruled adjacent-word contract.

Phase A1 replaced the per-character ``_regionSpans`` walk (one char-format
read per character) with a format-run walk, and Phase A2 derived the
highlighter's default-region wash from the same run map. The one-round
differential sweeps that replayed documents through both implementations —
region maps, the wash's merged layout formats, the whole-document word
walks — were retired after their round (2026-10-22) per the audit plan; the
catches they made are recorded in the audit ledger and their code is
retrievable from git history (the commit preceding this note).

What remains:

- ``testRunBasedEdgeDocuments`` pins terminator-adjacent and
  separator-boundary documents against a per-character reference walk —
  including the kind-merge rule: adjacent format runs of one kind merge
  into one span even when their observed backgrounds differ (untagged
  NoBrush text beside tagged text of the default kind is one region).
- ``testAdjacentWordInsideARunReturnsTheContainingRun`` pins B2's ruled
  whole-run return for the adjacent-word walk, including the reachable
  mid-run seed path.

The reference reads kinds exactly as the old code did: ``charFormat()``'s
background, mapped through the palette with
:data:`~pyraya.regions.DefaultRegionKind` as the fallback.
"""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication
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
    """The per-character kind read: one format read per position."""
    color = widget._charFormatAt(position).background().color()
    for kind, regionColor in widget._regionColors.items():
        if color == regionColor:
            return kind
    return DefaultRegionKind


def _referenceSpans(widget: PyRaya) -> list[TextRegion]:
    """The per-character span walk, reimplemented from its rule."""
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


def _assertSameMap(widget: PyRaya) -> None:
    """The widget's spans must equal the per-character reference walk."""
    assert widget.regions() == _referenceSpans(widget)


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
def testAdjacentWordInsideARunReturnsTheContainingRun(app) -> None:  # noqa: ARG001
    """The adjacent-word walk returns the containing run of the found character.

    B2 unified the word-run scan into one helper; the walk's directional
    skip (first Arabic character at or below / above the reference,
    crossing neighbour blocks) is kept, and the run it lands on is
    returned whole. Scenario 2 edge commits pass the active word's
    edge, which a maximal run's bounds guarantee is outside any run, so
    the whole-run return is byte-identical there (review-checked). A
    reference landing inside a run is reachable through one path — a
    scenario-1 seed anchored mid-run: the ASCII typing gate is
    region-kind-only, so its edge commit now lands on the run's facing
    edge instead of staying put (pinned end-to-end by
    ``testEdgeCommitFromMidRunSeedLandsOnTheRunEdge``); previously only
    the walk-direction's half-run was returned.
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

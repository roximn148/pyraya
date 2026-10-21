# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Latency harness: measured costs of the widget's hot paths.

Opt-in: the suite runs only when the ``PYRAYA_LATENCY`` environment
variable is ``1`` and is skipped otherwise, so the default test run
stays fast. The measured rows carry coarse budgets (Phase A4): generous
multiples of the measured post-A3 costs, sized to catch a return to
per-character work — the 400 ms-class regions scan, the 500 ms-class
menu, the per-character wash, whole-document copies on the word path —
while absorbing machine variance; see :func:`_checked`.

The fixture texts are the committed reference texts under
``tests/fixtures/``; the harness repeats and trims each reference to
its exact character target (4 000 / 50 000 / 200 000) so measured costs
scale with real document sizes. The 4 k target is forced to a single
paragraph; the larger targets keep the references' own paragraphing.
The measured paths (plan §3, A0):

1. keypresses into a 4 k paragraph — a typing press at the document
   end (the prepare-time sync leaves the overlay active there, so the
   gate lets the key through and it edits), the same press with the
   highlighter detached as the attribution sibling, a mid-paragraph
   Arabic press (edit + re-highlight), a seed-only ASCII press (the
   gate intercepts; no edit), plus a 50 k whole-document selection
   press and a batch of block-local word-path lookups on 200 k;
2. ``rehighlight()`` over one long (4 k) block;
3. ``regions()`` and ``createPopupMenu()`` on the 50 k and 200 k
   documents (the pre-run-based spans cost anchors);
4. the roman-input overlay path: a seed keypress, the cursor-anchored
   activation, and one overlay edit keystroke, engine warmed so the
   dictionary load is out.
"""

import os
import time
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from pyraya import PyRaya
from pyraya.pyraya_widget import _isArabicChar

_LatencyEnv = "PYRAYA_LATENCY"
_FixturesDir = Path(__file__).resolve().parent / "fixtures"
_TargetChars: dict[str, int] = {
    "01-4k-para.txt": 4_000,
    "02-50k-doc.txt": 50_000,
    "03-200k-doc.txt": 200_000,
}


# ******************************************************************************
pytestmark = pytest.mark.skipif(
    os.environ.get(_LatencyEnv) != "1",
    reason=f"opt-in latency harness (set {_LatencyEnv}=1 to run)",
)


@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
def _fixture(name: str, singleParagraph: bool = False) -> str:
    """Build the exact-size fixture text from its committed reference."""
    path = _FixturesDir / name
    if not path.exists():
        pytest.skip(f"missing committed reference text: {path}")
    text = path.read_text(encoding="utf-8")
    # The 50 k reference carries one U+FEFF; Qt's setPlainText drops it,
    # which would leave the built document one character short of the
    # target. Strip it so the targets are exact document sizes.
    text = text.replace("\ufeff", "")
    if singleParagraph:
        text = " ".join(line for line in text.splitlines() if line)
    target = _TargetChars[name]
    reps = -(-target // len(text))
    return (text * reps)[:target]


def _milliseconds(call: Callable[[], object]) -> float:
    """Run ``call`` once and return its wall time in milliseconds."""
    start = time.perf_counter_ns()
    call()
    return (time.perf_counter_ns() - start) / 1_000_000


def _report(label: str, ms: float) -> None:
    """Print one measurement row."""
    print(f"{label:<64s} {ms:10.3f} ms")


def _checked(label: str, ms: float, budget: float) -> float:
    """Report a measurement and enforce its A4 budget.

    The budgets are coarse regression guards (Phase A4): generous
    multiples of the measured post-A3 costs, sized to absorb machine
    variance while catching a return to per-character work — the
    400 ms-class regions scan, the 500 ms-class menu, the per-character
    wash, whole-document copies on the word path — not to police
    millisecond-level noise.
    """
    assert ms < budget, f"{label}: {ms:.3f} ms exceeds the {budget} ms budget"
    _report(label, ms)
    return ms


def _sendKey(
    widget: QWidget,
    key: int,
    text: str = "",
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    """Send a key-press event to a widget."""
    QCoreApplication.sendEvent(
        widget,
        QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text),
    )


def _processEvents() -> None:
    """Let Qt settle layout and pending signals before a timed region."""
    QCoreApplication.processEvents()


# ******************************************************************************
def _detachHighlighter(widget: PyRaya) -> None:
    """Detach the highlighter so no wash or spell pass ever runs."""
    widget.highlighter.setDocument(None)


def _prepareWidget(text: str, detach: bool = False) -> PyRaya:
    """A shown widget with ``text`` set, cursor at the document end."""
    widget = PyRaya()
    widget.resize(900, 600)
    if detach:
        _detachHighlighter(widget)  # before setPlainText: no initial wash
    widget.setPlainText(text)
    widget.show()
    cursor = widget.textCursor()
    cursor.setPosition(widget.document().characterCount() - 1)
    widget.setTextCursor(cursor)
    widget.romanEngine()  # engine warm: dictionary load is a one-time cost
    _processEvents()
    return widget


def _keypressIntoParagraph(attribution: bool) -> float:
    """One 'k' keypress at the end of the 4 k single-paragraph fixture.

    The prepare-time sync activates the overlay over the last word — the
    document cursor rests at the run's end — so the gate does not
    intercept: the press *types* 'k' and re-highlights the block, the
    same hot path the audit's per-keystroke finding measured. The overlay
    stays active and focused afterward.
    """
    widget = _prepareWidget(_fixture("01-4k-para.txt", True), detach=attribution)
    revision = widget.document().revision()
    ms = _milliseconds(lambda: _sendKey(widget, Qt.Key.Key_K.value, "k"))
    assert widget._overlay is not None, "the overlay stays active after the press"
    assert widget.document().revision() == revision + 1, "the press must type"
    return ms


def _keypressTypingIntoParagraph() -> float:
    """One Arabic keypress into the 4 k fixture: it types and re-highlights.

    An Arabic key types straight into the document, so this row measures
    typing, block re-highlight, layout, and the overlay sync over an
    actually edited paragraph (the post-edit sync re-activates the
    overlay over the edited word).
    """
    widget = _prepareWidget(_fixture("01-4k-para.txt", True))
    before = widget.toPlainText()
    ms = _milliseconds(lambda: _sendKey(widget, Qt.Key.Key_S.value, "س"))
    assert len(widget.toPlainText()) == len(before) + 1, "the keypress must type"
    return ms


def _keypressSeedOnly() -> float:
    """One ASCII keypress that seeds the overlay without editing.

    The prepare-time sync left the overlay active at the document end, so
    the cursor first parks between two consecutive non-Arabic characters
    — a cursor on a single space would still sit at the preceding word
    run's end (accepted by ``_wordUnderCursor``) — whose move's sync
    finds no Arabic word and deactivates the overlay, then the press
    runs the gate: the overlay seeds with the typed character and the
    document revision never moves.
    """
    widget = _prepareWidget(_fixture("01-4k-para.txt", True))
    text = widget.toPlainText()
    interior = next(
        (
            index
            for index in range(2, len(text))
            if not _isArabicChar(text[index - 1]) and not _isArabicChar(text[index])
        ),
        None,
    )
    assert interior is not None, "fixture carries no double non-Arabic slot"
    cursor = widget.textCursor()
    cursor.setPosition(interior)
    widget.setTextCursor(cursor)
    assert widget._overlay is not None and not widget._overlayActive(), (
        "the cursor move deactivated the overlay"
    )
    revision = widget.document().revision()
    ms = _milliseconds(lambda: _sendKey(widget, Qt.Key.Key_K.value, "k"))
    assert widget._overlayActive(), "the press must seed the overlay"
    assert widget.document().revision() == revision, "a seed must not edit"
    return ms


def _keypressWithSelection(chars: int) -> float:
    """One 'k' keypress into a whole-document selection in a big fixture."""
    name = "02-50k-doc.txt"
    widget = _prepareWidget(_fixture(name))
    assert chars == len(widget.toPlainText())
    cursor = widget.textCursor()
    cursor.select(cursor.SelectionType.Document)
    widget.setTextCursor(cursor)
    _processEvents()
    return _milliseconds(lambda: _sendKey(widget, Qt.Key.Key_K.value, "k"))


def _wordPathBatch(chars: int) -> float:
    """Sixty-four word-path calls on the largest fixture.

    `_wordUnderCursor` and both `_adjacentWord` directions per iteration:
    A3 made them block-local (linear in the word, not the document) — a
    return to whole-document copies or per-character scans shows up as a
    batch cost in the tens of milliseconds and trips the budget.
    """
    name = "03-200k-doc.txt"
    widget = _prepareWidget(_fixture(name))
    assert chars == len(widget.toPlainText())
    limit = widget.document().characterCount() - 1
    cursor = widget.textCursor()
    cursor.setPosition(limit - 200)
    widget.setTextCursor(cursor)
    _processEvents()

    def batch() -> None:
        for _ in range(64):
            widget._wordUnderCursor()
            widget._adjacentWord(limit - 200, True)
            widget._adjacentWord(limit - 200, False)

    return _milliseconds(batch)


def testTypingKeystrokes(app) -> None:  # noqa: ARG001
    """Keypress cost with and without the highlighter, and with a selection."""
    _checked(
        "one keypress, 4 000-char paragraph (typing at the end)",
        _keypressIntoParagraph(attribution=False),
        90.0,
    )
    _checked(
        "same keypress, highlighter detached (attribution)",
        _keypressIntoParagraph(attribution=True),
        25.0,
    )
    _checked(
        "one keypress typing into 4 000 chars (edit + re-highlight)",
        _keypressTypingIntoParagraph(),
        90.0,
    )
    _checked(
        "one ASCII keypress seeding the overlay (no edit)",
        _keypressSeedOnly(),
        25.0,
    )
    _checked(
        "one keypress, 50 000-char document with selection",
        _keypressWithSelection(50_000),
        300.0,
    )
    _checked(
        "64 word-path calls on 200 000 chars (block-local word lookups)",
        _wordPathBatch(200_000),
        100.0,
    )


# ******************************************************************************
def testRehighlightLongBlock(app) -> None:  # noqa: ARG001
    """Full ``rehighlight()`` over one long 4 000-character block."""
    widget = _prepareWidget(_fixture("01-4k-para.txt", True))
    rehighlight = widget.highlighter.rehighlight
    _checked("rehighlight() over one 4 000-char block", _milliseconds(rehighlight), 100.0)


# ******************************************************************************
def _measureRegionsAndMenu(name: str) -> None:
    """Measure span reconstruction and the context-menu scan on one fixture."""
    widget = _prepareWidget(_fixture(name))
    target = _TargetChars[name]
    spanCounts: list[int] = []

    def _runRegions() -> None:
        spanCounts.append(len(widget.regions()))

    first = _milliseconds(_runRegions)
    warm = _milliseconds(_runRegions)
    budgets = {
        "02-50k-doc.txt": (500.0, 40.0, 60.0),
        "03-200k-doc.txt": (1500.0, 150.0, 150.0),
    }
    coldBudget, warmBudget, menuBudget = budgets[name]
    _checked(
        f"regions() first call — {target:,} chars ({name}, cold: lazy layout)",
        first,
        coldBudget,
    )
    _checked(
        f"regions() second call — {target:,} chars ({name}, warm scan)",
        warm,
        warmBudget,
    )
    assert len(spanCounts) == 2 and spanCounts[0] >= 1 and spanCounts[1] >= 1, (
        "spans must reconstruct"
    )
    _checked(
        f"createPopupMenu() — {target:,} chars ({name})",
        _milliseconds(widget.createPopupMenu),
        menuBudget,
    )


# ******************************************************************************
def testRegionsAndContextMenu(app) -> None:  # noqa: ARG001
    """Span reconstruction and context-menu scan on the large documents."""
    for name in ("02-50k-doc.txt", "03-200k-doc.txt"):
        _measureRegionsAndMenu(name)


# ******************************************************************************
def _firstArabicPosition(text: str) -> int:
    """The first Arabic-script character position in ``text``."""
    for index, char in enumerate(text):
        if "\u0600" <= char <= "\u06ff":
            return index
    raise AssertionError("fixture has no Arabic-script word runs")


def testOverlayPath(app) -> None:  # noqa: ARG001
    """Overlay seed keypress, word-anchored activation, one overlay edit."""
    text = _fixture("01-4k-para.txt", True)
    widget = _prepareWidget(text)
    seed = _keypressSeedOnly()
    _checked("overlay seed keypress (gate intercepts, no edit)", seed, 25.0)

    cursor = widget.textCursor()
    cursor.setPosition(_firstArabicPosition(text) + 1)  # inside a word
    widget.setTextCursor(cursor)
    _processEvents()
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible(), "cursor on a word activates"
    lineEdit = overlay.lineEdit()

    # Warm one overlay keystroke and undo it so suggestions are settled.
    _sendKey(lineEdit, Qt.Key.Key_A.value, "a")
    _sendKey(lineEdit, Qt.Key.Key_Backspace.value, "")
    before = lineEdit.text()

    single = _milliseconds(lambda: _sendKey(lineEdit, Qt.Key.Key_A.value, "a"))
    assert lineEdit.text() != before, "the overlay keystroke must edit the text"
    _checked("one overlay keystroke (refresh + suggestions + re-place)", single, 10.0)

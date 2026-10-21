# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Latency harness: measured costs of the widget's hot paths.

Opt-in: the suite runs only when the ``PYRAYA_LATENCY`` environment
variable is ``1`` and is skipped otherwise, so the default test run
stays fast. The measurements carry no thresholds — Phase A4 turns the
baseline numbers into regression budgets.

The fixture texts are the committed reference texts under
``tests/fixtures/``; the harness repeats and trims each reference to
its exact character target (4 000 / 50 000 / 200 000) so measured costs
scale with real document sizes. The 4 k target is forced to a single
paragraph; the larger targets keep the references' own paragraphing.
The four measured paths (plan §3, A0):

1. one keypress into a 4 k paragraph — with the highlighter attached
   and, as an attribution sibling, with the highlighter detached; plus
   a keypress into a 50 k document with a whole-document selection;
2. ``rehighlight()`` over one long (4 k) block;
3. ``regions()`` and ``createPopupMenu()`` on the 50 k and 200 k
   documents (the pre-run-based spans cost anchors);
4. the roman-input overlay path: an activation keypress and one
   overlay edit keystroke, engine warmed so dictionary load is out.
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
    """One 'k' keypress at the end of the 4 k single-paragraph fixture."""
    widget = _prepareWidget(_fixture("01-4k-para.txt", True), detach=attribution)
    ms = _milliseconds(lambda: _sendKey(widget, Qt.Key.Key_K.value, "k"))
    assert widget._overlay is not None, "the 'k' press must seed the overlay"
    assert widget.toPlainText().endswith("k"), "the attributed press still types"
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


def testTypingKeystrokes(app) -> None:  # noqa: ARG001
    """Keypress cost with and without the highlighter, and with a selection."""
    _report(
        "one keypress, 4 000-char paragraph (assisted path)",
        _keypressIntoParagraph(attribution=False),
    )
    _report(
        "same keypress, highlighter detached (attribution)",
        _keypressIntoParagraph(attribution=True),
    )
    _report(
        "one keypress, 50 000-char document with selection",
        _keypressWithSelection(50_000),
    )


# ******************************************************************************
def testRehighlightLongBlock(app) -> None:  # noqa: ARG001
    """Full ``rehighlight()`` over one long 4 000-character block."""
    widget = _prepareWidget(_fixture("01-4k-para.txt", True))
    rehighlight = widget.highlighter.rehighlight
    _report("rehighlight() over one 4 000-char block", _milliseconds(rehighlight))


# ******************************************************************************
def _measureRegionsAndMenu(name: str) -> None:
    """Measure span reconstruction and the context-menu scan on one fixture."""
    widget = _prepareWidget(_fixture(name))
    target = _TargetChars[name]
    spanCount = 0

    def _runRegions() -> None:
        nonlocal spanCount
        spanCount = len(widget.regions())

    _report(f"regions() — {target:,} chars ({name})", _milliseconds(_runRegions))
    assert spanCount >= 1, "spans must reconstruct"
    _report(
        f"createPopupMenu() — {target:,} chars ({name})",
        _milliseconds(widget.createPopupMenu),
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
    """Overlay activation keypress and one overlay edit keystroke."""
    text = _fixture("01-4k-para.txt", True)
    widget = _prepareWidget(text)
    activation = _milliseconds(lambda: _sendKey(widget, Qt.Key.Key_K.value, "k"))
    _report("overlay activation (one keypress into the 4 000-char block)", activation)

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
    _report("one overlay keystroke (refresh + suggestions + re-place)", single)

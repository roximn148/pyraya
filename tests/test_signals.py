# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the widget's public state-change signals.

``assistModeChanged``, ``spellCheckChanged`` and ``dictionaryChanged`` tell a
host about *this* widget's own state changes — the dictionary is
process-wide, but notifying other instances is the host's job. Every
signal fires on an actual change only: a call that leaves the state as it
was emits nothing, so a host echoing a value back into the setter cannot
loop.

Runs headless via the offscreen Qt platform so no window is opened.
"""

import os
from collections.abc import Generator
from typing import Any

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget
from romanalfaz.engine import Vocabulary

from pyraya import PyRaya, RegionType


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
class _FakeMonotonic:
    """A controllable monotonic clock for deterministic double-tap tests."""

    def __init__(self) -> None:
        self._t = 0.0

    def __call__(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt


# ******************************************************************************
def _moveCursor(widget: PyRaya, position: int) -> None:
    """Move the widget's document cursor to a character offset."""
    cursor = widget.textCursor()
    cursor.setPosition(position)
    widget.setTextCursor(cursor)


# ******************************************************************************
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


# ******************************************************************************
def testAssistModeChangedFiresOnSetterFlip(app: QApplication) -> None:
    """Each real assist-mode flip through the setter emits its new value once."""
    widget = PyRaya()
    events: list[Any] = []
    widget.assistModeChanged.connect(events.append)
    widget.setAssistEnabled(False)
    assert events == [False]
    widget.setAssistEnabled(True)
    assert events == [False, True]


# ******************************************************************************
def testAssistModeChangedSilentOnUnchangedSetter(app: QApplication) -> None:
    """A setter call that leaves the mode as it was emits nothing.

    Assist mode starts on, so ``True`` is a no-op; the second ``False``
    repeats the first.
    """
    widget = PyRaya()
    events: list[Any] = []
    widget.assistModeChanged.connect(events.append)
    widget.setAssistEnabled(True)
    widget.setAssistEnabled(False)
    widget.setAssistEnabled(False)
    assert events == [False]


# ******************************************************************************
def testEnablingRomanInputResetsAssistAndNotifies(app: QApplication) -> None:
    """The feature's re-enable resets assist mode off to on and emits it."""
    widget = PyRaya()
    widget.setAssistEnabled(False)
    events: list[Any] = []
    widget.assistModeChanged.connect(events.append)
    widget.setRomanInputEnabled(True)
    assert widget.isAssistEnabled() is True
    assert events == [True]


# ******************************************************************************
def testDisablingRomanInputLeavesAssistSilent(app: QApplication) -> None:
    """Disabling the feature writes only the feature flag, not the mode."""
    widget = PyRaya()
    events: list[Any] = []
    widget.assistModeChanged.connect(events.append)
    widget.setRomanInputEnabled(False)
    assert widget.isAssistEnabled() is True
    assert events == []


# ******************************************************************************
def testCtrlEscInDocumentFiresAssistModeChanged(app: QApplication) -> None:
    """Ctrl+Esc in the document turns assist mode off and announces it."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    _moveCursor(widget, 1)
    events: list[Any] = []
    widget.assistModeChanged.connect(events.append)
    _sendKey(widget, Qt.Key.Key_Escape, modifiers=Qt.KeyboardModifier.ControlModifier)
    assert widget.isAssistEnabled() is False
    assert events == [False]


# ******************************************************************************
def testCtrlSpaceFiresAssistModeChanged(app: QApplication) -> None:
    """Ctrl+Space re-enters assist mode from off and announces the flip."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    _moveCursor(widget, 1)
    widget.setAssistEnabled(False)
    events: list[Any] = []
    widget.assistModeChanged.connect(events.append)
    _sendKey(widget, Qt.Key.Key_Space, modifiers=Qt.KeyboardModifier.ControlModifier)
    assert widget.isAssistEnabled() is True
    assert events == [True]


# ******************************************************************************
def testCtrlSpaceOnActiveAssistModeStaysSilent(app: QApplication) -> None:
    """Ctrl+Space with assist already on changes no state, so it emits nothing."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    _moveCursor(widget, 1)
    events: list[Any] = []
    widget.assistModeChanged.connect(events.append)
    _sendKey(widget, Qt.Key.Key_Space, modifiers=Qt.KeyboardModifier.ControlModifier)
    assert widget.isAssistEnabled() is True
    assert events == []


# ******************************************************************************
def testDoubleEscFiresAssistModeChangedOnce(app: QApplication, monkeypatch) -> None:
    """The double tap emits once, on the second Esc; the first stays silent."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello world")
    _moveCursor(widget, 1)
    clock = _FakeMonotonic()
    monkeypatch.setattr("pyraya.pyraya_widget.monotonic", clock)
    events: list[Any] = []
    widget.assistModeChanged.connect(events.append)
    _sendKey(widget, Qt.Key.Key_Escape)  # first tap, at t=0.0
    assert events == []
    clock.advance(0.1)  # within the 0.3 s interval
    _sendKey(widget, Qt.Key.Key_Escape)  # second tap, at t=0.1
    assert widget.isAssistEnabled() is False
    assert events == [False]


# ******************************************************************************
def testOverlayCtrlEscFiresAssistModeChanged(app: QApplication) -> None:
    """Ctrl+Esc on the active overlay turns assist mode off and announces it."""
    widget = PyRaya()
    widget.show()
    widget.setPlainText("hello خوش world دوست")
    widget.setRegionType(RegionType.RomanUrdu, 6, 9)
    _moveCursor(widget, 7)
    overlay = widget._overlay
    assert overlay is not None and overlay.isVisible()
    events: list[Any] = []
    widget.assistModeChanged.connect(events.append)
    _sendKey(overlay.lineEdit(), Qt.Key.Key_Escape, modifiers=Qt.KeyboardModifier.ControlModifier)
    assert widget.isAssistEnabled() is False
    assert events == [False]
    assert widget._overlay is None or not widget._overlay.isVisible()


# ******************************************************************************
def testSpellCheckChangedFiresOnFlip(app: QApplication) -> None:
    """Each spell-check switch flip emits its new value once."""
    widget = PyRaya()
    events: list[Any] = []
    widget.spellCheckChanged.connect(events.append)
    widget.setSpellCheckEnabled(False)
    assert events == [False]
    widget.setSpellCheckEnabled(True)
    assert events == [False, True]


# ******************************************************************************
def testSpellCheckChangedSilentOnUnchangedSetter(app: QApplication) -> None:
    """A spell-check switch call that changes nothing emits nothing."""
    widget = PyRaya()
    events: list[Any] = []
    widget.spellCheckChanged.connect(events.append)
    widget.setSpellCheckEnabled(True)
    widget.setSpellCheckEnabled(False)
    widget.setSpellCheckEnabled(False)
    assert events == [False]


# ******************************************************************************
def testDictionaryChangedCarriesTheInstalledVocabulary(app: QApplication) -> None:
    """A swap announces the Vocabulary now in effect — the shared instance."""
    widget = PyRaya()
    vocabulary = Vocabulary()
    vocabulary.add("کتاب", isCompleted=True)
    events: list[Any] = []
    widget.dictionaryChanged.connect(events.append)
    widget.setLocalDictionary(vocabulary)
    assert len(events) == 1
    assert events[0] is vocabulary
    assert events[0] is widget.localDictionary()


# ******************************************************************************
def testLearnNotifiesDictionaryChangeBeforeWordAdd(app: QApplication) -> None:
    """Learning announces the dictionary first, then the specific word."""
    widget = PyRaya()
    events: list[tuple[str, Any]] = []
    widget.dictionaryChanged.connect(lambda vocabulary: events.append(("dictionary", vocabulary)))
    widget.wordAdded.connect(lambda word: events.append(("word", word)))
    widget._learnWord("خلمق")
    assert [name for name, _ in events] == ["dictionary", "word"]
    assert events[0][1] is widget.localDictionary()
    assert events[1][1] == "خلمق"


# ******************************************************************************
def testDirectVocabularyMutationEmitsNothing(app: QApplication) -> None:
    """A host mutating localDictionary() directly is not announced: the
    widget does not proxy Vocabulary mutations."""
    widget = PyRaya()
    events: list[Any] = []
    widget.dictionaryChanged.connect(events.append)
    widget.localDictionary().add("کتاب", isCompleted=True)
    assert events == []

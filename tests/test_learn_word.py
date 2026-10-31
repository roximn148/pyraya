# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the application-wide shared engine holder.

Runs headless via the offscreen Qt platform so no window is opened.
"""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication
from romanalfaz.engine import Vocabulary

from pyraya import PyRaya
from pyraya.roman_input import RomanInputEngine, _sharedEngine


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
def testReplaceVocabularyInvalidatesCachedEngine(app: QApplication) -> None:
    """replaceVocabulary discards the cached engine and attaches the new Vocabulary."""
    engine_before = _sharedEngine.engine()
    newVocabulary = Vocabulary()
    _sharedEngine.replaceVocabulary(newVocabulary)
    engine_after = _sharedEngine.engine()
    assert engine_after is not engine_before
    # The new engine attaches the new Vocabulary, not the old one.
    assert engine_after._localVocabulary is newVocabulary
    assert engine_before._localVocabulary is not newVocabulary
    assert _sharedEngine.vocabulary is newVocabulary


# ******************************************************************************
def testResetRestoresFreshState(app: QApplication) -> None:
    """reset restores a fresh empty Vocabulary and discards the cached engine."""
    _sharedEngine.engine()
    _sharedEngine.reset()
    assert dict(_sharedEngine.vocabulary.counter) == {}
    assert _sharedEngine._engine is None


# ******************************************************************************
def testSharedVocabularyIsApplicationWide(app: QApplication) -> None:
    """Every widget borrows the same application-wide shared Vocabulary."""
    first = PyRaya()
    second = PyRaya()
    assert first.localDictionary() is second.localDictionary()
    word = "خلمق"
    first.localDictionary().add(word, isCompleted=True)
    assert second.localDictionary().counter[word] == 1


# ******************************************************************************
def testOneLearnTriggersOneNotification(app: QApplication) -> None:
    """One Vocabulary mutation triggers exactly one change callback."""
    widget = PyRaya()
    assert widget.localDictionary() is _sharedEngine.vocabulary
    notifications = 0

    def observe() -> None:
        nonlocal notifications
        notifications += 1

    callbacks = _sharedEngine.vocabulary.onChangeCallbacks
    callbacks.append(observe)
    try:
        word = "خلمق"
        widget.localDictionary().add(word, isCompleted=True)
    finally:
        callbacks.remove(observe)
    assert notifications == 1
    assert word in widget.localDictionary().completed


# ******************************************************************************
def testSharedEngineIsCreatedOnce(app: QApplication) -> None:
    """Both widgets borrow one lazily-created shared engine."""
    widget = PyRaya()
    other = PyRaya()
    assert _sharedEngine._engine is None
    assert widget.romanEngine() is other.romanEngine()
    assert _sharedEngine._engine is not None


# ******************************************************************************
def testLearnRomanWordMappabilityGate(app: QApplication) -> None:
    """An unmappable word raises AssertionError and mutates nothing."""
    vocabulary = Vocabulary()
    engine = RomanInputEngine(localVocabulary=vocabulary)
    notifications = 0

    def observe() -> None:
        nonlocal notifications
        notifications += 1

    callbacks = vocabulary.onChangeCallbacks
    callbacks.append(observe)
    try:
        with pytest.raises(AssertionError):
            engine.learnRomanWord("کA")
    finally:
        callbacks.remove(observe)
    assert dict(vocabulary.counter) == {}
    assert notifications == 0


# ******************************************************************************
def testLearnRomanWordSuccess(app: QApplication) -> None:
    """A mappable word is learned with one add(isCompleted=True) mutation."""
    vocabulary = Vocabulary()
    engine = RomanInputEngine(localVocabulary=vocabulary)
    notifications = 0

    def observe() -> None:
        nonlocal notifications
        notifications += 1

    callbacks = vocabulary.onChangeCallbacks
    callbacks.append(observe)
    try:
        result = engine.learnRomanWord("خلمق")
    finally:
        callbacks.remove(observe)
    assert result == "خلمق"
    assert dict(vocabulary.counter) == {"خلمق": 1}
    assert "خلمق" in vocabulary.completed
    assert notifications == 1
    assert vocabulary.isModified() is True


# ******************************************************************************
def testLearnRomanWordIdempotentRetry(app: QApplication) -> None:
    """A second learn increments the count and never duplicates the entry."""
    vocabulary = Vocabulary()
    engine = RomanInputEngine(localVocabulary=vocabulary)
    notifications = 0

    def observe() -> None:
        nonlocal notifications
        notifications += 1

    callbacks = vocabulary.onChangeCallbacks
    callbacks.append(observe)
    try:
        engine.learnRomanWord("خلمق")
        engine.learnRomanWord("خلمق")
    finally:
        callbacks.remove(observe)
    assert dict(vocabulary.counter) == {"خلمق": 2}
    assert len(vocabulary.counter) == 1
    assert notifications == 2


# ******************************************************************************
def testLearnRomanWordRequiresVocabulary(app: QApplication) -> None:
    """A bare engine (no localVocabulary) raises AssertionError."""
    engine = RomanInputEngine()
    with pytest.raises(AssertionError):
        engine.learnRomanWord("خلمق")

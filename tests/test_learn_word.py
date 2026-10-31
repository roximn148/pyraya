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

from pyraya.roman_input import _sharedEngine


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

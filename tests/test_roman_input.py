# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the roman-input overlay subsystem.

Runs headless via the offscreen Qt platform so no window is opened.
"""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication
from romanalfaz import DictionaryNotFoundError
from romanalfaz.engine import Vocabulary

from pyraya.roman_input import RomanInputEngine

# Verified zero-match roman strings (no suggestions at distance 0..2).
ZERO_MATCH_WORDS = ["xqwzrty", "qzxv", "kzqwxv", "zxrqvz", "qwzxq"]


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
@pytest.fixture()
def engine() -> RomanInputEngine:
    """Provide an available RomanInputEngine (cold loads the default wordlist)."""
    return RomanInputEngine()


# ******************************************************************************
def testRomanizeArabicKnownWords(engine: RomanInputEngine) -> None:
    """romanizeArabic lowercases the encoded roman for known words."""
    assert engine.romanizeArabic("خوش") == "khosh"
    assert engine.romanizeArabic("میری") == "myry"
    assert engine.romanizeArabic("دوست") == "dost"


# ******************************************************************************
def testSuggestTierOrderAndDedup(engine: RomanInputEngine) -> None:
    """suggest merges tiers in order and globally dedupes by Arabic word."""
    exact = engine.suggest("khosh")
    assert len(exact) > 0
    assert exact[0].arabic == "خوش"  # exact tier leads
    seen = set()
    for suggestion in exact:
        assert suggestion.arabic not in seen
        seen.add(suggestion.arabic)

    d1 = engine.suggest("khos")
    assert len(d1) > 0


# ******************************************************************************
def testSuggestCap(engine: RomanInputEngine) -> None:
    """suggest caps the merged list at maxSuggestions."""
    assert len(engine.suggest("khosh")) <= 10
    strict = RomanInputEngine(maxSuggestions=3)
    assert len(strict.suggest("khosh")) <= 3


# ******************************************************************************
def testSuggestNoMatches(engine: RomanInputEngine) -> None:
    """suggest returns an empty list for words with no matches."""
    for word in ZERO_MATCH_WORDS:
        assert engine.suggest(word) == []


# ******************************************************************************
def testSuggestTiers(engine: RomanInputEngine) -> None:
    """suggestTiers tags each suggestion with its tier; earlier tier wins dedup."""
    tiers = engine.suggestTiers("khosh")
    assert len(tiers) > 0
    assert tiers[0][1] == 0
    top = tiers[0][0]
    assert top.arabic == "خوش"

    d1 = engine.suggestTiers("khos")
    assert len(d1) > 0
    assert all(tier == 1 for _, tier in d1)
    seen = set()
    for suggestion, _ in d1:
        assert suggestion.arabic not in seen
        seen.add(suggestion.arabic)


# ******************************************************************************
def testSuggestDistanceConfig(engine: RomanInputEngine) -> None:
    """The distance parameter is passed through to RomanAlfaz.suggest."""
    d1 = RomanInputEngine(distance=1)
    assert len(d1.suggest("khosh")) > 0  # exact tier still found at distance 1


# ******************************************************************************
def testLearnRomanWordNoOp(engine: RomanInputEngine) -> None:
    """learnRomanWord returns the same word as-is for this session."""
    for word in ZERO_MATCH_WORDS:
        assert engine.learnRomanWord(word) == word
    assert engine.learnRomanWord("") == ""


# ******************************************************************************
def testEngineUnavailable(monkeypatch) -> None:
    """A DictionaryNotFoundError yields an unavailable, non-crashing engine."""

    class _Missing:
        def __init__(self) -> None:
            raise DictionaryNotFoundError("missing")

    monkeypatch.setattr("pyraya.roman_input.RomanAlfaz", _Missing)
    engine = RomanInputEngine()
    assert engine.available is False
    assert engine.suggest("khosh") == []
    assert engine.suggestTiers("khosh") == []
    assert engine.learnRomanWord("xqwzrty") == "xqwzrty"


# ******************************************************************************
def testAddVocabularyAttached(app: QApplication) -> None:
    """The local vocabulary is attached alongside the default wordlist."""
    local = Vocabulary()
    engine = RomanInputEngine(local)
    assert engine.available is True
    assert engine.suggest("khosh")[0].arabic == "خوش"

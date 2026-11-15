# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Tests for the gutter (line-number strip)."""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from pyraya.gutter import DigitSet, formatLineNumber


# ******************************************************************************
@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


# ******************************************************************************
def testFormatLineNumberEastern(app: QApplication) -> None:
    """Eastern digits: 0-9 map to Eastern Arabic-Indic."""
    assert formatLineNumber(0, DigitSet.Eastern) == "۰"
    assert formatLineNumber(1, DigitSet.Eastern) == "۱"
    assert formatLineNumber(12, DigitSet.Eastern) == "۱۲"
    assert formatLineNumber(999, DigitSet.Eastern) == "۹۹۹"
    assert formatLineNumber(1000, DigitSet.Eastern) == "۱۰۰۰"


# ******************************************************************************
def testFormatLineNumberWestern(app: QApplication) -> None:
    """Western digits: identity (no substitution)."""
    assert formatLineNumber(0, DigitSet.Western) == "0"
    assert formatLineNumber(42, DigitSet.Western) == "42"
    assert formatLineNumber(1000, DigitSet.Western) == "1000"


# ******************************************************************************
def testDigitSetIsClosedIntEnum(app: QApplication) -> None:
    """DigitSet is a closed IntEnum with exactly two members."""
    assert list(DigitSet) == [DigitSet.Western, DigitSet.Eastern]
    assert int(DigitSet.Western) == 0
    assert int(DigitSet.Eastern) == 1
    assert isinstance(DigitSet.Western, int)

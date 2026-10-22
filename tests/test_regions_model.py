# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Region-model contract tests.

Kinds are stored as a custom integer property on the document's character
formats and resolved in two steps: a stored tag wins (even when it equals the
seed — tags record intent), untagged characters take the widget's seed. These
tests pin the closed enum, the property id, the read-only module seed, the
resolution function, and the view-only palette.

Runs headless via the offscreen Qt platform so no window is opened.
"""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QTextCharFormat, QTextFormat
from PySide6.QtWidgets import QApplication

from pyraya import (
    RegionColors,
    RegionKindProperty,
    RegionType,
    SeedRegionKind,
    resolveRegionKind,
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
def testClosedEnum(app: QApplication) -> None:  # noqa: ARG001
    """Region kinds are exactly the two documented members."""
    assert set(RegionType) == {RegionType.Native, RegionType.RomanUrdu}


# ******************************************************************************
def testOneBasedValues(app: QApplication) -> None:  # noqa: ARG001
    """Values are one-based: intProperty's unset sentinel is 0, so a kind of
    0 can never be stored — 0 means "no stored tag"."""
    assert RegionType.Native == 1
    assert RegionType.RomanUrdu == 2


# ******************************************************************************
def testPropertyId(app: QApplication) -> None:  # noqa: ARG001
    """The kind property lives on the first custom property slot."""
    assert RegionKindProperty == int(QTextFormat.Property.UserProperty) + 1


# ******************************************************************************
def testSeedIsReadOnlyModuleValue(app: QApplication) -> None:  # noqa: ARG001
    """The module-level seed is the RomanUrdu member; widgets copy it at
    construction and keep it read-only afterwards."""
    assert SeedRegionKind is RegionType.RomanUrdu


# ******************************************************************************
def testResolveRegionKindUnstoredGivesSeed(app: QApplication) -> None:  # noqa: ARG001
    """A format without a stored kind resolves to the seed."""
    assert resolveRegionKind(QTextCharFormat(), RegionType.Native) is RegionType.Native


# ******************************************************************************
def testStoredTagWinsOverSeedEvenWhenEqual(app: QApplication) -> None:  # noqa: ARG001
    """A stored tag always wins, even when it equals the seed: tags record
    intent, resolution is by lookup, and redundant tags are not answered
    from the seed."""
    fmt = QTextCharFormat()
    fmt.setProperty(RegionKindProperty, int(RegionType.RomanUrdu))
    assert resolveRegionKind(fmt, RegionType.RomanUrdu) is RegionType.RomanUrdu


# ******************************************************************************
def testStoredNativeWinsOverRomanSeed(app: QApplication) -> None:  # noqa: ARG001
    """A stored Native tag resolves Native even under a RomanUrdu seed."""
    fmt = QTextCharFormat()
    fmt.setProperty(RegionKindProperty, int(RegionType.Native))
    assert resolveRegionKind(fmt, RegionType.RomanUrdu) is RegionType.Native


# ******************************************************************************
def testForeignIntFallsBackToSeed(app: QApplication) -> None:  # noqa: ARG001
    """Defensive: a value outside the closed enum falls back to the seed."""
    fmt = QTextCharFormat()
    fmt.setProperty(RegionKindProperty, 7)
    assert resolveRegionKind(fmt, RegionType.Native) is RegionType.Native


# ******************************************************************************
def testPaletteDefaultsViewOnly(app: QApplication) -> None:  # noqa: ARG001
    """The palette is view-only: it colours the kinds that have a tint and
    never feeds back into identity. Native is colourless."""
    assert set(RegionColors) == {RegionType.RomanUrdu}
    roman = RegionColors[RegionType.RomanUrdu]
    assert 0 < roman.alpha() < 255


# ******************************************************************************
def testSeedRegionKindIsRomanUrdu(app: QApplication) -> None:  # noqa: ARG001
    """SeedRegionKind names a RegionType member."""
    assert SeedRegionKind in set(RegionType)
    assert SeedRegionKind is RegionType.RomanUrdu

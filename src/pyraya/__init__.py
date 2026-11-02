# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""PyRaya: a reusable, self-contained Qt (PySide6) text editor widget for Urdu.

Drop-in component for Urdu/Nastaliq text in Qt applications — currently PySide6 only.
"""

import sys

from PySide6.QtWidgets import QApplication
from romanalfaz.engine import Suggestion

from .pyraya_widget import (
    DefaultFontSize,
    EscDoubleTapInterval,
    PyRaya,
    PyRayaFonts,
    PyRayaHighlighter,
    SpellCheckUnderlineColor,
)
from .regions import (
    RegionColors,
    RegionKindProperty,
    RegionSubstitutions,
    RegionType,
    SeedRegionKind,
    TextRegion,
    resolveRegionKind,
    substituteChar,
    substituteText,
)
from .roman_input import (
    AddWordDialog,
    ArabicScriptRanges,
    ArabicScriptSeparators,
    ArabicScriptWordChars,
    MaxVisibleRows,
    OverlayLayoutSpacing,
    RomanInputEngine,
    RomanLineEdit,
    RomanOverlay,
    SuggestionList,
    SuggestionListMargin,
)

__all__ = [
    "PyRaya",
    "PyRayaHighlighter",
    "PyRayaFonts",
    "DefaultFontSize",
    "EscDoubleTapInterval",
    "RegionColors",
    "RegionType",
    "TextRegion",
    "SeedRegionKind",
    "RegionKindProperty",
    "RegionSubstitutions",
    "resolveRegionKind",
    "substituteChar",
    "substituteText",
    "RomanInputEngine",
    "RomanOverlay",
    "ArabicScriptRanges",
    "ArabicScriptSeparators",
    "ArabicScriptWordChars",
    "SpellCheckUnderlineColor",
    "Suggestion",
    "SuggestionList",
    "RomanLineEdit",
    "MaxVisibleRows",
    "OverlayLayoutSpacing",
    "SuggestionListMargin",
    "AddWordDialog",
    "main",
]


# ******************************************************************************
def main() -> None:
    """Run the PyRaya demo application.

    Creates a :class:`QApplication`, shows a top-level :class:`PyRaya` widget,
    and enters the Qt event loop.
    """
    app = QApplication(sys.argv)
    editor = PyRaya()
    editor.setFontSize(24)
    editor.show()
    sys.exit(app.exec())


# ******************************************************************************
if __name__ == "__main__":
    main()


# ******************************************************************************

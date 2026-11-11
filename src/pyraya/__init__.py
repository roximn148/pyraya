# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""PyRaya: a reusable, self-contained Qt (PySide6) text editor widget for Urdu.

Drop-in component for Urdu/Nastaliq text in Qt applications — currently PySide6 only.
"""

import sys

from PySide6.QtGui import QColor, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import QApplication
from romanalfaz.engine import Suggestion

from .pyraya_widget import (
    DefaultFontSize,
    EscDoubleTapInterval,
    PyRaya,
    PyRayaFonts,
    PyRayaHighlighter,
    SpellCheckUnderlineColor,
    wordRuns,
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
    "wordRuns",
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
def _darkDemoPalette() -> QPalette:
    """The standard Fusion dark palette for the demo's light/dark toggle."""
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Window, QColor(0x31, 0x31, 0x31))
    dark.setColor(QPalette.ColorRole.WindowText, QColor(0xDF, 0xDF, 0xDF))
    dark.setColor(QPalette.ColorRole.Base, QColor(0x23, 0x23, 0x23))
    dark.setColor(QPalette.ColorRole.AlternateBase, QColor(0x2C, 0x2C, 0x2C))
    dark.setColor(QPalette.ColorRole.Text, QColor(0xDF, 0xDF, 0xDF))
    dark.setColor(QPalette.ColorRole.Button, QColor(0x31, 0x31, 0x31))
    dark.setColor(QPalette.ColorRole.ButtonText, QColor(0xDF, 0xDF, 0xDF))
    dark.setColor(QPalette.ColorRole.Highlight, QColor(0x29, 0x7D, 0xC6))
    dark.setColor(QPalette.ColorRole.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
    return dark


# ******************************************************************************
def main() -> None:
    """Run the PyRaya demo application.

    Creates a :class:`QApplication`, shows a top-level :class:`PyRaya`
    widget, and enters the Qt event loop. Ctrl+D toggles the light and
    dark palettes: the widget's document and overlay colours follow the
    effective palette, so the toggle repaints them live.
    """
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    light = app.palette()
    dark = _darkDemoPalette()
    editor = PyRaya()
    editor.setFontSize(24)
    toggle = QShortcut(QKeySequence("Ctrl+D"), editor)

    def _toggleTheme() -> None:
        app.setPalette(dark if app.palette() == light else light)

    toggle.activated.connect(_toggleTheme)
    editor.show()
    sys.exit(app.exec())


# ******************************************************************************
if __name__ == "__main__":
    main()


# ******************************************************************************

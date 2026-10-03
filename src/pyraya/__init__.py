"""PyRaya: a reusable, self-contained Qt (PySide6) text editor widget for Urdu.

Drop-in component for Urdu/Nastaliq text in Qt applications — currently PySide6 only.
"""

import sys

from PySide6.QtWidgets import QApplication

from .pyraya_widget import PyRaya, PyRayaHighlighter

__all__ = ["PyRaya", "PyRayaHighlighter", "main"]


def main() -> None:
    """Run the PyRaya demo application.

    Creates a :class:`QApplication`, shows a top-level :class:`PyRaya` widget,
    and enters the Qt event loop.
    """
    app = QApplication(sys.argv)
    editor = PyRaya()
    editor.set_font_size(24)
    editor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

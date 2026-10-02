# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""PyRaya — a self-contained PySide6 (Qt) text editor widget for Urdu.

The public entry point is :class:`PyRaya`, a drop-in ``QWidget`` designed for
right-to-left (Nastaliq) Urdu text in Qt applications — currently PySide6 only.
"""

from PySide6.QtWidgets import QWidget


class PyRaya(QWidget):
    """Self-contained PySide6 text editor widget for Urdu/Nastaliq text.

    A drop-in ``QWidget`` for embedding Urdu text editing in a Qt UI.
    RTL layout, Noto typography, and spell-checking are roadmap features;
    the current alpha provides the widget shell.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the widget.

        Args:
            parent: Optional parent widget; defaults to a top-level window.
        """
        super().__init__(parent)


# ******************************************************************************

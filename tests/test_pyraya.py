"""Smoke test for the PyRaya widget.

Runs headless via the offscreen Qt platform so no window is opened.
"""

import os
from collections.abc import Generator

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from pyraya import PyRaya


@pytest.fixture()
def app() -> Generator[QCoreApplication | QApplication]:
    """Provide a single offscreen QApplication for the tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()


def test_pyraya_instantiates(app: QApplication) -> None:
    """A PyRaya widget can be created under an offscreen QApplication."""
    widget = PyRaya()
    assert isinstance(widget, PyRaya)

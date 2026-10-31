# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Test-suite fixtures.

The autouse ``shared_engine`` fixture resets the application-wide shared
engine holder around every test, so the module-level holder never leaks
state across tests (in any test module).
"""

from collections.abc import Iterator

import pytest

from pyraya.roman_input import _sharedEngine


# ******************************************************************************
@pytest.fixture(autouse=True)
def shared_engine() -> Iterator[None]:
    """Reset the shared engine holder so module state never leaks across tests."""
    _sharedEngine.reset()
    yield
    _sharedEngine.reset()

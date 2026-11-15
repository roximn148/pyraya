# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""The line-number gutter module.

The gutter is a right-edge strip of line numbers, one per document line,
rendered in Eastern or Western digits. It is off by default; the host opts
in via :meth:`PyRaya.setGutterEnabled`.

The digit conversion reuses :func:`~pyraya.regions.substituteText` from
`regions.py` rather than defining a new digit table.
"""

from enum import IntEnum

from .regions import RegionType, substituteText


# ******************************************************************************
class DigitSet(IntEnum):
    """The digit set the gutter renders line numbers in.

    A closed IntEnum mirroring :class:`~pyraya.regions.RegionType`.
    """

    Western = 0
    Eastern = 1


# ******************************************************************************
def formatLineNumber(number: int, digitSet: DigitSet) -> str:
    """Format a 1-based line number as a digit string.

    Eastern digits are produced by substituting each ASCII digit
    ``0-9`` with its Eastern Arabic-Indic equivalent via
    :func:`~pyraya.regions.substituteText` (the ``RomanUrdu`` table);
    Western digits pass through unchanged (identity).

    Args:
        number: The 1-based line number to format.
        digitSet: The digit set to render in.

    Returns:
        The formatted digit string.
    """
    text = str(number)
    if digitSet is DigitSet.Eastern:
        return substituteText(text, RegionType.RomanUrdu)
    return text

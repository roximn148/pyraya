# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Bracket and quote pairs for selection enveloping.

The fixed data table behind PyRaya's selection enveloping (auto-wrap):
every candidate bracket or quotation pair — its opening and closing
marks and the characters that trigger wrapping a selection with it. The
default enabled subset covers the pairs a standard keyboard can trigger
(round/square/curly brackets and the straight quotes); the remaining
pairs are available data a host enables through
:meth:`PyRaya.setWrapPairs <pyraya.pyraya_widget.PyRaya.setWrapPairs>`.

Trigger rule: a pair's trigger characters are its own members — either
member envelopes with the whole pair — except the Urdu quote pairs,
whose keyboard twin is the straight form: ``"`` envelopes in “ ” and
``'`` in ‘ ’. When two pairs share a trigger character, the earlier
table entry wins.
"""

from dataclasses import dataclass


# ******************************************************************************
@dataclass(frozen=True)
class WrapPair:
    """A bracket or quote pair and the characters that trigger enveloping.

    Attributes:
        name: The pair's identity, as accepted by
            :meth:`PyRaya.setWrapPairs
            <pyraya.pyraya_widget.PyRaya.setWrapPairs>`.
        opening: The mark placed at the selection's start.
        closing: The mark placed at the selection's end.
        triggers: The characters that envelope a selection with this
            pair; at least one of them.
    """

    name: str
    opening: str
    closing: str
    triggers: tuple[str, ...]


# ******************************************************************************
WrapPairs: dict[str, WrapPair] = {
    pair.name: pair
    for pair in (
        WrapPair("parentheses", "(", ")", ("(", ")")),
        WrapPair("square", "[", "]", ("[", "]")),
        WrapPair("curly", "{", "}", ("{", "}")),
        WrapPair("guillemets", "\u00ab", "\u00bb", ("\u00ab", "\u00bb")),
        WrapPair("single-guillemets", "\u2039", "\u203a", ("\u2039", "\u203a", "<", ">")),
        WrapPair("angle-brackets", "\u27e8", "\u27e9", ("\u27e8", "\u27e9")),
        WrapPair("floor-brackets", "\u230a", "\u230b", ("\u230a", "\u230b")),
        WrapPair("ceiling-brackets", "\u2308", "\u2309", ("\u2308", "\u2309")),
        WrapPair("black-brackets", "\u27e6", "\u27e7", ("\u27e6", "\u27e7")),
        WrapPair("fullwidth-parentheses", "\uff08", "\uff09", ("\uff08", "\uff09")),
        WrapPair("double-quote", "\u201c", "\u201d", ('"',)),
        WrapPair("single-quote", "\u2018", "\u2019", ("'",)),
        WrapPair("low-double-quote", "\u201e", "\u201d", ("\u201e", "\u201d")),
        WrapPair("mixed-double-quote", "\u201c", "\u2033", ("\u201c", "\u2033")),
        WrapPair("low-single-quote", "\u201e", "\u2033", ("\u201e", "\u2033")),
    )
}
"""Every candidate bracket and quote pair, keyed by :attr:`WrapPair.name`."""


# ******************************************************************************
DefaultWrapPairs: frozenset[str] = frozenset(
    {"parentheses", "square", "curly", "double-quote", "single-quote"}
)
"""The pairs enabled on a fresh widget: the keyboard-reachable set."""

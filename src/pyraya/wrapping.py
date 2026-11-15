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

Mirroring: each pair carries a ``mirrored`` flag — True for the
algorithmic BiDi-mirrored pairs (brackets and guillemets, whose opening
and closing marks are as listed in every region) and False for the quote
pairs, which are not BiDi-mirrored and need manual handling per region
(for now only RomanUrdu swaps their ending assignments).
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
        mirrored: True for the algorithmic BiDi-mirrored pairs (opening and
            closing as listed in every region), False for the quote pairs
            that need manual handling per region (for now only RomanUrdu
            swaps the ending assignments).
    """

    name: str
    opening: str
    closing: str
    triggers: tuple[str, ...]
    mirrored: bool


# ******************************************************************************
WrapPairs: dict[str, WrapPair] = {
    pair.name: pair
    for pair in (
        WrapPair("parentheses", "(", ")", ("(", ")"), True),
        WrapPair("square", "[", "]", ("[", "]"), True),
        WrapPair("curly", "{", "}", ("{", "}"), True),
        WrapPair("guillemets", "\u00ab", "\u00bb", ("\u00ab", "\u00bb"), True),
        WrapPair("single-guillemets", "\u2039", "\u203a", ("\u2039", "\u203a", "<", ">"), True),
        WrapPair("angle-brackets", "\u27e8", "\u27e9", ("\u27e8", "\u27e9"), True),
        WrapPair("floor-brackets", "\u230a", "\u230b", ("\u230a", "\u230b"), True),
        WrapPair("ceiling-brackets", "\u2308", "\u2309", ("\u2308", "\u2309"), True),
        WrapPair("black-brackets", "\u27e6", "\u27e7", ("\u27e6", "\u27e7"), True),
        WrapPair("fullwidth-parentheses", "\uff08", "\uff09", ("\uff08", "\uff09"), True),
        WrapPair("double-quote", "\u201c", "\u201d", ('"',), False),
        WrapPair("single-quote", "\u2018", "\u2019", ("'",), False),
        WrapPair("low-double-quote", "\u201e", "\u201d", ("\u201e", "\u201d"), False),
        WrapPair("mixed-double-quote", "\u201c", "\u2033", ("\u201c", "\u2033"), False),
        WrapPair("low-single-quote", "\u201e", "\u2033", ("\u201e", "\u2033"), False),
    )
}
"""Every candidate bracket and quote pair, keyed by :attr:`WrapPair.name`."""


# ******************************************************************************
DefaultWrapPairs: frozenset[str] = frozenset(
    {"parentheses", "square", "curly", "double-quote", "single-quote"}
)
"""The pairs enabled on a fresh widget: the keyboard-reachable set."""

# ******************************************************************************
# Copyright (c) 2026, RoXimn. All rights reserved.
# ******************************************************************************
"""Roman-script input engine for PyRaya.

A thin, lazily-loaded wrapper around a :class:`romanalfaz.RomanAlfaz`
dictionary engine. It merges the three edit-distance tiers (exact,
edit distance 1, edit distance 2) into a single ordered, globally
deduplicated list of :class:`Suggestion` objects, romanizes Arabic-script
words into the encoded roman form the lookup consumes, and exposes
:meth:`RomanInputEngine.learnRomanWord` — a no-op for this session that
simply returns the typed word as-is, and the hook for the future learning
feature.

The engine (and its ~0.2 s cold dictionary load) is created on first
overlay activation, never during widget construction. If the default
wordlist is missing (:class:`romanalfaz.DictionaryNotFoundError`), the
engine surfaces an unavailable state rather than raising: suggestions are
empty and :meth:`RomanInputEngine.learnRomanWord` still works.
"""

from romanalfaz import DictionaryNotFoundError, RomanAlfaz
from romanalfaz.algorithm import tafseerUrduAr2Rm
from romanalfaz.engine import Suggestion, Vocabulary

__all__ = ["RomanInputEngine"]


# ******************************************************************************
class RomanInputEngine:
    """Thin wrapper around a :class:`romanalfaz.RomanAlfaz` engine.

    The default romanalfaz wordlist is loaded on construction and the
    document-local in-memory :class:`Vocabulary` is attached to it via
    :meth:`RomanAlfaz.addVocabulary` (so local mutations automatically
    recompile the lookup index). The local vocabulary is never mutated in
    this session — :meth:`learnRomanWord` is a no-op and is the hook for the
    future learning feature.

    Args:
        localVocabulary: The document-local in-memory dictionary to attach;
            ``None`` for a default-wordlist-only engine.
        distance: The maximum edit distance searched (tiers: exact,
            distance 1, …, distance ``distance``).
        maxPredictions: The per-tier candidate cap.
        maxSuggestions: The cap on the merged, deduplicated suggestion list.
    """

    def __init__(
        self,
        localVocabulary: Vocabulary | None = None,
        *,
        distance: int = 2,
        maxPredictions: int = 5,
        maxSuggestions: int = 10,
    ) -> None:
        self._localVocabulary = localVocabulary
        self._distance = distance
        self._maxPredictions = maxPredictions
        self._maxSuggestions = maxSuggestions
        self._alfaz: RomanAlfaz | None = None
        self.available = False
        try:
            alfaz = RomanAlfaz()
            if localVocabulary is not None:
                alfaz.addVocabulary(localVocabulary)
            self._alfaz = alfaz
            self.available = True
        except DictionaryNotFoundError:
            self._alfaz = None
            self.available = False

    # ==========================================================================
    def suggest(self, romanWord: str) -> list[Suggestion]:
        """Suggest Arabic-script words for a roman word.

        Merges the three edit-distance tiers in tier order, deduplicates
        globally by Arabic word (the earlier tier wins), and caps the list
        at ``maxSuggestions``.

        Args:
            romanWord: The roman-script word to look up.

        Returns:
            The ordered, deduplicated, capped suggestion list; empty when the
            engine is unavailable or nothing matches.
        """
        return [suggestion for suggestion, _ in self.suggestTiers(romanWord)]

    # ==========================================================================
    def suggestTiers(self, romanWord: str) -> list[tuple[Suggestion, int]]:
        """Suggest Arabic-script words with each suggestion's tier index.

        Like :meth:`suggest`, but returns ``(suggestion, tier)`` pairs so the
        overlay can color-code rows by edit-distance tier (0 = exact,
        1 = distance 1, 2 = distance 2) without re-deriving the distance.

        Args:
            romanWord: The roman-script word to look up.

        Returns:
            The tiered, globally deduplicated, capped list; empty when the
            engine is unavailable or nothing matches.
        """
        if self._alfaz is None:
            return []
        tierLists = self._alfaz.suggest(
            romanWord,
            distance=self._distance,
            maxPredictions=self._maxPredictions,
        )
        merged: list[tuple[Suggestion, int]] = []
        seen: set[str] = set()
        for tier, tierList in enumerate(tierLists):
            for suggestion in tierList:
                if suggestion.arabic in seen:
                    continue
                seen.add(suggestion.arabic)
                merged.append((suggestion, tier))
                if len(merged) >= self._maxSuggestions:
                    return merged
        return merged

    # ==========================================================================
    def romanizeArabic(self, arabicWord: str) -> str:
        """Romanize an Arabic-script word into the encoded roman form.

        Uses ``tafseerUrduAr2Rm`` and lowercases the result, so the form
        round-trips exactly with the romanalfaz lookup (e.g. ``خوش`` →
        ``khosh``, ``میری`` → ``myry``, ``دوست`` → ``dost``). Vowel-like
        marks derived from ی/ہ/ے are kept when present and dropped
        otherwise.

        Args:
            arabicWord: The Arabic-script word to romanize.

        Returns:
            The lowercased encoded roman.
        """
        encoded, _undef = tafseerUrduAr2Rm(arabicWord)
        return encoded.lower()

    # ==========================================================================
    def learnRomanWord(self, word: str) -> str:
        """Learn a typed roman word.

        **No-op for this session**: simply returns the same word as-is (the
        typed roman). It is the hook the placeholder (Learn) commit maps
        to; in the future it will return the Arabic-script word for the
        typed roman and update the local vocabulary, guarded by full
        mappability.

        Args:
            word: The typed roman word.

        Returns:
            The same word, unchanged.
        """
        return word

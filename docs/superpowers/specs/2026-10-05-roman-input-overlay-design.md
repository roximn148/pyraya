# PyRaya Roman-Script Overlay Input — Design Spec

- **Date:** 2026-10-05
- **Status:** Draft for review
- **Target version:** 0.1.0-alpha.4

## 1. Summary

Adds a **roman-script overlay editing subsystem** to the `PyRaya` widget. When the document
cursor is inside an Arabic-script Urdu word that belongs to a `RomanUrdu` text region, a small
**frameless, non-modal popup** appears over the word. It contains a `QLineEdit` pre-filled with
the word's roman-script equivalent (produced by `romanalfaz`) and, below it, a **suggestion
list** of Arabic-script words ranked by `romanalfaz`. All editing happens in the `QLineEdit`;
the document stays untouched until the user commits (Space, Enter, or an arrow key at a text
edge). On commit, the word span in the document is replaced with the selected Arabic word and
the overlay moves to the next/previous word, repeating the cycle. The suggestion list is
color-coded by edit-distance tier (green / orange / red hues), and when `romanalfaz` yields no
suggestion a **placeholder row** appears in place of the (empty) suggestion list; committing it
teaches the typed word to the document-local, in-memory dictionary (a `romanalfaz`
`Vocabulary`). Editing/integrating a custom romanalfaz dictionary is a **future addition** and
out of scope here — only the in-place placeholder option and its local-dictionary learning
ship now.

Overlay editing is gated to `RomanUrdu` regions only. `Latin` regions (the default, untagged
kind) have no processing mechanism. Future region types will hook their own processing the same
way.

## 2. End-to-end user flow

1. The user tags a span as Roman Urdu (existing mechanisms: context menu, `Ctrl+2`,
   `setRegionType`).
2. The cursor lands inside an Arabic-script word within that span. The overlay auto-appears
   over the word's visual rectangle: the `QLineEdit` is pre-filled with the word's romanized
   form (e.g. `خوش` → `khosh`, `میری` → `myry`), and the suggestion list is populated below it.
   The `QLineEdit` takes focus.
3. The user edits the roman text: typing, Backspace, Home/End, and Left/Right move the text
   cursor inside the `QLineEdit`. The suggestion list refreshes synchronously on every
   keystroke (lookups are < 1 ms).
4. **Up / Down** moves the highlighted suggestion (wrapping). Row 0 is highlighted by default,
   so committing the top suggestion costs no extra keys.
5. **Commit** (Space, Enter, or Right with the text cursor at the end of the text):
   - the word span in the document is replaced with the selected suggestion's Arabic word;
   - the span keeps its `RomanUrdu` tag;
   - the document cursor moves past the committed word (skipping trailing whitespace) and the
     overlay loads the next word under the cursor automatically — the cycle repeats;
   - `romanWordCommitted(arabic, roman)` is emitted.
   **Left with the text cursor at the start of the text** commits and moves the cursor back to
   the previous word (skipping leading whitespace); the overlay loads that word.
6. **Esc** cancels: the overlay hides, the document word is unchanged, focus returns to the
   document.
7. **No suggestions** for the typed text: the list shows a single placeholder row,
   `+ <typed roman> → <original arabic word>  (add to local dictionary)`. Committing it
   records the pair in the document-local vocabulary (making the typed roman a real match
   going forward) and advances the cycle exactly like a normal commit.

## 3. Region gating

- The overlay activates **only** for words fully contained in a `RomanUrdu` region span.
- Semantics of `RegionType.RomanUrdu` are updated: a span of **Arabic-script Urdu** whose
  editing is assisted by roman-script dictionary lookup (the romanalfaz overlay). The existing
  docstrings in `regions.py`, `AGENTS.md`, and `README.md` are revised accordingly.
- `Latin` regions (including all untagged text, `defaultRegionKind`) get **no** overlay
  processing.
- Region spans that mix scripts: only the maximal Arabic-script word run inside the span is
  eligible; Latin-letter runs and digits inside a `RomanUrdu` span are not words for this
  feature.
- The design treats region types as processing hooks: `RomanUrdu` is the first type with
  attached processing; the wiring is isolated so future types can attach their own.

## 4. Architecture and components

New module `src/pyraya/roman_input.py` (copyright banner per repo convention). No new
third-party dependencies (`romanalfaz` is already declared).

### 4.1 `RomanInputEngine`

Thin wrapper around `romanalfaz.RomanAlfaz`.

- **Lazy loading:** the engine (and its dictionary, ~0.2 s cold load) is created on the first
  overlay activation, never during widget construction.
- Construction: `RomanAlfaz()` (loads the default wordlist) followed by
  `addVocabulary(localVocabulary)` so the local document dictionary is attached and monitored
  (romanalfaz auto-recompiles the lookup index on every local mutation).
- Public methods:
  - `suggest(romanWord, distance=2, maxPredictions=5) -> list[Suggestion]` — calls
    `RomanAlfaz.suggest` (tiers: exact / edit-distance-1 / edit-distance-2), merges the three
    tiers in tier order, deduplicates globally by Arabic word (earlier tier wins), and caps
    the list (default cap: 10 rows).
  - `romanizeArabic(arabicWord) -> str` — lowercased encoded roman via
    `tafseerUrduAr2Rm` (e.g. `KHOSH` → `khosh`). The encoded form keeps vowel-like marks
    derived from ی/ہ/ے when present (`میری` → `myry`) and drops them otherwise (`دوست` →
    `dost`); this is the romanalfaz-native convention the lookup consumes, so it
    round-trips exactly.
  - `learnWord(arabicWord) -> bool` — adds the Arabic word to the local vocabulary
    (`Vocabulary.add(word, 1)` + `setCompleted(word, True)`); returns False (and does nothing)
    if the word is already present or is not fully mappable (`tafseerUrduAr2Rm` undef count > 0,
    which would trip `recompileLookup`'s assertion).
- Configuration parameters (constructor): `distance: int = 2`,
  `maxPredictions: int = 5` (per tier), `maxSuggestions: int = 10` (merged cap).

### 4.2 `RomanOverlay`

One small frameless, **non-modal** `QWidget` (a child of the PyRaya widget's **viewport**, so
it scrolls with the text for free). It contains, top to bottom:

- a `QLineEdit` — all editing happens here;
- the suggestion list (a lightweight row widget under the line edit).

The overlay widget and its `QLineEdit` use a right-to-left layout direction with right-aligned
text, so typed text grows leftward from the word's right edge, matching the document flow.

The suggestion list is a **passive display**: it never takes focus. Each row renders the
Arabic word in the document's font, the lowercased roman (muted), and the frequency (muted).
Rows are color-coded by tier: **green hue** = exact match, **orange hue** = edit distance 1,
**red hue** = edit distance 2; the selected row is emphasized (stronger tint + accent border).
The placeholder row (learning) renders in a distinct dashed/gray style with the label
`+ <typed> → <original arabic> (add to local dictionary)`.

The overlay emits internal signals consumed by `PyRaya`:
`committed(typedRoman: str, selected: Suggestion | None, placeholder: bool)` and
`canceled()`.

### 4.3 `PyRaya` integration

- `PyRaya.setRomanInputEnabled(enabled: bool)` — feature switch, **default False** so the
  existing drop-in behavior is unchanged.
- Activation logic in `PyRaya`:
  - on `cursorPositionChanged` / document change: find the word under the cursor (maximal
    run of U+0600–U+06FF inside a `RomanUrdu` span, fully within the span); if found and the
    overlay is inactive → activate (romanize, position over the word rect, focus the
    `QLineEdit`); if the cursor leaves the active word → deactivate (hide, refocus document).
  - on commit: perform the document edit (see §8), move the cursor per §6, and auto-load the
    next/previous word (cycle repeats) or hide the overlay.
- Public accessors:
  - `PyRaya.romanEngine() -> RomanInputEngine | None`
  - `PyRaya.localDictionary() -> Vocabulary` — the document-local in-memory
    `romanalfaz.Vocabulary` (the hook for the future custom-dictionary integration;
    `Vocabulary.save`/`Vocabulary.load` already exist for that, no integration UX ships now).
- New public signal: `PyRaya.romanWordCommitted(arabic: str, roman: str)`.

All new public symbols are re-exported from `pyraya/__init__.py` and added to `__all__`.

## 5. Suggestion pipeline

- Input: the `QLineEdit` text (any roman/Latin spelling the user types).
- `RomanInputEngine.suggest` → merged, deduplicated, capped list of `Suggestion`
  (`arabic`, `encodedRoman`, `frequency`).
- Empty overlay text → list hidden (no rows, no placeholder).
- Non-empty overlay text with **zero** matches → single placeholder row (the learning affordance,
  §2.7).
- Refresh is synchronous per keystroke; measured lookup time is < 1 ms, so no debouncing or
  background threads are needed.

## 6. Key handling (in the `QLineEdit` while the overlay is active)

| Key | Behavior |
| --- | --- |
| letters / digits / Backspace / Delete / Home / End / Left / Right inside the text | normal `QLineEdit` editing / text-cursor movement |
| **Right** with text cursor at end of text | commit selected suggestion; document cursor → past the word (skip trailing whitespace); auto-load next word |
| **Left** with text cursor at start of text | commit; document cursor → previous word (skip leading whitespace); auto-load it |
| **Space** | commit; cursor → past the word (skip trailing whitespace); auto-load next word |
| **Enter** | same as Space |
| **Up / Down** | move highlighted suggestion (wrapping); no commit |
| **Esc** | cancel: hide overlay, document unchanged, focus → document |
| **wheel** | forwarded to document scrolling |

Notes:
- Committing replaces only the original word span `[start, end)` that was active when the
  overlay loaded.
- Committing with **empty** overlay text deletes the word span; the cursor lands at the
  original span start and the overlay hides.
- Committing on the **placeholder** row: `learnWord(originalArabicWord)`, then the span is
  replaced with the original Arabic word (textually a no-op) and the cycle advances; the typed
  roman now yields a real match on subsequent lookups.
- After any commit, if the next/previous position is not a word in a `RomanUrdu` span
  (start/end of document, only whitespace left), the overlay hides and the cursor simply
  lands there.

## 7. Geometry and rendering

- **Word rectangle:** computed in viewport coordinates from
  `blockBoundingRect(cursor)` plus `positionAt(point)` hit-testing at the word's boundaries
  (verified feasible offscreen); `QFontMetrics` advance of the word is the fallback.
- **Overlay position:** the `QLineEdit` is sized to the word rect (small padding) with its
  **right edge anchored** to the word's right edge; as the typed text grows, the line edit
  resizes leftward to the new text width (font metrics of the overlay font). The suggestion
  list hangs below the line edit, right-aligned to the same edge, and its width is the max of
  the line-edit width and the widest row.
- **Edge flipping:** when the list would extend past the widget's bottom edge, it flips above
  the word; near the right edge it shifts left.
- **Scrolling/resize:** as a viewport child, the overlay scrolls with the text automatically;
  it is repositioned on document change and widget resize, and hidden when its word rect is
  fully outside the viewport.
- **Fonts:** the overlay and rows use the widget's resolved font family (with the existing
  `Noto Sans` fallback), at the widget's font size; suggested Arabic therefore previews
  exactly as it will render in the document.
- **Colors:** tier hues are subtle tints (green / orange / red families); the selected row adds
  an accent border; the placeholder row is gray with a dashed border — consistent with the
  widget's subtle region-color palette.

## 8. Document invariants and undo/redo

- The document is **never modified during overlay editing** (positioning, focus, popup repaint
  are all non-document operations).
- A commit is a **single undoable command**: `QTextCursor.insertText(arabic, fmt)` where `fmt`
  carries the `RomanUrdu` background color (`RegionColors[RegionType.RomanUrdu]`), so the
  region invariant (every character belongs to exactly one kind) holds and the region span
  survives with unchanged boundaries.
- Because region boundaries and kind are unchanged by a commit, `regionsChanged` is **not**
  emitted for a same-span commit; the normal document-change path still runs.
- No overlay operation is recorded in the undo stack; a fresh widget with the feature enabled
  performs no document work at construction (no phantom undo command).
- `characterCount() - 1` trailing-terminator guards from the existing region code are reused
  for all word-span and cursor lookups.

## 9. Edge cases

- Empty document, cursor on whitespace/punctuation/digits, cursor at the trailing terminator
  → no overlay.
- Word only partially inside a `RomanUrdu` span → no overlay (word must be fully contained).
- Original word contains unmapped characters (`tafseerUrduAr2Rm` undef > 0) → overlay still
  loads (pass-through roman) and suggestions still work, but the placeholder row is **not**
  offered (learning is refused by the engine guard).
- Latin-region words, and Latin-letter runs inside RomanUrdu spans → no overlay.
- Clicking the document while the overlay is active → overlay hides; the next cursor move
  re-activates it if inside an eligible word.
- Dictionary not yet loaded (first activation) → engine loads on demand (~0.2 s, one-time);
  the overlay activates after the engine is ready.
- The feature is inert (off by default) until `setRomanInputEnabled(True)`.

## 10. Public API

```python
class RomanInputEngine:
    def __init__(self, localVocabulary: Vocabulary | None = None, *,
                 distance: int = 2, maxPredictions: int = 5, maxSuggestions: int = 10) -> None
    def suggest(self, romanWord: str) -> list[Suggestion]
    def romanizeArabic(self, arabicWord: str) -> str
    def learnWord(self, arabicWord: str) -> bool

class RomanOverlay(QWidget):
    committed: Signal[str, object, bool]  # typedRoman, selected Suggestion | None, isPlaceholder
    canceled: Signal[]

class PyRaya:
    def setRomanInputEnabled(self, enabled: bool) -> None
    def romanEngine(self) -> RomanInputEngine | None
    def localDictionary(self) -> Vocabulary
    romanWordCommitted: Signal[str, str]
```

Re-exported from `pyraya/__init__.py`; added to `__all__`; Google-style docstrings with
reST cross-references; camelCase members per repo convention.

## 11. Testing strategy (offscreen)

New `tests/test_roman_input.py` reusing the single offscreen `app` fixture; no
`QApplication.exec()`.

- `romanizeArabic` on known words (`خوش → khosh`, `میری → myry`, `دوست → dost`).
- `suggest` ordering/dedup/cap; tier membership (exact vs d1 vs d2); no matches → empty.
- Overlay activates on an Arabic word inside a RomanUrdu region; not on whitespace, digits,
  Latin-region words, or a partially-contained word; not when the feature is disabled.
- Commit: span replaced by the selected Arabic word; region span unchanged (still RomanUrdu,
  same boundaries); single undoable edit (undo restores the original word exactly, no phantom
  commands, no ping-pong); `romanWordCommitted` emitted with correct arguments.
- Cursor advancement: Space/Enter → next word auto-loads; Left at text start → previous word
  auto-loads; start/end-of-document commits land correctly with the overlay hidden.
- Keys: Up/Down wraps selection; Esc cancels with document untouched; empty-text commit
  deletes the span.
- Learning: placeholder offered only when zero matches; committing it adds the word to
  `localDictionary()` (and `setCompleted`), and the typed roman then yields a real
  suggestion; unmapped original word → no placeholder, `learnWord` returns False.
- `localDictionary().save(tmp)` writes a SymSpell-format file and `Vocabulary.load` restores it.
- Geometry: overlay rect is non-empty and aligned to the word rect in the RTL layout
  (assert bounds/containment rather than pixel-exactness, since offscreen fonts may be
  fallbacks).

## 12. Documentation and release

- `AGENTS.md`: describe the overlay subsystem, the updated `RomanUrdu` region semantics, and
  the new gotchas (viewport-child overlay, single-command commits, learning guards).
- `README.md`: move the feature from roadmap framing into implemented status; document the
  `RomanUrdu` region semantics, the feature switch, and the local-dictionary hook.
- Version bump `0.1.0-alpha.3` → `0.1.0-alpha.4` in `pyproject.toml`, re-lock with `uv lock`,
  and update the version string in `README.md`.

## 13. Future work (out of scope for this spec)

- Custom romanalfaz dictionary editing: exporting/merging the local document dictionary into a
  custom dictionary file and any UX around it. Only the in-memory placeholder + local
  dictionary learning ships now; `Vocabulary.save`/`Vocabulary.load` are the future hooks.
- Per-type processing for additional region types (spell-check, etc.) using the same
  region-gating wiring.

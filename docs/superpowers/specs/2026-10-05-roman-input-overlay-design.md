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
the document stays untouched until the user commits. On commit, the word — and, for separator-key commits (space, Enter, or
punctuation), the typed separator character — is written to the document as a
single undoable command, and the overlay disappears; it reappears when the
cursor lands on an eligible word or when the user begins typing the next word. The suggestion
list is
color-coded by edit-distance tier (green / orange / red hues), and when `romanalfaz` yields no
suggestion a **placeholder row** appears in place of the (empty) suggestion list (in **both**
scenarios): a `+ Learn <typed roman>` option mapped to `learnRomanWord(word)`.
`learnRomanWord` is a **no-op** for this session — it simply returns the same word as-is —
and the returned word is committed to the document exactly like any normal commit. Converting
the typed word to an Arabic-script word and teaching it to the document-local, in-memory
dictionary (a `romanalfaz` `Vocabulary`) is a **future addition** and out of scope here, as
is editing/integrating a custom romanalfaz dictionary.

Two input scenarios are handled:

1. **Typing a new word** (no existing word under the cursor): the overlay shows the first
   typed character and its suggestions, and any selection can be committed — the Arabic word
   is inserted at the cursor position.
2. **An existing word under the cursor** (during keyboard/mouse navigation): the overlay
   offers roman-script editing of that word, and committing replaces the word span.

Commit is also triggered by **typed separator characters** — space, Enter (newline),
and punctuation (full stop, comma, brackets, hyphen, and the rest of the
punctuation set) — so the overlay stays least intrusive to continuous typing:
the user types a stream — word, separator, word, … — and each word commits at
its natural boundary, with the separator character written to the document
along with the word.

Overlay editing is gated to `RomanUrdu` regions only. `Latin` regions (the default, untagged
kind) have no processing mechanism. Future region types will hook their own processing the same
way.

## 2. End-to-end user flow

1. The user tags a span as Roman Urdu (existing mechanisms: context menu, `Ctrl+2`,
   `setRegionType`). With the feature enabled the overlay machinery is ready; the
   `romanalfaz` engine is lazy-loaded on first activation.

2. **Activation — existing word (scenario 2):** the cursor lands inside an Arabic-script
   word within that span (keyboard or mouse navigation). The overlay auto-appears over the
   word's visual rectangle: the `QLineEdit` is pre-filled with the word's romanized form
   (e.g. `خوش` → `khosh`, `میری` → `myry`), the suggestion list is populated below it, and
   the `QLineEdit` takes focus.

3. **Activation — new word (scenario 1):** the cursor is in the span but not on an existing
   word (between words or at an empty position). The user begins typing a roman character;
   the widget intercepts the keystroke (it does not enter the document) and the overlay
   appears with that character as its initial text and its suggestions populated.

4. The user edits the roman text: typing, Backspace, Home/End, and Left/Right move the text
   cursor inside the `QLineEdit`. The suggestion list refreshes synchronously on every
   keystroke (lookups are < 1 ms).

5. **Up / Down** moves the highlighted suggestion (wrapping). Row 0 is highlighted by default,
   so committing the top suggestion costs no extra keys.

6. **Separator-key commit** (Space, Enter, or typed punctuation): these keys are ordinary
   main-document characters — they contribute nothing to the suggestion. Committing writes
   the selected suggestion's Arabic word followed by the key's character (space, newline, or
   the punctuation mark) to the document as a single undoable command; the committed text
   keeps the `RomanUrdu` tag. The overlay disappears and focus returns to the document, with
   the cursor after the inserted character. Typing the next roman word re-activates the
   overlay (scenario 1). `romanWordCommitted(word, roman)` is emitted.

7. **Edge commit** (Left with the text cursor at the start of the text, or Right with it at
   the end): the selected suggestion is committed **without inserting a character**; the
   document cursor moves to the previous / next word (skipping whitespace). If that word is
   an eligible word in a `RomanUrdu` span the overlay reloads it (the walk repeats);
   otherwise the overlay disappears and focus returns to the document.

8. **Esc** cancels: the overlay hides, the document word is unchanged, and focus returns to
   the document.

9. **No suggestions** for the typed text — **both scenarios**: the list shows a single
   placeholder row, `+ Learn <typed roman>` (the Learn option). Committing it maps to
   `learnRomanWord(<typed roman>)` — a no-op for this session that simply returns the same
   word — and the returned word is committed exactly like a normal commit: the word span is
   replaced (scenario 2) or the word is inserted at the cursor (scenario 1), plus the
   separator character for a separator-key commit. The overlay disappears, focus returns to
   the document, and `romanWordCommitted(word, roman)` is emitted (the committed word is the
   typed roman for this session). Converting the typed word to an Arabic-script word and
   updating the dictionary is a **future addition**.

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
- Note for this session: a placeholder (Learn) commit writes the no-op `learnRomanWord`
  return value — the typed roman — into the span; once `learnRomanWord` is expanded,
  committed words will be Arabic-script.

## 4. Architecture and components

New module `src/pyraya/roman_input.py` (copyright banner per repo convention). No new
third-party dependencies (`romanalfaz` is already declared).

### 4.1 `RomanInputEngine`

Thin wrapper around `romanalfaz.RomanAlfaz`.

- **Lazy loading:** the engine (and its dictionary, ~0.2 s cold load) is created on the first
  overlay activation, never during widget construction.
- Construction: `RomanAlfaz()` (loads the default wordlist) followed by
  `addVocabulary(localVocabulary)` so the local document dictionary is attached and monitored
  (romanalfaz auto-recompiles the lookup index on every local mutation). The local
  vocabulary is never mutated in this session — `learnRomanWord` is a no-op; it is the hook
  for the future learning feature.
- Public methods:
  - `suggest(romanWord) -> list[Suggestion]` — calls `RomanAlfaz.suggest` using the
    constructor configuration (tiers: exact / edit-distance-1 / edit-distance-2), merges the
    three tiers in tier order, deduplicates globally by Arabic word (earlier tier wins), and
    caps the list (default cap: 10 rows).
  - `romanizeArabic(arabicWord) -> str` — lowercased encoded roman via
    `tafseerUrduAr2Rm` (e.g. `KHOSH` → `khosh`). The encoded form keeps vowel-like marks
    derived from ی/ہ/ے when present (`میری` → `myry`) and drops them otherwise (`دوست` →
    `dost`); this is the romanalfaz-native convention the lookup consumes, so it
    round-trips exactly.
  - `learnRomanWord(word: str) -> str` — **no-op for this session**: it simply returns the
    same word as-is (the typed roman). It is the hook the placeholder (Learn) commit maps
    to; in the future it will return the Arabic-script word for the typed roman and update
    the local vocabulary (`Vocabulary.add(word, 1)` + `setCompleted(word, True)`), guarded
    by full mappability (`tafseerUrduAr2Rm` undef count > 0 would trip
    `recompileLookup`'s assertion).
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
The placeholder row (the Learn option) renders in a distinct dashed/gray style with the
label `+ Learn <typed roman>`.

The overlay emits internal signals consumed by `PyRaya`:
`committed(typedRoman: str, selected: Suggestion | None, placeholder: bool,
separator: str)` — where `separator` is the character written to the document
alongside the committed word (space, newline, or the typed punctuation) for a
separator-key commit, and the empty string for an edge commit — and
`canceled()`.

### 4.3 `PyRaya` integration

- `PyRaya.setRomanInputEnabled(enabled: bool)` — feature switch, **default False** so the
  existing drop-in behavior is unchanged.
- Activation logic in `PyRaya`:
  - **Cursor-based (scenario 2):** on `cursorPositionChanged` / document change: find the
    word under the cursor (maximal run of U+0600–U+06FF inside a `RomanUrdu` span, fully
    within the span); if found and the overlay is inactive → activate (romanize, position
    over the word rect, focus the `QLineEdit`); if the cursor leaves the active word without
    a commit → deactivate (hide, refocus document).
  - **Keystroke-based (scenario 1):** in `keyPressEvent`, when the feature is on, the cursor
    is inside a `RomanUrdu` span, the overlay is inactive, and the key is a roman character
    (a–z, A–Z, 0–9) → intercept the key (it is **not** inserted into the document), activate
    the overlay with that character as the initial `QLineEdit` text, and focus the
    `QLineEdit`.
  - **On commit:** perform the document edit (see §8) — a separator-key commit inserts the
    committed word plus the separator character; an edge commit inserts the committed word
    alone — then either reload the adjacent word (edge commit) or hide the overlay
    (separator-key commit, or when the new cursor position is not an eligible word).
- Public accessors:
  - `PyRaya.romanEngine() -> RomanInputEngine | None`
  - `PyRaya.localDictionary() -> Vocabulary` — the document-local in-memory
    `romanalfaz.Vocabulary`, owned by the widget and passed to the engine on lazy load
    (the hook for the future `learnRomanWord` update; `Vocabulary.save`/`Vocabulary.load`
    already exist for persistence, no integration UX ships now; never mutated in this
    session).
- New public signal: `PyRaya.romanWordCommitted(word: str, roman: str)` — the word
  committed to the document (the selected Arabic word, or `learnRomanWord`'s return value
  for a placeholder commit — the typed roman for this session) and the typed roman.

All new public symbols are re-exported from `pyraya/__init__.py` and added to `__all__`.

## 5. Suggestion pipeline

- Input: the `QLineEdit` text (any roman/Latin spelling the user types).
- `RomanInputEngine.suggest` → merged, deduplicated, capped list of `Suggestion`
  (`arabic`, `encodedRoman`, `frequency`).
- Empty overlay text → list hidden (no rows, no placeholder).
- Non-empty overlay text with **zero** matches → a single placeholder row **in both
  scenarios** (the Learn option, §2.9).
- Refresh is synchronous per keystroke; measured lookup time is < 1 ms, so no debouncing or
  background threads are needed.

## 6. Key handling (in the `QLineEdit` while the overlay is active)

| Key | Behavior |
| --- | --- |
| letters / digits / Backspace / Delete / Home / End / Left / Right inside the text | normal `QLineEdit` editing / text-cursor movement |
| **Space** | **separator-key commit**: write the selected Arabic word **plus a space** to the document; overlay disappears; cursor lands after the space |
| **Enter** | **separator-key commit**: write the selected Arabic word **plus a newline** to the document; overlay disappears; cursor lands after the newline |
| **typed punctuation** (full stop, comma, brackets, hyphen, …) | **separator-key commit**: write the selected Arabic word **plus the punctuation character** to the document; overlay disappears; cursor lands after it |
| **Right** with text cursor at end of text | **edge commit**: commit the selected Arabic word **without inserting a character**; document cursor → past the word (skip trailing whitespace); reload the next word if eligible, else overlay disappears |
| **Left** with text cursor at start of text | **edge commit**: commit the selected Arabic word **without inserting a character**; document cursor → previous word (skip leading whitespace); reload if eligible, else overlay disappears |
| **Up / Down** | move highlighted suggestion (wrapping); no commit |
| **Esc** | cancel: hide overlay, document unchanged, focus → document |
| **wheel** | forwarded to document scrolling |

Notes:
- A separator-key commit inserts the separator character (space / newline / punctuation)
  into the document **together with** the Arabic word — a single undoable command; an edge
  commit inserts no character.
- Committing replaces only the original word span `[start, end)` that was active when the
  overlay loaded (scenario 2); in scenario 1 the word is **inserted** at the cursor position
  (no span is replaced).
- Committing with **empty** overlay text (scenario 2, the word was cleared): the word span is
  deleted and the separator character is inserted (edge commit inserts nothing); the cursor
  lands at the original span start and the overlay disappears.
- Committing on the **placeholder** (Learn) row: `learnRomanWord(<typed roman>)` — a no-op
  for this session, returning the same word — and the returned word is committed exactly
  like a normal commit (span replaced in scenario 2, inserted at the cursor in scenario 1,
  plus the separator character for a separator-key commit); the overlay disappears.
- After a separator-key commit the overlay does **not** follow the cursor; it reappears only
  when the user begins typing the next roman word (scenario 1) or the cursor lands on an
  eligible word (scenario 2).

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
- A commit is a **single undoable command**: select the active word's span (or select nothing
  for a new-word insertion) and `QTextCursor.insertText(text, fmt)`, where `text` is the
  committed word (the selected Arabic word, or `learnRomanWord`'s return value for a
  placeholder commit — the typed roman for this session) **plus, for separator-key commits,
  the separator character** (space / newline / punctuation), and `fmt` carries the
  `RomanUrdu` background color
  (`RegionColors[RegionType.RomanUrdu]`) — so the region invariant (every character belongs to
  exactly one kind) holds and the committed word and separator stay inside the `RomanUrdu` span.
- A text-replacing commit leaves region boundaries and kind unchanged, so `regionsChanged` is
  **not** emitted for it; the normal document-change path still runs. An empty-text commit
  (word deletion) does change the span, so `regionsChanged` **is** emitted there.

  > **Corrected 2026-10-22 (audit C-06, remediated as F-8):** the assumption above is wrong
  > for the selection-replacement path — replacing a selected *Latin* (or untagged-default)
  > span with a committed word **retags** the span to `RomanUrdu`, so a text-replacing commit
  > can change region state. The shipped contract (Q-2): `regionsChanged` is emitted **once
  > for every writing commit, unconditionally** — an edge commit (which writes nothing)
  > emits neither signal. The empty-text special case no longer exists.
- No overlay operation is recorded in the undo stack; a fresh widget with the feature enabled
  performs no document work at construction (no phantom undo command).
- `characterCount() - 1` trailing-terminator guards from the existing region code are reused
  for all word-span and cursor lookups.

## 9. Edge cases

- Empty document, cursor on whitespace/punctuation/digits, cursor at the trailing terminator
  → no overlay.
- Word only partially inside a `RomanUrdu` span → no overlay (word must be fully contained).
- Original word contains unmapped characters (`tafseerUrduAr2Rm` undef > 0) → overlay still
  loads (pass-through roman) and suggestions still work; the placeholder row is still
  offered (this session's `learnRomanWord` is a no-op and performs no mappability check;
  mappability guarding is a future `learnRomanWord` detail).
- Latin-region words, and Latin-letter runs inside RomanUrdu spans → no overlay.
- **No suggestion** for the typed word (both scenarios) → the placeholder (Learn) row is
  offered as the highlighted row; committing it (separator-key or edge) calls
  `learnRomanWord(<typed roman>)` — a no-op returning the same word — and commits that word
  to the document (inserted in scenario 1, span replaced in scenario 2, plus the separator
  character for a separator-key commit); the overlay disappears.
- Clicking the document while the overlay is active → overlay hides; the next cursor move
  re-activates it if inside an eligible word.
- Dictionary not yet loaded (first activation) → engine loads on demand (~0.2 s, one-time);
  the overlay activates after the engine is ready.
- Default wordlist unavailable (`romanalfaz.DictionaryNotFoundError`) → the engine surfaces an
  unavailable state; the overlay offers no suggestions and no placeholder row rather than
  raising during editing; a commit in that state is a no-op (document unchanged) and the
  overlay disappears.
- The feature is inert (off by default) until `setRomanInputEnabled(True)`.

## 10. Public API

```python
class RomanInputEngine:
    def __init__(self, localVocabulary: Vocabulary | None = None, *,
                 distance: int = 2, maxPredictions: int = 5, maxSuggestions: int = 10) -> None
    def suggest(self, romanWord: str) -> list[Suggestion]
    def romanizeArabic(self, arabicWord: str) -> str
    def learnRomanWord(self, word: str) -> str

class RomanOverlay(QWidget):
    committed: Signal[str, object, bool, str]  # typedRoman, selected Suggestion | None, isPlaceholder, separator char ("" = edge commit)
    canceled: Signal[]

class PyRaya:
    def setRomanInputEnabled(self, enabled: bool) -> None
    def romanEngine(self) -> RomanInputEngine | None
    def localDictionary(self) -> Vocabulary
    romanWordCommitted: Signal[str, str]  # (word committed to the document, typed roman)
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
- Commit (scenario 2, replacement): the span is replaced by the selected Arabic word; the
  region span is unchanged (still RomanUrdu, same boundaries); a single undoable edit (undo
  restores the original word exactly, no phantom commands, no ping-pong);
  `romanWordCommitted` emitted with correct arguments.
- Separator-key commit: Space → document contains the Arabic word **plus a space**; Enter →
  word **plus a newline**; punctuation → word **plus the punctuation character**; the
  committed word and separator both carry the `RomanUrdu` background; the overlay disappears
  and the cursor lands after the separator.
- Edge commit: Right/Left at the text edges commits **without inserting a character**; the
  cursor moves to the adjacent word and the overlay reloads it if eligible, else disappears;
  start/end-of-document commits land with the overlay hidden.
- Keystroke-based activation: a roman keystroke inside a `RomanUrdu` span (overlay inactive)
  is intercepted (not inserted into the document) and the overlay appears with that
  character; after a separator-key commit the overlay is hidden and the next roman keystroke
  re-activates it.
- Placeholder (Learn) commit, both scenarios: zero matches → the `+ Learn <typed>` row is
  offered; committing it commits `learnRomanWord(<typed>)` (the same word for this session)
  to the document — inserted in scenario 1, span replaced in scenario 2, plus the separator
  character for a separator-key commit — the overlay disappears, and `romanWordCommitted` is
  emitted with the committed word.
- Keys: Up/Down wraps selection; Esc cancels with document untouched; empty-text commit
  deletes the span.
- `learnRomanWord` no-op: returns the same word; committing the placeholder does not mutate
  `localDictionary()` (it stays in its initial state for this session).
- `localDictionary().save(tmp)` writes a SymSpell-format file and `Vocabulary.load` restores it.
- Geometry: overlay rect is non-empty and aligned to the word rect in the RTL layout
  (assert bounds/containment rather than pixel-exactness, since offscreen fonts may be
  fallbacks).

## 12. Documentation and release

- `AGENTS.md`: describe the overlay subsystem, the updated `RomanUrdu` region semantics, and
  the new gotchas (viewport-child overlay, single-command commits, placeholder/Learn commit
  semantics).
- `README.md`: move the feature from roadmap framing into implemented status; document the
  `RomanUrdu` region semantics, the feature switch, and the local-dictionary hook.
- Version bump `0.1.0-alpha.3` → `0.1.0-alpha.4` in `pyproject.toml`, re-lock with `uv lock`,
  and update the version string in `README.md`.

## 13. Future work (out of scope for this spec)

- Learning: `learnRomanWord` currently returns the typed roman as-is; in the future it will
  return the Arabic-script word for the typed roman and update the local `romanalfaz`
  `Vocabulary` (mappability guarding, `Vocabulary.add`/`setCompleted`).
- Custom romanalfaz dictionary editing: exporting/merging the local document dictionary into a
  custom dictionary file and any UX around it; `Vocabulary.save`/`Vocabulary.load` are the
  future hooks.
- Per-type processing for additional region types (spell-check, etc.) using the same
  region-gating wiring.

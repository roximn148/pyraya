# Roman-Input Overlay Implementation Plan

- **Goal:** Add the roman-script overlay editing subsystem to `PyRaya` per the approved design spec (`docs/superpowers/specs/2026-10-05-roman-input-overlay-design.md`), and release it as `0.1.0-alpha.4`.
- **Architecture:** A new module `src/pyraya/roman_input.py` with (a) `RomanInputEngine`, a thin lazy wrapper around `romanalfaz.RomanAlfaz`, and (b) `RomanOverlay`, a frameless non-modal `QWidget` child of the widget's **viewport** containing a `QLineEdit` plus a passive suggestion list. `PyRaya` owns feature state (`_activeWord`, `_anchorPosition`, `_committing`) and wires activation (cursor-based scenario 2, keystroke-based scenario 1) and single-command commits.
- **Tech Stack:** PySide6 (offscreen `QT_QPA_PLATFORM=offscreen` tests), `romanalfaz` (already declared), `uv`, pytest, ruff, pyrefly.
- **Spec:** `docs/superpowers/specs/2026-10-05-roman-input-overlay-design.md` (committed `835ff3d`).

## Global Constraints

- Python ≥ 3.14 via `uv`; every command runs as `uv run …` from the repo root.
- Offscreen GUI: tests reuse the single `app` fixture pattern from `tests/test_pyraya.py` (sets `QT_QPA_PLATFORM=offscreen`); never call `QApplication.exec()`.
- Naming: `camelCase` members, `PascalCase` classes; Google-style docstrings with reST cross-references on public API; type hints everywhere; keep `ruff check`, `ruff format`, and `pyrefly check` clean before any commit.
- New source module gets the copyright banner header; new public symbols re-exported from `pyraya/__init__.py` and added to `__all__`.
- **Feature-off behavior must remain byte-identical**: with `setRomanInputEnabled(False)` (default) roman keystrokes still type into the document; all overlay logic returns early.
- **Undo/redo invariants**: commits are single undoable commands; no overlay operation is recorded in the undo stack; a fresh widget with the feature enabled has no phantom undo command. Use `isUndoAvailable()` / `availableUndoSteps()` (PySide6 has no `undoCommandCount()`).
- `mergeCharFormat` **is** undoable; `setPlainText` records nothing. The committed text (word + separator) must carry the `RomanUrdu` background (`RegionColors[RegionType.RomanUrdu]`).
- Character-count guard: word-span and cursor lookups clamp to `characterCount() - 1` (the trailing terminator).
- Geometry (verified offscreen): PySide6 has **no** `QTextCursor.selectionRect`, `QTextCursor.positionAt`, or `QTextBlock.blockBoundingRect`. The working approach: `block = cursor.block()`; `layout = block.layout()`; `line = layout.lineForTextPosition(pos)` (NOT `layout.lineAt(i)` — that takes a line index and an invalid line segfaults); `line.cursorToX(pos).x()` gives the document-coordinate x; `line.rect()` is the line rect in document coordinates; viewport coords = document coords + `contentOffset()`. In RTL, `cursorToX(s).x()` is the word's left edge and `cursorToX(e).x()` its right edge; width = `abs(cursorToX(e).x() - cursorToX(s).x())`, height = `line.rect().height()`. Fallback: `QFontMetrics` advance of the word.
- Wheel: `QCoreApplication.sendEvent` does not bubble to parents, so overlay children must explicitly forward wheel events into `PyRaya.wheelEvent`. Test direction (verified): the vbar has `invertedControls=True`, `singleStep=1`, `QApplication.wheelScrollLines()=3`, so `angleDelta=(0, -120)` from value 0 → value 3.
- `romanalfaz` engine facts: `RomanAlfaz.suggest` defaults to `distance=1` — the wrapper must pass `distance=2`. SymSpell tier lists dedupe by encoded term only — the wrapper must **globally** dedupe by `Suggestion.arabic` (earlier tier wins), cap at 10 rows, `maxPredictions=5` per tier.
- Empirically verified data (offscreen): `tafseerUrduAr2Rm`: خوش→`KHOSH`, میری→`MYRY`, دوست→`DOST` (lowercased: `khosh`, `myry`, `dost`). Zero-match roman strings for placeholder tests: `xqwzrty`, `qzxv`, `kzqwxv`, `zxrqvz`, `qwzxq` (do **not** use `khila` — it has 8 matches).
- Engine construction: `RomanAlfaz()` first (loads the default wordlist), then `addVocabulary(localVocabulary)` (a constructor vocab argument would skip the default wordlist). Cold load ≈ 0.2 s; engine is per-widget and lazy.
- Unavailable-dictionary test: monkeypatch `pyraya.roman_input.RomanAlfaz` to raise `DictionaryNotFoundError`; do not remove the wordlist file.
- RTL key navigation in the overlay `QLineEdit` (verified): **not** swapped — Left = index−1, Right = index+1; Left at pos 0 = previous-word edge, Right at pos len = next-word edge.
- PowerShell: run git/uv steps as separate commands; Arabic output needs `PYTHONIOENCODING=utf-8`.

## Review Focus

- Spec §3: overlay gated to `RomanUrdu` spans only; `Latin` regions unprocessed.
- Spec §6: full key table — Space/Enter/punctuation commits, edge commits, Up/Down wrap, Esc, wheel forwarding.
- Spec §8: single undoable commit; `regionsChanged` emitted **only** for empty-text (span-deleting) commits; separator chars stay inside the `RomanUrdu` span.
- Spec §9: every edge case — no eligible word, partial containment, trailing terminator, unavailable dictionary, feature off.
- Spec §10/§12: public API shape, re-exports, docs, version bump.

---

## Task 1: `RomanInputEngine` (new module)

File: `src/pyraya/roman_input.py`. Tests: `tests/test_roman_input.py`.

- [ ] **Step 1 — Write failing tests** in `tests/test_roman_input.py` (new file; reuse the offscreen `app` fixture and `QT_QPA_PLATFORM=offscreen` from `tests/test_pyraya.py`):
  - `testRomanizeArabicKnownWords`: `engine.romanizeArabic("خوش") == "khosh"`, `"میری" → "myry"`, `"دوست" → "dost"`.
  - `testSuggestTierOrderAndDedup`: `suggest("khosh")` — tier-0 (exact) first, contains `خوش`; `suggest("khos")` (edit distance 1) non-empty; no duplicate `arabic` values anywhere in the merged list.
  - `testSuggestCap`: result length ≤ 10.
  - `testSuggestNoMatches`: `suggest("xqwzrty") == []` (verified zero-match string).
  - `testSuggestTiers`: `suggestTiers("khosh")` returns tier-0 entries with tier index 0 for `خوش`; a distance-1 input (e.g. `"khos"`) returns tier index 1 entries; global dedup — any `arabic` appears at most once and keeps its earliest tier.
  - `testLearnRomanWordNoOp`: `engine.learnRomanWord("xqwzrty") == "xqwzrty"`.
  - `testEngineUnavailable`: monkeypatch `pyraya.roman_input.RomanAlfaz` to raise `romanalfaz.DictionaryNotFoundError`; `RomanInputEngine()` constructs with `available == False`; `suggest` returns `[]`; `learnRomanWord` still returns the same word.
  - `testAddVocabularyAttached`: constructing with a fresh `romanalfaz.Vocabulary()` succeeds and `available is True` (default wordlist + local vocab both loaded).
  - Constructor config honored: `RomanInputEngine(distance=1)` for `"khosh"` still finds tier-0 (sanity that `distance` is passed through).
- [ ] **Step 2 — Run and confirm failure:** `uv run pytest tests/test_roman_input.py -q` → collection error / failures.
- [ ] **Step 3 — Implement `RomanInputEngine`** in `src/pyraya/roman_input.py`:
  - Copyright banner (same header style as `pyraya_widget.py`).
  - `__init__(self, localVocabulary: Vocabulary | None = None, *, distance: int = 2, maxPredictions: int = 5, maxSuggestions: int = 10) -> None`: try `RomanAlfaz()` then `addVocabulary(localVocabulary)`; on `DictionaryNotFoundError` set `self._alfaz = None`, `self.available = False`.
  - `available: bool` property (or attribute) — engine readiness.
  - `suggest(romanWord: str) -> list[Suggestion]`: unavailable → `[]`; call `self._alfaz.suggest(romanWord, distance=self._distance, maxPredictions=self._maxPredictions)` (the three-tier tuple), merge in tier order, globally dedupe by `Suggestion.arabic` (earlier tier wins), cap at `self._maxSuggestions`.
  - `suggestTiers(romanWord: str) -> list[tuple[Suggestion, int]]` — same pipeline but keeps each suggestion's tier index (needed by the overlay for row coloring; justified by spec §4.2/§5).
  - `romanizeArabic(arabicWord: str) -> str`: `tafseerUrduAr2Rm(arabicWord)` → lowercased encoded roman.
  - `learnRomanWord(word: str) -> str`: no-op, returns `word` unchanged (docstring documents the future behavior per spec §4.1).
  - Add `RomanInputEngine` to the module `__all__`.
- [ ] **Step 4 — Run tests until green:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 5 — Check + commit:** `uv run ruff check`, `uv run ruff format`, `uv run pyrefly check`, then `git add src/pyraya/roman_input.py tests/test_roman_input.py` and `git commit -m "feat: RomanInputEngine wrapper around romanalfaz"`.

## Task 2: `RomanOverlay` widget (standalone)

Files: `src/pyraya/roman_input.py` (extend), `tests/test_roman_input.py` (extend).

- [ ] **Step 1 — Write failing tests** (standalone, no `PyRaya` needed — the overlay is a plain `QWidget`):
  - `testOverlaySignals`: `overlay = RomanOverlay()` inside a parent `QWidget`; verify `committed` signal carries `(str, object, bool, str)` — drive a commit by emitting or by invoking the internal commit path with a fake separator; `canceled` emits on Esc.
  - `testEmptyTextHidesList`: `overlay.setText("")` → suggestion rows not visible (list hidden, no placeholder row).
  - `testZeroMatchesShowsPlaceholder`: with a zero-match string (`"xqwzrty"`, engine available) → exactly one row, the placeholder `+ Learn xqwzrty` flagged as placeholder.
  - `testPlaceholderSuppressedWhenUnavailable`: engine unavailable → no rows and no placeholder; commit is a no-op (signal emitted with `selected is None`, placeholder `False`, and `PyRaya` handles it as no-op — here just verify the overlay offers nothing).
  - `testUpDownWraps`: with ≥2 rows, Down then Up moves selection with wraparound; selection starts at row 0.
  - `testEdgeCommits`: with text-cursor at 0 → Left emits `committed` with `separator == ""` and edge direction "previous"; at `len(text)` → Right emits with `separator == ""` and "next".
  - `testSeparatorCommits`: with an active selection, typing Space emits `committed(typed, selected, False, " ")`; Enter → `"\n"`; `","` → `","`.
  - `testEscCancels`: Esc → `canceled` emitted, no `committed`.
  - `testWheelForwards`: build overlay inside a parent, send a synthesized `QWheelEvent` (ctor: `(pos, globalPos, pixelDelta, angleDelta, buttons, modifiers, phase, inverted)` with `angleDelta=(0,-120)`) via `QCoreApplication.sendEvent` to the line edit, and verify it was forwarded (record the forwarded event in a parent-side `wheelEvent` spy).
- [ ] **Step 2 — Run and confirm failure:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 3 — Implement `RomanOverlay`** in `src/pyraya/roman_input.py`:
  - `class RomanOverlay(QWidget)`: `committed = Signal(str, object, bool, str)`; `canceled = Signal()`.
  - Children: `RomanLineEdit` (a `QLineEdit` subclass) and `SuggestionList` (lightweight row widget, **passive** — never focusable).
  - Constructor takes `engine: RomanInputEngine` and the document font (`QFont`) so rows render in the document font.
  - RTL: overlay and line edit use right-to-left layout direction, right-aligned text (spec §4.2).
  - `setText(roman: str)`: sets line-edit text, cursor to end; `refreshSuggestions()`: `engine.suggestTiers(text)` → rows colored by tier (green = tier 0, orange = tier 1, red = tier 2); empty text → list hidden; zero matches with non-empty text and engine available → single placeholder row `+ Learn <typed>` (dashed gray style, placeholder flag).
  - `RomanLineEdit` key handling (`keyPressEvent`):
    - Letters/digits/Backspace/Delete/Home/End → normal `QLineEdit` editing, then `refreshSuggestions()` (synchronous, < 1 ms lookups).
    - Space / Enter / any `string.punctuation` char → emit `committed(text, selectedSuggestion or None, placeholderSelected, separatorChar)`.
    - Left at text-cursor 0 / Right at `len(text)` → emit `committed(…, separator="")` with the edge direction (stored as a transient state, e.g. `_edgeDirection: "previous" | "next" | ""`).
    - Up/Down → move highlighted row (wrapping); selection defaults to row 0.
    - Esc → emit `canceled()`.
    - `wheelEvent` → **explicitly forward** the event to the parent chain (do not call `super()` on the scroll area; `sendEvent` does not bubble) — forward into the host `PyRaya` via `self.parent()…`; expose a `forwardWheel(event)` hook or call `QCoreApplication.sendEvent(overlayHost, event)`; simplest verified approach: the overlay's wheel handler calls a parent-provided callback, or `event.accept()` is replaced by forwarding to the nearest `QAbstractScrollArea` ancestor. Implement as: `overlay.wheelEvent` → find nearest `QAbstractScrollArea` ancestor → `QCoreApplication.sendEvent(ancestor, event)`.
  - `selectedSuggestion` accessors: `selectedSuggestion() -> Suggestion | None`, `selectedIsPlaceholder() -> bool`.
  - Suggestion row rendering: Arabic word (document font) + lowercased roman (muted) + frequency (muted); selected row emphasized; placeholder row dashed gray.
  - Geometry helpers (used by `PyRaya` in Task 4): `sizeForText(text) -> QSize` via `QFontMetrics`; row height constant.
- [ ] **Step 4 — Run tests until green:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 5 — Check + commit:** ruff + pyrefly clean; `git add` + `git commit -m "feat: RomanOverlay widget with tier-colored suggestions and commit signals"`.

## Task 3: `PyRaya` scaffolding

Files: `src/pyraya/pyraya_widget.py`, `src/pyraya/__init__.py`, `tests/test_roman_input.py`.

- [ ] **Step 1 — Write failing tests:**
  - `testFeatureOffDefault`: fresh `PyRaya()` → `isRomanInputEnabled() is False`; typing roman chars into the document still inserts them (byte-identical behavior).
  - `testFeatureSwitch`: `setRomanInputEnabled(True)` / `(False)` toggles; `romanEngine()` is `None` while off.
  - `testLocalDictionary`: `localDictionary()` returns a `romanalfaz.Vocabulary`, stable across calls (same object), and its `save(tmp)` / `Vocabulary.load(tmp)` round-trips (tmp via `tmp_path`).
  - `testRomanEngineLazyAndUnavailable-safe`: with feature on, `romanEngine()` returns a `RomanInputEngine` (lazy first creation); the same object is returned on subsequent calls.
  - `testNoPhantomUndoEnabled`: fresh widget, enable feature, assert `not isUndoAvailable()`.
- [ ] **Step 2 — Run and confirm failure:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 3 — Implement in `PyRaya`:**
  - `romanWordCommitted = Signal(str, str)` (word committed to document, typed roman).
  - `_romanInputEnabled: bool = False`; `_localDictionary: Vocabulary` created in `__init__` (cheap, no I/O — `romanalfaz.Vocabulary()`); `_engine: RomanInputEngine | None`; `_activeWord: tuple[int, int] | None`; `_anchorPosition: int | None`; `_committing: bool = False`.
  - `setRomanInputEnabled(enabled: bool)`: sets the flag; on `False`, deactivate any active overlay.
  - `isRomanInputEnabled() -> bool`.
  - `localDictionary() -> Vocabulary`.
  - `romanEngine() -> RomanInputEngine | None`: off → `None`; on → lazily create `RomanInputEngine(self._localDictionary)` (catch unavailable state inside the engine).
  - In `__init__`: connect `document().cursorPositionChanged` and `document().contentsChanged` to `_syncOverlay` (both — the cursor can move without a content change and vice versa).
  - `_syncOverlay()`: early-return when feature off or `_committing`; find the word under the cursor (Task 4); activate/deactivate as per spec §4.3; guard the trailing terminator (`characterCount() - 1`).
- [ ] **Step 4 — Run tests until green:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 5 — Check + commit:** ruff + pyrefly clean; `git add` + `git commit -m "feat: PyRaya roman-input scaffolding (feature switch, dictionary, lazy engine)"`.

## Task 4: Word detection, geometry, scenario-2 activation

Files: `src/pyraya/pyraya_widget.py`, `tests/test_roman_input.py`.

- [ ] **Step 1 — Write failing tests:**
  - `testActivatesOnArabicWordInRomanUrduSpan`: tag a span containing an Arabic word (e.g. `"hello خوش world دوست"` → tag the span around `خوش` as RomanUrdu), move the cursor into the word → overlay active over the word; line-edit text == `engine.romanizeArabic("خوش")` (`"khosh"`).
  - `testNoOverlayOnWhitespaceDigitsLatin`: cursor on whitespace/digits → no overlay; word in a `Latin` region → no overlay; feature off → no overlay.
  - `testNoOverlayOnPartialContainment`: word partially inside the span → no overlay.
  - `testNoOverlayAtTrailingTerminator`: cursor at `characterCount() - 1` position in an otherwise-eligible setup → no overlay (no out-of-range `QTextCursor` request).
  - `testGeometryBounds`: overlay rect non-empty and aligned to the word rect (assert containment/alignment bounds, not pixel-exact — offscreen fonts may be fallbacks): line-edit right edge ≈ word right edge, rect within the widget.
  - `testDeactivatesWhenCursorLeaves`: cursor moves off the active word without a commit → overlay hidden, focus back on document, document unchanged.
- [ ] **Step 2 — Run and confirm failure:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 3 — Implement:**
  - `_wordUnderCursor() -> tuple[int, int] | None`: maximal run of `U+0600–U+06FF` containing the cursor position `p` (rule `s <= p < e`, i.e. the cursor is inside or at the start of the run; **cursor at the trailing terminator of the run → no word**), fully contained in a `RomanUrdu` span (`self._regionKindAt` / span check); clamp to `characterCount() - 1`.
  - `_wordRect(start, end) -> QRect`: verified approach — `cursor.block()`, `layout = block.layout()`, `line = layout.lineForTextPosition(start)`, x1 = `line.cursorToX(start).x()`, x2 = `line.cursorToX(end).x()`, rect = `[min, max]` width/height `line.rect().height()`, translate by `contentOffset()`; `QFontMetrics` advance fallback if layout values are degenerate.
  - `_activateOverlay(word: tuple[int, int])`: lazily create the overlay as a child of `self.viewport()`; position with right edge anchored to the word's right edge (spec §7); set text via `engine.romanizeArabic(wordText)`; store `_activeWord`, `_anchorPosition`; focus the `QLineEdit`.
  - `_deactivateOverlay()`: hide overlay, clear `_activeWord`, refocus the document.
  - `_syncOverlay()` completes the activate/deactivate logic using `_wordUnderCursor()`.
- [ ] **Step 4 — Run tests until green:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 5 — Check + commit:** ruff + pyrefly clean; `git add` + `git commit -m "feat: word detection and scenario-2 overlay activation"`.

## Task 5: Scenario-1 keystroke activation

Files: `src/pyraya/pyraya_widget.py`, `tests/test_roman_input.py`.

- [ ] **Step 1 — Write failing tests:**
  - `testRomanKeystrokeInterceptedInSpan`: feature on, cursor inside a `RomanUrdu` span on a non-word position, overlay inactive; send `QKeyEvent` for `"k"` → overlay appears with text `"k"`; document text **unchanged** (the char was not inserted).
  - `testLatinKeystrokeNotIntercepted`: same setup but cursor **not** in a `RomanUrdu` span (or feature off) → `"k"` is inserted into the document as before.
  - `testReactivationAfterCommit`: after a separator-key commit, overlay hidden; the next roman keystroke re-activates the overlay (scenario 1 again).
- [ ] **Step 2 — Run and confirm failure:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 3 — Implement in `PyRaya.keyPressEvent`** (before the Ctrl-shortcut block, after the feature/overlay checks): feature on, overlay inactive, no Ctrl modifier, key is ASCII alphanumeric (`a–z`, `A–Z`, `0–9`), cursor inside a `RomanUrdu` span → activate the overlay with that character as initial text (store `_anchorPosition = cursor position`), **do not** call `super()` (the char never reaches the document). Otherwise fall through to existing behavior.
- [ ] **Step 4 — Run tests until green:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 5 — Check + commit:** ruff + pyrefly clean; `git add` + `git commit -m "feat: scenario-1 roman keystroke activation"`.

## Task 6: Commits

Files: `src/pyraya/pyraya_widget.py`, `tests/test_roman_input.py`.

- [ ] **Step 1 — Write failing tests:**
  - `testScenario2ReplacementCommit`: activate on an existing word, commit (top selection) → the span `[start, end)` is replaced by the selected Arabic word; region span unchanged (still `RomanUrdu`, same boundaries); exactly one undoable edit: `undo()` restores the original word exactly, `availableUndoSteps()` back to baseline, no ping-pong; `romanWordCommitted` emitted with `(word, roman)`.
  - `testSeparatorCommits`: Space → document contains the Arabic word **plus a space**; Enter → word **plus `"\n"`**; `","` → word **plus `","`**; committed word and separator both carry the `RomanUrdu` background; overlay disappears; cursor after the separator.
  - `testEdgeCommits`: Left at text-cursor 0 / Right at end → commit inserts **no** character (document length unchanged); cursor moves to the adjacent word (skipping whitespace); overlay reloads if eligible, else disappears; at start/end of document the overlay is hidden after the commit.
  - `testEmptyTextCommitDeletesSpan`: scenario 2 with the overlay text cleared, separator-key commit → the word span is deleted, the separator is inserted, `regionsChanged` **is** emitted; a normal (non-empty) text-replacing commit does **not** emit `regionsChanged`.
  - `testPlaceholderCommitScenario1And2`: zero-match typed text (`"xqwzrty"`) → placeholder row; committing it commits `learnRomanWord("xqwzrty")` (the same word) — inserted at the cursor in scenario 1, span replaced in scenario 2, plus separator for a separator-key commit; `romanWordCommitted` emitted with the typed roman as the committed word; `localDictionary()` unchanged (initial state for this session).
  - `testUnavailableEngineCommitIsNoOp`: monkeypatched unavailable engine → commit does not modify the document; overlay disappears.
  - `testUpAndDownSelectionThenCommit`: Up/Down changes the committed suggestion.
- [ ] **Step 2 — Run and confirm failure:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 3 — Implement in `PyRaya`:**
  - `_onOverlayCommitted(typedRoman, selected, isPlaceholder, separator)`: set `_committing = True`; compute the committed word: selected `Suggestion.arabic`, or `engine.learnRomanWord(typedRoman)` for the placeholder (no-op returning the typed roman); unavailable engine → no-op path (hide overlay, refocus, no document edit).
  - Commit mechanics: scenario 2 → select the original span `[start, end)` and `QTextCursor.insertText(word + separator, fmt)` with `fmt` background = `RegionColors[RegionType.RomanUrdu]`; scenario 1 → insert at `_anchorPosition` (no span replaced). Empty text, scenario 2 → delete the span + insert the separator; empty text, scenario 1 → insert only the separator.
  - After a commit: move the document cursor (separator commit → after the separator; edge commit → walk to the adjacent word skipping whitespace and move the cursor there).
  - Emit `romanWordCommitted(word, typedRoman)`; emit `regionsChanged` **only** for the empty-text (span-deleting) commits.
  - Deactivate/reload per spec: separator commit → hide overlay (cursor lands on a non-word position, `_syncOverlay` stays inactive); edge commit → `_syncOverlay` reloads the adjacent word if eligible.
  - `_committing = False` afterwards; call `_syncOverlay()` explicitly once.
  - Wire `_syncOverlay` to also fire on `contentsChanged` so post-commit state settles.
- [ ] **Step 4 — Run tests until green:** `uv run pytest tests/test_roman_input.py -q`.
- [ ] **Step 5 — Check + commit:** ruff + pyrefly clean; `git add` + `git commit -m "feat: overlay commits (separator, edge, placeholder, empty-text)"`.

## Task 7: Re-exports, docs, version bump, final verification

Files: `src/pyraya/__init__.py`, `README.md`, `AGENTS.md`, `pyproject.toml`.

- [ ] **Step 1 — Re-export public symbols:** add `RomanInputEngine` and `RomanOverlay` to the imports from `.roman_input` in `pyraya/__init__.py` and to `__all__`.
- [ ] **Step 2 — Update `AGENTS.md`:** describe the overlay subsystem (viewport child, single-command commits, placeholder/Learn semantics, engine unavailability), the updated `RomanUrdu` region semantics, and the new gotchas (wheel forwarding, `suggestTiers`, `DictionaryNotFoundError` handling, no `undoCommandCount`).
- [ ] **Step 3 — Update `README.md`:** move the roman-overlay feature from roadmap framing into implemented status; document `setRomanInputEnabled`, `romanEngine()`, `localDictionary()`, `romanWordCommitted`, the `RomanUrdu` region semantics, and the local-dictionary hook.
- [ ] **Step 4 — Version bump:** `0.1.0-alpha.3` → `0.1.0-alpha.4` in `pyproject.toml`; update the version string in `README.md`; run `uv lock`.
- [ ] **Step 5 — Final verification (all must pass):** `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyrefly check`.
- [ ] **Step 6 — Commit:** `git add` the docs, `pyproject.toml`, `uv.lock`, `src/pyraya/__init__.py` and `git commit -m "chore: roman-input overlay docs, re-exports, version 0.1.0-alpha.4"`.

---

## Self-Review

- **Coverage:** every spec §11 test item maps to a step in Tasks 1–6; §3 gating → Tasks 3–4; §6 key table → Task 2 + Task 6; §8 invariants → Task 6; §9 edge cases → Tasks 2–6; §10 API → Tasks 1, 3, 7; §12 docs/release → Task 7.
- **API consistency:** `RomanInputEngine` signatures match spec §10; `suggestTiers` is the documented extension (§4.2/§5 justification). `PyRaya` signals: `committed(str, object, bool, str)` on the overlay, `romanWordCommitted(str, str)` on the widget.
- **Empirical fixes baked in:** geometry via `lineForTextPosition`/`cursorToX`/`contentOffset` (not the non-existent `blockBoundingRect`/`positionAt` from spec §7); wheel test direction `angleDelta=(0,-120)` → value 3; zero-match strings verified; `availableUndoSteps()` instead of `undoCommandCount()`.
- **Ordering:** each task's tests are written before its implementation; each task ends with a clean lint/type check and a commit, so every commit is independently green.

## Execution Handoff

Execute inline on branch `feat-overlay` (currently at `835ff3d`, clean tree), TDD per task, committing after each task's Step 5. After Task 7, run the full suite one last time: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyrefly check`, and `uv run pyraya` is out of scope (opens a real window) — offscreen verification only.

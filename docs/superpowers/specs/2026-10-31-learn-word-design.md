# PyRaya Learn-Word — Design Spec

- **Date:** 2026-10-31
- **Status:** Agreed in-conversation 2026-10-31; supersedes the future-work items in `2026-10-05-roman-input-overlay-design.md` (§13)
- **Target version:** 0.1.0-alpha.9 (bump lands with this feature; confirmation pending)

## 1. Summary

Lets an embedded user add a word the dictionary does not know to the application-wide
shared custom vocabulary, through a dialog. After a successful learn: the host application
persists the word on its next `Vocabulary.save`, the spell-check underline for that word
clears on the next re-highlight, and the word becomes suggestable from roman input — all
from a single `recompileLookup`. PyRaya never wraps `Vocabulary.save`: persistence is the
parent application's job.

This spec covers the learn-word feature end to end: the dependency upgrade to
`romanalfaz` 0.1.0a8 (its prerequisite, already landed), the shared engine/Vocabulary
ownership, the learn flow, the dialog, the triggers, the host-app contract, and the test
strategy.

## 2. Context: current state

- `RomanInputEngine.learnRomanWord` (`src/pyraya/roman_input.py:302`) is a no-op that
  returns the typed roman as-is; it is the hook this feature expands.
- The `+ Learn <typed-roman>` suggestion row (`src/pyraya/roman_input.py:878`) is a
  session no-op commit today.
- The spell-check underline flags unknown Arabic-script words that resolve `RomanUrdu`
  (maximal Arabic run, both ends RomanUrdu-resolved).
- `RomanInputEngine.hasWord` (`src/pyraya/roman_input.py:263`) already wraps
  `RomanAlfaz.hasWord` — an a7 API — and the spell-check pass already uses it
  (`src/pyraya/pyraya_widget.py:431`).
- Today each `PyRaya` widget owns its own `Vocabulary` (`PyRaya.__init__`, L561) and its
  own lazily created `RomanAlfaz` (`_ensureEngine`, L1102); `localDictionary()` (L1034)
  and `romanEngine()` return the per-widget instances.

## 3. Dependency: romanalfaz 0.1.0a8

The pin is `romanalfaz>=0.1.0a8` (`pyproject.toml`, re-locked via `uv lock`; the full
offscreen suite passes against the a8 wheel). API facts verified against the installed
0.1.0a8 wheel on 2026-10-31 (19/19 checks pass):

- `Vocabulary.isModified() -> bool` — **new method** (not an attribute). False at
  construction, after `save`, and after `load`; True after any mutation
  (`add`/`remove`/`replace`/`setCompleted`).
- `Vocabulary.add(word, count=1, isCompleted=False)` — the `isCompleted` parameter marks
  the word completed in the same mutation: one call, one change notification, one
  recompile.
- A `setCompleted` no-op (the word already holds the requested status) is a
  **non-mutation**: it fires no change notification and flips `isModified` not.
- `RomanAlfaz.recompileLookup` is **atomic**: the new index is built into fresh
  structures and swapped in only on success; a failed build leaves the previously
  compiled state intact. (In a7, stage 1 wiped `symSpell`/`reverseMapping` *before* the
  stage-3 `undef == 0` assertion, so a failed `add` left the engine blind to every word
  until the next successful recompile.)
- `RomanAlfaz.hasWord(arabic)` — normalized membership, present since a7 and already
  wrapped by PyRaya (no new PyRaya API needed).
- Documented startup guidance: "Populate the Vocabulary before attaching: a standalone
  Vocabulary built in bulk costs a single recompile."

## 4. Ownership: shared engine and shared Vocabulary

One application-wide shared `Vocabulary` **and** one shared `RomanAlfaz` engine, held in
a class-level holder (created once per process). Consequences:

- One `add` triggers exactly one `recompileLookup` regardless of widget count (N engines
  on one Vocabulary would mean N recompiles per `add`).
- One ~0.3 s dictionary cold load per process, one shared SymSpell index.
- `PyRaya.localDictionary()` and `PyRaya.romanEngine()` return the shared instances
  (per-widget accessors, application-wide objects).
- Per-widget flags stay per-widget: `_romanInputEnabled`, `_assistMode`, the spell-check
  switch, the region palette.
- The holder exposes a test-only reset seam so the offscreen suite can reset the shared
  state between tests.

## 5. Learn flow: `learnRomanWord`

`RomanInputEngine.learnRomanWord(arabic: str) -> str` — takes the **Arabic** word (the
`Vocabulary` counter is keyed by Arabic, not roman):

1. **Mappability check first** — `tafseerUrduAr2Rm(word)` must return `undef == 0`.
   Validated before `add` because the recompile the mutation triggers hard-asserts
   `undef == 0` (the assertion message names the offending word).
2. **`add(arabic, isCompleted=True)`** — one mutation, one notification, one recompile —
   then return the Arabic word.
3. **No bare `Vocabulary.add` from any PyRaya path.**

The user is in the loop, so the word is complete: `save` (which writes only completed
words) persists it. Failure semantics under a8: the index is intact, but the word stays
in the counter **and** the completed set — a failed add would be persisted on `save` —
so the pre-validation is load-bearing, and on `AssertionError` the dialog shows the
engine's message and stays open. Retry is safe: `add` is idempotent (increments the count,
no duplicate entry).

## 6. `isModified` contract

- Lives in `Vocabulary` (romanalfaz), not PyRaya. PyRaya never sets it — read-only.
- The host application polls `localDictionary().isModified()` (e.g., for a save prompt at
  exit); PyRaya does not wrap `save`.

## 7. Dialog (hybrid C)

- PyRaya ships a built-in `AddWordDialog` as the default: an editable Arabic-word field
  pre-filled with the trigger word, a read-only roman preview, and mappability feedback.
  OK → learn; Cancel → nothing.
- Plus an optional hook so a host application can install its own UI (handler API shape
  is an open item, §14).

## 8. Triggers

- **Right-click "Add to dictionary"** on the context menu (`PyRaya.createPopupMenu`,
  `src/pyraya/pyraya_widget.py:2057`) over an unknown word in a RomanUrdu-resolved
  region: a maximal Arabic run with both ends resolving RomanUrdu (stored tag or the
  seed) — the same candidate logic the spell-check pass already computes — and
  `hasWord` false (via the existing `RomanInputEngine.hasWord` wrapper; a word the
  engine already knows does not offer the action).
- **The `+ Learn` suggestion row**: committing it also opens the dialog.

## 9. `+ Learn` row semantics

- **Dialog OK:** the commit writes the chosen Arabic word (not the typed roman), tagged
  as usual.
- **Dialog Cancel:** the existing session no-op applies (the typed roman as-is).

## 10. Post-learn behavior

One recompile covers both: the spell-check underline for that word clears on the next
re-highlight (the engine knows the word), and the word becomes suggestable from roman
input. A `wordAdded(word)` signal fires after a successful learn.

## 11. Host-app contract

- **Persistence is the host's job:** the host calls `Vocabulary.save` on the shared
  `Vocabulary` (e.g., at exit, or whenever `isModified()` is True). PyRaya never wraps
  `save`.
- **Startup load:** `Vocabulary.load(file)` standalone (bulk, no recompile storm), then
  hand the Vocabulary to the shared holder → exactly one recompile (the a8 docs'
  populate-before-attaching guidance). The shared holder accepts a pre-populated
  Vocabulary.

## 12. Public API

```python
class AddWordDialog(QDialog):
    # built-in: editable arabic-word field (pre-filled), read-only roman preview,
    # mappability feedback; OK -> learn, Cancel -> nothing

class PyRaya:
    wordAdded: Signal[str]  # emitted after a successful learn
    def setAddWordHandler(self, handler) -> None  # host hook (shape pending, §14)

class RomanInputEngine:
    def learnRomanWord(self, arabic: str) -> str  # expanded from the no-op hook
```

Re-exported from `pyraya/__init__.py`, added to `__all__`; Google-style docstrings with
reST cross-references; camelCase members per repo convention. Final shapes land in the
implementation plan.

## 13. Testing strategy (offscreen)

Reuses the single offscreen `app` fixture; no `QApplication.exec()`.

- **Shared-holder fixture:** resets the shared holder between tests (module-level state
  must not leak across tests).
- **Shared-holder identity:** two `PyRaya` widgets share one `Vocabulary` and one
  `RomanAlfaz`; a single `add` triggers exactly one recompile (observable through a spy
  on `Vocabulary.onChangeCallbacks`).
- **`learnRomanWord`:** mappability gate (an unmappable word mutates nothing and fires
  no notification); success path (one `add(isCompleted=True)`, the word lands in
  `completed`, the return value is the Arabic word); idempotent retry (a second `add`
  increments the count, no duplicate entry).
- **`isModified` read path:** False at construction; True after a learn; False after the
  host's own `save` (host-side; no PyRaya wrapper).
- **Trigger matrix:** the "Add to dictionary" action appears over an unknown word in a
  RomanUrdu-resolved region (untagged seed-resolved text and an explicitly tagged run);
  it does not appear over a known word (`hasWord` true), over a Native-region word, or
  over whitespace / Latin runs / a partially contained word.
- **Dialog:** OK learns (`learnRomanWord` → `wordAdded` emitted); Cancel leaves the
  vocabulary unchanged.
- **`+ Learn` row:** OK → the commit writes the chosen Arabic word; Cancel → the typed
  roman commits as the session no-op.
- **Post-learn:** the spell-check underline for the learned word clears on the next
  re-highlight; the word is suggestable from roman input.
- **Signal contract:** `wordAdded` fires exactly once per successful learn; zero undo
  steps from the dialog path.

## 14. Open items

- **Handler API shape:** callable `setAddWordHandler` vs signal + callback — leaning
  callable.
- **Version bump:** whether this feature lands as `0.1.0-alpha.9` (pending confirmation).
- **No `replace`-based retry path** after a failed add — leaning: keep `add` idempotent
  and document the bounded half-state.

# PyRaya Learn-Word — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an embedded user add a word the dictionary does not know to the
application-wide shared vocabulary — through a built-in `AddWordDialog` (or a
host-installed handler), from the right-click context menu and from the
`+ Learn` suggestion row — so one `Vocabulary.add(arabic, isCompleted=True)`
triggers exactly one `recompileLookup` that clears the spell-check underline
and makes the word suggestable.

**Architecture:** One application-wide shared `Vocabulary` **and** one shared
`RomanAlfaz` engine, held in a module-level `_SharedEngine` singleton
(`roman_input.py`) created once per process; every `PyRaya` widget borrows
both. `RomanInputEngine.learnRomanWord` (currently a no-op,
`src/pyraya/roman_input.py:302`) validates mappability via
`tafseerUrduAr2Rm` **before** `add(arabic, isCompleted=True)`. The built-in
`AddWordDialog` is pure UI (editable Arabic field, read-only roman preview,
live mappability feedback, OK enabled only while mappable); the widget owns
the learn and stays open on `AssertionError` by re-opening. `PyRaya.setAddWordHandler`
installs a host callable `(trigger: str) -> str | None` in place of the
built-in dialog. `PyRaya.wordAdded = Signal(str)` fires after each successful
learn. Persistence stays the host's job: it polls `localDictionary().isModified()`
and calls `Vocabulary.save`; PyRaya never wraps `save`.

**Tech Stack:** Python 3.14, PySide6 (offscreen tests), romanalfaz 0.1.0a8,
uv, pytest, ruff (100 cols), pyrefly.

**Spec:** `docs/superpowers/specs/2026-10-31-learn-word-design.md`
(the plan argues from it; its §4–§11 decisions are reproduced in
"Global Constraints" below).

## Verification already done (probes, 2026-10-31)

Run via `uv run python` against the installed **0.1.0a8** wheel (19/19 checks
pass — the upgrade itself is landed and committed as `ff4b1b0`):

- **(A)** `Vocabulary.isModified()` is a **method**: False at construction,
  after `save`, after `load`; True after `add`. `save` writes the completed
  word (`کتاب$1` line) and resets the flag; `load` restores counter and
  completed set and resets the flag.
- **(B)** `Vocabulary.add(word, count=1, isCompleted=False)` — the
  `isCompleted=True` parameter marks the word completed in the same
  mutation: exactly one change notification, one recompile.
- **(C)** A `setCompleted` no-op (word already holds the requested status) is
  a **non-mutation**: no notification, `isModified` untouched.
- **(D)** `RomanAlfaz.recompileLookup` is **atomic**: an unmappable `add`
  raises `AssertionError` from the recompile, and the engine keeps
  suggesting and `hasWord` stays correct afterwards (a7 wiped the index
  before asserting).
- **(E)** `RomanAlfaz.hasWord(arabic)` — normalized membership, present since
  a7, already wrapped by `RomanInputEngine.hasWord`
  (`src/pyraya/roman_input.py:263`) and used by the spell-check pass
  (`src/pyraya/pyraya_widget.py:431`).

## Global Constraints (from the spec, verbatim decisions)

- One application-wide shared `Vocabulary` **and** one shared `RomanAlfaz`
  engine, held in a module-level holder created once per process. One `add`
  triggers exactly one `recompileLookup` regardless of widget count.
  `PyRaya.localDictionary()` and `PyRaya.romanEngine()` return the shared
  instances. Per-widget flags stay per-widget: `_romanInputEnabled`,
  `_assistMode`, the spell-check switch, the region palette. The holder
  exposes a test-only reset seam.
- **Learn flow:** `RomanInputEngine.learnRomanWord(arabic: str) -> str` —
  takes the **Arabic** word (the counter is keyed by Arabic). Mappability is
  validated **before** `add` (`tafseerUrduAr2Rm` must return `undef == 0`),
  because the recompile the mutation triggers hard-asserts `undef == 0` and
  names the offending word. Then `add(arabic, isCompleted=True)` — one
  mutation, one notification, one recompile — and return the Arabic word.
  No bare `Vocabulary.add` from any PyRaya path.
- **`isModified` contract:** lives in `Vocabulary` (romanalfaz). PyRaya never
  sets it — read-only. The host polls `localDictionary().isModified()`;
  PyRaya does not wrap `save`.
- **Dialog (hybrid C):** PyRaya ships a built-in `AddWordDialog` as the
  default — an editable Arabic-word field pre-filled with the trigger word,
  a read-only roman preview, and mappability feedback (OK enabled only while
  the field is non-empty **and** mappable). OK → learn; Cancel → nothing.
  Plus an optional hook so a host application can install its own UI
  (`setAddWordHandler`, callable shape).
- **Triggers:** right-click **"Add to dictionary"** on the context menu
  (`PyRaya.createPopupMenu`, `src/pyraya/pyraya_widget.py:2057`) over an
  unknown word in a RomanUrdu-resolved region — a maximal Arabic run with
  both ends resolving RomanUrdu (stored tag or the seed), `hasWord` false.
  **The `+ Learn` suggestion row:** committing it also opens the dialog
  (write commits only; edge commits stay dialog-free).
- **`+ Learn` row semantics:** dialog **OK** → the commit writes the chosen
  Arabic word (not the typed roman), tagged as usual. Dialog **Cancel** →
  the existing session no-op applies (the typed roman as-is).
- **Post-learn behavior:** one recompile covers both — the spell-check
  underline for that word clears on the next re-highlight, and the word
  becomes suggestable from roman input. A `wordAdded(word)` signal fires
  after a successful learn.
- **Host-app contract:** persistence is the host's job — it calls
  `Vocabulary.save` on the shared `Vocabulary`. **Startup load:**
  `Vocabulary.load(file)` standalone (bulk, no recompile storm), then hand
  the Vocabulary to the shared holder → exactly one recompile (the a8
  docs' populate-before-attaching guidance). The shared holder accepts a
  pre-populated Vocabulary (`replaceVocabulary`).
- **Failure semantics under a8:** the index is intact, but a failed `add`
  leaves the word in the counter **and** the completed set — a failed add
  would be persisted on `save`. The pre-validation is load-bearing. On
  `AssertionError` the dialog shows the engine's message and stays open.
  Retry is safe: `add` is idempotent (increments the count, no duplicate
  entry). No `replace`-based retry path.
- **Repo conventions:** camelCase members, Google-style docstrings with
  `Args:`/`Returns:`/`Raises:` sections and reST cross-references,
  type hints on everything public, new public symbols re-exported from
  `pyraya/__init__.py` and added to `__all__`, copyright banner on new
  source files, ruff 100-col lines, `ruff check` / `ruff format` /
  `pyrefly check` clean before work is done.
- **Testing:** single offscreen `QApplication` per suite (the existing
  `app` fixture pattern); never `QApplication.exec()` inside a test.
  Verified dictionary words for assertions: `کتاب` is **known**
  (`hasWord` true), `خلمق` is **unknown** (`hasWord` false) — the same
  pair `tests/test_spellcheck.py` pins.
- **Version:** the feature lands as `0.1.0-alpha.9` (spec §0 target; the
  bump is pending user confirmation — if declined, skip the
  `pyproject.toml` bump and the README version change, but update the
  README/AGENTS.md feature state regardless).

## Current state (exact references)

- `src/pyraya/roman_input.py`:
  - module docstring L6–13 — "exposes :meth:`RomanInputEngine.learnRomanWord`
    — a no-op for this session that simply returns the typed word as-is".
  - `RomanInputEngine` class docstring L158–178 — "The local vocabulary is
    never mutated in this session — :meth:`learnRomanWord` is a no-op and
    is the hook for the future learning feature."
  - `RomanInputEngine.__init__` L180–208 — `localVocabulary: Vocabulary |
    None = None`; builds `RomanAlfaz(vocabularies=[defaultVocabulary])` from
    `qamoos.sym`, `addVocabulary(localVocabulary)` when given.
  - `hasWord` L263–280 (wraps `RomanAlfaz.hasWord`; False while
    unavailable).
  - `romanizeArabic` L283–299 (`tafseerUrduAr2Rm`, lowercased).
  - `learnRomanWord` L302–317 — no-op returning `word` as-is.
  - `SuggestionList` L321+; `RomanOverlay` L500+; `refreshSuggestions`
    L847–882 (the `+ Learn <typed roman>` undefined-word row L871–881,
    blank `Suggestion`, tier -1); `commit` L897–921.
- `src/pyraya/pyraya_widget.py`:
  - signals L531–536: `regionsChanged = Signal()`,
    `romanWordCommitted = Signal(str, str)` — plain declaration, no
    per-signal docstring.
  - `__init__` L539–643: L559–560 flags; L561
    `self._localDictionary = Vocabulary()`; L562
    `self._romanEngine: RomanInputEngine | None = None`; L574
    `self._committing = False`; L607 `self._highlighter = PyRayaHighlighter(...)`.
  - `localDictionary()` L1034–1045 — returns `self._localDictionary`;
    docstring says "Owned by the widget".
  - `romanEngine()` L1068–1080 — `None` while the feature is disabled,
    else `self._ensureEngine()`.
  - `_ensureEngine` L1102–1115 — per-widget cache:
    `if self._romanEngine is None: self._romanEngine = RomanInputEngine(self._localDictionary)`.
  - `_wordUnderCursor` L1185+ — `tuple[int, int] | None`, the maximal
    Arabic run containing or **ending at** the cursor, entirely
    RomanUrdu-resolved, block-local.
  - `_wordRect` L1261–1298 — block-local text slice idiom:
    `block = cursor.block()`, `local = start - block.position()`,
    `block.text()[local : end - block.position()]`.
  - `_onOverlayCommitted` L1774–1836 — L1811
    `word = self._committedWord(engine, typedRoman, selected)`; L1812 edge
    keys; L1815–1816 write commit; L1817 `finally` clears `_committing`.
  - `_committedWord` L1839–1859 — `selected.isUndefined()` branch calls
    `engine.learnRomanWord(typedRoman)`; else `selected.arabic`; else `""`.
  - `_writeCommit` L1947–1987 — inserts `word + separator` tagged
    RomanUrdu; emits `regionsChanged` and `romanWordCommitted`.
  - `createPopupMenu` L2057–2095 — standard menu + region actions;
    `clearAll` action ends at L2094; `return menu` at L2095.
- `tests/test_roman_input.py`:
  - `app` fixture L47–53 (offscreen, per module).
  - `engine` fixture L57–60 — constructs its own `RomanInputEngine()`
    (unaffected by the shared holder).
  - `testLocalDictionaryStableAndRoundTrips` L901–911 — asserts
    `widget.localDictionary() is first`; adds `"khosh"`; save/load
    round-trip (still passes on the shared Vocabulary — no change needed).
  - `testUndefinedWordCommitScenario1And2` L3482–3524 — commits the
    `+ Learn` row; L3505 asserts `list(widget.localDictionary().counter) == []`
    (must gain the reset fixture + handler for the dialog flow).
- `tests/` — no `conftest.py` exists yet.
- `pyproject.toml` L3: `version = "0.1.0-alpha.8"`; L15
  `romanalfaz>=0.1.0a8` (already bumped).
- `README.md` L9: `⚠️ **Alpha** · 0.1.0-alpha.8 · Python 3.14+ · PySide6`.
- `src/pyraya/__init__.py` L29–38 imports from `.roman_input`; `__all__`
  L40–62.

## Task 1 — Shared engine holder + test-suite reset fixture

**Files:**
- Create: `tests/conftest.py`, `tests/test_learn_word.py`
- Modify: `src/pyraya/roman_input.py`

**Interfaces (exact):**

```python
# src/pyraya/roman_input.py — module level, after RomanInputEngine


class _SharedEngine:
    """The application-wide shared engine and Vocabulary holder.

    Created once per process (the module-level ``_sharedEngine``
    singleton). Owns the shared :class:`romanalfaz.Vocabulary` and the
    shared :class:`RomanInputEngine` (which wraps the shared
    :class:`romanalfaz.RomanAlfaz` and attaches the shared Vocabulary) —
    so one ``Vocabulary.add`` triggers exactly one ``recompileLookup``
    regardless of widget count, and the ~0.3 s dictionary cold load
    happens once per process.
    """

    def __init__(self) -> None:
        self._vocabulary = Vocabulary()
        self._engine: RomanInputEngine | None = None

    @property
    def vocabulary(self) -> Vocabulary:
        return self._vocabulary

    def engine(self) -> RomanInputEngine:
        if self._engine is None:
            self._engine = RomanInputEngine(localVocabulary=self._vocabulary)
        return self._engine

    def replaceVocabulary(self, vocabulary: Vocabulary) -> None:
        # Host startup path: ``Vocabulary.load(file)`` standalone (bulk,
        # no recompile storm), then hand the loaded Vocabulary to the
        # holder — exactly one recompile on first ``engine()`` (a8
        # docs' populate-before-attaching guidance). Discards a cached
        # engine.
        self._vocabulary = vocabulary
        self._engine = None

    def reset(self) -> None:
        # Test-only seam: fresh empty Vocabulary, engine discarded.
        self._vocabulary = Vocabulary()
        self._engine = None


_sharedEngine = _SharedEngine()
```

```python
# tests/conftest.py — new file (copyright banner + docstring, like the test modules)


@pytest.fixture(autouse=True)
def shared_engine() -> Iterator[None]:
    """Reset the shared engine holder so module state never leaks across tests."""
    _sharedEngine.reset()
    yield
    _sharedEngine.reset()
```

**Steps:**

- [ ] Create `tests/test_learn_word.py` (copyright banner + docstring,
      imports: `os` not needed — the `app` fixture pattern is copied from
      `tests/test_roman_input.py:47–53`; import `PyRaya`, `_sharedEngine`
      from `pyraya.roman_input`, `Vocabulary` from `romanalfaz.engine`).
      Write the failing tests:
  - `testSharedVocabularyIsApplicationWide(app)` — two `PyRaya` widgets;
    `first.localDictionary() is second.localDictionary()`; a word
    `first.localDictionary().add(..., isCompleted=True)` is visible
    through `second.localDictionary().counter`.
  - `testOneLearnTriggersOneNotification(app)` — spy
    `_sharedEngine.vocabulary.onChangeCallbacks.append(...)`; learn through
    one widget's engine; exactly one notification; the word lands in
    `completed`.
  - `testSharedEngineIsCreatedOnce(app)` — `widget.romanEngine() is
    other.romanEngine()`; laziness: `_sharedEngine._engine is None` before
    the first `romanEngine()` call, not `None` after.
  - `testReplaceVocabularyInvalidatesCachedEngine()` — no QApplication
    needed for this one, but keep the `app` fixture for consistency:
    `engine_before = _sharedEngine.engine()`;
    `_sharedEngine.replaceVocabulary(Vocabulary())`;
    `_sharedEngine.engine() is not engine_before`;
    `engine_after.vocabulary is not engine_before.vocabulary`… (assert the
    new engine attaches the new Vocabulary: learn through the new engine
    and observe the new Vocabulary, not the old).
  - `testResetRestoresFreshState(app)` — `_sharedEngine.reset()`;
    `dict(_sharedEngine.vocabulary.counter) == {}`;
    `_sharedEngine._engine is None`.
- [ ] Create `tests/conftest.py` with the autouse `shared_engine` fixture
      above (imports: `pytest`, `from pyraya.roman_input import
      _sharedEngine`).
- [ ] Run: `uv run pytest tests/test_learn_word.py -x -q` — confirm the
      tests fail (no `_sharedEngine` attribute / fixture not found).
- [ ] Implement `_SharedEngine` + `_sharedEngine` in
      `src/pyraya/roman_input.py` (module level, after `RomanInputEngine`).
      Google-style docstrings; `Vocabulary` is already imported there.
- [ ] Run: `uv run pytest tests/test_learn_word.py -x -q` — confirm pass.
- [ ] Run: `uv run pytest -q` — the full suite (the autouse fixture now
      resets the holder between **every** test in every module — confirm no
      cross-module fallout).
- [ ] Run: `uv run ruff check` and `uv run ruff format` — clean.
- [ ] Commit: `git add tests/conftest.py tests/test_learn_word.py src/pyraya/roman_input.py && git commit -m "feat: shared engine holder (shared Vocabulary + shared RomanAlfaz)"`

## Task 2 — PyRaya adopts the shared holder

**Files:**
- Modify: `src/pyraya/pyraya_widget.py`, `src/pyraya/roman_input.py`
      (docstrings only)

**Steps:**

- [ ] In `src/pyraya/pyraya_widget.py`:
  - L561: `self._localDictionary = Vocabulary()` →
    `self._localDictionary = _sharedEngine.vocabulary`.
  - L562: **remove** `self._romanEngine: RomanInputEngine | None = None`
    (the per-widget cache is redundant once the engine is shared —
    `_ensureEngine` returns the holder's engine directly).
  - `_ensureEngine` (L1102–1115): body → `return _sharedEngine.engine()`;
    docstring: "The application-wide shared roman-input engine, created
    lazily on first use. Both the roman-input overlay and the spell-check
    pass consult the same instance, and every widget borrows it, so the
    ~0.3 s dictionary cold load happens at most once per process."
  - `romanEngine()` (L1068–1080): keep the feature gate
    (`if not self._romanInputEnabled: return None`); docstring now notes
    the engine is shared application-wide.
  - `localDictionary()` (L1034–1045): docstring → the
    **application-wide shared** `Vocabulary` owned by the
    `_SharedEngine` holder; `Vocabulary.save`/`Vocabulary.load` exist for
    host persistence; `isModified()` is the host's mutation flag.
  - Add `_sharedEngine` to the `from .roman_input import (...)` block
    (keep it sorted; private name keeps its leading underscore).
  - The `Vocabulary` import stays (still the `localDictionary()` return
    annotation).
- [ ] In `src/pyraya/roman_input.py`: update the module docstring
      (L6–13: "a no-op for this session" → the shared holder is introduced
      in a later task; for now, note the shared `Vocabulary` + engine) and
      the `RomanInputEngine` class docstring (L158–178: "The local
      vocabulary is never mutated in this session" → the attached
      Vocabulary is the application-wide shared one, mutated by
      `learnRomanWord`).
- [ ] Run: `uv run pytest -q` — full suite (in particular
  `tests/test_roman_input.py::testLocalDictionaryStableAndRoundTrips`,
  `testRomanEngine...` identity tests, and the spell-check suite — the
  autouse reset means each test gets a fresh holder, so engine cold loads
  re-occur per test exactly as per-widget cold loads did before).
- [ ] Run: `uv run ruff check` — clean (no unused imports).
- [ ] Commit: `git add src/pyraya/pyraya_widget.py src/pyraya/roman_input.py && git commit -m "refactor: PyRaya widgets borrow the shared engine and Vocabulary"`

## Task 3 — `RomanInputEngine.learnRomanWord`

**Files:**
- Modify: `src/pyraya/roman_input.py`
- Modify: `tests/test_learn_word.py`

**Interfaces (exact):**

```python
# src/pyraya/roman_input.py — replaces the no-op at L302–317


def learnRomanWord(self, arabicWord: str) -> str:
    """Learn an Arabic-script word into the attached Vocabulary.

    Mappability is validated **before** the mutation:
    ``tafseerUrduAr2Rm`` must return ``undef == 0``, because the
    recompile the mutation triggers hard-asserts ``undef == 0`` and names
    the offending word. ``add`` with ``isCompleted=True`` is one
    mutation — one change notification, one ``recompileLookup`` — and
    the word lands in ``completed`` so the host's ``Vocabulary.save``
    persists it. ``add`` is idempotent: a retry increments the count,
    never duplicates the entry.

    Args:
        arabicWord: The Arabic-script word to learn.

    Returns:
        The Arabic word, unchanged.

    Raises:
        AssertionError: When no Vocabulary is attached, or the word is
            unmappable.
    """
```

**Steps:**

- [ ] Write the failing tests in `tests/test_learn_word.py`:
  - `testLearnRomanWordMappabilityGate(app)` — `engine =
    RomanInputEngine(localVocabulary=Vocabulary())`;
    `pytest.raises(AssertionError)` on `engine.learnRomanWord("کA")`
    (an Arabic letter + an unmappable Latin letter — `tafseerUrduAr2Rm`
    returns `undef > 0`); the counter is still empty; a spy on
    `vocabulary.onChangeCallbacks` saw zero notifications.
  - `testLearnRomanWordSuccess(app)` — same construction;
    `result == engine.learnRomanWord("خلمق")` (the verified-unknown
    word); the counter has exactly `{"خلمق": 1}`; `"خلمق" in
    vocabulary.completed`; the result is the Arabic word; exactly one
    notification; `vocabulary.isModified() is True`.
  - `testLearnRomanWordIdempotentRetry(app)` — a second
    `learnRomanWord("خلمق")`; counter `{"خلمق": 2}`; one entry; two
    notifications total.
  - `testLearnRomanWordRequiresVocabulary(app)` — bare
    `RomanInputEngine()` (no `localVocabulary`); `pytest.raises(
    AssertionError)` on `learnRomanWord("خلمق")`.
- [ ] Run: `uv run pytest tests/test_learn_word.py -x -q` — confirm fail
      (no-op returns the word, no `AssertionError`).
- [ ] Implement `learnRomanWord` per the interface (parameter name
      `arabicWord`; `_encoded, undef = tafseerUrduAr2Rm(arabicWord)`;
      `if self._localVocabulary is None: raise AssertionError(...)`;
      `if undef: raise AssertionError(...)` naming the word and the
      `undef` count; `self._localVocabulary.add(arabicWord,
      isCompleted=True)`; `return arabicWord`).
- [ ] Update the `RomanInputEngine` class docstring (L167–169) and the
      module docstring (L10–13): `learnRomanWord` is no longer a no-op —
      it learns into the attached Vocabulary, guarded by full mappability.
- [ ] Run: `uv run pytest -q` — full suite.
- [ ] Run: `uv run ruff check` — clean.
- [ ] Commit: `git add src/pyraya/roman_input.py tests/test_learn_word.py && git commit -m "feat: learnRomanWord validates mappability and learns with add(isCompleted=True)"`

## Task 4 — `AddWordDialog`

**Files:**
- Modify: `src/pyraya/roman_input.py`, `src/pyraya/__init__.py`
- Modify: `tests/test_learn_word.py`

**Interfaces (exact):**

```python
# src/pyraya/roman_input.py — new public class (after RomanInputEngine)


class AddWordDialog(QDialog):
    """Built-in learn-word dialog.

    An editable Arabic-script word field (pre-filled with the trigger
    word), a read-only roman preview, and live mappability feedback:
    OK is enabled only while the field is non-empty **and** mappable
    (``tafseerUrduAr2Rm`` returns ``undef == 0``). OK accepts the dialog;
    Cancel rejects it. The dialog is pure UI — it never mutates the
    Vocabulary; the caller learns the returned word.
    """

    def __init__(
        self, prefill: str = "", hint: str = "", parent: QWidget | None = None
    ) -> None: ...

    def word(self) -> str:
        """The Arabic word in the field (``""`` when empty)."""
```

**Behavior (exact):**

- Field: `QLineEdit`, `setLayoutDirection(Qt.LayoutDirection.RightToLeft)`
  (Arabic input). Pre-filled from `prefill`.
- Preview: read-only `QLabel`. On `textChanged`:
  - empty field → preview shows `hint` (the typed roman, or `"—"`);
    OK disabled.
  - `undef > 0` → preview shows a warning naming the unmappable count
    (e.g. `"unmappable: 1 character"`); OK disabled.
  - `undef == 0` → preview shows `tafseerUrduAr2Rm` lowercased (the
    :meth:`RomanInputEngine.romanizeArabic` form); OK enabled.
- Buttons: `QDialogButtonBox(Ok | Cancel)`, `clicked` connected — OK →
  `self.accept()`, Cancel → `self.reject()`.
- The dialog never calls `learnRomanWord`.

**Steps:**

- [ ] Write the failing tests in `tests/test_learn_word.py`:
  - `testAddWordDialogPrefillsAndReturnsWord(app)` —
    `dialog = AddWordDialog(prefill="خلمق")`; field text == `"خلمق"`;
    `dialog.accept()`; `dialog.word() == "خلمق"`.
  - `testAddWordDialogPreviewTracksMappability(app)` — fresh dialog
    (no prefill): empty field → OK disabled; set `"خلمق"` → preview
    shows the roman form, OK enabled; set `"کA"` → warning text, OK
    disabled; clear → OK disabled again. (Drive with
    `dialog._field.setText(...)` — the same private-access pattern the
    suite already uses for `widget._overlay`.)
  - `testAddWordDialogEmptyFieldDisablesOk(app)` — covered by the above;
    keep one dedicated assertion set for the empty state.
- [ ] Run: `uv run pytest tests/test_learn_word.py -x -q` — confirm fail.
- [ ] Implement `AddWordDialog` per the interface. Add the needed
      imports to `src/pyraya/roman_input.py` (`QDialog`,
      `QDialogButtonBox`, `QLabel` — check what is already imported).
- [ ] `src/pyraya/__init__.py`: add `AddWordDialog` to the
      `from .roman_input import (...)` block (sorted) and to `__all__`
      (after `"SuggestionListMargin"`, before `"main"`).
- [ ] Run: `uv run pytest -q` — full suite.
- [ ] Run: `uv run ruff check` — clean.
- [ ] Commit: `git add src/pyraya/roman_input.py src/pyraya/__init__.py tests/test_learn_word.py && git commit -m "feat: built-in AddWordDialog with live mappability feedback"`

## Task 5 — PyRaya learn plumbing (`wordAdded`, `setAddWordHandler`, `_learnDialog`, `_learnWord`)

**Files:**
- Modify: `src/pyraya/pyraya_widget.py`, `tests/test_learn_word.py`

**Interfaces (exact):**

```python
# src/pyraya/pyraya_widget.py — PyRaya class

wordAdded = Signal(str)  # next to romanWordCommitted (L536); plain declaration, no docstring


def setAddWordHandler(self, handler: Callable[[str], str | None] | None) -> None:
    """Install a host learn dialog in place of the built-in AddWordDialog.

    The handler receives the trigger word (the Arabic word for the
    right-click trigger, the typed roman for the + Learn row) and returns
    the chosen Arabic word on accept, or ``None`` on cancel. ``None``
    restores the built-in dialog.

    Args:
        handler: The host callable, or ``None`` for the built-in dialog.
    """


def _learnDialog(self, trigger: str, prefill: str = "") -> str | None:
    """Open the learn UI; the chosen Arabic word on accept, ``None`` on cancel.

    The handler path returns the handler's result. The built-in path
    re-opens the dialog on ``AssertionError`` (the mappability
    pre-validation is belt-and-braces behind the dialog's live feedback,
    so this stays open with the user's text until they accept or cancel),
    and treats an empty accepted field as a cancel.
    """


def _learnWord(self, word: str) -> None:
    """Learn ``word`` into the shared Vocabulary and clear its underline.

    ``RomanInputEngine.learnRomanWord`` (one mutation, one recompile),
    then a whole-document re-highlight so the spell-check underline for
    the word clears immediately, then ``wordAdded``.
    """
```

**Implementation notes:**

- `__init__` (near L574): `self._addWordHandler: Callable[[str],
  str | None] | None = None`.
- `_learnDialog` built-in loop (exact shape):

```python
if self._addWordHandler is not None:
    return self._addWordHandler(trigger)
arabic = prefill
while True:
    dialog = AddWordDialog(arabic, hint=trigger)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    word = dialog.word()
    if not word:
        return None
    try:
        self._learnWord(word)
        return word
    except AssertionError:
        arabic = word  # stay open: re-open with the user's text
```

  — note the dialog is **not** parented to `self` (offscreen modal
  `exec()` with a parent is fine, but a parentless top-level is the
  simplest correct choice for the offscreen suite; follow whichever the
  implementation finds works offscreen — if parented `exec()` misbehaves
  in the offscreen tests, drop the parent and note it in the
  docstring).

- `_learnWord` (exact shape): `self._ensureEngine().learnRomanWord(word)`;
  `self._highlighter.rehighlight()`; `self.wordAdded.emit(word)`.
- Import `Callable` from `collections.abc` (check the existing import
  style — `pyraya_widget.py` already imports from `collections.abc`;
  extend that line).
- `setAddWordHandler` placement: after `romanEngine()` (L1068–1080), in
  the dictionary/engine section.

**Steps:**

- [ ] Write the failing tests in `tests/test_learn_word.py`:
  - `testSetAddWordHandlerLearnsViaHandler(app)` — `widget = PyRaya()`;
    `widget.setAddWordHandler(lambda _trigger: "خلمق")`;
    `learned = widget._learnDialog("xqm")`; `learned == "خلمق"`;
    `widget.localDictionary().counter["خلمق"] == 1`; `widget
    .localDictionary().isModified() is True`.
  - `testLearnDialogBuiltInAccepted(app, monkeypatch)` — no handler;
    `monkeypatch.setattr(AddWordDialog, "exec", lambda self:
    QDialog.DialogCode.Accepted)`; `widget._learnDialog("قلم",
    prefill="قلم") == "قلم"`; the word lands in the shared Vocabulary.
  - `testLearnDialogBuiltInRejected(app, monkeypatch)` — patched
    `exec` → `Rejected`; returns `None`; the counter is empty.
  - `testLearnWordEmitsWordAddedOnce(app)` — fresh widget; connect
    `wordAdded`; `widget._learnWord("خلمق")`; exactly one emission with
    the Arabic word; `isModified` true; `availableUndoSteps() == 0`
    (the learn touches no document state).
  - `testDialogPathAddsNoUndoSteps(app)` — handler-OK path via
    `_learnDialog` + `_learnWord` on a fresh widget with a non-empty
    document (`setPlainText("hello")`, `baseline =
    widget.document().availableUndoSteps()`); after the dialog path,
    `availableUndoSteps() == baseline`.
- [ ] Run: `uv run pytest tests/test_learn_word.py -x -q` — confirm fail.
- [ ] Implement per the interfaces.
- [ ] Run: `uv run pytest -q` — full suite.
- [ ] Run: `uv run ruff check` and `uv run pyrefly check` — clean.
- [ ] Commit: `git add src/pyraya/pyraya_widget.py tests/test_learn_word.py && git commit -m "feat: wordAdded signal, setAddWordHandler, dialog-driven learn path"`

## Task 6 — Right-click "Add to dictionary"

**Files:**
- Modify: `src/pyraya/pyraya_widget.py`, `tests/test_learn_word.py`

**Interfaces (exact):**

```python
# src/pyraya/pyraya_widget.py — PyRaya class


def _learnCandidate(self) -> str | None:
    """The "Add to dictionary" candidate: the word under the cursor.

    ``None`` when the cursor has a selection, when there is no word run,
    or when the engine already knows the word. The word is the maximal
    Arabic run :meth:`_wordUnderCursor` returns — entirely
    RomanUrdu-resolved, so the same candidate logic the spell-check
    pass computes.
    """


def _addToDictionary(self, word: str) -> None:
    """The "Add to dictionary" trigger: dialog, then learn.

    ``None`` from the dialog (cancel) leaves the Vocabulary untouched.
    """
```

**Implementation notes:**

- `_learnCandidate` (exact shape): `cursor = self.textCursor()`;
  `if cursor.hasSelection(): return None`; `word =
  self._wordUnderCursor()`; `if word is None: return None`; `start, end =
  word`; `block = self.document().findBlock(start)`; `text =
  block.text()[start - block.position() : end - block.position()]`
  (the `_wordRect` L1272–1273 idiom); `if
  self._ensureEngine().hasWord(text): return None`; `return text`.
- `_addToDictionary` (exact shape): `learned =
  self._learnDialog(word, prefill=word)`; `if learned is not None:
  self._learnWord(learned)`.
- `createPopupMenu` (L2057–2095): after the `clearAll` action block
  (L2091–2094), before `return menu` (L2095):

```python
candidate = self._learnCandidate()
if candidate is not None:
    action = QAction("Add to dictionary", self)
    action.triggered.connect(lambda _checked, w=candidate: self._addToDictionary(w))
    menu.addAction(action)
```

**Steps:**

- [ ] Write the failing tests in `tests/test_learn_word.py`:
  - `testAddToDictionaryActionAppearsOverUnknownWord(app)` —
    `widget.setPlainText("کتاب خلمق")` (the verified pair);
    `setSpellCheckEnabled(False)` (isolate the underline from the menu
    assertion); cursor over `خلمق` (block-local position:
    `widget.document().findBlock(...)` or the `_moveCursor` helper
    copied from `tests/test_roman_input.py:923–927`);
    `menu = widget.createPopupMenu()`; an action titled
    `"Add to dictionary"` exists. Repeat with an explicitly tagged run
    (`widget.setRegionType(RegionType.RomanUrdu, start, end)` over
    `خلمق`).
  - `testAddToDictionaryActionHiddenOverKnownWord(app)` — cursor over
    `کتاب`; no such action.
  - `testAddToDictionaryActionHiddenOverNativeRegion(app)` —
    `widget.setRegionType(RegionType.Native, ...)` over the unknown
    word; no such action.
  - `testAddToDictionaryActionHiddenOverWhitespaceLatin(app)` — cursor
    over a space and over a Latin word; no such action.
  - `testAddToDictionaryActionHiddenWithSelection(app)` — a selection
    spanning the unknown word; no such action.
  - `testAddToDictionaryLearnsAndClearsUnderline(app)` — unknown word
    in the document with spell check on; `widget
    .setAddWordHandler(lambda _trigger: "خلمق")`; trigger the action
    (call `widget._addToDictionary("خلمق")` — the menu-trigger path is
    the same callable); `wordAdded` emitted once; the spell-check
    underline for the word is gone (read the per-block layout
    `FormatRange`s the way `tests/test_spellcheck.py` does — the
    underline format is absent for the word's character range).
  - `testAddToDictionaryCancelLearnsNothing(app)` — handler returns
    `None`; trigger the action; the counter is empty; no `wordAdded`.
- [ ] Run: `uv run pytest tests/test_learn_word.py -x -q` — confirm fail.
- [ ] Implement per the interfaces.
- [ ] Run: `uv run pytest -q` — full suite.
- [ ] Run: `uv run ruff check` and `uv run pyrefly check` — clean.
- [ ] Commit: `git add src/pyraya/pyraya_widget.py tests/test_learn_word.py && git commit -m "feat: right-click 'Add to dictionary' over unknown RomanUrdu words"`

## Task 7 — `+ Learn` row flow

**Files:**
- Modify: `src/pyraya/pyraya_widget.py`, `tests/test_roman_input.py`

**Implementation (exact):**

- `_onOverlayCommitted` (L1811, the `word = self._committedWord(...)`
  line) becomes:

```python
if (
    isinstance(selected, Suggestion)
    and selected.isUndefined()
    and key
    not in (
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
    )
):
    # The undefined-word (Learn) row: the dialog decides the committed
    # word (accept: the chosen Arabic word, learned; cancel: the
    # session no-op, the typed roman as-is). Edge commits (Left/Right)
    # write nothing and move in visual order, so they stay dialog-free.
    arabic = self._learnDialog(typedRoman)
    if arabic is not None:
        self._learnWord(arabic)
        word = arabic
    else:
        word = typedRoman
else:
    word = self._committedWord(engine, typedRoman, selected)
```

- `_committedWord` (L1839–1859): the `selected.isUndefined()` branch
  returns `typedRoman` (the session no-op — the dialog path owns the
  learn); docstring updated accordingly (the undefined-word row's blank
  `Suggestion` maps to the typed roman; the dialog decision happens in
  `_onOverlayCommitted`).

**Steps:**

- [ ] Update `tests/test_roman_input.py::testUndefinedWordCommitScenario1And2`
      (L3482–3524):
  - **scenario 1** (bare cursor, typed roman `xqwzrty`): install
    `widget.setAddWordHandler(lambda _trigger: None)` **before** the
    Space commit; the typed roman commits as-is (existing assertions);
    `wordAdded` not emitted; the counter stays empty (the autouse
    reset fixture in `tests/conftest.py` already guarantees a clean
    holder — no local reset needed); `setAddWordHandler(None)` to
    restore the built-in dialog after.
  - **scenario 2** (span replacement): install a handler returning
    `"خلمق"`; the Space commit replaces the span with the learned word
    (tagged RomanUrdu — `widget._regionKindAt` assertions), `wordAdded`
    emitted once, `widget.localDictionary().counter["خلمق"] == 1`,
    `isModified` true, and the typed roman is **not** written.
- [ ] Write `tests/test_learn_word.py::testLearnRowEdgeCommitSkipsDialog(app)`:
      overlay active over the `+ Learn` row; a Left edge commit (or
      Right) moves the cursor in visual order; the handler (a spy
      returning `None`) was **not** called; the counter is empty.
- [ ] Run: `uv run pytest tests/test_roman_input.py tests/test_learn_word.py -x -q` —
      confirm the updated tests fail before the implementation change.
- [ ] Implement per the interfaces.
- [ ] Run: `uv run pytest -q` — full suite.
- [ ] Run: `uv run ruff check` and `uv run pyrefly check` — clean.
- [ ] Commit: `git add src/pyraya/pyraya_widget.py tests/test_roman_input.py tests/test_learn_word.py && git commit -m "feat: + Learn row commits through the dialog (OK: learned word, Cancel: session no-op)"`

## Task 8 — `isModified` lifecycle (host contract)

**Files:**
- Modify: `tests/test_learn_word.py`

**Steps:**

- [ ] Write `tests/test_learn_word.py::testIsModifiedLifecycle(app)`:
  - `_sharedEngine.vocabulary.isModified() is False` (fresh holder from
    the autouse reset).
  - `widget._learnWord("خلمق")` → `True`.
  - Host-side save: `path = str(tmp_path / "vocab.sym")`;
    `widget.localDictionary().save(path)` → `False` again.
  - The save round-trip: `Vocabulary.load(path)` restores the word and
    the completed flag (mirroring the a8 wheel checks).
  - No PyRaya wrapper: `widget.localDictionary()` is the same
    `Vocabulary` the host saves — `widget.localDictionary().isModified()
    is False` after the host's save, and `hasWord`-level knowledge:
    `widget.romanEngine().hasWord("خلمق") is True`.
- [ ] Run: `uv run pytest tests/test_learn_word.py -x -q` — confirm pass
      (implementation already exists; this pins the host contract).
- [ ] Run: `uv run pytest -q` — full suite.
- [ ] Commit: `git add tests/test_learn_word.py && git commit -m "test: pin the isModified host-polling contract"`

## Task 9 — Docs and version

**Files:**
- Modify: `AGENTS.md`, `README.md`, `pyproject.toml`, `uv.lock`
  (regenerated)

**Steps:**

- [ ] `AGENTS.md`:
  - **Current status paragraph:** add the learn-word feature to the
    documented state — the shared `_SharedEngine` holder (one
    application-wide `Vocabulary` + one `RomanAlfaz`),
    `RomanInputEngine.learnRomanWord` (mappability pre-validation, then
    `add(arabic, isCompleted=True)` — one mutation, one notification,
    one `recompileLookup`), the built-in `AddWordDialog` (editable
    Arabic field, read-only roman preview, live mappability feedback,
    OK only while mappable; pure UI — the widget owns the learn and
    re-opens on `AssertionError`), `setAddWordHandler` (host callable
    `(trigger: str) -> str | None` — the Arabic word for the
    right-click trigger, the typed roman for the `+ Learn` row;
    `None` restores the built-in dialog), the right-click "Add to
    dictionary" action over unknown RomanUrdu words (`_learnCandidate`:
    no selection, `_wordUnderCursor` run, `hasWord` false), the
    `+ Learn` row semantics (dialog OK → the commit writes the chosen
    Arabic word; Cancel → the session no-op, typed roman as-is; edge
    commits dialog-free), `wordAdded = Signal(str)` after each
    successful learn, and the host contract: persistence is the host's
    job (`Vocabulary.save` on the shared Vocabulary; PyRaya never wraps
    `save`), startup load is `Vocabulary.load(file)` standalone then
    `replaceVocabulary` on the holder (populate-before-attaching —
    exactly one recompile), `isModified()` is a read-only host-polling
    method on `Vocabulary`.
  - **Gotchas:** romanalfaz 0.1.0a8 — `Vocabulary.isModified()` is a
    **method** (not an attribute); `add(word, count=1,
    isCompleted=False)` marks completed in the same mutation (one
    notification, one recompile); a `setCompleted` no-op is a
    non-mutation (no notification, `isModified` untouched);
    `recompileLookup` is atomic (a failed `add` leaves the previous
    index intact, but the word stays in the counter **and** completed —
    a failed add would be persisted on `save`, which is why
    `learnRomanWord` pre-validates mappability); `hasWord` is normalized
    membership (present since a7, already wrapped by
    `RomanInputEngine.hasWord` and used by the spell-check pass). The
    shared holder is a module-level `_SharedEngine` singleton in
    `roman_input.py` (created once per process; the test-only `reset()`
    seam is exercised by the autouse `shared_engine` fixture in
    `tests/conftest.py`, so every test — in every module — gets a fresh
    holder and pays the ~0.3 s dictionary cold load per test exactly as
    per-widget cold loads did before).
- [ ] `README.md`: add the learn-word feature to the feature state
      (dialog + right-click + `+ Learn` row + `wordAdded` + host
      `isModified`/`save` contract); update the version string (L9)
      `0.1.0-alpha.8` → `0.1.0-alpha.9`.
- [ ] `pyproject.toml` L3: `version = "0.1.0-alpha.8"` →
      `"0.1.0-alpha.9"`; run `uv lock` (regenerates `uv.lock` — never
      hand-edit).
- [ ] Run: `uv run pytest -q` — full suite (the version change touches
      nothing runtime, but the lock must resolve).
- [ ] Commit: `git add AGENTS.md README.md pyproject.toml uv.lock && git commit -m "docs: learn-word feature state; version 0.1.0-alpha.9"`

## Task 10 — Final verification

**Steps:**

- [ ] Run: `uv run ruff check` — clean.
- [ ] Run: `uv run ruff format --check` — clean (apply `uv run ruff
      format` and commit if it reformats anything).
- [ ] Run: `uv run pyrefly check` — clean (the whole project must pass).
- [ ] Run: `uv run pytest -q` — full offscreen suite, all pass (the
      opt-in latency harness stays skipped without `PYRAYA_LATENCY=1`).
- [ ] Run: `uv run pyraya` is **not** part of automated verification
      (it opens a real window) — the offscreen suite is the gate.
- [ ] If any fix was needed: `git add -A && git commit -m
      "chore: final verification fixes for the learn-word feature"`.

## Definition of done

- `uv run ruff check`, `uv run ruff format --check`, `uv run pyrefly
  check`, and `uv run pytest -q` all clean.
- One `Vocabulary.add` from any widget triggers exactly one
  `recompileLookup` (the notification-spy test pins it).
- The spell-check underline for a learned word clears immediately (the
  `_learnWord` re-highlight), and the word is suggestable from roman
  input after the learn.
- `wordAdded` fires exactly once per successful learn; zero undo steps
  from the dialog path; `regionsChanged` semantics unchanged.
- The host contract holds: `isModified()` False at construction / after
  host `save`, True after a learn; PyRaya never wraps `save`; the
  holder's `replaceVocabulary` accepts a pre-populated Vocabulary
  (populate-before-attaching → exactly one recompile).

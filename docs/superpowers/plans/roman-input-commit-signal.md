# Plan — roman-input commit-signal refactor

## Context

PyRaya (pyraya) is a reusable, self-contained PySide6 (Qt) text editor widget for Urdu / Nastaliq (right-to-left) text. Read `AGENTS.md` before starting — it carries the project conventions, the test-suite contract, and the PySide6/Qt gotchas that bind this work.

The roman-input overlay (`RomanOverlay` in `src/pyraya/roman_input.py`) lets the user type roman text over an Arabic-script word; the host widget `PyRaya` (`src/pyraya/pyraya_widget.py`) owns the commit policy through the overlay's `committed` signal and the `_onOverlayCommitted` handler.

This plan refactors that signal so it carries the committing keystroke and a homogeneous `Suggestion` payload instead of a pre-cooked separator character and a placeholder flag, letting the host widget own the entire commit policy — including Enter vs Ctrl+Enter differentiation.

The `romanalfaz` dependency is already upgraded to **0.1.0a4** (setup, done). That release added to `romanalfaz.engine.Suggestion` (a `NamedTuple`):

- field defaults `arabic: str = ""`, `encodedRoman: str = ""`, `frequency: int = 0`, so `Suggestion()` constructs the blank suggestion;
- an `isUndefined` **method** (call syntax: `suggestion.isUndefined()`), returning True exactly when `arabic == ""` and `frequency == 0`.

Work happens on the `feat-overlay` branch.

## Global Constraints

- Python >= 3.14, managed with uv; run everything through `uv` (`uv run ...`).
- `uv run pytest` (offscreen), `uv run ruff check`, `uv run ruff format`, and `uv run pyrefly check` must all be clean before the task is done.
- Qt toolkit naming: `camelCase` for variables, functions, methods, signals; `PascalCase` for classes and enum members; type hints on public functions and classes; Google-style docstrings with reST cross-references.
- PySide6 cannot map `Suggestion | None` as a `Signal` argument type — the signal argument is declared `object` and handlers narrow with `isinstance(..., Suggestion)`; keep this pattern.
- Tests run headless (`QT_QPA_PLATFORM=offscreen`) and reuse the single offscreen `QApplication` fixture; never call `QApplication.exec()` inside a test.
- Do not stage IDE files; do not hand-edit `uv.lock` (regenerate with `uv lock`); do not add third-party dependencies.
- Behavior outside the signal contract and the Enter / Ctrl+Enter split is unchanged: existing space, punctuation, edge, and empty-text commits behave identically.
- `learnRomanWord`, the `+ Learn <word>` row label, and `_PLACEHOLDER_COLOR` keep their existing names; "placeholder" wording that names the removed flag becomes "undefined-word" in prose.

## Task 1: refactor the commit signal, row model, widget policy, and tests

Refactor `RomanOverlay.committed`, the suggestion row model, and the host commit policy, and update the tests — tests first.

### Step 1 — tests first (`tests/test_roman_input.py`)

- The `_sendKey` helper already builds `QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)` — Ctrl+Enter is directly synthesizable; no helper change needed.
- Move every signal-capture lambda that currently captures `(typedRoman, selected, isPlaceholder, separator)` to the new five-argument signature `(typedRoman, selected, key, keyText, modifiers)` and assert `key`, `keyText`, and `modifiers` for the committing keystroke.
- Add a Ctrl+Enter commit test: with the overlay active over a roman urdu word, Ctrl+Enter commits the word **without** a newline (the document gains only the word; no cursor navigation), while plain Enter commits the word **with** a newline.
- `Suggestion` is a `NamedTuple`, so the blank suggestion is equality-comparable: assert the undefined-row payload directly, e.g. `selected == Suggestion("", <typed roman>, 0)`.
- Update assertions that referenced `row.isPlaceholder` or `suggestionList.isPlaceholderSelected()` to the row model below.

### Step 2 — signal (`src/pyraya/roman_input.py`)

- `RomanOverlay.committed` is declared `Signal(str, object, int, str, int)` and emits `(typedRoman, selected, key, keyText, modifiers)`:
  - `typedRoman`: the overlay's typed text;
  - `selected`: `None` **only** when the overlay text is empty / no row selected; a matched row emits its `Suggestion`; the undefined-word row emits a blank `Suggestion` — `isUndefined()` true, `encodedRoman` set to the typed roman;
  - `key`: the committing `Qt.Key` int; `keyText`: `event.text()`; `modifiers`: the `Qt.KeyboardModifiers` int.
- `commit()` takes `(key: int, keyText: str, modifiers: int)` and emits the signal from the current text and selection; the `RomanLineEdit.keyPressEvent` commit paths call it with the event's key, text, and modifiers.
- Update the `RomanOverlay` class docstring's `Signals:` section and the `commit()` docstring to spell the contract above, including the Enter / Ctrl+Enter behavior and the blank-`Suggestion` convention.

### Step 3 — row model (`src/pyraya/roman_input.py`)

- `_SuggestionRow.suggestion` becomes non-optional `Suggestion` (homogeneous — every row holds a `Suggestion`).
- The `+ Learn` row is constructed from `Suggestion(encodedRoman=<the typed roman>)` (a default-constructed blank suggestion carrying the typed text).
- `SuggestionList.selectedSuggestion()` returns `Suggestion | None`, with `None` meaning only "no row selected".
- The `_SuggestionRow.isPlaceholder` field is dropped; the paint code and `SuggestionList.isPlaceholderSelected()` (renamed `isUndefinedWordSelected()`) go through `suggestion.isUndefined()`.

### Step 4 — widget policy (`PyRaya._onOverlayCommitted`, `src/pyraya/pyraya_widget.py`)

Everything is derived from the signal arguments:

- Committed word: `""` when `selected is None`; `engine.learnRomanWord(typedRoman)` when `selected.isUndefined()`; else `selected.arabic`.
- `Key_Left` / `Key_Right` (unmodified): edge commit — nothing is written to the document; the direction is taken from the `key` argument (the `cursorPosition() == 0` peek is removed); the cursor moves in visual order — Left to the next Arabic word, Right to the previous — or, with no adjacent word, the overlay hides and the cursor lands at the word's visually left edge.
- `Key_Return` + `Ctrl`: commit the word, **no newline**, no navigation.
- Plain `Key_Return`: commit the word **+ newline**.
- `Key_Space` and typed punctuation: commit the word + `keyText` as the separator.
- The separator string for the insertion path is `"\n"` for `Key_Return`, `keyText` for `Key_Space` / punctuation, and `""` for `Key_Return` with `Ctrl`.
- `romanWordCommitted` is emitted with `(word, typedRoman)` only when the committed word is non-empty.
- Update the handler docstring accordingly.

### Step 5 — verify and commit

`uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, and `uv run pyrefly check` all clean. Commit `src/pyraya/roman_input.py`, `src/pyraya/pyraya_widget.py`, and `tests/test_roman_input.py` (specific paths only — nothing else).

## Task 2: docs and version bump

After Task 1 lands:

- `AGENTS.md`: the status paragraph and the test-suite description gain the Enter / Ctrl+Enter commit behavior (plain Enter commits the word plus a newline; Ctrl+Enter commits the word without a newline); the gotcha line that names the old signal declaration `Signal(str, object, bool, str)` is updated to `Signal(str, object, int, str, int)`; "placeholder" wording that names the removed `isPlaceholder` flag becomes "undefined-word" (`learnRomanWord`, the `+ Learn <word>` row label, and `_PLACEHOLDER_COLOR` keep their existing names).
- `README.md`: the same prose updates; the version string updates to `0.1.0-alpha.5`.
- `pyproject.toml`: `version` becomes `0.1.0-alpha.5`; run `uv lock` (do not hand-edit `uv.lock`).
- Verify: `uv run ruff check`, `uv run pyrefly check`, and `uv run pytest` clean. Commit `AGENTS.md`, `README.md`, `pyproject.toml`, and `uv.lock` (specific paths only).

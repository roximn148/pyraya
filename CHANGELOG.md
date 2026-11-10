# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file records changes starting from the baseline version `0.1.0a8` onward;
earlier releases (`0.1.0a1` through `0.1.0a7`) are all incorporated
into this release version.

## [0.1.0a13] - 2026-11-10

### Added

- `PyRaya.assistModeChanged(bool)`, `PyRaya.spellCheckChanged(bool)`, and
  `PyRaya.dictionaryChanged(vocabulary)`: the widget now reports its own
  state changes to its host instead of leaving it to poll. Assist mode
  announces every real flip — `setAssistEnabled`, `Ctrl+Space`, `Ctrl+Esc`
  in the document and on the overlay, the double-Esc tap, and
  `setRomanInputEnabled(True)` resetting the mode to on; the spell-check
  switch announces its new value; the dictionary signal carries the
  `Vocabulary` now in effect and fires from `setLocalDictionary` and from
  a learned word (before `wordAdded`). All three fire on an actual change
  only, so a host echoing a value back into the setter cannot loop, and
  each is local to the emitting widget: the dictionary is process-wide,
  but forwarding a change to other instances is the host's job.
- A roman-input commit whose word is the one already standing under the
  overlay no longer rewrites it: the word is left exactly as it is — same
  text, same tags — the cursor moves to its end, and only the typed
  separator is written (a bare commit — Enter, Ctrl+Up/Down — writes
  nothing at all: no undo step, no modification flag, no
  `regionsChanged`). Re-committing an existing word is the normal
  "learn the word that is already here" path, and rewriting the word over
  itself cost two undo steps and dirtied the document for no visible
  change. The comparison covers the word only, so a separator commit
  still lands — one undo step, beside the document's own whitespace — and
  a commit whose word differs from the span replaces it as before.
- `PyRaya.setLocalDictionary(vocabulary)`: install a host's persisted
  dictionary in one pass. A `romanalfaz` Vocabulary recompiles the whole
  lookup index on every mutation once it is attached, so the previous
  natural host loop — `for word, count in stored.items():
  localDictionary().add(...)` — paid a full rebuild per word (~0.2 s each;
  66 stored words froze a host's first file open for ~12 s). Build or
  `Vocabulary.load` the dictionary standalone, then hand it over: the
  shared holder swaps it and discards the cached engine, so the next lookup
  attaches the whole vocabulary at a constant cost, independent of its
  word count. The swap is application-wide and replaces rather than
  merges; every widget sees it through `localDictionary()` (which now reads
  the holder dynamically instead of a construction-time cached reference),
  and the calling widget is re-highlighted so its spell-check underlines
  follow immediately.

## [0.1.0a12] - 2026-11-10

### Fixed

- The context menu now describes what was right-clicked. The menu resolves
  the "Add to dictionary" candidate, the region actions and the selection
  state from the document cursor, and Qt never moves the cursor on a
  right-click, so the menu reported wherever the cursor had last been left.
  A context-menu request now places the cursor at the clicked point first —
  Windows pattern: a click inside the selection keeps the selection and the
  cursor, any other click collapses the selection and moves the cursor.
- A right-click no longer re-opens the roman-input overlay over the cursor's
  word: only a left-button release reconciles the overlay now.
- Cancelling the learn dialog from the `+ [..]` row no longer replaces the
  Arabic word under the cursor with the typed roman. A cancel is now no
  edit at all: the word stays, no separator is written, the word is not
  re-tagged, no undo step is added, and no signal fires — the overlay is
  dismissed exactly like a plain Esc.
- The shipped qamoos dictionary counts are corrected: `ملیں` is re-ranked
  from 998 to 3998, and the misspelling `شائد` (26) is merged into the
  correct spelling `شاید` (3387 → 3413). The misspelling `شائد` is no
  longer a known word, so it now gets the spell-check underline and the
  Add-to-dictionary action, and the frequency ranks of `ملیں` and `شاید`
  shift, which can change suggestion ordering and learn behavior for
  these words.

### Changed

- Cancelling the `+ [..]` row at a bare cursor no longer commits the typed
  roman. The suggestion overlay produces Arabic only; the typed roman is
  discarded with the overlay, as it already was on a plain Esc. Hosts that
  relied on the roman-as-is fallback should type roman with the feature
  off (`setRomanInputEnabled(False)`) or in a `Native` region instead.

## [0.1.0a11] - 2026-11-04

### Changed

- `romanalfaz >= 0.1.0a12`: a surface release — copyright-header and
  docstring reformatting, a comment moved inside `LIGATURE_MAP`, an
  explicit `strict=False` on a `zip` call, and `raise ... from e`
  exception chaining; no API or behavioural change (every fact
  documented for a11 holds).
- `[build-system] requires` raised from `uv_build>=0.12.6,<0.13.0` to
  `uv_build>=0.13.7,<0.14.0`, matching romanalfaz 0.1.0a12's own
  build pin.

## [0.1.0a10] - 2026-11-04

### Changed

- Python 3.13: `requires-python = ">=3.13"`, pinned interpreter 3.13, ruff
  `target-version = "py313"`, pyrefly `python-version = "3.13"`.
- `romanalfaz >= 0.1.0a11`: the engine pins `DistanceAlgorithm.DAMERAU_OSA_FAST`
  via `symspellpy[editdistpy]` (symspellpy >= 6.10.1); no API change.
- PySide6 6.12.0: the floor is raised from `>=6.11.2` to `>=6.12.0`. The
  offscreen suite, the latency harness, `ruff`, and `pyrefly` all pass on
  6.12.0; the 6.11.2 `QDialogButtonBox` wiring gotcha (the explicit handler
  is load-bearing) was re-verified on 6.12.0 and is unchanged.
- `pyside6` metapackage → `pyside6-essentials`: the direct dependency is now
  `pyside6-essentials>=6.12.0` instead of `pyside6>=6.12.0`. pyraya imports
  only `PySide6.QtCore`, `PySide6.QtGui`, and `PySide6.QtWidgets`, all of
  which `pyside6-essentials` provides (byte-identical `PySide6/__init__.py`
  and `.pyi` stubs, and the `.pyd` binaries), so the metapackage's
  transitive `pyside6-webengine` (Windows wheel ~250 MB), `pyside6-pdf`
  (~9 MB), and `pyside6-addons` (~90 MB) no longer install. The offscreen
  suite, the latency harness, `ruff`, and `pyrefly` all pass with
  essentials alone.

### Removed

- `pydantic` dependency: declared in the initial skeleton but never imported;
  re-add it when the roadmap work that reserved it lands.

## [0.1.0a9] - 2026-11-03

### Added

- Learn-word feature: one application-wide shared `Vocabulary` and `RomanAlfaz`
  engine borrowed by every `PyRaya` widget (`localDictionary()`,
  `romanEngine()`), `learnRomanWord` with mappability pre-validation, the
  `wordAdded` signal, a `setAddWordHandler` host hook, the built-in
  `AddWordDialog` with live mappability feedback, a right-click "Add to
  dictionary" action over unknown RomanUrdu words, and a `+ [word]` learn row
  for typed words with no exact match.
- Region-scoped 1:1 character substitution: `RegionSubstitutions` with
  `substituteChar` / `substituteText` maps typed Latin punctuation (full stop,
  comma, question mark, semicolon) and ASCII digits to their Eastern
  Arabic-Indic / Arabic-script forms in `RomanUrdu` regions; `Native` regions
  pass characters through unchanged.
- Overlay input cap: the typed word is capped at the collective vocabulary's
  longest word plus search depth and margin, read fresh from the
  `maxRomanWordLength` statistic on every suggestion call.
- `PyRaya.wordRuns()` and the module-level `wordRuns(text)`: a whole-text
  word-run walk sharing the point-query scan, so the point query and the
  whole-text walk cannot diverge.
- Double-tap Esc turns assist mode off; a single plain Esc only dismisses the
  overlay.
- Ctrl+Up / Ctrl+Down commit-and-navigate on the active overlay: commits the
  selected word bare and moves the document cursor one line up or down.

### Changed

- Commit semantics: a plain Enter commits the word without a newline (the
  resync is suppressed); Ctrl+Enter commits the word plus a newline.
- Esc split: a plain Esc dismisses the active overlay only (assist stays on);
  Ctrl+Esc turns assist mode off, from the overlay or the document.
- The roman engine's default Vocabulary is the bundled `qamoos.sym`, replacing
  the bundled `UrduWords5k.sym`.
- All `PyRaya` widgets borrow one shared engine and one shared `Vocabulary`:
  a single `Vocabulary.add` triggers exactly one `recompileLookup` regardless
  of widget count, and the dictionary cold load happens at most once per
  process.
- The Urdu word class is derived from Unicode general categories over
  `ArabicScriptRanges` (`ArabicScriptWordChars`, `ArabicScriptSeparators`)
  instead of a hand-maintained list; the default ink rule is built from the
  same ranges, and presentation forms and the Arabic supplement are covered.
- The `+ [word]` learn-row label elides input above 8 characters.
- The RomanUrdu region tint is recoloured to a faint blue.
- `romanalfaz` upgraded 0.1.0a7 → 0.1.0a10: a9 is a performance release; a10
  adds the `minRomanWordLength` / `maxRomanWordLength` vocabulary statistics.

### Fixed

- `AddWordDialog`'s button handler takes `QDialogButtonBox.clicked`'s single
  `button` argument.
- The `+ Learn` dialog seeds its field with the word under the cursor.
- The spell-check pass is routed through `wordRuns`.

## [0.1.0a8] - 2026-10-23

### Added

- Region model re-derivation (public API break): regions now record *intent*
  instead of appearance — region kinds are stored as a custom integer
  property (`RegionKindProperty`) on the document's character formats and
  resolved in two steps: a stored tag wins, untagged characters take the
  widget's read-only seed kind (`SeedRegionKind`, `seedRegionKind()`). New
  public surface: `seedRegionKind()`, the `regionsChanged` signal, and the
  per-widget, view-only region palette (`RegionColors`, `regionColors()`,
  `setRegionColor`).
- An opt-in latency test harness (`PYRAYA_LATENCY=1`) with committed reference
  fixtures and coarse per-row budgets.

### Changed

- The existing region API (`regions()`, `setRegionType`, `clearRegions`, the
  right-click region menu, `Ctrl+1` / `Ctrl+2`) now operates on the stored-kind
  model.
- The region palette is per widget and view-only: every widget copies the
  module-level `RegionColors` default at construction and owns it, and
  recolouring repaints the tint in the text layouts directly without bumping
  the document revision.
- Tag writes are format-only and recorded as one undo step each; a batch
  `clearRegions` replays its span removals inside one edit block.
- Performance: run-based region span reconstruction and recolour, a
  block-local word path, uniform-run merged layout writes for the tint wash
  and spell-check underline, coalesced per-keystroke overlay sync, and spell
  candidates resolved from block format runs.
- The README was overhauled for human readers.

### Fixed

- Alignment reaches every paragraph; region palette copies are deep.
- Every writing commit emits `regionsChanged`.
- Deep-tier suggestions clamp to the row palette.
- Cursor-only keys in the overlay keep the highlighted suggestion.
- Recolouring repaints the default-kind wash immediately.
- `setAlignment` no longer leaves the document selected.

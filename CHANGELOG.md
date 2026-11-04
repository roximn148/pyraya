# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file records changes starting from the baseline version `0.1.0a8` onward;
earlier releases (`0.1.0a1` through `0.1.0a7`) are all incorporated
into this release version.

## [Unreleased]

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

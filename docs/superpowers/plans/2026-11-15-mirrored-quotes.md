# Mirrored-quotes: same-kind gate + RomanUrdu quote-swap + font stack

**Plan:** agreed in conversation on 2026-11-15 (no separate spec file); authority is
the agreed plan plus the AGENTS.md conventions.
**Goal:** constrain selection enveloping (auto-wrap) to selections whose two ends
resolve to the same region kind, add a `mirrored` flag to `WrapPair`, and have only
the RomanUrdu region swap the ending assignments of the (unmirrored) quote pairs —
mirrored pairs and every other region write the marks as listed. Also incorporate
the three font families already added to `PyRayaFonts` in the working tree.
**Verification:** the repo's own gate — `uv run pytest`, `uv run ruff check`,
`uv run ruff format`, `uv run pyrefly check` (the latency harness is opt-in and
not run here: `PYRAYA_LATENCY=1 uv run pytest -s` only when a row is in question).

## Context

- Branch `mirrored-quotes` is cut from `main` (the 2 commits ahead of
  `github/main` are NOT pushed). The working tree carries exactly one uncommitted
  change: the three new `PyRayaFonts` entries (`Kawkab Mono`, `Mehr Nastaliq
  Web`, `Jameel Noori Nastaleeq`) at `pyraya_widget.py:99-101`. That hunk is
  committed by Task 5, not earlier — it must be kept out of Tasks 1-3's commits
  (stage with `git add -p` so the font hunk is not swept in).
- The auto-wrap write path is `_envelopSelection` (`pyraya_widget.py:2689-2751`):
  it reads `start`/`end`, resolves `openKind = _typingKindAt(start)` and
  `closeKind = _typingKindAt(end)` *before* any insertion shifts positions, then
  writes the closing mark at `end` and the opening mark at `start`, each tagged
  with its own landing kind, inside one edit block.
- The gate is in `keyPressEvent` (`pyraya_widget.py:2960-2963`): it currently
  requires `self.textCursor().hasSelection()`. It is replaced by
  `_selectionEndsShareKind()`, which subsumes `hasSelection()` (returns False
  without a selection) and additionally requires the two ends to resolve to the
  same kind.
- `_typingKindAt` (`pyraya_widget.py:3414-3452`) resolves the kind a character
  typed at `position` carries; `_regionKindAt` (`:3371-3379`) resolves a stored
  tag, else the seed. The predicate goes next to `_typingKindAt`.
- Glyph math (seed-resolved, untagged text is RomanUrdu):
  - `double-quote` pair: opening `\u201c` (at start), closing `\u201d` (at end).
    Seed text, selection [1,3): today `a\u201cbc\u201dd`; after the RomanUrdu
    swap `a\u201dbc\u201cd`.
  - `single-quote` pair: opening `\u2018`, closing `\u2019`. Seed text,
    selection [1,3): today `a\u2018bc\u2019d`; after the swap `a\u2019bc\u2018d`.
  - A Native selection [1,3] on all-Native text, press `"`: no swap,
    `a\u201cbc\u201dd`.
  - Mismatched-ends setup: "abcd", 0-1 Native, select [2,4], press `(`: the gate
    rejects it, the trigger replaces the selection as a plain keystroke,
    yielding `ab(` with the cursor at 3.
- `WrapPair` is a frozen dataclass (`wrapping.py:25-42`), re-exported from
  `pyraya/__init__.py` (`WrapPair`, `WrapPairs`, `DefaultWrapPairs`). The 15
  pairs: ten bracket/guillemet pairs (`parentheses`, `square`, `curly`,
  `guillemets`, `single-guillemets`, `angle-brackets`, `floor-brackets`,
  `ceiling-brackets`, `black-brackets`, `fullwidth-parentheses`) are
  BiDi-mirrored (`mirrored=True`); the five quote pairs (`double-quote`,
  `single-quote`, `low-double-quote`, `mixed-double-quote`, `low-single-quote`)
  are not (`mirrored=False`).
- Public API change: `WrapPair` gains a `mirrored: bool` field. That takes `!`
  after the type/scope plus a `BREAKING CHANGE:` footer on the commit that
  introduces it (Task 2).

## Global Constraints

- Everything runs through `uv` from the repo root.
- ruff 100-char lines; imports sorted/minimal; no new third-party deps.
- Docs keep the documented state accurate: AGENTS.md + README.md + CHANGELOG.md.
- No version cut (auto-wrap is still under `## [Unreleased]`): the gate/policy
  fold into the existing `## [Unreleased] > Added` auto-wrap entry; the font
  addition gets its own `## [Unreleased]` line.
- Offscreen Qt: tests run headless via the `app` fixture; `QT_QPA_PLATFORM=offscreen`.
- Conventional Commits with scopes (`widget`, `regions`, `tests`, `docs`, `build`).
- `ruff check`, `ruff format`, and `pyrefly check` stay clean before a task is done.

## Interfaces

- **Task 1 produces** `_selectionEndsShareKind()` (a `bool`, on `PyRaya`), and
  consumes the gate at `keyPressEvent`. **Task 3 consumes** the gate's guarantee
  that `openKind == closeKind` (the swap policy reads one of them, trusting the
  gate). If the gate is later relaxed, the swap policy must re-derive the kind.
- **Task 2 produces** `WrapPair.mirrored: bool`. **Task 3 consumes** it in the
  inline swap (`if not pair.mirrored and openKind is RegionType.RomanUrdu`).
- **Tasks 4 and 5** both edit AGENTS.md and CHANGELOG.md. They run sequentially
  (4 before 5); Task 4's edits are committed before Task 5's, so there is no
  overlap. Task 5 additionally touches `tests/test_pyraya.py` and the `PyRaya`
  class docstring (`pyraya_widget.py:711-713`), neither of which Task 4 touches.

## Task 1: same-kind gate (`_selectionEndsShareKind`)

### Step 1.1 (RED): write the three gate tests

In `tests/test_auto_wrap.py`:

1. **New mismatched-ends gate test** (this is the genuine RED test):

   ```python
   def testMismatchedEndsDoNotEnvelop(app: QApplication) -> None:
       """A selection whose ends resolve to different kinds does not envelope."""
       widget = PyRaya()
       widget.setPlainText("abcd")
       _select(widget, 0, 2)
       widget.setRegionType(RegionType.Native)  # "ab" Native
       _select(widget, 2, 4)  # ends: opening kind Native, closing kind RomanUrdu
       _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
       # The gate rejects it: the trigger replaces the selection as a plain
       # keystroke (no selection is consumed by the envelop).
       assert widget.toPlainText() == "ab("
       assert widget.textCursor().position() == 3
   ```

2. **Repurpose `testMarksCarryTheKindOfTheirLandingPosition`** to call
   `_envelopSelection` directly (bypassing the gate) so it keeps pinning the
   per-edge tagging that the gate no longer reaches. Change only the trigger
   line from `_keyPress(...)` to `widget._envelopSelection(WrapPairs["parentheses"])`
   and update the docstring to note it pins per-edge tagging on
   `_envelopSelection` itself, which the gate constrains to same-kind ends.

3. **Redesign `testNativeTaggedSelectionIsPreserved`** so the selection's ends
   share a kind (the original's [1,3) ends did not, so the new gate rejects it).
   Tag the inner sub-run Native while the selection spans a RomanUrdu end:

   ```python
   def testNativeTaggedSelectionIsPreserved(app: QApplication) -> None:
       """The envelop never replaces the selection: text and tags ride along."""
       widget = PyRaya()
       widget.setPlainText("abcd")
       _select(widget, 1, 3)
       widget.setRegionType(RegionType.Native)  # tag "bc" Native
       _select(widget, 1, 4)  # select "bcd": ends both resolve RomanUrdu
       _keyPress(widget, Qt.Key.Key_ParenLeft, "(")
       assert widget.toPlainText() == "a(bcd)"
       assert widget._regionKindAt(1) is RegionType.RomanUrdu  # opening mark
       assert widget._regionKindAt(2) is RegionType.Native  # 'b'
       assert widget._regionKindAt(3) is RegionType.Native  # 'c'
       assert widget._regionKindAt(4) is RegionType.RomanUrdu  # 'd'
       assert widget._regionKindAt(5) is RegionType.RomanUrdu  # closing mark
   ```

Expected: the file edits are in place; `WrapPairs` is already imported in the
test module (used by `testWrapPairsTableHoldsEveryEnumeratedPair`).

### Step 1.2 (RED): run the gate tests and watch them fail

- `uv run pytest tests/test_auto_wrap.py -k "MismatchedEnds or NativeTagged or MarksCarry"`

Expected: `testMismatchedEndsDoNotEnvelop` FAILS (the gate does not exist yet, so
`_keyPress` envelopes the mismatched selection and produces `ab(cd)` instead of
`ab(`). `testMarksCarryTheKindOfTheirLandingPosition` (now a direct
`_envelopSelection` call) and `testNativeTaggedSelectionIsPreserved` (ends both
RomanUrdu) PASS — they pin existing behavior and are the "keep pinned" half of
the RED step.

### Step 1.3 (GREEN): implement the predicate and swap the gate

- Add `_selectionEndsShareKind()` to `PyRaya` directly after `_typingKindAt`
  (`pyraya_widget.py:3452`):

  ```python
  def _selectionEndsShareKind(self) -> bool:
      """True iff the selection's two ends resolve to the same region kind.

      False without a selection. The gate for selection enveloping: a
      selection straddling a Native / RomanUrdu boundary (whose start and end
      resolve to different kinds) does not envelope.
      """
      cursor = self.textCursor()
      if not cursor.hasSelection():
          return False
      return self._typingKindAt(cursor.selectionStart()) == self._typingKindAt(cursor.selectionEnd())
  ```

- Swap the gate at `pyraya_widget.py:2960-2963` from
  `and self.textCursor().hasSelection()` to `and self._selectionEndsShareKind()`.
  Update the `keyPressEvent` docstring's auto-wrap sentence: the trigger
  character is consumed over a selection *whose two ends resolve to the same
  region kind* (a selection straddling a Native / RomanUrdu boundary does not
  envelope and the trigger types as its plain character instead).

Expected: the edits are in place.

### Step 1.4 (GREEN): run the full suite

- `uv run pytest tests/test_auto_wrap.py`
- `uv run pytest` (full offscreen suite — confirms no other suite regressed).

Expected: `testMismatchedEndsDoNotEnvelop` now PASSES; all three gate tests pass;
full suite green.

### Step 1.5: lint + type

- `uv run ruff check`
- `uv run ruff format`
- `uv run pyrefly check`

Expected: all clean.

### Step 1.6: commit

Stage ONLY the gate changes in `pyraya_widget.py` (NOT the font hunk at
`pyraya_widget.py:99-101`) plus `tests/test_auto_wrap.py`:

- `git add -p src/pyraya/pyraya_widget.py` — select the `_selectionEndsShareKind`
  hunk and the gate-swap hunk; skip the `PyRayaFonts` hunk.
- `git add tests/test_auto_wrap.py`
- Commit: `feat(widget): constrain enveloping to same-kind selections`
  with a body explaining the `_selectionEndsShareKind` gate and that it
  subsumes `hasSelection()`.

Expected: `git status` shows only the font hunk (3 lines in
`pyraya_widget.py`) still modified; `git show --stat` lists
`src/pyraya/pyraya_widget.py` and `tests/test_auto_wrap.py`.

## Task 2: `mirrored` flag on `WrapPair`

### Step 2.1 (RED): write the flag test

In `tests/test_auto_wrap.py`:

```python
def testMirroredFlagMarksQuotePairs(app: QApplication) -> None:
    """The mirrored flag is False exactly on the five quote pairs."""
    unmirrored = {name for name, pair in WrapPairs.items() if not pair.mirrored}
    assert unmirrored == {
        "double-quote",
        "single-quote",
        "low-double-quote",
        "mixed-double-quote",
        "low-single-quote",
    }
    assert sum(1 for pair in WrapPairs.values() if pair.mirrored) == 10
```

Expected: the test is in place.

### Step 2.2 (RED): run it and watch it fail

- `uv run pytest tests/test_auto_wrap.py -k MirroredFlag`

Expected: FAILS — `WrapPair` has no `mirrored` attribute yet
(`AttributeError: 'WrapPair' object has no attribute 'mirrored'`).

### Step 2.3 (GREEN): add the field and set the values

- In `wrapping.py`, add `mirrored: bool` to the `WrapPair` dataclass
  (`:25-42`), after `triggers`. Add a docstring line:
  `mirrored: True for the algorithmic BiDi-mirrored pairs (opening/closing as
  listed in every region), False for the quote pairs that need manual handling
  per region.`
- In the `WrapPairs` table (`:46-65`), set `mirrored=True` on the ten
  bracket/guillemet pairs and `mirrored=False` on the five quote pairs.

Expected: the dataclass and table edits are in place.

### Step 2.4 (GREEN): run the suite

- `uv run pytest tests/test_auto_wrap.py`
- `uv run pytest`

Expected: `testMirroredFlagMarksQuotePairs` PASSES; full suite green.

### Step 2.5: lint + type

- `uv run ruff check`, `uv run ruff format`, `uv run pyrefly check`

Expected: all clean.

### Step 2.6: commit

- `git add src/pyraya/wrapping.py tests/test_auto_wrap.py`
- Commit: `feat(wrapping)!: add mirrored flag to WrapPair` with a body explaining
  the flag (True = algorithmic BiDi mirroring, False = manual per-region
  handling; only RomanUrdu swaps, and only for now) and a
  `BREAKING CHANGE:` footer (`WrapPair` gains a `mirrored` field, exported via
  `pyraya/__init__.py`).

Expected: `git status` clean except the font hunk; `git show --stat` lists
`src/pyraya/wrapping.py` and `tests/test_auto_wrap.py`.

## Task 3: RomanUrdu quote-swap policy

### Step 3.1 (RED): update the two seed quote tests + add a Native no-swap test

In `tests/test_auto_wrap.py`:

1. `testStraightDoubleQuoteEnvelopsInCurlyPair` (`:158`): change the expected
   glyph from `"a\u201cbc\u201dd"` to `"a\u201dbc\u201cd"` (RomanUrdu swaps the
   quote pair's ending assignments). Keep `assert '"' not in widget.toPlainText()`.

2. `testStraightApostropheEnvelopsInSinglePair` (`:169`): change the expected
   glyph from `"a\u2018bc\u2019d"` to `"a\u2019bc\u2018d"`. Keep
   `assert "'" not in widget.toPlainText()`.

3. **New Native no-swap test**:

   ```python
   def testNativeQuotesAreNotSwapped(app: QApplication) -> None:
       """In a Native region the quote pair writes its marks as listed (no swap)."""
       widget = PyRaya()
       widget.setPlainText("abcd")
       _select(widget, 0, 4)
       widget.setRegionType(RegionType.Native)
       _select(widget, 1, 3)
       _keyPress(widget, Qt.Key.Key_QuoteDbl, '"')
       assert widget.toPlainText() == "a\u201cbc\u201dd"
       assert '"' not in widget.toPlainText()
   ```

Expected: the edits are in place.

### Step 3.2 (RED): run them and watch them fail

- `uv run pytest tests/test_auto_wrap.py -k "StraightDoubleQuote or StraightApostrophe or NativeQuotes"`

Expected: `testStraightDoubleQuoteEnvelopsInCurlyPair` and
`testStraightApostropheEnvelopsInSinglePair` FAIL (the swap is not implemented,
so they still produce the as-listed `a\u201cbc\u201dd` / `a\u2018bc\u2019d`).
`testNativeQuotesAreNotSwapped` PASSES (no swap in Native, which is the current
behavior).

### Step 3.3 (GREEN): implement the inline swap in `_envelopSelection`

- In `_envelopSelection` (`pyraya_widget.py:2731-2739`), before the write loop,
  resolve the two marks, swapping them for unmirrored pairs in RomanUrdu:

  ```python
  opening, closing = pair.opening, pair.closing
  if not pair.mirrored and openKind is RegionType.RomanUrdu:
      opening, closing = closing, opening
  ```

  Then write `opening` at `start` and `closing` at `end` (the tags stay
  `openKind`/`closeKind`, which the gate keeps equal). Update the
  `_envelopSelection` docstring: the quote pairs are not BiDi-mirrored, so in a
  RomanUrdu region their opening and closing marks are swapped (closing mark at
  the selection's start, opening mark at its end); mirrored pairs and every
  other region write the marks as listed.

Expected: the edits are in place.

### Step 3.4 (GREEN): run the suite

- `uv run pytest tests/test_auto_wrap.py`
- `uv run pytest`

Expected: `testStraightDoubleQuoteEnvelopsInCurlyPair`,
`testStraightApostropheEnvelopsInSinglePair`, and `testNativeQuotesAreNotSwapped`
all PASS; full suite green.

### Step 3.5: lint + type

- `uv run ruff check`, `uv run ruff format`, `uv run pyrefly check`

Expected: all clean.

### Step 3.6: commit

- `git add -p src/pyraya/pyraya_widget.py` — select the `_envelopSelection` swap
  hunk; skip the `PyRayaFonts` hunk.
- `git add tests/test_auto_wrap.py`
- Commit: `feat(widget): swap RomanUrdu quote pairs' ending assignments`
  with a body explaining the inline swap policy.

Expected: `git status` shows only the font hunk still modified; `git show --stat`
lists `src/pyraya/pyraya_widget.py` and `tests/test_auto_wrap.py`.

## Task 4: docs

### Step 4.1: AGENTS.md auto-wrap bullet

- Line 15 (the `**Auto-wrap**` bullet): add the same-kind gate and the RomanUrdu
  quote-swap. State that enveloping is restricted to selections whose two ends
  resolve to the same region kind (`_selectionEndsShareKind`); a selection
  straddling a Native / RomanUrdu boundary does not envelope (the trigger types
  as its plain character instead); the quote pairs are not BiDi-mirrored, so in
  a RomanUrdu region their opening and closing marks are swapped (the closing
  mark at the selection's start, the opening mark at its end) while mirrored
  pairs and every other region write the marks as listed.
- Add the region-extension contract sentence: a new region defines its own
  handling of unmirrored pairs (for now only RomanUrdu swaps; a future region
  either keeps the as-listed assignment or adds its own swap).

### Step 4.2: AGENTS.md region bullet + Testing section

- The region bullet (the `**Text regions**` bullet, line ~6): add a sentence that
  region extension is governed by the auto-wrap contract — a new region defines
  its own handling of unmirrored quote pairs.
- Line 104 (Testing section, the `test_auto_wrap.py` description): update the
  write-contract wording to reflect the gate — "a span straddling a Native /
  Roman Urdu boundary tags each mark at its own edge" is now the
  `_envelopSelection` per-edge pin (bypassing the gate); the gate itself is
  pinned by `testMismatchedEndsDoNotEnvelop`, the quote-swap by
  `testStraightDoubleQuoteEnvelopsInCurlyPair` / `testStraightApostropheEnvelopsInSinglePair`
  / `testNativeQuotesAreNotSwapped`.

### Step 4.3: README.md (if warranted)

- README.md lines 6, 54 mention the font stack generically ("a Nastaliq font
  stack"). Only update if the font addition (Task 5) makes a specific claim
  stale; otherwise leave the generic wording.

### Step 4.4: docstrings

- `keyPressEvent` (`pyraya_widget.py:2920-2950`): the auto-wrap sentence already
  updated in Task 1 Step 1.3; confirm it reads correctly here (no edit needed if
  Task 1 covered it).
- `_envelopSelection` (`pyraya_widget.py:2689-2751`): the swap-policy sentence
  already added in Task 3 Step 3.3; confirm it reads correctly here (no edit
  needed if Task 3 covered it).
- `wrapping.py` module docstring (`:4-19`) and `WrapPair` docstring (`:27-37`):
  confirm the `mirrored` field is documented (added in Task 2 Step 2.3).

Expected: the docstrings are consistent with the implemented behavior (no
stale wording).

### Step 4.5: CHANGELOG.md

- Under `## [Unreleased] > Added`, fold the gate + policy into the existing
  auto-wrap entry (lines 14-28). Add: enveloping is restricted to selections
  whose two ends resolve to the same region kind (`_selectionEndsShareKind`);
  the quote pairs are not BiDi-mirrored, so in a RomanUrdu region their opening
  and closing marks are swapped (the closing mark at the selection's start, the
  opening mark at its end), while mirrored pairs and other regions write the
  marks as listed.

Expected: the entry reads as one coherent description of the feature.

### Step 4.6: commit (docs + plan file)

- `git add AGENTS.md README.md CHANGELOG.md docs/superpowers/plans/2026-11-15-mirrored-quotes.md`
  (add README.md only if Step 4.3 changed it).
- Commit: `docs: same-kind gate, RomanUrdu quote-swap, and font-stack plan`
  with a body listing the doc updates.

Expected: `git status` shows only the font hunk still modified; `git show --stat`
lists `AGENTS.md`, `CHANGELOG.md`, the plan file, and (if touched) `README.md`.

## Task 5: font stack pin

### Step 5.1 (RED): write the font-stack pin test

In `tests/test_pyraya.py`:

```python
def testFontStackLeadsWithTheNewFamilies(app: QApplication) -> None:
    """The font stack leads with the three added families, in order."""
    assert PyRayaFonts[:3] == (
        "Kawkab Mono",
        "Mehr Nastaliq Web",
        "Jameel Noori Nastaleeq",
    )
```

(Import `PyRayaFonts` from `pyraya`.)

### Step 5.2 (RED): watch it fail by stashing the font hunk

- `git stash push src/pyraya/pyraya_widget.py` (stashes the font hunk).
- `uv run pytest tests/test_pyraya.py -k FontStack`

Expected: FAILS — with the font hunk stashed, `PyRayaFonts[:3]` is
`("Baloo Bhaijaan 2", "Noto Naskh Arabic", "Noto Nastaliq Urdu")`.

### Step 5.3 (GREEN): restore the font hunk

- `git stash pop` (restores the font hunk).
- `uv run pytest tests/test_pyraya.py -k FontStack`

Expected: PASSES — `PyRayaFonts[:3]` is the three new families.

### Step 5.4: update the `PyRaya` class docstring

- `pyraya_widget.py:711-713`: the class docstring says "default ``Baloo
  Bhaijaan 2``, the first installed entry of :data:`PyRayaFonts`". Update it to
  reflect the new default: "default ``Kawkab Mono``, the first installed entry
  of :data:`PyRayaFonts`".

Expected: the docstring is in place.

### Step 5.5: AGENTS.md + CHANGELOG.md

- AGENTS.md line 8: "a configurable font stack (default `Baloo Bhaijaan 2` —
  `PyRayaFonts`'s first installed entry, ...)". Update to: default `Kawkab
  Mono`, the first installed entry of `PyRayaFonts`, the Nastaliq web/mono
  fonts follow it.
- CHANGELOG.md under `## [Unreleased]`: add a `### Changed` line for the font
  stack — the preferred font stack now leads with `Kawkab Mono`, `Mehr
  Nastaliq Web`, and `Jameel Noori Nastaleeq` (the default is the first
  installed entry, `Kawkab Mono`).

Expected: the docs are in place.

### Step 5.6: lint + type

- `uv run ruff check`, `uv run ruff format`, `uv run pyrefly check`

Expected: all clean.

### Step 5.7: commit

- `git add src/pyraya/pyraya_widget.py tests/test_pyraya.py AGENTS.md CHANGELOG.md`
  (stages the font hunk + the `PyRaya` docstring + the docs).
- Commit: `feat(widget): lead the font stack with Kawkab Mono, Mehr Nastaliq
  Web, Jameel Noori Nastaleeq` with a body noting the new default.

Expected: `git status` clean; `git show --stat` lists `src/pyraya/pyraya_widget.py`,
`tests/test_pyraya.py`, `AGENTS.md`, `CHANGELOG.md`.

## Review Focus

The reviewer should deliberately check, beyond the tests:

- **Gate correctness on block boundaries.** `_selectionEndsShareKind` reads
  `_typingKindAt(selectionStart())` and `_typingKindAt(selectionEnd())`. Verify
  the predicate is correct when the selection spans a block separator
  (`testMultiLineSelectionGetsASinglePair` covers this: ends both seed-RomanUrdu,
  so the gate accepts and the envelop still happens). Confirm the gate does not
  reject a legitimate same-kind multi-line selection.
- **Swap policy vs. the gate's guarantee.** The swap reads `openKind` and trusts
  the gate that `openKind == closeKind`. Confirm the tags (`openKind`/
  `closeKind`) stay correct when the marks are swapped — a swapped mark still
  carries its own landing kind, not the other end's.
- **No font hunk in Tasks 1-3 commits.** Confirm `git show <Task 1 commit>` and
  `<Task 3 commit>` do NOT touch `pyrayaFonts` / `PyRayaFonts` (the three new
  families appear only in the Task 5 commit).
- **`mirrored` on guillemets.** Confirm `guillemets` and `single-guillemets` are
  `mirrored=True` (they are bracket/guillemet pairs, algorithmic), and only the
  five `*quote` pairs are `mirrored=False`.
- **No behavioral leak.** The gate and swap must not change the bracket pairs'
  behavior (they are `mirrored=True`, so the swap is a no-op for them) or the
  Native-region quote behavior (no swap in Native, pinned by
  `testNativeQuotesAreNotSwapped`).

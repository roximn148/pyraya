# PyRaya Region Model Re-derivation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the colour-as-identity region model with kinds stored as a custom
integer property on the character format, resolved in two steps (stored tag →
widget seed), so regions record intent instead of appearance.

**Architecture:** Kinds are a closed `IntEnum` (`Native`, `RomanUrdu`) written as
`QTextFormat.Property.UserProperty + 1` on the document's character formats
(nothing else stores region data). The seed — copied from a module-level initial
value at construction, read-only afterwards — resolves untagged text. The
palette becomes view-only; the paint pass merges each *resolved* kind's colour
into the layout and skips colourless (Native) fragments; undo/redo of
format-only tag writes is re-highlighted explicitly (probe C: Qt does not
re-highlight format-only writes or their undo).

**Tech Stack:** Python 3.14, PySide6 (offscreen tests), uv, pytest, ruff (100 cols),
pyrefly.

**Spec:** `docs/superpowers/specs/2026-10-23-region-model-re-derivation.md`
(the origin message "PyRaya region model re-derivation" — reproduced in
"Global Constraints" below; the plan argues from it). Two delegated decisions
were made by the human partner: `setRegionType` **stays selection-only**; the
**HTML export helper is deferred**.

## Verification already done (probes, offscreen, 2026-10-22/23)

Run via `uv run python` against throwaway scripts; recorded because later tasks
lean on them:

- **(A) passes** — a custom property on the last character of a block survives
  Enter: the new block's `block.charFormat()` carries
  `hasProperty(UserProperty+1) == True`, and the first character typed into that
  empty block (default widget key handling) carries the same property. Qt's
  `insertBlock` seeds the new block with `cursor.charFormat()`, and empty-block
  typing takes `block.charFormat()`. Hook-free Enter continuation works.
- **(B) passes** — per-character properties survive a block join in both
  directions (`cursor.deleteChar()` on the separator from the previous block,
  `cursor.deletePreviousChar()` at the next block's start): fragments after the
  join read `(unset, stored)` exactly as tagged.
- **(C) new finding, decisive** — `mergeCharFormat`/`setCharFormat` writes that
  change *only* a custom property do **not** trigger a `QSyntaxHighlighter`
  re-highlight; **undoing them does not either**. Consequence: tag-property
  writes re-highlight their affected blocks explicitly, and `PyRaya.undo()` /
  `PyRaya.redo()` gains a bounded whole-document re-highlight gated on a
  `_pendingTagRepaint` flag set by every tag write.
- **(D) passes** — format changes are undoable: undo removes the property,
  redo restores it, and this is one `deletePreviousChar`-class edit step.

## Global Constraints (from the spec, verbatim decisions)

- A region kind is an integer stored as a custom property on the CHARACTER
  format (`QTextFormat.Property.UserProperty + n`). Nothing else stores region
  data.
- Resolution: fragment's stored property → else the widget's seed. Two steps.
  No paragraph level. Kinds are a CLOSED enum: Native, RomanUrdu.
- Native: no behaviour, no colour, stored only when the user states it.
  RomanUrdu: the only kind that arms processing (overlay, spell-check).
- The seed is fixed at construction, exposed read-only (a module-level initial
  value seeds the property, mirroring how RegionColors seeds the palette).
- A stored tag always wins, even when it equals the seed. Tags record intent;
  do not canonicalise or clear redundant tags on write.
- Untagged text resolves to the seed. "Every character has exactly one kind"
  survives as a statement about resolution, not storage.
- Kind is never derived from appearance. The palette is view-only.
- Enter at a tagged paragraph's end continues its kind with no hook and no
  write — provided the tag covers the paragraph's TRAILING WHITESPACE.
- `setRegionType` / `clearRegions` are document writes, one undo step each.
  `clearRegions` removes intent (behaviourally invisible where tags equal the
  seed); its write is a batch apply inside ONE edit block replaying every
  stored span.
- `setRegionColor` writes nothing to the document and emits NO `regionsChanged`.
- ASCII typing inside RomanUrdu seeds the overlay; inside Native it types
  through. Spell-check stays RomanUrdu-only.
- Delete: colour-as-identity (`_regionColorMatch`/`_regionKindFor`), the wash's
  inference, `_clearRange`'s default repaint, the NoBrush-beside-tagged
  reconciliation, `RegionType.Latin`, `DefaultRegionKind`, the total-partition
  claim in docs.
- Keep untouched: overlay geometry, flip/truncation, mouse transparency, commit
  matrix, assist mode, resize/scroll re-anchoring, the lazy
  `RomanInputEngine`, the rule highlighter's foreground behaviour.
- Renames/labels decided by this plan: enum members `RegionType.Native = 1`,
  `RegionType.RomanUrdu = 2` (1-based; 0 is the unset sentinel
  `intProperty` returns); context-menu labels "Region: Native" / "Region:
  Roman Urdu"; `Ctrl+1` tags Native, `Ctrl+2` tags RomanUrdu; seed exported as
  `SeedRegionKind: RegionType = RegionType.RomanUrdu`; widget accessor
  `seedRegionKind()` (read-only: no setter, no constructor parameter).
- Version bump to `0.1.0-alpha.8` (public API breaks), `uv lock`, README
  version string.

## Review Focus

1. **Enter continuation silently falling back to the seed** when the tag does
   not cover the paragraph's trailing whitespace — expected: a Native tag
   ending before trailing whitespace does NOT continue past Enter; the user's
   expectation set by the new tests is tag-includes-whitespace → continues.
   *Pinned by:* `testEnterAtEndOfTaggedParagraphContinuesItsKind` (Task 2).
2. **Stale layout tint after undo/redo of a tag write** (probe C: no
   re-highlight fires) — expected: the tint follows the resolved kind
   immediately after undo/redo. *Pinned by:*
   `testUndoOfRegionWriteRepaintsTheLayout` (Task 2).
3. **A stored tag that equals the seed must still be stored and win** —
   expected: `regionTypeAt`/`regions()` read the stored property first; tests
   must verify storage via the property, not via resolution (which is
   identical). *Pinned by:* `testStoredTagWinsOverIdenticalSeed` (Task 2).
4. **Tag writes spanning the trailing terminator** (merges across it are
   silently dropped) — expected: clamped writes never touch the terminator and
   never print "out of range" warnings. *Pinned by:*
   `testRunBasedEdgeDocuments` (kept, parametrize updated) and
   `testContextMenuAtTextEdgesNoOutOfRangeCursor` (kept).
5. **Recolour is view-only** — expected: `setRegionColor` leaves
   `document().revision()` unchanged, emits nothing, and the new colour still
   reaches the layout through the paint pass. *Pinned by:*
   `testSetRegionColorTouchesNoDocument` (Task 2) +
   `testSetRegionColorRehighlightsTheTint` (Task 2).

---

### Task 1: Model tests and suite re-pointing (red by design)

**Files:**
- Create: `tests/test_regions_model.py`
- Modify: `tests/test_pyraya.py`, `tests/test_region_runs.py`,
  `tests/test_spellcheck.py`, `tests/test_roman_input.py`

**Interfaces:**
- Consumes: nothing new (current `pyraya` imports; `RegionType` ids).
- Produces (tests only in this task — the API they exercise is Task 2's
  deliverable): `pyraya.RegionType` closed {Native, RomanUrdu} with values
  (1, 2); `pyraya.SeedRegionKind` (RomanUrdu); `pyraya.RegionKindProperty`
  (`int(QTextFormat.Property.UserProperty) + 1`); `pyraya.resolveRegionKind(fmt, seed)`;
  `pyraya.RegionColors` → `{RomanUrdu: amber}`; widget `seedRegionKind()`.

- [ ] **Step 1: Write `tests/test_regions_model.py`** (the model is import-exact;
      every name below becomes the contract for Task 3):

```python
# assertions (write as individual tests, offscreen app fixture as usual, 100 cols):
def testClosedEnum(): set(RegionType) == {RegionType.Native, RegionType.RomanUrdu}
def testOneBasedValues(): (RegionType.Native, RegionType.RomanUrdu) == (1, 2)  # 0 = unset sentinel
def testPropertyId(): RegionKindProperty == int(QTextFormat.Property.UserProperty) + 1
def testSeedIsReadOnlyModuleValue(): SeedRegionKind is RegionType.RomanUrdu
def testResolveRegionKindUnstoredGivesSeed():
    assert resolveRegionKind(QTextCharFormat(), RegionType.Native) is RegionType.Native
def testStoredTagWinsOverSeedEvenWhenEqual():
    fmt = QTextCharFormat(); fmt.setProperty(RegionKindProperty, int(RegionType.RomanUrdu))
    assert resolveRegionKind(fmt, RegionType.RomanUrdu) is RegionType.RomanUrdu
def testStoredNativeWinsOverRomanSeed():
    fmt.setProperty(RegionKindProperty, int(RegionType.Native))
    assert resolveRegionKind(fmt, RegionType.RomanUrdu) is RegionType.Native
def testForeignIntFallsBackToSeed():  # defensive: closed enum rejects 7
    fmt.setProperty(RegionKindProperty, 7)
    assert resolveRegionKind(fmt, RegionType.Native) is RegionType.Native
def testPaletteDefaultsViewOnly():
    set(RegionColors) == {RegionType.RomanUrdu}  # Native is colourless
    and 0 < RegionColors[RegionType.RomanUrdu].alpha() < 255
```

- [ ] **Step 2: Rewrite the failing-by-design tests** (rewrite, never delete;
      the full list so nothing is missed):

`tests/test_pyraya.py`:
- `testRegionTypesDefined` → `assert set(RegionType) == {RegionType.Native, RegionType.RomanUrdu}`.
- `testRegionColorsAreDistinctAndSubtle` → single colourable kind, semi-transparent alpha.
- Latin-tag tests rewritten to `RegionType.Native`:
  `testSetRegionTypeFromSelection`, `testSetRegionTypeSplitsAndRetags`,
  `testSetRegionTypeMergesAdjacent`, `testRegionSpansBlocks`,
  `testRegionPersistsThroughInsertion`, `testRegionPersistsThroughDeletion`,
  `testRegionPersistsThroughUndoRedo`, `testRegionTypeAt`,
  `testRegionTypeAtTerminatorOffsetIsNone`, `testPopupMenuRegionActions`,
  `testPopupMenuDisabledWithoutSelection`, `testKeyboardShortcutsAssignRegions`
  (`Ctrl+1` → Native; `Ctrl+2` keeps RomanUrdu).
- spans over untagged text now report `RegionType.RomanUrdu` (the seed) —
  same expected values as today, so only names/comments change:
  `testSetRegionTypeExplicitRange`, `testSetRegionTypeNoSelectionIsNoop`,
  `testSetTextRetagsAsDefault` (→ rename `testSetTextResolvesToSeed`),
  `testSetPlainTextTagsAllTextAsDefault` (→ `testSetPlainTextResolvesToSeed`),
  `testFirstTypedCharacterGetsDefaultKind` (→
  `testFirstTypedCharacterResolvesToSeed`), `testClearRegionsResetsToDefault`
  (→ `testClearRegionsRemovesTagIntent`; assert the doc holds no stored tag
  afterwards *and* `regions()` == the seed partition).
- `testDefaultRegionKindIsDefined` → replaced by
  `testSeedRegionKindIsRomanUrdu` (element of test_regions_model.py).
- `testSetRegionColorRecolours` → palette-only: widget palette updated, module
  default untouched, `regions()` unchanged.
- `testRegionColorPaletteIsPerWidget`, `testRegionColorsReturnsAnIndependentCopy`
  → keep, trimmed to "module default untouched" (rationale text updated).
- `testSetRegionColorRejectsDuplicateColor`, `testSetRegionColorAlphaIsIdentity`
  → DELETE (colour-as-identity is gone).
- `testSetRegionColorRehighlightsTheDefaultWash` →
  `testSetRegionColorRehighlightsTheTint`: recolour `RegionType.RomanUrdu`,
  assert the layout formats show the new colour AND
  `document().revision()` unchanged.
- Wash pair: `testUntaggedLatinKeepsRuleForegroundUnderDefaultWash` →
  `testUntaggedLatinKeepsRuleForegroundUnderKindTint`,
  `testUntaggedWhitespaceKeepsDesignedDotColor` (keep name): untagged fixtures
  (seed RomanUrdu) keep the rule foregrounds; observed wash colour read via
  `widget.regionColors()[RegionType.RomanUrdu]`.
- `testRegionsChangedSignal`, `testRegionsChangedFiresForDefaultRepaint`,
  `testKeyboardShortcutsIgnoredWithoutSelection`,
  `testSetRegionTypeExplicitRange` keep assertions; docstrings re-worded.

New tests this task (all assert the NEW model):
- `testEnterAtEndOfTaggedParagraphContinuesItsKind` (Review Focus 1):
  `setPlainText("سلام ")` → widget tag Native, `[0, len("سلام "))` (explicit end,
  trailing whitespace included) → `keyPressEvent` Enter → the new block's
  `block.charFormat().hasProperty(RegionKindProperty)` is True with value
  `int(RegionType.Native)`; then keystroke `Key_A`/`"a"` (assist ON, default)
  types THROUGH: `regionTypeAt(new char)` is Native, text contains "a", overlay
  inactive, no overlay created.
- `testStoredTagWinsOverIdenticalSeed` (Review Focus 3): seed RomanUrdu,
  `setRegionType(RegionType.RomanUrdu, 0, 4)` on non-empty text → the character
  format at each position has the property and resolves RomanUrdu;
  `regions()` reports one merged RomanUrdu span (adjacent equal kinds merge).
- `testRegionColorTouchesNoDocument` (Review Focus 5):
  revision before == after `setRegionColor(RomanUrdu, new)` (True), no
  `regionsChanged`, `regions()` unchanged.
- `testBatchClearIsOneUndoStepAndUndoRestoresEverySpan` (Review list, one
  undo): two Native tags + one RomanUrdu tag on one document →
  `clearRegions()` → no stored property anywhere → ONE `undo()` restores all
  three stored tags (`regions()` and `regionTypeAt` back).
- `testUndoOfRegionWriteRepaintsTheLayout` (Review Focus 2): tag Native on a
  block, read the layout shows NO tint for it; `undo()` → the layout shows the
  seed tint again WITHOUT any other event (assert immediately, no
  processEvents beyond the undo call).
- `testSeedIsReadOnlyAfterConstruction`: `widget.seedRegionKind() is
  SeedRegionKind` and no `setSeed*`/`setSeedRegionKind` in
  `[n for n in dir(PyRaya) if "seed" in n.lower()]`.
- `testNativeKeystrokesTypeThroughTheGate` (spec requirement 9): cursor inside
  a Native span, `_keyPress(Key_A, "a")` (assist on) → text lands, no overlay,
  the char resolves Native.
- `testNativeHoleInsideTintedParagraph`: untagged paragraph -
  `setRegionType(RegionType.Native, 2, 5)` around untagged seed text →
  `regions()` == [(0,2,RomanUrdu),(2,5,Native),(5,n,RomanUrdu)]; layout
  formats: chars 2..4 have NO background; chars at 0..1 and the tail keep the
  RomanUrdu tint and the rule foregrounds.

`tests/test_region_runs.py`:
- `_referenceKindAt` re-implemented on the property: read the char format at
  the position, `resolveRegionKind(fmt, widget.seedRegionKind())`.
- `testRunBasedEdgeDocuments`: parametrize keys stay; the two tag calls become
  Native `[0, characterCount())`, then RomanUrdu `[0, characterCount() - 1)` (wait
  — pending: RomanUrdu call clamped end). Module docstring: drop
  NoBrush-beside-tagged rationale; keep the per-character parity claim.
- `testAdjacentWordInsideARunReturnsTheContainingRun`: untouched.

`tests/test_spellcheck.py`:
- `testLatinRegionNotUnderlined` → Native tag exemption rewrite.
- `testTaggedRomanUrduRegionChecked` → `(0, 4)` Native + `(5, 9)` RomanUrdu;
  only the RomanUrdu word is underlined. All other tests keep (they read
  layout underline ranges, kinds resolve as before).

`tests/test_roman_input.py`:
- `setRegionType(RegionType.Latin, ...)` call sites → Native (lines ~829, 975,
  992, 2350, 3150) and the island assertion at ~3163 →
  `assert RegionType.Native in [span.kind for span in widget.regions()]` —
  review the assertion's intent when editing (the island must exist as its own
  span, not merely not-be-RomanUrdu).
- every other `setRegionType(RegionType.RomanUrdu, ...)` call: unchanged (tags
  equal to the seed behave identically); `_regionKindAt` assertions unchanged
  (resolved kinds are the same numbers).

- [ ] **Step 3: Run the new model file to verify it fails**

Run: `uv run pytest tests/test_regions_model.py -q`
Expected: collection/ImportError (`RegionKindProperty` undefined) — red by
design; the suite stays red until Task 2.

- [ ] **Step 4: Commit**

```bash
git add tests/ && git commit -m "test: re-point the region suite at the re-derived model (red by design)"
```

---

### Task 2: Model, widget, and highlighter swap (red → green)

**Files:**
- Modify: `src/pyraya/regions.py` (full rewrite), `src/pyraya/__init__.py`,
  `src/pyraya/pyraya_widget.py`, `src/pyraya/roman_input.py` (only if region
  references exist — grep says none; verify).

**Interfaces:**
- Consumes: Task 1's test names/assertions.
- Produces (exact signatures pyrefly must honour):

```python
# src/pyraya/regions.py — full rewrite of the model, keep TextRegion as-is
class RegionType(IntEnum):
    """Closed region kinds. Native has no behaviour and no colour..."""
    Native = 1
    RomanUrdu = 2

RegionKindProperty: int          # int(QTextFormat.Property.UserProperty) + 1
SeedRegionKind: RegionType       # = RegionType.RomanUrdu (module initial value)
RegionColors: dict[RegionType, QColor]  # {RomanUrdu: amber}; Native colourless

def resolveRegionKind(charFormat: QTextCharFormat, seed: RegionType) -> RegionType:
    """Two-step resolution: stored property, else ``seed`` (defensive ValueError
    → seed; intProperty's unset sentinel 0 maps to no kind)."""

# src/pyraya/pyraya_widget.py — public surface
PyRaya.seedRegionKind(self) -> RegionType            # read-only accessor
PyRaya.setRegionType(self, kind, start=None, end=None) -> None   # selection-only fallback kept
PyRaya.regionTypeAt(self, position) -> RegionType | None
PyRaya.clearRegions(self) -> None
PyRaya.setRegionColor(self, kind, color) -> bool     # palette-only; False for colourless kinds
PyRaya.regions(self) -> list[TextRegion]             # resolved kinds, unstored reports the seed
PyRayaHighlighter.__init__(self, document, engineProvider=None, colors=None, seed=None)
```

- Internal shape (decided; same file): module-level `_regionColorMatch` and
  `_regionKindAt(... , palette ...)` deleted; `_backgroundRuns` → `_kindRuns`
  (returns `(start, end, RegionType)` triples, adjacent same-kind merged,
  covered to `characterCount() - 1`, separators read via `resolveRegionKind`
  over `_charFormatAt`); `_paintDefaultRegions` → `_paintResolvedKinds`;
  `_blockRegionRuns` / `_kindInRuns` resolve via
  `resolveRegionKind(fragment.charFormat(), seed)`; `_charFormatAt` kept.

- [ ] **Step 1: Rewrite `src/pyraya/regions.py`** exactly per Interfaces above.
      Include: the closed `IntEnum` (values 1/2 with a docstring note that 0 is
      the unset sentinel), `RegionKindProperty`, `SeedRegionKind`, one-entry
      `RegionColors`, `resolveRegionKind` (module-level owner of the two-step).
      Keep the copyright banner and Google-style docstrings.

- [ ] **Step 2: Update `src/pyraya/__init__.py`** — exports:
      `-DefaultRegionKind, +RegionKindProperty, +SeedRegionKind,
      +resolveRegionKind` in `__all__` (order preserved otherwise).

- [ ] **Step 3: Widget read path** — replace every colour-as-identity read with
      the two-step resolution:
      - widget `__init__`: `self._seedRegionKind: RegionType = SeedRegionKind`
        (before the highlighter), `self._pendingTagRepaint: bool = False`, and
        pass `seed=self._seedRegionKind` into `PyRayaHighlighter`.
      - `_regionAt`, `_regionUnderCursor`, `regionTypeAt`, `regions()`,
        `_regionSpans`, `_kindRuns`, `_regionKindAt` per Interfaces.
      - `_wordUnderCursor`: unchanged shape; kinds resolve stored → seed.
- [ ] **Step 4: Widget write path**:
      - `setRegionType`: clamp as today (`_clampRange`); guard selection-only
        fallback (unchanged per the human partner's decision);
        `fmt = QTextCharFormat(); fmt.setProperty(RegionKindProperty,
        int(kind))`; fresh-cursor `mergeCharFormat` over `[start, end)`; then
        `_rehighlightTags(start, end)` (per-block `rehighlightBlock` bounce paid
        inside like `_blockRegionRuns` walks fragments — implement as
        `blockFrom`/`blockTo` walk calling `rehighlightBlock`) — set
        `self._pendingTagRepaint = True` before returning; emit `regionsChanged`
        as today.
      - `clearRegions`: collect stored-tag fragment ranges (`hasProperty(RegionKindProperty)`
        on the fragment format, walk via the block iterator cast used in
        `_kindRuns`; skip the trailing terminator); `if not ranges: return`;
        `document().beginEditBlock()` … for each range fresh cursor +
        `cursor.setCharFormat(copy_of_fragment_charFormat_with_clearProperty(RegionKindProperty))`
        … `endEditBlock()` (ONE undo step, every stored span replayed);
        `rehighlight()`; `_pendingTagRepaint = True`; emit `regionsChanged`.
        DELETE `_clearRange`.
      - `_writeCommit` (overlay commit tag): `fmt = QTextCharFormat()` with the
        region property set to `int(RegionType.RomanUrdu)`; `insertText(word +
        separator, fmt)` (text edit → re-highlight automatic); keep the
        `regionsChanged` emit and `romanWordCommitted` contract.
      - `setRegionColor`: palette-only — reject colourless kinds (Native) with
        False where the palette has no entry; `self._regionColors[kind] =
        color`; `self._highlighter.rehighlight()`; return True. NO document
        write, NO `regionsChanged`, no blocking-signals block, no run-recolor
        walk (its reason is gone).
      - `undo()` / `redo()` overrides: `super().undo()`; if
        `self._pendingTagRepaint`: `self._pendingTagRepaint = False` and
        `self._highlighter.rehighlight()` (bounded repair for probe C; possibly
        one whole-doc re-highlight per undo chain after a tag write — accepted).
      - `_regionKindForTyping` per requirement 3 (exact algorithm):

```python
def _typingKindAt(self, position: int) -> RegionType:
    """The kind a character typed at ``position`` carries (fragment
    at/before the cursor; empty block / block start → block.charFormat()."""
    document = self.document()
    if position == document.characterCount() - 1 and position > 0:
        position -= 1  # document end: the last real character governs
    block = document.findBlock(position)
    if not block.isValid():  # setPlainText mid-flight guard, as _wordUnderCursor
        return self._seedRegionKind
    if position - block.position() == 0:
        return resolveRegionKind(block.charFormat(), self._seedRegionKind)
    return self._regionKindAt(position)


def _regionKindForTyping(self) -> RegionType | None:
    """Gate kind; None only for positions past the document end."""
    cursor = self.textCursor()
    document = self.document()
    limit = document.characterCount() - 1
    if limit <= 0:
        return self._seedRegionKind  # empty document
    if cursor.hasSelection():
        return self._typingKindAt(cursor.selectionStart())
    position = cursor.position()
    if not 0 <= position <= limit:
        return None
    return self._typingKindAt(position)
```

- [ ] **Step 5: Highlighter** — constructor gets `seed: RegionType | None =
      None` (default `SeedRegionKind`); `highlightBlock` calls
      `_paintResolvedKinds(block)` which per fragment resolves the kind, skips
      colourless kinds (`palette.get(kind) is None` → skip), and merges the
      kind's colour per `_uniformRuns` (keep the merge-not-replace idiom);
      `_blockRegionRuns` resolves via `resolveRegionKind(...)`; `_kindInRuns`
      falls back to `self._seed`; `_underlineUnknownWords` stays RomanUrdu-only
      (both ends RomanUrdu, candidate-scan-first engine gating intact).
- [ ] **Step 6: Context menu / shortcuts** — labels "Region: Native" and
      "Region: Roman Urdu"; `Ctrl+1` → `RegionType.Native`. Docstrings on all
      touched methods rewritten to the new model (resolution statement, not
      total-partition claim).
- [ ] **Step 7: Run the model file green**

Run: `uv run pytest tests/test_regions_model.py -q`
Expected: PASS.

- [ ] **Step 8: Run the roman-input suite as a migration tripwire**

Run: `uv run pytest tests/test_roman_input.py -q`
Expected: PASS except the Latin-listed commits named in Task 1 Step 2 — those
fail on `RegionType.Latin` usage until rewritten; after the routine rename they
pass. Everything else (commit matrix, geometry, assist) must be untouched.

- [ ] **Step 9: Commit**

```bash
git add src/ tests/ && git commit -m "feat: store region kinds on character formats, resolve in two steps"
```

---

### Task 3: Full suite green, lint/type clean

**Files:** Modify: `tests/` fallout only, `src/pyraya/*.py` fallout only.

- [ ] **Step 1: `uv run pytest -q`** — Expected: 0 failed. Fix fallout ONLY
      where a test's assertion genuinely contradicted the model contract over
      the probed property behaviour — comment about what it means when found.
- [ ] **Step 2: `uv run ruff check && uv run ruff format`** — Expected: clean
      (format unchanged or committed).
- [ ] **Step 3: `uv run pyrefly check`** — Expected: 0 errors. Watch the
      `_kindRuns` fragment-walk casts (reuse the `Iterable[QTextBlock.iterator]`
      cast) and `intProperty`-typed reads.
- [ ] **Step 4: `PYRAYA_LATENCY=1 uv run pytest tests/test_latency.py -s -q`**
      — budget rows still pass (regions scan is one read per kept run, cheaper
      than before).
- [ ] **Step 5: Commit** (only if fixes were needed; otherwise fold into the
      next commit):

```bash
git add -A && git commit -m "fix: region model fallout — full suite and tooling clean"
```

---

### Task 4: Docs rewrite and version bump

**Files:** Modify: `AGENTS.md`, `README.md`, `pyproject.toml`, `uv.lock`.

- [ ] **Step 1: Rewrite the region-model sections** — do not append; remove
      wash / Q-1 / Q-2 rationale that no longer applies; KEEP and re-point:
      the setFormat-replaces trap, the block-terminator drops, the
      stale-QTextBlock rule; ADD the probe findings worth keeping as gotchas:
      format-only writes do not re-highlight (tag writes re-highlight their
      blocks; undo/redo relies on `_pendingTagRepaint`); block.charFormat()
      neither paints nor merges (Enter continuation rides stored properties).
      Update: regions → kinds Native/RomanUrdu, seed read-only, stored-vs-
      unstored intent, the Q-2 contract → setRegionColor repaints only,
      clearRegions removes intent, Enter continuation and tag-trailing-
      whitespace note, Ctrl+1 menu labels.
- [ ] **Step 2: Rewrite the README regions/spell/features prose** — kinds, no
      "every character belongs to exactly one kind" as storage claim; state
      resolution ("untagged text acts as RomanUrdu"); Native has no tint.
- [ ] **Step 3: Version bump**: `pyproject.toml` → `0.1.0-alpha.8`, `uv lock`,
      README header string update.
- [ ] **Step 4: Final verify**
      `uv run pytest -q && uv run ruff check && uv run pyrefly check` — 0
      failures/errors.
- [ ] **Step 5: Commit**

```bash
git add AGENTS.md README.md pyproject.toml uv.lock && git commit -m "docs: region model rewrite; version 0.1.0-alpha.8"
```

---

## Self-review log

- Spec coverage: every Required-behaviour item maps to a task — (1) palette
  view-only → Task 1 tests + Task 2 paint; (2) read path → Task 2 Step 3;
  (3) gate → Task 2 Step 4; (4) Enter continuation → Task 1 test + probe A +
  Task 2 (no hook); (5) Native appearance → Native-hole test; (6) writes/undo
  → Task 2 Step 4 + Task 1 clear test; (7) `regions()` contract → Interfaces +
  Task 1; (8) setRegionColor → Task 1 + Task 2; (9) gate behaviour → Task 1;
  (10) spell-check → Task 1 spellcheck rewrite + Task 2 Step 5.
- Delete list is covered by the test rewrite list + Task 2 Steps 3–5 and 6.
- Type consistency: `resolveRegionKind`, `SeedRegionKind`, `RegionKindProperty`,
  `seedRegionKind()`, `_kindRuns`, `_paintResolvedKinds`, `_rehighlightTags`,
  `_typingKindAt`, `_pendingTagRepaint` — consistent across tasks.
- Review Focus lines 1–5 each have a named owning test (Task 1 Step 2).
- Post-execution note (2026-10-23): probe C's premise ("format-only writes and their undo do not trigger a re-highlight") did not reproduce on the shipped dependency set — measured twice (reviewer + executor probes): Qt auto-re-highlights the property-merge write and its undo/redo through its own contentsChange reactions, and the Python `undo()`/`redo()` overrides are dispatched for programmatic undo/redo only (keyboard Ctrl+Z bypasses them). Kept `_pendingTagRepaint` + overrides as belt-and-braces; corrected in AGENTS.md and the touched docstrings ("Measured correction").

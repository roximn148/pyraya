# PyRaya Gutter (line numbers) — Design Spec

- **Date:** 2026-11-15
- **Status:** Agreed in-conversation 2026-11-15
- **Target version:** 0.1.0-alpha.15 (bump lands with this feature; no cut here — the entry
  stays under `## [Unreleased]`)

## 1. Summary

A host-configurable line-number gutter for the `PyRaya` widget: one number per document
line on the **right edge**, rendered in Eastern or Western digits, coloured by the theme
stop, **off by default**. It reserves a right strip with `setViewportMargins`, paints the
numbers on a small `GutterArea` child widget (sibling of the viewport), and recomputes its
pixel width dynamically in both directions as the largest visible line number crosses powers
of ten. The digit conversion reuses `regions.substituteText`; the colours come from new
`ThemeTokens` fields. No public colour API, no width API, no alignment API, no signal, no
start-number API.

## 2. Context: current state

- `PyRaya` (`src/pyraya/pyraya_widget.py`) is a `QPlainTextEdit` subclass with RTL layout,
  right-aligned blocks, a roman-input overlay, a spell-check underline, region tagging, and
  palette-driven theming (`theme.py`).
- Every colour PyRaya paints lives in `theme.py` (`ThemeTokens` per stop, `LightStop` /
  `DarkStop`, `resolveTheme`). This feature adds three gutter tokens.
- `regions.py` already maps ASCII `0–9` to Eastern Arabic-Indic `۰–۹` (`RegionSubstitutions`
  / `substituteText`); the gutter reuses it rather than defining a new digit table.
- The overlay re-placement funnel is `PyRaya.resizeEvent → _onViewChanged()`
  (`pyraya_widget.py:3120`, `:2207`); a margin change at fixed widget size re-places an active
  overlay through this same path (verified, §7).
- The demo (`src/pyraya/__init__.py:107`) already wires a `Ctrl+D` theme toggle via
  `QShortcut` / `QKeySequence`; the gutter toggle joins it as `Ctrl+L`.

## 3. Public API

On `PyRaya`, following the existing `setXEnabled` / `isXEnabled` and `setFont*` naming:

```python
class PyRaya:
    def setGutterEnabled(self, enabled: bool) -> None
    def isGutterEnabled(self) -> bool          # off by default
    def setGutterFormat(self, digitSet: DigitSet) -> None   # default DigitSet.Eastern
    def gutterFormat(self) -> DigitSet
    def setGutterFont(self, font: QFont) -> None
    def gutterFont(self) -> QFont
```

New module-level names, re-exported from `pyraya/__init__.py` and added to `__all__`:

```python
class DigitSet(IntEnum):     # closed enum, mirrors RegionType
    Western = 0
    Eastern = 1

class GutterArea(QWidget):    # the paint widget; child of PyRaya, sibling of the viewport
```

Deliberately **not** part of the API: a colour setter, a width setter, an alignment setter,
a start-number setter, and a `gutterEnabledChanged`-style signal (pure view state,
host-driven — no host behaviour depends on it).

## 4. Architecture

- **New module `src/pyraya/gutter.py`** (the repo's feature-module pattern): `DigitSet`,
  `formatLineNumber`, the width helper, and `GutterArea`. `PyRaya` owns the integration and
  the state fields; the module stays small so the 3.5 k-line widget file stops growing.
- **Mechanism** (the canonical Qt gutter pattern, adapted to PySide6 and this widget):
  enabled → `setViewportMargins(0, 0, width, 0)` reserves the right strip; `GutterArea` —
  child of `PyRaya`, **sibling of the viewport** — is placed at the right edge of
  `contentsRect` and paints the numbers, offset by `contentOffset()` so the numbers move
  with the document while the strip stays fixed.
- **`GutterArea.paintEvent`** walks visible blocks only (`firstVisibleBlock()` upward,
  bounded to the dirty rect — load-bearing for the 200 k latency budget), draws each
  1-based number with the converted digit string, physical `AlignVCenter | AlignLeft`
  (painter alignment flags are physical, so the widget's RTL layout direction does not
  flip them), then a 1 px splitter on the text-facing (left) edge. Colours are resolved
  **per paint** from `resolveTheme(self.palette())`, so a palette swap repoints the strip on
  the next repaint and a no-op retheme paints nothing new.
- **Scroll** (`_onGutterUpdateRequest(rect, dy)`, connected to `updateRequest`): `dy ≠ 0` →
  `gutter.scroll(0, dy)` (fast path, shifts the painted pixels); `dy == 0` →
  `gutter.update(rect)` (partial repaint). The width recompute (§5) runs in the same handler,
  before the gutter repaints.

## 5. Width rule

- **Formula:** `width = max(3, digits of the largest visible line number) × digit advance +
  padding split both sides`. The 3-digit baseline covers the most common range; the digit
  count only changes at powers of ten (1000 / 10000 / 100000), so the reflow cost is rare
  enough to accept. The advance is measured with the **gutter font's** metrics (`"9"` for
  Western, `"۹"` for Eastern), since the font is host-configurable.
- **Dynamic in both directions:** a recompute that reveals a larger digit count expands the
  strip; one that reveals a smaller count shrinks it. The total line count **never** drives
  the width (only the largest *visible* line number does).
- **Recompute triggers:** every `updateRequest` and every widget resize — a text edit can
  shift line numbers without scrolling (a paste at the top shifts everything), and a resize
  changes which lines are visible. The recompute is one `cursorForPosition(QPoint)` +
  `findBlock`, cheap enough to run per paint region.
- **No-op guard:** the recompute is applied only when the result differs from the current
  width — a no-op recompute changes nothing (no margin, no reflow, no re-placement, no
  revision bump). A real change re-geometries the gutter and re-places the active overlay.
  `blockCountChanged` is **not** a width driver.
- **Largest visible line number:** `cursorForPosition(QPoint(vp.width() // 2, vp.height() -
  1))` + `document().findBlock(cursor.position()).blockNumber() + 1` — the block at the
  viewport's bottom, 1-based. (Verified, §7.)

## 6. Theme and font wiring

- `ThemeTokens` gains `gutterBackground`, `gutterText`, `gutterBorder`; `LightStop` /
  `DarkStop` carry first-guess values (light: a faint grey strip with muted ink; dark: the
  usual counterpart), fine-tuned by one table edit per the `DarkStop` precedent.
- The gutter resolves colours **per paint** from `resolveTheme(self.palette())` — the same
  no-paint-hook pattern as the overlay. A `setPalette` (or application palette swap)
  repoints the strip on the next repaint; a no-op retheme bumps nothing.
- The gutter font is a **separate variable** on `PyRaya`, independent of the document font:
  its default is a copy of the document font at construction; `setGutterFont` sets it and
  triggers the width recompute (the pixel width moves with the font even when the digit
  count doesn't); document font changes (`setFontFamily` / `setFontSize`) never repoint it.

## 7. Probe findings (load-bearing, verified on PySide6 6.12, offscreen, 2026-11-15)

- **`updateRequest`** delivers `(rect, dy)` to Python: the rect arrives as an **integer
  `QRect`**, `dy` as `int`. `dy ≠ 0` **is** reachable under incremental scrolling (saw
  `-60`, `-56`); `dy == 0` is the repaint path.
- **`cursorForPosition`** takes a **single `QPoint`** (not two ints); `findBlock` on its
  position returns the block at the viewport's bottom — the largest visible line number.
  Scrolled-to-bottom returned the last block; scrolled-to-top returned block 20 of 201.
- **`setViewportMargins`:** a real change **fires the widget's `resizeEvent`
  synchronously** (not scheduled) and also **fires `updateRequest`**; a no-op change fires
  **neither**. A margin change **reflows the text** (a wrapped line's block height moved
  480 → 564), which is why an active overlay must be re-placed on a real width change —
  and why the existing `PyRaya.resizeEvent → _onViewChanged()` path already does it: no
  separate re-placement hook is needed.
- **Paint coordinate math:** `top = int(blockBoundingGeometry(block).translated(
  contentOffset()).top())` is the correct gutter-local y for a block's top edge (a render
  probe confirmed the painted numbers align with the text lines; the gutter widget's origin
  is at `contentsRect().top()`, so the value is used directly).
- **`GutterArea` as a sibling of the viewport** (child of `PyRaya`, `setGeometry` at
  `contentsRect().right() - width, contentsRect().top()`, `raise_()`): after
  `setViewportMargins` + resize it does not overlap the viewport and is visible.
- **Synchronous margin change:** because `setViewportMargins` fires `resizeEvent`
  synchronously, the width recompute in `resizeEvent` recurses once per digit-count change
  and terminates on the no-op guard (the reflow can move the largest visible line number
  across a power-of-ten boundary; that one-cycle oscillation is accepted and documented,
  §9).

## 8. Interaction with existing machinery

- Enabling the gutter **reflows the document** (narrower viewport → different line
  wrapping). That is a layout change, not an edit: no revision bump, no undo step, no
  `regionsChanged` — but word rects move, so an **active overlay is re-placed** from its
  stored anchor by the margin change's `resizeEvent → _onViewChanged()` (verified, §7).
- The gutter is read-only over the document: painting never edits, never re-highlights,
  never bumps the revision, never touches the undo stack.
- The gutter is a child of `PyRaya`, **sibling of the viewport** — not a viewport child — so
  the mouse-transparent overlay, hit-testing, and the scroll hook
  (`verticalScrollBar().valueChanged`) are all untouched.
- The gutter's `changeEvent` is the default `QWidget` handler (it is a separate child
  widget), so a palette change marks it dirty and it repainted on the next paint with the
  new `resolveTheme` colours — no `PyRaya._applyTheme` hook needed.

## 9. Testing strategy (offscreen)

New `tests/test_gutter.py`, reusing the shared offscreen `app` fixture and the
`shared_engine` fixture; no `QApplication.exec()`.

- **Default off:** `isGutterEnabled()` is False; zero viewport margins; no `GutterArea`
  widget; no document change.
- **Enabled geometry:** `setGutterEnabled(True)` reserves the right margin; the `GutterArea`
  geometry sits at the right edge of `contentsRect` and does not overlap the viewport.
- **Width:** the 3-digit baseline on a small document; expansion past line 999; shrink-back
  below 1000; a no-op recompute bumps neither revision nor undo stack; `blockCountChanged`
  leaves the width alone (the width tracks the largest *visible* line number, not the total
  block count — a 1500-line document scrolled to the top keeps a 3-digit width); a font
  change moves the pixel width at an unchanged digit count.
- **Number formatting:** `formatLineNumber` as a pure function (Eastern digits via
  `substituteText`, Western identity); plus one `QPainter`-into-`QImage` check that the
  Eastern digits actually paint.
- **Theme:** the three new stop values pinned in `tests/test_theme.py` style; a palette swap
  repoints the strip on the next repaint; a no-op retheme bumps nothing.
- **Font independence:** a document font change leaves the gutter font and width untouched.
- **Overlay interaction:** enabling with an active overlay re-anchors it with no revision
  bump and no `regionsChanged`; a real width change (scrolling past line 1000) re-places the
  active overlay the same way.
- **Latency harness:** a row for gutter paint on the 200 k fixture (the visible-blocks loop
  is the budget it protects).

## 10. Docs and bookkeeping

- `AGENTS.md`: a feature bullet (mechanics + the overlay-reflow gotcha + the accepted
  power-of-ten oscillation) and a Gotchas entry (a margin change at fixed widget size fires
  the widget `resizeEvent` synchronously and reflows the text, so a real width change must
  re-place the overlay — which the existing `_onViewChanged` path already does).
- `README.md`: the gutter API.
- Demo (`main()`): a `Ctrl+L` toggle beside the existing `Ctrl+D`.
- `CHANGELOG.md`: an Unreleased `Added` entry. The version bump stays a release-time
  `ver:` step.

## 11. Constraints

- The gutter is read-only over the document: painting never edits, never re-highlights,
  never bumps the revision, never touches the undo stack.
- The gutter is a sibling of the viewport, never a viewport child — the mouse-transparent
  overlay, hit-testing, and scroll-hook contracts stay untouched.
- Every colour PyRaya paints lives in `theme.py`; no hard-coded literal in the paint path.
- Paint is bounded to visible blocks. Alignment is physical left and never flipped by the
  widget's RTL layout direction.
- Never: a public colour API (for now), a width API, an alignment API, a start-number API,
  a state signal, or a change to existing exported names.
- Conventions: camelCase methods, Google-style docstrings, type hints, ruff/pyrefly clean,
  tests on the shared offscreen `QApplication`.

## 12. Decided (operator)

- Right-edge gutter only; alignment fixed left within the gutter; no alignment API.
- Off by default; the host opts in.
- Default digit format **Eastern** (`DigitSet.Eastern`).
- Width: a 3-digit baseline covering the most common range, **dynamic in both directions**
  as the largest visible line number crosses powers of ten, never fixed to the total line
  count, padded on both sides — the digit-count steps are rare enough that the reflow cost
  is acceptable.
- Colours: fixed theme colours for background and foreground, **no public colour API**
  ("for now").
- The gutter font is a **separate variable** that changes independently of the
  `QPlainTextEdit` document font.
- The feature is referred to as the **gutter** throughout the API (`setGutter*`, not
  `setLineNumbers*`).

## 13. Open / first-guess (fine-tune by one table edit)

- Exact `LightStop` / `DarkStop` gutter colour values (first guess; one table edit).
- `DigitSet` and its members (`Western` / `Eastern`); the class name `GutterArea` and the
  module name `gutter.py` (chosen to match the `Gutter` API naming).

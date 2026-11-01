# Double-tap Esc assist-off

## Objective
Add one rule on top of the existing assist-mode contract: **two quick Esc
presses turn assist mode off**, irrespective of whether the overlay is shown.
The existing single-Esc contract is untouched:
- a plain Esc on the active overlay still dismisses it only (assist stays on);
- `Ctrl+Esc` (the exact Ctrl mask) still turns assist mode off;
- `Ctrl+Space` still re-enters the mode.

## Design
- **Mechanism:** a timestamp plus an interval check — no per-event
  bookkeeping beyond the timestamp. The focus model routes the second Esc to
  the document's `keyPressEvent` (the first Esc's dismiss returns focus to
  the document), so one shared `_lastEscAt` field covers both paths.
- **State:** `self._lastEscAt: float | None` on `PyRaya` (initial `None`),
  holding `time.monotonic()` of the last plain-Esc press.
- **Constant:** `EscDoubleTapInterval: float = 0.3` (module-level, public,
  re-exported from `pyraya/__init__.py` and added to `__all__`).
- **Recording site** — every plain Esc (no modifiers):
  - the overlay path, `_onOverlayCanceled` (`modifiers == 0`);
  - the document path, `keyPressEvent` (plain `Key_Escape`, `NoModifier`).
- **Trigger:** on a plain Esc, if `_lastEscAt` is not `None` and
  `now - _lastEscAt <= EscDoubleTapInterval`, turn assist mode off
  (`_assistMode = False`), reset `_lastEscAt = None`, and deactivate the
  overlay. A single Esc (or one out of interval) only records the timestamp.
- A plain Esc is the only tap candidate: `Ctrl+Esc` (exact Ctrl mask) and
  `Shift+Esc` do not record, so they cannot form a double tap.

## TDD
### RED — failing tests in `tests/test_roman_input.py`
1. `testDoubleEscInDocumentTurnsAssistModeOff` — two quick Esc in the document
   (overlay inactive) turn assist off: the "irrespective of overlay display"
   case.
2. `testDoubleEscWithActiveOverlayTurnsAssistModeOff` — two quick Esc starting
   from an active overlay turn assist off (first Esc dismisses, second Esc in
   the document completes the tap).
3. `testSingleEscDoesNotTurnAssistModeOff` — a single Esc does not turn off.
4. `testSlowEscDoesNotTurnAssistModeOff` — a second Esc out of interval does not
   turn off.

Test seam: monkeypatch `pyraya.pyraya_widget.monotonic` with a controllable
fake clock so the timing is deterministic (no wall-clock reliance).

### GREEN — minimal code in `src/pyraya/pyraya_widget.py`
- `from time import monotonic`.
- module constant `EscDoubleTapInterval: float = 0.3`.
- `self._lastEscAt: float | None = None` in `__init__`.
- `_onOverlayCanceled`: plain-Esc (`modifiers == 0`) branch — check the
  interval, turn off + reset on a double tap, else record.
- `keyPressEvent`: new plain-Esc branch before `super()` — check the interval,
  turn off + deactivate + accept on a double tap, else record and fall through
  (the document's plain-Esc no-op is preserved).

### REFACTOR
- docstrings in `pyraya_widget.py` (`_onOverlayCanceled`, `keyPressEvent`).
- `README.md` + `AGENTS.md` assist-mode contract (document the double-tap rule
  alongside `Ctrl+Esc`).
- re-export `EscDoubleTapInterval` from `pyraya/__init__.py` + `__all__`.

## Verification
- `uv run pytest` (full suite).
- `ruff check`, `ruff format --check`, `pyrefly check`.

# Alt-keymap plan (Ctrl -> Alt, homogeneous single-modifier)

Goal: move every **custom** PyRaya shortcut from `Ctrl` to `Alt`. Standard
editing shortcuts (Ctrl+Z undo, etc.) stay `Ctrl`. TDD: tests first (RED),
then code (GREEN), then docstrings + docs.

## Keymap (before -> after)
- Region tag: Ctrl+1 / Ctrl+2 -> Alt+1 / Alt+2
- Assist on + activate: Ctrl+Space -> Alt+Space
- Assist off + close: Ctrl+Esc -> Alt+Esc (exact Alt mask)
- Commit + newline: Ctrl+Enter -> Alt+Enter
- Commit bare + navigate: Ctrl+Up / Ctrl+Down -> Alt+Up / Alt+Down (exact Alt)
- Plain Esc in overlay: unchanged (dismiss only)
- Plain Space/Enter/punctuation commit: unchanged
- Plain Up/Down list navigation: unchanged
- Plain Left/Right visual order: unchanged

## Code (GREEN)
- src/pyraya/pyraya_widget.py
  - keyPressEvent seed gate (~2279): ADD `and not (event.modifiers() & AltModifier)`
    (keep the Ctrl exclusion so Ctrl+1/2 fall through instead of seeding).
  - keyPressEvent block (~2286): `& ControlModifier` -> `& AltModifier`.
  - keyPressEvent exact-mask Esc (~2297): `== ControlModifier.value` -> `== AltModifier.value`.
  - _onOverlayCanceled (~1683): `== ControlModifier.value` -> `== AltModifier.value`.
  - _commitSeparator (~2022): `& ControlModifier.value` -> `& AltModifier.value`.
- src/pyraya/roman_input.py
  - RomanLineEdit.keyPressEvent Up/Down exact (~854): `== ControlModifier.value` -> `== AltModifier.value`.
  - (Esc branch ~845 unchanged: emits whatever modifiers; host decides off on exact Alt.)

## Tests (RED)
- tests/test_pyraya.py
  - testKeyboardShortcutsAssignRegions: ControlModifier -> AltModifier (2x); docstring.
  - testKeyboardShortcutsIgnoredWithoutSelection: ControlModifier -> AltModifier; docstring.
- tests/test_roman_input.py
  - All `ControlModifier` -> `AltModifier` (24 occurrences).
  - Rename 12 fns Ctrl->Alt: testCtrlSpaceAtWordEndActivatesOverlay,
    testCtrlReturnCommitsWithNewline, testCtrlUpCommitsBareAndMovesOneLineUp,
    testCtrlDownCommitsBareAndMovesOneLineDown,
    testCtrlUpLandingOnRomanUrduWordReactivatesOverlay,
    testCtrlUpLandingWithoutWordStaysQuiet, testCtrlShiftUpDownStayListNavigation,
    testCtrlUpEmptyTextCommitRemovesSpan, testCtrlEscOnActiveOverlayTurnsAssistModeOff,
    testCtrlEscInDocumentTurnsAssistModeOff, testCtrlSpaceOnWordReentersAssistMode,
    testCtrlSpaceWithoutWordShowsEmptyOverlay.
  - All "Ctrl+x" docstrings/comments -> "Alt+x"; "exact-Ctrl" -> "exact-Alt".

## Docstrings (REFACTOR, keep green)
- src/pyraya/pyraya_widget.py: lines 1019, 1036, 1230, 1674-1681, 1901, 1954,
  2002-2003, 2252-2259 (Ctrl -> Alt). Line 753 "Ctrl+Z" STAYS (Qt default undo).
- src/pyraya/roman_input.py: lines 777, 782, 785, 850-852, 905-906, 921, 1130-1131.

## Docs
- README.md: lines 72-73, 103, 105-106, 157-160, 170, 173, 175, 178 (Ctrl -> Alt).
- AGENTS.md: lines 8, 73, 74, 94, 103, 106 (Ctrl -> Alt); line 109 "Ctrl/Shift
  variants" -> "modifier variants".

## Verification
- uv run pytest (full suite)
- uv run ruff check . ; uv run ruff format --check . ; uv run pyrefly check
- grep -rn "Ctrl" src tests README.md AGENTS.md -> only "Ctrl+Z" (undo) + the
  "modifier variants" line should remain; no custom Ctrl shortcuts.

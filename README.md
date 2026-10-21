## PyRaya (پیرایہ)

قلم کی روانی، سوچ کی آسانی؛ اردو تحریر کا نیا پیرایہ۔

*Styling Urdu text, one line of Python at a time.*

PyRaya is a reusable, self-contained Qt text editor widget
written in Python (PySide6). It is designed specifically
to bridge the gap between complex right-to-left scripts and
modern application frameworks, offering a drop-in solution
for Urdu text input. By relying on the globally comprehensive
Google Noto font ecosystem, PyRaya provides a highly unified,
streamlined, and clean visual appearance—even
when mixing Urdu Nastaliq with Latin scripts, numerals, and
punctuation.

------------------------------
## ⚠️ Alpha Status

PyRaya is at **version 0.1.0-alpha.7**. The widget is a drop-in `QPlainTextEdit`. The following are now **implemented**:

- **Native RTL layout** — right-to-left alignment and paragraph handling.
- **Noto typography** — a configurable font stack defaulting to Noto Naskh Arabic.
- **Visible whitespace** — tabs and spaces rendered as visible characters.
- **Configurable formatting** — a dedicated rule-based syntax highlighter.
- **Text regions** — spans tagged as *Latin* or *Roman Urdu* (`RegionType`), rendered with a subtle, type-specific background color; tag a selection from the right-click context menu, via the `Ctrl+1` / `Ctrl+2` keyboard shortcuts, or via `setRegionType`. Every character belongs to exactly one region kind at all times: untagged text belongs to `DefaultRegionKind` (Roman Urdu), each kind's identity is its unique background color (compared including the alpha channel), and clearing regions resets the text to `DefaultRegionKind`. The kind-to-color palette is per widget: each widget copies the module-level `RegionColors` default at construction, so `setRegionColor` recolours within that widget alone.
- **Roman-script input overlay** — on by default. An Arabic-script word inside a *Roman Urdu* region gets a small frameless, non-modal overlay line edit matched to the word's geometry; the typed roman text is edited there (the visual document stays Arabic-script), a tier-colored suggestion list (green = exact, orange = edit distance 1, red = distance 2) hangs below the line edit — flipping above it only when it would not fit below *and* the space above the anchor is larger than the space below (ties and near-top anchors keep it below, truncated in whole rows — the panel ends flush at the bottom edge of the last visible row — and the overlay's right edge stays pinned to the word even when the word hugs the viewport's edge) — at most five rows, scrolling so the highlighted row stays visible — and committing (Space / Enter / typed punctuation — including the Arabic script's own separator marks ؟ ، ؛ ۔ ٫ ٬ ؜, `ArabicScriptSeparators` — or Left/Right at the word's text edges) writes the selected Arabic word — plus the separator character, if typed — to the document (a plain Enter commits the word plus a newline; Ctrl+Enter commits the word without one). An edge commit (Left at the visually left edge of the word, Right at the visually right edge) writes nothing and moves the cursor in visual order to the adjacent word — the next word or the previous one — landing at that word's edge facing the active word (Left at its start, Right at its end), and the post-commit resync re-activates the overlay over the landed word (a cursor at the word's end is over the word); with no adjacent word — the commit lands on a boundary word, whose far side is only whitespace — the overlay is closed and the resync skipped, so the deactivation sticks and the cursor rests at the boundary edge (Left at the word's end, Right at its start). A Ctrl+Enter commit skips the resync, so a dismissed overlay is not re-triggered and the cursor rests at the inserted word's end. A zero-match typed word offers a `+ Learn <word>` undefined-word row; committing it commits the typed roman word (a no-op hook for the future learning feature) and leaves the local dictionary unchanged. Assist mode is on by default: Esc on an active overlay dismisses it and turns assist mode off, leaving the user alone (typing and the mouse no longer activate the overlay) until `Ctrl+Space` in the document turns it back on — over the Roman Urdu word under the cursor with its romanized text, or, with no such word, an empty overlay at the cursor; committing never turns the mode off.
- **Spell-check underline** — on by default. An Arabic-script word belonging to a *Roman Urdu* region (explicitly tagged, or untagged text carrying the default kind) that the romanalfaz dictionary does not know gets a wavy underline in a muted brick red (`SpellCheckUnderlineColor`) — display only: no correction, no suggestions, and nothing touches the document's character formats or the undo stack. Toggled by `setSpellCheckEnabled`, independently of the roman-input feature (all four flag combinations behave); the two features share one lazily created `RomanInputEngine`, and with the dictionary missing (an unavailable engine) the underline is simply absent.

The **inbuilt spell-checker**'s **correction and suggestion** side (real-time Urdu tokenization and fixing) remains **roadmap** and is *not yet implemented*. Do not assume it works yet.

------------------------------
## Key Features

* **Plug-and-Play Qt Component** *(available)*: A drop-in `QPlainTextEdit` for any Qt user interface (currently PySide6 only).
* **Native RTL Layout** *(available)*: Right-to-left alignment and paragraph handling.
* **Streamlined Noto Typography** *(available)*: Configurable font stack defaulting to Noto Naskh Arabic, with Noto Nastaliq Urdu and other fallbacks.
* **Visible Whitespace** *(available)*: Tabs and spaces rendered as visible characters.
* **Configurable Formatting** *(available)*: A dedicated rule-based highlighter for Urdu and mixed-script text.
* **Text Regions** *(available)*: Tag a selection (or any character range) as Latin or Roman Urdu from the context menu, the `Ctrl+1` / `Ctrl+2` shortcuts, or `setRegionType`; each type renders with a subtle background color that is its unique identity (including the alpha channel). Every character belongs to exactly one region kind — untagged text belongs to `DefaultRegionKind` (Roman Urdu) — clearing regions resets the text to that kind, and regions survive edits and undo/redo. The kind-to-color palette is per widget (each widget copies the `RegionColors` default; `setRegionColor` maps within that widget alone), and `regionsChanged` is emitted once when any region-touching widget operation (tagging, clearing, recolouring, a text replacement, a commit that writes) completes.
* **Roman-Script Input Overlay** *(available)*: While enabled, editing an Arabic-script word inside a Roman Urdu region happens in a small frameless overlay line edit — the visual document stays Arabic-script until a commit. Suggestions are tier-colored (exact / distance 1 / distance 2), shown up to five rows at a time and scrolling to keep the selected row visible (flipping above the line edit only when they would not fit below *and* the space above is larger — ties and near-top anchors keep them below, truncated in whole rows — the line edit itself always stays over the word, wherever the word sits in the viewport; the overlay follows its word on scroll and treats a fully scrolled-out word as a view suspension, resuming automatically when the word is scrolled, resized, or reflowed back into view (the on/off-screen decision is made on the word's rect, never on the overlay itself, and only view events suspend and resume — user decisions like clicking away or Esc are honored)); committing writes the selected Arabic word, plus the typed separator character (the Arabic script's own separator marks — ؟ ، ؛ ۔ ٫ ٬ ؜ — commit exactly like ASCII punctuation, and terminate a word run like it too), to the document; zero-match words commit their typed roman via the `+ Learn` undefined-word row. Assist mode is on by default: Esc on the overlay turns it off, leaving the user alone until `Ctrl+Space` re-enters it.
* **Inbuilt Spell-Checker** *(available, display-only)*: A wavy underline under Roman Urdu words the romanalfaz dictionary does not know, behind a `setSpellCheckEnabled` switch independent of the roman-input feature; real-time correction and suggestion remain roadmap.
* **Multilingual Harmony** *(roadmap)*: Smooth rendering when blending Nastaliq prose with English text strings.

------------------------------
## 💻 Quick Start

```python
import sys

from PySide6.QtWidgets import QApplication

from pyraya import PyRaya

app = QApplication(sys.argv)
editor = PyRaya()
editor.show()

sys.exit(app.exec())
```

------------------------------
## Roman-Script Input

The overlay feature is **on by default**, so roman Urdu input works out of the box: an ASCII alphanumeric key pressed with the cursor inside a Roman Urdu region (which is every untagged character) seeds the overlay instead of the document. Disabling it restores plain typing — roman keystrokes go straight into the document as in a plain `QPlainTextEdit`.

Assist mode is **on by default** as well: while on, typing and cursor movement activate the overlay as described. Esc on an active overlay dismisses it and turns assist mode off — the user is left alone: typing and the mouse no longer activate the overlay — until `Ctrl+Space` in the document turns it back on: over the Roman Urdu word under the cursor with its romanized text, or, with no such word, an empty overlay at the cursor. Committing never turns the mode off; only Esc on the overlay does. Esc in the document (overlay inactive) is a no-op.

```python
editor.setRomanInputEnabled(False)  # optional: type roman straight into the document
editor.setAssistEnabled(False)  # optional: leave the user alone until Ctrl+Space
```

- `setRomanInputEnabled(enabled)` / `isRomanInputEnabled()` — toggle the overlay feature; re-enabling it also turns assist mode back on.
- `setAssistEnabled(enabled)` / `isAssistEnabled()` — toggle assist mode; disabling hides a shown overlay, enabling only marks the mode ready.
- `romanEngine()` — the lazily created `RomanInputEngine` (loaded on first use: first overlay activation, or the first spell-check re-highlight over Roman Urdu text), or `None` while the feature is off.
- `localDictionary()` — the engine's document-local in-memory `Vocabulary`; a hook for the future learning feature, not mutated this session.
- `romanWordCommitted(word, typedRoman)` — signal emitted whenever a word is committed to the document.
- `RomanInputEngine` / `RomanOverlay` — the engine and the overlay widgets, re-exported from `pyraya`.

Committing (Space / Enter / typed punctuation — including the Arabic script's own separator marks ؟ ، ؛ ۔ ٫ ٬ ؜, `ArabicScriptSeparators` — or Left/Right at the word's text edges) writes the selected Arabic word — plus the typed separator character, when one is typed — into the word's span, or at the cursor for a new word, tagged as a *Roman Urdu* region. An edge commit — Left at the visually left edge of the word, Right at the visually right edge — writes nothing and moves the cursor in visual order to the adjacent word (the next word or the previous one), landing at that word's edge facing the active word (Left at its start, Right at its end); the post-commit resync re-activates the overlay over the landed word (a cursor at the word's end is over the word), and with no adjacent word — the commit lands on a boundary word, whose far side is only whitespace — the overlay is closed and the resync skipped, so the deactivation sticks and the cursor rests at the boundary edge (Left at the word's end, Right at its start); a Ctrl+Enter commit likewise skips the resync, so a dismissed overlay is not re-triggered and the cursor rests at the inserted word's end. Plain Left/Right arrow keys elsewhere in the document move the cursor in visual (screen) order, since Qt's default logical movement is flipped in this right-to-left document; Ctrl/Shift variants keep the logical behavior. A zero-match typed word commits its typed roman text via the `+ Learn <word>` undefined-word row.

------------------------------
## Spell Check

The underline feature is **on by default**: an Arabic-script word belonging to a Roman Urdu region (explicitly tagged, or untagged text carrying the default kind) that the romanalfaz dictionary does not know is underlined with a wavy line in a muted brick red, so unknown words are visible without interrupting the flow. The underline is display-only — painted into the text layout, never touching the document's character formats or the undo stack — and offers no correction or suggestion (that remains roadmap). Latin-region text and non-Arabic runs are never underlined.

The switch is **independent** of the roman-input feature: spell check keeps working with roman input disabled (and vice versa), and the two share one lazily created `RomanInputEngine`. If the dictionary cannot be loaded, the engine is unavailable and the underline pass is a no-op — a missing dictionary never underlines every word.

```python
editor.setSpellCheckEnabled(False)  # optional: no underline
```

- `setSpellCheckEnabled(enabled)` / `isSpellCheckEnabled()` — toggle the underline; toggling re-highlights the whole document, so the underline is removed or restored immediately.
- `SpellCheckUnderlineColor` — the muted brick red (`#B22222`) used for the underline, re-exported from `pyraya`.

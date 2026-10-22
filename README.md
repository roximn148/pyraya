# PyRaya (پیرایہ)

قلم کی روانی، سوچ کی آسانی؛ اردو تحریر کا نیا پیرایہ۔

A PySide6 text editor for Urdu. Drop the widget into your app and it handles
right-to-left paragraphs, a Nastaliq font stack, and typing Urdu from a roman
keyboard.

⚠️ **Alpha** · `0.1.0-alpha.8` · Python 3.14+ · PySide6

---

## Why PyRaya exists

Urdu writers type on roman keyboards and expect Urdu script on the page. Qt
shapes Nastaliq well, then hands you the rest: paragraph direction, a font
stack that carries Nastaliq beside English, and a way to turn `salam` into
سلام. PyRaya does that work. Type a roman word, choose the Urdu spelling from
a list, and the page stays in Urdu the whole time.

## Install

No package is published yet. In a clone of this repository, `uv sync` builds a
virtual environment with the pinned dependencies, and `uv run pyraya` opens
the demo window.

## Sixty seconds

```python
import sys

from PySide6.QtWidgets import QApplication

from pyraya import PyRaya

app = QApplication(sys.argv)
editor = PyRaya()
editor.show()

sys.exit(app.exec())
```

Run it and a right-aligned editor opens, cursor at the top right. Type
`salam` and a small line with a suggestion list appears; press space and the
selected Urdu word lands in the document, in Urdu script.

## Features at a glance

- Right-to-left paragraphs, right-aligned from the first keystroke.
- Nastaliq and Latin on one line, from one font stack.
- Spaces and tabs drawn as visible marks.
- Spans tagged Native or Roman Urdu; Roman-Urdu text gets a faint orange
  tint, Native text carries no tint. See [Regions](#regions).
- Roman input: type `salam`, pick سلام, keep writing. See
  [Roman input](#roman-input).
- A wavy underline under words the dictionary does not know. See
  [Spell check](#spell-check).

## Regions

A region kind marks a character span with intent, and there are two kinds:
`RegionType.Native` for English and other Latin text, `RegionType.RomanUrdu`
for Urdu written in roman letters. Kinds are stored as a tag on the document's
characters — a stored tag wins, and untagged text *acts as* Roman Urdu (it
gets the Roman-Urdu tint and takes roman input). Native text carries no tint;
nothing else changes for it.

Tag a span three ways. Select text and use the right-click menu ("Region:
Native", "Region: Roman Urdu"), or with a selection press `Ctrl+1` for Native
or `Ctrl+2` for Roman Urdu, or call the API:

```python
from pyraya import RegionType

editor.setRegionType(RegionType.Native, 0, 12)  # tag characters 0 through 11
editor.regions()  # every tagged span as TextRegion(start, end, kind)
editor.clearRegions()  # every character resolves to the seed kind again
```

The tags live in the document itself, so they survive edits and undo. Each
method that changes regions emits `regionsChanged` once when it finishes.
`seedRegionKind()` answers the kind untagged text resolves to; the seed is
read-only. `setRegionColor(kind, color)` recolors one kind's tint, inside
this widget only — it touches no document state and repaints the tint
immediately.

## Roman input

The overlay is on by default. Type a roman letter inside a Roman Urdu region
and a small line appears over the nearest Urdu word: your roman letters are
edited in that line while the document keeps its Urdu script. A suggestion
list sits under the line, or above it when the bottom is crowded. Green rows
match the word exactly, orange rows are one edit away, red rows two, and five
rows fit at a time with the list scrolling so the picked row stays visible.

Space, Enter, or any punctuation key commits the selected word, and a typed
Urdu mark such as ۔ or ، goes with it. Enter starts a new line; `Ctrl+Enter`
does not. Escape closes the overlay and turns assist mode off, so typing and
clicking stop opening it until `Ctrl+Space` brings it back, over the word
under the cursor or empty at the cursor. Turning the feature off restores
plain typing:

```python
editor.setRomanInputEnabled(False)  # roman letters type into the document
editor.setAssistEnabled(False)  # the overlay stops opening on its own
```

## Spell check

The underline is on by default. Any Arabic-script word inside a Roman Urdu
region that the romanalfaz dictionary does not know gets a wavy brick-red
underline, so unknown words are visible without interrupting the flow. It is
display only: nothing corrects, nothing suggests, nothing enters the undo
stack, and Native-region text is never underlined. The switch is independent
of roman input, so you can run the underline alone:

```python
editor.setSpellCheckEnabled(False)  # hide the underlines
```

## Repository layout

```text
pyraya/
├── pyproject.toml            # project metadata and tool configs
├── uv.lock                   # pinned dependencies
├── LICENSE                   # MIT
├── AGENTS.md                 # behavior contracts and test conventions
├── src/
│   └── pyraya/
│       ├── pyraya_widget.py  # the PyRaya widget and its highlighter
│       ├── regions.py        # region model: kinds, spans, seed, stored-tag property
│       ├── roman_input.py    # roman-input engine and overlay widgets
│       ├── __init__.py       # public API and the demo entry point
│       └── py.typed          # typing marker
├── tests/
│   └── fixtures/             # reference documents for the large-document tests
└── docs/
    └── superpowers/          # design specs and implementation plans
```

## Where the details live

This page covers what PyRaya does and how to switch things on. The behavior
contracts, edge cases, and test coverage live in `AGENTS.md`, and the design
history under `docs/superpowers/`. Every public class, method, and constant
documents itself in its docstring, and `pyraya/__init__.py` lists the whole
public surface.

## License

PyRaya is MIT licensed; see `LICENSE`. It is written by RoXimn and runs on
PySide6 with romanalfaz behind the roman-input features.

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

PyRaya is at **version 0.1.0-alpha.1**. The widget is a drop-in `QPlainTextEdit`. The following are now **implemented**:

- **Native RTL layout** — right-to-left alignment and paragraph handling.
- **Noto typography** — a configurable font stack defaulting to Noto Naskh Arabic.
- **Visible whitespace** — tabs and spaces rendered as visible characters.
- **Configurable formatting** — a dedicated rule-based syntax highlighter.
- **Text regions** — spans tagged as *Latin* or *Roman Urdu* (`RegionType`), rendered with a subtle, type-specific background color; tag a selection from the right-click context menu, via the `Ctrl+1` / `Ctrl+2` keyboard shortcuts, or via `set_region_type`.

The **inbuilt spell-checker** (real-time Urdu tokenization and misspelling highlighting) is **roadmap** and *not yet implemented*. Do not assume it works yet.

------------------------------
## Key Features

* **Plug-and-Play Qt Component** *(available)*: A drop-in `QPlainTextEdit` for any Qt user interface (currently PySide6 only).
* **Native RTL Layout** *(available)*: Right-to-left alignment and paragraph handling.
* **Streamlined Noto Typography** *(available)*: Configurable font stack defaulting to Noto Naskh Arabic, with Noto Nastaliq Urdu and other fallbacks.
* **Visible Whitespace** *(available)*: Tabs and spaces rendered as visible characters.
* **Configurable Formatting** *(available)*: A dedicated rule-based highlighter for Urdu and mixed-script text.
* **Text Regions** *(available)*: Tag a selection (or any character range) as Latin or Roman Urdu from the context menu, the `Ctrl+1` / `Ctrl+2` shortcuts, or `set_region_type`; each type renders with a subtle background color, and regions survive edits and undo/redo.
* **Inbuilt Spell-Checker** *(roadmap)*: Real-time tokenization and highlighting of misspelled Urdu words.
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

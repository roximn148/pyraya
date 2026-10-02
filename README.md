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

PyRaya is at **version 0.1.0-alpha.0**. The drop-in widget shell and API are available, but the headline features below are **roadmap** and *not yet implemented*:

- **Native RTL layout** — right-to-left alignment and paragraph handling.
- **Noto Nastaliq typography** — the default Urdu font stack.
- **Inbuilt spell-checker** — real-time Urdu tokenization and misspelling highlighting.

Do not assume these work yet.

------------------------------
## Key Features

* **Plug-and-Play Qt Component** *(available)*: Drop it instantly into any PySide6 or PyQt6 user interface.
* **Native RTL Layout** *(roadmap)*: Automatic Right-to-Left alignment and paragraph handling.
* **Streamlined Noto Typography** *(roadmap)*: Default font stack built on Noto Nastaliq Urdu.
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

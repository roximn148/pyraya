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
## Key Features

* Plug-and-Play Qt Component: Drop it instantly into any PySide6 or PyQt6 user interface.
* Native RTL Layout: Automatic Right-to-Left alignment and paragraph handling out of the box.
* Streamlined Noto Typography: Default font stack built on Noto Nastaliq Urdu for flawless script rendering.
* Inbuilt Spell-Checker: Real-time tokenization and highlighting of misspelled Urdu words.
* Multilingual Harmony: Smooth rendering when blending Nastaliq prose with English text strings.

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

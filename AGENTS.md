# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this project is
PyRaya (پیرایہ) is a **reusable, self-contained PySide6 (Qt) text editor widget** for Urdu / Nastaliq (right-to-left) text. It is a drop-in `QWidget` for embedding Urdu text editing in Qt applications — currently PySide6 only.

Current status: **alpha (0.1.0-alpha.1)**. The widget is a `QPlainTextEdit` with RTL layout, right-aligned paragraphs, a configurable Noto font stack (default `Noto Naskh Arabic`), visible whitespace, a dedicated rule-based formatting highlighter, and text regions implemented: spans tagged as `latin` or `roman urdu` (:class:`RegionType`) and rendered with a subtle, type-specific background color, tagged from the right-click context menu, the `Ctrl+1` / `Ctrl+2` keyboard shortcuts, or `set_region_type`. The built-in spell-checker remains on the **roadmap** (see `README.md`) and is *not yet implemented*. Do not assume it works.

## Repository layout
```
pyraya/
├── pyproject.toml          # uv project config, console script, tool configs
├── uv.lock                 # pinned dependency lock
├── README.md
├── AGENTS.md               # this file
├── LICENSE                 # MIT license
├── .python-version         # pinned interpreter (3.14)
├── src/
│   └── pyraya/
│       ├── __init__.py       # public API + main() demo entry point
│       ├── py.typed          # typed-package marker
│       ├── regions.py        # region model: RegionType, TextRegion, REGION_COLORS
│       └── pyraya_widget.py  # the PyRaya widget (QPlainTextEdit) + formatting highlighter
└── tests/
    └── test_pyraya.py      # offscreen widget + text-region tests
```

## Environment
- Python **>= 3.14**.
- Package manager: **uv**. `uv sync` creates the `.venv` and pins versions via `uv.lock`.
- Always run tools through `uv` so the correct interpreter and dev dependencies are used.

## Commands
| Action                 | Command                |
| ---------------------- | ---------------------- |
| Sync deps (incl. dev)  | `uv sync`              |
| Re-lock dependencies   | `uv lock`              |
| Run the demo widget    | `uv run pyraya`        |
| Run tests              | `uv run pytest`        |
| Lint                   | `uv run ruff check`    |
| Format                 | `uv run ruff format`   |
| Type-check             | `uv run pyrefly check` |

Bare `pyraya` only works with the `.venv` activated; `uv run pyraya` always works.

## Conventions
- Use the `src/` layout. The importable package is `pyraya` — import from `pyraya`, **not** `src.pyraya`.
- Type hints are required on public functions and classes; the whole project must pass `pyrefly check`.
- Public API must have docstrings (Google-style sections such as `Args:`, with reST cross-references like `:class:`).
- New public symbols must be re-exported from `pyraya/__init__.py` and added to `__all__`.
- New source modules include the copyright banner header used in `pyraya_widget.py`.
- Keep lines within ruff's 100-character limit.
- Keep `ruff check`, `ruff format`, and `pyrefly check` clean before considering work done.
- Keep imports sorted and minimal (ruff `I`).
- Do not add third-party dependencies without updating `pyproject.toml` and re-locking (`uv lock` / `uv sync`).
- Version bumps: change `version` in `pyproject.toml`, run `uv lock`, and update the version string in `README.md`.

## Testing
- This is a **GUI** app. Automated checks must run headless — use the offscreen Qt platform so tests do not open a window. The test sets `QT_QPA_PLATFORM=offscreen`.
- The suite instantiates `PyRaya` under an offscreen `QApplication` and covers widget defaults plus the text-region API (tagging, span reconstruction, persistence through edits and undo/redo, popup-menu actions, keyboard shortcuts, and the custom-context-menu trigger).
- New tests must reuse the single offscreen `QApplication` (see the `app` fixture); never call `QApplication.exec()` inside a test.

## Gotchas
- Instantiating `PyRaya` requires a `QApplication` to exist (see the offscreen test).
- The **Noto** fonts (Noto Naskh Arabic, Noto Nastaliq Urdu, Noto Sans Arabic, …) may not be installed in CI / agent environments — the widget falls back through its font stack and lets Qt substitute; do not assume a specific font is available in automated tests.
- RTL layout is implemented via the widget layout direction and right-aligned blocks; the shaping engine handles Urdu/Arabic script ordering. The Noto fonts may be absent in automated environments, so the rendered font may be a fallback.
- `pydantic` and `romanalfaz` are declared dependencies but are currently unused — reserved for roadmap work; do not build the current API on them.
- **Never stage IDE/editor files** — `.idea/`, `.vscode/`, and other IDE-specific files are git-ignored and must not be committed.
- Do not hand-edit `uv.lock` — regenerate it with `uv lock`.
- The demo (`uv run pyraya`) opens a real window; automated verification stays limited to the offscreen test suite.
- Qt documents keep an implicit trailing terminator character, so `characterCount()` is one greater than the visible text length. Character-format merges spanning that character are silently dropped — region ranges are clamped to `characterCount() - 1`, and cursor-based region lookups guard the same boundary so a right-click on an empty document, or with the cursor at the end of the text, never requests an out-of-range `QTextCursor` position. Region state lives in the document's character formats (background colors), which is why spans survive edits and undo/redo; cleared characters are repainted with the widget's background color because a merge cannot restore a `NoBrush` background.
- PySide6 does not dispatch `QWidget.createPopupMenu` or `QWidget.contextMenuEvent` to Python overrides on `QPlainTextEdit` subclasses (both work only on plain `QWidget`), and does not expose `QClipboard.hasText`. The context menu is therefore handled by connecting to `QAbstractScrollArea.customContextMenuRequested` — emitted by the scroll area's viewport event filter when the policy is `CustomContextMenu` (set in the constructor, which also suppresses Qt's automatic empty popup). The request position arrives in viewport coordinates and is converted with `viewport().mapToGlobal()`. The menu is built on `createStandardContextMenu()` plus the region actions. `QTextCursor.MoveMode.KeepAnchor` is the stub-correct spelling.
- If you add features, update `AGENTS.md` and `README.md` so the documented state stays accurate.

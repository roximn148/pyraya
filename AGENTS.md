# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this project is
PyRaya (پیرایہ) is a **reusable, self-contained PySide6 (Qt) text editor widget** for Urdu / Nastaliq (right-to-left) text. It is a drop-in `QWidget` for embedding Urdu text editing in Qt applications — currently PySide6 only.

Current status: **alpha (0.1.0-alpha.0)**. The widget shell exists; RTL layout, Noto Nastaliq typography, and the built-in spell-checker are on the **roadmap** (see `README.md`) and are *not yet implemented*. Do not assume they work.

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
│       └── pyraya_widget.py  # the PyRaya QWidget
└── tests/
    └── test_pyraya.py      # minimal offscreen smoke test
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
- The smoke test imports `PyRaya` under an offscreen `QApplication` and verifies it instantiates.
- New tests must reuse the single offscreen `QApplication` (see the `qapp` fixture); never call `QApplication.exec()` inside a test.

## Gotchas
- Instantiating `PyRaya` requires a `QApplication` to exist (see the offscreen test).
- The **Noto Nastaliq Urdu** font may not be installed in CI / agent environments — do not assume font availability in automated tests.
- RTL / Unicode bidi shaping is **not yet implemented** — do not assume correct Urdu rendering.
- `pydantic` and `romanalfaz` are declared dependencies but are currently unused — reserved for roadmap work; do not build the current API on them.
- **Never stage IDE/editor files** — `.idea/`, `.vscode/`, and other IDE-specific files are git-ignored and must not be committed.
- Do not hand-edit `uv.lock` — regenerate it with `uv lock`.
- The demo (`uv run pyraya`) opens a real window; automated verification stays limited to the offscreen smoke test.
- If you add features, update `AGENTS.md` and `README.md` so the documented state stays accurate.

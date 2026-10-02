# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this project is
PyRaya (پیرایہ) is a **reusable, self-contained PySide6 (Qt) text editor widget** for Urdu / Nastaliq (right-to-left) text. It is a drop-in `QWidget` for embedding Urdu text editing in any PySide6 application.

Current status: **alpha**. The widget shell exists; RTL layout, Noto Nastaliq typography, and the built-in spell-checker are on the **roadmap** (see `README.md`) and are *not yet implemented*. Do not assume they work.

## Repository layout
```
pyraya/
├── pyproject.toml          # uv project config, console script, tool configs
├── uv.lock                 # pinned dependency lock
├── README.md
├── AGENTS.md               # this file
├── LICENSE                 # MIT license
├── src/
|  └── pyraya/
|       ├── __init__.py       # public API + main() demo entry point
|       ├── py.typed          # typed-package marker
|       └── pyraya_widget.py  # the PyRaya QWidget
└── tests/
    └── test_pyraya.py      # minimal offscreen smoke test
```

## Environment
- Python **>= 3.14**.
- Package manager: **uv**. `uv sync` creates the `.venv` and pins versions via `uv.lock`.
- Always run tools through `uv` so the correct interpreter and dev dependencies are used.

## Commands
| Action         | Command                 |
| -------------- | ----------------------- |
| Sync deps (incl. dev) | `uv sync`        |
| Run the demo widget    | `pyraya` or `uv run pyraya` |
| Run tests              | `uv run pytest`     |
| Lint                 | `uv run ruff check` |
| Format               | `uv run ruff format`|
| Type-check           | `uv run pyrefly check`|

## Conventions
- Use the `src/` layout. The importable package is `pyraya` — import from `pyraya`, **not** `src.pyraya`.
- Type hints are required on public functions and classes.
- Public API must have docstrings.
- Keep `ruff check`, `ruff format`, and `pyrefly check` clean before considering work done.
- Keep imports sorted and minimal (ruff `I`).
- Do not add third-party dependencies without updating `pyproject.toml` and re-locking (`uv lock` / `uv sync`).

## Testing
- This is a **GUI** app. Automated checks must run headless — use the offscreen Qt platform so tests do not open a window. The test sets `QT_QPA_PLATFORM=offscreen`.
- The smoke test imports `PyRaya` under an offscreen `QApplication` and verifies it instantiates.

## Gotchas
- Instantiating `PyRaya` requires a `QApplication` to exist (see the offscreen test).
- The **Noto Nastaliq Urdu** font may not be installed in CI / agent environments — do not assume font availability in automated tests.
- RTL / Unicode bidi shaping is **not yet implemented** — do not assume correct Urdu rendering.
- If you add features, update `AGENTS.md` and `README.md` so the documented state stays accurate.

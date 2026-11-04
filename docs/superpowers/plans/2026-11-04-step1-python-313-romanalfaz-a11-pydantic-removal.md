# Step 1: Python 3.13 + romanalfaz a11 + pydantic removal

**Plan:** agreed in conversation on 2026-11-04 (no separate spec file); authority
is the agreed step-1 plan plus the AGENTS.md conventions.
**Goal:** downgrade the toolchain from Python 3.14 to 3.13, bump romanalfaz to
0.1.0a11, and remove the declared-but-unused pydantic dependency — one step,
kept separate from the PySide6 6.12.0 bump (step 2) for failure attribution.
**Verification:** the repo's own gate — `uv run pytest`,
`PYRAYA_LATENCY=1 uv run pytest -s`, `uv run ruff check`, `uv run pyrefly check`.

## Context

- The 3.14→3.13 downgrade is config-only: no 3.14-only syntax in src/tests
  (verified by grepping `except*`, PEP 695 `type`, `typing.override`,
  `assert_type`, `reveal_type`, `TypeForm`, `dataclass_transform`,
  `sys.version` in the pre-step evaluation).
- romanalfaz a10→a11 diff verified via GitHub compare
  (v0.1.0a10...v0.1.0a11, 2026-11-04): pyproject (`symspellpy[editdistpy]>=6.10.1`),
  engine.py pins `DistanceAlgorithm.DAMERAU_OSA_FAST` at both `SymSpell()` sites,
  tests, lock. No API changes; the a10 learn-semantics facts in AGENTS.md hold
  under a11.
- pydantic: declared in the initial skeleton (`eda0aa2`), never imported in any
  source, test, or branch in history; AGENTS.md gotcha: "declared dependency
  but currently unused — reserved for roadmap work". Removal per user
  instruction: "can easily be added in future if and when needed."
- Dependency matrix verified: PySide6 cp310-abi3 (interpreter-independent),
  romanalfaz/symspellpy pure-Python, editdistpy 0.5.0 has a cp313 win wheel,
  pytest/ruff/pyrefly fine on 3.13.

## Global Constraints

- Everything runs through `uv` from the worktree root.
- ruff 100-char lines; imports sorted/minimal; no new third-party deps.
- Docs keep the documented state accurate: AGENTS.md + README.md.
- No version cut in this step (no 0.1.0a10 yet): CHANGELOG entries go under the
  existing `## [Unreleased]`.
- Historical plan docs under docs/superpowers/plans/ keep "3.14" wording.
- Task is config-only: TDD's configuration-file exception applies — proof is
  the verification suite, not new tests.

## Task 1: Python 3.13 + romanalfaz a11 + pydantic removal

### Step 1.1: Write this plan file

`docs/superpowers/plans/2026-11-04-step1-python-313-romanalfaz-a11-pydantic-removal.md`
(this file). It commits with the task, giving the SDD machinery a real plan
file and keeping the repo's plans convention.

Expected: file exists; `git status` shows it untracked.

### Step 1.2: Config changes

- `.python-version`: `3.14` → `3.13`.
- `pyproject.toml`:
  - `requires-python = ">=3.13"` (was `">=3.14"`).
  - dependencies: remove the `pydantic==2.13.5` line;
    `romanalfaz>=0.1.0a10` → `romanalfaz>=0.1.0a11`.
  - `[tool.ruff] target-version = "py313"` (was `"py314"`).
  - `[tool.pyrefly] python-version = "3.13"` (was `"3.14"`).

Expected: `git diff` shows exactly these edits.

### Step 1.3: Docs

- `AGENTS.md` repo-layout comment: `# pinned interpreter (3.14)` → `(3.13)`.
- `AGENTS.md` Environment: `Python **>= 3.14**.` → `Python **>= 3.13**.`.
- `AGENTS.md` gotchas: rewrite the pydantic sentence — pydantic is no longer
  declared; record that it was declared in the skeleton, never imported, and
  removed in this step; re-add (with `uv lock`) when the roadmap work that
  reserved it lands.
- `AGENTS.md` gotchas heading `**romanalfaz 0.1.0a10 learn semantics**` →
  a11, and note a11's one change: it pins
  `DistanceAlgorithm.DAMERAU_OSA_FAST` via `symspellpy[editdistpy]>=6.10.1`;
  API and semantics otherwise unchanged (the a10 facts above hold).
- `README.md` L9 banner: `Python 3.14+` → `Python 3.13+`.
- `CHANGELOG.md` under `## [Unreleased]`: `### Changed` (Python 3.13 toolchain;
  `romanalfaz >= 0.1.0a11`) and `### Removed` (`pydantic` dependency).

Expected: `grep "3.14"` over AGENTS.md/README.md returns nothing; "pydantic"
appears in AGENTS.md only in the rewritten gotcha line.

### Step 1.4: Lock + venv

- `uv lock` (regenerates uv.lock).
- `uv sync` (rebuilds `.venv` on CPython 3.13).

Expected: `uv.lock` contains romanalfaz 0.1.0a11, editdistpy, and symspellpy
>= 6.10.1, and has NO pydantic / pydantic-core entries; `uv run python -V`
prints `Python 3.13.x`.

### Step 1.5: Verification

- `uv run pytest` — full offscreen suite.
- `PYRAYA_LATENCY=1 uv run pytest -s` — latency harness prints per-row numbers.
- `uv run ruff check`.
- `uv run pyrefly check`.

Expected: all four green; latency rows within the coarse per-row budgets.

### Step 1.6: Commit

Commit all of the task's changes:
`chore: python 3.13, romanalfaz 0.1.0a11, drop unused pydantic`
with a body explaining each of the three changes.

Expected: `git status` clean after the commit; `git show --stat` lists exactly
`.python-version`, `pyproject.toml`, `uv.lock`, `AGENTS.md`, `README.md`,
`CHANGELOG.md`, and the plan file.

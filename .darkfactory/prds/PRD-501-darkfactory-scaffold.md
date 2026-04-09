---
id: "PRD-501"
title: "Scaffold darkfactory repo structure"
kind: task
status: done
priority: high
effort: s
capability: simple
parent: "[[PRD-500-darkfactory-extraction]]"
depends_on: []
blocks:
  - "[[PRD-502-darkfactory-port-source]]"
impacts:
  - (darkfactory repo) pyproject.toml
  - (darkfactory repo) mise.toml
  - (darkfactory repo) .gitignore
  - (darkfactory repo) .python-version
  - (darkfactory repo) README.md
  - (darkfactory repo) justfile
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - extraction
  - scaffolding
---

# Scaffold darkfactory repo structure

## Summary

Clone the empty darkfactory repo locally and set up the top-level scaffolding: `pyproject.toml` with the new package name, `mise.toml` pinning python + uv, `.python-version`, an updated `.gitignore`, a README, and a `justfile` with the harness-relevant recipes.

## Requirements

1. darkfactory is checked out locally at `/Users/sksizer2/Developer/darkfactory` (or nearby).
2. `pyproject.toml` declares `name = "darkfactory"`, `[project.scripts] prd = "darkfactory.cli:main"`, and mypy strict config.
3. `mise.toml` pins `python = "3.12"` and `uv = "latest"` (no tauri/rust/node — this is a pure Python project).
4. `.python-version` contains `3.12`.
5. `.gitignore` ignores `.venv/`, `__pycache__/`, `.mypy_cache/`, `.pytest_cache/`, `.worktrees/`, `*.pyc`.
6. `README.md` briefly describes the harness and points to the original pumice PRD-110 for the design history.
7. `justfile` exposes `prd`, `test`, `typecheck`, `lint`, `format-check` recipes.

## Technical Approach

1. Clone: `gh repo clone sksizer/darkfactory ~/Developer/darkfactory` (or reuse the existing clone at DarkFactory/).
2. Write `pyproject.toml` derived from `tools/prd-harness/pyproject.toml` with:
   - `name = "darkfactory"` (was `prd-harness`)
   - `[tool.hatch.build.targets.wheel] packages = ["src/darkfactory"]`
   - Description updated to reference the standalone tool
3. Write `mise.toml`:
   ```toml
   [tools]
   python = "3.12"
   uv = "latest"
   ```
4. Copy `.python-version` (just `3.12`).
5. Update `.gitignore` — add python-specific entries to whatever the empty repo already has.
6. Write a short `README.md` (maybe 50 lines) — what it is, quick start with `mise install && uv sync && uv run prd status`, link to the original PRD-110 design doc in pumice for history.
7. Write `justfile` with recipes:
   - `prd *ARGS` — `@uv run prd {{ARGS}}`
   - `test` — `uv run pytest`
   - `typecheck` — `uv run mypy src tests workflows`
   - `lint` — `uv run ruff check src tests` (or skip if no ruff yet)
   - `default` — `@just --list`

### History carry-over via git filter-repo

Before scaffolding, **preserve the harness's commit history** by using `git filter-repo` to extract the `tools/prd-harness/` subdirectory from a fresh pumice clone:

```bash
git clone https://github.com/sksizer/pumice.git /tmp/pumice-extract
cd /tmp/pumice-extract
git filter-repo --subdirectory-filter tools/prd-harness
# Now /tmp/pumice-extract has only the harness's history, with paths
# rewritten as if tools/prd-harness/ had always been the repo root.
```

Then push that history to darkfactory's `main` as the initial commit set, and layer the scaffolding edits (pyproject rename, mise.toml, etc.) on top. This preserves PR #51..#71 as individual commits in darkfactory rather than collapsing them into one squash. PRD-502 onwards modifies files on top of that history.

Nothing else in this PRD touches the actual source code — that's PRD-502's job.

## Acceptance Criteria

- [ ] AC-1: darkfactory repo is checked out locally with all scaffolding files present.
- [ ] AC-2: `mise install` succeeds (installs python 3.12 and uv).
- [ ] AC-3: `uv sync` succeeds with zero dependencies resolved (no src yet — this just validates pyproject is parseable).
- [ ] AC-4: `just --list` in the repo shows the recipes.
- [ ] AC-5: `.gitignore` keeps venv / pycache out of staging.
- [ ] AC-6: `git log --oneline | wc -l` in the scaffolded darkfactory shows the carried-over harness commits (PR #51..#71 individual landings), not a single initial commit.

## References

- [[PRD-500-darkfactory-extraction]] — parent epic
- `tools/prd-harness/pyproject.toml` — reference for the new pyproject
- `tools/prd-harness/README.md` — reference for the new README

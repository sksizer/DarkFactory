---
id: PRD-634
title: Rename src to python and prepare dual source tree
kind: task
status: in-progress
priority: high
effort: s
capability: simple
parent:
depends_on: []
blocks:
  - "[[PRD-635-typescript-scaffold-and-core-types]]"
impacts:
  - src/ → python/
  - pyproject.toml
  - justfile
  - .github/workflows/ci.yml
  - .gitignore
  - CLAUDE.md
  - README.md
  - .darkfactory/data/prds/*.md
workflow: task
assignee:
reviewers: []
target_version:
created: 2026-04-13
updated: '2026-04-13'
tags:
  - infrastructure
  - typescript
---

# Rename src to python and prepare dual source tree

## Summary

Rename `src/` to `python/` and update all tooling references so the repository is ready for a `ts/` source tree alongside it. Update the root `justfile` and `.gitignore` for the dual-tree layout.

## Motivation

Porting DarkFactory to TypeScript will be done incrementally while the Python version remains the working tool. Renaming `src/` to `python/` makes the language boundary explicit and prepares for a sibling `ts/` directory. Doing the rename first — before any TS code exists — keeps the git history clean: one rename commit, then TS additions in [[PRD-635-typescript-scaffold-and-core-types]].

## Requirements

### Rename `src/` to `python/`

Update every reference to `src` or `src/darkfactory` in project configuration:

1. `git mv src python` — the actual rename
2. `pyproject.toml`:
   - `tool.hatch.version.path` → `python/darkfactory/__init__.py`
   - `tool.hatch.build.targets.wheel.packages` → `["python/darkfactory"]`
   - `tool.mypy.files` → `["python", "tests"]`
   - `tool.pytest.ini_options.testpaths` → `["python", "tests"]`
3. `justfile` — all `src` references → `python`
4. `.github/workflows/ci.yml` — `uv run mypy src tests` → `python tests`
5. `CLAUDE.md`:
   - `src/darkfactory/cli/new.py` → `python/darkfactory/cli/new.py`
   - `src/darkfactory/workflows/{name}/workflow.py` → `python/darkfactory/workflows/{name}/workflow.py`
6. `README.md` — update `src/darkfactory/cli/` and `src/darkfactory/builtins/` references in Architectural Principles section
7. Active PRDs (non-terminated) in `.darkfactory/data/prds/` — bulk-update `src/darkfactory` path references to `python/darkfactory`

### Update justfile and .gitignore

Update existing Python commands and add Node ignores:

```justfile
default:
    @just --list

prd *ARGS:
    @uv run prd {{ARGS}}

test:
    uv run pytest

typecheck:
    uv run mypy python tests

format:
    uv run ruff format python tests

lint:
    uv run ruff check python tests

format-check:
    uv run ruff format --check python tests
```

Add to `.gitignore`:
```
# Node / TypeScript
ts/node_modules/
ts/dist/
ts/coverage/
```

## Acceptance criteria

- [ ] `git mv src python` committed; no broken imports in Python
- [ ] `just test`, `just typecheck`, `just lint` all pass against `python/`
- [ ] CI workflow updated and would pass
- [ ] `.gitignore` updated for Node artifacts
- [ ] `CLAUDE.md` and `README.md` updated with new paths
- [ ] Active PRDs updated — no non-terminated PRD references `src/darkfactory`
- [ ] Editable install (`uv sync && prd --help`) produces working CLI

## Out of scope

- Creating the `ts/` directory or any TypeScript files (see [[PRD-635-typescript-scaffold-and-core-types]])
- Adding TypeScript justfile recipes (`ts-test`, `ts-typecheck`) — belongs in [[PRD-635-typescript-scaffold-and-core-types]]
- Updating `src/` references in terminated (done/cancelled) PRDs — those are historical records
- Changing the Python package name or import paths (still `import darkfactory`)
- Updating test fixture strings that use `src/foo.py` etc. as arbitrary example path data — these are not project structure references

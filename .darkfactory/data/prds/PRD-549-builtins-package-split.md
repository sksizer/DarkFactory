---
id: PRD-549
title: Split builtins.py into a package of per-function modules with colocated unit tests
kind: epic
status: done
priority: medium
effort: l
capability: moderate
parent:
depends_on: []
blocks:
  - "[[PRD-549.1-pytest-config-wheel-conftest]]"
  - "[[PRD-549.2-scaffold-builtins-package]]"
  - "[[PRD-549.3-move-ensure-worktree]]"
  - "[[PRD-549.4-move-set-status]]"
  - "[[PRD-549.5-move-commit]]"
  - "[[PRD-549.6-move-push-branch]]"
  - "[[PRD-549.7-move-summarize-agent-run]]"
  - "[[PRD-549.8-move-commit-transcript]]"
  - "[[PRD-549.9-move-create-pr]]"
  - "[[PRD-549.10-move-lint-attribution]]"
  - "[[PRD-549.11-move-cleanup-worktree]]"
  - "[[PRD-549.12-final-cleanup]]"
impacts: []
workflow: planning
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: '2026-04-09'
tags:
  - refactor
  - tests
  - organization
---

# Split builtins.py into a package of per-function modules with colocated unit tests

## Summary

Two organizational changes bundled as one epic because they touch the same files and the second is much easier to apply while the first is in flight:

1. **Turn `python/darkfactory/builtins.py` (582 lines, 9 public builtins) into a package.** Each public builtin gets its own submodule (`ensure_worktree.py`, `commit.py`, `create_pr.py`, …). Shared helpers live in `_shared.py`. The registry + `@builtin` decorator live in `_registry.py`. `__init__.py` re-exports the public API so every existing `from darkfactory.builtins import create_pr` keeps working.

2. **Establish a colocated unit-test convention.** Unit tests for `foo.py` live next to it as `foo_test.py`. Integration and end-to-end tests continue to live under `tests/` at the repo root. `pytest` discovers both.

This is an **epic**. It decomposes into a handful of independently shippable child PRDs, several of which can run in parallel — intentionally structured that way to exercise DAG execution in the harness.

## Motivation

### `builtins.py` is past its organizational sweet spot

At 582 lines the file holds nine public builtins, seven private helpers, the registry decorator, and a kitchen-sink set of imports that every builtin drags in whether it needs them or not. Concrete problems:

- **Diff noise.** Any change to `create_pr` touches the same file as `ensure_worktree`, producing cross-concern PRs and merge conflicts.
- **Discovery.** "Where is the logic for `commit`?" requires a search, not a file name.
- **Import overhead.** Importing `darkfactory.builtins` pulls in every builtin's dependencies (subprocess, git, gh CLI wrappers, PR-body formatters, transcript formatters, …) even if the caller only needs `set_status`.
- **Growth trajectory.** We expect more builtins, not fewer — PRD-543 will add a `run_cli` helper and harden `create_pr`, other PRDs will add `open_editor`, `run_tests`, etc. Splitting now is cheaper than splitting later.
- **Organizational preference.** One-concept-per-file is easier to reason about, navigate, and diff.

### Colocated unit tests

Tests that verify a single module are easiest to read, write, and maintain when they sit next to that module. When you open `foo.py` in your editor, `foo_test.py` is right there. This is the convention in Go, Rust (`#[cfg(test)] mod tests`), and increasingly in Python projects. It does not replace integration/e2e tests — those still live in a top-level `tests/` dir because they span modules.

Concrete benefits for this project:

- **One-stop shop for a unit.** Open a file, see its tests, see what it's tested against.
- **Renaming is obvious.** If you rename `foo.py` → `bar.py` and forget to rename `bar_test.py`, pytest skips it silently. If the test file was off in `tests/test_foo.py`, you'd rename the module and forget the test existed for weeks.
- **Coverage pressure.** When every module ships with a colocated test file, it's immediately obvious which modules don't have one.
- **Natural fit for the split above.** Each new per-builtin module gets a matching `*_test.py` the moment it's created — no separate "and now write the test" step, no sprawling `tests/test_builtins.py` file that has to be partitioned afterwards.

### Why this is an epic, not one PR

The split-plus-colocation has a natural DAG:

- **A** (pytest config + conftest split + wheel exclusion) is independent of everything else.
- **B** (scaffold the `builtins/` package, move registry to `_registry.py`, re-export from `__init__.py`, empty functional change) depends on nothing.
- **C1…C9** (one PRD per builtin, moving it into its own submodule with a colocated `*_test.py`) each depend on both **A** and **B**, but are **independent of each other**. Nine parallel PRDs.
- **D** (delete the old `tests/test_builtins.py` once everything is migrated) depends on all of C1…C9.

That's explicitly a DAG with a fan-out of 9. Running this epic is a good stress test of parallel execution.

## Requirements

### Target module layout

```
python/darkfactory/
├── builtins/
│   ├── __init__.py              # re-exports public API, imports every submodule to register builtins
│   ├── _registry.py             # `@builtin` decorator + BUILTIN_REGISTRY dict
│   ├── _registry_test.py        # colocated unit tests
│   ├── _shared.py               # helpers used by 2+ builtins (_worktree_target, _branch_exists_*, etc.)
│   ├── _shared_test.py
│   ├── ensure_worktree.py
│   ├── ensure_worktree_test.py
│   ├── set_status.py
│   ├── set_status_test.py
│   ├── commit.py
│   ├── commit_test.py
│   ├── push_branch.py
│   ├── push_branch_test.py
│   ├── summarize_agent_run.py
│   ├── summarize_agent_run_test.py
│   ├── commit_transcript.py
│   ├── commit_transcript_test.py
│   ├── create_pr.py
│   ├── create_pr_test.py
│   ├── cleanup_worktree.py
│   └── cleanup_worktree_test.py
```

Public API preservation: every existing import site (`from darkfactory.builtins import create_pr`, `from darkfactory import builtins`, etc.) must continue to work unchanged. The refactor is strictly internal.

### Shared helpers

- Helpers used by **2 or more** builtins → `python/darkfactory/builtins/_shared.py`.
- Helpers used by **exactly one** builtin → live inside that builtin's own submodule as module-level private functions.
- The `_run` subprocess helper is a special case: PRD-543 wants to promote subprocess handling into a shared `run_cli` helper outside `builtins/`. If PRD-543 lands first, this epic adopts it. If not, `_run` goes into `_shared.py` for now and PRD-543 moves it later.
- As helpers in `_shared.py` grow to dominate their caller count or accrete too much logic, they can be promoted out into their own modules (`_git.py`, `_gh.py`, etc.). Not a hard rule — do it when the file is uncomfortable to read.

### Registry

- `@builtin(name)` decorator + `BUILTIN_REGISTRY: dict[str, BuiltInFunc]` live in `python/darkfactory/builtins/_registry.py`.
- `python/darkfactory/builtins/__init__.py` imports every submodule at the top so their `@builtin`-decorated functions register on package import. Order doesn't matter — the registry is just a dict.
- `__init__.py` re-exports the public names for backwards compatibility.

### Colocated test convention

- **Unit tests** for `foo.py` live next to it as `foo_test.py`. One test file per module under test. Tests are strict unit tests — no cross-module integration, no filesystem setup beyond `tmp_path`, no process spawning unless the module under test is specifically about spawning.
- **Integration, end-to-end, and cross-module tests** continue to live under the top-level `tests/` directory and retain the `test_*.py` prefix. No migration forced on them.
- **Mixed discovery.** Pytest is configured to discover both patterns in both locations.
- The convention applies to *new* code and to code touched by this epic. Existing tests under `tests/` migrate only when it's natural (e.g. a test that was already a pure unit test of one module moves to that module's colocated file as part of this epic). Nothing else moves.

### Pytest configuration

Update `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["src", "tests", "workflows"]
python_files = ["test_*.py", "*_test.py"]
addopts = "--import-mode=importlib"
```

- `testpaths = ["src", ...]` lets pytest discover colocated tests inside the package tree.
- `python_files` adds `*_test.py` alongside the existing `test_*.py` prefix, so old and new tests coexist.
- `--import-mode=importlib` is the modern pytest import mode. Avoids the double-import trap that path-based discovery can hit when tests live inside an installed package.

### conftest.py placement

- **Repo root `conftest.py`** for fixtures used by both unit and integration tests.
- **Package-local `conftest.py`** (e.g. `python/darkfactory/builtins/conftest.py`) for fixtures specific to that package's colocated unit tests.
- The existing `tests/conftest.py` stays put; whatever fixtures in it are truly project-wide move to repo root `conftest.py` as part of PRD-549.1.

### Wheel exclusion

- Colocated `*_test.py` files must **not** ship in the built wheel. End users don't need test files taking up space in their `site-packages/`.
- Mechanism depends on the build backend (check `pyproject.toml` — likely Hatchling or setuptools). Add the appropriate exclude glob:
  - **Hatchling**: `[tool.hatch.build.targets.wheel] exclude = ["**/*_test.py"]`
  - **setuptools**: `[tool.setuptools.packages.find] exclude = ["*_test"]` plus a MANIFEST check.
- PRD-549.1 verifies by building the wheel and asserting no `*_test.py` file is inside it.

### Must not regress

- All 283 existing tests continue to pass at every child PRD merge.
- `just test`, `just lint`, `just typecheck`, `just format-check` all clean at every child PRD merge.
- No change to the public Python API of `darkfactory.builtins`.
- No change to workflow behavior — this is a pure refactor.

## Proposed decomposition (child PRDs and DAG)

```
            ┌──────────────┐     ┌──────────────┐
            │ PRD-549.1    │     │ PRD-549.2    │
            │ pytest config│     │ scaffold     │
            │ + wheel      │     │ builtins/    │
            │ + conftest   │     │ package      │
            └──────┬───────┘     └──────┬───────┘
                   │                    │
                   └─────────┬──────────┘
                             │
    ┌───────────┬────────────┼────────────┬───────────┐
    │           │            │            │           │
  549.3      549.4         549.5        ...          549.11
  ensure_    set_status    commit       (9 parallel children,
  worktree                                one per builtin)
    │           │            │                        │
    └───────────┴────────────┼────────────────────────┘
                             │
                     ┌───────┴────────┐
                     │ PRD-549.12     │
                     │ delete old     │
                     │ tests/test_    │
                     │ builtins.py    │
                     └────────────────┘
```

### PRD-549.1 — Pytest config + wheel exclude + conftest split
- Update `[tool.pytest.ini_options]` with `testpaths`, `python_files`, `addopts` as above.
- Update build backend config to exclude `*_test.py` from the wheel.
- Split `tests/conftest.py` into repo-root `conftest.py` (shared) + keep any integration-specific fixtures in `tests/conftest.py`.
- Add one throwaway colocated `*_test.py` somewhere (e.g. `python/darkfactory/prd_test.py` with a single trivial assertion) purely to verify discovery works. Remove or replace with a real test before merge.
- Build the wheel, unzip it, assert no `*_test.py` inside. Add a `just wheel-check` recipe (or equivalent) to run this check in CI later.

### PRD-549.2 — Scaffold `builtins/` package
- Create `python/darkfactory/builtins/` directory.
- Move `BUILTIN_REGISTRY` and the `@builtin` decorator into `python/darkfactory/builtins/_registry.py`.
- Create empty `_shared.py`.
- `python/darkfactory/builtins/__init__.py` imports nothing yet (no builtins have moved), just re-exports the registry and the decorator.
- **Do not move any builtins yet.** This PRD is an empty functional change: every existing import still resolves, nothing functionally changes, all tests still pass.
- Done in one commit so that C1…C9 can branch from a clean scaffold.

### PRD-549.3 … PRD-549.11 — One PRD per builtin (9 in parallel)

> **ID format note.** Earlier drafts of this epic used alphabetic suffixes (PRD-549.3a…3i). That scheme is invalid — `prd validate` requires numeric-only IDs matching `^PRD-\d+(?:\.\d+)*$`. The children below use numeric IDs 549.3 through 549.11. Do **not** reintroduce alphabetic suffixes in any decomposition.

Nine sibling PRDs, one per public builtin:

- **PRD-549.3** `ensure_worktree` → `builtins/ensure_worktree.py` + `ensure_worktree_test.py`
- **PRD-549.4** `set_status` → `builtins/set_status.py` + `set_status_test.py`
- **PRD-549.5** `commit` → `builtins/commit.py` + `commit_test.py`
- **PRD-549.6** `push_branch` → `builtins/push_branch.py` + `push_branch_test.py`
- **PRD-549.7** `summarize_agent_run` → `builtins/summarize_agent_run.py` + `summarize_agent_run_test.py`
- **PRD-549.8** `commit_transcript` → `builtins/commit_transcript.py` + `commit_transcript_test.py`
- **PRD-549.9** `create_pr` → `builtins/create_pr.py` + `create_pr_test.py`
- **PRD-549.10** `lint_attribution` → `builtins/lint_attribution.py` + `lint_attribution_test.py`
- **PRD-549.11** `cleanup_worktree` → `builtins/cleanup_worktree.py` + `cleanup_worktree_test.py`

Each PRD in this fan-out:
1. Creates the new submodule file, moves the relevant function + its exclusively-used helpers, adds colocated `*_test.py` with unit tests covering the function's branches.
2. Deletes the function from `python/darkfactory/builtins/__init__.py` (the old monolith content). By the end of PRD-549.11, `__init__.py` should contain only imports and re-exports.
3. Passes `just test && just lint && just typecheck && just format-check`.
4. Is independent of its siblings — any conflict on the shrinking `__init__.py` file is a known friction point worth observing for DAG execution.

**DAG friction note.** All nine children modify the same file (`python/darkfactory/builtins/__init__.py` — deleting different functions from it). This will produce merge conflicts on the file if they land in parallel. Two options:
- **(a)** Accept the conflict and let the harness handle rebases. This is a *good* DAG stress test — it exposes whether the harness can rebase child PRDs of an epic cleanly.
- **(b)** Have PRD-549.2 also pre-delete `builtins.py` entirely and move its contents into a temporary `_legacy.py` that each child imports from and chips away at. More complex but avoids the conflict.
- Recommendation: **(a)** — the point of this epic *is* to stress-test the harness, and avoiding the conflict would defeat that.

### PRD-549.12 — Final cleanup
- Delete `tests/test_builtins.py` (its coverage has been migrated into the colocated files by 549.3–549.11).
- Delete `python/darkfactory/builtins.py` if it still exists as a stub; otherwise no-op.
- Verify the `builtins/` directory is the single source of truth and re-exports everything needed.

## Acceptance Criteria

- [ ] **AC-1** (post-549.1): `pyproject.toml` configures pytest to discover both `test_*.py` and `*_test.py` across `src/`, `tests/`, and `workflows/` with `--import-mode=importlib`. All 283 existing tests pass under the new config.
- [ ] **AC-2** (post-549.1): A colocated `*_test.py` file created anywhere under `python/darkfactory/` is discovered and run by `just test` without any additional config.
- [ ] **AC-3** (post-549.1): A built wheel (`uv build` / `python -m build`) contains zero `*_test.py` files. Automated check exists to prove this.
- [ ] **AC-4** (post-549.1): `conftest.py` at the repo root provides shared fixtures to both `tests/` and colocated unit tests.
- [ ] **AC-5** (post-549.2): `python/darkfactory/builtins/` exists as a package, `_registry.py` holds the decorator + registry, `__init__.py` re-exports the public API unchanged. Every existing import site still resolves. All tests pass.
- [ ] **AC-6** (post-549.3–549.11): Each of the nine builtins lives in its own submodule `python/darkfactory/builtins/<name>.py` with a colocated `<name>_test.py` that exercises the function's non-trivial branches.
- [ ] **AC-7** (post-549.11): Shared helpers used by more than one builtin live in `python/darkfactory/builtins/_shared.py`. Helpers used by exactly one builtin live in that builtin's own submodule.
- [ ] **AC-8** (post-549.12): The old `python/darkfactory/builtins.py` monolith and `tests/test_builtins.py` are both deleted. No dead code remains.
- [ ] **AC-9** (ongoing): At every child PRD merge, `just test`, `just lint`, `just typecheck`, and `just format-check` all pass clean. No existing test is deleted without a colocated replacement.
- [ ] **AC-10** (ongoing): The public Python API of `darkfactory.builtins` is unchanged. Grep of the rest of the codebase confirms no import sites needed edits beyond what the refactor itself changed.

## Open Questions

- [ ] **Conflict-stress vs conflict-avoidance in the 549.3–549.11 fan-out.** Recommendation: accept the conflict and let the harness prove it can rebase. Confirm before kicking off the nine parallel children.
- [ ] **PRD-543 interaction with `_run`.** PRD-543 wants to promote subprocess handling into a shared `run_cli` helper. If 543 merges first, this epic adopts the new helper directly and skips `_shared._run`. If 549 merges first, `_run` lives in `builtins/_shared.py` until 543 moves it. Either order is fine; flagging so the two don't surprise each other.
- [ ] **Test discovery under `workflows/`.** Do we want colocated unit tests inside workflow modules too, or is the convention scoped to `python/darkfactory/`? Leaning toward "yes, everywhere" — but flagging since it expands the pytest `testpaths` list.
- [ ] **`summarize_agent_run` coverage.** The existing `tests/test_builtins.py` coverage for this function may be thin; PRD-549.7 should audit and backfill as needed.
- [ ] **Follow-up epics.** Same treatment for `cli.py`, `runner.py`, and `invoke.py` is explicitly **out of scope** for this epic. If the pattern works out, each of those gets its own epic; the first to run will revisit the lessons learned here.

## References

- Current `python/darkfactory/builtins.py` — 582 lines, 9 public builtins, 7 private helpers, registry decorator, all in one file.
- Current `tests/test_builtins.py` — sibling monolith.
- [[PRD-543-harness-pr-creation-hardening]] — overlaps on `_run` / `create_pr`.
- Pytest import modes: https://docs.pytest.org/en/stable/explanation/pythonpath.html#import-modes

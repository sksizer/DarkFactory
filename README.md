# darkfactory

[![CI](https://github.com/sksizer/DarkFactory/actions/workflows/ci.yml/badge.svg)](https://github.com/sksizer/DarkFactory/actions/workflows/ci.yml)

Standalone PRD harness: DAG orchestration, declarative workflows, agent invocation, and stacked PRs.

This is the extracted standalone version of the harness originally developed inside [pumice](https://github.com/sksizer/pumice) under `tools/prd-harness`. See [PRD-110](https://github.com/sksizer/pumice/blob/main/docs/prd/PRD-110-prd-harness.md) for the full design history.

## Quickstart

### Install

```bash
uv tool install darkfactory
# or: pipx install darkfactory
```

### Set up a project

```bash
cd ~/my-project
prd init        # creates .darkfactory/ directory
prd status      # view PRD status
```

### Project layout

darkfactory stores all project state under `.darkfactory/` at your repo root:
- `.darkfactory/prds/` — PRD files (tracked in git)
- `.darkfactory/workflows/` — custom workflows (tracked; optional)
- `.darkfactory/config.toml` — project config (tracked; optional)
- `.darkfactory/worktrees/` — runtime state (git-ignored)

This convention applies universally — darkfactory's own repo uses the same `.darkfactory/` layout with no special cases.

## Recipes

```bash
just          # list all recipes
just prd      # run prd CLI (pass args after)
just test     # run pytest
just typecheck  # run mypy
just lint     # run ruff check
just format-check  # run ruff format --check
```

## Architecture

Three layers:

1. **SDLC harness** — CLI, DAG orchestration, status transitions
2. **Built-in tasks** — `ensure_worktree`, `commit`, `create_pr`, etc.
3. **Workflows** — declarative Python (`workflows/{name}/workflow.py`) describing the per-PRD-type implementation procedure

## Concurrency

`prd run` uses advisory file locking (via [`filelock`](https://pypi.org/project/filelock/)) to prevent two runners from working on the same PRD simultaneously. The lock is held for the lifetime of the runner process and auto-released by the kernel on process exit (including crashes). This works on macOS, Linux, and Windows.

Read-only subcommands (`prd status`, `prd plan`, `prd validate`) do not acquire locks and are safe to run from multiple terminals at the same time.

## Contributing

### Branch protection

The `main` branch requires **"Require branches to be up to date before merging"** in GitHub branch protection settings. This prevents a class of silent code loss where a long-lived branch that rewrites a file merges cleanly but drops changes that landed on `main` after the branch was created.

If your PR is out of date with `main`, GitHub will block the merge until you rebase or merge main into your branch. This is intentional — it surfaces conflicts that would otherwise be silently resolved in the wrong direction.

The ruleset definition lives at [`.github/rulesets/main-protection.json`](.github/rulesets/main-protection.json) and can be imported via **Settings > Rules > Rulesets > New ruleset > Import a ruleset**.

### Large refactors

When a PR does a structural rewrite (e.g. moving a module into a package, renaming files), rebase onto latest `main` before the final review pass. Structural changes are the most likely to silently drop concurrent work during merge.

## Architectural Principles

### Module-per-concern with peer tests

New functionality should be decomposed into small, focused module files rather than growing existing files. Each module should have a peer test file in the same directory (e.g., `_python.py` / `_python_test.py`). This fights file bloat and keeps context small — for both humans and AI agents working on the codebase. See `src/darkfactory/cli/` and `src/darkfactory/builtins/` for the established patterns.

### Parse errors at the boundary, trust types internally

Validate external input (config files, CLI args, frontmatter) strictly at the point of ingestion — prefer parsing into typed structures that fail fast on bad input. Once data is parsed and typed, trust it throughout the codebase. No defensive shape checks at every call site.

### Hard failures over silent degradation

Start with hard failures and clear error messages when invariants are violated. Relax to graceful degradation only after real usage reveals where strictness hurts more than it helps.

## Development

```bash
just typecheck
just test
```

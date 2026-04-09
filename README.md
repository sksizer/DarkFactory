# darkfactory

[![CI](https://github.com/sksizer/DarkFactory/actions/workflows/ci.yml/badge.svg)](https://github.com/sksizer/DarkFactory/actions/workflows/ci.yml)

Standalone PRD harness: DAG orchestration, declarative workflows, agent invocation, and stacked PRs.

This is the extracted standalone version of the harness originally developed inside [pumice](https://github.com/sksizer/pumice) under `tools/prd-harness`. See [PRD-110](https://github.com/sksizer/pumice/blob/main/docs/prd/PRD-110-prd-harness.md) for the full design history.

## Quick start

```bash
# Install tools (requires mise)
mise install

# Install Python dependencies
uv sync

# Install git hooks (prevents accidental direct pushes to main)
./scripts/install-hooks.sh

# Run the CLI
uv run prd status
```

Or use the justfile recipes:

```bash
just prd status
just prd validate
just prd tree PRD-001
just prd next --limit 5
```

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

## Development

```bash
just typecheck
just test
```

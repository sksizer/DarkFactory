# prd-harness

SDLC harness for the Pumice PRD lifecycle. Walks the dependency DAG, creates worktrees, invokes Claude Code agents per declarative workflow, runs checks, and stacks pull requests.

See [PRD-110](../../docs/prd/PRD-110-prd-harness.md) for the full specification.

## Quick start

From the repo root:

```bash
# Install (mise installs python + uv from mise.toml)
mise install
uv sync --project tools/prd-harness

# Read-only commands (foundation phase) — three equivalent forms:
just prd status                                  # justfile recipe (recommended)
make prd ARGS="status"                           # makefile target
./scripts/prd status                             # direct shell wrapper
uv run --project tools/prd-harness prd status    # raw uv invocation
```

Common subcommands:

```bash
just prd status
just prd validate
just prd tree PRD-001
just prd next --limit 5
just prd conflicts PRD-070
```

## Architecture

Three layers (see [PRD-110](../../docs/prd/PRD-110-prd-harness.md) for details):

1. **SDLC harness** — CLI, DAG orchestration, status transitions
2. **Built-in tasks** — `ensure_worktree`, `commit`, `create_pr`, etc.
3. **Workflows** — declarative Python (`workflows/{name}/workflow.py`) describing the per-PRD-type implementation procedure

## Development

```bash
# Type-check
uv run --project tools/prd-harness mypy src tests

# Test
uv run --project tools/prd-harness pytest
```

## Status

Foundation phase: PRD parsing, DAG/containment/impacts modules, read-only CLI subcommands. Workflow execution and migration are follow-up phases.

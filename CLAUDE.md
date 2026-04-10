# DarkFactory — Claude Code Instructions

## Project Overview

DarkFactory is a standalone PRD harness: DAG orchestration, declarative workflows, agent invocation, and stacked PRs. Python CLI tool using hatchling, mypy strict, pytest.

## Architectural Principles

See `README.md § Architectural Principles` for the canonical list. Key points:

- **Module-per-concern with peer tests** — decompose into small focused files, each with a peer test file. Follow patterns in `cli/` and `builtins/`.
- **Parse at the boundary, trust types internally** — validate config/frontmatter/CLI args at ingestion via strict types (Pydantic, dataclasses). No defensive checks deeper in.
- **Hard failures over silent degradation** — fail loudly with clear messages. Don't silently skip or fall back.

## Code Standards

- mypy strict mode across all source and test files
- ruff for linting and formatting
- Tests colocated as peer files (`_foo.py` / `_foo_test.py`) or in `tests/` for integration tests
- Minimal runtime dependencies (pyyaml, filelock, rich)

## PRD System

- PRDs live in `.darkfactory/prds/` with YAML frontmatter
- Use `_next_flat_prd_id()` from `src/darkfactory/cli/new.py` for new PRD IDs
- Workflows in `src/darkfactory/workflows/{name}/workflow.py`
- Config in `.darkfactory/config.toml`

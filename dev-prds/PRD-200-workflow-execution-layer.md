---
id: "PRD-200"
title: "Workflow Execution Layer"
kind: epic
status: in-progress
priority: high
effort: l
capability: complex
parent: null
depends_on: []
blocks:
  - "[[PRD-201-workflow-dataclasses]]"
  - "[[PRD-202-builtins-registry-stubs]]"
  - "[[PRD-203-workflow-loader]]"
  - "[[PRD-204-assignment-logic]]"
  - "[[PRD-205-default-workflow]]"
  - "[[PRD-206-list-workflows-assign-cli]]"
  - "[[PRD-207-prompt-templates]]"
  - "[[PRD-208-agent-invoke]]"
  - "[[PRD-209-real-builtins]]"
  - "[[PRD-210-runner]]"
  - "[[PRD-211-plan-run-cli]]"
impacts:
  - tools/prd-harness/src/prd_harness/**
  - tools/prd-harness/workflows/default/**
  - tools/prd-harness/tests/**
workflow: null
target_version: null
created: 2026-04-07
updated: 2026-04-07
tags:
  - harness
  - workflows
  - execution
---

# Workflow Execution Layer

## Summary

The second phase of the PRD harness: adds the declarative workflow system, the builtin task primitives, the workflow loader and assignment logic, the default workflow, the Claude Code agent invocation wrapper, the runner that ties it all together, and the `prd plan` / `prd run` CLI subcommands. After this epic, the harness can actually execute a workflow against a single PRD end-to-end.

## Motivation

PRD-110 (the harness meta-spec in `docs/prd/`) describes the full system. The first phase (PR #51 — foundation) shipped the read-only layer: PRD parsing, graph, containment, impacts, and the status/validate/tree/conflicts CLI. This epic adds the execution layer: workflows + builtins + runner + agent invoke + `prd plan` and `prd run`.

At the end of this epic we should be able to:

```bash
just prd run PRD-2.3.4 --execute   # runs a single trivial task PRD via the default workflow
```

...and watch an agent implement it end-to-end: worktree → status → commit → agent invocation → tests → lint → commit → push → PR.

## Requirements

1. Declarative workflow abstractions (BuiltIn, AgentTask, ShellTask, Workflow) usable from a workflow.py module
2. Built-in task registry with deterministic primitives (ensure_worktree, set_status, commit, push_branch, create_pr, cleanup_worktree)
3. Dynamic workflow loader scanning `workflows/*/workflow.py`
4. Workflow assignment: explicit frontmatter field > `applies_to` predicate > `default` fallback
5. Default workflow that runs for any PRD without specialization
6. Prompt template loader with `{{PRD_ID}}` etc. substitution
7. Claude Code subprocess wrapper with sentinel-based success detection
8. Runner that walks a workflow's task list against an ExecutionContext, enforcing status transitions and retry logic
9. `prd plan <PRD-ID>` — dry-run output showing the execution plan
10. `prd run <PRD-ID> [--execute]` — single-PRD execution

## Technical Approach

See child task PRDs for the detailed decomposition. Summary of the 11 tasks and their dependency order:

```
201 (workflow.py) ──┬── 202 (builtins stubs)
                    ├── 203 (loader)
                    ├── 204 (assign)
                    ├── 207 (templates)
                    └── 208 (invoke)
                         │
                    ┌────┴──────────────────┐
                    ▼                       ▼
              205 (default workflow)   209 (real builtins, replaces 202)
                    │                       │
                    ▼                       │
              206 (list/assign CLI)         │
                                            │
                              210 (runner) ─┤
                                    │
                                    ▼
                              211 (plan/run CLI)
```

## Acceptance Criteria

- [ ] AC-1: All 11 child task PRDs are `done`
- [ ] AC-2: `just prd-dev list-workflows` shows the `default` workflow
- [ ] AC-3: `just prd-dev plan PRD-201` produces a readable execution plan without side effects
- [ ] AC-4: `just prd run PRD-<trivial>` (against the canonical PRD set) executes end-to-end on a real task PRD
- [ ] AC-5: `uv run pytest` passes (existing 47 tests + new ones for each module)
- [ ] AC-6: `uv run mypy src tests` passes with `strict = true`

## References

- `docs/prd/PRD-110-prd-harness.md` — full system spec
- `~/.claude/plans/fizzy-herding-acorn.md` — detailed implementation plan
- Child tasks PRD-201 through PRD-211

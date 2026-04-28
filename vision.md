---
id: "PRD-110"
title: "PRD Harness (SDLC Automation System)"
kind: epic
status: ready
priority: high
effort: xl
capability: complex
parent: null
depends_on: []
blocks: []
assignee: claude
reviewers: []
target_version: null
created: 2026-04-06
updated: 2026-04-06
tags:
  - automation
  - tooling
  - prd
  - harness
  - meta
---

# PRD Harness (SDLC Automation System)

## Summary

A layered SDLC harness in `tools/prd-harness/` that automates the PRD lifecycle: walking the dependency DAG, creating worktrees, invoking Claude Code agents per declarative workflow, running checks, and stacking pull requests. Separates orchestration (deterministic) from per-PRD implementation (workflow-driven). Includes a planning workflow that decomposes large PRDs into fine-grained children, file-impact tracking for safe parallelization, and a one-shot migration of existing PRD IDs from flat (`PRD-070`) to hierarchical (`PRD-4.1.1`).

## Motivation

Pumice has ~47 PRDs forming a dependency DAG. 27 are fine-grained tasks designed to be agent-delegable. The bottleneck is now manual: picking an actionable PRD, branching, invoking the agent, running checks, opening a PR. Automating this lets a single human (or a meta-agent) trigger entire stacked PR chains with one command. The architecture must support specialized per-PRD-type workflows (UI components, planning/decomposition, future kinds) without duplicating SDLC primitives.

## Requirements

### Functional

#### Layer 1 — Workflows (declarative Python, per PRD type)

1. **Workflow definition**: each workflow is a Python module at `tools/prd-harness/workflows/{name}/workflow.py` exporting a `workflow = Workflow(...)` object built from `BuiltIn`, `AgentTask`, and `ShellTask` task instances.
2. **Default workflow**: catchall implementation workflow for general PRDs. Tasks: ensure_worktree → set_status in-progress → commit → AgentTask(implement) → ShellTask(test) → ShellTask(lint) → set_status review → push → create_pr.
3. **UI component workflow**: triggered by `tags` containing `ui`/`component`/`frontend`/`settings`. Pre-loads design-system context into the agent prompt, runs `pnpm storybook:build` as verification, pins model to `sonnet`.
4. **Planning workflow**: meta-workflow that decomposes `epic`/`feature` PRDs lacking task descendants into child task PRDs with `parent` and `depends_on` links. Uses model `opus`. Allowlist excludes `Edit` (only creates new PRD files; never modifies existing code).
5. **Workflow assignment**: explicit `workflow:` frontmatter field takes precedence; otherwise the highest-priority workflow whose `applies_to(prd)` returns true wins; `default` is the fallback. The `prd assign` subcommand can persist resolved assignments via `--write`.

#### Layer 2 — Built-in tasks (deterministic primitives)

6. **Built-in registry**: `BUILTINS: dict[str, BuiltInFunc]` populated via `@builtin("name")` decorators. Workflows reference builtins via `BuiltIn("name", kwargs={...})`.
7. **Shipped builtins**: `ensure_worktree`, `set_status`, `commit`, `push_branch`, `create_pr`, `cleanup_worktree`, `touch_updated`.
8. **Worktree isolation**: `ensure_worktree` creates `.worktrees/{prd_id}-{slug}/` via `git worktree add`, enabling parallel execution of independent DAG nodes.
9. **Status transitions**: enforced by the runner — `ready → in-progress` on first task, `in-progress → review` on PR creation, `in-progress → blocked` on failure. `review → done` stays manual.

#### Layer 3 — SDLC harness (orchestration + CLI)

10. **CLI subcommands** (all via `uv run --project tools/prd-harness prd <cmd>`):
    - `status` — DAG overview, counts by status, top-N actionable
    - `next [--limit N] [--capability TIER]` — list actionable PRDs
    - `validate` — cycle/missing-dep/orphan-parent/id-mismatch checks; warns on impact overlaps
    - `tree [<PRD-ID>]` — containment tree visualization
    - `children <PRD-ID>` — direct children
    - `orphans` — top-level PRDs (no parent)
    - `undecomposed` — epics/features lacking task children
    - `conflicts <PRD-ID>` — show PRDs whose impacts overlap
    - `list-workflows` — show loaded workflows with priorities/predicates
    - `assign [--write]` — compute workflow assignment per PRD
    - `plan <PRD-ID>` — show execution plan (workflow, tasks, model, prompts)
    - `run <PRD-ID> [--execute]` — single-PRD execution (dry-run by default)
    - `run-chain <PRD-ID> [--execute] [--max N]` — walk DAG, stack worktrees and PRs
    - `migrate [--dry-run]` — one-shot flat→hierarchical ID migration
11. **Capability→model mapping**: `trivial→haiku`, `simple→sonnet`, `moderate→sonnet`, `complex→opus`. Overridable per AgentTask or via `--model` flag.
12. **Sentinel-based agent contract**: agents must emit `PRD_EXECUTE_OK: {prd_id}` or `PRD_EXECUTE_FAILED: {reason}` as their final line. The harness greps for these.
13. **Restricted tool allowlists**: agents never get `git push`, `gh`, or unbounded `Bash(*)`. The harness owns destructive and remote operations.
14. **Stacked PRs**: `run-chain` stacks PRs by setting each new PR's base to the previous PR's branch. Worktrees persist for the duration of the chain.

#### Containment tree (parent/children)

15. **Two graphs**: the dependency DAG (`depends_on`/`blocks`) and the containment tree (`parent`) are orthogonal and surfaced separately.
16. **`is_runnable` guard**: an epic/feature with undecomposed children cannot run through implementation workflows. The runner refuses or auto-routes to `planning`.
17. **Hierarchical IDs**: PRD IDs migrate from flat (`PRD-070`) to hierarchical (`PRD-4.1.1`). Roots are `PRD-1`, `PRD-2`, ...; descendants append `.N` per level. Filenames: `PRD-{id}-{slug}.md`. Sibling order within a parent is determined by original flat numeric ID ascending.
18. **Natural sort**: hierarchical IDs sort numerically per component, not lexically (`PRD-1.2` before `PRD-1.10`).

#### File impact tracking

19. **`impacts` frontmatter field**: list of glob patterns naming files the PRD will create, modify, or delete. Empty/missing means undeclared.
20. **Overlap detection**: `prd conflicts <PRD-ID>` lists other PRDs whose declared impacts intersect. `prd validate` warns on unacknowledged overlaps between `ready` PRDs.
21. **Parallel safety**: `run-chain` parallelizes sibling DAG nodes only when their declared impacts don't overlap. Otherwise it serializes them.

#### Migration

22. **Flat→hierarchical migration**: `prd migrate` rewrites every existing PRD file (filename, frontmatter `id`, `parent`, `depends_on`, `blocks`, body wikilinks). Atomic single commit. Schema is updated to accept only the hierarchical pattern post-migration.

#### Claude Code skill

23. **`/prd-execute` skill**: `.claude/skills/prd-execute/SKILL.md` invokable in an interactive Claude Code session. Reads the same workflow prompt files as the harness. Standalone mode assumes the user is on a working branch; orchestrated mode is invoked by `prd run` after creating the worktree.

### Non-Functional

1. **Type safety**: all Python code is annotated and passes `mypy --strict`. `from __future__ import annotations` everywhere.
2. **Package management**: uv-managed package with `pyproject.toml` declaring dependencies (`pyyaml`, `types-PyYAML`, `pytest`, `mypy`). Python 3.11+.
3. **Determinism**: sibling-tie-breaks are alphabetical/natural; the harness produces the same plan output on the same input every time.
4. **Default-safe**: `--dry-run` is the default for any subcommand that mutates state. `--execute` is the explicit opt-in.
5. **Idempotent**: running `prd run` on a PRD already in `in-progress` resumes from its existing worktree rather than failing.
6. **Bounded cost**: 1 retry per AgentTask, default `run-chain --max 5`, capability→model routing for budget control.
7. **Test coverage**: unit tests for prd parsing, graph operations, containment, impacts, assignment, builtin dispatch, migration. Run via `uv run pytest`.

## Technical Approach

See `/Users/sksizer2/.claude/plans/fizzy-herding-acorn.md` for the detailed implementation plan including:
- Full package layout under `tools/prd-harness/`
- Type-annotated dataclass definitions for `Task`, `BuiltIn`, `AgentTask`, `ShellTask`, `Workflow`, `ExecutionContext`
- Workflow Python source examples for `default`, `ui-component`, `planning`
- Migration algorithm with sibling-order rules and sample mapping
- CLI subcommand specifications
- Risk catalog and mitigations

### Architecture summary

```
┌─────────────────────────────────────────────────┐
│  Layer 3: SDLC HARNESS (CLI + DAG)              │
│   prd status / next / plan / run / run-chain    │
│   prd assign / list-workflows / migrate         │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│  Layer 2: BUILT-IN TASKS                        │
│   ensure_worktree / set_status / commit /       │
│   push_branch / create_pr / cleanup_worktree    │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│  Layer 1: WORKFLOWS (per PRD type)              │
│   default / ui-component / planning             │
└─────────────────────────────────────────────────┘
```

### Key files

- `tools/prd-harness/pyproject.toml`
- `tools/prd-harness/src/prd_harness/{__init__,cli,prd,graph,containment,impacts,workflow,builtins,runner,invoke,assign,loader,migrate,templates}.py`
- `tools/prd-harness/workflows/{default,planning,ui-component}/{workflow.py,prompts/}`
- `.claude/skills/prd-execute/SKILL.md`
- `.scripts/prd` — thin shell wrapper for ergonomics
- `docs/prd/_schema.yaml` — add `workflow` and `impacts` fields, update id pattern
- `docs/prd/_template.md` — add new fields

## Acceptance Criteria

- [ ] AC-1: `prd migrate --execute` rewrites all 47 flat-ID PRDs to hierarchical form with no data loss; `prd validate` passes post-migration.
- [ ] AC-2: `uv run prd status` prints accurate counts for the migrated PRD set.
- [ ] AC-3: `prd validate` detects injected cycles and missing deps; exits non-zero.
- [ ] AC-4: `prd list-workflows` shows `default`, `planning`, and `ui-component` with priorities and descriptions.
- [ ] AC-5: `prd assign` resolves a UI-tagged PRD to `ui-component` and a non-UI PRD to `default`; an undecomposed epic to `planning`.
- [ ] AC-6: `prd plan <task-PRD>` shows the assigned workflow's task list, capability→model mapping, and composed prompt preview. No git changes.
- [ ] AC-7: `prd run <trivial-PRD> --execute` creates a worktree, runs the default workflow end-to-end, produces a PR, and leaves status = `review`.
- [ ] AC-8: `prd run <ui-PRD> --execute` routes to `ui-component`, runs storybook build, creates a PR.
- [ ] AC-9: `/prd-execute <PRD-ID>` skill works standalone in a fresh Claude Code session and produces an equivalent commit.
- [ ] AC-10: `prd run-chain <PRD> --execute --max 2` creates stacked worktrees and stacked PRs.
- [ ] AC-11: Explicit `workflow:` frontmatter override beats `applies_to` predicate matching.
- [ ] AC-12: `prd_harness` unit tests pass: PRD parsing, graph, cycles, containment, impacts, assignment, migration.
- [ ] AC-13: `mypy --strict` passes with zero type errors.
- [ ] AC-14: `prd tree PRD-1` shows the Core Timer Engine containment subtree post-migration.
- [ ] AC-15: `prd undecomposed` lists epics/features lacking task children.
- [ ] AC-16: Running planning on an undecomposed epic produces valid child task PRDs with `parent` set and IDs following `{parent}.{N}`.
- [ ] AC-17: `prd run <epic>` on an undecomposed epic refuses to use `default` and routes to `planning`.
- [ ] AC-18: Hierarchical IDs sort naturally: `PRD-1.2` before `PRD-1.10`.
- [ ] AC-19: `prd conflicts <PRD>` lists every other PRD whose `impacts` globs overlap, plus the specific files.
- [ ] AC-20: `prd validate` warns on overlapping impacts between `ready` PRDs with no explicit dependency.
- [ ] AC-21: `prd run-chain` serializes sibling DAG nodes with overlapping impacts; parallelizes when disjoint.
- [ ] AC-22: The planning workflow populates `impacts` on every generated task PRD with specific file paths.

## Open Questions

- [ ] **OPEN**: Should `review → done` be automated post-merge (via webhook or polling) or stay manual?
- [ ] **OPEN**: Worktree cleanup policy for chain execution — auto-cleanup after merge, after manual `prd cleanup`, or both?
- [ ] **OPEN**: Strict-impacts mode that fails an AgentTask if it modifies files outside its declared `impacts` set?
- [ ] **DEFERRED**: Verification workflow as a second-pass agent that checks the implementation against acceptance criteria before PR creation.
- [ ] **DEFERRED**: Multi-machine parallelism (running multiple worktrees on separate hosts).

## References

- `/Users/sksizer2/.claude/plans/fizzy-herding-acorn.md` — full implementation plan with code examples and risk catalog
- `docs/prd/_schema.yaml` — frontmatter contract being extended
- `docs/prd/README.md` — schema conventions
- `commitlint.config.ts` — conventional-commits rules the workflows must respect
- `scripts/dev-port.sh` — reference script style; harness reuses its port-block convention for parallel worktrees
- [rust-template scripts](https://github.com/sksizer/rust-template/blob/main/scripts/bring_up_to_date_all.sh) — pattern reference for hybrid bash + agent invocation


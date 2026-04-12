---
id: PRD-631
title: Unified RunContext, parameterized git primitives, and project operation PR support
kind: epic
status: draft
priority: high
effort: l
capability: complex
parent: null
depends_on:
  - "[[PRD-632-reorganize-workflow-and-operation-definitions]]"
blocks: []
impacts:
  - src/darkfactory/workflow/_core.py
  - src/darkfactory/system.py
  - src/darkfactory/runner.py
  - src/darkfactory/operations/system_builtins.py
  - src/darkfactory/operations/ensure_worktree.py
  - src/darkfactory/operations/commit.py
  - src/darkfactory/operations/push_branch.py
  - src/darkfactory/operations/create_pr.py
  - src/darkfactory/utils/git/
  - src/darkfactory/utils/github/
workflow: null
assignee: null
reviewers: []
target_version: null
created: 2026-04-12
updated: 2026-04-12
tags:
  - architecture
  - refactor
---

# Unified RunContext, parameterized git primitives, and project operation PR support

## Summary

Four changes shipped together: (1) unify `Workflow` and `ProjectOperation` into a single `Workflow` type, (2) unify `ExecutionContext` and `ProjectContext` into a single `RunContext`, (3) extract context-agnostic git primitives from the current workflow operations, and (4) register git operations in `PROJECT_BUILTINS` so project workflows can create worktrees and PRs.

## Dependency on PRD-632

PRD-632 lands first and delivers:
- `prd system` → `prd project` CLI rename
- Workflow definitions moved to `definitions/prd/`, project operations to `definitions/project/`
- `SystemOperation` / `SystemContext` references renamed to "project" throughout CLI
- Shell tasks in project operations execute with `operation_dir` as cwd
- `load_operations()` gains a two-layer scan (built-in + project)

PRD-631 builds on that by unifying the execution contexts and making git primitives available to project operations. Where PRD-632 renames the CLI and reorganizes definitions, PRD-631 unifies the runtime.

**Note**: PRD-632 now renames `SystemOperation` → `ProjectOperation`, `SystemContext` → `ProjectContext`, `system.py` → `project.py`, and `SYSTEM_BUILTINS` → `PROJECT_BUILTINS`. PRD-631 inherits those names and replaces `ProjectContext` (along with `ExecutionContext`) with the unified `RunContext`. References below use the post-632 names.

## Motivation

Project operations cannot create worktrees or PRs today. The `ProjectOperation` dataclass declares `creates_pr`, `pr_title`, and `pr_body` fields, but no operations implement them. The `plan` operation (moved to `definitions/project/plan/` by PRD-632) references `ensure_worktree`, `commit`, `push_branch`, `create_pr` — all of which fail at runtime because they only exist in the workflow `BUILTINS` registry.

Two separate definition types (`Workflow` and `ProjectOperation`) and two separate context types (`ExecutionContext` and `ProjectContext`) maintain artificial distinctions. Both are "a named sequence of tasks with metadata" executed by the same runner. The differences are in *how they're invoked* and *what runtime data the runner seeds* — which is exactly what `PhaseState` payloads handle. Unifying the types eliminates duplication and makes git primitives naturally available to both execution modes.

## Requirements

### Functional

1. **Unified `Workflow` type** replaces both `Workflow` and `ProjectOperation`. The definition type is kept general — routing fields (`applies_to`, `priority`) are optional; runtime concerns (`creates_pr`, `pr_title`, etc.) move to PhaseState payloads, not the definition.
2. **Unified `RunContext`** replaces both `ExecutionContext` and `ProjectContext` as the single context type passed to all operations and task runners.
3. **Parameterized git primitives** — context-free functions for worktree creation, commit, push, and PR creation, living in `utils/`.
4. **Git operations available in both registries** — `ensure_worktree`, `commit`, `push_branch`, `create_pr` work in both PRD workflow and project workflow modes.
5. **All `operation.py` entry files become `workflow.py`** — single discovery mechanism via `load_workflows()`.
6. Existing PRD workflow runs behave identically.
7. Existing project operations (verify-merges, audit-impacts, discuss) behave identically.
8. `prd project run plan --target PRD-X --execute` creates worktree, commits, pushes, and opens a PR.

### Non-Functional

1. No duplication of git/github subprocess logic — one implementation, two registrations.
2. Existing tests continue to pass after migration.
3. `mypy --strict` clean across all changed modules.

## Technical Approach

### Part 0: Unify Workflow and ProjectOperation

`ProjectOperation` is absorbed into `Workflow`. The `Workflow` dataclass stays general:

```python
@dataclass
class Workflow:
    name: str
    description: str
    tasks: list[Task]
    workflow_dir: Path | None = None
    # Routing (PRD workflows only — ignored for project workflows)
    applies_to: AppliesToPredicate = _default_applies_to
    priority: int = 0
    template_name: str | None = None
```

Fields that were on `ProjectOperation` but are runtime concerns move to PhaseState payloads:

| Former `ProjectOperation` field | Where it goes |
|---|---|
| `creates_pr` | Implicit — if the task list includes `create_pr`, a PR gets created |
| `pr_title` / `pr_body` | `PrRequest` payload in PhaseState, put by the task that initiates PR creation |
| `requires_clean_main` | Runner-level pre-check (invocation config, not definition) |
| `accepts_target` | Runner-level — whether `--target` is required, part of invocation |

All `operation.py` entry files are renamed to `workflow.py`. The loader uses a single `load_workflows()` function. PRD-632's `definitions/project/` directory keeps its structure, but each subdirectory now contains `workflow.py` exporting a `Workflow` instance instead of `operation.py` exporting a `ProjectOperation`.

### Part 1: Parameterized git primitives

Extract the actual logic from the current workflow operations into plain functions in `utils/`:

```
utils/git/primitives.py    — do_ensure_worktree(), do_commit(), do_push()
utils/github/primitives.py — do_create_pr()
```

These take explicit arguments (repo_root, branch, message, etc.) — no context, no PhaseState. Independently testable.

The existing workflow operations become thin adapters: read values from `ctx` / PhaseState payloads, call the primitive, update state.

### Part 2: Unified RunContext

Replace `ExecutionContext` and `SystemContext` with a single `RunContext` dataclass.

**Shared fields** (present in both today, move directly to RunContext):

| Field | Type | Notes |
|---|---|---|
| `repo_root` | `Path` | Immutable |
| `cwd` | `Path` | Starts as repo_root, may move to worktree |
| `dry_run` | `bool` | Default True |
| `logger` | `Logger` | Factory-created |
| `state` | `PhaseState` | Typed inter-task registry |
| `event_writer` | `EventWriter \| None` | Optional |
| `pr_url` | `str \| None` | Set by create_pr |

**Variant data moves to frozen PhaseState payloads:**

| Payload dataclass | Contents | Put by |
|---|---|---|
| `PrdWorkflowRun` | `prd: PRD`, `workflow: Workflow`, `branch_name: str`, `base_ref: str`, `run_summary: str \| None` | `run_prd_workflow()` at construction |
| `ProjectRun` | `workflow: Workflow`, `prds: dict[str, PRD]`, `targets: list[str]`, `target_prd: str \| None`, `report: list[str]` | `run_project_workflow()` at construction |
| `WorktreeState` | `branch: str`, `base_ref: str`, `worktree_path: Path` | `ensure_worktree` operation (both modes) |
| `PrRequest` | `title: str`, `body: str` | Task that initiates PR creation (or runner from workflow metadata) |

**Design choice: separate `WorktreeState` payload (Option B)**

`ensure_worktree` creates and puts a frozen `WorktreeState`. Downstream operations (`commit`, `push_branch`, `create_pr`) get it. This is context-agnostic — the same `WorktreeState` type is used regardless of whether a PRD workflow or project operation created the worktree.

Benefits:
- All payloads are frozen/immutable after creation
- `WorktreeState` is a shared contract — git operations don't need to know which mode they're in
- Clean separation: "what are we running?" (`PrdWorkflowRun` / `ProjectRun`) vs "where is the worktree?" (`WorktreeState`)

**`format_string()` method** merges all placeholder sets. Unknown placeholders pass through unchanged. Resolves from:
- RunContext direct fields (`{cwd}`, `{repo_root}`)
- PrdWorkflowRun if present (`{prd_id}`, `{prd_title}`, `{prd_slug}`, `{branch}`, `{base_ref}`, `{worktree}`)
- ProjectRun if present (`{operation_name}`, `{target_count}`, `{target_prd}`)
- WorktreeState if present (`{branch}`, `{worktree}`)

**Convenience properties** on RunContext for common access patterns:

```python
@property
def prd(self) -> PRD:
    return self.state.get(PrdWorkflowRun).prd

@property
def workflow(self) -> Workflow:
    # Available in both modes — PrdWorkflowRun and ProjectRun both carry workflow
    if self.state.has(PrdWorkflowRun):
        return self.state.get(PrdWorkflowRun).workflow
    return self.state.get(ProjectRun).workflow
```

These raise `KeyError` if the required payload is absent — fail-fast by design.

**Migration**: `ExecutionContext` becomes a type alias for `RunContext` temporarily, then is removed. Same for `SystemContext`. The 41+ files importing `ExecutionContext` are updated mechanically. Convenience properties mean most `ctx.prd`, `ctx.branch_name` accesses need minimal change.

### Part 3: Git operations in both registries

With unified `RunContext`, the git operations can be registered in both `BUILTINS` (PRD workflows) and `PROJECT_BUILTINS` (project operations, renamed from `SYSTEM_BUILTINS` by PRD-632 or this PRD).

Each operation:
1. Gets `WorktreeState` from `ctx.state` (or creates it, in `ensure_worktree`'s case)
2. Calls the shared primitive from `utils/`
3. Updates state as needed

The resolution of *what branch name to use* differs:
- PRD workflow: `prd/{id}-{slug}` from `PrdWorkflowRun`
- Project operation: `project/{op-name}` or `project/{op-name}-{target_prd}` from `ProjectRun`

This resolution lives in `ensure_worktree`, which reads the appropriate payload and puts a `WorktreeState`. All downstream operations are mode-agnostic.

### Part 4: Operations package reorganization

Organize `operations/` by lifecycle concern:

```
operations/
  __init__.py
  _registry.py
  _shared.py
  git/           — ensure_worktree, commit, push_branch, rebase, fast_forward, cleanup
  pr/            — create_pr, fetch_pr_comments, reply_pr_comments, lint_attribution
  status/        — set_status, rework_guard, resolve_rework_context
  reporting/     — commit_events, commit_transcript, analyze_transcript, summarize_agent_run
  project/       — project_builtins (renamed from system_builtins), gather_prd_context, discuss_prd, commit_prd_changes
```

### Type changes (building on PRD-632 renames)

PRD-632 delivers: `ProjectOperation`, `ProjectContext`, `project.py`, `PROJECT_BUILTINS`, `project_builtins.py`.

PRD-631 then:

| Before (post-632) | After | Notes |
|---|---|---|
| `ProjectOperation` | Removed | Absorbed into `Workflow` |
| `ProjectContext` | Removed | Replaced by `RunContext` |
| `ExecutionContext` | Removed | Replaced by `RunContext` |
| `project.py` | Removed | `ProjectRun` payload moves to `engine/payloads.py`; runner-level config stays in runner |
| `PROJECT_BUILTINS` | Unchanged | Git operations added to it |
| `operation.py` (entry files) | `workflow.py` | Single discovery mechanism |

## Acceptance Criteria

- [ ] AC-1: `ProjectOperation` absorbed into `Workflow` — single definition type, no references to `ProjectOperation` remain
- [ ] AC-2: `ProjectContext` and `ExecutionContext` replaced by unified `RunContext` — no references to either old type remain
- [ ] AC-3: All `operation.py` entry files renamed to `workflow.py` — single `load_workflows()` discovery mechanism
- [ ] AC-4: All existing PRD workflow tests pass (with mechanical import updates)
- [ ] AC-5: All existing project workflow tests pass
- [ ] AC-6: Parameterized primitives in `utils/` with standalone tests
- [ ] AC-7: `prd project run plan --target PRD-X --execute` creates worktree, commits, pushes, opens PR
- [ ] AC-8: Dry-run mode logs intent without side effects for all git operations
- [ ] AC-9: `mypy --strict` clean across all changed modules
- [ ] AC-10: Operations package reorganized by lifecycle concern
- [ ] AC-11: `WorktreeState` is the shared contract between ensure_worktree and downstream git operations in both modes
- [ ] AC-12: Runtime concerns (`creates_pr`, `pr_title`, `requires_clean_main`, `accepts_target`) are not on `Workflow` — they live in PhaseState payloads or runner-level config

## Decomposition

Suggested task ordering (assumes PRD-632 is complete):

1. **Unify Workflow type** — absorb `ProjectOperation` into `Workflow`. Move runtime fields to payloads. Rename `operation.py` → `workflow.py` in project definitions. Update loader to single `load_workflows()`. Update all importers.
2. **Extract git primitives** to `utils/git/primitives.py` and `utils/github/primitives.py`. Refactor existing workflow operations to delegate. All tests pass, zero behavior change.
3. **Unify RunContext** — create `RunContext`, `PrdWorkflowRun`, `ProjectRun`, `WorktreeState`, `PrRequest` payloads. Migrate `ExecutionContext` and `ProjectContext`. Update imports across ~60 files.
4. **Register git operations in PROJECT_BUILTINS** — `ensure_worktree`, `commit`, `push_branch`, `create_pr` with project-mode branch resolution.
5. **Reorganize operations/** — move operations into lifecycle subdirectories (git/, pr/, status/, reporting/, project/).
6. **End-to-end validation** — verify `plan` operation works, add integration test.

## Resolved Questions

- RESOLVED: State threading uses `PhaseState` with frozen payload dataclasses.
- RESOLVED: Operation naming — use same names in both registries (unprefixed). The `plan` operation already references these names.
- RESOLVED: Separate `WorktreeState` payload (Option B) — ensure_worktree puts it, downstream operations get it. Context-agnostic, immutable.
- RESOLVED: "System" → "project" naming delivered by PRD-632. PRD-631 inherits `ProjectOperation`, `ProjectContext`, `PROJECT_BUILTINS`.
- RESOLVED: `Workflow` and `ProjectOperation` unified into single `Workflow` type. `Workflow` stays general — no runtime state fields. Runtime concerns (`pr_title`, `creates_pr`, `requires_clean_main`, `accepts_target`) become PhaseState payloads or runner-level config.
- RESOLVED: All `operation.py` entry files become `workflow.py`. Single loader, single discovery mechanism.

## Impact on PRD-632

PRD-632's out-of-scope note says: *"Renaming `operation.py` → `workflow.py` or unifying `ProjectOperation` and `Workflow` into a single type ... is a separate architectural decision."* PRD-631 now makes that decision. PRD-632 should proceed as planned (keeping `ProjectOperation` and `operation.py`); PRD-631 will unify them immediately after.

## Open Questions

- OPEN: Branch naming for project operations — `project/{op-name}` or another prefix? Must avoid collision with `prd/` branches.

## References

- PRD-632 — prerequisite: reorganizes definitions, renames CLI to `prd project`
- `src/darkfactory/workflow/_core.py` — current `ExecutionContext`
- `src/darkfactory/system.py` — current `SystemContext` / `SystemOperation`
- `src/darkfactory/runner.py` — `RunContext` protocol, construction paths, task dispatch
- `src/darkfactory/operations/ensure_worktree.py` — workflow operation to extract from
- `src/darkfactory/operations/commit.py` — workflow operation to extract from
- `src/darkfactory/operations/push_branch.py` — workflow operation to extract from
- `src/darkfactory/operations/create_pr.py` — workflow operation to extract from
- `src/darkfactory/operations/system_builtins.py` — project operation registry
- `src/darkfactory/engine/phase_state.py` — PhaseState registry

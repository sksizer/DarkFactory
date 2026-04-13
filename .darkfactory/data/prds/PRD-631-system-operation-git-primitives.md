---
id: PRD-631
title: Unified RunContext, unified Workflow type, and project operation PR support
kind: task
status: in-progress
priority: high
effort: l
capability: complex
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/workflow/_core.py
  - src/darkfactory/project.py
  - src/darkfactory/runner.py
  - src/darkfactory/operations/project_builtins.py
  - src/darkfactory/operations/ensure_worktree.py
  - src/darkfactory/operations/commit.py
  - src/darkfactory/operations/push_branch.py
  - src/darkfactory/operations/create_pr.py
  - src/darkfactory/engine/payloads.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-12
updated: '2026-04-12'
tags:
  - architecture
  - refactor
---

# Unified RunContext, unified Workflow type, and project operation PR support

## Summary

Three changes shipped together: (1) unify `Workflow` and `ProjectOperation` into a single `Workflow` type, (2) unify `ExecutionContext` and `ProjectContext` into a single `RunContext`, and (3) register git operations in `PROJECT_BUILTINS` so project workflows can create worktrees and PRs.

## Motivation

Project operations cannot create worktrees or PRs today. The `ProjectOperation` dataclass declares `creates_pr`, `pr_title`, and `pr_body` fields, but no operations implement them. The `plan` operation (`definitions/project/plan/operation.py`) references `ensure_worktree`, `commit`, `push_branch`, `create_pr` — all of which fail at runtime because they only exist in the workflow `BUILTINS` registry.

Two separate definition types (`Workflow` and `ProjectOperation`) and two separate context types (`ExecutionContext` and `ProjectContext`) maintain artificial distinctions. Both are "a named sequence of tasks with metadata" executed by the same runner. The differences are in *how they're invoked* and *what runtime data the runner seeds* — which is exactly what `PhaseState` payloads handle. Unifying the types eliminates duplication and makes git primitives naturally available to both execution modes.

## Requirements

### Functional

1. **Unified `Workflow` type** replaces both `Workflow` and `ProjectOperation`. The definition type is kept general — routing fields (`applies_to`, `priority`) are optional; runtime concerns (`creates_pr`, `pr_title`, etc.) move to PhaseState payloads, not the definition.
2. **Unified `RunContext`** replaces both `ExecutionContext` and `ProjectContext` as the single context type passed to all operations and task runners.
3. **Git operations available in both registries** — `ensure_worktree`, `commit`, `push_branch`, `create_pr` work in both PRD workflow and project workflow modes. The operations already delegate to context-free primitives in `utils/git/`; this PRD rewires them to use `RunContext` and registers them in both registries.
4. **All `operation.py` entry files become `workflow.py`** — single discovery mechanism via `load_workflows()`.
5. Existing PRD workflow runs behave identically.
6. Existing project operations (verify-merges, audit-impacts, discuss) behave identically.
7. Existing `plan` project operation runs end-to-end — `ensure_worktree`, `commit`, `push_branch`, `create_pr` resolve from `PROJECT_BUILTINS` and execute successfully.

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

Fields that were on `ProjectOperation` but are runtime concerns move to PhaseState payloads or become tasks:

| Former `ProjectOperation` field | Where it goes                                                                       |
| ------------------------------- | ----------------------------------------------------------------------------------- |
| `creates_pr`                    | Implicit — if the task list includes `create_pr`, a PR gets created                 |
| `pr_title` / `pr_body`          | `PrRequest` payload in PhaseState, put by the task that initiates PR creation       |
| `requires_clean_main`           | A builtin task — `check_clean_main` — placed at the start of workflows that need it |
| `accepts_target`                | Runner-level — whether `--target` is required, part of invocation                   |

All `operation.py` entry files are renamed to `workflow.py`. The loader uses a single `load_workflows()` function. The `definitions/project/` directory keeps its structure, but each subdirectory now contains `workflow.py` exporting a `Workflow` instance instead of `operation.py` exporting a `ProjectOperation`.

### Part 1: Unified RunContext

Replace `ExecutionContext` and `ProjectContext` with a single `RunContext` dataclass.

**RunContext** holds only immutable harness concerns:

| Field          | Type                  | Notes           |
| -------------- | --------------------- | --------------- |
| `dry_run`      | `bool`                | Default True    |
| `logger`       | `Logger`              | Factory-created |
| `state`        | `PhaseState`          | Typed inter-task registry |
| `event_writer` | `EventWriter \| None` | Optional        |
| `report`       | `list[str]`           | Accumulator for project operation output |

All execution state lives in frozen PhaseState payloads, replaced (not mutated) as the run progresses:

| Payload dataclass | Contents | Put by |
|---|---|---|
| `CodeEnv` | `repo_root: Path`, `cwd: Path` | Runner at construction (cwd=repo_root); replaced by `ensure_worktree` (cwd=worktree_path) |
| `PrdWorkflowRun` | `prd: PRD`, `workflow: Workflow`, `run_summary: str \| None` | `run_prd_workflow()` at construction |
| `ProjectRun` | `workflow: Workflow`, `prds: tuple[str, ...]`, `targets: tuple[str, ...]`, `target_prd: str \| None` | `run_project_workflow()` at construction |
| `WorktreeState` | `branch: str`, `base_ref: str`, `worktree_path: Path \| None` | `name_worktree` task (branch/base_ref only); replaced by `ensure_worktree` (adds worktree_path) |
| `PrRequest` | `title: str`, `body: str` | `create_pr` kwargs or PRD-mode fallback |

`RunContext` also has a `report: list[str]` accumulator field for project operations that build up output during execution. This is the one mutable field on `RunContext`.

**`CodeEnv`** is the execution environment — where code runs. Tasks that execute commands read `ctx.state.get(CodeEnv).cwd`. They don't need to know whether a worktree exists. `ensure_worktree` replaces `CodeEnv` with an updated `cwd` and separately puts `WorktreeState` for git-aware operations.

**`WorktreeState`** is the git worktree contract. Operations like `commit`, `push_branch`, `create_pr` read branch/base_ref from here. It's context-agnostic — the same type regardless of whether a PRD workflow or project operation created the worktree.

**`format_string()` method** merges placeholders from all payloads present in state. No payload shares a placeholder name with another — each piece of data lives in exactly one payload type. Unknown placeholders pass through unchanged. Resolves from:
- CodeEnv (`{cwd}`, `{repo_root}`)
- PrdWorkflowRun if present (`{prd_id}`, `{prd_title}`, `{prd_slug}`)
- ProjectRun if present (`{workflow_name}`, `{target_count}`, `{target_prd}`)
- WorktreeState if present (`{branch}`, `{base_ref}`, `{worktree}`)

**Migration**: `ExecutionContext` and `ProjectContext` are removed and replaced by `RunContext` in a single commit (no alias — see DI-5). Operations read environment data from `state.get()` calls instead of direct context fields.

### Part 2: Git operations in both registries

Two registries are kept — `BUILTINS` for PRD workflows, `PROJECT_BUILTINS` for project workflows — as an intentional scoping mechanism. Project-only operations (e.g. `set_status_bulk`) should not be callable from PRD workflows, and vice versa. Git operations are registered in both explicitly.

Each operation:
1. Gets `WorktreeState` from `ctx.state` (or creates it, in `ensure_worktree`'s case)
2. Calls the shared primitive from `utils/`
3. Updates state as needed

Worktree naming is handled by a `name_worktree` builtin task placed before `ensure_worktree` in workflow definitions:

```python
# PRD workflow
tasks=[
    BuiltIn("name_worktree", kwargs={"branch": "prd/{prd_id}-{prd_slug}"}),
    BuiltIn("ensure_worktree"),
    ...
]

# Project workflow
tasks=[
    BuiltIn("name_worktree", kwargs={"branch": "project/{workflow_name}/{target_prd}"}),
    BuiltIn("ensure_worktree"),
    ...
]
```

`name_worktree` puts a `WorktreeState` with the desired branch name (resolved via `format_string()`). `ensure_worktree` reads it if present and does the actual git work, or generates a default name if absent. This keeps `ensure_worktree` mode-agnostic — the naming decision is explicit in the workflow definition. All downstream operations (`commit`, `push_branch`, `create_pr`) are mode-agnostic via `WorktreeState`.

### Type changes

| Before | After | Notes |
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
- [ ] AC-6: Existing `plan` project operation runs end-to-end — `ensure_worktree`, `commit`, `push_branch`, `create_pr` resolve from `PROJECT_BUILTINS` and execute successfully
- [ ] AC-7: Dry-run mode logs intent without side effects for all git operations
- [ ] AC-8: `mypy --strict` clean across all changed modules
- [ ] AC-9: `RunContext` has no mutable fields — `CodeEnv` (frozen PhaseState payload) holds `repo_root` and `cwd`, replaced by `ensure_worktree`
- [ ] AC-10: `WorktreeState` is the shared contract between ensure_worktree and downstream git operations in both modes
- [ ] AC-11: Runtime concerns (`creates_pr`, `pr_title`, `accepts_target`) are not on `Workflow` — they live in PhaseState payloads or runner-level config
- [ ] AC-12: `requires_clean_main` is a builtin task, not a definition field or runner pre-check

## Decomposition

Suggested task ordering:

1. **Unify Workflow type** — absorb `ProjectOperation` into `Workflow`. Move runtime fields to payloads. Convert `requires_clean_main` to a `check_clean_main` builtin task. Rename `operation.py` → `workflow.py` in project definitions. Update loader to single `load_workflows()`. Update all importers.
2. **Unify RunContext** — create `RunContext` (no mutable fields), `CodeEnv`, `PrdWorkflowRun`, `ProjectRun`, `WorktreeState`, `PrRequest` payloads. Migrate `ExecutionContext` and `ProjectContext`. Operations read `CodeEnv` for cwd/repo_root via `state.get()`. Operations already delegate to `utils/git/` primitives, so the rewiring is mechanical.
3. **Register git operations in PROJECT_BUILTINS** — `ensure_worktree`, `commit`, `push_branch`, `create_pr` with project-mode branch resolution.
4. **End-to-end validation** — verify `plan` operation works, add integration test.

## Resolved Questions

- RESOLVED: State threading uses `PhaseState` with frozen payload dataclasses.
- RESOLVED: Operation naming — use same names in both registries (unprefixed). The `plan` operation already references these names.
- RESOLVED: Separate `WorktreeState` payload — ensure_worktree puts it, downstream operations get it. Context-agnostic, immutable.
- RESOLVED: `Workflow` and `ProjectOperation` unified into single `Workflow` type. `Workflow` stays general — no runtime state fields.
- RESOLVED: All `operation.py` entry files become `workflow.py`. Single loader, single discovery mechanism.
- RESOLVED: `cwd` and `repo_root` are not mutable fields on `RunContext`. They live in a frozen `CodeEnv` PhaseState payload. The runner seeds `CodeEnv(repo_root=..., cwd=repo_root)` at construction. `ensure_worktree` replaces it with `CodeEnv(repo_root=..., cwd=worktree_path)` and separately puts `WorktreeState`. Shell tasks read `CodeEnv.cwd`; git operations read `WorktreeState`. Lock key uses the branch name (deterministic from workflow name + optional target), not a PRD ID.
- RESOLVED: Keep two registries (`BUILTINS` and `PROJECT_BUILTINS`) as an intentional scoping mechanism. Git operations are registered in both explicitly.
- RESOLVED: `requires_clean_main` becomes a builtin task (`check_clean_main`) placed at the start of workflows that need it, rather than a definition field or runner pre-check.
- RESOLVED: Branch naming for project operations — `project/{op-name}` for non-targeted operations, `project/{op-name}/{prd-id}` for targeted ones. The `project/` prefix avoids collision with `prd/` branches.
- RESOLVED: `workflow_dir` is the surviving field name after unification (replacing `operation_dir`). The loader sets it for both `definitions/prd/*/workflow.py` and `definitions/project/*/workflow.py`.
- RESOLVED: `report` moves out of `ProjectRun` to become an accumulator on `RunContext`. `ProjectRun` stays frozen with `prds` and `targets` as tuples. More generally, result accumulation from task handlers may warrant a first-class pattern on `RunContext`.
- RESOLVED: `PrRequest` population — `create_pr` accepts optional `title`/`body` kwargs. If provided, formats them via `format_string()`. If absent, falls back to generating from `PrdWorkflowRun`. No new builtins needed.
- RESOLVED: Worktree naming — a `name_worktree` builtin task puts a `WorktreeState` with the desired branch name (via format string or hardcoded). `ensure_worktree` reads it if present, or generates a random/default name if absent. This makes `ensure_worktree` mode-agnostic — no mode-branching needed.
- RESOLVED: Clean rename — `ExecutionContext` and `ProjectContext` are removed in a single commit. No type alias. `mypy --strict` catches all breakage.
- RESOLVED: No placeholder collision — each piece of data lives in exactly one payload type. `PrdWorkflowRun` does not carry `branch_name` or `base_ref`; those live exclusively on `WorktreeState`. `format_string()` is a flat merge with no precedence rules needed.

## References

- `src/darkfactory/workflow/_core.py` — `ExecutionContext`, `Workflow`
- `src/darkfactory/project.py` — `ProjectContext`, `ProjectOperation`
- `src/darkfactory/runner.py` — `RunContext` protocol, construction paths, task dispatch
- `src/darkfactory/operations/project_builtins.py` — project operation registry (`PROJECT_BUILTINS`)
- `src/darkfactory/operations/_registry.py` — workflow operation registry (`BUILTINS`)
- `src/darkfactory/engine/phase_state.py` — PhaseState registry

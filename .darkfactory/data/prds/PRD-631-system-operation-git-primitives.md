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

## Discussion Items (Review Required)

### DI-1: Operations package reorganization is orthogonal — extract to separate PRD

Part 4 (operations package reorganization) and AC-10 add significant diff churn without contributing to the core goal of type unification or enabling project-mode PRs. The reorganization has no dependency on the type changes and no other task depends on it.

**Current structure:**

```
operations/
  __init__.py
  _registry.py
  _shared.py
  ensure_worktree.py
  commit.py
  push_branch.py
  create_pr.py
  set_status.py
  project_builtins.py
  gather_prd_context.py
  discuss_prd.py
  ...
```

**Proposed structure (Part 4):**

```
operations/
  git/           — ensure_worktree, commit, push_branch, rebase, fast_forward, cleanup
  pr/            — create_pr, fetch_pr_comments, reply_pr_comments, lint_attribution
  status/        — set_status, rework_guard, resolve_rework_context
  reporting/     — commit_events, commit_transcript, analyze_transcript, summarize_agent_run
  project/       — project_builtins, gather_prd_context, discuss_prd, commit_prd_changes
```

This is a pure code-organization change that can land before or after PRD-631. Bundling it increases review burden and blast radius without unblocking any functionality.

**Recommendation:** Remove Part 4 and AC-10 from this PRD. File as a separate PRD.

---

### DI-2: Two registries or one? — the split rationale disappears after unification

The PRD says git operations get "registered in both `BUILTINS` and `PROJECT_BUILTINS`." But today the split exists because the registries enforce different function signatures:

```python
# operations/_registry.py — workflow builtins take ExecutionContext
BUILTINS: dict[str, BuiltInFunc] = {}

@builtin("ensure_worktree")
def ensure_worktree(ctx: ExecutionContext) -> None: ...

# operations/project_builtins.py — project builtins take ProjectContext
SYSTEM_BUILTINS: dict[str, Callable[..., None]] = {}

@_register("set_status_bulk")
def set_status_bulk(ctx: ProjectContext, *, status: str) -> None: ...
```

After unification, both take `RunContext`. The type-based reason for the split disappears. The runner already dispatches by passing the appropriate registry:

```python
# runner.py:711 — workflow mode
result = run_tasks(
    tasks=workflow.tasks,
    ctx=ctx,
    builtins=BUILTINS,                          # <-- workflow registry
    ...
)

# runner.py:809 — project mode
result = run_tasks(
    tasks=operation.tasks,
    ctx=ctx,
    builtins=SYSTEM_BUILTINS,                   # <-- project registry
    ...
)
```

**Questions to resolve:**

1. **Unify into a single `BUILTINS`?** — simplest approach, but means project-only operations (e.g. `set_status_bulk`, `system_check_merged`) become visible in PRD workflow mode. Workflows don't reference them, but they're discoverable.

2. **Keep two registries as an allow-list?** — if the split is intentional scoping (project operations shouldn't be callable from PRD workflows), keep two registries but document this as the reason. The git operations would be registered in both explicitly.

3. **Single registry + runner-level allow-list?** — one registry, but the runner filters available operations by mode at dispatch time. More flexible, single source of truth for implementations.

**This needs a decision before implementation.** The PRD currently says "registered in both registries" without addressing whether two registries should continue to exist.

---

### DI-3: `cwd` mutation vs immutable `WorktreeState` — clarify the contract

The PRD introduces `WorktreeState` as an immutable PhaseState payload, but `RunContext.cwd` must still be mutated. Today `ensure_worktree` does both:

```python
# operations/ensure_worktree.py:154-155 — mutates ctx directly
ctx.worktree_path = worktree_path
ctx.cwd = worktree_path
```

Shell tasks depend on `ctx.cwd` for their working directory:

```python
# runner.py:426 — shell tasks resolve cwd from ctx
cmd = ctx.format_string(task.cmd)
...
first_result = run_shell(cmd, ctx.cwd, task.env)
```

After the change, `ensure_worktree` would need to both put an immutable `WorktreeState` AND mutate `ctx.cwd`:

```python
# Post-PRD-631 ensure_worktree (inferred, not specified in PRD)
def ensure_worktree(ctx: RunContext) -> None:
    # ... create worktree ...
    
    # Put immutable payload — the inter-operation contract
    ctx.state.put(WorktreeState(
        branch=branch,
        base_ref=base_ref,
        worktree_path=worktree_path,
    ))
    
    # Also mutate ctx.cwd — the runner-level side effect
    ctx.cwd = worktree_path    # <-- still needed for shell tasks
```

**The PRD should be explicit about this dual responsibility.** Currently it says `WorktreeState` replaces the old state threading but doesn't mention that `ctx.cwd` mutation is still required. Implementers may think `WorktreeState` replaces the `ctx.cwd` assignment.

Additionally: the current `ExecutionContext` has a `worktree_path` field. The PRD's `RunContext` shared fields table includes `cwd` but not `worktree_path`. Should `RunContext` keep `worktree_path` as a field, or should all downstream consumers read `ctx.state.get(WorktreeState).worktree_path` instead? The lock path logic also reads `ctx.prd.id`:

```python
# operations/ensure_worktree.py:97 — lock keyed on PRD id
lock_path = ctx.repo_root / ".worktrees" / f"{ctx.prd.id}.lock"
```

In project mode there's no single PRD. What is the lock key?

---

### DI-4: `workflow_dir` vs `operation_dir` — confirm naming survives unification

PRD-632 adds `operation_dir` to `ProjectOperation`. The existing `Workflow` has `workflow_dir`. Both serve the same purpose (resolve relative paths for prompts/tasks), but the runner uses them differently:

```python
# runner.py:755 — project mode reads operation_dir
def _project_compose_prompt(task: AgentTask, ctx: Any, ...) -> str:
    op_dir = ctx.operation.operation_dir
    if op_dir is None:
        raise ValueError(...)
    raw = load_prompt_files(op_dir, task.prompts)
    ...

# workflow/_core.py — workflow mode uses workflow_dir via compose_prompt
def compose_prompt(workflow: Workflow, prompts: list[str], ctx: ...) -> str:
    # Uses workflow.workflow_dir to resolve prompt paths
    ...
```

After absorbing `ProjectOperation` into `Workflow`, the unified type has only `workflow_dir`. The PRD's proposed `Workflow` dataclass confirms this:

```python
@dataclass
class Workflow:
    name: str
    description: str
    tasks: list[Task]
    workflow_dir: Path | None = None   # <-- this is the surviving name
    ...
```

But `_project_compose_prompt` reads `ctx.operation.operation_dir`. After unification, the prompt composer needs to read from the `Workflow` stored in the `ProjectRun` payload:

```python
# What _project_compose_prompt needs to become:
def _project_compose_prompt(task: AgentTask, ctx: RunContext, ...) -> str:
    workflow = ctx.state.get(ProjectRun).workflow
    op_dir = workflow.workflow_dir                # <-- was operation_dir
    if op_dir is None:
        raise ValueError(...)
    raw = load_prompt_files(op_dir, task.prompts)
    ...
```

**Confirm:** `workflow_dir` is the surviving field name and serves both purposes. The loader sets it when discovering both `definitions/prd/*/workflow.py` and `definitions/project/*/workflow.py`.

---

### DI-5: `PrRequest` population — who puts it and when?

The PRD moves `pr_title` and `pr_body` from `ProjectOperation` to a `PrRequest` PhaseState payload. Today these are static templates on the definition:

```python
# definitions/project/plan/operation.py:18-29
operation = ProjectOperation(
    name="plan",
    ...
    creates_pr=True,
    pr_title="chore(prd): decompose {target_prd}",      # <-- static template
    pr_body="Auto-generated by ...\n\n{target_prd}.",    # <-- static template
    tasks=[
        BuiltIn("ensure_worktree"),
        AgentTask(name="decompose", ...),
        ShellTask(name="validate", ...),
        BuiltIn("commit", kwargs={"message": "..."}),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),                             # <-- consumes title/body
    ],
)
```

After the change, `Workflow` has no `pr_title`/`pr_body` fields. The PRD says "task that initiates PR creation" puts `PrRequest`, but doesn't specify the mechanism. Three options:

**Option A: `create_pr` takes kwargs** — title/body passed as task kwargs, formatted at dispatch time:

```python
# definitions/project/plan/workflow.py — Option A
workflow = Workflow(
    name="plan",
    tasks=[
        ...
        BuiltIn("create_pr", kwargs={
            "title": "chore(prd): decompose {target_prd}",
            "body": "Auto-generated by ...",
        }),
    ],
)
```

The `create_pr` operation would build a `PrRequest` from kwargs when present, or fall back to the current PRD-based title generation for workflow mode. Simple, no new tasks. But now `create_pr` has two code paths.

**Option B: Dedicated `prepare_pr` builtin** — a new task that reads metadata and puts `PrRequest`:

```python
# definitions/project/plan/workflow.py — Option B
workflow = Workflow(
    name="plan",
    tasks=[
        ...
        BuiltIn("prepare_pr", kwargs={
            "title": "chore(prd): decompose {target_prd}",
            "body": "Auto-generated by ...",
        }),
        BuiltIn("create_pr"),  # reads PrRequest from state
    ],
)
```

Clean separation, but adds a task that exists only to move data into PhaseState.

**Option C: Runner seeds `PrRequest`** — the runner constructs `PrRequest` at context creation time from some source:

```python
# runner.py — Option C
def run_project_workflow(...):
    ctx.state.put(PrRequest(
        title="chore(prd): decompose {target_prd}",
        body="Auto-generated by ...",
    ))
    result = run_tasks(...)
```

But this requires the runner to know operation-specific metadata, coupling it back to the definition. Where does the runner read the title template from if not the `Workflow`?

**For PRD-mode workflows**, `create_pr` currently constructs the title and body from `ctx.prd`:

```python
# operations/create_pr.py:63-64 — current PRD-mode title generation
title = f"{ctx.prd.id}: {ctx.prd.title}"
body = _pr_body(ctx)
```

Does this also become a `PrRequest` payload put by the runner? Or does `create_pr` keep this PRD-aware logic and only use `PrRequest` when present?

**This needs a decision.** The mechanism determines how workflow definitions express PR metadata after `pr_title`/`pr_body` are removed from the type.

---

### DI-6: Convenience properties that crash by mode — document the access contract

The PRD proposes convenience properties that raise on mode mismatch:

```python
@property
def prd(self) -> PRD:
    return self.state.get(PrdWorkflowRun).prd    # KeyError in project mode

@property
def workflow(self) -> Workflow:
    if self.state.has(PrdWorkflowRun):
        return self.state.get(PrdWorkflowRun).workflow
    return self.state.get(ProjectRun).workflow    # KeyError if neither
```

This is good fail-fast behavior. But consider the `plan` operation, which runs in project mode and targets a specific PRD. Its tasks reference both project-mode data AND PRD-specific data:

```python
# definitions/project/plan/operation.py — runs in project mode
operation = ProjectOperation(
    ...
    accepts_target=True,
    tasks=[
        BuiltIn("ensure_worktree"),          # needs branch name — from where?
        BuiltIn("commit", kwargs={
            "message": "chore(prd): {target_prd} decomposition"
        }),                                   # needs cwd — from WorktreeState
        BuiltIn("create_pr"),                # needs title/body — from where?
    ],
)
```

When `ensure_worktree` runs in project mode, it can't do `ctx.prd` to compute the worktree path. The PRD says it reads from `ProjectRun`:

```python
# Inferred ensure_worktree in project mode
def ensure_worktree(ctx: RunContext) -> None:
    if ctx.state.has(PrdWorkflowRun):
        prd_run = ctx.state.get(PrdWorkflowRun)
        branch = prd_run.branch_name
        worktree_name = f"{prd_run.prd.id}-{prd_run.prd.slug}"
    elif ctx.state.has(ProjectRun):
        proj_run = ctx.state.get(ProjectRun)
        # What's the worktree name? What's the branch?
        branch = f"project/{proj_run.workflow.name}"
        if proj_run.target_prd:
            branch = f"project/{proj_run.workflow.name}/{proj_run.target_prd}"
        worktree_name = branch.replace("/", "-")
    else:
        raise KeyError("no run payload — ensure_worktree requires PrdWorkflowRun or ProjectRun")
    
    worktree_path = ctx.repo_root / ".worktrees" / worktree_name
    # ... rest of logic ...
```

This mode-branching inside `ensure_worktree` is the kind of thing the PRD wants to avoid — operations shouldn't need to know which mode they're in. But the branch name and worktree path must come from somewhere mode-specific.

**Alternative:** Have the runner (or a `prepare_worktree_config` builtin) put a `WorktreeRequest` payload *before* `ensure_worktree` runs, containing branch name and worktree path. Then `ensure_worktree` is truly mode-agnostic:

```python
@dataclass(frozen=True)
class WorktreeRequest:
    branch: str
    base_ref: str
    worktree_name: str

def ensure_worktree(ctx: RunContext) -> None:
    req = ctx.state.get(WorktreeRequest)
    worktree_path = ctx.repo_root / ".worktrees" / req.worktree_name
    # ... no mode-branching needed ...
```

**Is this additional payload worth the indirection, or is mode-branching in `ensure_worktree` acceptable?**

---

### DI-7: `format_string()` placeholder collision between payloads

The PRD says `format_string()` resolves from multiple payload sources:

```
- PrdWorkflowRun if present: {branch}, {base_ref}, {worktree}
- WorktreeState if present:  {branch}, {base_ref}, {worktree}
```

Both `PrdWorkflowRun` and `WorktreeState` define `{branch}`. In PRD workflow mode, `PrdWorkflowRun` is put at context construction (before `ensure_worktree`) and `WorktreeState` is put by `ensure_worktree` later. If both are present, which wins?

```python
# Scenario: PRD workflow mode, after ensure_worktree has run
ctx.state.get(PrdWorkflowRun).branch_name  # "prd/PRD-070-add-feature"
ctx.state.get(WorktreeState).branch        # "prd/PRD-070-add-feature" (same)

# These HAPPEN to be the same today, but the PRD doesn't guarantee it.
# In project mode, WorktreeState.branch comes from a different source.
```

The PRD says "unknown placeholders pass through unchanged" but doesn't specify precedence for colliding placeholders.

**Recommendation:** Define explicit precedence (e.g. `WorktreeState` > `PrdWorkflowRun` for git-related placeholders) or eliminate the overlap by giving the fields different names (e.g. `{wt_branch}` vs `{run_branch}`).

---

### DI-8: Migration strategy — clean rename vs type alias

The PRD says:

> `ExecutionContext` becomes a type alias for `RunContext` temporarily, then is removed.

A type alias creates a state where both names compile, which invites new code using the old name during the transition. With `mypy --strict`, a mechanical rename across all 23+ files that import `ExecutionContext` will catch any misses at compile time.

```python
# Option A: type alias (PRD's proposal)
# workflow/_core.py
RunContext = ...
ExecutionContext = RunContext  # temporary alias

# This compiles, which is the problem — nothing forces migration:
from darkfactory.workflow import ExecutionContext  # still works

# Option B: clean cut (recommendation)
# workflow/_core.py
RunContext = ...
# ExecutionContext is simply gone

# This fails at import time — forces immediate update:
from darkfactory.workflow import ExecutionContext  # ImportError
```

**Recommendation:** Do a clean rename in a single commit as part of the decomposition task. No alias. `mypy --strict` catches all breakage. This matches the project's "hard failures over silent degradation" principle.

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

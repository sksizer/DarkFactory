---
id: PRD-630
title: Unify execution engine and introduce typed inter-task state
kind: epic
status: review
priority: high
effort: l
capability: complex
parent: null
depends_on: []
blocks: []
impacts:
  - src/darkfactory/workflow.py
  - src/darkfactory/system.py
  - src/darkfactory/runner.py
  - src/darkfactory/system_runner.py
  - src/darkfactory/templates.py
  - src/darkfactory/templates_builtin.py
  - src/darkfactory/loader.py
  - src/darkfactory/invoke.py
  - src/darkfactory/builtins/__init__.py
  - src/darkfactory/builtins/_registry.py
  - src/darkfactory/builtins/system_builtins.py
  - src/darkfactory/builtins/gather_prd_context.py
  - src/darkfactory/builtins/discuss_prd.py
  - src/darkfactory/builtins/resolve_rework_context.py
  - src/darkfactory/commands/discuss/operation.py
  - src/darkfactory/cli/run.py
  - src/darkfactory/cli/discuss.py
  - src/darkfactory/cli/system.py
workflow: null
assignee: null
reviewers: []
target_version: null
created: '2026-04-11'
updated: '2026-04-12'
tags:
  - refactor
  - architecture
  - runner
  - workflow
---

# Unify execution engine and introduce typed inter-task state

## Summary

Eliminate the duplicated workflow/system-operation execution paths by
extracting a single parameterized dispatch engine, replace the untyped
`_shared_state` bag and bolted-on context fields with a type-keyed
`PhaseState` registry for inter-task data, and extend `WorkflowTemplate`
to enforce data-flow contracts between template phases.

## Motivation

The harness has two parallel execution systems — `runner.py` (per-PRD
workflows) and `system_runner.py` (repo-wide system operations) — that share
the same `Task` hierarchy but duplicate the dispatch loop, builtin lookup,
shell runner, retry logic, prompt composition, and model selection. Every
new feature (event logging, styler passthrough, timeout config) gets
implemented on the workflow runner and either duplicated on the system runner
or silently omitted.

`system_runner.py` already imports `TaskStep`, `RunResult`, `_task_name`,
`_task_kind` from `runner.py` — acknowledging the duplication. The actual
differences between the two engines reduce to: which builtin registry to
consult, how to compose the agent prompt, and how to pick the model. These
are parameters, not reasons for two separate 350+ line modules.

Separately, inter-task data flows through three inconsistent mechanisms:

1. `SystemContext._shared_state: dict[str, Any]` — an untyped bag where
   `gather_prd_context` writes `"prd_context"` as a string key and
   `discuss_prd` reads it. Typos are silent. Types are unknown.
2. Bolted-on fields on `ExecutionContext` — `pr_number`, `review_threads`,
   `comment_filters`, `reply_to_comments` were added for rework and are
   `None` for every other workflow. The context becomes a God object.
3. `setattr(ctx, "_last_agent_result", result)` — a side-channel hack in
   `_run_agent` because the function signature doesn't accommodate the
   return value.

All three share the same flaw: the contract between producer and consumer
is implicit. You must read both builtins' implementations to know what
keys/fields they share.

Finally, the `discuss` command has a fundamentally different execution model
(interactive `spawn_claude()`) but hides it inside a `BuiltIn` task that
looks identical to deterministic builtins. The task type system doesn't
capture this distinction.

## Design

### PhaseState: type-keyed inter-task data

Each inter-task data bundle is a frozen dataclass. Its **type** serves as
its unique key into a `PhaseState` registry. `mypy` infers that
`state.get(PrdContext)` returns `PrdContext`, not `Any`.

```python
# phase_state.py
class PhaseState:
    _store: dict[type, Any]

    def put(self, value: object) -> None:
        self._store[type(value)] = value

    @overload
    def get(self, key: type[T]) -> T: ...
    @overload
    def get(self, key: type[T], default: T) -> T: ...

    def has(self, key: type) -> bool: ...
```

Data bundles are declared near their producing builtins:

```python
# Near gather_prd_context.py
@dataclass(frozen=True)
class PrdContext:
    summary: str
    body: str
    parent_ref: str | None = None
    dependency_refs: tuple[str, ...] = ()

# Near resolve_rework_context.py
@dataclass(frozen=True)
class ReworkContext:
    pr_number: int
    review_threads: list[ReviewThread]
    reply_to_comments: bool = False
    comment_filters: CommentFilters | None = None
```

Both `ExecutionContext` and `SystemContext` gain a `state: PhaseState`
field. The rework-specific fields (`pr_number`, `review_threads`,
`comment_filters`) move off `ExecutionContext` into `ReworkContext`. The
`_shared_state` dict is removed from `SystemContext`. The `setattr`
side-channel for `_last_agent_result` is replaced by an `AgentResult`
bundle in `PhaseState`.

The unified engine unconditionally calls `state.put(AgentResult(...))`
after every agent invocation. Builtins that currently read
`ctx.agent_output`, `ctx.agent_success`, or `ctx.last_invoke_result`
migrate to reading from `PhaseState` instead. Fields like `invoke_count`
become derivable from the PhaseState contents (or a simple counter on
the engine) rather than context fields. This eliminates the post-agent
mutation asymmetry between the workflow and system operation paths —
both paths produce the same `AgentResult` bundle, and consumers pull
from `PhaseState` if they need it.

### Unified dispatch engine

Extract the core dispatch loop into a function parameterized on what varies:

```python
def run_tasks(
    tasks: list[Task],
    ctx: C,
    builtins: dict[str, Callable],
    compose_prompt: Callable[[AgentTask, C], str],
    pick_model: Callable[[AgentTask, C, str | None], str],
    model_override: str | None = None,
    ...
) -> RunResult:
```

The `runner.py` and `system_runner.py` dispatch loops collapse into callers
that supply their own builtin registry, prompt composer, and model picker.
`system_runner.py` becomes a thin module (or disappears entirely) that
provides the system-specific callables.

The unified engine handles: task dispatch, event logging, styler
passthrough, timeout resolution, dry-run, retry-on-failure, and worktree
lock lifecycle. Features implemented once apply to both execution paths.
System operations gain event logging, styler passthrough, and timeout
resolution — these were previously workflow-only. `system_runner.py` is
deleted entirely (no backward-compat shim needed — alpha, single user).

### Template data-flow contracts

`WorkflowTemplate` gains two optional fields:

```python
@dataclass(frozen=True)
class WorkflowTemplate:
    # ... existing fields ...
    provides: frozenset[type] = frozenset()  # open phase guarantees these
    expects: frozenset[type] = frozenset()   # close phase requires these
```

`provides` declares what `PhaseState` bundles the open phase will produce.
`expects` declares what the close phase needs from the middle. The runner
asserts after the open phase that `provides` are present, and before the
close phase that `expects` are present, with clear error messages naming
the missing bundle type.

This makes the inter-phase contract visible and enforceable — template
authors declare data-flow invariants alongside the existing task-count
invariants from PRD-227.

### InteractiveTask type

A new `InteractiveTask` joins the `Task` hierarchy alongside `AgentTask`:

```python
@dataclass
class InteractiveTask(Task):
    name: str
    prompt_file: str
    tools: list[str] = field(default_factory=list)
    model: str | None = None
    effort_level: EffortLevel | None = None
```

The unified engine dispatches `InteractiveTask` to `spawn_claude()`
(takes over the terminal) instead of `invoke_claude()` (headless, sentinel
parsing). The `discuss_prd` system builtin is replaced by an
`InteractiveTask` in the discuss operation's task list:

```python
tasks=[
    BuiltIn("gather_prd_context"),
    InteractiveTask(name="discuss", prompt_file="prompts/discuss.md",
                    effort_level="max"),
    InteractiveTask(name="critique", prompt_file="prompts/critique.md",
                    effort_level="max"),
    BuiltIn("commit_prd_changes"),
]
```

This makes the operation definition honest about what it does and opens the
door for other interactive-mode recipes without smuggling them through
builtins.

## Requirements

### Functional

1. **PhaseState module** — `src/darkfactory/phase_state.py` with
   `PhaseState` class, `put`/`get`/`has` methods, and `@overload`
   signatures that give mypy full type inference on `get()`.

2. **Data bundles** — `PrdContext`, `ReworkContext`, `AgentResult` frozen
   dataclasses declared near their producing builtins. Each replaces a
   specific untyped mechanism.

3. **Context cleanup** — `ExecutionContext` and `SystemContext` gain
   `state: PhaseState`. Remove: `_shared_state` from `SystemContext`;
   `pr_number`, `review_threads`, `comment_filters` from
   `ExecutionContext`; `setattr` side-channel for `_last_agent_result`.

4. **Unified engine** — single `run_tasks()` dispatch function.
   `runner.run_workflow()` and `system_runner.run_system_operation()` become
   thin callers that provide their builtin registry, prompt composer, and
   model picker. All existing runner features (event logging, styler,
   timeout, dry-run, retry) work for both paths.

5. **InteractiveTask** — new task type dispatched to `spawn_claude()`.
   Discuss operation uses `InteractiveTask` instead of a `BuiltIn` that
   internally calls `spawn_claude()`.

6. **Template data-flow contracts** — `WorkflowTemplate` gains `provides`
   and `expects` fields. Runner asserts after open and before close phases.
   `PRD_IMPLEMENTATION_TEMPLATE` declares its contracts.

7. **Post-agent results via PhaseState** — the unified engine
   unconditionally calls `state.put(AgentResult(...))` after every agent
   invocation. `ctx.agent_output`, `ctx.agent_success`,
   `ctx.last_invoke_result`, `ctx.model`, and `ctx.invoke_count` are
   removed from `ExecutionContext`. Builtins that consumed these fields
   migrate to reading `AgentResult` from `PhaseState`.

8. **System operations gain event logging, styler, and timeout** — the
   unified engine threads `EventWriter`, `Styler`, and timeout config
   through to system operation runs. `cli/system.py` passes `styler` to
   the engine. System agent invocations produce colorized streaming output
   and emit `task_start`/`task_finish` events.

### Non-functional

9. All existing tests pass without modification to assertions (test setup
   may need updating for new context shape).
10. mypy strict passes across all modified files.
11. No new runtime dependencies.

## Relationships to existing PRDs

- **PRD-557** (modularize runner, draft) — this PRD addresses the runner's
  structural problems at a higher level. If PRD-630 lands first, PRD-557's
  scope shrinks significantly or becomes unnecessary, since the unified
  engine will be a smaller, more focused module.
- **PRD-600.1.3** (remove setattr side channel, draft) — subsumed by the
  `AgentResult` PhaseState bundle.
- **PRD-600.3.1** (extract `_run_shell_once` to shared utility, draft) —
  subsumed by the unified engine (one `_run_shell_once`, not two).
- **PRD-621** (refactor utils, ready) — addresses the shell runner
  duplication from the utils side. PRD-630 eliminates the duplication at
  the source (one engine, not two). The two PRDs are compatible — PRD-621
  can land independently.
- **PRD-227** (workflow templates, done) — PRD-630 extends the template
  system with data-flow contracts.
- **PRD-223** (system operations, done) — PRD-630 preserves the
  SystemOperation concept but unifies its execution path with workflows.

## Acceptance criteria

- [ ] AC-1: `PhaseState` exists with `put`/`get`/`has` and mypy infers
  concrete return types from `get()`.
- [ ] AC-2: `_shared_state` dict removed from `SystemContext`; rework
  fields removed from `ExecutionContext`. All inter-task data flows through
  `PhaseState`.
- [ ] AC-3: A single dispatch function handles both workflow and system
  operation execution. `system_runner.py` either becomes a thin shim or is
  removed.
- [ ] AC-4: Event logging, styler, and timeout resolution work for system
  operation runs (they currently only work for workflow runs).
- [ ] AC-5: `InteractiveTask` exists and the discuss operation uses it
  instead of a builtin that calls `spawn_claude()`.
- [ ] AC-6: `WorkflowTemplate` supports `provides`/`expects` and the
  runner asserts them at phase boundaries.
- [ ] AC-7: `AgentResult` bundle stored in `PhaseState` after every agent
  invocation. `ctx.agent_output`, `ctx.agent_success`,
  `ctx.last_invoke_result`, `ctx.model`, `ctx.invoke_count` removed from
  `ExecutionContext`. No `setattr` side-channel.
- [ ] AC-8: `system_runner.py` deleted. All callers updated.
- [ ] AC-9: `just test && just lint && just typecheck && just format-check`
  clean.

## Resolved questions

- **Context types**: keep `ExecutionContext` and `SystemContext` separate.
  Both carry `PhaseState`. Revisit after unification reveals whether the
  remaining differences justify two types.
- **Engine shape**: function with callables, not a class. Matches existing
  codebase style.
- **`frozenset[type]` for template contracts**: accepted. If declarative
  YAML/TOML templates are needed later, write a loader/adapter that maps
  string names to Python types via a registry.
- **Post-agent mutation**: the unified engine unconditionally stores
  `AgentResult` in `PhaseState`. No per-path callbacks. Consumers pull
  from state.

## Open questions

- [ ] Should unused templates (`REWORK_TEMPLATE`, `SYSTEM_OPERATION_TEMPLATE`
  in `templates_builtin.py`) be removed as part of this work, or left for
  a separate cleanup? They were defined by PRD-227.5/227.6 but never
  adopted by their respective recipes.

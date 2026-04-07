---
id: "PRD-210"
title: "Runner — Task Dispatch + Status Transitions"
kind: task
status: ready
priority: high
effort: m
capability: moderate
parent: "[[PRD-200-workflow-execution-layer]]"
depends_on:
  - "[[PRD-201-workflow-dataclasses]]"
  - "[[PRD-202-builtins-registry-stubs]]"
  - "[[PRD-205-default-workflow]]"
  - "[[PRD-207-prompt-templates]]"
  - "[[PRD-208-agent-invoke]]"
blocks:
  - "[[PRD-211-plan-run-cli]]"
impacts:
  - tools/prd-harness/src/prd_harness/runner.py
  - tools/prd-harness/tests/test_runner.py
workflow: null
target_version: null
created: 2026-04-07
updated: 2026-04-07
tags:
  - harness
  - runner
  - execution
---

# Runner — Task Dispatch + Status Transitions

## Summary

The orchestration loop: given a PRD and a Workflow, walk the task list, dispatch each task to the appropriate handler (BUILTINS dict, `invoke_claude`, `subprocess.run`), and thread an `ExecutionContext` through. Enforces status transitions and retry logic for shell task failures.

## Requirements

1. `run_workflow(prd, workflow, repo_root, base_ref, dry_run, model_override=None) -> RunResult` — top-level entry point
2. For each `BuiltIn` task: look up `name` in `BUILTINS`, call with `(ctx, **task.kwargs)` (kwargs format-stringed via `ctx.format_string`)
3. For each `AgentTask`: compose prompt via `templates.compose_prompt`, pick model (explicit > capability-derived > override), invoke via `invoke_claude`, set `ctx.agent_output` / `ctx.agent_success`
4. For each `ShellTask`: run via `subprocess.run` with `cmd` format-stringed, `cwd=ctx.cwd`
5. Shell task `on_failure="retry_agent"`: compose the retry prompt with `verify_prompts` + `{{CHECK_OUTPUT}}` set to the failed stdout/stderr, re-invoke agent once, retry the shell task once
6. On any unrecoverable failure: `prd.set_status(ctx.prd, "blocked")`, log, raise/return failure
7. Runner never catches `NotImplementedError` from stubs — lets them propagate (until PRD-209 lands)
8. Dry-run mode (`ctx.dry_run=True`): prints each task and what it would do, never calls builtins/invoke/subprocess
9. Returns a `RunResult` dataclass with status, pr_url, agent_output summary, list of tasks completed

## Technical Approach

**New file**: `tools/prd-harness/src/prd_harness/runner.py`

```python
@dataclass
class RunResult:
    success: bool
    pr_url: str | None
    completed_tasks: list[str]
    failure_reason: str | None

def run_workflow(prd, workflow, repo_root, base_ref, dry_run=True, model_override=None):
    ctx = ExecutionContext(prd=prd, repo_root=repo_root, workflow=workflow,
                           base_ref=base_ref, branch_name=_branch_name(prd),
                           cwd=repo_root, dry_run=dry_run)
    completed = []
    try:
        for task in workflow.tasks:
            _dispatch(task, ctx, model_override)
            completed.append(_describe(task))
    except Exception as e:
        return RunResult(success=False, pr_url=ctx.pr_url, completed_tasks=completed, failure_reason=str(e))
    return RunResult(success=True, pr_url=ctx.pr_url, completed_tasks=completed, failure_reason=None)

def _dispatch(task, ctx, model_override):
    if isinstance(task, BuiltIn):
        _run_builtin(task, ctx)
    elif isinstance(task, AgentTask):
        _run_agent(task, ctx, model_override)
    elif isinstance(task, ShellTask):
        _run_shell(task, ctx)
    else:
        raise TypeError(f"unknown task type: {type(task).__name__}")
```

Plus `_run_builtin` / `_run_agent` / `_run_shell` helpers, plus the retry loop for `on_failure="retry_agent"`.

**New file**: `tools/prd-harness/tests/test_runner.py`

- Fixture workflow with a few BuiltIn stubs + mocked invoke
- Test dry-run mode doesn't invoke anything
- Test successful run returns success=True
- Test shell failure with retry_agent triggers one retry then fails
- Test agent failure (sentinel) sets status to blocked

## Acceptance Criteria

- [ ] AC-1: `run_workflow` dispatches all three task types correctly
- [ ] AC-2: Dry-run mode never calls subprocess or builtins
- [ ] AC-3: Successful run returns `RunResult(success=True)`
- [ ] AC-4: Shell task failure with `retry_agent` triggers one retry
- [ ] AC-5: After double failure, sets PRD status to `blocked`
- [ ] AC-6: `mypy --strict` passes
- [ ] AC-7: `pytest tests/test_runner.py` passes

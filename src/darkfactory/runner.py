"""Workflow execution engine — walks a workflow's tasks against a context.

The runner is the glue between every other module in the harness:

- It holds an :class:`~darkfactory.workflow.ExecutionContext` and
  threads it through the task list.
- For each :class:`~darkfactory.workflow.BuiltIn`, it looks up the
  named function in :data:`~darkfactory.builtins.BUILTINS` and calls
  it with the context + formatted kwargs.
- For each :class:`~darkfactory.workflow.AgentTask`, it composes the
  prompt via :func:`~darkfactory.templates.compose_prompt`, picks the
  model (explicit override > capability mapping > sonnet fallback),
  invokes Claude Code via :func:`~darkfactory.invoke.invoke_claude`,
  and stores the output on the context.
- For each :class:`~darkfactory.workflow.ShellTask`, it runs the
  formatted command and handles the configured ``on_failure`` policy.

The runner does **not** know how to create branches, manage
worktrees, or open PRs — those are built-in tasks. Its only job is
the dispatch loop and the retry-on-failure bookkeeping.

Retry semantics: when a ShellTask fails with
``on_failure="retry_agent"``, the runner looks backward in the task
list for the most recent AgentTask, re-invokes it with the failed
output bound to ``{{CHECK_OUTPUT}}``, and re-runs the failed shell
task once. If it still fails, the runner gives up and marks the
PRD blocked (via a separate ``set_status`` built-in call).

Dry-run mode: when ``ctx.dry_run=True``, every built-in and shell
task logs what it would do without executing. Agent tasks return a
synthetic success result via :func:`~darkfactory.invoke.invoke_claude`'s
``dry_run=True`` path. This is what ``prd plan`` uses.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .builtins import BUILTINS
from .invoke import InvokeResult, capability_to_model, invoke_claude
from .templates import compose_prompt
from .workflow import (
    AgentTask,
    BuiltIn,
    ExecutionContext,
    ShellTask,
    Task,
    Workflow,
)

if TYPE_CHECKING:
    from .prd import PRD


logger = logging.getLogger("darkfactory.runner")


@dataclass
class TaskStep:
    """A single executed task step and its outcome.

    Used by :class:`RunResult` to record what actually happened during
    a workflow run, for both success reporting and debugging failures.
    """

    name: str
    kind: str  # "builtin" | "agent" | "shell"
    success: bool
    detail: str = ""


@dataclass
class RunResult:
    """Structured outcome of a workflow run.

    The runner populates this as it walks the task list. On success,
    ``success=True`` and ``pr_url`` is set (assuming the workflow
    includes a ``create_pr`` built-in). On failure, ``success=False``
    and ``failure_reason`` describes what went wrong; ``steps`` is
    still populated with every step that completed before the failure.
    """

    success: bool
    pr_url: str | None = None
    steps: list[TaskStep] = field(default_factory=list)
    failure_reason: str | None = None


def _compute_branch_name(prd: "PRD") -> str:
    """Derive the branch name a workflow should use for this PRD.

    Matches the convention in ``ensure_worktree``:
    ``prd/<id>-<slug>``. Surfaced as a helper so callers can compute
    it before creating the ExecutionContext.
    """
    return f"prd/{prd.id}-{prd.slug}"


def _pick_model(task: AgentTask, prd: "PRD", override: str | None = None) -> str:
    """Resolve the model to use for an AgentTask invocation.

    Priority: CLI override > task.model > capability-derived > sonnet.
    """
    if override:
        return override
    if task.model:
        return task.model
    if task.model_from_capability:
        return capability_to_model(prd.capability)
    return "sonnet"


def run_workflow(
    prd: "PRD",
    workflow: Workflow,
    repo_root: Path,
    base_ref: str,
    *,
    dry_run: bool = True,
    model_override: str | None = None,
) -> RunResult:
    """Execute a workflow against a single PRD and return the result.

    Builds an :class:`ExecutionContext` and dispatches each task in
    ``workflow.tasks`` in order. Tasks mutate the context as they run
    (set worktree path, store agent output, capture PR URL). On any
    uncaught exception, returns a failure result with the partial
    ``steps`` list so the caller can see what completed.

    ``dry_run=True`` (default) makes every task log instead of
    executing — safe to call on arbitrary PRDs.
    """
    branch_name = _compute_branch_name(prd)
    ctx = ExecutionContext(
        prd=prd,
        repo_root=repo_root,
        workflow=workflow,
        base_ref=base_ref,
        branch_name=branch_name,
        cwd=repo_root,
        dry_run=dry_run,
        logger=logger,
    )

    result = RunResult(success=True)
    # Track the last AgentTask so a later ShellTask with
    # on_failure=retry_agent can re-invoke it.
    last_agent_task: AgentTask | None = None
    last_agent_result: InvokeResult | None = None

    for task in workflow.tasks:
        try:
            step = _dispatch(
                task, ctx, model_override, last_agent_task, last_agent_result
            )
            result.steps.append(step)

            if isinstance(task, AgentTask):
                last_agent_task = task
                # We can't easily reach the InvokeResult from _dispatch without
                # restructuring, so we re-record it here via a side channel:
                # _dispatch stores the agent result on the context.
                last_agent_result = getattr(ctx, "_last_agent_result", None)

            if not step.success:
                result.success = False
                result.failure_reason = step.detail or f"task {step.name!r} failed"
                break
        except Exception as exc:  # noqa: BLE001 — we want to log any failure
            result.success = False
            result.failure_reason = f"task {_task_name(task)!r} raised: {exc}"
            result.steps.append(
                TaskStep(
                    name=_task_name(task),
                    kind=_task_kind(task),
                    success=False,
                    detail=str(exc),
                )
            )
            break

    result.pr_url = ctx.pr_url
    return result


def _task_name(task: Task) -> str:
    if isinstance(task, BuiltIn):
        return task.name
    if isinstance(task, AgentTask):
        return task.name
    if isinstance(task, ShellTask):
        return task.name
    return type(task).__name__


def _task_kind(task: Task) -> str:
    if isinstance(task, BuiltIn):
        return "builtin"
    if isinstance(task, AgentTask):
        return "agent"
    if isinstance(task, ShellTask):
        return "shell"
    return "unknown"


def _dispatch(
    task: Task,
    ctx: ExecutionContext,
    model_override: str | None,
    last_agent_task: AgentTask | None,
    last_agent_result: InvokeResult | None,
) -> TaskStep:
    """Dispatch a single task by type and return a TaskStep describing the outcome."""
    if isinstance(task, BuiltIn):
        return _run_builtin(task, ctx)
    if isinstance(task, AgentTask):
        return _run_agent(task, ctx, model_override)
    if isinstance(task, ShellTask):
        return _run_shell(task, ctx, last_agent_task, model_override)
    raise TypeError(f"unknown task type: {type(task).__name__}")


def _run_builtin(task: BuiltIn, ctx: ExecutionContext) -> TaskStep:
    """Look up the built-in by name and call it with formatted kwargs."""
    if task.name not in BUILTINS:
        return TaskStep(
            name=task.name,
            kind="builtin",
            success=False,
            detail=f"no builtin registered for {task.name!r}",
        )

    func = BUILTINS[task.name]

    # Format any string kwargs against the context (e.g. commit messages
    # like "chore(prd): {prd_id} start work").
    formatted_kwargs: dict[str, object] = {}
    for key, value in task.kwargs.items():
        if isinstance(value, str):
            formatted_kwargs[key] = ctx.format_string(value)
        else:
            formatted_kwargs[key] = value

    func(ctx, **formatted_kwargs)
    return TaskStep(name=task.name, kind="builtin", success=True)


def _run_agent(
    task: AgentTask,
    ctx: ExecutionContext,
    model_override: str | None,
    *,
    extras: dict[str, object] | None = None,
) -> TaskStep:
    """Compose prompts, invoke Claude Code, and record the result on context."""
    prompt = compose_prompt(ctx.workflow, task.prompts, ctx, extras=extras)
    model = _pick_model(task, ctx.prd, override=model_override)

    result = invoke_claude(
        prompt=prompt,
        tools=task.tools,
        model=model,
        cwd=ctx.cwd,
        sentinel_success=task.sentinel_success,
        sentinel_failure=task.sentinel_failure,
        dry_run=ctx.dry_run,
    )

    ctx.agent_output = result.stdout
    ctx.agent_success = result.success
    # Side channel for the retry-on-failure path — keeps the function
    # signature stable.
    setattr(ctx, "_last_agent_result", result)

    return TaskStep(
        name=task.name,
        kind="agent",
        success=result.success,
        detail=result.failure_reason or "",
    )


def _run_shell(
    task: ShellTask,
    ctx: ExecutionContext,
    last_agent_task: AgentTask | None,
    model_override: str | None,
) -> TaskStep:
    """Run a shell command, handling on_failure policy with agent retry if configured."""
    cmd = ctx.format_string(task.cmd)

    if ctx.dry_run:
        ctx.logger.info("[dry-run] %s", cmd)
        return TaskStep(name=task.name, kind="shell", success=True, detail="dry-run")

    first_result = _run_shell_once(cmd, ctx, task.env)

    if first_result.returncode == 0:
        return TaskStep(name=task.name, kind="shell", success=True)

    # Shell task failed — apply on_failure policy.
    failure_output = first_result.stdout + "\n" + first_result.stderr

    if task.on_failure == "ignore":
        ctx.logger.warning(
            "shell task %r failed (ignored): exit=%d",
            task.name,
            first_result.returncode,
        )
        return TaskStep(
            name=task.name,
            kind="shell",
            success=True,
            detail=f"ignored failure (exit {first_result.returncode})",
        )

    if task.on_failure == "fail" or last_agent_task is None:
        return TaskStep(
            name=task.name,
            kind="shell",
            success=False,
            detail=f"exit {first_result.returncode}: {failure_output.strip()[:500]}",
        )

    # on_failure == "retry_agent" and we have a prior AgentTask to re-invoke
    ctx.logger.info(
        "shell task %r failed (exit %d); retrying via agent",
        task.name,
        first_result.returncode,
    )

    # Re-invoke the last AgentTask with verify_prompts + CHECK_OUTPUT
    agent_step = _run_agent(
        AgentTask(
            name=f"{last_agent_task.name}-retry",
            prompts=last_agent_task.verify_prompts or last_agent_task.prompts,
            tools=last_agent_task.tools,
            model=last_agent_task.model,
            model_from_capability=last_agent_task.model_from_capability,
            retries=0,
            sentinel_success=last_agent_task.sentinel_success,
            sentinel_failure=last_agent_task.sentinel_failure,
        ),
        ctx,
        model_override,
        extras={"CHECK_OUTPUT": failure_output},
    )
    if not agent_step.success:
        return TaskStep(
            name=task.name,
            kind="shell",
            success=False,
            detail=f"retry agent failed: {agent_step.detail}",
        )

    # Re-run the shell task once more after the agent fix
    second_result = _run_shell_once(cmd, ctx, task.env)
    if second_result.returncode == 0:
        return TaskStep(
            name=task.name,
            kind="shell",
            success=True,
            detail="passed after agent retry",
        )

    return TaskStep(
        name=task.name,
        kind="shell",
        success=False,
        detail=(
            f"still failing after agent retry (exit {second_result.returncode}): "
            f"{(second_result.stdout + second_result.stderr).strip()[:500]}"
        ),
    )


def _run_shell_once(
    cmd: str,
    ctx: ExecutionContext,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run a shell command once and return the completed-process result."""
    import os

    full_env = dict(os.environ)
    full_env.update(env)

    return subprocess.run(
        cmd,
        shell=True,
        cwd=str(ctx.cwd),
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )

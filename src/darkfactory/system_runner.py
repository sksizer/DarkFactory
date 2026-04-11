"""System operation execution engine.

Mirrors :func:`~darkfactory.runner.run_workflow` but operates on a
:class:`~darkfactory.system.SystemContext` instead of an
:class:`~darkfactory.workflow.ExecutionContext`.

Key differences from the workflow runner:

- **BuiltIn dispatch** uses :data:`SYSTEM_BUILTINS` — a separate registry
  whose callables receive a :class:`SystemContext` rather than an
  :class:`ExecutionContext`.
- **AgentTask prompt composition** resolves prompt files relative to
  :attr:`~darkfactory.system.SystemOperation.operation_dir` and substitutes
  system-op placeholders (``OPERATION_NAME``, ``TARGET_COUNT``, ``TARGET_PRD``).
- **No worktree lock lifecycle** — system operations are either read-only or
  handle their own git mutations through system builtins.
"""

from __future__ import annotations

import logging
from typing import Callable

from .utils.claude_code import invoke_claude
from .utils.shell import run_shell_once
from .runner import RunResult, TaskStep, _task_kind, _task_name
from .system import SystemContext, SystemOperation
from .templates import load_prompt_files, substitute_placeholders
from .timeouts import resolve_timeout
from .workflow import AgentTask, BuiltIn, ShellTask, Task

logger = logging.getLogger("darkfactory.system_runner")

SystemBuiltInFunc = Callable[..., None]
"""Signature every system built-in shares: ``(ctx: SystemContext, **kwargs) -> None``.

System builtins communicate results by mutating the context (setting
``ctx.pr_url``, appending to ``ctx.report``, etc.) and signal failure by
raising an exception.
"""

SYSTEM_BUILTINS: dict[str, SystemBuiltInFunc] = {}
"""Registry mapping system built-in names to their implementing functions.

Analogous to :data:`~darkfactory.builtins.BUILTINS` but scoped to system
operations. Populated at import time by importing
:mod:`~darkfactory.builtins.system_builtins` (which registers each builtin
via its own ``_register`` decorator), and can be extended by direct
assignment during testing.
"""

# Import system_builtins to trigger side-effect registration into this dict.
# The module populates its own SYSTEM_BUILTINS dict; we merge that here so
# run_system_operation can dispatch against all registered implementations.
from .builtins.system_builtins import SYSTEM_BUILTINS as _impl_builtins  # noqa: E402

SYSTEM_BUILTINS.update(_impl_builtins)


def system_builtin(name: str) -> Callable[[SystemBuiltInFunc], SystemBuiltInFunc]:
    """Decorator that registers a function in :data:`SYSTEM_BUILTINS`.

    Rejects duplicate registrations with ``ValueError``.
    """

    def decorator(func: SystemBuiltInFunc) -> SystemBuiltInFunc:
        if name in SYSTEM_BUILTINS:
            raise ValueError(f"duplicate system builtin registration for {name!r}")
        SYSTEM_BUILTINS[name] = func
        return func

    return decorator


def run_system_operation(
    operation: SystemOperation,
    ctx: SystemContext,
    model_override: str | None = None,
) -> RunResult:
    """Dispatch loop for system operations — mirrors :func:`~darkfactory.runner.run_workflow`.

    Walks ``operation.tasks`` in order, dispatching each to the appropriate
    handler based on its type:

    - :class:`~darkfactory.workflow.BuiltIn` → :data:`SYSTEM_BUILTINS` lookup
    - :class:`~darkfactory.workflow.AgentTask` → Claude Code invocation via
      :func:`~darkfactory.invoke.invoke_claude` with system-op prompt placeholders
    - :class:`~darkfactory.workflow.ShellTask` → subprocess execution with
      :meth:`~darkfactory.system.SystemContext.format_string` substitution

    On any task failure (non-zero exit, exception, or missing builtin), the
    loop halts and returns a :class:`~darkfactory.runner.RunResult` with
    ``success=False`` and the partial ``steps`` list.

    The caller is responsible for acquiring any process lock before calling
    this function (see :func:`~darkfactory.builtins.ensure_worktree` for the
    pattern used in the workflow runner).
    """
    result = RunResult(success=True)
    last_agent_task: AgentTask | None = None

    for task in operation.tasks:
        try:
            step = _dispatch_system(task, ctx, model_override, last_agent_task)
            result.steps.append(step)

            if isinstance(task, AgentTask):
                last_agent_task = task

            if not step.success:
                result.success = False
                result.failure_reason = (
                    step.detail or f"task {_task_name(task)!r} failed"
                )
                break
        except Exception as exc:  # noqa: BLE001 — log any failure
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


def _dispatch_system(
    task: Task,
    ctx: SystemContext,
    model_override: str | None,
    last_agent_task: AgentTask | None,
) -> TaskStep:
    """Dispatch a single task by type and return a TaskStep describing the outcome."""
    if isinstance(task, BuiltIn):
        return _run_system_builtin(task, ctx)
    if isinstance(task, AgentTask):
        return _run_system_agent(task, ctx, model_override)
    if isinstance(task, ShellTask):
        return _run_system_shell(task, ctx, last_agent_task, model_override)
    raise TypeError(f"unknown task type: {type(task).__name__}")


def _run_system_builtin(task: BuiltIn, ctx: SystemContext) -> TaskStep:
    """Look up the system built-in by name and call it with formatted kwargs."""
    if task.name not in SYSTEM_BUILTINS:
        return TaskStep(
            name=task.name,
            kind="builtin",
            success=False,
            detail=f"no system builtin registered for {task.name!r}",
        )

    func = SYSTEM_BUILTINS[task.name]

    formatted_kwargs: dict[str, object] = {}
    for key, value in task.kwargs.items():
        if isinstance(value, str):
            formatted_kwargs[key] = ctx.format_string(value)
        else:
            formatted_kwargs[key] = value

    func(ctx, **formatted_kwargs)
    return TaskStep(name=task.name, kind="builtin", success=True)


def _pick_system_model(task: AgentTask, model_override: str | None = None) -> str:
    """Resolve the model to use for a system AgentTask.

    Priority: CLI override > task.model > sonnet.
    System operations do not have PRD capability, so the capability-derived
    lookup used in :func:`~darkfactory.runner._pick_model` is omitted.
    """
    if model_override:
        return model_override
    if task.model:
        return task.model
    return "sonnet"


def _compose_system_prompt(
    task: AgentTask,
    ctx: SystemContext,
    extras: dict[str, object] | None = None,
) -> str:
    """Load prompt files and substitute system-op placeholders.

    Prompt files are resolved relative to
    :attr:`~darkfactory.system.SystemOperation.operation_dir`.

    Standard placeholders:

    - ``{{OPERATION_NAME}}`` — the operation's name
    - ``{{TARGET_COUNT}}`` — number of targets
    - ``{{TARGET_PRD}}`` — the target PRD id, or ``""`` if not set

    ``extras`` values (e.g. ``CHECK_OUTPUT`` for retry prompts) are merged
    in after the standard set.
    """
    op_dir = ctx.operation.operation_dir
    if op_dir is None:
        raise ValueError(
            f"operation {ctx.operation.name!r} has no operation_dir; "
            "the loader normally sets this at import time"
        )

    raw = load_prompt_files(op_dir, task.prompts)

    context: dict[str, object] = {
        "OPERATION_NAME": ctx.operation.name,
        "TARGET_COUNT": len(ctx.targets),
        "TARGET_PRD": ctx.target_prd or "",
    }
    if extras:
        context.update(extras)

    return substitute_placeholders(raw, context)


def _run_system_agent(
    task: AgentTask,
    ctx: SystemContext,
    model_override: str | None,
    *,
    extras: dict[str, object] | None = None,
) -> TaskStep:
    """Compose prompts, invoke Claude Code, and return the TaskStep."""
    prompt = _compose_system_prompt(task, ctx, extras)
    model = _pick_system_model(task, model_override)

    timeout_seconds, timeout_source = resolve_timeout(
        effort=None,
        capability=None,
        timeout_minutes_frontmatter=None,
        config_timeouts=None,
        cli_override=None,
    )
    logger.info("Timeout: %ds (source: %s)", timeout_seconds, timeout_source)

    result = invoke_claude(
        prompt=prompt,
        tools=task.tools,
        model=model,
        cwd=ctx.cwd,
        sentinel_success=task.sentinel_success,
        sentinel_failure=task.sentinel_failure,
        dry_run=ctx.dry_run,
        timeout_seconds=timeout_seconds,
    )

    return TaskStep(
        name=task.name,
        kind="agent",
        success=result.success,
        detail=result.failure_reason or "",
    )


def _run_system_shell(
    task: ShellTask,
    ctx: SystemContext,
    last_agent_task: AgentTask | None,
    model_override: str | None,
) -> TaskStep:
    """Run a shell command with format_string substitution and on_failure policy."""
    cmd = ctx.format_string(task.cmd)

    if ctx.dry_run:
        ctx.logger.info("[dry-run] %s", cmd)
        return TaskStep(name=task.name, kind="shell", success=True, detail="dry-run")

    first_result = run_shell_once(cmd, ctx.cwd, task.env)

    if first_result.returncode == 0:
        return TaskStep(name=task.name, kind="shell", success=True)

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

    # on_failure == "retry_agent"
    ctx.logger.info(
        "shell task %r failed (exit %d); retrying via agent",
        task.name,
        first_result.returncode,
    )

    agent_step = _run_system_agent(
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

    second_result = run_shell_once(cmd, ctx.cwd, task.env)
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



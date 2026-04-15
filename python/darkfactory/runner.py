"""Unified execution engine — walks task lists against typed contexts.

The engine is the glue between every other module in the harness:

- For each :class:`~darkfactory.workflow.BuiltIn`, it looks up the
  named function in the provided builtin registry and calls it with
  the context + formatted kwargs.
- For each :class:`~darkfactory.workflow.AgentTask`, it composes the
  prompt via the provided ``compose_prompt`` callback, picks the
  model, invokes Claude Code via :func:`~darkfactory.invoke.invoke_claude`,
  and stores an :class:`~darkfactory.engine.AgentResult` in
  the context's :class:`~darkfactory.engine.PhaseState`.
- For each :class:`~darkfactory.workflow.ShellTask`, it runs the
  formatted command and handles the configured ``on_failure`` policy.
- For each :class:`~darkfactory.workflow.InteractiveTask`, it launches
  an interactive Claude Code session via ``spawn_claude``.

Both workflow and project workflow execution paths use the single
:func:`run_tasks` dispatch function, parameterized on their respective
builtin registries, prompt composers, and model pickers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .operations import BUILTINS
from .event_log import EventWriter, emit_task_event
from .utils.claude_code import InvokeResult, capability_to_model, invoke_claude
from .utils.shell import run_shell
from .model import compute_branch_name
from .engine import (
    AgentResult,
    CodeEnv,
    PrResult,
    PrdWorkflowRun,
    ProjectRun,
    WorktreeState,
)
from .workflow import compose_prompt
from .timeouts import resolve_timeout
from .utils.claude_code import spawn_claude
from .workflow import (
    AgentTask,
    BuiltIn,
    InteractiveTask,
    RunContext,
    ShellTask,
    Task,
    Workflow,
)

if TYPE_CHECKING:
    from .model import PRD
    from .style import Styler


logger = logging.getLogger("darkfactory.runner")


# ---------- result types ----------


@dataclass
class TaskStep:
    """A single executed task step and its outcome."""

    name: str
    kind: str  # "builtin" | "agent" | "shell" | "interactive"
    success: bool
    detail: str = ""


@dataclass
class RunResult:
    """Structured outcome of a workflow or project workflow run."""

    success: bool
    pr_url: str | None = None
    steps: list[TaskStep] = field(default_factory=list)
    failure_reason: str | None = None


# ---------- model selection ----------


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


def _pick_system_model(task: AgentTask, override: str | None = None) -> str:
    """Resolve the model for a system AgentTask (no PRD capability)."""
    if override:
        return override
    if task.model:
        return task.model
    return "sonnet"


# ---------- task name/kind helpers ----------


def _task_name(task: Task) -> str:
    if isinstance(task, BuiltIn):
        return task.name
    if isinstance(task, AgentTask):
        return task.name
    if isinstance(task, ShellTask):
        return task.name
    if isinstance(task, InteractiveTask):
        return task.name
    return type(task).__name__


def _task_kind(task: Task) -> str:
    if isinstance(task, BuiltIn):
        return "builtin"
    if isinstance(task, AgentTask):
        return "agent"
    if isinstance(task, ShellTask):
        return "shell"
    if isinstance(task, InteractiveTask):
        return "interactive"
    return "unknown"


# ---------- unified dispatch engine ----------


ComposePromptFn = Callable[[AgentTask, Any, dict[str, object] | None], str]
PickModelFn = Callable[[AgentTask, str | None], str]


def run_tasks(
    tasks: list[Task],
    ctx: RunContext,
    builtins: dict[str, Callable[..., None]],
    compose_prompt_fn: ComposePromptFn,
    pick_model_fn: PickModelFn,
    *,
    model_override: str | None = None,
    cli_timeout_minutes: int | None = None,
    config_timeouts: dict[str, object] | None = None,
    styler: "Styler | None" = None,
    timeout_effort: str | None = None,
    timeout_capability: str | None = None,
    timeout_frontmatter: int | None = None,
) -> RunResult:
    """Unified dispatch loop for both workflow and project workflow runs.

    Walks ``tasks`` in order, dispatching each to the appropriate handler
    based on its type. On any task failure or uncaught exception, the
    loop halts and returns a failure result with the partial steps.
    """
    result = RunResult(success=True)
    last_agent_task: AgentTask | None = None
    last_agent_invoke: InvokeResult | None = None
    writer: EventWriter | None = ctx.event_writer

    for task in tasks:
        try:
            t_name = _task_name(task)
            t_kind = _task_kind(task)

            if writer:
                task_fields: dict[str, object] = {
                    "task": t_name,
                    "kind": t_kind,
                }
                if isinstance(task, ShellTask):
                    task_fields["cmd"] = (
                        ctx.format_string(task.cmd) if not ctx.dry_run else task.cmd
                    )
                elif isinstance(task, AgentTask):
                    task_fields["model"] = pick_model_fn(task, model_override)
                writer.emit("workflow", "task_start", **task_fields)

            task_start = time.monotonic()

            if isinstance(task, BuiltIn):
                step = _run_builtin(task, ctx, builtins)
            elif isinstance(task, AgentTask):
                step, invoke_result = _run_agent(
                    task,
                    ctx,
                    compose_prompt_fn,
                    pick_model_fn,
                    model_override,
                    cli_timeout_minutes=cli_timeout_minutes,
                    config_timeouts=config_timeouts,
                    styler=styler,
                    timeout_effort=timeout_effort,
                    timeout_capability=timeout_capability,
                    timeout_frontmatter=timeout_frontmatter,
                )
                if invoke_result is not None:
                    last_agent_invoke = invoke_result
            elif isinstance(task, ShellTask):
                step = _run_shell(
                    task,
                    ctx,
                    last_agent_task,
                    last_agent_invoke,
                    compose_prompt_fn,
                    pick_model_fn,
                    model_override,
                    cli_timeout_minutes=cli_timeout_minutes,
                    config_timeouts=config_timeouts,
                    styler=styler,
                    timeout_effort=timeout_effort,
                    timeout_capability=timeout_capability,
                    timeout_frontmatter=timeout_frontmatter,
                )
            elif isinstance(task, InteractiveTask):
                step = _run_interactive(task, ctx)
            else:
                raise TypeError(f"unknown task type: {type(task).__name__}")

            duration_ms = int((time.monotonic() - task_start) * 1000)
            result.steps.append(step)

            if writer:
                writer.emit(
                    "workflow",
                    "task_finish",
                    task=t_name,
                    kind=t_kind,
                    success=step.success,
                    duration_ms=duration_ms,
                    detail=step.detail or None,
                )

            if isinstance(task, AgentTask):
                last_agent_task = task

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
            if writer:
                writer.emit(
                    "workflow",
                    "task_finish",
                    task=_task_name(task),
                    kind=_task_kind(task),
                    success=False,
                    detail=str(exc),
                )
            break

    return result


# ---------- per-task dispatch ----------


def _run_builtin(
    task: BuiltIn,
    ctx: RunContext,
    builtins: dict[str, Callable[..., None]],
) -> TaskStep:
    """Look up the built-in by name and call it with formatted kwargs."""
    if task.name not in builtins:
        return TaskStep(
            name=task.name,
            kind="builtin",
            success=False,
            detail=f"no builtin registered for {task.name!r}",
        )

    func = builtins[task.name]

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
    ctx: RunContext,
    compose_prompt_fn: ComposePromptFn,
    pick_model_fn: PickModelFn,
    model_override: str | None,
    *,
    extras: dict[str, object] | None = None,
    cli_timeout_minutes: int | None = None,
    config_timeouts: dict[str, object] | None = None,
    styler: "Styler | None" = None,
    timeout_effort: str | None = None,
    timeout_capability: str | None = None,
    timeout_frontmatter: int | None = None,
) -> tuple[TaskStep, InvokeResult | None]:
    """Compose prompts, invoke Claude Code, store AgentResult in PhaseState."""
    prompt = compose_prompt_fn(task, ctx, extras)
    model = pick_model_fn(task, model_override)

    timeout_seconds, timeout_source = resolve_timeout(
        effort=timeout_effort,
        capability=timeout_capability,
        timeout_minutes_frontmatter=timeout_frontmatter,
        config_timeouts=config_timeouts,
        cli_override=cli_timeout_minutes,
    )
    logger.info("Timeout: %ds (source: %s)", timeout_seconds, timeout_source)

    writer: EventWriter | None = ctx.event_writer

    result = invoke_claude(
        prompt=prompt,
        tools=task.tools,
        model=model,
        cwd=ctx.cwd,
        sentinel_success=task.sentinel_success,
        sentinel_failure=task.sentinel_failure,
        dry_run=ctx.dry_run,
        timeout_seconds=timeout_seconds,
        effort_level=task.effort_level,
        styler=styler,
        event_writer=writer,
        event_task_name=task.name,
    )

    # Derive invoke_count from previous AgentResult if any.
    prev_count = 0
    if ctx.state.has(AgentResult):
        prev_count = ctx.state.get(AgentResult).invoke_count

    ctx.state.put(
        AgentResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            success=result.success,
            failure_reason=result.failure_reason,
            tool_counts=result.tool_counts,
            sentinel=result.sentinel,
            model=model,
            invoke_count=prev_count + 1,
        )
    )

    return (
        TaskStep(
            name=task.name,
            kind="agent",
            success=result.success,
            detail=result.failure_reason or "",
        ),
        result,
    )


def _run_shell(
    task: ShellTask,
    ctx: RunContext,
    last_agent_task: AgentTask | None,
    last_agent_result: InvokeResult | None,
    compose_prompt_fn: ComposePromptFn,
    pick_model_fn: PickModelFn,
    model_override: str | None,
    *,
    cli_timeout_minutes: int | None = None,
    config_timeouts: dict[str, object] | None = None,
    styler: "Styler | None" = None,
    timeout_effort: str | None = None,
    timeout_capability: str | None = None,
    timeout_frontmatter: int | None = None,
) -> TaskStep:
    """Run a shell command, handling on_failure policy with agent retry if configured."""
    cmd = ctx.format_string(task.cmd, shell_escape=True)

    if ctx.dry_run:
        ctx.logger.info("[dry-run] %s", cmd)
        return TaskStep(name=task.name, kind="shell", success=True, detail="dry-run")

    first_result = run_shell(cmd, ctx.cwd, task.env)

    # Emit shell output events via the event writer.
    writer: EventWriter | None = ctx.event_writer
    if writer:
        if first_result.stdout:
            emit_task_event(
                ctx,
                "shell_output",
                task=task.name,
                stream="stdout",
                text=first_result.stdout[:10000],
            )
        if first_result.stderr:
            emit_task_event(
                ctx,
                "shell_output",
                task=task.name,
                stream="stderr",
                text=first_result.stderr[:10000],
            )

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

    retry_task = AgentTask(
        name=f"{last_agent_task.name}-retry",
        prompts=last_agent_task.verify_prompts or last_agent_task.prompts,
        tools=last_agent_task.tools,
        model=last_agent_task.model,
        model_from_capability=last_agent_task.model_from_capability,
        retries=0,
        sentinel_success=last_agent_task.sentinel_success,
        sentinel_failure=last_agent_task.sentinel_failure,
    )

    agent_step, _ = _run_agent(
        retry_task,
        ctx,
        compose_prompt_fn,
        pick_model_fn,
        model_override,
        extras={"CHECK_OUTPUT": failure_output},
        cli_timeout_minutes=cli_timeout_minutes,
        config_timeouts=config_timeouts,
        styler=styler,
        timeout_effort=timeout_effort,
        timeout_capability=timeout_capability,
        timeout_frontmatter=timeout_frontmatter,
    )
    if not agent_step.success:
        return TaskStep(
            name=task.name,
            kind="shell",
            success=False,
            detail=f"retry agent failed: {agent_step.detail}",
        )

    # Re-run the shell task once more after the agent fix
    second_result = run_shell(cmd, ctx.cwd, task.env)
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


def _run_interactive(task: InteractiveTask, ctx: RunContext) -> TaskStep:
    """Launch an interactive Claude Code session via spawn_claude."""
    if ctx.dry_run:
        ctx.logger.info("[dry-run] interactive: %s", task.name)
        return TaskStep(
            name=task.name, kind="interactive", success=True, detail="dry-run"
        )

    # Load and compose prompt from the prompt_file.
    from .engine import PrdContext

    prompt = ""
    if task.prompt_file:
        # Resolve prompt file relative to workflow_dir
        wf_dir: Path | None = None
        if ctx.state.has(PrdWorkflowRun):
            wf_dir = ctx.state.get(PrdWorkflowRun).workflow.workflow_dir
        elif ctx.state.has(ProjectRun):
            wf_dir = ctx.state.get(ProjectRun).workflow.workflow_dir

        if wf_dir is not None:
            prompt_path = wf_dir / task.prompt_file
        else:
            prompt_path = Path(task.prompt_file)

        if prompt_path.exists():
            raw = prompt_path.read_text(encoding="utf-8")
            # Substitute known placeholders.
            prd_context = ""
            if ctx.state.has(PrdContext):
                pc = ctx.state.get(PrdContext)
                prd_context = pc.body
            prompt = raw.replace("{PRD_CONTEXT}", prd_context).replace(
                "{PHASE}", task.name
            )
        else:
            raise FileNotFoundError(f"prompt file not found: {prompt_path}")

    from .utils.tui import print_phase_banner

    print_phase_banner(task.name)
    time.sleep(1)

    exit_code = spawn_claude(prompt, ctx.cwd, effort_level=task.effort_level)

    if exit_code != 0:
        ctx.logger.warning(
            "interactive task %r: claude exited with code %d (continuing)",
            task.name,
            exit_code,
        )

    return TaskStep(name=task.name, kind="interactive", success=True)


# ---------- worktree lock management ----------


def _release_worktree_lock(ctx: RunContext) -> None:
    """Release the advisory lock acquired by ensure_worktree, if any."""
    lock = ctx._worktree_lock
    if lock is None:
        return
    try:
        lock.release()
    except Exception as exc:  # noqa: BLE001
        ctx.logger.warning("failed to release worktree lock: %s", exc)
    finally:
        ctx._worktree_lock = None


# ---------- workflow-specific entry point ----------


def _workflow_compose_prompt(
    task: AgentTask, ctx: RunContext, extras: dict[str, object] | None = None
) -> str:
    """Compose prompt for workflow AgentTask.

    Injects ``REWORK_FEEDBACK`` from ReworkState when present.
    """
    from .engine import ReworkState

    prd_run = ctx.state.get(PrdWorkflowRun)

    rework_extras: dict[str, object] = {}
    if ctx.state.has(ReworkState):
        rework = ctx.state.get(ReworkState)
        if rework.review_threads is not None:
            from darkfactory.rework.prompt import render_rework_feedback

            rework_extras["REWORK_FEEDBACK"] = render_rework_feedback(
                rework.review_threads
            )
    if extras:
        rework_extras.update(extras)

    return compose_prompt(
        prd_run.workflow, task.prompts, ctx, extras=rework_extras or None
    )


def run_workflow(
    prd: "PRD",
    workflow: Workflow,
    repo_root: Path,
    base_ref: str,
    *,
    dry_run: bool = True,
    model_override: str | None = None,
    cli_timeout_minutes: int | None = None,
    config_timeouts: dict[str, object] | None = None,
    styler: "Styler | None" = None,
    session_id: str | None = None,
    phase_state_init: list[object] | None = None,
) -> RunResult:
    """Execute a workflow against a single PRD and return the result."""
    branch_name = compute_branch_name(prd)

    writer: EventWriter | None = None
    if not dry_run and session_id:
        writer = EventWriter(repo_root, session_id, prd.id)

    ctx = RunContext(
        dry_run=dry_run,
        logger=logger,
        event_writer=writer,
    )

    # Seed the PhaseState with CodeEnv, PrdWorkflowRun, and WorktreeState.
    ctx.state.put(CodeEnv(repo_root=repo_root, cwd=repo_root))
    ctx.state.put(PrdWorkflowRun(prd=prd, workflow=workflow))
    ctx.state.put(WorktreeState(branch=branch_name, base_ref=base_ref))

    if phase_state_init:
        for bundle in phase_state_init:
            ctx.state.put(bundle)

    if writer:
        wt = ctx.state.get(WorktreeState)
        writer.emit(
            "workflow",
            "workflow_start",
            workflow=workflow.name,
            branch_name=wt.branch,
            worktree_path=str(wt.worktree_path) if wt.worktree_path else None,
        )

    def pick_model_for_prd(task: AgentTask, override: str | None = None) -> str:
        return _pick_model(task, prd, override)

    try:
        result = run_tasks(
            tasks=workflow.tasks,
            ctx=ctx,
            builtins=BUILTINS,
            compose_prompt_fn=_workflow_compose_prompt,
            pick_model_fn=pick_model_for_prd,
            model_override=model_override,
            cli_timeout_minutes=cli_timeout_minutes,
            config_timeouts=config_timeouts,
            styler=styler,
            timeout_effort=prd.effort,
            timeout_capability=prd.capability,
            timeout_frontmatter=prd.raw_frontmatter.get("timeout_minutes"),
        )
    finally:
        if writer:
            # We may not have result if an exception was raised before run_tasks returned.
            _result = locals().get("result", RunResult(success=False))
            writer.emit(
                "workflow",
                "workflow_finish",
                success=_result.success,
                failure_reason=_result.failure_reason,
                steps=[
                    {"name": s.name, "kind": s.kind, "success": s.success}
                    for s in _result.steps
                ],
            )
            writer.close()
        _release_worktree_lock(ctx)

    result.pr_url = ctx.state.get(PrResult).url if ctx.state.has(PrResult) else None
    return result


# ---------- project workflow entry point ----------


def _project_compose_prompt(
    task: AgentTask, ctx: RunContext, extras: dict[str, object] | None = None
) -> str:
    """Load prompt files and substitute project-workflow placeholders."""
    from darkfactory.workflow import load_prompt_files, substitute_placeholders

    proj = ctx.state.get(ProjectRun)
    wf_dir = proj.workflow.workflow_dir
    if wf_dir is None:
        raise ValueError(
            f"workflow {proj.workflow.name!r} has no workflow_dir; "
            "the loader normally sets this at import time"
        )

    raw = load_prompt_files(wf_dir, task.prompts)

    context: dict[str, object] = {
        "OPERATION_NAME": proj.workflow.name,
        "TARGET_COUNT": len(proj.targets),
        "TARGET_PRD": proj.target_prd or "",
    }
    if extras:
        context.update(extras)

    return substitute_placeholders(raw, context)


def run_project_operation(
    operation: Workflow,
    ctx: RunContext,
    model_override: str | None = None,
    *,
    session_id: str | None = None,
    cli_timeout_minutes: int | None = None,
    config_timeouts: dict[str, object] | None = None,
    styler: "Styler | None" = None,
) -> RunResult:
    """Execute a project workflow via the unified dispatch engine.

    When ``session_id`` is provided and the context is not dry-run, an
    :class:`EventWriter` is created automatically so project workflows
    produce event logs just like workflow runs.
    """
    from .operations.project_builtins import SYSTEM_BUILTINS

    writer: EventWriter | None = ctx.event_writer
    owns_writer = False

    if writer is None and session_id and not ctx.dry_run:
        writer = EventWriter(ctx.repo_root, session_id, operation.name)
        ctx.event_writer = writer
        owns_writer = True

    if writer:
        writer.emit(
            "workflow",
            "workflow_start",
            workflow=operation.name,
        )

    try:
        result = run_tasks(
            tasks=operation.tasks,
            ctx=ctx,
            builtins=SYSTEM_BUILTINS,
            compose_prompt_fn=_project_compose_prompt,
            pick_model_fn=_pick_system_model,
            model_override=model_override,
            cli_timeout_minutes=cli_timeout_minutes,
            config_timeouts=config_timeouts,
            styler=styler,
        )
    finally:
        if writer:
            _result = locals().get("result", RunResult(success=False))
            writer.emit(
                "workflow",
                "workflow_finish",
                success=_result.success,
                failure_reason=_result.failure_reason,
                steps=[
                    {"name": s.name, "kind": s.kind, "success": s.success}
                    for s in _result.steps
                ],
            )
            if owns_writer:
                writer.close()

    result.pr_url = ctx.state.get(PrResult).url if ctx.state.has(PrResult) else None
    return result

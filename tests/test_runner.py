"""Tests for the workflow runner.

The runner is the most integration-heavy module so the tests mostly
exercise the full dispatch loop against mocked builtins and a mocked
``invoke_claude``. Dry-run mode is tested throughout because that's
the normal path for ``prd plan``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.invoke import InvokeResult
from darkfactory.prd import PRD, load_all
from darkfactory.runner import (
    RunResult,
    TaskStep,
    _compute_branch_name,
    _pick_model,
    run_workflow,
)
from darkfactory.workflow import (
    AgentTask,
    BuiltIn,
    ExecutionContext,
    ShellTask,
    Task,
    Workflow,
)

from .conftest import write_prd


# ---------- helpers ----------


def _make_workflow(tmp_path: Path, tasks: list[Task]) -> Workflow:
    """Create a Workflow with workflow_dir set for prompt composition."""
    wf_dir = tmp_path / "wf"
    wf_dir.mkdir(exist_ok=True)
    prompts_dir = wf_dir / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    (prompts_dir / "role.md").write_text("# Role\nYou are an agent.\n")
    (prompts_dir / "task.md").write_text("# Task\nImplement {{PRD_ID}}.\n")
    (prompts_dir / "verify.md").write_text("# Verify\nFix:\n{{CHECK_OUTPUT}}\n")

    return Workflow(
        name="test",
        applies_to=lambda prd, prds: True,
        tasks=tasks,
        workflow_dir=wf_dir,
    )


def _make_prd(
    tmp_path: Path, prd_id: str = "PRD-070", capability: str = "simple"
) -> PRD:
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir(exist_ok=True)
    write_prd(prd_dir, prd_id, "test-task", capability=capability)
    prds = load_all(prd_dir)
    return prds[prd_id]


# ---------- helpers (unit) ----------


def test_compute_branch_name(tmp_path: Path) -> None:
    prd = _make_prd(tmp_path)
    assert _compute_branch_name(prd) == "prd/PRD-070-test-task"


def test_pick_model_explicit_override(tmp_path: Path) -> None:
    prd = _make_prd(tmp_path, capability="simple")
    task = AgentTask()
    assert _pick_model(task, prd, override="opus") == "opus"


def test_pick_model_task_explicit(tmp_path: Path) -> None:
    prd = _make_prd(tmp_path, capability="simple")
    task = AgentTask(model="haiku", model_from_capability=False)
    assert _pick_model(task, prd) == "haiku"


def test_pick_model_from_capability(tmp_path: Path) -> None:
    prd = _make_prd(tmp_path, capability="complex")
    task = AgentTask()  # model_from_capability=True by default
    assert _pick_model(task, prd) == "opus"


def test_pick_model_fallback(tmp_path: Path) -> None:
    prd = _make_prd(tmp_path, capability="simple")
    task = AgentTask(model=None, model_from_capability=False)
    assert _pick_model(task, prd) == "sonnet"


# ---------- dry-run ----------


def test_dry_run_dispatches_every_task(tmp_path: Path) -> None:
    """Dry-run mode walks every task and records a step but doesn't execute."""
    wf = _make_workflow(
        tmp_path,
        [
            BuiltIn("ensure_worktree"),
            BuiltIn("set_status", kwargs={"to": "in-progress"}),
            AgentTask(prompts=["prompts/task.md"]),
            ShellTask("test", cmd="echo test"),
            BuiltIn("set_status", kwargs={"to": "review"}),
        ],
    )
    prd = _make_prd(tmp_path)

    result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=True)
    assert result.success is True
    assert len(result.steps) == 5
    assert [s.kind for s in result.steps] == [
        "builtin",
        "builtin",
        "agent",
        "shell",
        "builtin",
    ]
    assert all(s.success for s in result.steps)


def test_dry_run_does_not_create_worktree(tmp_path: Path) -> None:
    wf = _make_workflow(tmp_path, [BuiltIn("ensure_worktree")])
    prd = _make_prd(tmp_path)
    run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=True)
    assert not (tmp_path / ".worktrees" / "PRD-070-test-task").exists()


def test_dry_run_agent_returns_synthetic_success(tmp_path: Path) -> None:
    """The invoke dry-run path returns success without calling subprocess."""
    wf = _make_workflow(tmp_path, [AgentTask(prompts=["prompts/task.md"])])
    prd = _make_prd(tmp_path)

    with patch("subprocess.run") as mock_run:
        result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=True)

    assert result.success is True
    # subprocess.run should never have been called for the agent in dry-run
    # (it might have been called by the builtins, but we have none here).
    assert mock_run.call_count == 0


# ---------- builtin dispatch (with live builtins but mocked subprocess) ----------


def test_builtin_unknown_name_fails(tmp_path: Path) -> None:
    """Referencing an unregistered builtin produces a step failure."""
    wf = _make_workflow(tmp_path, [BuiltIn("nonexistent_builtin")])
    prd = _make_prd(tmp_path)

    result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)
    assert result.success is False
    assert len(result.steps) == 1
    assert "nonexistent_builtin" in (result.failure_reason or "")


def test_builtin_kwargs_are_format_stringed(tmp_path: Path) -> None:
    """BuiltIn.kwargs with {placeholder} strings get expanded against context."""
    wf = _make_workflow(
        tmp_path,
        [BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} test"})],
    )
    prd = _make_prd(tmp_path)

    # In dry-run mode, commit just logs the formatted message.
    result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=True)
    assert result.success is True
    assert result.steps[0].success is True


# ---------- agent dispatch ----------


def test_agent_success_path(tmp_path: Path) -> None:
    wf = _make_workflow(tmp_path, [AgentTask(prompts=["prompts/task.md"])])
    prd = _make_prd(tmp_path)

    with patch("darkfactory.runner.invoke_claude") as mock_invoke:
        mock_invoke.return_value = InvokeResult(
            stdout="did the work\nPRD_EXECUTE_OK: PRD-070\n",
            stderr="",
            exit_code=0,
            success=True,
        )
        result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)

    assert result.success is True
    assert len(result.steps) == 1
    assert result.steps[0].kind == "agent"
    assert result.steps[0].success is True


def test_agent_failure_path(tmp_path: Path) -> None:
    wf = _make_workflow(tmp_path, [AgentTask(prompts=["prompts/task.md"])])
    prd = _make_prd(tmp_path)

    with patch("darkfactory.runner.invoke_claude") as mock_invoke:
        mock_invoke.return_value = InvokeResult(
            stdout="",
            stderr="",
            exit_code=1,
            success=False,
            failure_reason="sentinel missing",
        )
        result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)

    assert result.success is False
    assert result.failure_reason is not None
    assert "sentinel" in result.failure_reason.lower()


def test_agent_model_passed_to_invoke(tmp_path: Path) -> None:
    """The capability-derived model should reach invoke_claude."""
    wf = _make_workflow(tmp_path, [AgentTask(prompts=["prompts/task.md"])])
    prd = _make_prd(tmp_path, capability="complex")

    with patch("darkfactory.runner.invoke_claude") as mock_invoke:
        mock_invoke.return_value = InvokeResult(
            stdout="PRD_EXECUTE_OK: PRD-070\n",
            stderr="",
            exit_code=0,
            success=True,
        )
        run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)

    _, call_kwargs = mock_invoke.call_args
    assert call_kwargs["model"] == "opus"


def test_agent_model_override(tmp_path: Path) -> None:
    wf = _make_workflow(tmp_path, [AgentTask(prompts=["prompts/task.md"])])
    prd = _make_prd(tmp_path, capability="simple")

    with patch("darkfactory.runner.invoke_claude") as mock_invoke:
        mock_invoke.return_value = InvokeResult(
            stdout="PRD_EXECUTE_OK: PRD-070\n",
            stderr="",
            exit_code=0,
            success=True,
        )
        run_workflow(
            prd,
            wf,
            tmp_path,
            base_ref="main",
            dry_run=False,
            model_override="haiku",
        )

    _, call_kwargs = mock_invoke.call_args
    assert call_kwargs["model"] == "haiku"


# ---------- shell dispatch ----------


def test_shell_success_passes_step(tmp_path: Path) -> None:
    wf = _make_workflow(tmp_path, [ShellTask("ok", cmd="true")])
    prd = _make_prd(tmp_path)

    result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)
    assert result.success is True
    assert result.steps[0].success is True


def test_shell_failure_fails_workflow(tmp_path: Path) -> None:
    wf = _make_workflow(tmp_path, [ShellTask("fail", cmd="false", on_failure="fail")])
    prd = _make_prd(tmp_path)

    result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)
    assert result.success is False
    assert result.steps[0].success is False


def test_shell_failure_ignored(tmp_path: Path) -> None:
    """on_failure=ignore -> step marked successful with a note."""
    wf = _make_workflow(
        tmp_path, [ShellTask("fail", cmd="false", on_failure="ignore")]
    )
    prd = _make_prd(tmp_path)

    result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)
    assert result.success is True
    assert "ignored" in (result.steps[0].detail or "").lower()


def test_shell_cmd_is_format_stringed(tmp_path: Path) -> None:
    """ShellTask.cmd gets {placeholder} expansion before execution."""
    wf = _make_workflow(tmp_path, [ShellTask("echo", cmd="echo {prd_id}")])
    prd = _make_prd(tmp_path)

    with patch("darkfactory.runner._run_shell_once") as mock_once:
        mock_once.return_value = subprocess.CompletedProcess(
            args=["echo PRD-070"], returncode=0, stdout="PRD-070\n", stderr=""
        )
        run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)

    args, _ = mock_once.call_args
    assert args[0] == "echo PRD-070"


# ---------- retry_agent on shell failure ----------


def test_shell_failure_triggers_agent_retry(tmp_path: Path) -> None:
    """A failing shell task with retry_agent invokes the prior AgentTask once."""
    wf = _make_workflow(
        tmp_path,
        [
            AgentTask(prompts=["prompts/task.md"], verify_prompts=["prompts/verify.md"]),
            ShellTask("test", cmd="exit 1", on_failure="retry_agent"),
        ],
    )
    prd = _make_prd(tmp_path)

    shell_results = [
        # First shell run: fails
        subprocess.CompletedProcess(
            args=["exit 1"], returncode=1, stdout="test_foo FAILED\n", stderr=""
        ),
        # Second shell run (after agent retry): passes
        subprocess.CompletedProcess(
            args=["exit 1"], returncode=0, stdout="", stderr=""
        ),
    ]

    with patch("darkfactory.runner.invoke_claude") as mock_invoke, patch(
        "darkfactory.runner._run_shell_once", side_effect=shell_results
    ) as mock_shell:
        mock_invoke.return_value = InvokeResult(
            stdout="PRD_EXECUTE_OK: PRD-070\n",
            stderr="",
            exit_code=0,
            success=True,
        )
        result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)

    # Agent was called twice: once for the initial run, once for the retry
    assert mock_invoke.call_count == 2
    # Shell was called twice: initial fail + retry success
    assert mock_shell.call_count == 2
    assert result.success is True
    # The final step should indicate it passed after retry
    final_step = result.steps[-1]
    assert final_step.success is True
    assert "retry" in (final_step.detail or "").lower()


def test_shell_failure_retry_also_fails(tmp_path: Path) -> None:
    """If the retry shell run also fails, the workflow fails."""
    wf = _make_workflow(
        tmp_path,
        [
            AgentTask(prompts=["prompts/task.md"], verify_prompts=["prompts/verify.md"]),
            ShellTask("test", cmd="exit 1", on_failure="retry_agent"),
        ],
    )
    prd = _make_prd(tmp_path)

    failing = subprocess.CompletedProcess(
        args=["exit 1"], returncode=1, stdout="still broken\n", stderr=""
    )

    with patch("darkfactory.runner.invoke_claude") as mock_invoke, patch(
        "darkfactory.runner._run_shell_once", return_value=failing
    ) as mock_shell:
        mock_invoke.return_value = InvokeResult(
            stdout="PRD_EXECUTE_OK: PRD-070\n",
            stderr="",
            exit_code=0,
            success=True,
        )
        result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)

    # Two invocations of the agent (initial + retry) and two shell runs
    assert mock_invoke.call_count == 2
    assert mock_shell.call_count == 2
    assert result.success is False
    assert "still failing" in (result.failure_reason or "").lower()


def test_shell_retry_agent_without_prior_agent_fails_normally(tmp_path: Path) -> None:
    """retry_agent with no prior AgentTask falls through to a hard failure."""
    wf = _make_workflow(
        tmp_path,
        [ShellTask("test", cmd="false", on_failure="retry_agent")],
    )
    prd = _make_prd(tmp_path)

    result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)
    assert result.success is False


# ---------- stops on first failure ----------


def test_runner_stops_after_first_failure(tmp_path: Path) -> None:
    """Once a task fails, subsequent tasks are not executed."""
    wf = _make_workflow(
        tmp_path,
        [
            ShellTask("first-ok", cmd="true"),
            ShellTask("fail", cmd="false"),
            ShellTask("never", cmd="true"),  # should never run
        ],
    )
    prd = _make_prd(tmp_path)

    result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=False)
    assert result.success is False
    # First two steps recorded, third never executed
    assert len(result.steps) == 2
    assert result.steps[0].name == "first-ok"
    assert result.steps[0].success is True
    assert result.steps[1].name == "fail"
    assert result.steps[1].success is False


def test_runner_result_has_pr_url_when_set(tmp_path: Path) -> None:
    """If create_pr runs, ctx.pr_url is copied to result.pr_url."""
    wf = _make_workflow(tmp_path, [BuiltIn("create_pr")])
    prd = _make_prd(tmp_path)

    # Dry-run sets a placeholder pr_url
    result = run_workflow(prd, wf, tmp_path, base_ref="main", dry_run=True)
    assert result.pr_url is not None

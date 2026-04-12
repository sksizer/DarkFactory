"""Tests for the workflow dataclasses and ExecutionContext."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from darkfactory.model import load_all
from darkfactory.workflow import (
    AgentTask,
    BuiltIn,
    ExecutionContext,
    ShellTask,
    Task,
    Workflow,
    _default_applies_to,
)

from .conftest import write_prd


# ---------- Task construction ----------


def test_builtin_minimal() -> None:
    task = BuiltIn("ensure_worktree")
    assert task.name == "ensure_worktree"
    assert task.kwargs == {}
    assert isinstance(task, Task)


def test_builtin_with_kwargs() -> None:
    task = BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start"})
    assert task.kwargs == {"message": "chore(prd): {prd_id} start"}


def test_agent_task_defaults() -> None:
    task = AgentTask()
    assert task.name == "implement"
    assert task.prompts == []
    assert task.tools == []
    assert task.model is None
    assert task.model_from_capability is True
    assert task.retries == 1
    assert task.verify_prompts == []
    assert task.sentinel_success == "PRD_EXECUTE_OK"
    assert task.sentinel_failure == "PRD_EXECUTE_FAILED"
    assert isinstance(task, Task)


def test_agent_task_fully_specified() -> None:
    task = AgentTask(
        name="decompose",
        prompts=["prompts/role.md", "prompts/task.md"],
        tools=["Read", "Write", "Bash(git status:*)"],
        model="opus",
        model_from_capability=False,
        retries=0,
        verify_prompts=["prompts/verify.md"],
        sentinel_success="OK",
        sentinel_failure="FAIL",
    )
    assert task.name == "decompose"
    assert task.model == "opus"
    assert task.model_from_capability is False
    assert task.retries == 0
    assert len(task.prompts) == 2
    assert len(task.tools) == 3


def test_shell_task_minimal() -> None:
    task = ShellTask("test", cmd="just test")
    assert task.name == "test"
    assert task.cmd == "just test"
    assert task.on_failure == "fail"
    assert task.env == {}
    assert isinstance(task, Task)


def test_shell_task_with_retry_policy() -> None:
    task = ShellTask(
        name="test",
        cmd="just test",
        on_failure="retry_agent",
        env={"RUST_BACKTRACE": "1"},
    )
    assert task.on_failure == "retry_agent"
    assert task.env == {"RUST_BACKTRACE": "1"}


# ---------- isinstance dispatch ----------


def test_task_types_are_distinguishable() -> None:
    tasks: list[Task] = [
        BuiltIn("ensure_worktree"),
        AgentTask(),
        ShellTask("test", cmd="just test"),
    ]
    # Each task is a Task but only its own subtype
    assert all(isinstance(t, Task) for t in tasks)
    assert isinstance(tasks[0], BuiltIn) and not isinstance(tasks[0], AgentTask)
    assert isinstance(tasks[1], AgentTask) and not isinstance(tasks[1], ShellTask)
    assert isinstance(tasks[2], ShellTask) and not isinstance(tasks[2], BuiltIn)


# ---------- Workflow construction ----------


def test_workflow_minimal() -> None:
    wf = Workflow(name="default")
    assert wf.name == "default"
    assert wf.description == ""
    assert wf.priority == 0
    assert wf.tasks == []
    assert wf.workflow_dir is None
    # Default predicate matches nothing
    assert wf.applies_to is _default_applies_to


def test_workflow_with_tasks() -> None:
    wf = Workflow(
        name="sample",
        description="Sample workflow for testing.",
        priority=10,
        tasks=[
            BuiltIn("ensure_worktree"),
            AgentTask(prompts=["role.md"]),
            ShellTask("test", cmd="just test"),
        ],
    )
    assert len(wf.tasks) == 3
    assert wf.priority == 10
    assert isinstance(wf.tasks[0], BuiltIn)
    assert isinstance(wf.tasks[1], AgentTask)
    assert isinstance(wf.tasks[2], ShellTask)


def test_workflow_custom_applies_to(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-070", "ui-task")
    prds = load_all(tmp_data_dir)

    def predicate(prd, prds):  # type: ignore[no-untyped-def]
        return prd.id == "PRD-070"

    wf = Workflow(name="custom", applies_to=predicate)
    assert wf.applies_to(prds["PRD-070"], prds) is True


def test_default_applies_to_returns_false(tmp_data_dir: Path) -> None:
    write_prd(tmp_data_dir / "prds", "PRD-070", "task")
    prds = load_all(tmp_data_dir)
    assert _default_applies_to(prds["PRD-070"], prds) is False


# ---------- ExecutionContext ----------


def _make_ctx(tmp_data_dir: Path) -> ExecutionContext:
    write_prd(tmp_data_dir / "prds", "PRD-070", "tera-filter-obsidian-link")
    prds = load_all(tmp_data_dir)
    return ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_data_dir,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-tera-filter-obsidian-link",
        worktree_path=tmp_data_dir / ".worktrees" / "PRD-070-tera-filter-obsidian-link",
    )


def test_execution_context_defaults(tmp_data_dir: Path) -> None:
    ctx = _make_ctx(tmp_data_dir)
    assert ctx.base_ref == "main"
    assert ctx.pr_url is None
    assert ctx.dry_run is True
    assert isinstance(ctx.logger, logging.Logger)
    from darkfactory.phase_state import PhaseState

    assert isinstance(ctx.state, PhaseState)


def test_format_string_expands_prd_fields(tmp_data_dir: Path) -> None:
    ctx = _make_ctx(tmp_data_dir)
    assert ctx.format_string("hello {prd_id}") == "hello PRD-070"
    assert ctx.format_string("{prd_title}") == "Test PRD"
    assert ctx.format_string("{prd_slug}") == "tera-filter-obsidian-link"


def test_format_string_expands_branch_refs(tmp_data_dir: Path) -> None:
    ctx = _make_ctx(tmp_data_dir)
    assert ctx.format_string("{branch} from {base_ref}") == (
        "prd/PRD-070-tera-filter-obsidian-link from main"
    )


def test_format_string_expands_worktree(tmp_data_dir: Path) -> None:
    ctx = _make_ctx(tmp_data_dir)
    worktree_str = str(ctx.worktree_path)
    assert worktree_str in ctx.format_string("cd {worktree}")


def test_format_string_empty_worktree_when_unset(tmp_data_dir: Path) -> None:
    ctx = _make_ctx(tmp_data_dir)
    ctx.worktree_path = None
    assert ctx.format_string("{worktree}") == ""


def test_format_string_unknown_placeholder_raises(tmp_data_dir: Path) -> None:
    ctx = _make_ctx(tmp_data_dir)
    with pytest.raises(KeyError):
        ctx.format_string("{nonexistent}")


def test_format_string_composite_commit_message(tmp_data_dir: Path) -> None:
    """The common case: a commit message template with multiple fields."""
    ctx = _make_ctx(tmp_data_dir)
    msg = ctx.format_string("chore(prd): {prd_id} start work on '{prd_title}'")
    assert msg == "chore(prd): PRD-070 start work on 'Test PRD'"

"""Tests for the rework workflow definition and execution.

Covers:
- Workflow loads correctly from the built-in workflows directory.
- Task sequence: starts with ``resolve_rework_context`` and skips
  ``ensure_worktree`` / ``set_status`` / ``create_pr``.
- Commit message format.
- ``run_workflow`` applies ``context_overrides`` to the ExecutionContext
  before dispatch so the resolve builtin is a no-op.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.loader import load_workflows
from darkfactory.utils.github.pr.comments import ReviewThread
from darkfactory.runner import run_workflow
from darkfactory.workflow import (
    AgentTask,
    BuiltIn,
    ExecutionContext,
    Workflow,
)

from .conftest import write_prd


# ---------- helpers ----------


def _thread(
    *,
    author: str = "reviewer",
    path: str | None = "src/foo.py",
    line: int | None = 10,
    body: str = "Please fix this.",
    is_resolved: bool = False,
) -> ReviewThread:
    return ReviewThread(
        thread_id="t-1",
        author=author,
        path=path,
        line=line,
        body=body,
        posted_at="2026-04-10T00:00:00Z",
        is_resolved=is_resolved,
        replies=[],
        review_state=None,
    )


# ---------- workflow load ----------


def test_rework_workflow_loads_from_builtins(real_builtin_workflows: None) -> None:
    """The rework workflow is discoverable via the built-in workflows loader."""
    workflows = load_workflows()
    assert "rework" in workflows


def test_rework_workflow_has_expected_task_names(real_builtin_workflows: None) -> None:
    """The rework workflow task list includes the required steps."""
    workflows = load_workflows()
    wf = workflows["rework"]
    task_names = [t.name for t in wf.tasks]

    assert "resolve_rework_context" in task_names
    assert "agent" in task_names
    assert "format" in task_names
    assert "lint" in task_names
    assert "typecheck" in task_names
    assert "test" in task_names
    assert "commit" in task_names
    assert "push_branch" in task_names


def test_rework_workflow_starts_with_resolve(real_builtin_workflows: None) -> None:
    """resolve_rework_context runs before any other task."""
    workflows = load_workflows()
    wf = workflows["rework"]
    assert wf.tasks[0].name == "resolve_rework_context"


def test_rework_workflow_agent_uses_max_effort(real_builtin_workflows: None) -> None:
    """The rework AgentTask must request Claude Code's max effort level."""
    workflows = load_workflows()
    wf = workflows["rework"]
    agent_tasks = [t for t in wf.tasks if isinstance(t, AgentTask)]
    assert len(agent_tasks) == 1
    assert agent_tasks[0].effort_level == "max"


def test_rework_workflow_skips_sdlc_steps(real_builtin_workflows: None) -> None:
    """The rework workflow must NOT include ensure_worktree, set_status, create_pr."""
    workflows = load_workflows()
    wf = workflows["rework"]
    task_names = {t.name for t in wf.tasks}

    assert "ensure_worktree" not in task_names
    assert "set_status" not in task_names
    assert "create_pr" not in task_names


def test_rework_workflow_commit_message_format(real_builtin_workflows: None) -> None:
    """The commit task uses the rework-specific message template."""
    workflows = load_workflows()
    wf = workflows["rework"]
    commit_tasks = [
        t for t in wf.tasks if isinstance(t, BuiltIn) and t.name == "commit"
    ]

    assert len(commit_tasks) == 1
    assert (
        commit_tasks[0].kwargs.get("message")
        == "chore(prd): {prd_id} address review feedback"
    )


def test_rework_workflow_ends_with_reply(real_builtin_workflows: None) -> None:
    """The last task in the rework workflow is reply_pr_comments."""
    workflows = load_workflows()
    wf = workflows["rework"]
    assert wf.tasks[-1].name == "reply_pr_comments"


def test_rework_workflow_has_push_branch(real_builtin_workflows: None) -> None:
    """The rework workflow includes push_branch before reply_pr_comments."""
    workflows = load_workflows()
    wf = workflows["rework"]
    names = [t.name for t in wf.tasks]
    assert "push_branch" in names
    push_idx = names.index("push_branch")
    reply_idx = names.index("reply_pr_comments")
    assert push_idx < reply_idx


def test_rework_workflow_has_no_legacy_fetch_pr_comments(
    real_builtin_workflows: None,
) -> None:
    """The legacy fetch_pr_comments task is gone — resolve_rework_context handles it."""
    workflows = load_workflows()
    wf = workflows["rework"]
    task_names = [t.name for t in wf.tasks]
    assert "fetch_pr_comments" not in task_names


# ---------- run_workflow rework integration ----------


def _make_prd(tmp_path: Path, prd_id: str = "PRD-001") -> object:
    from darkfactory.model import load_all

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    prds_dir = data_dir / "prds"
    prds_dir.mkdir(exist_ok=True)
    write_prd(prds_dir, prd_id, "my-feature", status="review")
    return load_all(data_dir)[prd_id]


def _make_rework_workflow(tmp_path: Path) -> Workflow:
    """Create a minimal rework-shaped workflow for integration tests."""
    wf_dir = tmp_path / "rework"
    wf_dir.mkdir()
    prompts_dir = wf_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "role.md").write_text("# Role\n")
    (prompts_dir / "task.md").write_text("# Task\n{{REWORK_FEEDBACK}}\n")

    return Workflow(
        name="rework",
        tasks=[
            BuiltIn("resolve_rework_context"),
            AgentTask(
                name="agent",
                prompts=["prompts/role.md", "prompts/task.md"],
            ),
            BuiltIn(
                "commit",
                kwargs={"message": "chore(prd): {prd_id} address review feedback"},
            ),
            BuiltIn("push_branch"),
        ],
        workflow_dir=wf_dir,
    )


def test_run_workflow_applies_context_overrides(tmp_path: Path) -> None:
    """context_overrides values appear on the ExecutionContext for every task."""
    from darkfactory.utils.claude_code import InvokeResult
    from darkfactory.engine import ReworkState

    prd = _make_prd(tmp_path)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    threads = [_thread()]

    captured_ctx: list[ExecutionContext] = []

    def _fake_builtin(ctx: ExecutionContext, **kwargs: object) -> None:
        captured_ctx.append(ctx)

    fake_invoke = InvokeResult(
        stdout="PRD_EXECUTE_OK: PRD-001\n",
        stderr="",
        exit_code=0,
        success=True,
        failure_reason=None,
    )

    rework_state = ReworkState(
        pr_number=42,
        review_threads=threads,
    )

    from darkfactory.builtins._registry import BUILTINS

    with (
        patch.dict(
            BUILTINS,
            {
                "resolve_rework_context": _fake_builtin,
                "commit": _fake_builtin,
                "push_branch": _fake_builtin,
            },
        ),
        patch("darkfactory.runner.invoke_claude", return_value=fake_invoke),
    ):
        result = run_workflow(
            prd,  # type: ignore[arg-type]
            _make_rework_workflow(tmp_path),
            tmp_path,
            "main",
            dry_run=False,
            context_overrides={
                "worktree_path": worktree,
                "cwd": worktree,
            },
            phase_state_init=[rework_state],
        )

    assert result.success
    assert captured_ctx[0].state.get(ReworkState).review_threads == threads
    assert captured_ctx[0].state.get(ReworkState).pr_number == 42
    assert captured_ctx[0].worktree_path == worktree
    assert captured_ctx[0].cwd == worktree


def test_run_workflow_rejects_unknown_override_key(tmp_path: Path) -> None:
    """Unknown context_overrides keys raise ValueError instead of silently dropping."""
    prd = _make_prd(tmp_path)
    with pytest.raises(ValueError, match="unknown ExecutionContext field"):
        run_workflow(
            prd,  # type: ignore[arg-type]
            _make_rework_workflow(tmp_path),
            tmp_path,
            "main",
            dry_run=True,
            context_overrides={"not_a_real_field": "value"},
        )


def test_run_workflow_commit_message_uses_prd_id(tmp_path: Path) -> None:
    """The commit message for rework is formatted with the PRD id."""
    from darkfactory.engine import ReworkState

    prd = _make_prd(tmp_path, "PRD-007")
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    threads = [_thread()]

    commit_messages: list[str] = []

    def _fake_commit(ctx: ExecutionContext, *, message: str) -> None:
        commit_messages.append(ctx.format_string(message))

    from darkfactory.utils.claude_code import InvokeResult

    fake_invoke = InvokeResult(
        stdout="PRD_EXECUTE_OK: PRD-007\n",
        stderr="",
        exit_code=0,
        success=True,
        failure_reason=None,
    )

    rework_state = ReworkState(
        pr_number=42,
        review_threads=threads,
    )

    from darkfactory.builtins._registry import BUILTINS

    with (
        patch.dict(
            BUILTINS,
            {
                "resolve_rework_context": lambda ctx, **kw: None,
                "commit": _fake_commit,
                "push_branch": lambda ctx, **kw: None,
            },
        ),
        patch("darkfactory.runner.invoke_claude", return_value=fake_invoke),
    ):
        run_workflow(
            prd,  # type: ignore[arg-type]
            _make_rework_workflow(tmp_path),
            tmp_path,
            "main",
            dry_run=False,
            context_overrides={
                "worktree_path": worktree,
                "cwd": worktree,
            },
            phase_state_init=[rework_state],
        )

    assert commit_messages == ["chore(prd): PRD-007 address review feedback"]

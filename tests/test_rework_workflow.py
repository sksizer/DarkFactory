"""Tests for the rework workflow definition and execution.

Covers:
- Workflow loads correctly from the built-in workflows directory.
- Task sequence: no ensure_worktree / set_status / create_pr steps.
- Commit message format.
- fetch_pr_comments builtin no-op when threads pre-loaded.
- No comments found → cmd_rework early exit with message.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from darkfactory.loader import load_workflows
from darkfactory.pr_comments import ReviewThread
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

    assert "fetch_pr_comments" in task_names
    assert "agent" in task_names
    assert "format" in task_names
    assert "lint" in task_names
    assert "typecheck" in task_names
    assert "test" in task_names
    assert "commit" in task_names
    assert "push_branch" in task_names


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


# ---------- fetch_pr_comments builtin ----------


def test_fetch_pr_comments_builtin_noop_when_preloaded(tmp_path: Path) -> None:
    """The builtin is a no-op when ctx.review_threads is already populated."""
    from darkfactory.builtins.fetch_pr_comments import fetch_pr_comments as builtin_fn
    from darkfactory.prd import load_all

    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")
    prd = load_all(prds_dir)["PRD-001"]

    threads = [_thread()]
    ctx = ExecutionContext(
        prd=prd,
        repo_root=tmp_path,
        workflow=Workflow(name="rework", tasks=[]),
        base_ref="main",
        branch_name="prd/PRD-001-my-feature",
        review_threads=threads,
        dry_run=True,
    )

    # Should not call gh at all — threads already loaded
    with patch("darkfactory.pr_comments.fetch_pr_comments") as mock_fetch:
        builtin_fn(ctx)
        mock_fetch.assert_not_called()

    assert ctx.review_threads is threads  # unchanged


def test_fetch_pr_comments_builtin_dry_run_sets_empty_threads(tmp_path: Path) -> None:
    """In dry-run with no pre-loaded threads, builtin sets review_threads to []."""
    from darkfactory.builtins.fetch_pr_comments import fetch_pr_comments as builtin_fn
    from darkfactory.prd import load_all

    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")
    prd = load_all(prds_dir)["PRD-001"]

    ctx = ExecutionContext(
        prd=prd,
        repo_root=tmp_path,
        workflow=Workflow(name="rework", tasks=[]),
        base_ref="main",
        branch_name="prd/PRD-001-my-feature",
        pr_number=42,
        review_threads=None,
        dry_run=True,
    )

    builtin_fn(ctx)
    assert ctx.review_threads == []


def test_fetch_pr_comments_builtin_fetches_when_pr_number_set(tmp_path: Path) -> None:
    """When pr_number is set and threads not pre-loaded, builtin fetches threads."""
    from darkfactory.builtins.fetch_pr_comments import fetch_pr_comments as builtin_fn
    from darkfactory.prd import load_all

    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")
    prd = load_all(prds_dir)["PRD-001"]

    ctx = ExecutionContext(
        prd=prd,
        repo_root=tmp_path,
        workflow=Workflow(name="rework", tasks=[]),
        base_ref="main",
        branch_name="prd/PRD-001-my-feature",
        pr_number=42,
        review_threads=None,
        dry_run=False,
    )

    fetched = [_thread()]
    with patch(
        "darkfactory.pr_comments.fetch_pr_comments", return_value=fetched
    ) as mock_fetch:
        builtin_fn(ctx)
        # Verify called with the pr_number; filters may vary
        assert mock_fetch.call_count == 1
        assert mock_fetch.call_args.args[0] == 42

    assert ctx.review_threads == fetched


def test_fetch_pr_comments_builtin_raises_without_pr_number(tmp_path: Path) -> None:
    """Without pr_number or pre-loaded threads in live mode, raise RuntimeError."""
    from darkfactory.builtins.fetch_pr_comments import fetch_pr_comments as builtin_fn
    from darkfactory.prd import load_all

    prds_dir = tmp_path / "prds"
    prds_dir.mkdir()
    write_prd(prds_dir, "PRD-001", "my-feature", status="review")
    prd = load_all(prds_dir)["PRD-001"]

    ctx = ExecutionContext(
        prd=prd,
        repo_root=tmp_path,
        workflow=Workflow(name="rework", tasks=[]),
        base_ref="main",
        branch_name="prd/PRD-001-my-feature",
        pr_number=None,
        review_threads=None,
        dry_run=False,
    )

    with pytest.raises(RuntimeError, match="pr_number must be set"):
        builtin_fn(ctx)


# ---------- run_workflow rework integration ----------


def _make_prd(tmp_path: Path, prd_id: str = "PRD-001") -> object:
    from darkfactory.prd import load_all

    prds_dir = tmp_path / "prds"
    prds_dir.mkdir(exist_ok=True)
    write_prd(prds_dir, prd_id, "my-feature", status="review")
    return load_all(prds_dir)[prd_id]


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
            BuiltIn("fetch_pr_comments"),
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


def test_run_workflow_passes_review_threads_to_context(tmp_path: Path) -> None:
    """review_threads passed to run_workflow appear on ExecutionContext."""
    from darkfactory.invoke import InvokeResult

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

    from darkfactory.builtins._registry import BUILTINS

    with (
        patch.dict(
            BUILTINS,
            {
                "fetch_pr_comments": _fake_builtin,
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
            initial_worktree_path=worktree,
            initial_pr_number=42,
            initial_review_threads=threads,
        )

    assert result.success
    assert captured_ctx[0].review_threads == threads
    assert captured_ctx[0].pr_number == 42
    assert captured_ctx[0].worktree_path == worktree
    assert captured_ctx[0].cwd == worktree


def test_run_workflow_commit_message_uses_prd_id(tmp_path: Path) -> None:
    """The commit message for rework is formatted with the PRD id."""
    prd = _make_prd(tmp_path, "PRD-007")
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    threads = [_thread()]

    commit_messages: list[str] = []

    def _fake_commit(ctx: ExecutionContext, *, message: str) -> None:
        commit_messages.append(ctx.format_string(message))

    from darkfactory.invoke import InvokeResult

    fake_invoke = InvokeResult(
        stdout="PRD_EXECUTE_OK: PRD-007\n",
        stderr="",
        exit_code=0,
        success=True,
        failure_reason=None,
    )

    from darkfactory.builtins._registry import BUILTINS

    with (
        patch.dict(
            BUILTINS,
            {
                "fetch_pr_comments": lambda ctx, **kw: None,
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
            initial_worktree_path=worktree,
            initial_pr_number=42,
            initial_review_threads=threads,
        )

    assert commit_messages == ["chore(prd): PRD-007 address review feedback"]

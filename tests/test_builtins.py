"""Tests for the real builtin implementations.

Split into three categories:

1. **Registry tests**: the @builtin decorator and BUILTINS dict still
   work as they did in the stub phase.
2. **Pure helper tests**: `_worktree_target`, `_extract_acceptance_criteria`,
   `_pr_body` are unit-testable without any I/O.
3. **Subprocess-touching tests**: use ``tmp_path`` + ``git init`` for a
   real tmp repo (for worktree + commit flows) or ``unittest.mock.patch``
   for ``push_branch`` and ``create_pr`` (since those hit origin/gh).

Dry-run mode is tested throughout to confirm builtins log but don't
execute.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from prd_harness import builtins
from prd_harness.builtins import (
    BUILTINS,
    _extract_acceptance_criteria,
    _pr_body,
    _worktree_target,
    builtin,
)
from prd_harness.prd import load_all
from prd_harness.workflow import ExecutionContext, Workflow

from .conftest import write_prd


# ---------- registry ----------


def test_registry_populated_at_import() -> None:
    expected = {
        "ensure_worktree",
        "set_status",
        "commit",
        "push_branch",
        "create_pr",
        "cleanup_worktree",
    }
    assert expected <= set(BUILTINS.keys())


def test_each_builtin_is_callable() -> None:
    for name, func in BUILTINS.items():
        assert callable(func), f"{name!r} is not callable"


def test_builtin_decorator_registers_function() -> None:
    @builtin("_test_dynamic_one")
    def _noop(ctx):  # type: ignore[no-untyped-def]
        return None

    assert "_test_dynamic_one" in BUILTINS
    assert BUILTINS["_test_dynamic_one"] is _noop
    del BUILTINS["_test_dynamic_one"]


def test_builtin_decorator_rejects_duplicates() -> None:
    @builtin("_test_dynamic_two")
    def _first(ctx):  # type: ignore[no-untyped-def]
        return None

    try:
        with pytest.raises(ValueError, match="duplicate builtin"):

            @builtin("_test_dynamic_two")
            def _second(ctx):  # type: ignore[no-untyped-def]
                return None

    finally:
        del BUILTINS["_test_dynamic_two"]


# ---------- pure helpers ----------


def test_worktree_target(tmp_path: Path) -> None:
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "my-task")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_path,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-my-task",
    )
    target = _worktree_target(ctx)
    assert target == tmp_path / ".worktrees" / "PRD-070-my-task"


def test_extract_acceptance_criteria_basic() -> None:
    body = """
## Acceptance Criteria

- [ ] AC-1: the widget exists
- [ ] AC-2: the widget does thing
- [ ] AC-3: the widget handles edge case
"""
    acs = _extract_acceptance_criteria(body)
    assert len(acs) == 3
    assert "AC-1: the widget exists" in acs
    assert "AC-2: the widget does thing" in acs


def test_extract_acceptance_criteria_with_indent() -> None:
    """Indented AC lines should still match."""
    body = "  - [ ] AC-1: indented\n- [ ] AC-2: not indented\n"
    acs = _extract_acceptance_criteria(body)
    assert len(acs) == 2


def test_extract_acceptance_criteria_ignores_non_ac_checkboxes() -> None:
    """Only lines matching the AC-N pattern should be picked up."""
    body = """
- [ ] AC-1: this one counts
- [ ] Not an AC-formatted line
- [ ] AC-2: this one too
"""
    acs = _extract_acceptance_criteria(body)
    assert len(acs) == 2


def test_extract_acceptance_criteria_ignores_checked() -> None:
    """Already-completed ACs ([x]) should not be extracted — only open ones."""
    body = "- [x] AC-1: already done\n- [ ] AC-2: still open\n"
    acs = _extract_acceptance_criteria(body)
    assert len(acs) == 1
    assert "AC-2" in acs[0]


def test_pr_body_includes_prd_path_and_acs(tmp_path: Path) -> None:
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(
        prd_dir,
        "PRD-070",
        "my-task",
        body="# Title\n\n## Acceptance Criteria\n\n- [ ] AC-1: test it\n",
    )
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_path,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-my-task",
    )
    body = _pr_body(ctx)
    assert "prds/PRD-070-my-task.md" in body
    assert "AC-1: test it" in body
    assert "default" in body  # workflow name in footer


# ---------- dry-run behavior ----------


def _make_dry_run_ctx(tmp_path: Path) -> ExecutionContext:
    """Build an ExecutionContext with dry_run=True for safe testing."""
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "task")
    prds = load_all(prd_dir)

    return ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_path,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-task",
        cwd=tmp_path,
        dry_run=True,
    )


def test_dry_run_ensure_worktree_logs_and_returns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ctx = _make_dry_run_ctx(tmp_path)
    with caplog.at_level(logging.INFO, logger="prd_harness"):
        builtins.ensure_worktree(ctx)
    # Should not have actually created a worktree
    assert not (tmp_path / ".worktrees" / "PRD-070-task").exists()
    # But should have set the target path on ctx
    assert ctx.worktree_path == tmp_path / ".worktrees" / "PRD-070-task"
    # And logged the command
    assert any("git" in rec.message for rec in caplog.records)


def test_dry_run_set_status_does_not_mutate(tmp_path: Path) -> None:
    ctx = _make_dry_run_ctx(tmp_path)
    original_status = ctx.prd.status
    builtins.set_status(ctx, to="in-progress")
    # File should be untouched
    reloaded = load_all(tmp_path / "prds")
    assert reloaded["PRD-070"].status == original_status


def test_dry_run_commit_does_not_subprocess(tmp_path: Path) -> None:
    ctx = _make_dry_run_ctx(tmp_path)
    with patch("subprocess.run") as mock_run:
        builtins.commit(ctx, message="chore(prd): {prd_id} dry")
        mock_run.assert_not_called()


def test_dry_run_push_does_not_subprocess(tmp_path: Path) -> None:
    ctx = _make_dry_run_ctx(tmp_path)
    with patch("subprocess.run") as mock_run:
        builtins.push_branch(ctx)
        mock_run.assert_not_called()


def test_dry_run_create_pr_does_not_subprocess(tmp_path: Path) -> None:
    ctx = _make_dry_run_ctx(tmp_path)
    with patch("subprocess.run") as mock_run:
        builtins.create_pr(ctx)
        mock_run.assert_not_called()
    # But should set a placeholder pr_url
    assert ctx.pr_url is not None


# ---------- real git operations (tmp repo fixtures) ----------


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Initialize a bare-bones git repo with an initial commit at tmp_path/repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("initial\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"],
        cwd=repo,
        check=True,
    )
    return repo


def test_ensure_worktree_creates_worktree(tmp_git_repo: Path) -> None:
    """A real git repo should get a real worktree directory + branch."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "wt-test")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-wt-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )

    builtins.ensure_worktree(ctx)

    expected = tmp_git_repo / ".worktrees" / "PRD-070-wt-test"
    assert expected.exists()
    assert (expected / ".git").exists()  # worktree marker file
    assert ctx.worktree_path == expected
    assert ctx.cwd == expected


def test_ensure_worktree_resumes_existing(tmp_git_repo: Path) -> None:
    """Second call to ensure_worktree with same PRD should reuse, not re-create."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "resume-test")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-resume-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    first_path = ctx.worktree_path
    assert first_path is not None

    # Touch a file in the worktree to prove we're reusing it
    (first_path / "marker.txt").write_text("first run\n")

    # Reset the context and call again
    ctx2 = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-resume-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx2)
    assert ctx2.worktree_path == first_path
    assert (first_path / "marker.txt").read_text() == "first run\n"


def test_commit_stages_and_commits(tmp_git_repo: Path) -> None:
    """commit() should git-add-all and commit a message inside the worktree."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "commit-test")
    prds = load_all(prd_dir)

    # Create the worktree first
    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-commit-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    assert ctx.worktree_path is not None

    # Add a change inside the worktree
    (ctx.worktree_path / "hello.txt").write_text("hi\n")

    # Commit via the builtin
    builtins.commit(ctx, message="chore(prd): {prd_id} add hello")

    # Verify there's a new commit
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=ctx.worktree_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "PRD-070 add hello" in log.stdout


def test_commit_noop_on_empty_diff(tmp_git_repo: Path) -> None:
    """commit() should not error when there's nothing staged."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "noop-test")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-noop-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)

    # No changes — calling commit should log and return cleanly
    builtins.commit(ctx, message="chore(prd): {prd_id} empty")
    # Nothing to assert except: no exception raised.


def test_cleanup_worktree_removes_existing(tmp_git_repo: Path) -> None:
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "cleanup-test")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-cleanup-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    assert ctx.worktree_path is not None
    assert ctx.worktree_path.exists()

    builtins.cleanup_worktree(ctx)
    assert not ctx.worktree_path.exists()


def test_cleanup_worktree_idempotent(tmp_path: Path) -> None:
    """Cleanup with no worktree path should log and return without erroring."""
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "task")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_path,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-task",
        worktree_path=None,
        dry_run=False,
    )
    builtins.cleanup_worktree(ctx)  # no exception


def test_set_status_mutates_frontmatter(tmp_path: Path) -> None:
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-070", "status-test", status="ready")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_path,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-status-test",
        dry_run=False,
    )
    builtins.set_status(ctx, to="in-progress")

    # Reload from disk and confirm
    reloaded = load_all(prd_dir)
    assert reloaded["PRD-070"].status == "in-progress"


# ---------- push_branch / create_pr (mocked subprocess) ----------


def test_push_branch_invokes_git_push(tmp_path: Path) -> None:
    ctx = _make_dry_run_ctx(tmp_path)
    ctx.dry_run = False

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="", stderr=""
        )
        builtins.push_branch(ctx)

    args, _ = mock_run.call_args
    cmd = args[0]
    assert cmd[:3] == ["git", "push", "-u"]
    assert "origin" in cmd
    assert ctx.branch_name in cmd


def test_create_pr_captures_url_from_stdout(tmp_path: Path) -> None:
    ctx = _make_dry_run_ctx(tmp_path)
    ctx.dry_run = False

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["gh"],
            returncode=0,
            stdout="https://github.com/owner/repo/pull/42\n",
            stderr="",
        )
        builtins.create_pr(ctx)

    assert ctx.pr_url == "https://github.com/owner/repo/pull/42"

    # The command should invoke `gh pr create --base --title --body-file`
    args, _ = mock_run.call_args
    cmd = args[0]
    assert cmd[0] == "gh"
    assert "pr" in cmd
    assert "create" in cmd
    assert "--base" in cmd
    assert "--title" in cmd
    assert "--body-file" in cmd

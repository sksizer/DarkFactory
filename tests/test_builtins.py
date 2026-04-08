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

from darkfactory import builtins
from darkfactory.builtins import (
    BUILTINS,
    _branch_exists_local,
    _branch_exists_remote,
    _extract_acceptance_criteria,
    _pr_body,
    _worktree_target,
    builtin,
)
from darkfactory.prd import load_all
from darkfactory.workflow import ExecutionContext, Workflow

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
    with caplog.at_level(logging.INFO, logger="darkfactory"):
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


def test_set_status_mutates_worktree_not_source(tmp_path: Path) -> None:
    """``set_status`` writes to the worktree copy of the PRD, not the
    source repo. Asserts the source PRD file is byte-identical after the
    call and the worktree copy carries the new status. This is the
    PRD-213 invariant: ``prd run`` never touches the source repo.
    """
    source = tmp_path / "source"
    worktree = tmp_path / "worktree"
    source_prds = source / "prds"
    worktree_prds = worktree / "prds"
    source_prds.mkdir(parents=True)
    worktree_prds.mkdir(parents=True)

    # Create the PRD in both trees with identical content.
    src_path = write_prd(source_prds, "PRD-070", "status-test", status="ready")
    wt_path = worktree_prds / src_path.name
    wt_path.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
    source_bytes_before = src_path.read_bytes()

    prds = load_all(source_prds)
    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=source,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-status-test",
        worktree_path=worktree,
        dry_run=False,
    )
    builtins.set_status(ctx, to="in-progress")

    # Source repo: byte-identical (the invariant).
    assert src_path.read_bytes() == source_bytes_before, (
        "set_status must not modify the source repo"
    )

    # Worktree: status updated.
    reloaded = load_all(worktree_prds)
    assert reloaded["PRD-070"].status == "in-progress"

    # In-memory PRD also reflects the new status.
    assert ctx.prd.status == "in-progress"


def test_set_status_requires_worktree(tmp_path: Path) -> None:
    """Calling ``set_status`` without a worktree path is a programming
    error — the workflow author forgot to put ``ensure_worktree`` first.
    """
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
        worktree_path=None,
        dry_run=False,
    )
    with pytest.raises(RuntimeError, match="worktree"):
        builtins.set_status(ctx, to="in-progress")


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


# ---------- branch-existence guard tests ----------


def test_ensure_worktree_errors_if_branch_exists_without_worktree(
    tmp_git_repo: Path,
) -> None:
    """AC-1 / AC-5: Second invocation (branch exists, worktree gone) raises RuntimeError."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-215", "guard-test")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-215"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-215-guard-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    # First invocation: creates worktree + branch.
    builtins.ensure_worktree(ctx)
    assert ctx.worktree_path is not None

    # Simulate worktree dir being gone (e.g. deleted manually or by another process).
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_git_repo),
            "worktree",
            "remove",
            "--force",
            str(ctx.worktree_path),
        ],
        check=True,
        capture_output=True,
    )
    assert not ctx.worktree_path.exists()

    # Second invocation: branch still exists, worktree gone → guard fires.
    ctx2 = ExecutionContext(
        prd=prds["PRD-215"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-215-guard-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    with pytest.raises(RuntimeError, match="already exists"):
        builtins.ensure_worktree(ctx2)


def test_ensure_worktree_errors_on_remote_branch(tmp_git_repo: Path) -> None:
    """AC-2: A fake remote branch (via update-ref) also triggers the guard."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-215", "remote-guard")
    prds = load_all(prd_dir)

    branch = "prd/PRD-215-remote-guard"

    # Simulate a remote-tracking ref without a local branch or worktree.
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_git_repo),
            "update-ref",
            f"refs/remotes/origin/{branch}",
            "HEAD",
        ],
        check=True,
        capture_output=True,
    )

    ctx = ExecutionContext(
        prd=prds["PRD-215"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name=branch,
        cwd=tmp_git_repo,
        dry_run=False,
    )

    # Patch _branch_exists_remote to simulate ls-remote finding the branch.
    with patch("darkfactory.builtins._branch_exists_remote", return_value=True):
        with pytest.raises(RuntimeError, match="already exists"):
            builtins.ensure_worktree(ctx)


def test_ensure_worktree_resumes_when_both_branch_and_worktree_exist(
    tmp_git_repo: Path,
) -> None:
    """AC-3: Resuming (worktree dir exists, branch exists) works as before."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-215", "resume-guard")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-215"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-215-resume-guard",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    first_path = ctx.worktree_path
    assert first_path is not None and first_path.exists()

    # Second call with same branch + existing worktree: should resume, not error.
    ctx2 = ExecutionContext(
        prd=prds["PRD-215"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-215-resume-guard",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx2)  # Must not raise
    assert ctx2.worktree_path == first_path


def test_ensure_worktree_remote_timeout_falls_back_to_local(
    tmp_git_repo: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-4: When git ls-remote times out, guard falls back to local check and logs warning."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-215", "timeout-test")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-215"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-215-timeout-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )

    # Simulate ls-remote timeout — worktree and local branch don't exist,
    # so the guard should not fire despite the timeout.
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if "ls-remote" in cmd:
            raise subprocess.TimeoutExpired(cmd, 10)
        return original_run(cmd, **kwargs)

    with caplog.at_level(logging.WARNING, logger="darkfactory"):
        with patch("darkfactory.builtins.subprocess.run", side_effect=fake_run):
            builtins.ensure_worktree(ctx)

    assert ctx.worktree_path is not None
    assert any("timed out" in rec.message for rec in caplog.records)


def test_branch_exists_local_true(tmp_git_repo: Path) -> None:
    """_branch_exists_local returns True when the branch exists."""
    subprocess.run(
        ["git", "-C", str(tmp_git_repo), "branch", "test-local-branch"],
        check=True,
        capture_output=True,
    )
    assert _branch_exists_local(tmp_git_repo, "test-local-branch") is True


def test_branch_exists_local_false(tmp_git_repo: Path) -> None:
    """_branch_exists_local returns False when the branch does not exist."""
    assert _branch_exists_local(tmp_git_repo, "no-such-branch-xyz") is False


def test_branch_exists_remote_timeout_returns_false(
    tmp_git_repo: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-4: _branch_exists_remote returns False and logs a warning on timeout."""
    timeout_exc = subprocess.TimeoutExpired(["git"], 10)
    with caplog.at_level(logging.WARNING, logger="darkfactory"):
        with patch("darkfactory.builtins.subprocess.run", side_effect=timeout_exc):
            result = _branch_exists_remote(tmp_git_repo, "prd/PRD-215-some-branch")

    assert result is False
    assert any("timed out" in rec.message for rec in caplog.records)


def test_ensure_worktree_guard_stubbed_subprocess(tmp_path: Path) -> None:
    """AC-5: Stubs subprocess.run to simulate branch-exists case and asserts the error."""
    prd_dir = tmp_path / "prds"
    prd_dir.mkdir()
    write_prd(prd_dir, "PRD-215", "stub-test")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-215"],
        repo_root=tmp_path,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-215-stub-test",
        cwd=tmp_path,
        dry_run=False,
    )

    # Patch helpers directly: local branch exists, no worktree on disk.
    with patch("darkfactory.builtins._branch_exists_local", return_value=True):
        with patch("darkfactory.builtins._branch_exists_remote", return_value=False):
            with pytest.raises(RuntimeError, match="already exists"):
                builtins.ensure_worktree(ctx)

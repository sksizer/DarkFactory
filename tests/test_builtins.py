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
    _extract_acceptance_criteria,
    _pr_body,
    builtin,
)
from darkfactory.builtins.ensure_worktree import (
    _branch_exists_local,
    _branch_exists_remote,
    _worktree_target,
)
from darkfactory.checks import ResumeStatus
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
        "summarize_agent_run",
        "commit_transcript",
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

    # Release the lock so the second context can acquire it (simulating
    # a new process that resumes an interrupted run).
    assert ctx._worktree_lock is not None
    ctx._worktree_lock.release()
    ctx._worktree_lock = None

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
    # Release the lock acquired by ctx2 to avoid leaking it after the test.
    if ctx2._worktree_lock is not None:
        ctx2._worktree_lock.release()
        ctx2._worktree_lock = None


def test_ensure_worktree_raises_on_merged_pr(tmp_git_repo: Path) -> None:
    """ensure_worktree should raise RuntimeError when is_resume_safe returns not-safe (merged)."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "stale-test")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-stale-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    # Create the worktree first so the resume path is taken
    builtins.ensure_worktree(ctx)
    assert ctx.worktree_path is not None
    assert ctx._worktree_lock is not None
    ctx._worktree_lock.release()
    ctx._worktree_lock = None

    not_safe = ResumeStatus(
        safe=False,
        reason="PR for prd/PRD-070-stale-test is merged; run `prd cleanup` to start fresh",
        kind="pr_merged",
    )
    ctx2 = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-stale-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    with patch(
        "darkfactory.builtins.ensure_worktree.is_resume_safe", return_value=not_safe
    ):
        with pytest.raises(RuntimeError, match="prd cleanup"):
            builtins.ensure_worktree(ctx2)


def test_ensure_worktree_raises_on_closed_pr(tmp_git_repo: Path) -> None:
    """ensure_worktree should raise RuntimeError when is_resume_safe returns not-safe (closed)."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-071", "closed-test")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-071"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-071-closed-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    assert ctx._worktree_lock is not None
    ctx._worktree_lock.release()
    ctx._worktree_lock = None

    not_safe = ResumeStatus(
        safe=False,
        reason="PR for prd/PRD-071-closed-test is closed; run `prd cleanup` to start fresh",
        kind="pr_closed",
    )
    ctx2 = ExecutionContext(
        prd=prds["PRD-071"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-071-closed-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    with patch(
        "darkfactory.builtins.ensure_worktree.is_resume_safe", return_value=not_safe
    ):
        with pytest.raises(RuntimeError, match="prd cleanup"):
            builtins.ensure_worktree(ctx2)


def test_ensure_worktree_resumes_when_safe(tmp_git_repo: Path) -> None:
    """ensure_worktree should proceed when is_resume_safe returns safe."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-072", "safe-resume-test")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-072"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-072-safe-resume-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    assert ctx._worktree_lock is not None
    ctx._worktree_lock.release()
    ctx._worktree_lock = None

    safe = ResumeStatus(safe=True, reason="", kind="safe")
    ctx2 = ExecutionContext(
        prd=prds["PRD-072"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-072-safe-resume-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    with patch(
        "darkfactory.builtins.ensure_worktree.is_resume_safe", return_value=safe
    ):
        builtins.ensure_worktree(ctx2)

    assert ctx2.worktree_path is not None
    if ctx2._worktree_lock is not None:
        ctx2._worktree_lock.release()
        ctx2._worktree_lock = None


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


def test_lint_attribution_rejects_claude_trailer_in_commit(tmp_git_repo: Path) -> None:
    """lint_attribution should raise when a branch commit credits Claude."""
    import pytest

    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "lint-attr")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-lint-attr",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    assert ctx.worktree_path is not None
    (ctx.worktree_path / "x.txt").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=ctx.worktree_path, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "feat: do a thing\n\nCo-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>",
        ],
        cwd=ctx.worktree_path,
        check=True,
        capture_output=True,
    )

    with pytest.raises(RuntimeError, match="forbidden attribution pattern"):
        builtins.lint_attribution(ctx)


def test_lint_attribution_clean_branch_passes(tmp_git_repo: Path) -> None:
    """lint_attribution is a no-op when no commits credit Claude/Anthropic."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "lint-clean")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-lint-clean",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    assert ctx.worktree_path is not None
    (ctx.worktree_path / "x.txt").write_text("x\n")
    builtins.commit(ctx, message="chore(prd): {prd_id} clean commit")

    # Should not raise.
    builtins.lint_attribution(ctx)


def test_commit_rejects_forbidden_attribution(tmp_git_repo: Path) -> None:
    """commit() itself should refuse a message that credits Claude."""
    import pytest

    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "commit-guard")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-commit-guard",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    assert ctx.worktree_path is not None
    (ctx.worktree_path / "x.txt").write_text("x\n")

    with pytest.raises(RuntimeError, match="forbidden attribution pattern"):
        builtins.commit(
            ctx,
            message="chore: fix\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
        )


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

    # Release the lock so the second context can proceed past the lock
    # (simulating that the first runner finished or was interrupted).
    assert ctx._worktree_lock is not None
    ctx._worktree_lock.release()
    ctx._worktree_lock = None

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
    with patch(
        "darkfactory.builtins.ensure_worktree._branch_exists_remote", return_value=True
    ):
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

    # Release the lock so the second context can acquire it (simulating
    # a new process that resumes the run).
    assert ctx._worktree_lock is not None
    ctx._worktree_lock.release()
    ctx._worktree_lock = None

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
    # Release lock to avoid leaking it after the test.
    if ctx2._worktree_lock is not None:
        ctx2._worktree_lock.release()
        ctx2._worktree_lock = None


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

    from typing import Any

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        cmd = args[0] if args else kwargs.get("args")
        if isinstance(cmd, list) and "ls-remote" in cmd:
            raise subprocess.TimeoutExpired(cmd, 10)
        return original_run(*args, **kwargs)

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
    with patch(
        "darkfactory.builtins.ensure_worktree._branch_exists_local", return_value=True
    ):
        with patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_remote",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="already exists"):
                builtins.ensure_worktree(ctx)


# ---------- process lock ----------


def test_ensure_worktree_acquires_lock(tmp_git_repo: Path) -> None:
    """AC-1/AC-8: After ensure_worktree, ctx._worktree_lock is set and lock file exists."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-217", "lock-acquire")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-217"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-217-lock-acquire",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)

    assert ctx._worktree_lock is not None
    lock_path = tmp_git_repo / ".worktrees" / "PRD-217.lock"
    assert lock_path.exists()

    # Cleanup
    ctx._worktree_lock.release()
    ctx._worktree_lock = None


def test_ensure_worktree_refuses_when_locked(tmp_git_repo: Path) -> None:
    """AC-1: A second concurrent call raises RuntimeError naming the lock file."""
    from filelock import FileLock as _FileLock

    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-217", "lock-refuse")
    prds = load_all(prd_dir)

    lock_path = tmp_git_repo / ".worktrees" / "PRD-217.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Hold the lock externally to simulate another process.
    external_lock = _FileLock(str(lock_path))
    external_lock.acquire()
    try:
        ctx = ExecutionContext(
            prd=prds["PRD-217"],
            repo_root=tmp_git_repo,
            workflow=Workflow(name="default"),
            base_ref="main",
            branch_name="prd/PRD-217-lock-refuse",
            cwd=tmp_git_repo,
            dry_run=False,
        )
        with pytest.raises(RuntimeError, match="already being worked on"):
            builtins.ensure_worktree(ctx)
        # Context should not have a lock set since acquisition failed.
        assert ctx._worktree_lock is None
    finally:
        external_lock.release()


def test_ensure_worktree_dry_run_no_lock(tmp_path: Path) -> None:
    """AC-2/AC-6: Dry-run path does not create or acquire the lock."""
    ctx = _make_dry_run_ctx(tmp_path)
    builtins.ensure_worktree(ctx)

    assert ctx._worktree_lock is None
    lock_path = tmp_path / ".worktrees" / "PRD-070.lock"
    assert not lock_path.exists()


def test_ensure_worktree_releases_on_branch_guard_raise(tmp_git_repo: Path) -> None:
    """AC-4: When the branch-exists guard fires, lock is released before raising."""
    from filelock import FileLock as _FileLock

    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-217", "lock-guard")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-217"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-217-lock-guard",
        cwd=tmp_git_repo,
        dry_run=False,
    )

    with patch(
        "darkfactory.builtins.ensure_worktree._branch_exists_local", return_value=True
    ):
        with patch(
            "darkfactory.builtins.ensure_worktree._branch_exists_remote",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="already exists"):
                builtins.ensure_worktree(ctx)

    # Lock must be released — context should not hold it.
    assert ctx._worktree_lock is None

    # We should be able to acquire the lock immediately after the failed call.
    lock_path = tmp_git_repo / ".worktrees" / "PRD-217.lock"
    probe = _FileLock(str(lock_path))
    probe.acquire(timeout=0)  # raises Timeout if still locked
    probe.release()


def test_runner_releases_lock_on_success(tmp_git_repo: Path) -> None:
    """AC-5: run_workflow releases the lock on the context when the run completes."""
    from filelock import FileLock as _FileLock

    from darkfactory.runner import run_workflow
    from darkfactory.workflow import BuiltIn

    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-217", "runner-success")
    prds = load_all(prd_dir)

    wf = Workflow(name="default", tasks=[BuiltIn("ensure_worktree")])
    result = run_workflow(
        prds["PRD-217"], wf, tmp_git_repo, base_ref="main", dry_run=False
    )
    assert result.success is True

    # After run_workflow returns, the lock should be released.
    lock_path = tmp_git_repo / ".worktrees" / "PRD-217.lock"
    probe = _FileLock(str(lock_path))
    probe.acquire(timeout=0)
    probe.release()


def test_runner_releases_lock_on_exception(tmp_git_repo: Path) -> None:
    """AC-5: run_workflow releases the lock even when a task raises mid-run."""
    from filelock import FileLock as _FileLock

    from darkfactory.runner import run_workflow
    from darkfactory.workflow import BuiltIn, ShellTask

    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-217", "runner-exception")
    prds = load_all(prd_dir)

    # Workflow acquires the lock then immediately fails via a shell task.
    wf = Workflow(
        name="default",
        tasks=[
            BuiltIn("ensure_worktree"),
            ShellTask("fail", cmd="false", on_failure="fail"),
        ],
    )
    result = run_workflow(
        prds["PRD-217"], wf, tmp_git_repo, base_ref="main", dry_run=False
    )
    assert result.success is False

    # Lock must be released despite the failure.
    lock_path = tmp_git_repo / ".worktrees" / "PRD-217.lock"
    probe = _FileLock(str(lock_path))
    probe.acquire(timeout=0)
    probe.release()


def test_lock_auto_releases_on_subprocess_exit(tmp_path: Path) -> None:
    """AC-3: A lock held by a subprocess is released when that process exits."""
    import sys as _sys

    from filelock import FileLock as _FileLock

    lock_path = tmp_path / "auto-release.lock"

    # Launch a child process that acquires the lock and exits normally.
    child = subprocess.run(
        [
            _sys.executable,
            "-c",
            f"from filelock import FileLock; FileLock(r'{lock_path}').acquire()",
        ],
        timeout=10,
    )
    assert child.returncode == 0

    # After the child exits, the lock file handle is reclaimed by the kernel.
    # We must be able to acquire it immediately.
    probe = _FileLock(str(lock_path))
    probe.acquire(timeout=1)
    probe.release()


# ---------- summarize_agent_run ----------


def _make_ctx_with_invoke_result(
    tmp_path: Path,
    tool_counts: dict[str, int] | None = None,
    sentinel: str | None = None,
    model: str = "sonnet",
    invoke_count: int = 1,
) -> ExecutionContext:
    """Build a dry-run context with a populated last_invoke_result."""
    from darkfactory.invoke import InvokeResult

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
        cwd=tmp_path,
        dry_run=True,
        model=model,
        invoke_count=invoke_count,
    )
    ctx.last_invoke_result = InvokeResult(
        stdout="",
        stderr="",
        exit_code=0,
        success=True,
        tool_counts=tool_counts or {},
        sentinel=sentinel,
    )
    return ctx


def test_summarize_agent_run_registered() -> None:
    assert "summarize_agent_run" in BUILTINS


def test_summarize_agent_run_sets_run_summary(tmp_path: Path) -> None:
    ctx = _make_ctx_with_invoke_result(
        tmp_path,
        tool_counts={"Read": 3, "Edit": 2},
        sentinel="PRD-070",
        model="sonnet",
        invoke_count=1,
    )
    builtins.summarize_agent_run(ctx)

    assert ctx.run_summary is not None
    assert "## Harness execution summary" in ctx.run_summary
    assert "default" in ctx.run_summary  # workflow name
    assert "sonnet" in ctx.run_summary  # model
    assert "1" in ctx.run_summary  # invoke count
    assert "PRD-070" in ctx.run_summary  # sentinel
    assert "Read" in ctx.run_summary
    assert "Edit" in ctx.run_summary


def test_summarize_agent_run_no_result(tmp_path: Path) -> None:
    """With no last_invoke_result, summarize_agent_run should be a no-op."""
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
        dry_run=True,
    )
    builtins.summarize_agent_run(ctx)
    assert ctx.run_summary is None


def test_summarize_agent_run_empty_tool_counts(tmp_path: Path) -> None:
    ctx = _make_ctx_with_invoke_result(tmp_path, tool_counts={}, sentinel=None)
    builtins.summarize_agent_run(ctx)
    assert ctx.run_summary is not None
    assert "none" in ctx.run_summary  # tool counts: none


def test_create_pr_appends_run_summary(tmp_path: Path) -> None:
    """create_pr includes run_summary in the PR body when it is set."""
    ctx = _make_ctx_with_invoke_result(
        tmp_path, tool_counts={"Read": 2}, sentinel="PRD-070"
    )
    builtins.summarize_agent_run(ctx)
    assert ctx.run_summary is not None

    # Dry-run create_pr builds the body in-memory, so we capture what it
    # would pass to gh by intercepting _pr_body and checking the body used.
    # Easiest: call create_pr in dry-run mode and inspect run_summary was non-None.
    # For a non-dry-run path, we patch subprocess.run and read the body file.
    ctx.dry_run = False
    captured_body: list[str] = []

    original_run = subprocess.run

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(cmd, list) and "gh" in cmd:
            # Read the body file before it is deleted.
            for i, arg in enumerate(cmd):
                if arg == "--body-file" and i + 1 < len(cmd):
                    captured_body.append(Path(cmd[i + 1]).read_text(encoding="utf-8"))
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="https://github.com/owner/repo/pull/1\n",
                stderr="",
            )
        return original_run(cmd, **kwargs)

    with patch("darkfactory.builtins.subprocess.run", side_effect=fake_run):
        builtins.create_pr(ctx)

    assert len(captured_body) == 1
    body = captured_body[0]
    assert "## Harness execution summary" in body


def test_create_pr_without_run_summary_unchanged(tmp_path: Path) -> None:
    """create_pr without run_summary produces same body as before (no regression)."""
    ctx = _make_dry_run_ctx(tmp_path)
    ctx.dry_run = False

    captured_body: list[str] = []
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(cmd, list) and "gh" in cmd:
            for i, arg in enumerate(cmd):
                if arg == "--body-file" and i + 1 < len(cmd):
                    captured_body.append(Path(cmd[i + 1]).read_text(encoding="utf-8"))
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="https://github.com/owner/repo/pull/2\n",
                stderr="",
            )
        return original_run(cmd, **kwargs)

    with patch("darkfactory.builtins.subprocess.run", side_effect=fake_run):
        builtins.create_pr(ctx)

    assert len(captured_body) == 1
    body = captured_body[0]
    assert "## Harness execution summary" not in body


# ---------- commit_transcript ----------


def test_commit_transcript_registered() -> None:
    assert "commit_transcript" in BUILTINS


def test_commit_transcript_noop_when_no_transcript(tmp_path: Path) -> None:
    """AC-5: When no .harness-agent-output.log exists, commit_transcript is a no-op."""
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
        cwd=tmp_path,
        dry_run=False,
    )
    # Should not raise and should not create any transcript dir
    builtins.commit_transcript(ctx)
    assert not (tmp_path / ".darkfactory" / "transcripts").exists()


def test_commit_transcript_moves_and_stages(tmp_git_repo: Path) -> None:
    """AC-2/AC-3: commit_transcript moves transcript to .darkfactory/transcripts/ and stages it."""
    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "transcript-test")
    prds = load_all(prd_dir)

    # Set up a worktree (needed for a real git context)
    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-transcript-test",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    assert ctx.worktree_path is not None

    # Write a fake transcript at the expected source location
    src = ctx.cwd / ".harness-agent-output.log"
    src.write_text("# fake transcript\ncontent here\n", encoding="utf-8")

    builtins.commit_transcript(ctx)

    # Source should be gone
    assert not src.exists()

    # Destination should exist under .darkfactory/transcripts/
    transcript_dir = ctx.cwd / ".darkfactory" / "transcripts"
    assert transcript_dir.exists()
    logs = list(transcript_dir.glob("PRD-070-*.log"))
    assert len(logs) == 1
    assert logs[0].read_text(encoding="utf-8") == "# fake transcript\ncontent here\n"

    # File should be staged
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(ctx.cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    assert ".darkfactory/transcripts/" in result.stdout


def test_commit_transcript_multiple_invocations_separate_files(
    tmp_git_repo: Path,
) -> None:
    """AC-6: Multiple invocations produce separate timestamped files."""
    import time

    prd_dir = tmp_git_repo / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    write_prd(prd_dir, "PRD-070", "multi-transcript")
    prds = load_all(prd_dir)

    ctx = ExecutionContext(
        prd=prds["PRD-070"],
        repo_root=tmp_git_repo,
        workflow=Workflow(name="default"),
        base_ref="main",
        branch_name="prd/PRD-070-multi-transcript",
        cwd=tmp_git_repo,
        dry_run=False,
    )
    builtins.ensure_worktree(ctx)
    assert ctx.worktree_path is not None

    transcript_dir = ctx.cwd / ".darkfactory" / "transcripts"

    # First invocation
    src = ctx.cwd / ".harness-agent-output.log"
    src.write_text("first transcript\n", encoding="utf-8")
    builtins.commit_transcript(ctx)
    assert len(list(transcript_dir.glob("PRD-070-*.log"))) == 1

    # Wait a second so timestamps differ
    time.sleep(1)

    # Second invocation
    src.write_text("second transcript\n", encoding="utf-8")
    builtins.commit_transcript(ctx)

    logs = sorted(transcript_dir.glob("PRD-070-*.log"))
    assert len(logs) == 2, "Each invocation must produce a separate file"
    # Files should have different names (timestamps)
    assert logs[0].name != logs[1].name


def test_commit_transcript_dry_run_noop(tmp_path: Path) -> None:
    """In dry-run mode, commit_transcript logs but does not move or stage anything."""
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
        cwd=tmp_path,
        dry_run=True,
    )

    src = tmp_path / ".harness-agent-output.log"
    src.write_text("dry run transcript\n", encoding="utf-8")

    with patch("subprocess.run") as mock_run:
        builtins.commit_transcript(ctx)
        mock_run.assert_not_called()

    # Source file should remain untouched in dry-run
    assert src.exists()
    assert not (tmp_path / ".darkfactory" / "transcripts").exists()

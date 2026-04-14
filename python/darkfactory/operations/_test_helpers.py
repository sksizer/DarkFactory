"""Shared test helpers for darkfactory.operations peer test files.

Import ``make_builtin_ctx`` in any builtin ``*_test.py`` file to avoid
redefining the same ``_make_ctx`` boilerplate in every module.
"""

from __future__ import annotations

from pathlib import Path

from darkfactory.engine import CodeEnv, PrdWorkflowRun, WorktreeState
from darkfactory.model import PRD
from darkfactory.workflow import RunContext, Workflow


def _make_test_prd(
    prd_id: str = "PRD-001",
    slug: str = "test",
    title: str = "Test PRD",
    repo_root: Path | None = None,
) -> PRD:
    """Create a minimal PRD for testing."""
    root = repo_root or Path("/tmp")
    return PRD(
        id=prd_id,
        path=root / ".darkfactory" / "prds" / f"{prd_id}-{slug}.md",
        slug=slug,
        title=title,
        kind="task",
        status="ready",
        priority="medium",
        effort="s",
        capability="simple",
        parent=None,
        depends_on=[],
        blocks=[],
        impacts=[],
        workflow=None,
        assignee=None,
        reviewers=[],
        target_version=None,
        created="2026-04-06",
        updated="2026-04-06",
        tags=[],
        raw_frontmatter={},
        body="",
    )


def make_builtin_ctx(
    tmp_path: Path,
    *,
    dry_run: bool = False,
    prd_id: str = "PRD-001",
    branch_name: str = "prd/PRD-001-test",
    base_ref: str = "main",
    worktree_path: Path | None = None,
    repo_root: Path | None = None,
    event_writer: object = None,
) -> RunContext:
    """Build a ``RunContext`` with seeded payloads for builtin unit tests.

    Parameters
    ----------
    tmp_path:
        Temporary directory (from pytest's ``tmp_path`` fixture) used as
        ``cwd`` and, when ``repo_root`` is *None*, as ``repo_root``.
    dry_run:
        Value set on ``ctx.dry_run``.
    prd_id:
        PRD id for the PrdWorkflowRun payload.
    branch_name:
        Branch name for the WorktreeState payload.
    base_ref:
        Base ref for the WorktreeState payload.
    worktree_path:
        Worktree path for the WorktreeState payload. Defaults to ``None``.
    repo_root:
        Repository root for CodeEnv. Defaults to ``tmp_path``.
    event_writer:
        Value set on ``ctx.event_writer``. Defaults to ``None``.
    """
    effective_root = repo_root if repo_root is not None else tmp_path
    prd = _make_test_prd(prd_id=prd_id, repo_root=effective_root)

    ctx = RunContext(
        dry_run=dry_run,
        event_writer=event_writer,  # type: ignore[arg-type]
    )
    ctx.state.put(CodeEnv(repo_root=effective_root, cwd=tmp_path))
    ctx.state.put(PrdWorkflowRun(prd=prd, workflow=Workflow(name="test", tasks=[])))
    ctx.state.put(
        WorktreeState(
            branch=branch_name,
            base_ref=base_ref,
            worktree_path=worktree_path,
        )
    )
    return ctx

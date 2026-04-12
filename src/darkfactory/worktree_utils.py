"""Shared worktree discovery and management helpers.

Single source-of-truth for finding an active worktree path for a given PRD
and for worktree/branch removal operations shared across CLI commands.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from darkfactory.checks import StaleWorktree
from darkfactory.git_ops import git_check, git_run

# Re-export for backwards compatibility — cleanup.py imports checks directly
# but the type is used here too.
__all__ = [
    "find_worktree_for_prd",
    "find_stale_worktree_for_prd",
    "find_orphaned_branches",
    "remove_worktree",
]


def find_worktree_for_prd(prd_id: str, repo_root: Path) -> Path | None:
    """Find the worktree path for *prd_id*, or return ``None``.

    Two strategies are tried in order:

    **Strategy 1 — ``git worktree list --porcelain``** (primary):
    Reflects git's own registration of worktrees.  Handles worktrees in
    non-standard locations, but misses directories that git has forgotten
    (e.g. after a failed ``git worktree remove`` that left the directory
    behind without pruning the entry).

    **Strategy 2 — ``.worktrees/`` directory scan** (fallback):
    Matches by the ``PRD-NNN*`` naming convention used when worktrees are
    created by ``ensure_worktree``.  Catches directories git has forgotten,
    but misses worktrees registered outside ``.worktrees/`` (e.g. created
    manually with a custom path).

    Investigation finding (E3): the two existing callers — ``cli/cleanup.py``
    (directory scan) and ``cli/rework.py`` (``git worktree list``) — each
    handled the edge case the other missed.  This function preserves the
    union of both strategies.
    """
    # Strategy 1: git worktree list --porcelain
    try:
        result = git_run("worktree", "list", "--porcelain", cwd=repo_root)
        current_path: str | None = None
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                current_path = line[len("worktree ") :]
            elif line.startswith("branch "):
                branch_ref = line[len("branch ") :]
                branch = branch_ref.removeprefix("refs/heads/")
                if re.match(rf"^prd/{re.escape(prd_id)}-", branch):
                    return Path(current_path) if current_path else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Strategy 2: .worktrees/ directory scan
    worktrees_dir = repo_root / ".worktrees"
    if worktrees_dir.exists():
        for entry in sorted(worktrees_dir.iterdir()):
            if not entry.is_dir():
                continue
            m = re.match(r"^(PRD-[\d.]+)", entry.name)
            if m and m.group(1) == prd_id:
                return entry

    return None


def find_stale_worktree_for_prd(prd_id: str, repo_root: Path) -> StaleWorktree | None:
    """Find the worktree entry for *prd_id*, wrapped with PR state.

    Delegates path discovery to :func:`find_worktree_for_prd`, then wraps
    the result in a :class:`StaleWorktree` with PR state for cleanup/reset
    operations.
    """
    from darkfactory import checks

    entry = find_worktree_for_prd(prd_id, repo_root)
    if entry is None:
        return None
    branch = f"prd/{entry.name}"
    pr_state = checks._get_pr_state(branch, repo_root)
    return StaleWorktree(
        prd_id=prd_id,
        branch=branch,
        worktree_path=entry,
        pr_state=pr_state,
    )


def find_orphaned_branches(prd_id: str, repo_root: Path) -> list[str]:
    """Find local branches matching ``prd/{prd_id}-*`` (glob match).

    Returns all matching branch names (may be empty).
    """
    result = git_run("branch", "--list", f"prd/{prd_id}-*", cwd=repo_root)
    branches: list[str] = []
    for line in result.stdout.splitlines():
        branch = line.strip().lstrip("* ")
        if branch:
            branches.append(branch)
    return branches


def remove_worktree(worktree: StaleWorktree, repo_root: Path) -> None:
    """Remove a worktree directory and delete the local branch."""
    git_run("worktree", "remove", "--force", str(worktree.worktree_path), cwd=repo_root)
    git_check("branch", "-D", worktree.branch.removeprefix("prd/"), cwd=repo_root)

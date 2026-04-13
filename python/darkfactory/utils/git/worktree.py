"""Shared worktree discovery and management helpers.

Single source-of-truth for finding an active worktree path for a given PRD
and for worktree/branch removal operations shared across CLI commands.
"""

from __future__ import annotations

import re
from pathlib import Path

from darkfactory.checks import StaleWorktree
from darkfactory.utils.git._run import git_run
from darkfactory.utils.git._types import GitErr, Ok

__all__ = [
    "find_worktree_for_prd",
    "find_stale_worktree_for_prd",
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
    match git_run("worktree", "list", "--porcelain", cwd=repo_root):
        case Ok(stdout=output):
            current_path: str | None = None
            for line in output.splitlines():
                if line.startswith("worktree "):
                    current_path = line[len("worktree ") :]
                elif line.startswith("branch "):
                    branch_ref = line[len("branch ") :]
                    branch = branch_ref.removeprefix("refs/heads/")
                    if re.match(rf"^prd/{re.escape(prd_id)}-", branch):
                        return Path(current_path) if current_path else None
        case GitErr():
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


def _find_worktree_path_and_branch_for_prd(
    prd_id: str, repo_root: Path
) -> tuple[Path, str] | None:
    """Find a matching worktree path and branch from Git porcelain output.

    Uses ``git worktree list --porcelain`` so the authoritative branch name is
    preserved even when the worktree directory name does not match the branch
    suffix.
    """
    match git_run("worktree", "list", "--porcelain", cwd=repo_root):
        case Ok(stdout=output):
            pass
        case GitErr():
            return None

    worktree_path: Path | None = None
    branch_name: str | None = None

    for line in output.splitlines() + [""]:
        if not line:
            if (
                worktree_path is not None
                and branch_name is not None
                and re.fullmatch(rf"prd/{re.escape(prd_id)}-[^/]+", branch_name)
            ):
                return worktree_path, branch_name
            worktree_path = None
            branch_name = None
            continue

        if line.startswith("worktree "):
            worktree_path = Path(line.removeprefix("worktree ").strip())
        elif line.startswith("branch refs/heads/"):
            branch_name = line.removeprefix("branch refs/heads/").strip()

    return None


def find_stale_worktree_for_prd(prd_id: str, repo_root: Path) -> StaleWorktree | None:
    """Find the worktree entry for *prd_id*, wrapped with PR state.

    Prefers authoritative branch information from
    ``git worktree list --porcelain`` and falls back to
    :func:`find_worktree_for_prd` for convention-based path discovery.
    """
    from darkfactory import checks

    result = _find_worktree_path_and_branch_for_prd(prd_id, repo_root)
    if result is not None:
        entry, branch = result
    else:
        fallback = find_worktree_for_prd(prd_id, repo_root)
        if fallback is None:
            return None
        entry = fallback
        branch = f"prd/{entry.name}"

    pr_state = checks._get_pr_state(branch, repo_root)
    return StaleWorktree(
        prd_id=prd_id,
        branch=branch,
        worktree_path=entry,
        pr_state=pr_state,
    )


def remove_worktree(worktree: StaleWorktree, repo_root: Path) -> None:
    """Remove a worktree directory and delete the local branch.

    Raises ``RuntimeError`` if the worktree removal fails. Branch deletion
    is best-effort (may already be gone).
    """
    match git_run(
        "worktree", "remove", "--force", str(worktree.worktree_path), cwd=repo_root
    ):
        case Ok():
            pass
        case GitErr(returncode=code, stderr=err):
            raise RuntimeError(f"git worktree remove failed (exit {code}):\n{err}")
    # Branch deletion is best-effort — the branch may already be gone.
    git_run("branch", "-D", worktree.branch, cwd=repo_root)

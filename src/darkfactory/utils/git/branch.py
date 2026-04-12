"""Branch discovery helpers for PRD operations."""

from __future__ import annotations

from pathlib import Path

from darkfactory.utils.git._run import git_run
from darkfactory.utils.git._types import GitErr, Ok

__all__ = [
    "find_local_branches",
    "find_remote_branches",
]


def find_local_branches(prd_id: str, repo_root: Path) -> list[str]:
    """Return local branches matching ``prd/{prd_id}-*``.

    Strips the leading ``* `` marker that git emits for the current branch.
    Returns an empty list when none match.
    """
    match git_run("branch", "--list", f"prd/{prd_id}-*", cwd=repo_root):
        case Ok(stdout=output):
            return [
                line.strip().lstrip("* ")
                for line in output.splitlines()
                if line.strip()
            ]
        case GitErr():
            return []


def find_remote_branches(prd_id: str, repo_root: Path) -> list[str]:
    """Return remote tracking refs matching ``origin/prd/{prd_id}-*``.

    Each entry is the full remote ref as reported by ``git branch -r``
    (e.g. ``origin/prd/PRD-42-add-retry-logic``).
    Returns an empty list when none match or on git failure.
    """
    match git_run("branch", "-r", "--list", f"origin/prd/{prd_id}-*", cwd=repo_root):
        case Ok(stdout=output):
            return [line.strip() for line in output.splitlines() if line.strip()]
        case GitErr():
            return []

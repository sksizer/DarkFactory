"""Branch discovery helpers for PRD operations."""

from __future__ import annotations

import subprocess
from pathlib import Path

from darkfactory.git_ops import git_run

__all__ = [
    "find_local_branches",
    "find_remote_branches",
]


def find_local_branches(prd_id: str, repo_root: Path) -> list[str]:
    """Return local branches matching ``prd/{prd_id}-*``.

    Strips the leading ``* `` marker that git emits for the current branch.
    Returns an empty list when none match.
    """
    result = git_run("branch", "--list", f"prd/{prd_id}-*", cwd=repo_root)
    branches: list[str] = []
    for line in result.stdout.splitlines():
        branch = line.strip().lstrip("* ")
        if branch:
            branches.append(branch)
    return branches


def find_remote_branches(prd_id: str, repo_root: Path) -> list[str]:
    """Return remote tracking refs matching ``origin/prd/{prd_id}-*``.

    Each entry is the full remote ref as reported by ``git branch -r``
    (e.g. ``origin/prd/PRD-42-add-retry-logic``).
    Returns an empty list when none match or on git failure.
    """
    try:
        result = git_run(
            "branch", "-r", "--list", f"origin/prd/{prd_id}-*", cwd=repo_root
        )
    except subprocess.CalledProcessError:
        return []
    branches: list[str] = []
    for line in result.stdout.splitlines():
        branch = line.strip()
        if branch:
            branches.append(branch)
    return branches

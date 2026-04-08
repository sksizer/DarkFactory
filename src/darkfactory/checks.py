"""Reusable check functions for PRD harness invariants.

Each function takes injected dependencies so it can be tested without a real
repo. The return type is always ``list[Issue]``.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol

from .prd import PRD


@dataclass
class Issue:
    prd_id: str
    message: str
    severity: str  # "warning" | "error"


class GitStateAdapter(Protocol):
    """Minimal git-state interface required by check functions."""

    def remote_branch_exists(self, branch: str) -> bool:
        """Return True if ``branch`` exists on origin."""
        ...


class SubprocessGitState:
    """Real implementation that shells out to git."""

    def __init__(self, repo_root: str | None = None) -> None:
        self._cwd = repo_root

    def remote_branch_exists(self, branch: str) -> bool:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", branch],
            capture_output=True,
            text=True,
            cwd=self._cwd,
        )
        return bool(result.stdout.strip())


def validate_review_branches(
    prds: dict[str, PRD],
    git_state: GitStateAdapter,
) -> list[Issue]:
    """Return issues for PRDs in 'review' whose branch is gone from origin."""
    issues = []
    for prd_id, meta in prds.items():
        if meta.status != "review":
            continue
        branch = f"prd/{prd_id}-{meta.slug}"
        if not git_state.remote_branch_exists(branch):
            issues.append(
                Issue(
                    prd_id=prd_id,
                    message=f"{prd_id} is in 'review' but branch '{branch}' is gone from origin",
                    severity="warning",
                )
            )
    return issues

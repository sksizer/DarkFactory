"""Reusable check functions for PRD harness invariants.

Each function takes injected dependencies so it can be tested without a real
repo. The return type is always ``list[Issue]``.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from darkfactory.utils._result import Ok
from darkfactory.utils.git import GitErr, git_run
from darkfactory.utils.github._types import GhErr
from darkfactory.utils.github.pr import (
    fetch_all_pr_states,
    get_resume_pr_state,
)

from .model import PRD, compute_branch_name

logger = logging.getLogger(__name__)


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


@dataclass
class ResumeStatus:
    safe: bool
    reason: str  # human-readable explanation
    kind: str  # "safe" | "pr_merged" | "pr_closed" | "diverged"


def is_resume_safe(branch: str, repo_root: Path) -> ResumeStatus:
    """Check if resuming work on branch is safe.

    Checks PR state via ``gh`` (with graceful fallback if ``gh`` is absent)
    and compares local branch tip against ``origin/<branch>``.
    """
    # 1. Check PR state via gh (best-effort; missing gh is not fatal)
    match get_resume_pr_state(branch, repo_root):
        case Ok(value=prs):
            for pr in prs:
                if pr["state"] == "MERGED":
                    return ResumeStatus(
                        safe=False,
                        reason=(
                            f"PR for {branch} is merged; run `prd cleanup` to start fresh"
                        ),
                        kind="pr_merged",
                    )
                if pr["state"] == "CLOSED":
                    return ResumeStatus(
                        safe=False,
                        reason=(
                            f"PR for {branch} is closed; run `prd cleanup` to start fresh"
                        ),
                        kind="pr_closed",
                    )
        case GhErr(returncode=-1, stderr=err):
            logger.warning("gh not found; skipping PR state check")
        case GhErr(stderr=err):
            err_lower = err.lower()
            if (
                "no such file or directory" in err_lower
                or "command not found" in err_lower
            ):
                logger.warning("gh not found; skipping PR state check")
            else:
                logger.warning("gh pr list failed; skipping PR state check")

    # 2. Check local vs origin divergence (warn only, don't refuse)
    match git_run("rev-parse", f"refs/heads/{branch}", cwd=repo_root):
        case Ok(stdout=local_raw):
            local_sha = local_raw.strip()
        case GitErr():
            return ResumeStatus(safe=True, reason="", kind="safe")

    match git_run("rev-parse", f"refs/remotes/origin/{branch}", cwd=repo_root):
        case Ok(stdout=origin_raw):
            origin_sha = origin_raw.strip()
        case GitErr():
            return ResumeStatus(safe=True, reason="", kind="safe")

    if local_sha != origin_sha:
        match git_run(
            "rev-list", "--count", f"{branch}..origin/{branch}", cwd=repo_root
        ):
            case Ok(stdout=count_raw):
                count = int(count_raw.strip() or "0")
                if count > 0:
                    logger.warning(
                        "local branch %r is %d commit(s) behind origin/%s — "
                        "consider pulling before resuming",
                        branch,
                        count,
                        branch,
                    )
                    return ResumeStatus(
                        safe=True,
                        reason=(
                            f"local branch {branch!r} is {count} commit(s) behind "
                            f"origin/{branch}"
                        ),
                        kind="diverged",
                    )
            case GitErr():
                pass

    return ResumeStatus(safe=True, reason="", kind="safe")


@dataclass
class StaleWorktree:
    prd_id: str
    branch: str
    worktree_path: Path
    pr_state: str  # "MERGED" | "CLOSED" | "OPEN" | "UNKNOWN"


@dataclass
class RemoveStatus:
    safe: bool
    reason: str


def _get_pr_state(branch: str, repo_root: Path) -> str:
    """Get the PR state for a branch. Returns MERGED, CLOSED, OPEN, or UNKNOWN."""
    from darkfactory.utils.github.pr import get_pr_state

    match get_pr_state(branch, repo_root, timeout=10):
        case Ok(value=state):
            return state
        case _:
            return "UNKNOWN"


def _fetch_all_pr_states(repo_root: Path) -> dict[str, str]:
    """Fetch PR states for all branches in a single gh call."""
    match fetch_all_pr_states(repo_root, timeout=30):
        case Ok(value=states):
            return states
        case _:
            return {}


def _has_unpushed_commits(worktree_path: Path, branch: str) -> bool:
    """Return True if branch has local commits not yet pushed to origin."""
    match git_run(
        "rev-list", "--count", f"origin/{branch}..{branch}", cwd=worktree_path
    ):
        case Ok(stdout=raw):
            try:
                return int(raw.strip() or "0") > 0
            except ValueError:
                return False
        case _:
            return False


def find_stale_worktrees(repo_root: Path) -> list[StaleWorktree]:
    """Find worktrees for PRDs whose PR is merged or closed."""
    worktrees_dir = repo_root / ".worktrees"
    if not worktrees_dir.exists():
        return []

    # Single API call to get all PR states instead of one per worktree.
    all_pr_states = _fetch_all_pr_states(repo_root)

    stale = []
    for entry in sorted(worktrees_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        m = re.match(r"^(PRD-[\d.]+)", name)
        if not m:
            continue
        prd_id = m.group(1)
        branch = f"prd/{name}"
        pr_state = all_pr_states.get(branch, "UNKNOWN")
        if pr_state in ("MERGED", "CLOSED"):
            stale.append(
                StaleWorktree(
                    prd_id=prd_id,
                    branch=branch,
                    worktree_path=entry,
                    pr_state=pr_state,
                )
            )
    return stale


def is_safe_to_remove(worktree: StaleWorktree, force: bool = False) -> RemoveStatus:
    """Check if a worktree can be safely removed.

    Refuses if the PR is still open.
    Refuses if there are unpushed commits unless ``force`` is True.
    """
    if worktree.pr_state == "OPEN":
        return RemoveStatus(
            safe=False,
            reason=(f"PR for {worktree.branch} is still open; close or merge it first"),
        )
    if not force and _has_unpushed_commits(worktree.worktree_path, worktree.branch):
        return RemoveStatus(
            safe=False,
            reason=(
                f"{worktree.branch} has unpushed commits; use --force to remove anyway"
            ),
        )
    return RemoveStatus(safe=True, reason="")


def validate_review_branches(
    prds: dict[str, PRD],
    git_state: GitStateAdapter,
) -> list[Issue]:
    """Return issues for PRDs in 'review' whose branch is gone from origin."""
    issues = []
    for prd_id, meta in prds.items():
        if meta.status != "review":
            continue
        branch = compute_branch_name(meta)
        if not git_state.remote_branch_exists(branch):
            issues.append(
                Issue(
                    prd_id=prd_id,
                    message=f"{prd_id} is in 'review' but branch '{branch}' is gone from origin",
                    severity="warning",
                )
            )
    return issues

"""Reusable check functions for PRD harness invariants.

Each function takes injected dependencies so it can be tested without a real
repo. The return type is always ``list[Issue]``.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .prd import PRD

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
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "all",
                "--json",
                "state,mergedAt",
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode == 0:
            prs = json.loads(result.stdout)
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
        else:
            logger.warning(
                "gh pr list failed (rc=%d); skipping PR state check", result.returncode
            )
    except FileNotFoundError:
        logger.warning("gh not found; skipping PR state check")

    # 2. Check local vs origin divergence (warn only, don't refuse)
    try:
        local_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", f"refs/heads/{branch}"],
            capture_output=True,
            text=True,
        )
        origin_result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", f"refs/remotes/origin/{branch}"],
            capture_output=True,
            text=True,
        )
        if local_result.returncode == 0 and origin_result.returncode == 0:
            local_sha = local_result.stdout.strip()
            origin_sha = origin_result.stdout.strip()
            if local_sha != origin_sha:
                # Check if origin has commits local doesn't
                behind_result = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(repo_root),
                        "rev-list",
                        "--count",
                        f"{branch}..origin/{branch}",
                    ],
                    capture_output=True,
                    text=True,
                )
                if behind_result.returncode == 0:
                    count = int(behind_result.stdout.strip() or "0")
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
    except Exception as exc:
        logger.warning("divergence check failed (%s); skipping", exc)

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
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "all",
                "--json",
                "state",
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=10,
        )
        if result.returncode == 0:
            prs = json.loads(result.stdout)
            if prs:
                return str(prs[0]["state"])
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
        subprocess.TimeoutExpired,
    ):
        pass
    return "UNKNOWN"


def _fetch_all_pr_states(repo_root: Path) -> dict[str, str]:
    """Fetch PR states for all branches in a single gh call.

    Returns a mapping of ``headRefName`` → state (MERGED, CLOSED, OPEN).
    If a branch has multiple PRs, the most relevant state wins
    (MERGED > CLOSED > OPEN).
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "all",
                "--limit",
                "500",
                "--json",
                "headRefName,state",
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=30,
        )
        if result.returncode != 0:
            return {}
        prs = json.loads(result.stdout)
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
        subprocess.TimeoutExpired,
    ):
        return {}

    # If a branch has multiple PRs (e.g. one MERGED, one OPEN), prefer MERGED.
    priority = {"MERGED": 2, "CLOSED": 1, "OPEN": 0}
    states: dict[str, str] = {}
    for pr in prs:
        branch = pr.get("headRefName", "")
        state = str(pr.get("state", ""))
        if not branch or not state:
            continue
        existing = states.get(branch)
        if existing is None or priority.get(state, -1) > priority.get(existing, -1):
            states[branch] = state
    return states


def _has_unpushed_commits(worktree_path: Path, branch: str) -> bool:
    """Return True if branch has local commits not yet pushed to origin."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", f"origin/{branch}..{branch}"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
        )
        if result.returncode == 0:
            return int(result.stdout.strip() or "0") > 0
    except (ValueError, Exception):  # noqa: BLE001
        pass
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

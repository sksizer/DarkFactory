"""Reusable check functions for PRD harness invariants.

Each function takes injected dependencies so it can be tested without a real
repo. The return type is always ``list[Issue]``.
"""

from __future__ import annotations

import json
import logging
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

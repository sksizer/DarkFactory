"""GitHub pull request state queries and creation helpers."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def list_prs_for_branch(
    branch: str,
    repo_root: Path,
    fields: str = "state",
) -> list[dict[str, Any]]:
    """Return list of PR dicts for a branch (all states).

    Raises :class:`FileNotFoundError` if ``gh`` is not installed — callers
    that want graceful degradation must catch it themselves. Returns an empty
    list on other errors (e.g. non-zero exit, JSON decode failures).
    """
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
                fields,
            ],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode == 0:
            return list(json.loads(result.stdout))
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def get_pr_state(branch: str, repo_root: Path) -> str:
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


def fetch_all_pr_states(repo_root: Path) -> dict[str, str]:
    """Fetch PR states for all branches in a single ``gh`` call.

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


def create_pull_request(
    base_ref: str,
    title: str,
    body_path: str,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Run ``gh pr create`` and return the completed-process result.

    Raises :class:`subprocess.CalledProcessError` on non-zero exit.
    """
    return subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            base_ref,
            "--title",
            title,
            "--body-file",
            body_path,
        ],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )

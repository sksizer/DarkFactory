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


def create_pull_request_inline(
    title: str,
    body: str,
    base_ref: str | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``gh pr create`` with an inline body string.

    Unlike :func:`create_pull_request`, this passes ``--body`` directly rather
    than writing a temp file.  Use for short, generated bodies where a temp file
    is unnecessary.

    Raises :class:`subprocess.CalledProcessError` on non-zero exit.
    """
    cmd = ["gh", "pr", "create", "--title", title, "--body", body]
    if base_ref is not None:
        cmd.extend(["--base", base_ref])
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        check=True,
        capture_output=True,
        text=True,
    )


def list_prs(
    state: str,
    fields: str,
    limit: int = 100,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Return a list of PR dicts from ``gh pr list``.

    ``state`` is one of ``"open"``, ``"closed"``, or ``"merged"``.
    ``fields`` is a comma-separated list of JSON field names.

    Raises :class:`subprocess.CalledProcessError` on non-zero exit,
    :class:`FileNotFoundError` if ``gh`` is not installed, or
    :class:`json.JSONDecodeError` on unparseable output.
    """
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            state,
            "--json",
            fields,
            "--limit",
            str(limit),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo_root) if repo_root is not None else None,
    )
    return list(json.loads(result.stdout))


def gh_pr_view_json(
    pr_number: int,
    fields: str,
    repo_root: Path | None = None,
) -> dict[str, Any] | None:
    """Run ``gh pr view {pr_number} --json {fields}`` and return parsed JSON.

    Returns ``None`` on any error (gh not installed, non-zero exit, parse
    failure) so callers can treat missing data as an empty result.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--json",
                fields,
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(repo_root) if repo_root is not None else None,
        )
        return dict(json.loads(result.stdout))
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None

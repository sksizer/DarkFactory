"""GitHub CLI (gh) utilities — typed wrappers around gh subprocess calls."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PrInfo:
    """Minimal PR descriptor returned by gh pr list."""

    number: int
    head_ref_name: str


def list_open_prs(repo_root: Path, *, limit: int = 100) -> list[PrInfo]:
    """Return open PRs as typed :class:`PrInfo` records.

    Returns an empty list if ``gh`` is unavailable or returns a non-zero
    exit code.
    """
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,headRefName",
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return []
    try:
        prs: list[dict[str, object]] = json.loads(result.stdout)
        return [
            PrInfo(
                number=int(str(pr["number"])),
                head_ref_name=str(pr["headRefName"]),
            )
            for pr in prs
        ]
    except (json.JSONDecodeError, KeyError):
        return []


def close_pr(pr_number: int, repo_root: Path, *, comment: str = "") -> bool:
    """Close a PR by number.  Returns ``True`` on success.

    Optionally posts *comment* on the PR before closing.
    """
    cmd = ["gh", "pr", "close", str(pr_number)]
    if comment:
        cmd += ["--comment", comment]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    return result.returncode == 0

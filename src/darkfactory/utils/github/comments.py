"""GitHub PR comment subprocess helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ._cli import gh_api


def post_comment_reply(
    pr_number: int,
    target_id: str,
    body: str,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Post a reply to a PR inline review comment via ``gh api``.

    Calls ``POST /repos/{owner}/{repo}/pulls/{pr}/comments/{target_id}/replies``.
    Returns the completed-process result — callers decide how to handle
    non-zero exit codes.
    """
    endpoint = f"repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments/{target_id}/replies"
    return gh_api("POST", endpoint, [("body", body)], cwd=cwd)

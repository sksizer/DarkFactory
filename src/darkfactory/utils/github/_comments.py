"""GitHub CLI helpers for PR comments and GraphQL queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from darkfactory.utils._result import Ok
from darkfactory.utils.github._cli import gh_json, gh_run
from darkfactory.utils.github._types import GhCheckResult, GhErr, GhResult


def graphql_fetch(
    query: str,
    variables: dict[str, str],
    cwd: Path,
) -> GhResult[dict[str, Any]]:
    """Run a ``gh api graphql`` call and return parsed JSON.

    *variables* are passed as ``-F key=value`` pairs (for non-string values)
    or ``-f key=value`` pairs (for the query itself).
    """
    args: list[str] = ["api", "graphql"]
    for key, value in variables.items():
        args.extend(["-F", f"{key}={value}"])
    args.extend(["-f", f"query={query}"])
    return gh_json(*args, cwd=cwd)


def post_reply(
    endpoint: str,
    body: str,
    cwd: Path,
) -> GhCheckResult:
    """POST a reply to a PR comment via ``gh api``."""
    return gh_run(
        "api",
        "--method",
        "POST",
        endpoint,
        "-f",
        f"body={body}",
        cwd=cwd,
    )


def repo_nwo(cwd: Path) -> GhResult[tuple[str, str]]:
    """Return ``(owner, name)`` for the current repo via gh.

    Uses ``gh repo view --json nameWithOwner -q .nameWithOwner``.
    The ``-q`` flag makes gh output plain text, not JSON.
    """
    match gh_run(
        "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner",
        cwd=cwd,
    ):
        case Ok(stdout=raw):
            nwo = raw.strip()
            owner, _, name = nwo.partition("/")
            if owner and name:
                return Ok((owner, name), stdout=raw)
            return GhErr(-1, raw, "unexpected nameWithOwner format", ["gh", "repo", "view"])
        case err:
            return err

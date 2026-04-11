"""Low-level ``gh`` CLI subprocess wrappers.

Parallel to the git primitives in ``utils/git/_ops.py``: thin wrappers
over ``subprocess.run(["gh", ...])``.

- :func:`gh_repo_nwo` — return ``(owner, name)`` for the current repo.
- :func:`gh_graphql` — run ``gh api graphql`` and return parsed JSON.
- :func:`gh_api` — generic ``gh api`` call with configurable method and fields.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def gh_repo_nwo(cwd: Path | None = None) -> tuple[str, str]:
    """Return ``(owner, name)`` for the current repo via ``gh``.

    ``cwd`` is forwarded to :func:`subprocess.run` so the query is resolved
    against the intended repository rather than the process working directory.
    """
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(cwd) if cwd is not None else None,
    )
    nwo = result.stdout.strip()
    owner, _, name = nwo.partition("/")
    return owner, name


def gh_graphql(
    owner: str,
    name: str,
    pr_number: int,
    query: str,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Run ``gh api graphql`` with PR variables and return parsed JSON.

    Passes ``owner``, ``name``, and ``number`` as GraphQL variables.
    Raises :class:`subprocess.CalledProcessError` on non-zero exit.

    ``cwd`` is forwarded to :func:`subprocess.run` so the query is resolved
    against the intended repository rather than the process working directory.
    """
    result = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={pr_number}",
            "-f",
            f"query={query}",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(cwd) if cwd is not None else None,
    )
    import json

    return dict(json.loads(result.stdout))


def gh_api(
    method: str,
    endpoint: str,
    fields: list[tuple[str, str]],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``gh api --method METHOD ENDPOINT`` with ``-f key=value`` fields.

    Returns the completed-process result without raising — callers decide
    how to handle non-zero exit codes.
    """
    cmd = ["gh", "api", "--method", method, endpoint]
    for key, value in fields:
        cmd.extend(["-f", f"{key}={value}"])
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
    )

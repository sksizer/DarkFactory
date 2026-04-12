"""GitHub PR operations — typed wrappers around gh PR subprocess calls."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from darkfactory.utils._result import Ok
from darkfactory.utils.github._cli import gh_json, gh_run
from darkfactory.utils.github._types import GhCheckResult, GhErr, GhResult


@dataclass(frozen=True)
class PrInfo:
    """Minimal PR descriptor returned by gh pr list."""

    number: int
    head_ref_name: str


def get_pr_state(
    branch: str, repo_root: Path, *, timeout: int | None = None
) -> GhResult[str]:
    """Get the PR state for a branch.

    Returns ``Ok("MERGED")``, ``Ok("OPEN")``, etc., or ``GhErr``.
    Returns ``Ok("NONE")`` if there are no PRs for the branch.
    """
    match gh_json(
        "pr",
        "list",
        "--head",
        branch,
        "--state",
        "all",
        "--json",
        "state",
        cwd=repo_root,
        timeout=timeout,
    ):
        case Ok(value=prs) if isinstance(prs, list) and prs:
            return Ok(str(prs[0]["state"]))
        case Ok(value=prs) if isinstance(prs, list):
            return Ok("NONE")
        case Ok():
            return GhErr(-1, "", "unexpected response format", ["gh", "pr", "list"])
        case err:
            return err


def fetch_all_pr_states(
    repo_root: Path, *, timeout: int | None = None
) -> GhResult[dict[str, str]]:
    """Fetch PR states for all branches in a single gh call.

    Returns a mapping of ``headRefName`` -> state (MERGED, CLOSED, OPEN).
    If a branch has multiple PRs, the most relevant state wins
    (MERGED > CLOSED > OPEN).
    """
    match gh_json(
        "pr",
        "list",
        "--state",
        "all",
        "--limit",
        "500",
        "--json",
        "headRefName,state",
        cwd=repo_root,
        timeout=timeout,
    ):
        case Ok(value=prs) if isinstance(prs, list):
            priority = {"MERGED": 2, "CLOSED": 1, "OPEN": 0}
            states: dict[str, str] = {}
            for pr in prs:
                branch = pr.get("headRefName", "")
                state = str(pr.get("state", ""))
                if not branch or not state:
                    continue
                existing = states.get(branch)
                if existing is None or priority.get(state, -1) > priority.get(
                    existing, -1
                ):
                    states[branch] = state
            return Ok(states)
        case Ok():
            return GhErr(-1, "", "unexpected response format", ["gh", "pr", "list"])
        case err:
            return err


def get_resume_pr_state(branch: str, repo_root: Path) -> GhResult[list[dict[str, Any]]]:
    """Return the raw PR list (state, mergedAt fields) for a branch.

    Used by ``is_resume_safe`` to interpret PR state.
    """
    match gh_json(
        "pr",
        "list",
        "--head",
        branch,
        "--state",
        "all",
        "--json",
        "state,mergedAt",
        cwd=repo_root,
    ):
        case Ok(value=prs) if isinstance(prs, list):
            return Ok(prs)
        case Ok():
            return GhErr(-1, "", "unexpected response format", ["gh", "pr", "list"])
        case err:
            return err


def create_pr(base: str, title: str, body_path: str, cwd: Path) -> GhResult[str]:
    """Create a PR via ``gh pr create``. Returns the PR URL on success."""
    match gh_run(
        "pr",
        "create",
        "--base",
        base,
        "--title",
        title,
        "--body-file",
        body_path,
        cwd=cwd,
    ):
        case Ok(stdout=raw):
            url_line = raw.strip().splitlines()[-1] if raw.strip() else ""
            return Ok(url_line, stdout=raw)
        case err:
            return err


def list_open_prs(repo_root: Path, *, limit: int = 100) -> GhResult[list[PrInfo]]:
    """Return open PRs as typed :class:`PrInfo` records."""
    match gh_json(
        "pr",
        "list",
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        "number,headRefName",
        cwd=repo_root,
    ):
        case Ok(value=prs) if isinstance(prs, list):
            try:
                result = [
                    PrInfo(
                        number=int(str(pr["number"])),
                        head_ref_name=str(pr["headRefName"]),
                    )
                    for pr in prs
                ]
                return Ok(result)
            except (KeyError, ValueError) as exc:
                return GhErr(-1, "", str(exc), ["gh", "pr", "list"])
        case Ok():
            return GhErr(-1, "", "unexpected response format", ["gh", "pr", "list"])
        case err:
            return err


def close_pr(pr_number: int, repo_root: Path, *, comment: str = "") -> GhCheckResult:
    """Close a PR by number."""
    args = ["pr", "close", str(pr_number)]
    if comment:
        args += ["--comment", comment]
    return gh_run(*args, cwd=repo_root)

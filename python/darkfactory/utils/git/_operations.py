"""Git operation helpers built on top of ``_run.py`` primitives.

All non-display helpers call ``git_run`` — no direct ``subprocess`` calls.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from darkfactory.utils.git._run import git_run
from darkfactory.utils.git._types import CheckResult, GitErr, GitResult, Ok, Timeout

_log = logging.getLogger(__name__)

__all__ = [
    "branch_exists_local",
    "branch_exists_remote",
    "diff_quiet",
    "diff_show",
    "resolve_commit_timestamp",
    "run_add",
    "run_commit",
    "status_other_dirty",
]


def branch_exists_local(repo_root: Path, branch: str) -> bool:
    """Return True if ``branch`` exists in the local repo's refs."""
    match git_run(
        "rev-parse",
        "--verify",
        "--quiet",
        f"refs/heads/{branch}",
        cwd=repo_root,
    ):
        case Ok():
            return True
        case GitErr() | Timeout():
            return False


def branch_exists_remote(repo_root: Path, branch: str) -> bool:
    """Return True if ``branch`` exists on origin.

    Best-effort: returns False (and logs a warning) on timeout or any
    subprocess error so the caller can fall back to the local check.
    """
    match git_run(
        "ls-remote",
        "--exit-code",
        "origin",
        f"refs/heads/{branch}",
        cwd=repo_root,
        timeout=10,
    ):
        case Ok():
            return True
        case Timeout(timeout=t):
            _log.warning("ls-remote timed out after %ds", t)
            return False
        case GitErr():
            return False


def run_add(paths: list[str], cwd: Path) -> CheckResult:
    """Stage specific files."""
    return git_run("add", "--", *paths, cwd=cwd)


def run_commit(message: str, cwd: Path) -> CheckResult:
    """Create a commit with the given message."""
    return git_run("commit", "-m", message, cwd=cwd)


def diff_quiet(paths: list[str], cwd: Path) -> CheckResult:
    """Return ``Ok(None)`` if there are NO changes (clean), ``GitErr`` if dirty."""
    return git_run("diff", "--quiet", "--", *paths, cwd=cwd)


def status_other_dirty(paths: list[str], cwd: Path) -> GitResult[list[str]]:
    """Return dirty files NOT in *paths*.

    ``Ok.value`` is the parsed dirty-file list; ``Ok.stdout`` is the raw
    porcelain output.
    """
    match git_run("status", "--porcelain", cwd=cwd):
        case Ok(stdout=raw):
            other: list[str] = [
                line[3:].strip()
                for line in raw.splitlines()
                if line.strip() and line[3:].strip() not in paths
            ]
            return Ok(other, stdout=raw)
        case GitErr() as err:
            return err
        case Timeout(cmd=cmd, timeout=t):
            return GitErr(-1, "", f"timed out after {t}s", cmd)


def resolve_commit_timestamp(commit: str, cwd: Path) -> GitResult[str]:
    """Resolve a commit SHA or ref to an ISO-8601 author timestamp.

    Returns ``Ok(timestamp_string)`` on success, ``GitErr`` on failure.
    """
    match git_run("log", "-1", "--format=%aI", commit, cwd=cwd):
        case Ok(stdout=raw):
            return Ok(raw.strip(), stdout=raw)
        case GitErr() as err:
            return err
        case Timeout(cmd=cmd, timeout=t):
            return GitErr(-1, "", f"timed out after {t}s", cmd)


def diff_show(paths: list[str], cwd: Path) -> None:
    """Print a colored diff to the terminal."""
    subprocess.run(
        ["git", "diff", "--"] + paths,
        cwd=str(cwd),
        check=False,
    )

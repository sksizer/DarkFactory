"""Git operation helpers built on top of ``_run.py`` primitives.

All non-display helpers call ``git_run`` — no direct ``subprocess`` calls.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from darkfactory.utils.git._run import git_run
from darkfactory.utils.git._types import CheckResult, GitErr, GitResult, Ok


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


def diff_show(paths: list[str], cwd: Path) -> None:
    """Print a colored diff to the terminal."""
    subprocess.run(
        ["git", "diff", "--"] + paths,
        cwd=str(cwd),
        check=False,
    )

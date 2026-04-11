"""Git staging and commit helpers."""

from __future__ import annotations

from pathlib import Path

from ._ops import git_run


def status_other_dirty(paths: list[str], cwd: Path) -> list[str]:
    """Return list of dirty files NOT in paths."""
    result = git_run("status", "--porcelain", cwd=cwd)
    other_dirty: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        file_path = line[3:].strip()
        if file_path not in paths:
            other_dirty.append(file_path)
    return other_dirty


def run_add(paths: list[str], cwd: Path) -> None:
    """Stage specific files."""
    git_run("add", "--", *paths, cwd=cwd)


def run_commit(message: str, cwd: Path) -> None:
    """Create a commit with the given message."""
    git_run("commit", "-m", message, cwd=cwd)

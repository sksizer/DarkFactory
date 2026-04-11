"""Git subprocess helpers for PRD operations."""

from __future__ import annotations

import subprocess
from pathlib import Path


def diff_quiet(paths: list[str], cwd: Path) -> bool:
    """Return True if there are NO changes (clean). False if dirty."""
    result = subprocess.run(
        ["git", "diff", "--quiet", "--"] + paths,
        cwd=str(cwd),
        check=False,
    )
    return result.returncode == 0


def diff_show(paths: list[str], cwd: Path) -> None:
    """Print a colored diff to the terminal."""
    subprocess.run(
        ["git", "diff", "--"] + paths,
        cwd=str(cwd),
        check=False,
    )


def status_other_dirty(paths: list[str], cwd: Path) -> list[str]:
    """Return list of dirty files NOT in paths."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
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
    subprocess.run(
        ["git", "add", "--"] + paths,
        cwd=str(cwd),
        check=True,
    )


def run_commit(message: str, cwd: Path) -> None:
    """Create a commit with the given message."""
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(cwd),
        check=True,
    )

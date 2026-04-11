"""Git diff helpers."""

from __future__ import annotations

from pathlib import Path

from ._ops import git_check, git_run


def diff_quiet(paths: list[str], cwd: Path) -> bool:
    """Return True if there are NO changes (clean). False if dirty."""
    return git_check("diff", "--quiet", "--", *paths, cwd=cwd)


def diff_show(paths: list[str], cwd: Path) -> None:
    """Print a colored diff to the terminal."""
    import subprocess

    subprocess.run(
        ["git", "diff", "--"] + paths,
        cwd=str(cwd),
        check=False,
    )

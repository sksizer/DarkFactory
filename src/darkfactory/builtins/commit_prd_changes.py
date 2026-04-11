"""System builtin: commit_prd_changes — interactive commit prompt for PRD edits."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from darkfactory.builtins.system_builtins import _register
from darkfactory.system import SystemContext


def _find_prd_file(ctx: SystemContext) -> Path:
    """Resolve the file path for the target PRD."""
    if not ctx.target_prd:
        raise ValueError("commit_prd_changes requires ctx.target_prd to be set")
    prd = ctx.prds.get(ctx.target_prd)
    if prd is None:
        raise ValueError(f"target PRD {ctx.target_prd!r} not found in loaded PRDs")
    return Path(prd.path)


def _git_diff_quiet(paths: list[str], cwd: Path) -> bool:
    """Return True if there are NO changes (clean). False if dirty."""
    result = subprocess.run(
        ["git", "diff", "--quiet", "--"] + paths,
        cwd=str(cwd),
        check=False,
    )
    return result.returncode == 0


def _git_diff_show(paths: list[str], cwd: Path) -> None:
    """Print a colored diff to the terminal."""
    subprocess.run(
        ["git", "diff", "--"] + paths,
        cwd=str(cwd),
        check=False,
    )


def _git_status_other_dirty(paths: list[str], cwd: Path) -> list[str]:
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


def _run_git_add(paths: list[str], cwd: Path) -> None:
    """Stage specific files."""
    subprocess.run(
        ["git", "add", "--"] + paths,
        cwd=str(cwd),
        check=True,
    )


def _run_git_commit(message: str, cwd: Path) -> None:
    """Create a commit with the given message."""
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(cwd),
        check=True,
    )


def _prompt_user(prompt: str) -> str:
    """Read user input. Extracted for testability."""
    return input(prompt)


@_register("commit_prd_changes")
def commit_prd_changes(
    ctx: SystemContext,
    *,
    message: str | None = None,
    paths: list[str] | None = None,
) -> None:
    """Offer to commit PRD changes at the end of a discuss chain."""
    prd_file = _find_prd_file(ctx)

    if paths is None:
        paths = [str(prd_file)]

    if message is None:
        message = f"chore(prd): {ctx.target_prd} discuss session refinements"
    elif "{target_prd}" in message:
        message = ctx.format_string(message)

    is_clean = _git_diff_quiet(paths, ctx.cwd)
    if is_clean:
        print("No PRD changes to commit.", file=sys.stderr)
        return

    bar = "\u2500" * 37
    print(f"{bar}", file=sys.stderr)
    print(" Phase: commit", file=sys.stderr)
    print(f"{bar}", file=sys.stderr)

    _git_diff_show(paths, ctx.cwd)

    other_dirty = _git_status_other_dirty(paths, ctx.cwd)
    if other_dirty:
        n = len(other_dirty)
        print(f"\nNote: {n} other file(s) have unstaged changes that will NOT be included.", file=sys.stderr)
        if n <= 5:
            for f in other_dirty:
                print(f"  {f}", file=sys.stderr)

    print(f"\nCommit message: {message}", file=sys.stderr)
    choice = _prompt_user("Commit these changes? [y/N/e(dit message)] ").strip().lower()

    if choice == "y":
        _run_git_add(paths, ctx.cwd)
        _run_git_commit(message, ctx.cwd)
        ctx.logger.info("commit_prd_changes: committed %s", ", ".join(paths))
    elif choice == "e":
        new_message = _prompt_user("Enter new commit message: ").strip()
        if new_message:
            _run_git_add(paths, ctx.cwd)
            _run_git_commit(new_message, ctx.cwd)
            ctx.logger.info("commit_prd_changes: committed with custom message")
        else:
            print("Empty message — skipped commit. Changes left in working tree.", file=sys.stderr)
    else:
        print("Skipped commit. Changes left in working tree.", file=sys.stderr)

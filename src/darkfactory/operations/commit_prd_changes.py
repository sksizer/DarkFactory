"""System builtin: commit_prd_changes — interactive commit prompt for PRD edits."""

from __future__ import annotations

import sys

from darkfactory.operations.system_builtins import _register
from darkfactory.system import SystemContext
from darkfactory.utils.git import (
    GitErr,
    Ok,
    diff_quiet,
    diff_show,
    run_add,
    run_commit,
    status_other_dirty,
)
from darkfactory.utils.terminal import prompt_user


@_register("commit_prd_changes")
def commit_prd_changes(
    ctx: SystemContext,
    *,
    message: str | None = None,
    paths: list[str] | None = None,
) -> None:
    """Offer to commit PRD changes at the end of a discuss chain."""
    prd_file = ctx.find_prd_file()

    if paths is None:
        paths = [str(prd_file)]

    if message is None:
        message = f"docs(prd): {ctx.target_prd} discuss session refinements"
    elif "{target_prd}" in message:
        message = ctx.format_string(message)

    match diff_quiet(paths, ctx.cwd):
        case Ok():
            print("No PRD changes to commit.", file=sys.stderr)
            return
        case GitErr():
            pass  # There are changes — proceed.

    bar = "\u2500" * 37
    print(f"{bar}", file=sys.stderr)
    print(" Phase: commit", file=sys.stderr)
    print(f"{bar}", file=sys.stderr)

    diff_show(paths, ctx.cwd)

    match status_other_dirty(paths, ctx.cwd):
        case Ok(value=other_dirty):
            pass
        case GitErr():
            other_dirty = []
    if other_dirty:
        n = len(other_dirty)
        print(
            f"\nNote: {n} other file(s) have unstaged changes that will NOT be included.",
            file=sys.stderr,
        )
        if n <= 5:
            for f in other_dirty:
                print(f"  {f}", file=sys.stderr)

    print(f"\nCommit message: {message}", file=sys.stderr)
    choice = prompt_user("Commit these changes? [y/N/e(dit message)] ").strip().lower()

    if choice == "y":
        match run_add(paths, ctx.cwd):
            case Ok():
                pass
            case GitErr(returncode=code, stderr=err):
                raise RuntimeError(f"git add failed (exit {code}):\n{err}")
        match run_commit(message, ctx.cwd):
            case Ok():
                pass
            case GitErr(returncode=code, stderr=err):
                raise RuntimeError(f"git commit failed (exit {code}):\n{err}")
        ctx.logger.info("commit_prd_changes: committed %s", ", ".join(paths))
    elif choice == "e":
        new_message = prompt_user("Enter new commit message: ").strip()
        if new_message:
            match run_add(paths, ctx.cwd):
                case Ok():
                    pass
                case GitErr(returncode=code, stderr=err):
                    raise RuntimeError(f"git add failed (exit {code}):\n{err}")
            match run_commit(new_message, ctx.cwd):
                case Ok():
                    pass
                case GitErr(returncode=code, stderr=err):
                    raise RuntimeError(f"git commit failed (exit {code}):\n{err}")
            ctx.logger.info("commit_prd_changes: committed with custom message")
        else:
            print(
                "Empty message — skipped commit. Changes left in working tree.",
                file=sys.stderr,
            )
    else:
        print("Skipped commit. Changes left in working tree.", file=sys.stderr)

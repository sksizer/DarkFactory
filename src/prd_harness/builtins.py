"""Built-in task primitives for the PRD harness.

Built-ins are the deterministic SDLC operations that every workflow can
reference by name: create a worktree, set a PRD's status, make a commit,
push a branch, open a PR. They live here (not in individual workflow
modules) because they're shared — every workflow uses the same ``commit``
primitive, not a bespoke one.

Workflows reference built-ins by name via :class:`~prd_harness.workflow.BuiltIn`::

    BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start work"})

The runner looks up ``"commit"`` in :data:`BUILTINS` and calls the
registered function with the :class:`~prd_harness.workflow.ExecutionContext`
plus any formatted kwargs.

This module currently ships **stub implementations** that raise
``NotImplementedError``. The registry itself is fully functional, so
downstream code (loader, assign, dry-run plans, list-workflows) can
reference built-ins by name without the real git/gh operations being
wired up yet. Real implementations land in a follow-up PR so they can
carry their own test fixtures (tmp git repos, mocked subprocess) without
blocking the upstream scaffolding.
"""

from __future__ import annotations

from typing import Callable

from .workflow import ExecutionContext, Status

BuiltInFunc = Callable[..., None]
"""Signature every built-in shares: takes ``ExecutionContext`` plus **kwargs, returns None.

Return value is always ``None`` — built-ins communicate results by
mutating the context (setting ``ctx.worktree_path``, ``ctx.pr_url``, etc.)
and signal failure by raising an exception. This keeps the dispatch
uniform in the runner.
"""


BUILTINS: dict[str, BuiltInFunc] = {}
"""Global registry mapping built-in name to its implementing function.

Populated at import time via the :func:`builtin` decorator. The runner
looks up names in this dict when dispatching a
:class:`~prd_harness.workflow.BuiltIn` task. Workflows never touch this
dict directly — they reference built-ins by name only.
"""


def builtin(name: str) -> Callable[[BuiltInFunc], BuiltInFunc]:
    """Decorator that registers a function in :data:`BUILTINS`.

    Rejects duplicate registrations with ``ValueError`` to catch typos
    and accidental overrides during development. Applied at import time::

        @builtin("ensure_worktree")
        def ensure_worktree(ctx: ExecutionContext) -> None:
            ...
    """

    def decorator(func: BuiltInFunc) -> BuiltInFunc:
        if name in BUILTINS:
            raise ValueError(f"duplicate builtin registration for {name!r}")
        BUILTINS[name] = func
        return func

    return decorator


# ---------- stub implementations ----------
#
# These raise NotImplementedError on call. The decorators still run at
# import time so BUILTINS is populated and the registry is fully
# functional for name lookup, dry-run plans, and list-workflows output.
#
# Real implementations land in the PRD-209 follow-up (see the dev-prds
# set) where they'll carry tmp-git-repo and mocked-subprocess fixtures.


@builtin("ensure_worktree")
def ensure_worktree(ctx: ExecutionContext) -> None:
    """Create (or resume) a git worktree for this PRD.

    Target path: ``{repo_root}/.worktrees/{prd_id}-{slug}``. Branch:
    ``prd/{prd_id}-{slug}`` created from ``ctx.base_ref``. If the worktree
    already exists (previous run resumed), reuses it. Sets
    ``ctx.worktree_path`` and ``ctx.cwd`` on success.
    """
    raise NotImplementedError("ensure_worktree — real impl in PRD-209 follow-up")


@builtin("set_status")
def set_status(ctx: ExecutionContext, *, to: Status) -> None:
    """Rewrite the PRD's ``status:`` frontmatter field.

    Delegates to :func:`prd_harness.prd.set_status`, which preserves the
    body byte-for-byte and bumps ``updated`` to today's date. Used at
    workflow start (ready -> in-progress) and end (-> review).
    """
    raise NotImplementedError("set_status — real impl in PRD-209 follow-up")


@builtin("commit")
def commit(ctx: ExecutionContext, *, message: str) -> None:
    """Stage all changes and make a commit inside the worktree.

    ``message`` is format-string expanded against the context (so
    ``"chore(prd): {prd_id} start work"`` becomes
    ``"chore(prd): PRD-070 start work"``) before being passed to
    ``git commit -m``. No-ops gracefully on an empty diff so workflows
    can safely commit after each logical step without worrying about
    whether anything actually changed.
    """
    raise NotImplementedError("commit — real impl in PRD-209 follow-up")


@builtin("push_branch")
def push_branch(ctx: ExecutionContext) -> None:
    """Push the current branch to origin with upstream tracking.

    Runs ``git push -u origin {branch}`` inside the worktree. Required
    before ``create_pr`` because ``gh pr create --base`` needs the remote
    to exist.
    """
    raise NotImplementedError("push_branch — real impl in PRD-209 follow-up")


@builtin("create_pr")
def create_pr(ctx: ExecutionContext) -> None:
    """Open a pull request via ``gh pr create``.

    Title: ``"{prd_id}: {prd_title}"``. Body: generated from the PRD's
    acceptance criteria plus a link back to the PRD file. Base branch:
    ``ctx.base_ref``. On success, sets ``ctx.pr_url`` to the URL printed
    by ``gh``. On failure, raises — the runner will mark the PRD blocked.
    """
    raise NotImplementedError("create_pr — real impl in PRD-209 follow-up")


@builtin("cleanup_worktree")
def cleanup_worktree(ctx: ExecutionContext) -> None:
    """Remove the worktree after a successful run.

    Idempotent — if the worktree is already gone, logs and returns.
    Normally skipped during chain execution so downstream worktrees can
    base on this branch; called explicitly via ``prd cleanup`` after the
    whole chain is done.
    """
    raise NotImplementedError("cleanup_worktree — real impl in PRD-209 follow-up")

"""Built-in task primitives — re-export hub.

Imports every submodule so @builtin-decorated functions register on
package import. Re-exports the public API for backwards compatibility.

Built-ins are the deterministic SDLC operations that every workflow
references by name: create a worktree, set a PRD's status, make a
commit, push a branch, open a PR. They live here (not in individual
workflow modules) because they're shared — every workflow uses the
same ``commit`` primitive, not a bespoke one.

Workflows reference built-ins by name via :class:`~darkfactory.workflow.BuiltIn`::

    BuiltIn("commit", kwargs={"message": "chore(prd): {prd_id} start work"})

The runner looks up ``"commit"`` in :data:`BUILTINS` and calls the
registered function with the :class:`~darkfactory.workflow.ExecutionContext`
plus any formatted kwargs.

**Dry-run mode**: every built-in checks ``ctx.dry_run`` before doing
anything destructive. In dry-run, we log what we WOULD do at INFO
level and return. This is what powers ``prd plan`` and the default
``prd run`` (without ``--execute``).

**Subprocess discipline**: all shell commands use ``subprocess.run``
with an explicit argv list (never ``shell=True``), capture output,
and check the return code. Git and gh invocations go through
:func:`_run_git` and :func:`_run_gh` helpers that centralize cwd
handling and dry-run support.
"""

from __future__ import annotations

import subprocess  # noqa: F401  # re-exported for test monkeypatching

from darkfactory.builtins._registry import BUILTINS, BuiltInFunc, builtin
from darkfactory.workflow import ExecutionContext
from darkfactory.builtins._shared import (
    _FORBIDDEN_ATTRIBUTION_PATTERNS,
    _run,
    _scan_for_forbidden_attribution,
)

# Import submodules to trigger @builtin registration.
from darkfactory.builtins.cleanup_worktree import cleanup_worktree
from darkfactory.builtins.commit import commit
from darkfactory.builtins.commit_transcript import commit_transcript
from darkfactory.builtins.create_pr import create_pr
from darkfactory.builtins.ensure_worktree import ensure_worktree
from darkfactory.builtins.lint_attribution import lint_attribution
from darkfactory.builtins.push_branch import push_branch
from darkfactory.builtins.set_status import set_status
from darkfactory.builtins.summarize_agent_run import summarize_agent_run

__all__ = [
    "BUILTINS",
    "BuiltInFunc",
    "builtin",
    "_run",
    "_scan_for_forbidden_attribution",
    "_FORBIDDEN_ATTRIBUTION_PATTERNS",
    "ensure_worktree",
    "set_status",
    "commit",
    "push_branch",
    "summarize_agent_run",
    "commit_transcript",
    "create_pr",
    "lint_attribution",
    "cleanup_worktree",
]


def _format_tool_counts(tool_counts: dict[str, int]) -> str:
    """Format tool counts as a compact inline string, e.g. 'Read×5, Edit×3'."""
    if not tool_counts:
        return "none"
    return ", ".join(f"{name}×{count}" for name, count in sorted(tool_counts.items()))


def _format_invocations(ctx: ExecutionContext) -> str:
    """Format agent invocation count from context."""
    count = ctx.invoke_count
    if count == 0:
        return "0"
    if count == 1:
        return "1"
    return str(count)

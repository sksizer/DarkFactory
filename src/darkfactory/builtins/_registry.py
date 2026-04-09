from __future__ import annotations

from typing import Callable

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
:class:`~darkfactory.workflow.BuiltIn` task. Workflows never touch this
dict directly — they reference built-ins by name only.
"""


def builtin(name: str) -> Callable[[BuiltInFunc], BuiltInFunc]:
    """Decorator that registers a function in :data:`BUILTINS`.

    Rejects duplicate registrations with ``ValueError`` to catch typos
    and accidental overrides during development.
    """

    def decorator(func: BuiltInFunc) -> BuiltInFunc:
        if name in BUILTINS:
            raise ValueError(f"duplicate builtin registration for {name!r}")
        BUILTINS[name] = func
        return func

    return decorator

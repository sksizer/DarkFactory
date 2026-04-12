"""Shared test helpers for darkfactory.operations peer test files.

Import ``make_builtin_ctx`` in any builtin ``*_test.py`` file to avoid
redefining the same ``_make_ctx`` boilerplate in every module.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


def make_builtin_ctx(
    tmp_path: Path,
    *,
    dry_run: bool = False,
    prd_id: str = "PRD-001",
    worktree_path: Path | None = None,
    repo_root: Path | None = None,
    event_writer: object = None,
) -> MagicMock:
    """Build a minimal ``ExecutionContext`` mock for builtin unit tests.

    Parameters
    ----------
    tmp_path:
        Temporary directory (from pytest's ``tmp_path`` fixture) used as
        ``ctx.cwd`` and, when ``repo_root`` is *None*, as ``ctx.repo_root``.
    dry_run:
        Value set on ``ctx.dry_run``.
    prd_id:
        Value set on ``ctx.prd.id``.
    worktree_path:
        Value set on ``ctx.worktree_path``.  Defaults to ``None``.
    repo_root:
        Value set on ``ctx.repo_root``.  Defaults to ``tmp_path``.
    event_writer:
        Value set on ``ctx.event_writer``.  Defaults to ``None``.
    """
    ctx = MagicMock()
    ctx.dry_run = dry_run
    ctx.cwd = tmp_path
    ctx.prd.id = prd_id
    ctx.worktree_path = worktree_path
    ctx.repo_root = repo_root if repo_root is not None else tmp_path
    ctx.event_writer = event_writer
    ctx.format_string.side_effect = lambda s: s
    return ctx

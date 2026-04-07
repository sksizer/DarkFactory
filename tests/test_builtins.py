"""Tests for the builtins registry and stub primitives."""

from __future__ import annotations

import pytest

from prd_harness import builtins
from prd_harness.builtins import BUILTINS, builtin


# ---------- registry ----------


def test_registry_populated_at_import() -> None:
    """The expected set of built-in names should be registered."""
    expected = {
        "ensure_worktree",
        "set_status",
        "commit",
        "push_branch",
        "create_pr",
        "cleanup_worktree",
    }
    assert expected <= set(BUILTINS.keys())


def test_each_builtin_is_callable() -> None:
    for name, func in BUILTINS.items():
        assert callable(func), f"{name!r} is not callable"


def test_builtin_decorator_registers_function() -> None:
    """Applying @builtin adds the function to BUILTINS."""

    @builtin("_test_dynamic_one")
    def _noop(ctx):  # type: ignore[no-untyped-def]
        return None

    assert "_test_dynamic_one" in BUILTINS
    assert BUILTINS["_test_dynamic_one"] is _noop
    # Clean up so tests stay isolated
    del BUILTINS["_test_dynamic_one"]


def test_builtin_decorator_rejects_duplicates() -> None:
    """Registering the same name twice should raise ValueError."""

    @builtin("_test_dynamic_two")
    def _first(ctx):  # type: ignore[no-untyped-def]
        return None

    try:
        with pytest.raises(ValueError, match="duplicate builtin"):

            @builtin("_test_dynamic_two")
            def _second(ctx):  # type: ignore[no-untyped-def]
                return None

    finally:
        del BUILTINS["_test_dynamic_two"]


# ---------- stub behavior ----------
#
# Each stub raises NotImplementedError when actually called. Full
# implementations land in PRD-209. We test the raise path here so the
# runner's exception handling can exercise the stubs safely.


def test_ensure_worktree_stub_raises() -> None:
    with pytest.raises(NotImplementedError, match="ensure_worktree"):
        builtins.ensure_worktree(ctx=None)


def test_set_status_stub_raises() -> None:
    with pytest.raises(NotImplementedError, match="set_status"):
        builtins.set_status(ctx=None, to="in-progress")


def test_commit_stub_raises() -> None:
    with pytest.raises(NotImplementedError, match="commit"):
        builtins.commit(ctx=None, message="chore: test")


def test_push_branch_stub_raises() -> None:
    with pytest.raises(NotImplementedError, match="push_branch"):
        builtins.push_branch(ctx=None)


def test_create_pr_stub_raises() -> None:
    with pytest.raises(NotImplementedError, match="create_pr"):
        builtins.create_pr(ctx=None)


def test_cleanup_worktree_stub_raises() -> None:
    with pytest.raises(NotImplementedError, match="cleanup_worktree"):
        builtins.cleanup_worktree(ctx=None)

"""Unit tests for the @builtin decorator and BUILTINS registry."""

from __future__ import annotations

import pytest

from darkfactory.builtins._registry import BUILTINS, builtin


def test_builtin_decorator_registers_function() -> None:
    @builtin("_test_registry_one")
    def _noop(ctx):  # type: ignore[no-untyped-def]
        return None

    assert "_test_registry_one" in BUILTINS
    assert BUILTINS["_test_registry_one"] is _noop
    del BUILTINS["_test_registry_one"]


def test_builtin_decorator_rejects_duplicates() -> None:
    @builtin("_test_registry_dup")
    def _first(ctx):  # type: ignore[no-untyped-def]
        return None

    try:
        with pytest.raises(ValueError, match="duplicate builtin registration"):

            @builtin("_test_registry_dup")
            def _second(ctx):  # type: ignore[no-untyped-def]
                return None

    finally:
        del BUILTINS["_test_registry_dup"]


def test_builtin_decorator_returns_original_function() -> None:
    def _original(ctx):  # type: ignore[no-untyped-def]
        return None

    decorated = builtin("_test_registry_return")(_original)
    assert decorated is _original
    del BUILTINS["_test_registry_return"]


def test_builtin_registry_is_dict() -> None:
    assert isinstance(BUILTINS, dict)

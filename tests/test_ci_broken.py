"""Intentionally broken test to verify CI fails on test failure."""


def test_intentionally_broken() -> None:
    assert False, "This test is intentionally broken for CI verification (PRD-530 AC-3)"

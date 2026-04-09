"""Colocated unit test — verifies pytest discovers *_test.py files under src/."""

from __future__ import annotations

from pathlib import Path


def test_colocated_discovery(tmp_prd_dir: Path) -> None:
    """Trivial assertion confirming colocated discovery and root-conftest fixture work."""
    assert tmp_prd_dir.is_dir()

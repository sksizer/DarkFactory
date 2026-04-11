"""Unit tests for shared CLI helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.cli._shared import (
    CAPABILITY_ORDER,
    EFFORT_ORDER,
    PRIORITY_ORDER,
    _action_sort_key,
    _find_repo_root,
    _load,
)


# ---------- _find_repo_root ----------


def test_find_repo_root_finds_git_dir(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    subdir = tmp_path / "sub" / "dir"
    subdir.mkdir(parents=True)
    result = _find_repo_root(subdir)
    assert result == tmp_path


def test_find_repo_root_raises_when_no_git(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="could not locate git repo root"):
        _find_repo_root(tmp_path)


def test_find_repo_root_returns_start_when_git_at_start(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    result = _find_repo_root(tmp_path)
    assert result == tmp_path


# ---------- _load ----------


def test_load_raises_when_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-dir"
    with pytest.raises(SystemExit, match="PRD directory not found"):
        _load(missing)


def test_load_returns_empty_dict_for_empty_dir(tmp_path: Path) -> None:
    (tmp_path / "prds").mkdir()
    result = _load(tmp_path)
    assert result == {}


# ---------- _action_sort_key ----------


def test_action_sort_key_priority_ordering() -> None:
    from unittest.mock import MagicMock

    high = MagicMock()
    high.priority = "high"
    high.effort = "s"
    high.id = "PRD-001"

    low = MagicMock()
    low.priority = "low"
    low.effort = "s"
    low.id = "PRD-002"

    assert _action_sort_key(high) < _action_sort_key(low)


def test_action_sort_key_effort_ordering() -> None:
    from unittest.mock import MagicMock

    xs = MagicMock()
    xs.priority = "medium"
    xs.effort = "xs"
    xs.id = "PRD-001"

    xl = MagicMock()
    xl.priority = "medium"
    xl.effort = "xl"
    xl.id = "PRD-002"

    assert _action_sort_key(xs) < _action_sort_key(xl)


def test_action_sort_key_unknown_priority_sorts_last() -> None:
    from unittest.mock import MagicMock

    known = MagicMock()
    known.priority = "low"
    known.effort = "xs"
    known.id = "PRD-001"

    unknown = MagicMock()
    unknown.priority = "bogus"
    unknown.effort = "xs"
    unknown.id = "PRD-002"

    assert _action_sort_key(known) < _action_sort_key(unknown)


# ---------- ordering dicts ----------


def test_priority_order_covers_expected_values() -> None:
    for key in ("critical", "high", "medium", "low"):
        assert key in PRIORITY_ORDER


def test_effort_order_covers_expected_values() -> None:
    for key in ("xs", "s", "m", "l", "xl"):
        assert key in EFFORT_ORDER


def test_capability_order_covers_expected_values() -> None:
    for key in ("trivial", "simple", "moderate", "complex"):
        assert key in CAPABILITY_ORDER

"""Tests for darkfactory.discovery module."""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.config import find_darkfactory_dir, resolve_project_root


# ---------------------------------------------------------------------------
# find_darkfactory_dir
# ---------------------------------------------------------------------------


def test_find_in_start_directory(tmp_path: Path) -> None:
    """Finds .darkfactory/ in the start directory itself."""
    df = tmp_path / ".darkfactory"
    df.mkdir()
    assert find_darkfactory_dir(tmp_path) == df


def test_find_in_parent_directory(tmp_path: Path) -> None:
    """Walks up and finds .darkfactory/ in a parent directory."""
    df = tmp_path / ".darkfactory"
    df.mkdir()
    child = tmp_path / "sub" / "deep"
    child.mkdir(parents=True)
    assert find_darkfactory_dir(child) == df


def test_find_in_grandparent_directory(tmp_path: Path) -> None:
    """Walks up multiple levels to find .darkfactory/."""
    df = tmp_path / ".darkfactory"
    df.mkdir()
    grandchild = tmp_path / "a" / "b" / "c"
    grandchild.mkdir(parents=True)
    assert find_darkfactory_dir(grandchild) == df


def test_prefers_nearest_darkfactory(tmp_path: Path) -> None:
    """Finds the closest .darkfactory/ when multiple exist in ancestor chain."""
    # Create .darkfactory/ at two levels
    outer_df = tmp_path / ".darkfactory"
    outer_df.mkdir()
    inner = tmp_path / "sub"
    inner.mkdir()
    inner_df = inner / ".darkfactory"
    inner_df.mkdir()
    # Start from a child of inner — should find inner_df first
    child = inner / "project"
    child.mkdir()
    assert find_darkfactory_dir(child) == inner_df


def test_returns_none_when_not_found(tmp_path: Path) -> None:
    """Returns None when no .darkfactory/ exists in the directory tree.

    tmp_path is under /tmp or /var/folders (macOS), which have no .darkfactory/.
    We create a fresh subdirectory with no .darkfactory/ anywhere inside.
    """
    child = tmp_path / "project" / "src"
    child.mkdir(parents=True)
    # No .darkfactory/ anywhere in tmp_path tree
    result = find_darkfactory_dir(child)
    # Result is None (no .darkfactory/ in tmp tree) OR points to a real
    # .darkfactory/ above tmp_path (e.g. if tests run inside a project with one).
    # We can verify our tmp subtree has none:
    assert not (tmp_path / ".darkfactory").exists()
    if result is not None:
        # If found, it must be outside our tmp subtree
        assert not str(result).startswith(str(tmp_path))


# ---------------------------------------------------------------------------
# resolve_project_root - cli_dir takes precedence
# ---------------------------------------------------------------------------


def test_cli_dir_with_darkfactory(tmp_path: Path) -> None:
    """cli_dir pointing to project root with .darkfactory/ returns it."""
    df = tmp_path / ".darkfactory"
    df.mkdir()
    assert resolve_project_root(cli_dir=tmp_path) == df


def test_cli_dir_without_darkfactory(tmp_path: Path) -> None:
    """cli_dir without .darkfactory/ returns None."""
    assert resolve_project_root(cli_dir=tmp_path) is None


def test_cli_dir_beats_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--directory CLI flag wins over DARKFACTORY_DIR env var."""
    cli_project = tmp_path / "cli_project"
    cli_project.mkdir()
    cli_df = cli_project / ".darkfactory"
    cli_df.mkdir()

    env_project = tmp_path / "env_project"
    env_project.mkdir()
    (env_project / ".darkfactory").mkdir()

    monkeypatch.setenv("DARKFACTORY_DIR", str(env_project))

    result = resolve_project_root(cli_dir=cli_project)
    assert result == cli_df


def test_cli_dir_beats_walkup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--directory beats walk-up when both have .darkfactory/."""
    monkeypatch.delenv("DARKFACTORY_DIR", raising=False)

    cli_project = tmp_path / "cli_project"
    cli_project.mkdir()
    cli_df = cli_project / ".darkfactory"
    cli_df.mkdir()

    # cwd has .darkfactory/ via walk-up
    walkup = tmp_path / "walkup"
    walkup.mkdir()
    (walkup / ".darkfactory").mkdir()
    cwd = walkup / "src"
    cwd.mkdir()

    result = resolve_project_root(cli_dir=cli_project, cwd=cwd)
    assert result == cli_df


# ---------------------------------------------------------------------------
# resolve_project_root - env var fallback
# ---------------------------------------------------------------------------


def test_env_var_used_when_no_cli_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DARKFACTORY_DIR env var is used when cli_dir is not provided."""
    df = tmp_path / ".darkfactory"
    df.mkdir()

    monkeypatch.setenv("DARKFACTORY_DIR", str(tmp_path))

    assert resolve_project_root() == df


def test_env_var_without_darkfactory_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DARKFACTORY_DIR set but no .darkfactory/ inside → returns None."""
    monkeypatch.setenv("DARKFACTORY_DIR", str(tmp_path))

    assert resolve_project_root() is None


def test_env_var_beats_walkup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DARKFACTORY_DIR takes precedence over walk-up discovery."""
    # Set up env var target (used)
    env_project = tmp_path / "env_project"
    env_project.mkdir()
    env_df = env_project / ".darkfactory"
    env_df.mkdir()

    # Set up walk-up target (should be ignored)
    walkup_project = tmp_path / "walkup"
    walkup_project.mkdir()
    (walkup_project / ".darkfactory").mkdir()
    cwd = walkup_project / "sub"
    cwd.mkdir()

    monkeypatch.setenv("DARKFACTORY_DIR", str(env_project))

    result = resolve_project_root(cwd=cwd)
    assert result == env_df


# ---------------------------------------------------------------------------
# resolve_project_root - walk-up fallback
# ---------------------------------------------------------------------------


def test_walkup_from_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Walk-up from cwd finds .darkfactory/ in ancestor."""
    monkeypatch.delenv("DARKFACTORY_DIR", raising=False)

    df = tmp_path / ".darkfactory"
    df.mkdir()
    sub = tmp_path / "src" / "module"
    sub.mkdir(parents=True)

    result = resolve_project_root(cwd=sub)
    assert result == df


def test_returns_none_when_no_darkfactory_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Returns None when no .darkfactory/ is found anywhere."""
    monkeypatch.delenv("DARKFACTORY_DIR", raising=False)

    child = tmp_path / "nope" / "sub"
    child.mkdir(parents=True)
    # No .darkfactory/ in our tmp tree
    assert not (tmp_path / ".darkfactory").exists()

    result = resolve_project_root(cwd=child)
    # Either None (expected) or points outside our tmp tree (acceptable)
    if result is not None:
        assert not str(result).startswith(str(tmp_path))

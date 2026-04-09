"""Tests for darkfactory.init module."""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.init import (
    GITIGNORE_ENTRIES,
    init_project,
)


def _git_init(path: Path) -> None:
    """Create a minimal .git/ directory so init_project sees a git repo."""
    (path / ".git").mkdir()


# ---------------------------------------------------------------------------
# Full scaffold in a fresh git repo
# ---------------------------------------------------------------------------


def test_fresh_repo_creates_full_structure(tmp_path: Path) -> None:
    _git_init(tmp_path)
    msg = init_project(tmp_path)

    assert (tmp_path / ".darkfactory" / "prds").is_dir()
    assert (tmp_path / ".darkfactory" / "workflows").is_dir()
    assert (tmp_path / ".darkfactory" / "worktrees").is_dir()
    assert (tmp_path / ".darkfactory" / "transcripts").is_dir()
    assert (tmp_path / ".darkfactory" / "config.toml").is_file()
    assert msg == "Initialized"


# ---------------------------------------------------------------------------
# config.toml contains commented examples
# ---------------------------------------------------------------------------


def test_config_toml_contains_examples(tmp_path: Path) -> None:
    _git_init(tmp_path)
    init_project(tmp_path)

    config = (tmp_path / ".darkfactory" / "config.toml").read_text(encoding="utf-8")
    assert "[model]" in config
    assert "[timeouts]" in config
    assert "sonnet" in config


# ---------------------------------------------------------------------------
# .gitignore creation and update
# ---------------------------------------------------------------------------


def test_gitignore_created_with_entries(tmp_path: Path) -> None:
    _git_init(tmp_path)
    init_project(tmp_path)

    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    for entry in GITIGNORE_ENTRIES:
        assert entry in gitignore


def test_gitignore_appends_missing_entries(tmp_path: Path) -> None:
    _git_init(tmp_path)
    gitignore_path = tmp_path / ".gitignore"
    gitignore_path.write_text("*.pyc\n", encoding="utf-8")

    init_project(tmp_path)

    content = gitignore_path.read_text(encoding="utf-8")
    assert "*.pyc" in content
    for entry in GITIGNORE_ENTRIES:
        assert entry in content


def test_gitignore_no_duplicate_entries(tmp_path: Path) -> None:
    _git_init(tmp_path)
    init_project(tmp_path)
    init_project(tmp_path)  # second run

    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    for entry in GITIGNORE_ENTRIES:
        assert gitignore.count(entry) == 1


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_second_run_reports_already_initialized(tmp_path: Path) -> None:
    _git_init(tmp_path)
    init_project(tmp_path)
    msg = init_project(tmp_path)
    assert msg == "Already initialized"


def test_idempotent_does_not_modify_config(tmp_path: Path) -> None:
    _git_init(tmp_path)
    init_project(tmp_path)

    config_path = tmp_path / ".darkfactory" / "config.toml"
    config_path.write_text("# custom\n", encoding="utf-8")

    init_project(tmp_path)

    assert config_path.read_text(encoding="utf-8") == "# custom\n"


# ---------------------------------------------------------------------------
# Partial fill-in
# ---------------------------------------------------------------------------


def test_partial_fill_in_creates_missing_pieces(tmp_path: Path) -> None:
    _git_init(tmp_path)
    init_project(tmp_path)

    # Remove one subdirectory
    workflows_dir = tmp_path / ".darkfactory" / "workflows"
    workflows_dir.rmdir()
    assert not workflows_dir.exists()

    msg = init_project(tmp_path)

    assert workflows_dir.is_dir()
    # Should NOT report "Already initialized" since something was missing
    assert msg != "Already initialized"


def test_partial_fill_in_does_not_overwrite_existing(tmp_path: Path) -> None:
    _git_init(tmp_path)
    init_project(tmp_path)

    prds_dir = tmp_path / ".darkfactory" / "prds"
    sentinel = prds_dir / "keep-me.md"
    sentinel.write_text("existing content", encoding="utf-8")

    # Remove another dir to trigger partial fill-in
    (tmp_path / ".darkfactory" / "workflows").rmdir()
    init_project(tmp_path)

    assert sentinel.read_text(encoding="utf-8") == "existing content"


# ---------------------------------------------------------------------------
# Error when no .git/ directory
# ---------------------------------------------------------------------------


def test_error_when_no_git_directory(tmp_path: Path) -> None:
    # No .git/ here
    with pytest.raises(SystemExit) as exc_info:
        init_project(tmp_path)

    assert "git" in str(exc_info.value).lower()
    assert "git init" in str(exc_info.value)

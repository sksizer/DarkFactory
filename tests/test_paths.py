"""Tests for darkfactory.paths module."""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.config import user_config_dir, user_config_file, user_workflows_dir


def test_user_config_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    result = user_config_dir()
    assert result == Path.home() / ".config" / "darkfactory"


def test_user_config_dir_xdg_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = user_config_dir()
    assert result == tmp_path / "darkfactory"


def test_user_config_file_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert user_config_file() is None


def test_user_config_file_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config_dir = tmp_path / "darkfactory"
    config_dir.mkdir(parents=True)
    config_toml = config_dir / "config.toml"
    config_toml.write_text("[settings]\n", encoding="utf-8")
    result = user_config_file()
    assert result == config_toml


def test_user_workflows_dir_creates_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    workflows = user_workflows_dir()
    assert workflows == tmp_path / "darkfactory" / "workflows"
    assert workflows.is_dir()


def test_user_workflows_dir_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    first = user_workflows_dir()
    second = user_workflows_dir()
    assert first == second
    assert first.is_dir()

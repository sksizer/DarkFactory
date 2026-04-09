"""Tests for darkfactory.config — cascade resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from darkfactory.config import Config, resolve_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_toml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Built-in defaults
# ---------------------------------------------------------------------------


def test_defaults_when_no_files_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """resolve_config() returns built-in defaults when no files or env vars exist."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    # Strip all DARKFACTORY_ env vars so they don't leak in from the shell.
    for key in list(__import__("os").environ):
        if key.startswith("DARKFACTORY_"):
            monkeypatch.delenv(key, raising=False)

    config = resolve_config(env={})

    assert config.model.trivial == "haiku"
    assert config.model.simple == "sonnet"
    assert config.model.moderate == "sonnet"
    assert config.model.complex == "opus"
    assert config.style.theme == "dark"
    assert config.style.icon_set == "ascii"
    assert config.style.no_color is False


# ---------------------------------------------------------------------------
# User config overrides built-in defaults
# ---------------------------------------------------------------------------


def test_user_config_overrides_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _write_toml(
        xdg / "darkfactory" / "config.toml",
        '[style]\ntheme = "light"\n[model]\ntrivial = "sonnet"\n',
    )

    config = resolve_config(env={})

    assert config.style.theme == "light"
    assert config.model.trivial == "sonnet"
    # Unset keys keep built-in defaults
    assert config.model.complex == "opus"
    assert config.style.icon_set == "ascii"


# ---------------------------------------------------------------------------
# Project config overrides user config (AC-2)
# ---------------------------------------------------------------------------


def test_project_config_overrides_user_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _write_toml(
        xdg / "darkfactory" / "config.toml",
        '[style]\ntheme = "light"\n',
    )
    project_dir = tmp_path / "project" / ".darkfactory"
    _write_toml(
        project_dir / "config.toml",
        '[style]\ntheme = "dark"\n',
    )

    config = resolve_config(project_dir=project_dir, env={})

    assert config.style.theme == "dark"


# ---------------------------------------------------------------------------
# Env vars override config files (AC-3)
# ---------------------------------------------------------------------------


def test_env_vars_override_file_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _write_toml(
        xdg / "darkfactory" / "config.toml",
        '[model]\ntrivial = "sonnet"\n',
    )

    config = resolve_config(env={"DARKFACTORY_MODEL_TRIVIAL": "haiku"})

    assert config.model.trivial == "haiku"


def test_env_var_style_theme(tmp_path: Path) -> None:
    config = resolve_config(env={"DARKFACTORY_STYLE_THEME": "light"})
    assert config.style.theme == "light"


def test_env_var_style_no_color_bool(tmp_path: Path) -> None:
    config = resolve_config(env={"DARKFACTORY_STYLE_NO_COLOR": "true"})
    assert config.style.no_color is True

    config2 = resolve_config(env={"DARKFACTORY_STYLE_NO_COLOR": "0"})
    assert config2.style.no_color is False


# ---------------------------------------------------------------------------
# CLI flags override everything (AC-4)
# ---------------------------------------------------------------------------


def test_cli_flags_override_env_and_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _write_toml(
        xdg / "darkfactory" / "config.toml",
        '[style]\ntheme = "light"\n',
    )

    config = resolve_config(
        env={"DARKFACTORY_STYLE_THEME": "light"},
        cli_overrides={"style": {"theme": "dark"}},
    )

    assert config.style.theme == "dark"


def test_cli_overrides_model(tmp_path: Path) -> None:
    config = resolve_config(
        env={"DARKFACTORY_MODEL_TRIVIAL": "sonnet"},
        cli_overrides={"model": {"trivial": "opus"}},
    )
    assert config.model.trivial == "opus"


# ---------------------------------------------------------------------------
# Key-by-key merge — partial override doesn't wipe other keys (AC-5)
# ---------------------------------------------------------------------------


def test_partial_override_preserves_other_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _write_toml(
        xdg / "darkfactory" / "config.toml",
        '[model]\ntrivial = "sonnet"\nsimple = "opus"\n',
    )

    config = resolve_config(env={"DARKFACTORY_MODEL_TRIVIAL": "haiku"})

    # Only trivial was overridden by env var; simple from user config survives
    assert config.model.trivial == "haiku"
    assert config.model.simple == "opus"
    # Keys not in any file keep their defaults
    assert config.model.complex == "opus"


def test_project_partial_override_preserves_user_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _write_toml(
        xdg / "darkfactory" / "config.toml",
        '[style]\ntheme = "light"\nicon_set = "emoji"\n',
    )
    project_dir = tmp_path / "proj" / ".darkfactory"
    _write_toml(project_dir / "config.toml", '[style]\ntheme = "dark"\n')

    config = resolve_config(project_dir=project_dir, env={})

    assert config.style.theme == "dark"  # overridden by project
    assert config.style.icon_set == "emoji"  # preserved from user config


# ---------------------------------------------------------------------------
# Absent config files produce no errors (AC-7)
# ---------------------------------------------------------------------------


def test_absent_user_config_file_no_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = resolve_config(env={})
    assert isinstance(config, Config)


def test_absent_project_config_file_no_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    project_dir = tmp_path / "nonexistent" / ".darkfactory"
    config = resolve_config(project_dir=project_dir, env={})
    assert isinstance(config, Config)


def test_unknown_env_vars_are_ignored(tmp_path: Path) -> None:
    config = resolve_config(
        env={
            "DARKFACTORY_NONEXISTENT": "value",
            "DARKFACTORY_STYLE_UNKNOWN_KEY": "value",
            "OTHER_VAR": "value",
        }
    )
    assert isinstance(config, Config)


def test_unknown_cli_override_section_is_ignored(tmp_path: Path) -> None:
    config = resolve_config(cli_overrides={"nonexistent": {"key": "val"}}, env={})
    assert isinstance(config, Config)

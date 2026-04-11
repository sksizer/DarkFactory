"""Cascade resolver for darkfactory configuration.

Merges settings across all layers:
  built-in defaults < user config.toml < project config.toml < env vars < CLI flags

Usage::

    from darkfactory.config import resolve_config

    config = resolve_config(project_dir=Path(".darkfactory"))
    print(config.style.theme)
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from darkfactory.paths import user_config_file


@dataclass
class ModelConfig:
    """Model defaults per capability tier."""

    trivial: str = "haiku"
    simple: str = "sonnet"
    moderate: str = "sonnet"
    complex: str = "opus"


@dataclass
class StyleConfig:
    """Style settings: theme, icon set, color suppression."""

    theme: str = "dark"
    icon_set: str = "ascii"
    no_color: bool = False


@dataclass
class PathsConfig:
    """System paths resolved from project discovery."""

    project_dir: Path | None = None
    data_dir: Path | None = None
    prds_dir: Path | None = None
    archive_dir: Path | None = None


@dataclass
class Config:
    """Fully resolved configuration object."""

    model: ModelConfig = field(default_factory=ModelConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)


def load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file, returning {} if absent."""
    if not path.is_file():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


# Private alias kept for internal use within this module.
_load_toml = load_toml


def load_section(
    path: Path,
    section: str,
    fallback: str | None = None,
) -> dict[str, Any]:
    """Load a named section from a TOML config file.

    Checks ``[workflow.<section>]`` first, then falls back to
    ``[<fallback>]`` if given, or ``[<section>]`` directly.  Returns
    ``{}`` when the file is absent or the section is not present.
    """
    data = load_toml(path)
    workflow_cfg = data.get("workflow", {})
    section_data = workflow_cfg.get(section)
    if section_data is None:
        section_data = data.get(fallback if fallback is not None else section, {})
    return section_data if isinstance(section_data, dict) else {}


def _merge_section(target: object, section_data: dict[str, Any]) -> None:
    """Merge a dict into a dataclass, key-by-key (unknown keys are ignored)."""
    for key, value in section_data.items():
        if hasattr(target, key):
            setattr(target, key, value)


def _apply_env_vars(config: Config, env: dict[str, str]) -> None:
    """Apply DARKFACTORY_<SECTION>_<KEY> env vars to config.

    Examples:
        DARKFACTORY_MODEL_TRIVIAL  -> config.model.trivial
        DARKFACTORY_STYLE_THEME    -> config.style.theme
        DARKFACTORY_STYLE_NO_COLOR -> config.style.no_color (truthy strings)
    """
    prefix = "DARKFACTORY_"
    for key, value in env.items():
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix) :]
        parts = rest.split("_", 1)
        if len(parts) != 2:
            continue
        section_name, field_name = parts[0].lower(), parts[1].lower()
        section = getattr(config, section_name, None)
        if section is None or not hasattr(section, field_name):
            continue
        current = getattr(section, field_name)
        if isinstance(current, bool):
            setattr(section, field_name, value.lower() in ("1", "true", "yes"))
        else:
            setattr(section, field_name, value)


def resolve_config(
    project_dir: Path | None = None,
    env: dict[str, str] | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> Config:
    """Resolve config through the full cascade.

    Precedence (highest wins):
    1. CLI flags (*cli_overrides*)
    2. Environment variables (``DARKFACTORY_<SECTION>_<KEY>``)
    3. Project config -- ``<project_dir>/config.toml``
    4. User config -- ``~/.config/darkfactory/config.toml``
    5. Built-in defaults

    Args:
        project_dir: Path to the ``.darkfactory/`` directory.
        env: Environment dict to use (defaults to ``os.environ``).
        cli_overrides: Nested dict of overrides, e.g.
            ``{"style": {"theme": "light"}}``.
    """
    config = Config()

    if project_dir is not None:
        config.paths.project_dir = project_dir
        config.paths.data_dir = project_dir / "data"
        config.paths.prds_dir = project_dir / "data" / "prds"
        config.paths.archive_dir = project_dir / "data" / "archive"

    # Layer 1: user config
    user_file = user_config_file()
    if user_file:
        user_data = _load_toml(user_file)
        _merge_section(config.model, user_data.get("model", {}))
        _merge_section(config.style, user_data.get("style", {}))

    # Layer 2: project config
    if project_dir is not None:
        proj_file = project_dir / "config.toml"
        proj_data = _load_toml(proj_file)
        _merge_section(config.model, proj_data.get("model", {}))
        _merge_section(config.style, proj_data.get("style", {}))

    # Layer 3: env vars
    env_dict: dict[str, str] = env if env is not None else dict(os.environ)
    _apply_env_vars(config, env_dict)

    # Layer 4: CLI flags
    if cli_overrides:
        for section_name, section_data in cli_overrides.items():
            if isinstance(section_data, dict):
                section = getattr(config, section_name, None)
                if section is not None:
                    _merge_section(section, section_data)

    return config

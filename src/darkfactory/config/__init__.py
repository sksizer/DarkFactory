"""Configuration: project discovery, path constants, settings resolution, and initialization.

Submodules:

- :mod:`~darkfactory.config._config` — cascade config resolver
- :mod:`~darkfactory.config._paths` — path constants and user directory resolution
- :mod:`~darkfactory.config._discovery` — project root discovery
- :mod:`~darkfactory.config._init` — ``.darkfactory/`` scaffolding
"""

from __future__ import annotations

# _config — cascade configuration resolver
from ._config import (
    Config,
    ModelConfig,
    PathsConfig,
    StyleConfig,
    load_section,
    load_toml,
    resolve_config,
)

# _paths — path constants and user directory helpers
from ._paths import (
    DARKFACTORY_SUBDIR,
    EVENTS_SUBDIR,
    STATE_SUBDIR,
    TRANSCRIPTS_SUBDIR,
    WORKTREES_SUBDIR,
    user_config_dir,
    user_config_file,
    user_operations_dir,
    user_workflows_dir,
)

# _discovery — project root locator
from ._discovery import find_darkfactory_dir, resolve_project_root

# _init — project scaffolding
from ._init import CONFIG_SKELETON, GITIGNORE_ENTRIES, init_project

__all__ = [
    # _config
    "Config",
    "ModelConfig",
    "PathsConfig",
    "StyleConfig",
    "load_section",
    "load_toml",
    "resolve_config",
    # _paths
    "DARKFACTORY_SUBDIR",
    "EVENTS_SUBDIR",
    "STATE_SUBDIR",
    "TRANSCRIPTS_SUBDIR",
    "WORKTREES_SUBDIR",
    "user_config_dir",
    "user_config_file",
    "user_operations_dir",
    "user_workflows_dir",
    # _discovery
    "find_darkfactory_dir",
    "resolve_project_root",
    # _init
    "CONFIG_SKELETON",
    "GITIGNORE_ENTRIES",
    "init_project",
]

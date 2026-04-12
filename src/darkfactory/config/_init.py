"""Scaffold the .darkfactory/ directory structure in a project root."""

from __future__ import annotations

from pathlib import Path

GITIGNORE_ENTRIES = [
    ".darkfactory/worktrees/",
    ".darkfactory/transcripts/",
]

CONFIG_SKELETON = """\
# Darkfactory project configuration
# See https://darkfactory.dev/docs/config for all options

# [model]
# trivial = "haiku"
# simple = "sonnet"
# moderate = "sonnet"
# complex = "opus"

# [timeouts]
# xs = 5    # minutes
# s = 10
# m = 20
# l = 40
# xl = 75
"""

_REQUIRED_DIRS = [
    ".darkfactory/data/prds",
    ".darkfactory/data/archive",
    ".darkfactory/workflows",
    ".darkfactory/worktrees",
    ".darkfactory/transcripts",
]

_CONFIG_PATH = ".darkfactory/config.toml"


def _update_gitignore(project_root: Path) -> None:
    """Append missing entries to .gitignore (create if absent)."""
    gitignore = project_root / ".gitignore"
    existing_text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    existing_lines = set(existing_text.splitlines())

    missing = [e for e in GITIGNORE_ENTRIES if e not in existing_lines]
    if not missing:
        return

    prefix = ""
    if existing_text and not existing_text.endswith("\n"):
        prefix = "\n"

    with gitignore.open("a", encoding="utf-8") as fh:
        fh.write(prefix + "\n".join(missing) + "\n")


def init_project(target: Path) -> str:
    """Scaffold .darkfactory/ in target. Returns status message."""
    target = target.resolve()

    if not (target / ".git").exists():
        raise SystemExit("Not a git repository. Run `git init` first.")

    df = target / ".darkfactory"

    # Check for fully-initialized state (all dirs + config exist)
    all_present = (
        all((target / d).exists() for d in _REQUIRED_DIRS)
        and (target / _CONFIG_PATH).exists()
    )
    if all_present:
        return "Already initialized"

    # Create missing directories
    for rel in _REQUIRED_DIRS:
        d = target / rel
        d.mkdir(parents=True, exist_ok=True)

    # Write config only if it doesn't exist yet
    config_path = target / _CONFIG_PATH
    if not config_path.exists():
        config_path.write_text(CONFIG_SKELETON, encoding="utf-8")

    # Update .gitignore
    _update_gitignore(target)

    if df.exists():
        return "Initialized"
    return "Initialized"

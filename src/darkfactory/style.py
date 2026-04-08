"""Styling layer for the darkfactory CLI.

All style definitions live here. Command modules ask the :class:`Styler`
to format text by semantic role — they never hardcode colors, ANSI codes,
or icon glyphs themselves.

Architecture
------------

- :class:`Element` — enum of every semantic element that can be styled.
- :class:`StyleDef` — a bundle of color + bold/italic/underline flags.
- :class:`Theme` — maps ``Element`` → :class:`StyleDef`.
- :class:`IconSet` — maps string keys to icon glyphs.
- :data:`DARK_THEME`, :data:`LIGHT_THEME` — built-in themes.
- :data:`NERDFONT_ICONS`, :data:`ASCII_ICONS`, :data:`EMOJI_ICONS` — built-in icon sets.
- :class:`StyleConfig` — fully resolved config (theme name, icon set, no_color).
- :func:`resolve_style_config` — merges defaults → user config → project config
  → env vars → CLI flags into a single :class:`StyleConfig`.
- :class:`Styler` — renders text for a given element, honoring the active config.

Adding a new semantic element
------------------------------

1. Add a member to :class:`Element`.
2. Add ``Element.YOUR_ELEMENT: StyleDef(...)`` entries to :data:`DARK_THEME`
   and :data:`LIGHT_THEME`.
3. Optionally add icon entries to :data:`NERDFONT_ICONS` / :data:`ASCII_ICONS`.
4. Call ``styler.render(Element.YOUR_ELEMENT, text)`` at the call site.
"""

from __future__ import annotations

import io
import os
import sys
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.style import Style
from rich.text import Text


# ---------------------------------------------------------------------------
# Element — every semantic concept that can be styled
# ---------------------------------------------------------------------------


class Element(Enum):
    """Semantic roles that the styler can colorize/format."""

    # Agent streaming output
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ASSISTANT_TEXT = "assistant_text"
    ERROR = "error"
    SYSTEM = "system"
    FILE_PATH = "file_path"
    DIFF = "diff"
    TOKEN_COUNT = "token_count"
    THINKING = "thinking"
    RATE_LIMIT = "rate_limit"

    # prd tree — task kind
    KIND_EPIC = "kind_epic"
    KIND_FEATURE = "kind_feature"
    KIND_COMPONENT = "kind_component"
    KIND_TASK = "kind_task"

    # prd tree — status / priority (best-effort)
    TREE_STATUS = "tree_status"
    TREE_PRIORITY = "tree_priority"

    # prd run — result output
    RUN_SUCCESS = "run_success"
    RUN_FAILURE = "run_failure"
    RUN_HEADER = "run_header"


# ---------------------------------------------------------------------------
# StyleDef — color + decoration flags
# ---------------------------------------------------------------------------


@dataclass
class StyleDef:
    """Color + decoration bundle for one :class:`Element`."""

    color: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    dim: bool = False

    def to_rich_style(self) -> Style:
        return Style(
            color=self.color,
            bold=self.bold or None,
            italic=self.italic or None,
            underline=self.underline or None,
            dim=self.dim or None,
        )


# ---------------------------------------------------------------------------
# Theme — Element → StyleDef mapping
# ---------------------------------------------------------------------------


@dataclass
class Theme:
    """Map every semantic :class:`Element` to a :class:`StyleDef`."""

    styles: dict[Element, StyleDef] = field(default_factory=dict)

    def get(self, element: Element) -> StyleDef:
        """Return the StyleDef for *element*, or a plain StyleDef if absent."""
        return self.styles.get(element, StyleDef())


# ---------------------------------------------------------------------------
# IconSet — string key → glyph
# ---------------------------------------------------------------------------


@dataclass
class IconSet:
    """Map short string keys (e.g. ``"task"``, ``"done"``) to icon glyphs."""

    icons: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str = "") -> str:
        return self.icons.get(key, default)


# ---------------------------------------------------------------------------
# Built-in themes
# ---------------------------------------------------------------------------

DARK_THEME = Theme(
    styles={
        Element.TOOL_CALL: StyleDef(color="cyan", bold=True),
        Element.TOOL_RESULT: StyleDef(color="bright_cyan"),
        Element.ASSISTANT_TEXT: StyleDef(color="white"),
        Element.ERROR: StyleDef(color="red", bold=True),
        Element.SYSTEM: StyleDef(color="yellow"),
        Element.FILE_PATH: StyleDef(color="bright_blue", underline=True),
        Element.DIFF: StyleDef(color="green"),
        Element.TOKEN_COUNT: StyleDef(bold=True),
        Element.THINKING: StyleDef(italic=True, dim=True),
        Element.RATE_LIMIT: StyleDef(color="yellow", dim=True),
        Element.KIND_EPIC: StyleDef(color="magenta", bold=True),
        Element.KIND_FEATURE: StyleDef(color="blue", bold=True),
        Element.KIND_COMPONENT: StyleDef(color="cyan"),
        Element.KIND_TASK: StyleDef(color="green"),
        Element.TREE_STATUS: StyleDef(color="yellow"),
        Element.TREE_PRIORITY: StyleDef(color="red"),
        Element.RUN_SUCCESS: StyleDef(color="green", bold=True),
        Element.RUN_FAILURE: StyleDef(color="red", bold=True),
        Element.RUN_HEADER: StyleDef(color="bright_white", bold=True),
    }
)

LIGHT_THEME = Theme(
    styles={
        Element.TOOL_CALL: StyleDef(color="dark_cyan", bold=True),
        Element.TOOL_RESULT: StyleDef(color="cyan"),
        Element.ASSISTANT_TEXT: StyleDef(color="black"),
        Element.ERROR: StyleDef(color="red", bold=True),
        Element.SYSTEM: StyleDef(color="dark_goldenrod"),
        Element.FILE_PATH: StyleDef(color="blue", underline=True),
        Element.DIFF: StyleDef(color="dark_green"),
        Element.TOKEN_COUNT: StyleDef(bold=True),
        Element.THINKING: StyleDef(italic=True, dim=True),
        Element.RATE_LIMIT: StyleDef(color="dark_goldenrod", dim=True),
        Element.KIND_EPIC: StyleDef(color="dark_magenta", bold=True),
        Element.KIND_FEATURE: StyleDef(color="dark_blue", bold=True),
        Element.KIND_COMPONENT: StyleDef(color="teal"),
        Element.KIND_TASK: StyleDef(color="dark_green"),
        Element.TREE_STATUS: StyleDef(color="dark_goldenrod"),
        Element.TREE_PRIORITY: StyleDef(color="dark_red"),
        Element.RUN_SUCCESS: StyleDef(color="dark_green", bold=True),
        Element.RUN_FAILURE: StyleDef(color="red", bold=True),
        Element.RUN_HEADER: StyleDef(color="black", bold=True),
    }
)

THEMES: dict[str, Theme] = {
    "dark": DARK_THEME,
    "light": LIGHT_THEME,
}


# ---------------------------------------------------------------------------
# Built-in icon sets
# ---------------------------------------------------------------------------

NERDFONT_ICONS = IconSet(
    icons={
        # Task kinds
        "epic": "\uf0e8 ",
        "feature": "\uf0ad ",
        "component": "\uf1b3 ",
        "task": "\uf0ae ",
        # Status
        "done": "\uf058 ",
        "in-progress": "\uf252 ",
        "ready": "\uf0e7 ",
        "draft": "\uf040 ",
        "blocked": "\uf05e ",
        "review": "\uf06e ",
        "cancelled": "\uf00d ",
        # Priority
        "critical": "\uf071 ",
        "high": "\uf102 ",
        "medium": "\uf105 ",
        "low": "\uf103 ",
        # Streaming
        "tool_call": "\uf0ad ",
        "tool_result": "\uf00c ",
        "thinking": "\uf0eb ",
        "error": "\uf071 ",
        "system": "\uf013 ",
        # Run result
        "success": "\uf058 ",
        "failure": "\uf057 ",
    }
)

ASCII_ICONS = IconSet(
    icons={
        # Task kinds
        "epic": "E ",
        "feature": "F ",
        "component": "C ",
        "task": "T ",
        # Status
        "done": "[x] ",
        "in-progress": "[~] ",
        "ready": "[>] ",
        "draft": "[.] ",
        "blocked": "[!] ",
        "review": "[?] ",
        "cancelled": "[-] ",
        # Priority
        "critical": "!! ",
        "high": "^^ ",
        "medium": " > ",
        "low": " v ",
        # Streaming
        "tool_call": "> ",
        "tool_result": "< ",
        "thinking": "~ ",
        "error": "! ",
        "system": "* ",
        # Run result
        "success": "[+] ",
        "failure": "[X] ",
    }
)

EMOJI_ICONS = IconSet(
    icons={
        # Task kinds
        "epic": "\U0001f5c2\ufe0f ",
        "feature": "\u2728 ",
        "component": "\U0001f9e9 ",
        "task": "\u2705 ",
        # Status
        "done": "\u2705 ",
        "in-progress": "\u23f3 ",
        "ready": "\u26a1 ",
        "draft": "\U0001f4dd ",
        "blocked": "\U0001f6ab ",
        "review": "\U0001f440 ",
        "cancelled": "\u274c ",
        # Priority
        "critical": "\U0001f525 ",
        "high": "\u2b06\ufe0f ",
        "medium": "\u27a1\ufe0f ",
        "low": "\u2b07\ufe0f ",
        # Streaming
        "tool_call": "\U0001f527 ",
        "tool_result": "\U0001f4e8 ",
        "thinking": "\U0001f4ad ",
        "error": "\u274c ",
        "system": "\u2699\ufe0f ",
        # Run result
        "success": "\u2705 ",
        "failure": "\u274c ",
    }
)

ICON_SETS: dict[str, IconSet] = {
    "nerdfont": NERDFONT_ICONS,
    "ascii": ASCII_ICONS,
    "emoji": EMOJI_ICONS,
}


# ---------------------------------------------------------------------------
# Nerd Font detection
# ---------------------------------------------------------------------------


def detect_nerdfont() -> bool | None:
    """Heuristic: detect whether a Nerd Font is likely available.

    Returns ``True`` if detected, ``False`` if definitely absent, ``None``
    if inconclusive (the caller should fall back to the configured default).

    Always overridable via ``DARKFACTORY_NERDFONT=1`` (force on) or
    ``DARKFACTORY_NERDFONT=0`` (force off).
    """
    nf_env = os.environ.get("DARKFACTORY_NERDFONT", "")
    if nf_env.lower() in ("1", "true", "yes"):
        return True
    if nf_env.lower() in ("0", "false", "no"):
        return False

    # Terminal programs known to ship/support Nerd Fonts by default
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program in ("iTerm.app", "Hyper", "WezTerm"):
        return True

    # Kitty has excellent Unicode rendering
    if os.environ.get("KITTY_WINDOW_ID"):
        return True

    return None  # inconclusive


# ---------------------------------------------------------------------------
# StyleConfig — the single resolved configuration object
# ---------------------------------------------------------------------------


@dataclass
class StyleConfig:
    """Fully resolved style settings consumed by :class:`Styler`."""

    theme_name: str = "dark"
    icon_set_name: str = "ascii"
    no_color: bool = False


# ---------------------------------------------------------------------------
# Config loading helpers
# ---------------------------------------------------------------------------


def _merge_toml_file(config: dict[str, Any], path: Path) -> None:
    """Merge style settings from a TOML config file into *config*.

    Silently ignores missing files and parse errors (best-effort).
    Expected TOML shape::

        [style]
        theme = "light"
        icon_set = "nerdfont"
        no_color = false
    """
    if not path.exists():
        return
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        style_section = data.get("style", {})
        if isinstance(style_section, dict):
            for key in ("theme", "icon_set", "no_color"):
                if key in style_section:
                    config[key] = style_section[key]
    except Exception:  # noqa: BLE001 — never fail on bad/missing config
        pass


def resolve_style_config(
    *,
    theme: str | None = None,
    icon_set: str | None = None,
    no_color: bool = False,
    repo_root: Path | None = None,
) -> StyleConfig:
    """Merge all config sources into a single :class:`StyleConfig`.

    Precedence (highest wins):

    1. CLI flags (*theme*, *icon_set*, *no_color*)
    2. Environment variables (``DARKFACTORY_THEME``, ``DARKFACTORY_ICON_SET``,
       ``NO_COLOR``)
    3. Project config — ``<repo_root>/.darkfactory/config.toml``
    4. User config — ``~/.config/darkfactory/config.toml``
    5. Built-in defaults (dark theme, ascii icons, color enabled)

    Color is also automatically suppressed when stdout is not a TTY (unless
    an explicit ``--no-color`` flag or ``NO_COLOR`` env var was set and the
    caller already passes ``no_color=True``).
    """
    config: dict[str, Any] = {"theme": "dark", "icon_set": None, "no_color": False}

    # Layer 4: user config
    user_cfg = Path.home() / ".config" / "darkfactory" / "config.toml"
    _merge_toml_file(config, user_cfg)

    # Layer 3: project config (overrides user)
    if repo_root is not None:
        project_cfg = repo_root / ".darkfactory" / "config.toml"
        _merge_toml_file(config, project_cfg)

    # Layer 2: environment variables
    if os.environ.get("NO_COLOR") is not None:
        config["no_color"] = True
    env_theme = os.environ.get("DARKFACTORY_THEME")
    if env_theme:
        config["theme"] = env_theme
    env_icon_set = os.environ.get("DARKFACTORY_ICON_SET")
    if env_icon_set:
        config["icon_set"] = env_icon_set

    # Layer 1: CLI flags (highest priority)
    if no_color:
        config["no_color"] = True
    if theme is not None:
        config["theme"] = theme
    if icon_set is not None:
        config["icon_set"] = icon_set

    # Resolve icon set: explicit config > Nerd Font detection > ascii default
    resolved_icon_set: str = config.get("icon_set") or ""
    if not resolved_icon_set:
        detected = detect_nerdfont()
        resolved_icon_set = "nerdfont" if detected is True else "ascii"

    # Suppress color when stdout is not a TTY (unless already disabled above)
    no_color_final = bool(config["no_color"])
    if not no_color_final and not sys.stdout.isatty():
        no_color_final = True

    return StyleConfig(
        theme_name=str(config.get("theme", "dark")),
        icon_set_name=resolved_icon_set,
        no_color=no_color_final,
    )


# ---------------------------------------------------------------------------
# Styler — the single rendering interface for all command modules
# ---------------------------------------------------------------------------


def _render_text(text: Text, *, force_terminal: bool = False) -> str:
    """Render a Rich :class:`~rich.text.Text` to a plain string.

    When *force_terminal* is False (the default), no ANSI codes are emitted
    (plain text). When True, ANSI escape sequences are included.
    """
    buf = io.StringIO()
    console = Console(
        file=buf,
        force_terminal=force_terminal,
        no_color=not force_terminal,
        highlight=False,
        markup=False,
        width=10000,  # prevent line wrapping
    )
    console.print(text, end="")
    return buf.getvalue()


class Styler:
    """Render text elements with theming, icons, and color-aware output.

    All command modules use :class:`Styler` exclusively for any output that
    carries semantic meaning. No ANSI codes or color literals live outside
    this module.
    """

    def __init__(self, config: StyleConfig) -> None:
        self._config = config
        self._theme = THEMES.get(config.theme_name, DARK_THEME)
        self._icons = ICON_SETS.get(config.icon_set_name, ASCII_ICONS)

    @property
    def no_color(self) -> bool:
        return self._config.no_color

    @property
    def icon_set_name(self) -> str:
        return self._config.icon_set_name

    def icon(self, key: str, default: str = "") -> str:
        """Return the icon glyph for *key* from the active icon set."""
        return self._icons.get(key, default)

    def render(self, element: Element, text: str) -> str:
        """Return *text* styled for *element* as a plain string.

        When color is disabled (no TTY, ``NO_COLOR``, ``--no-color``), returns
        *text* unchanged. Otherwise returns *text* wrapped in ANSI sequences
        matching the active theme.

        Machine-readable paths (``--json``) must not call this — they use
        plain ``print()`` directly.
        """
        if self._config.no_color:
            return text
        style_def = self._theme.get(element)
        rich_text = Text(text, style=style_def.to_rich_style())
        return _render_text(rich_text, force_terminal=True)

    def kind_element(self, kind: str) -> Element:
        """Map a PRD kind string to the appropriate :class:`Element`."""
        return {
            "epic": Element.KIND_EPIC,
            "feature": Element.KIND_FEATURE,
            "component": Element.KIND_COMPONENT,
            "task": Element.KIND_TASK,
        }.get(kind, Element.KIND_TASK)

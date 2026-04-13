---
id: PRD-541
title: Add color to prd output
kind: feature
status: done
priority: medium
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-08
updated: '2026-04-08'
tags:
  - feature
---

# Add color to prd output

## Summary

Add color, icons, and text formatting to CLI output to make it easier to visually parse — particularly the high-volume agent streaming output from `prd run`, and the structured task listings from `prd tree`. Styling is driven by a single in-module configuration object so it can be tuned, themed, and eventually ported to another language.

## Motivation

When executing a workflow there is a great deal of text output from the agent, and it is difficult to distinguish the components by text alone. Tool calls, tool results, assistant text, errors, and status messages all blur together. Similarly, `tree` output is dense and hard to scan for task kind/status at a glance. Color, icons, and weight/style cues let the eye jump to the relevant region instantly.

## Requirements

### Functional

1. **Commands styled in v1:** `prd run` (agent streaming) and `prd tree`. Other commands may follow later.
2. **Agent streaming semantic elements** — each gets a distinct style:
   - Tool calls
   - Tool results
   - Assistant text
   - Errors
   - System / status messages
   - File paths
   - Diffs
   - **Token counts — bold**
   - **Thinking blocks — italic**
3. **Tree command:** task `kind` gets a color + Nerd Font icon. Best-effort initial mapping for `status` and `priority` as well; we will iterate.
4. **Theme support:** ship `light` and `dark` themes from day one. Theme selectable via config / flag / env var.
5. **Layered configuration** — settings resolve in this precedence (highest wins):
   1. CLI flag (e.g. `--theme`, `--no-color`, `--icon-set`)
   2. Environment variable (e.g. `DARKFACTORY_THEME`, `NO_COLOR`)
   3. **Project config** — `.darkfactory/config.toml` (or equivalent) at the project root
   4. **User config** — `~/.config/darkfactory/config.toml`
   5. Built-in defaults
   Project config overrides user config so a repo can pin its own look. Both files are optional; missing files are not an error.
6. **Color disable conditions** (any one disables color):
   - stdout is not a TTY
   - `NO_COLOR` environment variable is set (per no-color.org)
   - `--no-color` CLI flag passed
7. **Icon sets** — ship at least two:
   - `nerdfont` — Nerd Font glyphs (richest, default if detected)
   - `ascii` — plain ASCII fallback (`*`, `>`, `[x]`, etc.) so users without a Nerd Font still get readable output
   - (optional) `emoji` — standard Unicode emoji as a middle ground
   Selectable via config/flag/env (`--icon-set`, `DARKFACTORY_ICON_SET`).
8. **Nerd Font detection:** attempt a best-effort runtime check (e.g. probe `TERM_PROGRAM`, `NERD_FONT`, or known terminal env hints) to auto-pick `nerdfont` vs `ascii`. Detection is heuristic and **always overridable** by explicit config. If detection is inconclusive, default to the user's configured icon set, or `ascii` if none.
9. **Machine-readable output** (e.g. any `--json` mode) must remain free of ANSI escapes regardless of TTY state.

### Non-Functional

1. We are eventually going to port this code to another compiled language. Take advantage of Python features (dataclasses, enums, `rich`) but keep the styling layer **functional and well-organized** — pure data config + thin render functions, no styling logic scattered across call sites.
2. All style definitions live in a **single module** (e.g. `darkfactory/style.py`) for now. Extraction to a config file comes later.
3. Use the `rich` library for rendering.

## Technical Approach

- **Single style module** exposes:
  - An `Element` enum (or string constants) for every semantic element above.
  - A `Theme` dataclass mapping `Element → Style` (where `Style` bundles color, bold/italic/underline, etc.).
  - An `IconSet` dataclass mapping `Element → glyph`.
  - Built-in `LIGHT_THEME`, `DARK_THEME`, `NERDFONT_ICONS`, `ASCII_ICONS` (and optionally `EMOJI_ICONS`).
  - A `Styler` (or module-level functions) that takes an `Element` + text and returns a `rich`-renderable, honoring the active theme, icon set, and color-disable conditions.
- Call sites in `run` and `tree` ask the styler to format chunks by semantic role — they never hardcode colors or icons themselves.
- **Config loading** is its own small layer that merges built-in defaults → user config → project config → env vars → CLI flags into a single resolved `StyleConfig` at startup. Style module consumes the resolved object; it does not know about files.
- TTY / `NO_COLOR` / `--no-color` detection happens during config resolution and produces a "plain" styler that returns unstyled text, so call sites stay identical.
- Nerd Font detection is a single helper function (`detect_nerdfont() -> bool | None`) that the resolver consults only when the user has not explicitly chosen an icon set.

## Acceptance Criteria

- [ ] AC-1: All styling lives in a single module; no ANSI codes or color literals in command modules.
- [ ] AC-2: `prd run` visually distinguishes tool calls, tool results, assistant text, errors, system messages, file paths, and diffs.
- [ ] AC-3: Token counts in `prd run` output render bold.
- [ ] AC-4: Thinking blocks in `prd run` output render italic.
- [ ] AC-5: `prd tree` shows a color + Nerd Font icon for each task kind, with a best-effort visual treatment for status and priority.
- [ ] AC-6: `light` and `dark` themes both ship and are selectable.
- [ ] AC-7: Color is automatically suppressed when stdout is not a TTY, when `NO_COLOR` is set, or when `--no-color` is passed.
- [ ] AC-8: Any existing `--json` / machine-readable output contains no ANSI escape sequences under any condition.
- [ ] AC-9: Adding a new semantic element requires changes in only the style module + the call site that emits it.
- [ ] AC-10: User config at `~/.config/darkfactory/config.toml` and project config at `.darkfactory/config.toml` are both loaded when present, with project overriding user, and both overridden by env vars and CLI flags.
- [ ] AC-11: An `ascii` icon set is available and produces readable output with no Nerd Font installed.
- [ ] AC-12: Icon set can be explicitly chosen via config / env / `--icon-set` flag, and that choice always wins over auto-detection.

## Open Questions

<!-- Tag each with OPEN | RESOLVED | DEFERRED -->

- OPEN: Exact icon glyph choices for each task kind / status / priority — resolve by experimentation after initial implementation.
- OPEN: Reliable Nerd Font detection is hard — there is no portable API. Initial heuristic will likely lean on `TERM_PROGRAM` and a `DARKFACTORY_NERDFONT=1` opt-in env var. Acceptable that detection is imperfect as long as users can override.
- OPEN: Config file format — TOML assumed (stdlib `tomllib`); confirm before implementation.
- RESOLVED: Theme/config persisted in user + project config files from v1.
- DEFERRED: Extending styling to `list`, `show`, `status`, and other commands.
- DEFERRED: Per-element user overrides inside config files (v1 chooses theme + icon set; finer overrides come later if needed).

## References

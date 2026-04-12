---
id: PRD-627
title: Allow configuration of node package manager to use to spawn claude code and other tools
kind: feature
status: draft
priority: low
effort: m
capability: moderate
parent: null
depends_on: [PRD-629]
blocks: []
impacts: []
workflow: null
assignee: null
reviewers: []
target_version: null
created: '2026-04-11'
updated: '2026-04-11'
tags: []
---

# Allow configuration of node package manager to use to spawn claude code and other tools

## Summary

Add a `[tools] node_package_manager` key to `.darkfactory/config.toml` so
users can specify which Node package manager (pnpm, npm, bun, yarn) is used
to invoke `@anthropic-ai/claude-code`. All invocation paths — agent runner,
transcript analysis, and interactive sessions — are unified to use this
setting, removing all hardcoded `pnpm` references from source.

## Motivation

DarkFactory currently hardcodes `pnpm` as the Node package manager in three
separate places. Users who prefer `bun`, `npm`, or `yarn` cannot use the tool
without modifying source. Removing this friction is a prerequisite for broader
adoption. There is also a known bug where calling the `claude` binary directly
fails in headless mode; unifying both invocation paths to go through the
package manager runner resolves that bug as a side-effect.

## Requirements

### Functional

1. Add `[tools]` section to `.darkfactory/config.toml` with
   `node_package_manager = "pnpm"` as the default, along with a comment
   explaining the supported values and that it controls how
   `@anthropic-ai/claude-code` is invoked.
2. Add a `ToolsConfig` dataclass (`node_package_manager: str = "pnpm"`) to the
   config package (introduced in PRD-629) and wire it into `Config` and
   `resolve_config()`.
3. Validate `node_package_manager` at config-load time; raise a loud error for
   unrecognized values. Supported values: `pnpm`, `npm`, `bun`, `yarn`.
4. Implement a shared `_build_claude_command(package_manager: str, args:
   list[str]) -> list[str]` helper that maps the package manager name to the
   correct invocation prefix and appends `@anthropic-ai/claude-code` and the
   given args.
5. Update `invoke_claude()` (`invoke.py`) and its callers in `runner.py` to
   use the config value via the helper.
6. Update `analyze_transcript.py` to use the helper; remove the hardcoded
   `"pnpm"` subprocess call.
7. Update `spawn_claude()` (`utils/claude_code.py`) to use the helper instead
   of calling the `claude` binary directly. This also resolves the headless
   invocation bug.

### Non-Functional

1. No new runtime dependencies.
2. Default behavior (pnpm) is unchanged for existing users who do not add a
   `[tools]` section.
3. The helper is covered by unit tests for all four supported package managers.

## Technical Approach

**Command prefix mapping** (in a new `utils/node_runner.py` or inside the
config package):

```python
_PREFIXES: dict[str, list[str]] = {
    "pnpm": ["pnpm", "dlx"],
    "npm":  ["npx"],
    "bun":  ["bunx"],
    "yarn": ["yarn", "dlx"],
}

def build_claude_command(package_manager: str, args: list[str]) -> list[str]:
    prefix = _PREFIXES[package_manager]   # KeyError impossible after validation
    return [*prefix, "@anthropic-ai/claude-code", *args]
```

**Config validation** at `resolve_config()` boundary:

```python
SUPPORTED_PACKAGE_MANAGERS = frozenset(_PREFIXES)

if config.tools.node_package_manager not in SUPPORTED_PACKAGE_MANAGERS:
    raise ValueError(
        f"Unsupported node_package_manager: "
        f"{config.tools.node_package_manager!r}. "
        f"Supported: {sorted(SUPPORTED_PACKAGE_MANAGERS)}"
    )
```

**Affected modules:**
- `config/` — new `ToolsConfig`, validation in `resolve_config()`
- `invoke.py` — use `build_claude_command()`; remove `executable` default parameter
- `runner.py` — pass `config.tools.node_package_manager` to `invoke_claude()`
- `builtins/analyze_transcript.py` — replace hardcoded subprocess with `build_claude_command()`
- `utils/claude_code.py` — `spawn_claude()` uses `build_claude_command()`
- `.darkfactory/config.toml` — add `[tools]` section

## Acceptance Criteria

- [ ] AC-1: Setting `node_package_manager = "bun"` causes all
      `@anthropic-ai/claude-code` invocations to use `bunx
      @anthropic-ai/claude-code …`.
- [ ] AC-2: Setting `node_package_manager = "npm"` uses `npx
      @anthropic-ai/claude-code …`.
- [ ] AC-3: Setting `node_package_manager = "yarn"` uses `yarn dlx
      @anthropic-ai/claude-code …`.
- [ ] AC-4: An unrecognized value (e.g. `"pnpx"`) raises a clear error at
      config-load time, not at invocation time.
- [ ] AC-5: Default behavior (pnpm) is preserved when the `[tools]` section is
      absent.
- [ ] AC-6: `spawn_claude()` uses the package manager runner; no bare `claude`
      binary invocation remains in source.
- [ ] AC-7: No hardcoded `"pnpm"` strings remain in non-config source files.
- [ ] AC-8: `build_claude_command()` has unit tests covering all four package
      managers.

## Open Questions

<!-- Tag each with OPEN | RESOLVED | DEFERRED -->

- RESOLVED: Config stores the package manager name (`"pnpm"`, `"bun"`, etc.),
  not the runner command (`"bunx"`, `"npx"`); code maps to the correct prefix.
- RESOLVED: Both invocation paths (agent runner and interactive) use the package
  manager. The bare-`claude` path is removed; this also fixes the headless
  invocation bug.
- RESOLVED: Scoping — `spawn_claude()` and interactive sessions are in scope.
  `gh` and `git` subprocess calls are not affected.

## References

- PRD-629 — config package refactor; must land first
- `src/darkfactory/invoke.py:380` — existing `executable` parameter (never wired)
- `src/darkfactory/builtins/analyze_transcript.py:190` — hardcoded pnpm
- `src/darkfactory/utils/claude_code.py:28` — bare `claude` binary invocation

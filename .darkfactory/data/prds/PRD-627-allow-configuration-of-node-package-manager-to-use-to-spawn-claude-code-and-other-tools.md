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
updated: '2026-04-11'  # revised post-critique
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
2. Add a `ToolsConfig` dataclass with
   `node_package_manager: Literal["pnpm", "npm", "bun", "yarn"] = "pnpm"` to
   the config package (introduced in PRD-629) and wire it into `Config` and
   `resolve_config()`. Using `Literal` (not plain `str`) keeps the type
   provably exhaustive under mypy strict.
3. Validate `node_package_manager` at config-load time; raise a loud error for
   unrecognized values. Supported values: `pnpm`, `npm`, `bun`, `yarn`.
4. Create `utils/node_runner.py` exposing the following public API:
   - `build_claude_command(pm: PackageManager, args: list[str]) -> list[str]`
     — maps `pm` to its invocation prefix, appends
     `@anthropic-ai/claude-code` and `args`.
   - `is_present(pm: PackageManager) -> bool` — returns `True` if the PM
     binary is on PATH (uses `shutil.which`).
   - `check_version(pm: PackageManager) -> None` — raises `ValueError` with a
     human-readable message if the installed version is incompatible (currently
     only relevant for `yarn`: v1 lacks `dlx` support; v2+ / Berry required).
   - `validate_invocation(pm: PackageManager) -> None` — composite
     `is_present` + `check_version`; called by `build_claude_command` so
     errors surface before any subprocess is launched.
   `PackageManager = Literal["pnpm", "npm", "bun", "yarn"]` is defined in
   this module.
5. Update `invoke_claude()` (`invoke.py`) to call `resolve_config()` internally
   and use `build_claude_command(config.tools.node_package_manager, ...)`.
   Remove the existing (never-wired) `executable` parameter. Callers
   (`runner.py`, `system_runner.py`) need no changes.
6. Update `analyze_transcript.py` to use `build_claude_command()`; remove the
   hardcoded `"pnpm"` subprocess call. Note: PRD-629 owns the migration of
   this file's `load_section()` usage to `Config`; this requirement only
   covers replacing the subprocess invocation.
7. Update `spawn_claude()` (`utils/claude_code.py`) to use
   `build_claude_command()` instead of calling the bare `claude` binary. This
   also resolves the headless invocation bug.
8. Update `utils/system.py` to check presence of the configured PM binary
   (via `is_present()` from `node_runner`) rather than using
   `shutil.which("claude")`.

### Non-Functional

1. No new runtime dependencies.
2. Default behavior (pnpm) is unchanged for existing users who do not add a
   `[tools]` section.
3. The helper is covered by unit tests for all four supported package managers.
4. A pytest scan test in `tests/` asserts that no `*.py` file under
   `src/darkfactory/` (excluding `config/` and `node_runner.py`) contains the
   literal string `"pnpm"`. This enforces AC-7 automatically in CI.

## Technical Approach

**`utils/node_runner.py`** — new module, owns all PM-to-command mapping and
runtime validation:

```python
from typing import Literal
import shutil, subprocess

PackageManager = Literal["pnpm", "npm", "bun", "yarn"]

_PREFIXES: dict[PackageManager, list[str]] = {
    "pnpm": ["pnpm", "dlx"],
    "npm":  ["npx"],
    "bun":  ["bunx"],
    "yarn": ["yarn", "dlx"],
}

def build_claude_command(pm: PackageManager, args: list[str]) -> list[str]:
    validate_invocation(pm)           # fail before subprocess launch
    return [*_PREFIXES[pm], "@anthropic-ai/claude-code", *args]

def is_present(pm: PackageManager) -> bool:
    binary = _PREFIXES[pm][0]         # first token is the binary name
    return shutil.which(binary) is not None

def check_version(pm: PackageManager) -> None:
    """Raises ValueError for incompatible installed versions.
    Currently enforced only for yarn: v1 lacks `dlx` (requires v2+ / Berry).
    """
    if pm != "yarn":
        return
    result = subprocess.run(["yarn", "--version"], capture_output=True, text=True)
    major = int(result.stdout.strip().split(".")[0])
    if major < 2:
        raise ValueError(
            f"yarn v{result.stdout.strip()} does not support `dlx`. "
            "Upgrade to Yarn Berry (v2+) or choose a different package manager."
        )

def validate_invocation(pm: PackageManager) -> None:
    if not is_present(pm):
        raise ValueError(
            f"Configured node_package_manager {pm!r} is not on PATH."
        )
    check_version(pm)
```

**Config validation** at `resolve_config()` boundary — the `Literal` type
means mypy rejects unknown values statically; runtime validation is belt-and-
suspenders for values read from TOML:

```python
# In resolve_config(), after loading tools section:
_SUPPORTED: frozenset[str] = frozenset(get_args(PackageManager))
if config.tools.node_package_manager not in _SUPPORTED:
    raise ValueError(
        f"Unsupported node_package_manager: "
        f"{config.tools.node_package_manager!r}. "
        f"Supported: {sorted(_SUPPORTED)}"
    )
```

**`invoke_claude()` reads config internally** — callers (`runner.py`,
`system_runner.py`) pass no PM argument; the function calls `resolve_config()`
and passes `config.tools.node_package_manager` to `build_claude_command()`.
The `executable` parameter is removed.

**Affected modules:**
- `config/` — new `ToolsConfig`, validation in `resolve_config()`
- `utils/node_runner.py` — new module (command mapping + runtime validation)
- `invoke.py` — use `build_claude_command()`; remove `executable` parameter;
  read PM from config internally
- `builtins/analyze_transcript.py` — replace hardcoded subprocess with
  `build_claude_command()`
- `utils/claude_code.py` — `spawn_claude()` uses `build_claude_command()`
- `utils/system.py` — replace `shutil.which("claude")` with `is_present(pm)`
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
- [ ] AC-7: No hardcoded `"pnpm"` strings remain in non-config source files,
      enforced by a pytest scan test (NF-4) that fails CI if any are added.
- [ ] AC-8: `build_claude_command()` and `validate_invocation()` have unit
      tests covering all four package managers, including a test that a
      missing binary raises a clear error before subprocess launch.
- [ ] AC-9: `utils/system.py` uses `is_present(pm)` from `node_runner` rather
      than `shutil.which("claude")`; the configured PM binary governs the
      check.
- [ ] AC-10: Configuring `yarn` with Yarn v1 installed raises a `ValueError`
      naming the installed version and the v2 requirement before any subprocess
      is launched.

## Open Questions

<!-- Tag each with OPEN | RESOLVED | DEFERRED -->

- RESOLVED: Config stores the package manager name (`"pnpm"`, `"bun"`, etc.),
  not the runner command (`"bunx"`, `"npx"`); code maps to the correct prefix.
- RESOLVED: Both invocation paths (agent runner and interactive) use the package
  manager. The bare-`claude` path is removed; this also fixes the headless
  invocation bug.
- RESOLVED: Scoping — `spawn_claude()` and interactive sessions are in scope.
  `gh` and `git` subprocess calls are not affected.
- RESOLVED: `invoke_claude()` reads the package manager from `resolve_config()`
  internally. Callers (`runner.py`, `system_runner.py`) need no changes; the
  `executable` parameter is removed as dead code.
- RESOLVED: `ToolsConfig.node_package_manager` uses
  `Literal["pnpm", "npm", "bun", "yarn"]` (not `str`) to give mypy exhaustive
  type coverage. TOML validation at `resolve_config()` provides belt-and-
  suspenders for runtime.
- RESOLVED: Runner validation (presence + version) lives in `utils/node_runner.py`
  and is called by `build_claude_command()` before subprocess launch. Yarn v1
  is explicitly detected and rejected with a human-readable error. No version
  constraints apply to pnpm, npm, or bun.
- RESOLVED: Hardcoded-string enforcement uses a pytest scan test (not a custom
  ruff plugin). The test lives in `tests/` and scans `src/darkfactory/**/*.py`
  excluding `config/` and `node_runner.py`.

## References

- PRD-629 — config package refactor; must land first
- `src/darkfactory/invoke.py:380` — existing `executable` parameter (never wired)
- `src/darkfactory/builtins/analyze_transcript.py:190` — hardcoded pnpm
- `src/darkfactory/utils/claude_code.py:28` — bare `claude` binary invocation
- `src/darkfactory/utils/system.py:11` — `shutil.which("claude")` to replace

---
id: PRD-564
title: Interactive project init with configurable prd/workflow path overrides
kind: feature
status: draft
priority: medium
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-222-general-purpose-tool]]"
blocks: []
impacts:
  - src/darkfactory/init.py
  - src/darkfactory/cli.py
  - src/darkfactory/config.py
  - src/darkfactory/discovery.py
  - tests/test_init.py
  - tests/test_config.py
  - tests/test_discovery.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-09
updated: '2026-04-09'
tags:
  - harness
  - cli
  - config
  - init
  - ergonomics
---

# Interactive project init with configurable prd/workflow path overrides

## Summary

Enhance `prd init` so that a first-time project setup prompts the user for where PRDs and workflows should live (defaulting to `.darkfactory/prds/` and `.darkfactory/workflows/`), and record any non-default choices in `config.toml` under a new `[paths]` section. Discovery and all path-consuming code paths honor those overrides, so teams that want their PRDs visible at the repo root (e.g. `prds/` next to `README.md`) can have that without forking directory conventions.

This is an enhancement layered on top of the PRD-222 general-purpose-tool epic — specifically extending PRD-222.2 (init), PRD-222.6 (cascade config), and the discovery layer from PRD-222.1. It should not be scheduled until those land.

## Motivation

The default `.darkfactory/` layout buries PRDs under a hidden directory, which is fine for harness state but awkward for projects where PRDs are the primary planning artifact and should be top-level visible to collaborators browsing the repo. Several users have asked for their PRDs to live at `prds/` or `docs/prds/` instead. The init experience should also guide new users through this choice rather than silently scaffolding a layout they may want to change later.

## Requirements

### Interactive init (default behavior)

1. Running `prd init` in a fresh project prompts, in order:
   - "Where should PRDs be stored?" — default `.darkfactory/prds/`
   - "Where should workflows be stored?" — default `.darkfactory/workflows/`
   - Prompts accept repo-relative paths (e.g. `prds`, `docs/prds`) or absolute paths. Repo-relative is the documented recommendation.
2. `--defaults` / `-y` flag skips all prompts and uses `.darkfactory/prds/` and `.darkfactory/workflows/` silently. This preserves the non-interactive behavior PRD-222.2 originally specced.
3. `--prds <path>` and `--workflows <path>` flags set values without prompting (and imply `--defaults` for any unasked question).
4. Combining `--defaults` with `--prds` / `--workflows` is allowed — flag values win, unasked questions take defaults.
5. When run in a non-TTY (CI, piped stdin), init behaves as if `--defaults` was passed and prints a note saying so. Never hang waiting for input.

### `config.toml` `[paths]` section

6. Add a new `[paths]` section to the config schema:
   ```toml
   [paths]
   # Repo-relative (recommended) or absolute. Omit keys to use defaults.
   prds = "prds"
   workflows = ".darkfactory/workflows"
   ```
7. Only non-default values are written to `config.toml` by `prd init`. If the user accepts both defaults, no `[paths]` section is written at all (keeps the generated file minimal).
8. `config.toml` continues to live at `<project>/.darkfactory/config.toml` regardless of where prds/workflows are relocated. The `.darkfactory/` directory is still the anchor that discovery finds.
9. Path values are resolved relative to the project root (the directory containing `.darkfactory/`), not relative to `.darkfactory/` itself or the cwd. Absolute paths are used as-is.

### Discovery and path resolution

10. Extend `resolve_config()` from PRD-222.6 to populate a `PathsConfig` dataclass with resolved absolute `prds_dir` and `workflows_dir` paths.
11. Replace the current hardcoded `<root>/.darkfactory/prds/` and `<root>/.darkfactory/workflows/` in the discovery/CLI glue with the resolved values from `Config.paths`.
12. Existing `--prd-dir` and `--workflows-dir` CLI flags continue to work as runtime overrides with highest precedence.
13. Resolution order (later wins): built-in defaults → user config `[paths]` → project config `[paths]` → env vars (`DARKFACTORY_PATHS_PRDS`, `DARKFACTORY_PATHS_WORKFLOWS`) → CLI flags.

### Re-init behavior

14. Running `prd init` on an already-initialized project detects the current state of `[paths]` and prompts whether to change them (reading the existing values as the new defaults). Changing a value updates `config.toml` only — moving existing files is out of scope and must be done manually. If the user changes a path while files still exist at the old location, print a warning listing the orphaned files.

### `config.toml` skeleton updates

18. The generated `config.toml` skeleton (from PRD-222.2) gets a commented-out `[paths]` section showing both options, only materialized as uncommented when the user chooses non-defaults during init.
19. When the user picks non-default paths, the resulting `config.toml` has a real `[paths]` section with only the overridden keys.

## Technical Approach

### `src/darkfactory/init.py` — changes on top of PRD-222.2

```python
from dataclasses import dataclass
from pathlib import Path
import sys

@dataclass
class InitChoices:
    prds_dir: str   # repo-relative or absolute, as the user typed it
    workflows_dir: str
    move_existing: bool = False

def prompt_choices(defaults: InitChoices, interactive: bool) -> InitChoices:
    """Prompt the user, or return defaults if non-interactive."""
    if not interactive or not sys.stdin.isatty():
        return defaults
    prds = input(f"PRDs directory [{defaults.prds_dir}]: ").strip() or defaults.prds_dir
    workflows = input(f"Workflows directory [{defaults.workflows_dir}]: ").strip() or defaults.workflows_dir
    return InitChoices(prds_dir=prds, workflows_dir=workflows)

def init_project(
    target: Path,
    *,
    interactive: bool = True,
    prds_override: str | None = None,
    workflows_override: str | None = None,
    use_defaults: bool = False,
) -> str:
    """Scaffold .darkfactory/, prompt for paths, write config.toml, optionally migrate."""
    ...
```

### `src/darkfactory/config.py` — extension

Add a `PathsConfig` dataclass to the cascade resolver from PRD-222.6:

```python
@dataclass
class PathsConfig:
    prds: str = ".darkfactory/prds"
    workflows: str = ".darkfactory/workflows"

    def resolved_prds(self, project_root: Path) -> Path:
        p = Path(self.prds)
        return p if p.is_absolute() else (project_root / p)

    def resolved_workflows(self, project_root: Path) -> Path:
        p = Path(self.workflows)
        return p if p.is_absolute() else (project_root / p)

@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
```

The `resolve_config()` function merges `[paths]` sections from each layer the same way it already merges `[model]` and `[style]`.

### `src/darkfactory/discovery.py` — caller changes

Discovery itself still finds `.darkfactory/`. The CLI glue in `main()` changes from:

```python
prd_dir = darkfactory_dir / "prds"
workflows_dir = darkfactory_dir / "workflows"
```

to:

```python
config = resolve_config(darkfactory_dir, ...)
project_root = darkfactory_dir.parent
prd_dir = args.prd_dir or config.paths.resolved_prds(project_root)
workflows_dir = args.workflows_dir or config.paths.resolved_workflows(project_root)
```

### `tests/test_init.py` — new cases

- Interactive prompts accept defaults when user hits enter.
- Interactive prompts accept custom relative paths.
- `--defaults` in a TTY skips prompts.
- Non-TTY stdin behaves as `--defaults` and notes this in output.
- `--prds` and `--workflows` flags bypass prompts.
- Non-default choices produce a `[paths]` section in `config.toml`.
- Default choices produce no `[paths]` section.
- Re-running init on an existing project prompts with current values as defaults.
- Changing a path on re-init updates config and warns about orphaned files at the old location.

### `tests/test_config.py` — new cases

- `[paths]` section parses correctly.
- `PathsConfig.resolved_prds()` returns absolute paths for both relative and absolute inputs.
- Project config `[paths]` overrides user config `[paths]` key-by-key.
- Env vars `DARKFACTORY_PATHS_PRDS` / `DARKFACTORY_PATHS_WORKFLOWS` override file config.

### `tests/test_discovery.py` — new cases

- CLI consumers use `config.paths.resolved_prds()` instead of hardcoded `.darkfactory/prds/`.
- A project with `paths.prds = "prds"` in config.toml resolves the prd_dir to `<root>/prds/`.

## Acceptance Criteria

- [ ] AC-1: `prd init` in a TTY prompts for PRDs and workflows directories with sensible defaults.
- [ ] AC-2: `prd init --defaults` scaffolds without prompting, using `.darkfactory/prds/` and `.darkfactory/workflows/`.
- [ ] AC-3: `prd init --prds docs/prds --workflows .darkfactory/workflows` uses flag values without prompting.
- [ ] AC-4: Non-TTY stdin behaves as `--defaults` and prints a notice.
- [ ] AC-5: Non-default paths are written to a `[paths]` section in `config.toml`; default paths produce no `[paths]` section.
- [ ] AC-6: `Config.paths.resolved_prds()` returns correct absolute paths for both repo-relative and absolute inputs.
- [ ] AC-7: All subcommands (`status`, `next`, `run`, etc.) honor `[paths]` overrides — a project with `paths.prds = "prds"` finds PRDs at `<root>/prds/`.
- [ ] AC-8: CLI flags `--prd-dir` and `--workflows-dir` still win over config values at runtime.
- [ ] AC-9: Re-running `prd init` on an initialized project prompts with current values as defaults and updates `config.toml` if changed.
- [ ] AC-10: Changing a path on re-init prints a warning listing orphaned files at the old location (no automatic move).
- [ ] AC-11: Env vars `DARKFACTORY_PATHS_PRDS` / `DARKFACTORY_PATHS_WORKFLOWS` override file config but lose to CLI flags.

## Open Questions

1. Should `[paths]` support globbing or multiple roots (e.g. split leaf PRDs from epics)? Not in scope for this PRD; call out as a future extension if requested.
2. Does `user-level ~/.config/darkfactory/config.toml` meaningfully benefit from a `[paths]` section? A user-level default of `paths.prds = "prds"` would apply to every project the user touches, which is probably surprising. Consider restricting `[paths]` resolution to project-level config only, and ignoring any `[paths]` found in user config (with a warning).

## Dependencies

- **PRD-222** (general-purpose-tool epic) and its children must be complete. Specifically this PRD extends:
  - PRD-222.1 (discovery) — already done
  - PRD-222.2 (prd init subcommand) — extended with interactive prompts and `[paths]` writing
  - PRD-222.6 (cascade resolver for config) — extended with `PathsConfig`
- Should not be scheduled until PRD-222 is marked done.

## Assessment (2026-04-11)

- **Value**: 3/5 — the projects-want-PRDs-at-top-level case is real
  for multi-adopter usage but hypothetical today. The `prd init`
  interactive layer also carries a "good first impression" effect
  that doesn't show up in direct utility metrics.
- **Effort**: m — new interactive prompts in `init.py`, new `[paths]`
  section in `config.toml`, extending `PathsConfig` (already exists)
  with resolve-relative-to-project-root helpers, call-site updates
  to use `config.paths.resolved_prds()`. State survey confirms
  `cli/init_cmd.py` exists but is scaffold-only.
- **Current state**: scaffolded. `PathsConfig` is already used
  throughout (post PRD-622). The resolver primitive is in place.
  The interactive prompting layer and `[paths]` materialization in
  the generated `config.toml` aren't.
- **Gaps to fully implement**:
  - `init.py` — add `prompt_choices()` with `isatty()` check.
  - `init_cmd.py` — wire the prompts and `--prds` / `--workflows`
    flags into the argparse parser.
  - `config.py` — `PathsConfig.resolved_prds()` /
    `resolved_workflows()` relative-to-project-root helpers (if
    not already there).
  - Env var support (`DARKFACTORY_PATHS_PRDS` etc.).
  - Re-init behavior: detect existing `[paths]`, prompt with them
    as defaults, warn on orphaned files at the old location.
  - Tests for TTY / non-TTY paths.
- **Recommendation**: defer — do-next when a second-adopter scenario
  is imminent. The current dogfooding usage works fine with the
  default `.darkfactory/data/prds/` layout. Keep this as the first
  onboarding PRD to land once we're seriously recruiting adopters.
  Note: the "depends on PRD-222 being marked done" dependency is
  already satisfied (PRD-222 is done).

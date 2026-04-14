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
  - python/darkfactory/init.py
  - python/darkfactory/cli/init_cmd.py
  - python/darkfactory/config.py
  - python/darkfactory/discovery.py
  - python/darkfactory/paths.py
  - tests/test_init.py
  - tests/test_config.py
  - tests/test_discovery.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-09
updated: '2026-04-11'
tags:
  - harness
  - cli
  - config
  - init
  - ergonomics
  - feature
---

# Interactive project init with configurable prd/workflow path overrides

## Summary

Enhance `prd init` so that a first-time project setup prompts the user for where PRDs and workflows should live (defaulting to `.darkfactory/data/prds/` and `.darkfactory/workflows/`), and record any non-default choices in `config.toml` under the existing `[paths]` section. Discovery and all path-consuming code paths honor those overrides, so teams that want their PRDs visible at the repo root (e.g. `prds/` next to `README.md`) can have that without forking directory conventions.

## Context — what PRD-622 already delivered

PRD-622 merged a data-model refactor that partially overlaps with the original scope of this PRD:

- `Config` now has a nested `PathsConfig` (`config.paths.project_dir`, `data_dir`, `prds_dir`, `archive_dir`) in `python/darkfactory/config.py` + `python/darkfactory/paths.py`.
- `prd init` now scaffolds `.darkfactory/data/prds/` and `.darkfactory/data/archive/` (not the old `.darkfactory/prds/`).
- The `--prd-dir` CLI flag was **removed**. `--directory` / `DARKFACTORY_DIR` is the only runtime override for the project root.
- `cli.py` was split into the `python/darkfactory/cli/` package; init logic lives in `cli/init_cmd.py` delegating to `python/darkfactory/init.py`.
- An `ensure_data_layout()` migration runs on every CLI entry and prompts to move legacy `.darkfactory/prds/` → `.darkfactory/data/prds/`.

The remaining novel scope of this PRD is: (1) **interactive prompting** for PRD/workflow locations during `prd init`, and (2) **honoring repo-root-relative path overrides** (e.g. `prds = "prds"`) written into `config.toml [paths]` so that all subcommands find PRDs outside `.darkfactory/`. Discovery itself still anchors on `.darkfactory/`.

## Motivation

The default `.darkfactory/` layout buries PRDs under a hidden directory, which is fine for harness state but awkward for projects where PRDs are the primary planning artifact and should be top-level visible to collaborators browsing the repo. Several users have asked for their PRDs to live at `prds/` or `docs/prds/` instead. The init experience should also guide new users through this choice rather than silently scaffolding a layout they may want to change later.

## Requirements

### Interactive init (default behavior)

1. Running `prd init` in a fresh project prompts, in order:
   - "Where should PRDs be stored?" — default `.darkfactory/data/prds/`
   - "Where should workflows be stored?" — default `.darkfactory/workflows/`
   - Prompts accept repo-relative paths (e.g. `prds`, `docs/prds`) or absolute paths. Repo-relative is the documented recommendation.
2. `--defaults` / `-y` flag skips all prompts and uses `.darkfactory/data/prds/` and `.darkfactory/workflows/` silently. This preserves the current non-interactive behavior of `prd init`.
3. `--prds <path>` and `--workflows <path>` flags set values without prompting (and imply `--defaults` for any unasked question).
4. Combining `--defaults` with `--prds` / `--workflows` is allowed — flag values win, unasked questions take defaults.
5. When run in a non-TTY (CI, piped stdin), init behaves as if `--defaults` was passed and prints a note saying so. Never hang waiting for input.

### `config.toml` `[paths]` section

6. PRD-622 already added a `[paths]` section to `Config` (`PathsConfig`) with `project_dir`, `data_dir`, `prds_dir`, `archive_dir`. Extend it so those values can be read from `config.toml` (currently they're computed from `project_dir`) and add a `workflows_dir` field. Accepted keys in `config.toml`:
   ```toml
   [paths]
   # Repo-relative (recommended) or absolute. Omit keys to use defaults.
   prds = "prds"
   workflows = ".darkfactory/workflows"
   ```
7. Only non-default values are written to `config.toml` by `prd init`. If the user accepts both defaults, no `[paths]` override keys are written at all (keeps the generated file minimal).
8. `config.toml` continues to live at `<project>/.darkfactory/config.toml` regardless of where prds/workflows are relocated. The `.darkfactory/` directory is still the anchor that discovery finds.
9. Path values are resolved relative to the project root (the directory containing `.darkfactory/`), not relative to `.darkfactory/` itself or the cwd. Absolute paths are used as-is.
10. The `archive_dir` stays as a sibling of `prds_dir` (i.e. if the user sets `prds = "prds"`, archive becomes `prds-archive/` or an equivalent adjacent location). Alternative: keep `archive_dir` under `.darkfactory/data/archive/` regardless — decide in OPEN questions.

### Discovery and path resolution

11. Extend `resolve_config()` (see `python/darkfactory/config.py`) to read `[paths] prds = …` / `workflows = …` from `config.toml` and populate `Config.paths` with resolved absolute paths. Today `PathsConfig` is computed from `project_dir`; after this PRD the `prds_dir` / `workflows_dir` values become the resolved override (or the default `project_dir/data/prds` / `project_dir/workflows` if no override).
12. Replace all remaining callers of the old `.darkfactory/prds/` or `.darkfactory/data/prds/` hardcoding in the CLI glue with `config.paths.prds_dir` / `config.paths.workflows_dir`. (Most load-sites already use `args.data_dir` from `cli/_shared.py`; those need to become paths-aware.)
13. The `--prd-dir` CLI flag was removed in PRD-622 and is NOT reintroduced. CLI override for the project root stays as `--directory` / `DARKFACTORY_DIR`. There is no per-invocation `--prds` flag outside `prd init` itself.
14. Resolution order (later wins): built-in defaults → user config `[paths]` → project config `[paths]` → env vars (`DARKFACTORY_PATHS_PRDS`, `DARKFACTORY_PATHS_WORKFLOWS`).

### Re-init behavior

14. Running `prd init` on an already-initialized project detects the current state of `[paths]` and prompts whether to change them (reading the existing values as the new defaults). Changing a value updates `config.toml` only — moving existing files is out of scope and must be done manually. If the user changes a path while files still exist at the old location, print a warning listing the orphaned files.

### `config.toml` skeleton updates

18. The generated `config.toml` skeleton (from PRD-222.2) gets a commented-out `[paths]` section showing both options, only materialized as uncommented when the user chooses non-defaults during init.
19. When the user picks non-default paths, the resulting `config.toml` has a real `[paths]` section with only the overridden keys.

## Technical Approach

### `python/darkfactory/init.py` — add interactive prompting on top of the existing scaffolder

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

### `python/darkfactory/config.py` / `python/darkfactory/paths.py` — extension

`PathsConfig` already exists (added in PRD-622). Today it is derived from a single `project_dir` argument. This PRD adds optional override fields plus a resolver that honors repo-relative or absolute values read from `config.toml [paths]`:

```python
@dataclass
class PathsConfig:
    project_dir: Path
    data_dir: Path
    prds_dir: Path
    archive_dir: Path
    workflows_dir: Path  # NEW in this PRD

def resolve_paths(
    project_dir: Path,
    *,
    prds_override: str | None = None,       # from config.toml [paths].prds or env
    workflows_override: str | None = None,  # from config.toml [paths].workflows or env
) -> PathsConfig:
    """Resolve PathsConfig with optional repo-relative/absolute overrides."""
    ...
```

The `resolve_config()` function (in `python/darkfactory/config.py`) merges `[paths]` override keys from each layer the same way it already merges `[model]` and `[style]`, then feeds them into `resolve_paths()`.

### `python/darkfactory/discovery.py` and `cli/_shared.py` — caller changes

Discovery itself still finds `.darkfactory/`. The CLI glue in `cli/main.py` / `cli/_shared.py` currently derives `args.data_dir = darkfactory_dir / "data"` and then passes it down as `load_all(data_dir=...)`. After this PRD:

```python
config = resolve_config(darkfactory_dir)
args.data_dir = config.paths.data_dir              # unchanged default
args.prds_dir = config.paths.prds_dir              # may be e.g. <root>/prds
args.workflows_dir = config.paths.workflows_dir    # may be e.g. <root>/docs/workflows
```

Call-sites inside `cli/` that currently call `load_all(args.data_dir)` must be audited: when the `prds_dir` override diverges from `data_dir/prds`, `load_all` needs to accept a `prds_dir` parameter (or we teach `PathsConfig.prds_dir` to be the single source of truth and pass that instead).

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
- [ ] AC-2: `prd init --defaults` scaffolds without prompting, using `.darkfactory/data/prds/` and `.darkfactory/workflows/`.
- [ ] AC-3: `prd init --prds docs/prds --workflows .darkfactory/workflows` uses flag values without prompting.
- [ ] AC-4: Non-TTY stdin behaves as `--defaults` and prints a notice.
- [ ] AC-5: Non-default paths are written to a `[paths]` section in `config.toml`; default paths produce no `[paths]` override keys.
- [ ] AC-6: `PathsConfig` resolves both repo-relative (e.g. `prds`) and absolute inputs to correct absolute paths.
- [ ] AC-7: All subcommands (`status`, `next`, `run`, etc.) honor `[paths]` overrides — a project with `paths.prds = "prds"` finds PRDs at `<root>/prds/`.
- [ ] AC-8: Runtime override `--directory` / `DARKFACTORY_DIR` still resolves the project root; no per-invocation `--prd-dir` flag is re-added.
- [ ] AC-9: Re-running `prd init` on an initialized project prompts with current values as defaults and updates `config.toml` if changed.
- [ ] AC-10: Changing a path on re-init prints a warning listing orphaned files at the old location (no automatic move).
- [ ] AC-11: Env vars `DARKFACTORY_PATHS_PRDS` / `DARKFACTORY_PATHS_WORKFLOWS` override file config.

## Open Questions

1. Should `[paths]` support globbing or multiple roots (e.g. split leaf PRDs from epics)? Not in scope for this PRD; call out as a future extension if requested.
2. Does `user-level ~/.config/darkfactory/config.toml` meaningfully benefit from a `[paths]` section? A user-level default of `paths.prds = "prds"` would apply to every project the user touches, which is probably surprising. Consider restricting `[paths]` resolution to project-level config only, and ignoring any `[paths]` found in user config (with a warning).
3. When the user overrides `prds_dir` to e.g. `prds/`, where does `archive_dir` go? Options: (a) sibling `prds-archive/`, (b) stay under `.darkfactory/data/archive/` regardless, (c) second override `paths.archive = "prds-archive"`. Tilts toward (b) — archive is harness state, not a primary browsing surface.
4. How does `ensure_data_layout()` (the PRD-622 legacy-migration helper) interact with overrides? If the user has `paths.prds = "prds"` but there's a stale `.darkfactory/prds/` directory from before migration, should migration still offer to move those files into the new `<root>/prds/` location, or just into `.darkfactory/data/prds/`?

## Dependencies

- **PRD-222** (general-purpose-tool epic) and **PRD-622** (data model refactor) are both prerequisites. PRD-622 already delivered the base `PathsConfig`, the `.darkfactory/data/` layout, and the `ensure_data_layout()` migration hook. This PRD extends that foundation with interactive prompting and user-configurable overrides.

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
  Note: both PRD-222 and PRD-622 dependencies are already satisfied.

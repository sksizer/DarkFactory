---
id: PRD-629
title: Refactor config and discovery into a config package
kind: refactor
status: draft
priority: medium
effort: s
capability: simple
parent: null
depends_on: []
blocks: [PRD-627]
impacts: []
workflow: null
assignee: null
reviewers: []
target_version: null
created: '2026-04-11'
updated: '2026-04-11'
tags: []
---

# Refactor config and discovery into a config package

## Summary

Move `config.py` and `discovery.py` into a `config/` subpackage, rename the
internal `load_toml` to `_load_toml`, lift `[timeouts]`, `[analysis]`, and
`[events]` TOML sections into typed `Config` sub-dataclasses, and eliminate
direct `load_section()` callers so all config flows through `resolve_config()`.

## Motivation

`discovery.py` and `config.py` are tightly coupled — discovery finds the
project directory, config loads from it. They belong in the same module
boundary. Additionally, three internal modules (`cli/run.py`,
`builtins/analyze_transcript.py`, `builtins/commit_events.py`) call
`load_section()` directly, bypassing the cascade and leaving their sections
untyped. This violates "parse at the boundary, trust types internally." Fixing
it now unblocks PRD-627, which needs to add a new typed config section and
can't do so cleanly without this foundation.

## Requirements

### Functional

1. Create `src/darkfactory/config/` package; preserve `from darkfactory.config
   import resolve_config, Config` as the stable public surface.
2. Move `config.py` content into `config/__init__.py` (or `config/_config.py`
   with re-exports from `__init__.py`).
3. Move `discovery.py` → `config/discovery.py`; update the single caller
   (`cli/main.py`).
4. Remove the `_load_toml = load_toml` alias; rename `load_toml` to
   `_load_toml` throughout. It was never part of the public API.
5. Add `TimeoutsConfig`, `AnalysisConfig`, and `EventsConfig` dataclasses
   (mirroring the TOML sections already in use) and wire them into `Config` and
   `resolve_config()`.
6. Update `cli/run.py`, `builtins/analyze_transcript.py`, and
   `builtins/commit_events.py` to consume typed fields from a passed `Config`
   object instead of calling `load_section()` directly.
7. Once all callers are gone, underscore `load_section` → `_load_section` (or
   remove it if no internal use remains).

### Non-Functional

1. Pure structural refactor — no behavior changes.
2. All existing mypy and pytest checks pass after the move.
3. No new runtime dependencies.

## Technical Approach

Resulting structure:

```
src/darkfactory/config/
    __init__.py        # re-exports: resolve_config, Config, ToolsConfig, …
    _config.py         # dataclasses + resolve_config implementation
    _discovery.py      # find_darkfactory_dir, resolve_project_root
```

`Config` gains three new typed sections:

```python
@dataclass
class TimeoutsConfig:
    xs: int = 5
    s: int = 10
    m: int = 20
    l: int = 40
    xl: int = 75

@dataclass
class AnalysisConfig:
    min_severity: str = "warning"
    model_default: str = "haiku"
    model_severe: str = "sonnet"

@dataclass
class EventsConfig:
    # keys populated from [events] section; defaults TBD from usage
    ...
```

`resolve_config()` loads these sections the same way as `model` and `style`
today. Callers that currently call `load_section()` are updated to receive a
`Config` object and read the relevant typed field.

## Acceptance Criteria

- [ ] AC-1: `from darkfactory.config import resolve_config, Config` works
      unchanged from all existing call sites.
- [ ] AC-2: `from darkfactory.discovery import resolve_project_root` is
      replaced by `from darkfactory.config import resolve_project_root` (old
      path removed).
- [ ] AC-3: No module outside `darkfactory/config/` imports `_load_toml` or
      `_load_section`.
- [ ] AC-4: No module calls `load_section()` directly; all config access flows
      through a `Config` object.
- [ ] AC-5: `mypy --strict` and `pytest` pass with no new errors.

## Open Questions

<!-- Tag each with OPEN | RESOLVED | DEFERRED -->

- RESOLVED: `load_section` stays public until all callers are migrated; goes
  private (or is removed) as part of this PRD once migration is done.

## References

- PRD-627 — depends on this refactor to add `ToolsConfig` cleanly

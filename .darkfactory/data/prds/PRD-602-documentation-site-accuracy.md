---
id: PRD-602
title: Documentation site accuracy overhaul
kind: task
status: review
priority: medium
effort: m
capability: moderate
parent:
depends_on: []
blocks: []
impacts:
  - site/src/content/docs/
workflow:
target_version:
created: 2026-04-09
updated: '2026-04-11'
tags:
  - docs
  - quality
---

# Documentation site accuracy overhaul

## Problem

PR #146 (documentation site) has ~30 review comments identifying inaccuracies between the docs and the actual codebase. The docs were likely generated from an outline or LLM output without verifying against the current API. Key issues:

### API field names
- `AgentTask` docs use `prompt_file`/`allowed_tools` — actual API is `prompts`/`tools`
- `ShellTask` docs use `command` — actual field is `cmd`
- `ExecutionContext` documented fields don't match actual dataclass
- `set_status` kwarg documented as `status` — actual is `to`
- `ensure_worktree` documented with `base_ref` kwarg it doesn't accept

### Paths
- Worktrees documented under `.darkfactory/worktrees/` — actual location is `.worktrees/`
- Transcripts documented at `.darkfactory/transcripts/` — actual is `.harness-transcripts/`
- Lock files documented with wrong naming convention
- PRD storage documented at `.darkfactory/prds/` — actual location (post PRD-622) is `.darkfactory/data/prds/` for active PRDs and `.darkfactory/data/archive/` for terminal-state PRDs

### Module paths (post PRD-622 refactor)
- Any reference to `src/darkfactory/prd.py` or `from darkfactory.prd import ...` is stale — the module is now the `src/darkfactory/model/` package, imported as `from darkfactory.model import PRD, load_all, save, set_status, archive, ...`
- `src/darkfactory/cli.py` is no longer a monolith — it is now the `src/darkfactory/cli/` package with one module per subcommand (`cli/new.py`, `cli/status.py`, `cli/archive.py`, etc.)
- The `--prd-dir` CLI flag has been removed — only `--directory` / `DARKFACTORY_DIR` is used to override the project root
- `Config` now has a nested `PathsConfig` section (`config.paths.project_dir`, `config.paths.data_dir`, `config.paths.prds_dir`, `config.paths.archive_dir`)
- `prd archive PRD-NNN` is a new command (terminal-state PRDs only; transitive-terminal guardrail)

### Behavioral inaccuracies
- Priority semantics inverted (higher wins, docs say lower wins)
- `cleanup_worktree` described as default behavior — it's opt-in
- Lock scope described as per-command — it's per-run
- CLI examples use non-existent subcommands (`prd execute`)
- Builtin names wrong (`open_pr` → `create_pr`, `ensure_branch` → `ensure_worktree`)
- Sentinel format missing required colon suffix
- Workflow plan output examples don't match actual output
- `[model]` config described as effort-based — actual is capability-based

## Requirements

1. Audit every code example and API reference against the current source.
2. Fix all field names, paths, and behavioral descriptions.
3. Verify sentinel format, CLI output examples, and config sections match reality.
4. Update all imports and module-path references to reflect the PRD-622 data-model refactor (`darkfactory.model` package, `.darkfactory/data/prds/` layout, no `--prd-dir` flag).
5. Document the new `prd archive` command and terminal-state archival behaviour.
6. Document `PathsConfig` and the deterministic frontmatter serializer (canonical field order, date/wikilink quoting).

## Acceptance criteria

- [ ] All `AgentTask`, `ShellTask`, `BuiltIn`, `ExecutionContext` references match `src/darkfactory/workflow.py`
- [ ] All path references match actual runtime locations, including `.darkfactory/data/prds/` and `.darkfactory/data/archive/`
- [ ] All CLI output examples match `prd plan`/`prd run` output
- [ ] All config examples match `src/darkfactory/` config handling, including `config.paths.*`
- [ ] Sentinel format uses colon form (`PRD_EXECUTE_OK:`)
- [ ] All Python snippets import from `darkfactory.model` (not `darkfactory.prd`)
- [ ] `prd archive` command is documented with its guardrails
- [ ] No references to the removed `--prd-dir` flag remain

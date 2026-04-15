---
id: PRD-638
title: Promote TypeScript to primary `prd` CLI and prefix Python recipes with `py-`
kind: task
status: draft
priority: medium
effort: m
capability: moderate
parent: null
depends_on: []
blocks: []
impacts: []
workflow: null
assignee: null
reviewers: []
target_version: null
created: '2026-04-14'
updated: '2026-04-14'
tags: []
---

# Promote TypeScript to primary `prd` CLI and prefix Python recipes with `py-`

## Summary

Rename every existing Python-facing `justfile` recipe with a `py-` prefix (`prd` → `py-prd`, `test` → `py-test`, `typecheck` → `py-typecheck`, etc.) and promote the TypeScript CLI to the unprefixed names (`ts-prd` → `prd`, `ts-test` → `test`, `ts-typecheck` → `typecheck`, etc.). This makes TypeScript the default implementation contributors reach for and encodes that the Python port is now in migration-to-deprecation mode.

## Motivation

The TypeScript port ([[PRD-635-typescript-scaffold-and-core-types]], [[PRD-636-typescript-utils-layer]], [[PRD-637-typescript-workflow-engine]]) is the target implementation; Python is the legacy implementation we're migrating away from. Keeping Python as the default `just prd` / `just test` means every contributor and every piece of muscle memory continues to pull toward the legacy code. Flipping the defaults:

- Puts the TS implementation on the critical path for daily development, surfacing gaps faster.
- Makes Python invocations explicit (`just py-prd`), which is what we want as it winds down.
- Aligns tooling ergonomics with the project's direction before the TS CLI accumulates users who'd have to re-learn commands later.

Today `ts/src/cli/index.ts` is just `export {}` — there is no TS entry point to promote. This PRD therefore covers both the entry-point plumbing *and* the recipe rename in one atomic migration.

## Requirements

### Functional

1. **TS CLI entry point.** Provide `ts/src/cli/main.ts` exporting `main(argv: string[]): Promise<number>`, plus `ts/src/cli/bin.ts` as the executable shim that calls `main(process.argv.slice(2))` and sets `process.exitCode`.
2. **Stub subcommand surface.** The TS CLI need not implement real subcommands in this PRD; `--help`, no-args, and unknown-command behavior are sufficient. Real subcommands land in follow-up PRDs.
3. **Recipe rename — Python side.** Every current Python-facing recipe in `justfile` gains a `py-` prefix:
    - `prd *ARGS` → `py-prd *ARGS`
    - `test` → `py-test`
    - `typecheck` → `py-typecheck`
    - `format` → `py-format`
    - `lint` → `py-lint`
    - `format-check` → `py-format-check`
4. **Recipe rename — TS side becomes default.** The existing `ts-*` recipes are renamed to the unprefixed forms, and a new `prd` recipe wires into the TS CLI:
    - new `prd *ARGS` recipe running `cd ts && bun run src/cli/bin.ts {{ARGS}}`
    - `ts-test` → `test`
    - `ts-typecheck` → `typecheck`
    - `ts-format` → `format`
    - `ts-lint` → `lint`
    - `ts-build` → `build`
    - `ts-install` → `install`
5. **No aliases or shims.** Old recipe names are removed outright, not kept as aliases. Per project principle: "Hard failures over silent degradation" — running `just test` should execute TS tests, not silently dispatch to Python.
6. **Callers updated.** Any repo-internal references to the renamed recipes (scripts, CI configs, docs, CLAUDE.md, README) are updated in the same change.
7. **Exit code semantics for the new `prd` recipe** match Python's: `0` on success, non-zero on error, `--help` exits `0`.

### Non-Functional

1. No new runtime dependencies beyond what `ts/package.json` already declares (`js-yaml`, `ts-pattern`).
2. CLI execution path must not throw across the process boundary — errors surface as typed `Result` values internally and are rendered + exit-coded at the outer `main`, consistent with `ts/ARCHITECTURE.md` "Result types over exceptions".
3. Peer test colocated with the CLI module (`ts/src/cli/main_test.ts`) covering: success exit code, unknown-command exit code, `--help` output.
4. `just py-test`, `just py-typecheck`, `just py-lint`, `just py-format-check` must continue to pass after the rename — the Python implementation is not being modified, just re-prefixed.
5. `just default` (`@just --list`) output is the contributor-facing signal of this migration; no separate announcement is required, but the README/CLAUDE.md should be updated so future readers see the new names.

## Technical Approach

- **New files:**
    - `ts/src/cli/main.ts` — exports `main(argv): Promise<number>`. Parses argv, dispatches to a (stub) subcommand registry, returns exit code.
    - `ts/src/cli/bin.ts` — `#!/usr/bin/env bun` shim; imports `main`, invokes it, sets `process.exitCode`.
    - `ts/src/cli/main_test.ts` — peer tests.
- **Updated files:**
    - `ts/src/cli/index.ts` — re-export `main` (replace the current `export {}`).
    - `ts/package.json` — add `"bin": { "darkfactory": "./src/cli/bin.ts" }`.
    - `justfile` — full rewrite of recipe names per the rename table above.
    - Repo-wide grep for old recipe names (`just prd`, `just test`, `just ts-test`, etc.) in `README.md`, `CLAUDE.md`, `docs/`, `scripts/`, any CI configs, and any tooling hooks; update each hit.
- **Argument parsing:** manual `argv` inspection for now (subcommand is `argv[0]`, flags are simple). Defer a parsing library until the TS subcommand surface grows.
- **Rename mechanics:** the `justfile` rename is a single commit; the TS CLI scaffolding is the preceding commit(s). Bundling rename + scaffold ensures `just prd` is never broken between commits.
- **Ties to existing work:** this PRD establishes the TS CLI entry point that [[PRD-637-typescript-workflow-engine]] and later PRDs register subcommands against.

## Acceptance Criteria

- [ ] AC-1: `just prd` invokes the TypeScript CLI (not Python), prints help, exits `0`.
- [ ] AC-2: `just prd --help` prints help and exits `0`.
- [ ] AC-3: `just prd bogus-subcommand` prints an unknown-command error to stderr and exits non-zero.
- [ ] AC-4: `just py-prd --help` invokes the Python CLI and prints its existing help output.
- [ ] AC-5: `just test` runs TypeScript tests (`bun test`) and passes.
- [ ] AC-6: `just py-test` runs Python tests (`uv run pytest`) and passes.
- [ ] AC-7: `just typecheck`, `just lint`, `just format`, `just format-check`, `just build`, `just install` all dispatch to the TypeScript toolchain; their `py-` prefixed counterparts dispatch to the Python toolchain.
- [ ] AC-8: `just --list` shows no recipe named `ts-prd`, `ts-test`, `ts-typecheck`, `ts-format`, `ts-lint`, `ts-build`, or `ts-install` — the `ts-` prefix is fully retired.
- [ ] AC-9: `just --list` shows no unprefixed Python recipes; every Python-facing recipe is now `py-*`.
- [ ] AC-10: `ts/src/cli/main_test.ts` covers success, unknown-command, and `--help` cases and passes under `just test`.
- [ ] AC-11: `README.md` and `CLAUDE.md` reference the new recipe names; no stale `just ts-*` or unprefixed Python references remain.
- [ ] AC-12: Grep of the repo finds no live references to the old `ts-*` or unprefixed Python recipe names outside of historical PRD files in `.darkfactory/data/prds/PRD-*.md`, this PRD's own body, and git history.
- [ ] AC-13: All `ShellTask(cmd="just …")` invocations in `python/darkfactory/workflow/definitions/prd/**/workflow.py` are updated to use `py-*` recipe names so existing Python-driven PRD workflows continue to run.
- [ ] AC-14: Agent-visible prompts in `python/darkfactory/workflow/definitions/prd/**/prompts/*.md` are updated to reference `py-*` recipes so agents invoke the right commands.
- [ ] AC-15: `tests/test_workflow.py`, `tests/test_workflow_templates.py`, and `python/darkfactory/cli/plan_test.py` pass after their string assertions are updated to match the new recipe names.
- [ ] AC-16: `site/src/content/docs/**/*.mdx` and `.darkfactory/data/prds/README.md` are updated to match the resolved decision on marketing/docs site content (see Open Questions).

## Call-Site Audit (2026-04-14)

Repo-wide grep for `just (prd|test|typecheck|format|lint|build|format-check|ts-*)` finds **186 hits across 85 files**. Breakdown:

### Live, load-bearing call sites — must update in lockstep

- **`justfile`** — the rename itself.
- **Python workflow runtime** — these `ShellTask` invocations execute the renamed recipe at runtime; if we don't update them, every active Python-driven PRD workflow breaks on the next run:
    - `python/darkfactory/workflow/definitions/prd/default/workflow.py:83-86` — `just test`, `just format`, `just lint format-check`, `just typecheck`
    - `python/darkfactory/workflow/definitions/prd/task/workflow.py` (4 hits)
    - `python/darkfactory/workflow/definitions/prd/extraction/workflow.py` (1 hit)
    - `python/darkfactory/workflow/_core.py` (1 hit)
- **Python workflow prompts** — agent-visible text; agents read these to decide what commands to run:
    - `python/darkfactory/workflow/definitions/prd/default/prompts/task.md` (3 hits)
    - `python/darkfactory/workflow/definitions/prd/task/prompts/task.md` (3 hits)
    - `python/darkfactory/workflow/definitions/prd/extraction/prompts/role.md` (1 hit)
- **Python test suite** — tests assert recipe names in strings:
    - `tests/test_workflow.py` (5 hits)
    - `tests/test_workflow_templates.py` (5 hits)
    - `python/darkfactory/cli/plan_test.py` (2 hits)
- **`README.md`** (7 hits) — lines 40–44 and 92–93 document the recipe surface.

These must all move to `py-*` in the same change.

### Marketing/docs site — update to reflect new primary surface

- `site/src/content/docs/index.mdx` (1 hit)
- `site/src/content/docs/getting-started/first-workflow.mdx` (2 hits)
- `site/src/content/docs/guides/verification.mdx` (5 hits)
- `site/src/content/docs/concepts/workflows.mdx` (12 hits)

These reference `just test` etc. as documentation examples. Since the TS CLI won't have equivalent subcommands yet, the correct framing depends on intent: if the docs describe the *public* `prd` workflow surface, update to whatever surface users see; if they describe *internal* development commands, update to `py-*`. Most of these are in ShellTask examples that will eventually target TS — flagging this as an open question below.

### `.darkfactory/data/prds/README.md` (4 hits)

Contributor-facing doc explaining the PRD directory. Update.

### Historical PRD files (~70 files, ~90 hits)

Every `.darkfactory/data/prds/PRD-###-*.md` file except this one references old recipe names as historical context. **Do not update** — these are immutable records of past work. The rename doesn't rewrite history.

### Not affected

- No `.github/workflows/` directory exists — nothing to update in CI.
- `scripts/test.sh`, `scripts/install-hooks.sh` — neither references any `just` recipe.
- `mise.toml` — tool version declarations only, no recipe references.

## Open Questions

- **RESOLVED** — Recipe naming scheme: TS commands take the unprefixed names (`prd`, `test`, …), Python commands get `py-` prefix. Confirmed by author 2026-04-14.
- **RESOLVED** — Keep aliases for the old names? No. Hard cutover.
- **RESOLVED** — `pyproject.toml`'s `[project.scripts]` `prd = "darkfactory.cli:main"` stays as `prd`. That's the published-package surface; the `py-` prefix is a repo-development concern only. Confirmed by author 2026-04-14.
- **RESOLVED** — CI audit: no `.github/workflows/` exists, `scripts/` and `mise.toml` are clean. Confirmed 2026-04-14.
- **OPEN** — `site/src/content/docs/**` uses `just test` etc. in `ShellTask` workflow examples. These are illustrative docs showing how workflows call tools. Options:
    - (a) Update to `just py-test` — accurate to the renamed Python-side recipes.
    - (b) Leave as `just test` — assumes docs describe the eventual TS-primary world.
    - (c) Rewrite examples to use a generic placeholder like `just <your-test-recipe>`.
    - Leaning (a) — the examples are concrete and should match the repo's actual recipes today. Revisit (b) once the TS CLI has the matching subcommands.
- **DEFERRED** — Long-term: once the TS CLI reaches parity, remove the `py-*` recipes entirely. Out of scope for this PRD.

## References

- [[PRD-635-typescript-scaffold-and-core-types]] — TS scaffold this entry point plugs into
- [[PRD-636-typescript-utils-layer]] — Result/subprocess utilities the CLI will use for error rendering
- [[PRD-637-typescript-workflow-engine]] — will register the first real subcommands against this entry point

---
id: "PRD-500"
title: "Migrate harness to darkfactory repo"
kind: epic
status: ready
priority: high
effort: m
capability: moderate
parent: null
depends_on: []
blocks:
  - "[[PRD-501-darkfactory-scaffold]]"
  - "[[PRD-502-darkfactory-port-source]]"
  - "[[PRD-503-darkfactory-port-tests-workflows]]"
  - "[[PRD-504-darkfactory-cli-defaults]]"
  - "[[PRD-505-darkfactory-verify-and-push]]"
  - "[[PRD-510-prd-new-subcommand]]"
  - "[[PRD-520-pumice-harness-cleanup]]"
impacts: []  # epic: no direct file impacts — children declare theirs
workflow: null
target_version: null
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - migration
  - darkfactory
---

# Migrate harness to darkfactory repo

## Summary

Extract the PRD harness from `tools/prd-harness/` in pumice into its own standalone repository at https://github.com/sksizer/darkfactory. The migration is mechanical — copy files, rename the Python package from `prd_harness` to `darkfactory`, update paths that currently assume the nested pumice layout, and verify everything still runs against the harness's own dev-PRDs.

## Motivation

The harness is reaching a point where it has its own development velocity, its own test suite, its own task backlog (see PRD-200..211 and beyond), and is being used to drive work on itself. Keeping it as a subdirectory of pumice has friction:

- Its work tracking (dev-PRDs) is under a project that doesn't own the work
- Its CI, release, and publishing story is coupled to pumice
- Pumice contributors get noise from harness-only changes
- The tool's identity is obscured when it's nested under `tools/`

Extracting it to `darkfactory` gives it independent lifecycle while keeping pumice lean. The harness already works fine — nothing needs to change about its behavior — it just needs a new home.

## Requirements

1. The Python package is renamed from `prd_harness` to `darkfactory` (imports become `from darkfactory.workflow import BuiltIn`).
2. All source files, tests, workflows, and dev-PRDs are copied from `tools/prd-harness/` to the darkfactory repo root.
3. Dev-PRDs move to `prds/` at the darkfactory repo root (not `dev-prds/`).
4. CLI defaults are updated: `--prd-dir` defaults to `prds/` (at repo root), `--workflows-dir` defaults to `workflows/` (at repo root). No more `tools/prd-harness/` prefix.
5. `mise.toml` is ported and simplified (python + uv only; no tauri/rust/node).
6. `pyproject.toml` is updated to reflect the new package name and repository URL.
7. The harness's own test suite (200+ tests) passes in darkfactory.
8. `mypy --strict` passes in darkfactory.
9. `just prd status --prd-dir prds` (or equivalent) works end-to-end against the dev-PRDs inside darkfactory.
10. First commit to darkfactory is pushed, squash-free, with the full harness history.

## Technical Approach

See child PRDs for the detailed decomposition:

- **PRD-501**: Scaffold the darkfactory repo (pyproject.toml, mise.toml, .gitignore, README, justfile)
- **PRD-502**: Port source tree with `prd_harness → darkfactory` rename
- **PRD-503**: Port tests and workflows (same rename)
- **PRD-504**: Update CLI defaults for standalone operation
- **PRD-505**: Verify end-to-end and make the first commit

And follow-ups that depend on the migration:

- **PRD-510**: Add `prd new <title>` subcommand for creating draft PRDs
- **PRD-520**: Remove `tools/prd-harness/` from pumice in a separate pumice PR

## Acceptance Criteria

- [ ] AC-1: `darkfactory/src/darkfactory/` exists with all modules renamed from `prd_harness`.
- [ ] AC-2: `darkfactory/tests/` has all tests passing.
- [ ] AC-3: `darkfactory/workflows/default/` exists with the default workflow.
- [ ] AC-4: `darkfactory/prds/` contains the migrated dev-PRDs (renumbered if needed).
- [ ] AC-5: `mise install && uv sync && uv run pytest` passes in a fresh clone of darkfactory.
- [ ] AC-6: `uv run mypy src tests workflows` passes with `strict = true`.
- [ ] AC-7: `uv run prd status` works against `darkfactory/prds/` after clone.
- [ ] AC-8: First commit pushed to `main` on darkfactory, visible at github.com/sksizer/darkfactory.

## Open Questions

- [ ] **OPEN**: Should we carry the full commit history (git filter-repo), or start fresh with a single initial commit? Starting fresh is simpler but loses the work history from PR #51 through #67.
- [ ] **DEFERRED**: CI setup (GitHub Actions for lint + test + mypy) — scope for a follow-up after the initial migration lands.
- [ ] **DEFERRED**: PyPI publishing — future concern; initial users install via `uv tool install git+https://github.com/sksizer/darkfactory`.

## References

- https://github.com/sksizer/darkfactory — target repo
- `docs/prd/PRD-110-prd-harness.md` — the original harness spec
- `tools/prd-harness/` — current location being migrated from

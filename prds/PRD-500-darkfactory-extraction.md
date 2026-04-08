---
id: "PRD-500"
title: "Extract harness into darkfactory repo"
kind: epic
status: done
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
  - "[[PRD-530-darkfactory-ci-setup]]"
  - "[[PRD-540-darkfactory-pypi-publishing]]"
impacts: []  # epic: no direct file impacts — children declare theirs
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - extraction
  - darkfactory
---

# Extract harness into darkfactory repo

## Summary

Extract the PRD harness from `tools/prd-harness/` in pumice into its own standalone repository at https://github.com/sksizer/darkfactory. The extraction is mechanical — copy files, rename the Python package from `prd_harness` to `darkfactory`, update paths that currently assume the nested pumice layout, and verify everything still runs against the harness's own dev-PRDs. Full git history is carried over via `git filter-repo` rather than starting fresh.

## Motivation

The harness is reaching a point where it has its own development velocity, its own test suite, its own task backlog (see PRD-200..212 and beyond), and is being used to drive work on itself. Keeping it as a subdirectory of pumice has friction:

- Its work tracking (dev-PRDs) is under a project that doesn't own the work
- Its CI, release, and publishing story is coupled to pumice
- Pumice contributors get noise from harness-only changes
- The tool's identity is obscured when it's nested under `tools/`

Extracting it to `darkfactory` gives it independent lifecycle while keeping pumice lean. The harness already works fine — nothing needs to change about its behavior — it just needs a new home.

**Terminology note**: this epic is called "extraction" rather than "migration" because we're splitting an existing piece of code out of a larger codebase into its own repository. "Migration" usually implies transforming data in place; this is a code-split operation.

## Requirements

1. The Python package is renamed from `prd_harness` to `darkfactory` (imports become `from darkfactory.workflow import BuiltIn`).
2. All source files, tests, workflows, and dev-PRDs are copied from `tools/prd-harness/` to the darkfactory repo root.
3. **Full commit history is carried over** via `git filter-repo --subdirectory-filter tools/prd-harness` (or equivalent). The darkfactory repo's history shows every individual PRD landing — PR #51 onwards — not a single squash commit.
4. Dev-PRDs move to `prds/` at the darkfactory repo root (not `dev-prds/`).
5. CLI defaults are updated: `--prd-dir` defaults to `prds/` (at repo root), `--workflows-dir` defaults to `workflows/` (at repo root). No more `tools/prd-harness/` prefix.
6. `mise.toml` is ported and simplified (python + uv only; no tauri/rust/node).
7. `pyproject.toml` is updated to reflect the new package name and repository URL.
8. The harness's own test suite (215+ tests) passes in darkfactory.
9. `mypy --strict` passes in darkfactory.
10. `just prd status --prd-dir prds` (or equivalent) works end-to-end against the dev-PRDs inside darkfactory.
11. First commits pushed to `main` on darkfactory include the preserved history.

## Technical Approach

See child PRDs for the detailed decomposition:

- **PRD-501**: Scaffold the darkfactory repo (pyproject.toml, mise.toml, .gitignore, README, justfile) — now also covers the `git filter-repo` history carry-over step.
- **PRD-502**: Port source tree with `prd_harness → darkfactory` rename
- **PRD-503**: Port tests and workflows (same rename)
- **PRD-504**: Update CLI defaults for standalone operation
- **PRD-505**: Verify end-to-end and push everything

And follow-ups that depend on the extraction:

- **PRD-510**: Add `prd new <title>` subcommand for creating draft PRDs
- **PRD-520**: Remove `tools/prd-harness/` from pumice in a separate pumice PR
- **PRD-530**: Set up CI (GitHub Actions) for darkfactory
- **PRD-540**: Set up PyPI publishing for darkfactory

## Acceptance Criteria

- [ ] AC-1: `darkfactory/src/darkfactory/` exists with all modules renamed from `prd_harness`.
- [ ] AC-2: `darkfactory/tests/` has all tests passing.
- [ ] AC-3: `darkfactory/workflows/default/` exists with the default workflow.
- [ ] AC-4: `darkfactory/prds/` contains the extracted dev-PRDs.
- [ ] AC-5: `mise install && uv sync && uv run pytest` passes in a fresh clone of darkfactory.
- [ ] AC-6: `uv run mypy src tests workflows` passes with `strict = true`.
- [ ] AC-7: `uv run prd status` works against `darkfactory/prds/` after clone.
- [ ] AC-8: Commit history shows individual PRD landings from PR #51 onwards (not a single squash).
- [ ] AC-9: History pushed to `main` on darkfactory, visible at github.com/sksizer/darkfactory.

## Open Questions

- [x] **RESOLVED**: Carry full commit history via `git filter-repo --subdirectory-filter tools/prd-harness`. Starting fresh is simpler but loses the PR #51..#71 history. See PRD-501 for the implementation step.
- [x] **RESOLVED**: CI setup — moved to PRD-530 as a follow-up (draft).
- [x] **RESOLVED**: PyPI publishing — moved to PRD-540 as a follow-up (draft).

## References

- https://github.com/sksizer/darkfactory — target repo
- `docs/prd/PRD-110-prd-harness.md` — the original harness spec
- `tools/prd-harness/` — current location being extracted from
- [[PRD-530-darkfactory-ci-setup]]
- [[PRD-540-darkfactory-pypi-publishing]]

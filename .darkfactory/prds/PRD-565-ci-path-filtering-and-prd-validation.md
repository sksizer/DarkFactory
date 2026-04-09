---
id: PRD-565
title: CI path filtering with dedicated PRD validation workflow
kind: feature
status: done
priority: high
effort: s
capability: simple
parent:
depends_on: []
blocks:
  - "[[PRD-565.1-ci-path-filter]]"
  - "[[PRD-565.2-prd-validate-workflow]]"
  - "[[PRD-565.3-branch-protection-config]]"
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-09
updated: 2026-04-09
tags:
  - harness
  - ci
  - validation
  - ergonomics
---

# CI path filtering with dedicated PRD validation workflow

## Summary

Split CI into path-filtered workflows so that markdown/PRD-only changes skip the expensive Python test+typecheck suite, while PRD validation (`prd validate`) runs on every PR regardless of what changed. A new lightweight `prd-validate.yml` workflow handles PRD-specific checks using the existing `prd validate` subcommand. The main `ci.yml` gains path filters so it only runs when source code, tests, or dependency files change.

## Motivation

The current `ci.yml` runs `pytest` and `mypy` on every PR — including PRD-only changes that touch nothing but `.darkfactory/prds/*.md`. This wastes CI minutes and creates unnecessary wait times for planning work. Meanwhile, PRD structural validation (schema, references, cycles) isn't enforced in CI at all — errors are only caught when someone runs `prd validate` locally.

## Requirements

### Path-filtered main CI

1. `ci.yml` triggers on `push` to `main` (unchanged) and `pull_request`, but only when relevant paths change:
   ```yaml
   paths:
     - 'src/**'
     - 'tests/**'
     - 'pyproject.toml'
     - 'uv.lock'
     - '.github/workflows/ci.yml'
   ```
2. Push to `main` continues to run unconditionally (safety net — always validate main).
3. The existing `test` job content (`uv sync`, `pytest`, `mypy`) is unchanged.

### Dedicated PRD validation workflow

4. New `.github/workflows/prd-validate.yml` runs on every `pull_request` and `push` to `main` — no path filter. PRD validation is cheap and should always run.
5. The workflow installs the project (`uv sync`) and runs `uv run prd validate`.
6. Non-zero exit from `prd validate` fails the workflow.
7. The workflow should be a required status check on PRs, just like CI.

### PRD validation scope

8. The existing `prd validate` subcommand already checks:
   - Filename ↔ id consistency
   - Missing dependency/blocks/parent references
   - Dependency DAG cycles
   - Containment tree cycles
   - Container PRDs with non-empty impacts
   - Impact overlap warnings (ready PRDs)
9. No new validation logic is needed in this PRD — the existing `cmd_validate` is sufficient. Future schema validation enhancements (e.g. required fields, valid status enum, valid kind enum) are out of scope and should be separate PRDs if desired.

### GitHub branch protection

10. Both `ci.yml` (test job) and `prd-validate.yml` (validate job) should be listed as required status checks. Since `ci.yml` now uses path filters, GitHub will skip it for PRD-only PRs — configure the branch protection rule to only require `prd-validate` as strictly required, while `ci / test` uses "require when applicable" (the path-filtered behavior GitHub supports for required checks).

## Technical Approach

### `.github/workflows/ci.yml` — modified

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    paths:
      - 'src/**'
      - 'tests/**'
      - 'pyproject.toml'
      - 'uv.lock'
      - '.github/workflows/ci.yml'
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv python install 3.12
      - run: uv sync
      - run: uv run pytest
      - run: uv run mypy src tests
```

### `.github/workflows/prd-validate.yml` — new

```yaml
name: PRD Validation
on:
  push:
    branches: [main]
  pull_request:
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - run: uv python install 3.12
      - run: uv sync
      - run: uv run prd validate
```

### Branch protection updates

- Add `PRD Validation / validate` as a required status check (always required).
- Update `CI / test` to use "Require branches to be up to date" with the path-filtered skip behavior — GitHub automatically handles this for path-filtered workflows when configured as required checks.

## Acceptance Criteria

- [ ] AC-1: A PR that only touches `.darkfactory/prds/*.md` files does NOT trigger `ci.yml` (no pytest/mypy run).
- [ ] AC-2: A PR that only touches `.darkfactory/prds/*.md` files DOES trigger `prd-validate.yml`.
- [ ] AC-3: A PR that touches `src/**` or `tests/**` triggers both `ci.yml` and `prd-validate.yml`.
- [ ] AC-4: Push to `main` triggers both workflows unconditionally.
- [ ] AC-5: `prd-validate.yml` runs `uv run prd validate` and fails the check on non-zero exit.
- [ ] AC-6: A PRD with a broken reference (e.g. `depends_on` pointing to a nonexistent PRD) causes the validation workflow to fail.
- [ ] AC-7: Both status checks appear on PRs; PRD-only PRs can merge without waiting for the skipped CI check.

## Notes

- The `uv sync` step in `prd-validate.yml` installs the full project since `prd validate` is part of the `darkfactory` package. If install time becomes a concern, a future optimization could create a minimal install target, but this is unnecessary for now — `uv sync` with caching is fast.
- `prd-status-on-merge.yml` (existing) is unrelated and unchanged by this work.

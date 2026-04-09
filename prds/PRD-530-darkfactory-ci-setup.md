---
id: PRD-530
title: Set up CI for darkfactory
kind: task
status: ready
priority: medium
effort: s
capability: simple
parent: "[[PRD-500-darkfactory-extraction]]"
depends_on:
  - "[[PRD-505-darkfactory-verify-and-push]]"
blocks: []
impacts:
  - (darkfactory repo) .github/workflows/ci.yml
workflow:
target_version:
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - extraction
  - ci
---

# Set up CI for darkfactory

## Summary

Once the darkfactory extraction is live, add a GitHub Actions workflow that runs `pytest` and `mypy --strict` on every push and PR. This is a follow-up to PRD-500 — extraction first, CI second — so the initial push doesn't get blocked on CI plumbing.

## Requirements

1. `.github/workflows/ci.yml` runs on `push` to `main` and on every `pull_request`.
2. CI installs python via `actions/setup-python` (or mise) and uv via `astral-sh/setup-uv`.
3. CI runs `uv sync`, `uv run pytest`, and `uv run mypy src tests workflows`.
4. CI fails the build on any test failure or mypy error.
5. README gets a CI badge linking to the workflow.

## Technical Approach

Standard uv-based GitHub Actions workflow:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
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
      - run: uv run mypy src tests workflows
```

Status `draft` until PRD-505 lands and we can iterate on the real repo.

## Acceptance Criteria

- [ ] AC-1: `.github/workflows/ci.yml` exists in darkfactory.
- [ ] AC-2: A test PR triggers the workflow and it passes.
- [ ] AC-3: An intentionally-broken test causes the workflow to fail.
- [ ] AC-4: README has a CI status badge.

## References

- [[PRD-500-darkfactory-extraction]] — parent epic
- [[PRD-505-darkfactory-verify-and-push]] — must complete first

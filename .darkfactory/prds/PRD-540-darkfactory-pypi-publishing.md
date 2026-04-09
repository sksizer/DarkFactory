---
id: "PRD-540"
title: "Set up PyPI publishing for darkfactory"
kind: task
status: draft
priority: low
effort: s
capability: simple
parent: "[[PRD-500-darkfactory-extraction]]"
depends_on:
  - "[[PRD-530-darkfactory-ci-setup]]"
blocks: []
impacts:
  - (darkfactory repo) .github/workflows/release.yml
  - (darkfactory repo) pyproject.toml
workflow: null
target_version: null
created: 2026-04-08
updated: 2026-04-08
tags:
  - harness
  - extraction
  - release
  - pypi
---

# Set up PyPI publishing for darkfactory

## Summary

Once CI is green, wire up a release workflow that publishes `darkfactory` to PyPI on every tag push. Uses PyPI Trusted Publishing (OIDC) so no long-lived API tokens are stored. This is the final follow-up — once it lands, anyone can `uv tool install darkfactory` or `pip install darkfactory`.

## Requirements

1. `.github/workflows/release.yml` triggers on `push` of tags matching `v*`.
2. Build job uses `uv build` to produce sdist + wheel.
3. Publish job uses `pypa/gh-action-pypi-publish` with Trusted Publishing (no API token in secrets).
4. `pyproject.toml` has accurate metadata: description, license, homepage, repository, keywords, classifiers.
5. PyPI project `darkfactory` is registered and Trusted Publishing is configured for the GitHub repo.
6. README documents the install command (`uv tool install darkfactory`).

## Technical Approach

```yaml
name: Release
on:
  push:
    tags: ["v*"]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
```

Manual steps before the first release:
1. Reserve `darkfactory` on PyPI (create account if needed).
2. Configure Trusted Publishing on PyPI: project = darkfactory, owner = sksizer, repo = darkfactory, workflow = release.yml, environment = pypi.
3. Create the `pypi` GitHub environment in the darkfactory repo settings.

Status `draft` until CI (PRD-530) is in place.

## Acceptance Criteria

- [ ] AC-1: `.github/workflows/release.yml` exists and uses Trusted Publishing.
- [ ] AC-2: Tagging `v0.1.0` triggers a successful publish to PyPI.
- [ ] AC-3: `uv tool install darkfactory` from a clean machine works.
- [ ] AC-4: `darkfactory --help` (or `prd --help`) runs after install.
- [ ] AC-5: README install instructions are accurate.

## References

- [[PRD-500-darkfactory-extraction]] — parent epic
- [[PRD-530-darkfactory-ci-setup]] — must complete first
- https://docs.pypi.org/trusted-publishers/

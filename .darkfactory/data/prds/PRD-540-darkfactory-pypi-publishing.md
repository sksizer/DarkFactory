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

## Assessment (2026-04-11)

- **Value**: 2/5 today — PyPI publishing only matters for adoption
  outside the author's machine. Currently zero external adopters.
  Value jumps to 4/5 as soon as adoption is a real goal.
- **Effort**: s — one GitHub Actions workflow file, pyproject metadata
  completion, one-time PyPI account + Trusted Publishing setup. The
  manual steps (PyPI reservation, TP config, `pypi` environment
  creation) are not things the agent can do — they require human
  action.
- **Current state**: greenfield. `.github/workflows/release.yml`
  doesn't exist. `pyproject.toml` metadata is minimal (check
  `description`, `classifiers`, `urls`).
- **Gaps to fully implement**:
  - Author `release.yml` per the PRD's skeleton.
  - Flesh out pyproject metadata (description, keywords, classifiers,
    homepage URL).
  - Human-only steps (reserve `darkfactory` on PyPI, configure
    Trusted Publishing, create `pypi` environment).
  - Document the install command in README.
- **Recommendation**: defer — schedule alongside whatever other
  "time to announce DarkFactory" milestone arrives. There's no point
  publishing v0.1.0 to PyPI if nobody's going to `uv tool install`
  it. Keep the PRD ready-to-go so the day you decide to release,
  this is an afternoon of work.

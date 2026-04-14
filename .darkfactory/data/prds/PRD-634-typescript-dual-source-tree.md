---
id: PRD-634
title: Rename src to python and prepare dual source tree
kind: task
status: done
priority: high
effort: s
capability: simple
parent:
depends_on: []
blocks:
  - "[[PRD-635-typescript-scaffold-and-core-types]]"
impacts:
  - src/ → python/
  - pyproject.toml
  - justfile
  - .github/workflows/ci.yml
  - .gitignore
  - CLAUDE.md
  - README.md
  - .darkfactory/data/prds/*.md
workflow: task
assignee:
reviewers: []
target_version:
created: 2026-04-13
updated: 2026-04-13
tags:
  - infrastructure
  - typescript
---

# Rename src to python and prepare dual source tree

## Summary

Rename `src/` to `python/` and update all tooling references so the repository is ready for a `ts/` source tree alongside it. Update the root `justfile` and `.gitignore` for the dual-tree layout.

## Motivation

Porting DarkFactory to TypeScript will be done incrementally while the Python version remains the working tool. Renaming `src/` to `python/` makes the language boundary explicit and prepares for a sibling `ts/` directory. Doing the rename first — before any TS code exists — keeps the git history clean: one rename commit, then TS additions in [[PRD-635-typescript-scaffold-and-core-types]].

## Requirements

### Rename `src/` to `python/`

Update every reference to `src` or `python/darkfactory` in project configuration:

<<<<<<< Updated upstream
1. `git mv src python` — the actual rename
2. `pyproject.toml`:
   - `tool.hatch.version.path` → `python/darkfactory/__init__.py`
   - `tool.hatch.build.targets.wheel.packages` → `["python/darkfactory"]`
   - `tool.mypy.files` → `["python", "tests"]`
   - `tool.pytest.ini_options.testpaths` → `["python", "tests"]`
3. `justfile` — all `src` references → `python`
4. `.github/workflows/ci.yml` — `uv run mypy src tests` → `python tests`
5. `CLAUDE.md`:
   - `python/darkfactory/cli/new.py` → `python/darkfactory/cli/new.py`
   - `python/darkfactory/workflows/{name}/workflow.py` → `python/darkfactory/workflows/{name}/workflow.py`
6. `README.md` — update `python/darkfactory/cli/` and `python/darkfactory/builtins/` references in Architectural Principles section
7. Active PRDs (non-terminated) in `.darkfactory/data/prds/` — bulk-update `python/darkfactory` path references to `python/darkfactory`
=======
1. [ ] `git mv src python` — the actual rename
2. [ ] `pyproject.toml`:
   - [ ] `tool.hatch.version.path` → `python/darkfactory/__init__.py`
   - [ ] `tool.hatch.build.targets.wheel.packages` → `["python/darkfactory"]`
   - [ ] `tool.mypy.files` → `["python", "tests"]`
   - [ ] `tool.pytest.ini_options.testpaths` → `["python", "tests"]`
3. [ ] `justfile` — all `src` references → `python`
4. [ ] `.github/workflows/ci.yml` — `uv run mypy src tests` → `python tests`
5. [ ] `CLAUDE.md`:
   - [ ] `src/darkfactory/cli/new.py` → `python/darkfactory/cli/new.py`
   - [ ] `src/darkfactory/workflows/{name}/workflow.py` → `python/darkfactory/workflows/{name}/workflow.py`
6. [ ] `README.md` — update `src/darkfactory/cli/` and `src/darkfactory/builtins/` references in Architectural Principles section
7. [ ] Active PRDs (non-terminated) in `.darkfactory/data/prds/` — bulk-update `src/darkfactory` path references to `python/darkfactory`
8. [ ] Typescript CI Runs as a new workflow 
>>>>>>> Stashed changes

### Update justfile and .gitignore

Update existing Python commands and add Node ignores:

```justfile
default:
    @just --list

prd *ARGS:
    @uv run prd {{ARGS}}

test:
    uv run pytest

typecheck:
    uv run mypy python tests

format:
    uv run ruff format python tests

lint:
    uv run ruff check python tests

format-check:
    uv run ruff format --check python tests
```

Add to `.gitignore`:
```
# Node / TypeScript
ts/node_modules/
ts/dist/
ts/coverage/
```

## Acceptance criteria

- [ ] `git mv src python` committed; no broken imports in Python
- [ ] `just test`, `just typecheck`, `just lint` all pass against `python/`
- [ ] CI workflow updated and would pass
- [ ] `.gitignore` updated for Node artifacts
- [ ] `CLAUDE.md` and `README.md` updated with new paths
- [ ] Active PRDs updated — no non-terminated PRD references `python/darkfactory`
- [ ] Editable install (`uv sync && prd --help`) produces working CLI

## Out of scope

- Creating the `ts/` directory or any TypeScript files (see [[PRD-635-typescript-scaffold-and-core-types]])
- Adding TypeScript justfile recipes (`ts-test`, `ts-typecheck`) — belongs in [[PRD-635-typescript-scaffold-and-core-types]]
- Updating `src/` references in terminated (done/cancelled) PRDs — those are historical records
- Changing the Python package name or import paths (still `import darkfactory`)
- Updating test fixture strings that use `src/foo.py` etc. as arbitrary example path data — these are not project structure references

# To Address

CI Is emitting some warnings we want to address now:

Need CI Update: 
- [ ] Warning: Node.js 20 actions are deprecated. The following actions are running on Node.js 20 and may not work as expected: actions/checkout@v4, astral-sh/setup-uv@v3. Actions will be forced to run with Node.js 24 by default starting June 2nd, 2026. Node.js 20 will be removed from the runner on September 16th, 2026. Please check if updated versions of these actions are available that support Node.js 24. To opt into Node.js 24 now, set the FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true environment variable on the runner or in your workflow file. Once Node.js 24 becomes the default, you can temporarily opt out by setting ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true. For more information see: [https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/](https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/)

- [ ] UV Cache Service Isn't Working
-Run astral-sh/setup-uv@v3

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:9)Downloading uv from "[https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz](https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz)" ...

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:10)/usr/bin/tar xz --warning=no-unknown-keyword --overwrite -C /home/runner/work/_temp/d0d56637-4279-4e43-bd46-d0315d1a5bde -f /home/runner/work/_temp/a54f7d5b-79f6-46d9-92e2-66a8f871158c

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:11)Added /opt/hostedtoolcache/uv/0.11.6/x86_64 to the path

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:12)Added /home/runner/.local/bin to the path

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:13)Successfully installed uv version 0.11.6

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:14)Set UV_CACHE_DIR to /home/runner/work/_temp/setup-uv-cache

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:15)Searching files using cache dependency glob: **/uv.lock

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:16)/home/runner/work/DarkFactory/DarkFactory/uv.lock

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:17)Found 1 files to hash.

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:18)Trying to restore uv cache from GitHub Actions cache with key: setup-uv-1-x86_64-unknown-linux-gnu-0.11.6-fa22a2693b19dd64a4133faf92ad964f8b6adbaff6b80c75cb9a7b06df5f76a0

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:19)Warning: Failed to restore: Cache service responded with 400

[](https://github.com/sksizer/DarkFactory/actions/runs/24364980194/job/71154202126#step:3:20)No GitHub Actions cache found for key: setup-uv-1-x86_64-unknown-linux-gnu-0.11.6-fa22a2693b19dd64a4133faf92ad964f8b6adbaff6b80c75cb9a7b06df5f76a0a

- [ ] Typescript build steps are not being run in CI

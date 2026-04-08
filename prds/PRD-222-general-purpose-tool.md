---
id: "PRD-222"
title: "Make darkfactory a general-purpose CLI tool installable anywhere"
kind: epic
status: draft
priority: high
effort: l
capability: moderate
parent: null
depends_on: []
blocks: []
impacts: []  # epic — children declare their own
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-08'
tags:
  - harness
  - cli
  - packaging
  - config
---

# Make darkfactory a general-purpose CLI tool installable anywhere

## Summary

Today darkfactory is shaped like "a harness for the darkfactory repo that lives in a git clone of darkfactory." To become a useful tool anyone can point at any project, three things need to change:

1. **Installable CLI**: users should be able to run `prd` (or `darkfactory`) directly without the `uv run` preamble, from any directory.
2. **Target directory is the current working directory by default**, overridable with `--directory` (or a global env var).
3. **Convention-over-configuration layout**: instead of a bare `prds/` directory at the repo root, all darkfactory state (PRDs, workflows, local config, lock files, worktree metadata) lives under a single `.darkfactory/` directory in the target repo. `prds/` is too specific — users will want custom workflows, model overrides, project-specific prompts, etc.

This is an **epic**. It decomposes into scoped child PRDs that can land independently.

## Motivation

### Friction today

Running the harness currently requires:

```
cd ~/Developer/darkfactory    # must be inside the darkfactory clone
uv run --quiet prd status      # uv preamble
```

If you want to use it against a different project, you're stuck. The CLI defaults look for `prds/` and `workflows/` relative to the current working directory, but:

- The target project has no `prds/` directory (why would it?).
- There's no way to tell the CLI "read config from this other dir."
- Installing globally requires knowing the `uv run` dance.

For a tool whose whole pitch is "drive any project's SDLC through a pluggable workflow harness," those are all dealbreakers.

### Conceptual shift: target project ≠ darkfactory repo

darkfactory needs to work in two modes and not confuse them:

- **darkfactory-as-tool**: a Python package installed as a CLI. Its source lives wherever pip/uv puts it. You don't `cd` into it.
- **darkfactory-as-project-convention**: a `.darkfactory/` directory *inside some other project* holding that project's PRDs, workflows, config, and runtime state.

Today we conflate these — the tool assumes it's running inside its own clone, and the "target project's PRDs" and "the tool's own PRDs" happen to be the same set. Separating them is the prerequisite for everything else.

### Why `.darkfactory/` is the right home

A dot-directory at the target repo root gives us:

- **Namespace isolation** — no collision with the project's own `docs/`, `config/`, etc.
- **Obvious gitignoring of runtime state** — `.darkfactory/worktrees/`, `.darkfactory/locks/` can be ignored while `.darkfactory/prds/` and `.darkfactory/workflows/` stay tracked.
- **Extensibility** — future features (model overrides, agent transcripts, cached prompts, CI hooks) all have a natural home.
- **Discoverable** — "where does darkfactory put its stuff?" has one answer.
- **Familiar pattern** — matches `.github/`, `.vscode/`, `.cursor/`, `.mise/`, etc.

Proposed layout inside a target repo:

```
.darkfactory/
├── config.toml          # project-level config (model defaults, workflow overrides, etc.)
├── prds/                # tracked — PRDs live here
│   ├── PRD-001-*.md
│   └── ...
├── workflows/           # tracked — custom workflows override built-ins by name
│   ├── default/         # optional; if present, shadows the bundled default
│   └── my-custom/
├── worktrees/           # NOT tracked — .gitignore'd
│   ├── PRD-001-.../
│   └── PRD-001.lock
└── transcripts/         # NOT tracked — agent output logs (future)
    └── PRD-001-2026-04-08T12-34-56.log
```

## Requirements

1. **Installability**: `uv tool install darkfactory` (or `pipx install darkfactory`, or `pip install darkfactory`) must produce a `prd` binary on the user's PATH. Running `prd status` in any directory should work without further setup.
2. **Target directory default**: `prd <subcommand>` without flags uses `Path.cwd()` as the target repo. This means `prd status` in a fresh repo with no `.darkfactory/` errors cleanly with "no .darkfactory/ directory found — run `prd init` to create one".
3. **Explicit target**: `--directory PATH` (or `-C PATH` matching git's convention) overrides the default. `DARKFACTORY_DIR` env var does the same, with CLI flag winning.
4. **Config layout**: all project-level darkfactory state lives under `<target>/.darkfactory/`:
   - `.darkfactory/prds/` — PRD files (tracked)
   - `.darkfactory/workflows/` — custom workflow definitions (tracked; optional, shadows built-ins by name)
   - `.darkfactory/worktrees/` — runtime worktrees (git-ignored)
   - `.darkfactory/config.toml` — project config (tracked; optional)
5. **Built-in workflows ship with the package**: the `default` workflow (and future built-ins like `planning`) live inside the installed darkfactory package, not on disk in the target repo. A user can override any built-in by dropping a same-named directory into `.darkfactory/workflows/`.
6. **`prd init` subcommand**: scaffolds `.darkfactory/prds/`, `.darkfactory/workflows/` (empty, ready for overrides), `.darkfactory/config.toml` (with commented examples), and updates `.gitignore` to exclude `.darkfactory/worktrees/` and `.darkfactory/transcripts/`.
7. **Migration path for darkfactory itself**: darkfactory's own `prds/` and `workflows/` directories get moved to `.darkfactory/prds/` and `.darkfactory/workflows/`. This PRD is eating its own dog food as the first project to adopt the new layout.
8. **Backwards compatibility during transition**: the CLI accepts the old `prds/`-at-repo-root layout with a deprecation warning, pointing users at `prd init` for the new layout. Removed after one or two releases.
9. **`pyproject.toml` scripts entry**: `prd = "darkfactory.cli:main"` already exists; verify that `uv tool install` picks it up. If a name conflict with other `prd` binaries is a concern, also expose `darkfactory = "darkfactory.cli:main"` as a second entry point.
10. **Documentation update**: README rewritten to show `uv tool install darkfactory && cd ~/my-project && prd init && prd status` as the quickstart.

## Proposed decomposition (child PRDs)

This is an epic. Suggested breakdown:

- **PRD-222.1 — Config directory discovery + `--directory` flag**
  - Add `_find_darkfactory_dir(cwd: Path) -> Path` that walks up from cwd looking for `.darkfactory/`.
  - Add `--directory` / `-C` global flag + `DARKFACTORY_DIR` env var to `cli.py`.
  - Rewrite `_default_prd_dir` and `_default_workflows_dir` to resolve via the discovered `.darkfactory/` path.
  - Backwards compat: if no `.darkfactory/` is found but `prds/` exists at the repo root, warn and use it.

- **PRD-222.2 — `prd init` subcommand**
  - Creates `.darkfactory/prds/`, `.darkfactory/workflows/`, `.darkfactory/config.toml` skeleton.
  - Updates `.gitignore` (creating if absent) with the runtime-state ignores.
  - Idempotent — re-running on an initialized dir reports "already initialized" and makes no changes.

- **PRD-222.3 — Bundle built-in workflows inside the package**
  - Move `workflows/default/` into `src/darkfactory/workflows/default/` so it ships inside the wheel.
  - Loader resolves in order: `.darkfactory/workflows/<name>/` (user override) → `darkfactory.workflows.<name>` (bundled).
  - Tests cover the override precedence.

- **PRD-222.4 — Dogfood migration: move darkfactory's own files**
  - Move `prds/` → `.darkfactory/prds/`.
  - Custom workflows (e.g. `workflows/extraction/`) stay in the project at `.darkfactory/workflows/extraction/` since extraction is darkfactory-specific, not a general-purpose workflow.
  - Update `.gitignore`.
  - The `prd` tool continues to work from darkfactory's own root after this — self-validation.

- **PRD-222.5 — Package metadata + installability**
  - Verify `pyproject.toml` scripts entry works via `uv tool install`.
  - Add `darkfactory` as a secondary entry point alias.
  - Update README quickstart.
  - Publish to PyPI (may be a separate PRD blocker; see PRD-540).

- **PRD-222.6 — Config file support (`.darkfactory/config.toml`)**
  - Schema: model defaults per capability tier, workflow override map, agent timeout defaults, tool allowlist additions, etc.
  - Loader in `cli.py` that merges CLI flags > env vars > `.darkfactory/config.toml` > package defaults.

Each child PRD should be 1–4 hours of work and independently shippable.

## Acceptance Criteria

High-level for the epic; children get their own concrete ACs:

- [ ] AC-1 (post-222.1 + 222.2): `prd init` followed by `prd status` works in a fresh empty directory, not inside the darkfactory clone.
- [ ] AC-2 (post-222.3): `prd list-workflows` shows the bundled `default` workflow without `.darkfactory/workflows/default/` existing on disk.
- [ ] AC-3 (post-222.4): darkfactory's own dogfood runs continue working after its files move under `.darkfactory/`.
- [ ] AC-4 (post-222.5): `uv tool install darkfactory` produces a working `prd` binary on PATH.
- [ ] AC-5 (post-222.6): Setting `model.trivial = "haiku"` in `.darkfactory/config.toml` overrides the default for a trivial PRD.
- [ ] AC-6: `.gitignore` correctly ignores runtime state while tracking PRDs and workflows.
- [ ] AC-7: Backwards compat: a repo still using bare `prds/` at the root works with a deprecation warning.

## Open Questions

- [ ] Should we also provide `prd` as `dfctr` or `df` for people who want a shorter alias? Recommendation: stick with `prd` as the primary; users can alias in their shell if they want.
- [ ] How should bundled workflows be packaged? Options: (a) importable Python modules under `darkfactory.workflows`, (b) data files shipped via `importlib.resources`, (c) both. Recommendation: (a) — they're Python anyway.
- [ ] `.darkfactory/config.toml` schema — toml vs yaml vs json? Recommendation: toml, matches pyproject.toml conventions and Python stdlib support since 3.11.
- [ ] How do we handle running darkfactory against a target project that has NO git repo? Is that a supported case or do we require git? Recommendation: require git for now — worktrees and branches are core primitives. Later we could support "scratchpad mode" for non-git dirs.
- [ ] Does `prd init` initialize git if the target has no `.git/`? Recommendation: no, error with a clear message. git init is a destructive-enough operation that users should run it themselves.
- [ ] Should built-in workflows be extensible via Python entry points (e.g. plugins from other packages)? Recommendation: not in this PRD, but design the loader to make it possible later.

## References

- Current CLI structure: `src/darkfactory/cli.py` (`_default_prd_dir`, `_default_workflows_dir`, `_find_repo_root`)
- Workflow loader: `src/darkfactory/loader.py`
- Examples of similar tools with dot-directories: `.github/`, `.vscode/`, `.mise/`, `.cursor/`, `.claude/`
- [[PRD-540-darkfactory-pypi-publishing]] — blocks AC-4

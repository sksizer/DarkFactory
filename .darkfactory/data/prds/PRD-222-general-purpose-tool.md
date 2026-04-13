---
id: PRD-222
title: Make darkfactory a general-purpose CLI tool installable anywhere
kind: epic
status: done
priority: high
effort: l
capability: moderate
parent:
depends_on: []
blocks:
  - "[[PRD-222.1-config-directory-discovery]]"
  - "[[PRD-222.2-prd-init-subcommand]]"
  - "[[PRD-222.3-bundle-builtin-workflows]]"
  - "[[PRD-222.4-user-config-directory]]"
  - "[[PRD-222.5-cascade-resolver-workflows]]"
  - "[[PRD-222.6-cascade-resolver-config]]"
  - "[[PRD-222.7-package-metadata-installability]]"
  - "[[PRD-222.8-dogfood-move-state]]"
impacts: []
workflow:
target_version:
created: 2026-04-08
updated: '2026-04-09'
tags:
  - harness
  - cli
  - packaging
  - config
  - feature
---

# Make darkfactory a general-purpose CLI tool installable anywhere

## Summary

Today darkfactory is shaped like "a harness for the darkfactory repo that lives in a git clone of darkfactory." To become a useful tool anyone can point at any project, four things need to change:

1. **Installable CLI**: users should be able to run `prd` (or `darkfactory`) directly without the `uv run` preamble, from any directory.
2. **Target directory is the current working directory by default**, overridable with `--directory` (or a global env var).
3. **One convention everywhere**: every project managed by darkfactory — *including darkfactory's own repo* — keeps its PRDs, custom workflows, local config, and worktree metadata under a single `.darkfactory/` directory at the project root. No special cases.
4. **Cascading configuration and workflow resolution** across layers: built-in (shipped with the package) → user-level (`~/.config/darkfactory/`) → project-level (`.darkfactory/`), with directory-level as a future extension. Name collisions across layers are a **hard error** during this early period — we prefer loud failure to silent magic.

This is an **epic**. It decomposes into scoped child PRDs that can land independently.

## Scope: two concerns, one convention

There are two conceptually separate things that the previous draft conflated, and the *right* way to untangle them is to apply a single convention uniformly rather than special-case darkfactory's own repo.

- **Darkfactory-the-tool's own Python source** — `src/darkfactory/`, tests, pyproject.toml, etc. This is package source code and ships in the wheel.
- **Darkfactory the project's design state** — its roadmap PRDs (PRD-200, PRD-222, …), config, and any custom workflows it wants for its *own* development. This is exactly the kind of thing `.darkfactory/` is designed to hold.

The clean split is:

- **First-party built-in workflows live inside the package** at `src/darkfactory/workflows/`. They ship in the wheel and every install gets them for free. This currently means **`default`, `extraction`, and `planning`** — all three are first-party built-ins, not custom darkfactory-specific things.
- **Darkfactory's own repo uses `.darkfactory/` like any other project.** It gets a `.darkfactory/prds/` (where PRD-200, PRD-222, etc. move to), a `.darkfactory/config.toml` (if it wants any project-level overrides), a `.darkfactory/workflows/` (empty, or for one-off dev workflows darkfactory doesn't want to ship to end users), and `.darkfactory/worktrees/` / `.darkfactory/transcripts/` for runtime state.
- **No dev-mode hardcoding.** The tool does not sniff pyproject.toml to decide "am I running in my own repo?" and take a special-case path. There is one convention — `.darkfactory/` at the target repo root — and darkfactory's own clone follows it the same way any other project does.

The previous "category error" framing was itself the category error: the right thing to dogfood is the *convention*, not to hide darkfactory's own design state somewhere else to avoid "conflation." Running `prd` inside darkfactory's own clone should look and feel identical to running it inside any other project.

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
- There's no way for the user to keep cross-project preferences (default model, preferred workflow, color theme) in one place — everything lives in the repo clone.

For a tool whose whole pitch is "drive any project's SDLC through a pluggable workflow harness," those are all dealbreakers.

### Why `.darkfactory/` is the right home (for target projects)

A dot-directory at the target repo root gives us:

- **Namespace isolation** — no collision with the project's own `docs/`, `config/`, etc.
- **Obvious gitignoring of runtime state** — `.darkfactory/worktrees/`, `.darkfactory/transcripts/` can be ignored while `.darkfactory/prds/` and `.darkfactory/workflows/` stay tracked.
- **Extensibility** — future features (model overrides, agent transcripts, cached prompts, CI hooks) all have a natural home.
- **Discoverable** — "where does darkfactory put its stuff in my project?" has one answer.
- **Familiar pattern** — matches `.github/`, `.vscode/`, `.cursor/`, `.mise/`, etc.

Proposed layout inside a target repo:

```
.darkfactory/
├── config.toml          # project-level config (model defaults, workflow overrides, etc.)
├── prds/                # tracked — PRDs live here
│   ├── PRD-001-*.md
│   └── ...
├── workflows/           # tracked — custom workflows; must not collide with built-ins or user workflows
│   └── my-custom/
├── worktrees/           # NOT tracked — .gitignore'd
│   ├── PRD-001-.../
│   └── PRD-001.lock
└── transcripts/         # NOT tracked — agent output logs (future)
    └── PRD-001-2026-04-08T12-34-56.log
```

### The cascade: built-in → user → project

Both workflows and config settings resolve through the same layered model:

| Layer | Workflow location | Config location | Scope |
|---|---|---|---|
| **Built-in** | `src/darkfactory/workflows/<name>/` (inside the wheel) | hardcoded defaults | Ships with the tool. Available to every install. |
| **User** | `~/.config/darkfactory/workflows/<name>/` | `~/.config/darkfactory/config.toml` | Per-developer. Same across all projects on this machine. |
| **Project** | `<project>/.darkfactory/workflows/<name>/` | `<project>/.darkfactory/config.toml` | Per-project. Tracked in the project's git repo. |
| *(future)* | *(directory-level — deferred)* | *(directory-level — deferred)* | Per-subtree within a project. Not in this epic. |

**Config cascade semantics:** settings merge from top to bottom. A later layer overrides earlier layers key-by-key. Built-in < user < project < env vars < CLI flags. This matches the layering already proposed by PRD-541 for style config; the same resolver is generalized here.

**Workflow cascade semantics:** workflows are discovered from *all* layers. Names must be **globally unique across layers**. If the same workflow name (e.g. `default`) appears in more than one layer, the tool **errors at startup** naming the conflicting paths and refuses to run until the user resolves it (rename, delete, or explicitly shadow — see Open Questions).

Rationale for strictness: we are in early days. Silent overrides create mystery behavior ("why did my custom workflow not run?") that is extremely painful to debug. Loud errors are cheap to fix manually. We can relax this later — once the expected API is stable and users have a mental model — by introducing an explicit `shadow: <name>` opt-in. Until then, every conflict is a bug until proven otherwise.

### Workflow API conformance — fail early

A workflow discovered in any layer must conform to the expected module API (required exports, `applies_to` signature, `steps` shape, etc.). At load time, the loader **validates every discovered workflow** and raises a clear error naming the offending file and the failing check if it doesn't conform. Policy for now:

- **Strict.** No "skip the broken one and load the rest" — if any workflow fails validation the whole `prd` invocation errors. We want users to notice and fix, not for a typo in a custom workflow to be silently ignored.
- **Clear messages.** The error must name (a) which layer the bad workflow came from, (b) the file path, and (c) the specific API contract that was violated (e.g. "`steps` must be a list of Step instances; got `NoneType`").
- **Cheap to relax later.** If/when strictness becomes annoying, adding a `--ignore-invalid-workflows` flag is a one-line change.

## Requirements

1. **Installability**: `uv tool install darkfactory` (or `pipx install darkfactory`, or `pip install darkfactory`) must produce a `prd` binary on the user's PATH. Running `prd status` in any directory should work without further setup.
2. **Target directory default**: `prd <subcommand>` without flags uses `Path.cwd()` as the target repo, walking up to find `.darkfactory/`. In a fresh repo with no `.darkfactory/`, it errors cleanly with "no `.darkfactory/` found — run `prd init` here".
3. **Explicit target**: `--directory PATH` (or `-C PATH` matching git's convention) overrides the default. `DARKFACTORY_DIR` env var does the same, with CLI flag winning.
4. **Target project layout**: all project-level darkfactory state lives under `<target>/.darkfactory/`:
   - `.darkfactory/prds/` — PRD files (tracked)
   - `.darkfactory/workflows/` — custom workflow definitions (tracked; optional)
   - `.darkfactory/worktrees/` — runtime worktrees (git-ignored)
   - `.darkfactory/transcripts/` — agent output logs (git-ignored)
   - `.darkfactory/config.toml` — project config (tracked; optional)
5. **Built-in workflows ship with the package**: built-in workflows (`default`, eventually `planning`, `extraction`, etc.) live inside the installed darkfactory package at `src/darkfactory/workflows/`, not on disk in the target repo.
6. **User-level config directory**: darkfactory reads `~/.config/darkfactory/` (honoring `$XDG_CONFIG_HOME` if set) for:
   - `~/.config/darkfactory/config.toml` — user-level config
   - `~/.config/darkfactory/workflows/<name>/` — user-level custom workflows shared across all projects
7. **Cascade resolution**:
   - **Config**: built-in defaults < `~/.config/darkfactory/config.toml` < `<project>/.darkfactory/config.toml` < env vars < CLI flags. Later layers override earlier ones key-by-key.
   - **Workflows**: discovered from all three layers (built-in, user, project). Names must be globally unique. Any collision is a **hard error** at startup naming all conflicting paths.
8. **Strict workflow API validation**: every discovered workflow is validated against the expected module contract at load time. Failures raise a clear error naming the layer, the file, and the specific violation. No silent skipping.
9. **`prd init` subcommand**: scaffolds `.darkfactory/prds/`, `.darkfactory/workflows/` (empty, ready for overrides), `.darkfactory/config.toml` (with commented examples), and updates `.gitignore` to exclude `.darkfactory/worktrees/` and `.darkfactory/transcripts/`.
10. **Darkfactory's own repo follows the `.darkfactory/` convention.** Its roadmap PRDs move from `prds/` to `.darkfactory/prds/`. Its in-repo workflows (`default`, `extraction`, `planning`) move *into the package* at `src/darkfactory/workflows/` as first-party built-ins. No dev-mode fallback, no special-case detection — the tool runs against its own clone exactly the way it runs against any other project.
11. **`pyproject.toml` scripts entry**: `prd = "darkfactory.cli:main"` already exists; verify that `uv tool install` picks it up. Also expose `darkfactory = "darkfactory.cli:main"` as a secondary alias in case of `prd` name conflicts.
12. **Documentation update**: README rewritten to show `uv tool install darkfactory && cd ~/my-project && prd init && prd status` as the quickstart. Must explicitly call out that `.darkfactory/` is the target-project convention, separate from darkfactory's own source tree.

## Proposed decomposition (child PRDs)

This is an epic. Suggested breakdown:

- **PRD-222.1 — Config directory discovery + `--directory` flag**
  - Add `_find_darkfactory_dir(cwd: Path) -> Path | None` that walks up from cwd looking for `.darkfactory/`.
  - Add `--directory` / `-C` global flag + `DARKFACTORY_DIR` env var to `cli.py`.
  - Rewrite `_default_prd_dir` and friends to resolve via the discovered `.darkfactory/` path.
  - No special cases — darkfactory's own repo participates in this mechanism via its own `.darkfactory/` directory (created in PRD-222.8), not via a dev-mode fallback.

- **PRD-222.2 — `prd init` subcommand**
  - Creates `.darkfactory/prds/`, `.darkfactory/workflows/`, `.darkfactory/config.toml` skeleton.
  - Updates `.gitignore` (creating if absent) with the runtime-state ignores.
  - Idempotent — re-running on an initialized dir reports "already initialized" and makes no changes.
  - Works inside darkfactory's own repo too; PRD-222.8 uses it to bootstrap.

- **PRD-222.3 — Bundle built-in workflows inside the package**
  - Move `workflows/default/`, `workflows/extraction/`, and `workflows/planning/` into `src/darkfactory/workflows/` so they ship in the wheel.
  - All three are first-party built-ins available to every install.
  - Loader discovers built-in workflows via direct module import under `darkfactory.workflows`.
  - Delete the old top-level `workflows/` directory once the loader is switched over.

- **PRD-222.4 — User config directory (`~/.config/darkfactory/`)**
  - Create on first access if missing (for workflows subdir); `config.toml` is lazy — absent is fine.
  - Honor `$XDG_CONFIG_HOME` override.
  - Documented as "settings that follow you across every project on this machine."

- **PRD-222.5 — Cascade resolver for workflows**
  - Single loader walks all three layers, collects every workflow, validates each against the API contract, and builds a registry.
  - **Collision detection**: if any name appears in more than one layer, raise `WorkflowNameCollision` naming all paths. Fatal.
  - **API validation**: each workflow runs through a conformance check at load time. Any failure raises `InvalidWorkflow(layer, path, reason)`. Fatal.
  - Both errors print actionable remediation hints ("rename or delete one of:", "expected `steps` to be …, got …").
  - Unit tests cover: built-in only, user only, project only, built-in + project no collision, collision across every pair of layers, invalid workflow in every layer.

- **PRD-222.6 — Cascade resolver for config**
  - Generalizes the style config resolver from PRD-541 into a shared `darkfactory.config` module.
  - Merges built-in defaults < user < project < env < CLI flags, key-by-key.
  - Schema: model defaults per capability tier, workflow override hints, agent timeout defaults, style (from PRD-541), tool allowlist additions.
  - PRD-541's style module consumes the resolved `Config` object instead of resolving its own.

- **PRD-222.7 — Package metadata + installability**
  - Verify `pyproject.toml` scripts entry works via `uv tool install`.
  - Add `darkfactory` as a secondary entry point alias.
  - Update README quickstart.
  - Publish to PyPI (may be a separate PRD blocker; see PRD-540).

- **PRD-222.8 — Dogfood: move darkfactory's own state to `.darkfactory/`**
  - Run `prd init` against darkfactory's own repo root.
  - Move `prds/*` → `.darkfactory/prds/*` in one commit. Update any code or docs referencing the old path.
  - Remove the old top-level `prds/` directory.
  - Ensure `.gitignore` picks up `.darkfactory/worktrees/` and `.darkfactory/transcripts/`.
  - Verify: every existing harness flow (`prd status`, `prd run`, `prd tree`, workflow execution) continues to work against darkfactory's own clone after the move, with no dev-mode fallback anywhere in the codebase.
  - This PRD blocks on 222.1 (discovery) + 222.2 (`prd init`) + 222.3 (bundled workflows) landing first.

Each child PRD should be 1–4 hours of work and independently shippable.

## Acceptance Criteria

High-level for the epic; children get their own concrete ACs:

- [ ] AC-1 (post-222.1 + 222.2): `prd init` followed by `prd status` works in a fresh empty directory, not inside the darkfactory clone.
- [ ] AC-2 (post-222.3): `prd list-workflows` shows the bundled `default` workflow without `default/` existing on disk anywhere in the target project.
- [ ] AC-3 (post-222.4 + 222.5): A workflow file dropped into `~/.config/darkfactory/workflows/my-custom/` is discovered and usable from every project, without any project-level setup.
- [ ] AC-4 (post-222.5): A workflow name that collides across any two layers (built-in / user / project) causes `prd` to exit with a clear error naming both paths, and no other subcommand runs until the collision is resolved.
- [ ] AC-5 (post-222.5): A workflow with an invalid module shape (missing `applies_to`, wrong `steps` type, etc.) causes `prd` to exit with an error naming the layer, file, and specific contract violation.
- [ ] AC-6 (post-222.6): `model.trivial = "haiku"` in `~/.config/darkfactory/config.toml` is overridden by the same key in a project's `.darkfactory/config.toml`, which is in turn overridden by `DARKFACTORY_MODEL_TRIVIAL=...`, which is in turn overridden by `--model-trivial ...` on the CLI.
- [ ] AC-7 (post-222.7): `uv tool install darkfactory` produces a working `prd` binary on PATH.
- [ ] AC-8 (post-222.8): Darkfactory's own roadmap PRDs live at `.darkfactory/prds/` and every harness flow works against its own clone via the same code path every other project uses. No dev-mode fallback, no pyproject.toml sniffing, no special cases in the loader.
- [ ] AC-9: README documents `.darkfactory/` as the universal convention — the same one darkfactory's own repo uses.
- [ ] AC-10: `.gitignore` generated by `prd init` correctly ignores runtime state while tracking PRDs and workflows.
- [ ] AC-11 (post-222.3): `extraction` and `planning` are discoverable as first-party built-ins in a fresh install with no on-disk workflow directories anywhere.

## Open Questions

- [ ] **Explicit shadow opt-in.** Right now any workflow name collision is a hard error. Eventually we'll want users to be able to deliberately shadow a built-in (e.g. override `default` with their own variant). Proposal: add a `shadow:` field in the workflow module itself (e.g. `shadow = "default"`), and when loading a workflow with `shadow = "X"`, any existing "X" from a lower layer is *replaced* rather than colliding. Defer to a follow-up PRD once strict mode has caught enough real bugs.
- [ ] **Directory-level config (fourth layer).** Nice-to-have for monorepos where different subtrees want different settings. Defer to a later epic; design the cascade so a fourth layer slots in cleanly.
- [ ] **Short alias (`df`, `dfctr`).** Stick with `prd` as the primary; users can alias in their shell.
- [ ] **Built-in workflow packaging.** Python modules under `darkfactory.workflows` (importable) vs data files via `importlib.resources`. Recommendation: importable Python modules — they're Python anyway.
- [ ] **Config file format.** TOML. Matches pyproject.toml conventions and Python stdlib support since 3.11.
- [ ] **Non-git target projects.** Require git for now — worktrees and branches are core primitives. Later: "scratchpad mode" for non-git dirs.
- [ ] **`prd init` initializing git.** No — error with a clear message if `.git/` is absent. `git init` is destructive enough that users should run it themselves.
- [ ] **Entry-point plugin workflows.** Out of scope for this PRD, but design the loader to make it possible later (fourth discovery source alongside built-in/user/project).

## References

- Current CLI structure: `src/darkfactory/cli.py` (`_default_prd_dir`, `_default_workflows_dir`, `_find_repo_root`)
- Workflow loader: `src/darkfactory/loader.py`
- Style config cascade (same layering, prior art): [[PRD-541-add-color-to-prd-output]]
- Examples of similar tools with dot-directories: `.github/`, `.vscode/`, `.mise/`, `.cursor/`, `.claude/`
- [[PRD-540-darkfactory-pypi-publishing]] — blocks AC-7

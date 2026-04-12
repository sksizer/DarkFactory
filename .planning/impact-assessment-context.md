# Impact Assessment Context — Recent Codebase Changes

This document summarizes the recent changes to the DarkFactory codebase that may affect open PRDs. Use this to assess each open PRD: does it still make sense? Does it reference APIs, paths, or modules that have been renamed, moved, or restructured?

## Change #1 — PRD-622 Data Model Refactor (merged, the largest change)

**Summary:** `src/darkfactory/prd.py` was deleted and replaced with a `src/darkfactory/model/` package. The `.darkfactory/prds/` directory was moved to `.darkfactory/data/prds/`. A new `archive` command + `.darkfactory/data/archive/` folder was added. Frontmatter serialization is now deterministic. Every write stamps `app_version`.

### Module renames

| Before | After |
|---|---|
| `src/darkfactory/prd.py` (monolithic) | `src/darkfactory/model/` (package) |
| `from darkfactory.prd import PRD, load_all, ...` | `from darkfactory.model import PRD, load_all, ...` |
| `from darkfactory import prd` | `from darkfactory import model` |

The `model/` package has:
- `model/_prd.py` — `PRD` dataclass + domain helpers (wikilink parsing, sort helpers, regex constants, `compute_branch_name`, `parse_id_sort_key`)
- `model/_persistence.py` — Frontmatter read/write, file discovery, auto-migration, archive logic, deterministic serializer
- `model/__init__.py` — re-exports the public API

### Public API (from `darkfactory.model`)

```python
def load_all(data_dir: Path, *, include_archived: bool = False) -> dict[str, PRD]
def load_one(data_dir: Path, prd_id: str, *, include_archived: bool = True) -> PRD
def save(prd: PRD) -> None
def set_status(prd: PRD, new_status: str) -> None
def set_status_at(path: Path, new_status: str) -> None  # worktree variant, no app_version stamp
def set_workflow(prd: PRD, workflow_name: str | None) -> None
def archive(prd: PRD, data_dir: Path) -> PRD
def parse_prd(path: Path) -> PRD
def dump_frontmatter(fm: dict[str, Any]) -> str
def normalize_list_field_at(path: Path, field: str, items: list[str], *, write: bool = True) -> bool
def update_frontmatter_field_at(path: Path, updates: dict[str, str]) -> None
def ensure_data_layout(darkfactory_dir: Path) -> None  # auto-migration
```

**Important:** `load_all` takes `data_dir` (`.darkfactory/data/`), not a `prds_dir`. Internally it derives `data_dir/"prds"` and `data_dir/"archive"`. Default `include_archived=False` is correct for active-DAG commands (status, next, validate, tree, run, etc.).

### Directory layout change

```
BEFORE:                          AFTER:
.darkfactory/                    .darkfactory/
  config.toml                      config.toml
  prds/                            data/
    PRD-*.md                         prds/
                                       PRD-*.md
                                     archive/
                                       (terminal-state PRDs moved here)
```

**Migration:** `ensure_data_layout()` runs in CLI `main()` before command dispatch. Detects the legacy layout (`.darkfactory/prds/` exists, `.darkfactory/data/prds/` doesn't), prompts interactively on TTY, errors on non-TTY. Moves all files (including `Dashboard.base`) to the new location and stamps `app_version` on each.

### CLI flag removal

The `--prd-dir` CLI flag has been removed. All internal `args.prd_dir` references are now `args.data_dir`. The `--directory` / `DARKFACTORY_DIR` discovery mechanism is the only way to override the project root.

### Config expansion

`Config` now has a nested `PathsConfig` section:

```python
config.paths.project_dir  # .darkfactory/
config.paths.data_dir     # .darkfactory/data/
config.paths.prds_dir     # .darkfactory/data/prds/
config.paths.archive_dir  # .darkfactory/data/archive/
```

### New `archive` command

`prd archive PRD-NNN` moves a completed PRD from `data/prds/` to `data/archive/`. Guardrails:
- Only terminal-state PRDs (`done`, `superseded`, `cancelled`) can be archived
- The full transitive dependency chain (ancestors, descendants, `depends_on`, `blocks` — BFS across all four axes) must also be terminal
- Archive guardrails prevent active PRDs from referencing archived ones, so `include_archived=False` is a safe default elsewhere

### Deterministic serialization

`save()` now uses a custom serializer with:
- **Canonical field order** — fixed sequence defined in `model/_persistence.py:CANONICAL_FIELD_ORDER`
- **Explicit quoting** — dates single-quoted (`'2026-04-11'`), wikilinks double-quoted, `null` for None
- **Block-style lists** sorted per `CANONICAL_SORTS`
- **Single write path** — `set_status`, `set_workflow`, `archive` all mutate the PRD and delegate to `save()`. All of them stamp `app_version` from `src/darkfactory/__init__.py`.
- **Exception:** `set_status_at()` (worktree variant) uses surgical line-editing and does NOT stamp `app_version` because worktree writes are ephemeral.

### Test fixtures

The `tmp_prd_dir` pytest fixture was renamed to `tmp_data_dir`. It still creates a `prds/` and `archive/` subdirectory under `tmp_path`. Tests that previously wrote to `tmp_prd_dir / "file.md"` now write to `tmp_data_dir / "prds" / "file.md"`.

### `pyproject.toml` version sourcing

`[tool.hatch.version]` now reads the version from `src/darkfactory/__init__.py:__version__` — no more duplication.

### `init.py` scaffolding

`prd init` now scaffolds `.darkfactory/data/prds/` and `.darkfactory/data/archive/` for new projects (replacing `.darkfactory/prds/`).

## Change #2 — PRD-556 CLI Split (in-progress, partially merged)

`src/darkfactory/cli.py` is being decomposed into a `src/darkfactory/cli/` package with one module per subcommand. Most submodules already exist: `cli/new.py`, `cli/status.py`, `cli/validate.py`, `cli/tree.py`, `cli/children.py`, `cli/orphans.py`, `cli/undecomposed.py`, `cli/conflicts.py`, `cli/list_workflows.py`, `cli/assign_cmd.py`, `cli/normalize.py`, `cli/plan.py`, `cli/run.py`, `cli/reconcile.py`, `cli/next_cmd.py`, `cli/cleanup.py`, `cli/rework.py`, `cli/rework_watch.py`, `cli/system.py`, `cli/discuss.py`, `cli/init_cmd.py`, `cli/archive.py`, `cli/_parser.py`, `cli/_shared.py`, `cli/main.py`.

**Implication:** PRDs that reference `src/darkfactory/cli.py` should be updated to reference the new `cli/` package. PRDs that talk about adding a new subcommand should target `cli/<name>.py` with a peer `cli/<name>_test.py`.

## Change #3 — Dry-run support for git builtins

`src/darkfactory/builtins/fast_forward_branch.py` and `src/darkfactory/builtins/rebase_onto_main.py` gained `dry_run` support (commit `16d1a8e`). PRDs that propose git-safety features may want to note this pattern as an example.

## Change #4 — Architectural principles (from README and CLAUDE.md)

- **Module-per-concern with peer tests** — decompose into small focused files, each with a peer test file (`_foo.py` / `_foo_test.py`)
- **Parse at the boundary, trust types internally** — validate config/frontmatter/CLI args at ingestion via strict types. No defensive checks deeper in.
- **Hard failures over silent degradation** — fail loudly with clear messages. Don't silently skip or fall back.

## Assessment guidance

When reading an open PRD, check for:

1. **Stale module paths** — any reference to `src/darkfactory/prd.py`, `from darkfactory.prd import`, `from darkfactory import prd`, or `.darkfactory/prds/` (without `data/`) should be updated to the new location/module.
2. **Stale callsites** — code snippets in PRD bodies that import from `darkfactory.prd` or use `args.prd_dir` need updating.
3. **Redundant scope** — if PRD-622 already delivered something the PRD proposed (e.g., "add archive command", "add deterministic serialization", "expand Config with paths"), mark the PRD as superseded or shrink its scope.
4. **Approach changes** — if the PRD's technical approach is now invalid (e.g., "modify prd.py" no longer works because prd.py is deleted), update the approach section.
5. **Test fixture names** — references to `tmp_prd_dir` → `tmp_data_dir`.
6. **CLI flag references** — mentions of `--prd-dir` should be removed (flag was deleted).
7. **cli.py references** — PRDs that talk about `src/darkfactory/cli.py` as a monolith should be updated to acknowledge the `cli/` package split.

## What NOT to change

- Don't rewrite well-scoped PRDs that are orthogonal to the changes (e.g., a PRD about PyPI publishing, ruff config, CI matrix, agent model fallback, etc.). Note in your report that it's unaffected.
- Don't bump the `status` field unless the PRD is now literally redundant.
- Don't touch the `created` date. Do update `updated` if you make content changes.
- Don't restructure PRDs for style reasons. Only touch what's stale.

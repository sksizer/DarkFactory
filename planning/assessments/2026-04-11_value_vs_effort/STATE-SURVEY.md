# Current-code state survey (2026-04-11)

Snapshot of what's actually in the codebase at `origin/main` (commit
`b976797`), captured via a parallel exploration pass. This is the baseline
the value/effort judgments in `SUMMARY.md` assume. If you're reading this
more than a month later, regenerate it — PRDs assessed against a stale
baseline miss "already done" cases.

## Top-level package layout

```
src/darkfactory/
├── __init__.py                 # version = "0.1.0"
├── __main__.py
├── cli/                        # ✅ Fully decomposed (PRD-556 scope)
│   ├── __init__.py
│   ├── _parser.py              # ~461 LOC argparse builder
│   ├── _shared.py
│   ├── main.py
│   ├── archive.py              # ✅ PRD-625 territory already landed via PRD-622
│   ├── assign_cmd.py
│   ├── children.py
│   ├── cleanup.py
│   ├── conflicts.py
│   ├── discuss.py              # ✅ PRD-616 landed
│   ├── init_cmd.py             # scaffold only — not interactive
│   ├── list_workflows.py
│   ├── new.py
│   ├── next_cmd.py
│   ├── normalize.py
│   ├── orphans.py
│   ├── plan.py
│   ├── reconcile.py
│   ├── run.py
│   ├── rework.py               # ✅ PRD-225 scaffold exists
│   ├── rework_watch.py         # ✅ PRD-225.6 scaffold exists
│   ├── status.py
│   ├── system.py
│   ├── tree.py
│   ├── undecomposed.py
│   ├── validate.py
│   └── (19 colocated *_test.py files)
├── builtins/                   # ✅ Fully decomposed (PRD-549 scope)
│   ├── __init__.py             # re-exports all builtins
│   ├── _registry.py
│   ├── _shared.py
│   ├── analyze_transcript.py   # ✅ PRD-559.4 done
│   ├── cleanup_worktree.py
│   ├── commit.py
│   ├── commit_events.py
│   ├── commit_transcript.py    # already uses .jsonl
│   ├── create_pr.py
│   ├── ensure_worktree.py
│   ├── fast_forward_branch.py  # ✅ PRD-617 done
│   ├── fetch_pr_comments.py
│   ├── lint_attribution.py
│   ├── push_branch.py
│   ├── rebase_onto_main.py
│   ├── reply_pr_comments.py
│   ├── resolve_rework_context.py
│   ├── rework_guard.py
│   ├── set_status.py
│   ├── summarize_agent_run.py
│   ├── system_builtins.py
│   └── (colocated *_test.py files)
├── model/                      # ✅ PRD-622 landed
│   ├── __init__.py             # re-exports load_all, load_one, save, archive, parse_prd, ensure_data_layout
│   ├── _prd.py                 # dataclass + domain helpers
│   └── _persistence.py         # YAML I/O, archive, auto-migration
├── workflows/                  # 6 workflows (up from 4)
│   ├── default/
│   ├── extraction/
│   ├── planning/
│   ├── planning_review/        # ✅ PRD-231 landed
│   ├── rework/                 # ✅ PRD-225 scaffold
│   └── task/
├── utils/                      # Partial (PRD-621 target — flat files only)
│   ├── git.py                  # not yet split into utils/git/ package
│   ├── system.py
│   ├── terminal.py
│   ├── secrets.py
│   ├── tui.py
│   ├── claude_code.py          # not yet split into utils/claude_code/ package
│   └── (tests)
├── assign.py, checks.py, config.py, containment.py
├── discovery.py
├── event_log.py                # ✅ structured JSONL events; session_id (not worker_id)
├── git_ops.py                  # still top-level (PRD-621 wants to merge into utils/git/)
├── graph.py, graph_execution.py
├── impacts.py
├── init.py                     # called by cli/init_cmd.py
├── invoke.py                   # still top-level (PRD-621 wants to move)
├── loader.py                   # dynamic workflow loader
├── paths.py                    # ✅ nested PathsConfig used consistently
├── pr_comments.py              # ~500 LOC — GitHub comment logic
├── registry.py                 # builtins registry
├── rework_context.py
├── runner.py
├── style.py                    # still no tests (largest untested module)
├── system.py, system_runner.py # duplicate _run_shell_once lives here
├── templates.py, templates_builtin.py
├── timeouts.py, timestamps.py
├── workflow.py                 # pure-data task/workflow types
└── worktree_utils.py
```

## CI and tooling

### `.github/workflows/ci.yml` (18 lines)
- Trigger: all PRs, pushes to main. **No path filter.**
- Steps: `uv sync` → `pytest` → `mypy src tests`
- **Missing:** `ruff check`, `ruff format --check`, `pytest-cov`, wheel build
- **Matrix:** Python 3.12 only

### `.github/workflows/prd-validate.yml` (19 lines)
- Already exists as a separate workflow. **PRD-565.2 scope is landed.**

### `.github/workflows/prd-status-on-merge.yml` (35 lines)
- Already exists. **PRD-224.5 scope is landed.**

### `pyproject.toml`
- `ruff>=0.15.9` in dev deps, but **no `[tool.ruff]` rule config** and **no
  ruff in CI**.
- No `pytest-cov`.
- `mypy` strict mode on.
- `requires-python = ">=3.12"` but CI only runs 3.12.

## Feature presence (for PRD cross-reference)

| Feature | State | PRD(s) affected |
|---------|-------|-----------------|
| `prd validate --json` | ✅ parser wires `--json` globally, validate uses it | 600.3.2 done |
| `prd tree --json` | ⚠️ flag wired, not implemented in command | 600.3.3 still needed |
| `prd show` command | ❌ missing | 600.3.7 still needed |
| `cleanup --yes` / `--force` | ⚠️ has `--force`, not `--yes` | 600.3.5 still needed (rename?) |
| `prd archive` command | ✅ `cli/archive.py` | PRD-625 superseded |
| `prd discuss` | ✅ `cli/discuss.py` | PRD-616 landed |
| `--version` flag | ❌ missing | 600.2.3 still needed |
| `HarnessError` exception class | ❌ missing | 600.4.4 still needed |
| `analyze_transcript` builtin | ✅ exists + wired into planning workflow | 559.4 done, 559.5 partially done |
| `session_id` vs `worker_id` | `session_id` in events | 570 still needed (rename) |
| `sync_branch` builtin | ❌ missing | 618 still needed |
| `rework` subcommand | ✅ `cli/rework.py` exists | PRD-225 mostly landed |
| Transcript format | ✅ `.jsonl` everywhere | PRD-560 landed |
| Auto-migration of legacy layout | ✅ `ensure_data_layout()` | PRD-622 landed |
| ruff in CI | ❌ | 600.1.4 still needed |
| pytest-cov in CI | ❌ | 600.2.2 still needed |
| Python 3.13 in CI matrix | ❌ | 600.2.5 still needed |
| Parallel graph execution | ❌ no ThreadPool / parallel | 551 still needed |
| Event-sourced status | ❌ `status_from_events` absent | 226 still needed |
| Interactive init wizard | ❌ `init_cmd.py` is scaffold only | 564, 608 still needed |

## Risky-pattern scan (src/ only, excluding tests)

### `subprocess.run(.*shell=True)`
- **Count: 2** (earlier research pass reported 0 — that was a grep miss).
  - `src/darkfactory/runner.py:593` — `_run_shell_once()` dispatches
    ShellTask commands through `shell=True`.
  - `src/darkfactory/system_runner.py:367` — duplicate of the above for
    system operations.
- `src/darkfactory/runner.py:472` calls `ctx.format_string(task.cmd)`
  before `_run_shell_once`, so user-controlled PRD title / slug flows
  directly into the shell string.
- **Implication:** PRD-600.1.2 (shell-escape `format_string`) targets a
  real surface. The builtins registry and agent dispatch paths are
  shell-free, but ShellTask dispatch is not. Don't supersede 600.1.2.

### `setattr(` in `runner.py`
- Line 305: `setattr(ctx, key, value)` — generic attribute set during task
  execution (legitimate).
- Line 451: `setattr(ctx, "_last_agent_result", result)` — this is the
  side-channel PRD-600.1.3 targets. Replace with the already-typed
  `last_invoke_result` field.

### `shlex.quote`
- **Not used anywhere.** Consistent with the no-`shell=True` discipline.

### `config.paths` nesting
- Nested `PathsConfig` used consistently in 4+ call sites. No legacy
  `config.prds_dir` references found. PRD-622 migration is clean.

### Broad `except Exception` handlers
- 15+ in `src/`, most marked `# noqa: BLE001` (intentional).
- Notable unprotected ones (candidates for narrower except):
  - `pr_comments.py:438`
  - `system_runner.py:117`
  - `model/_persistence.py:601`
  - `analyze_transcript.py` (multiple — PRD-603 scope)
  - `git_ops.py:80`, `loader.py:113` (PRD-600.3.8 scope), `checks.py:157`

## Event log state

- File: `src/darkfactory/event_log.py` (~100+ lines)
- Envelope fields: `ts`, `session_id`, `prd_id`, `scope`, `type`, plus
  `**fields`
- Thread-safe (`threading.Lock` at line 67)
- **Missing:** `worker_start` / `worker_finish` lifecycle events (PRD-566
  designed them, never implemented)
- **Missing:** structured failure context on `task_finish` events
  (PRD-567.6 scope)

## Test layout

- `tests/` integration tests: 43 files
- Colocated `*_test.py`: many (each cli/ and builtins/ submodule has one)
- **Largest untested module: `style.py` at 499 LOC** (PRD-600.2.6 scope)

## Open questions flagged for human

These aren't PRD assessments — they're things the survey raised that the
assessment pass couldn't resolve unilaterally.

1. **Is `analyze_transcript` wired into `default` and `extraction`
   workflows, or only `planning`?** The research agent only confirmed the
   planning workflow. PRD-559.5 AC-1/2/3 require all three; verify before
   flipping to `done`.
2. **Is `cleanup --force` the same as `cleanup --yes`?** Research shows
   `--force` exists. PRD-600.3.5 may want `--yes` specifically. Decide if
   rename or add new alias.
3. **Does the old `src/darkfactory/cli.py` stub file truly not exist, or
   did the research agent miss it?** Research explicitly says "absent."
   PRD-556.18 AC-1 should verify this and close.

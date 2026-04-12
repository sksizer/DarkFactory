---
id: PRD-600
title: "Architectural Review and Code Quality Roadmap"
kind: epic
status: draft
priority: high
effort: xl
capability: complex
parent:
depends_on: []
blocks:
  - "[[PRD-600.1-safety-and-correctness]]"
  - "[[PRD-600.2-tooling-and-ci]]"
  - "[[PRD-600.3-operational-hardening]]"
  - "[[PRD-600.4-frontend-optionality]]"
impacts: []
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-09
updated: '2026-04-09'
tags:
  - architecture
  - code-quality
  - review
  - roadmap
---

# Architectural Review and Code Quality Roadmap

## 1. Executive Architectural Assessment

DarkFactory is a well-architected Python CLI tool (~10.5K LOC production, ~13.5K LOC tests) for PRD lifecycle management with DAG orchestration, declarative workflows, and Claude Code agent invocation. The architecture demonstrates strong fundamentals in its core: pure-data modules (`workflow.py`, `graph.py`, `containment.py`) with no I/O, injectable dependencies via Protocols and callbacks, a `WorkflowTemplate` composition pattern that enforces SDLC lifecycle invariants, and strict mypy compliance with only 1 error across 76 files.

**Overall Maintainability: 7/10.** The architecture is fundamentally sound with clean abstractions where they matter. Debt is concentrated in two areas: the `cli/__init__.py` god module (1,564 LOC, 15 command handlers) and operational safety gaps in destructive subprocess chains. The codebase is well-positioned for continued evolution as a CLI-first tool.

**Key verdict on future directions:**
- **Rust migration: Not justified.** Over 95% of wall-clock time is in subprocess calls (claude, git, gh). No compute-bound hotspot exists. The cost of a mixed codebase would far exceed any benefit.
- **Frontend enablement: Moderately well-positioned.** Domain layer is clean. CLI layer is the blocker. Minimum seams are achievable without premature abstraction.

---

## 2. Repository Structure

```
DarkFactory/
├── src/darkfactory/                  # Main package (10,461 LOC prod)
│   ├── cli/                          # CLI package (2,453 LOC) -- 15/21 handlers still in __init__.py
│   ├── builtins/                     # Built-in task primitives (1,339 LOC)
│   ├── workflows/                    # 4 built-in workflow definitions (336 LOC + 13 prompt templates)
│   ├── runner.py                     # Workflow execution engine (572 LOC)
│   ├── graph_execution.py            # DAG traversal (685 LOC)
│   ├── invoke.py                     # Claude Code subprocess wrapper (678 LOC)
│   ├── prd.py                        # PRD dataclass + frontmatter parser (489 LOC)
│   ├── workflow.py                   # Pure-data task/workflow types (276 LOC)
│   ├── style.py                      # Rich-based CLI theming (499 LOC)
│   └── [14 other modules]            # Config, graph, templates, checks, etc.
├── tests/                            # Integration tests (11,008 LOC, 37 files)
├── conftest.py                       # Project-wide fixtures
├── pyproject.toml                    # hatchling build, mypy strict, pytest
├── justfile                          # Build/test/lint recipes
└── mise.toml                         # Python 3.12 + uv
```

**LOC by module area:**

| Area | Prod LOC | Test LOC | Total |
|------|----------|----------|-------|
| CLI commands | 2,453 | ~4,942 | ~7,395 |
| Core engine (runner, graph_execution, invoke) | 1,935 | ~1,555 | ~3,490 |
| Builtins | 1,339 | ~2,180 | ~3,519 |
| Data model (prd, workflow, system) | 866 | ~880 | ~1,746 |
| DAG/containment/impacts | 423 | ~774 | ~1,197 |
| Support (templates, config, checks, etc.) | 1,445 | ~1,595 | ~3,040 |
| **Total** | **10,461** | **~13,516** | **~23,977** |

Test-to-code ratio: **1.29:1** -- healthy coverage.

---

## 3. Tooling & Dependency Management

### Strengths
- **Minimal runtime dependencies**: Only 3 -- `pyyaml`, `filelock`, `rich`. Exemplary minimalism.
- **mypy strict mode**: Comprehensive type checking across all source and test files. Only 1 error.
- **Lock file reproducibility**: `uv.lock` pins exact versions with hashes.
- **hatchling build**: Correctly configured for src-layout with test exclusion from wheel.
- **Clone-to-develop**: 3 commands (`mise install`, `uv sync`, `just test`).

### Gaps

| Finding | Severity | Action |
|---------|----------|--------|
| No ruff rule configuration -- only default E/F rules active | Medium | Configure `select = ["E","F","I","UP","B","S","RUF","SIM","PT"]` |
| Ruff not run in CI -- lint violations can merge undetected | High | Add `ruff check` and `ruff format --check` to CI |
| CI missing wheel-build verification | Medium | Add `uv build` step |
| No test coverage measurement | Medium | Add `pytest-cov` to dev deps |
| Version duplicated in `pyproject.toml` and `__init__.py` | Medium | Single-source with `hatch-regex-version` |
| Python 3.13 not tested despite `>=3.12` claim | Medium | Add matrix CI build |
| Duplicated `write_prd` test helper in two conftest files | Low | Extract to shared test utility |

---

## 4. CLI Architecture & UX

### Strengths
- **`--execute` opt-in pattern**: Dry-run by default on all mutating commands. Safer than industry convention.
- **`Styler` abstraction**: Clean separation of presentation from logic. No ANSI codes outside `style.py`.
- **Config cascade**: User TOML < project TOML < env vars < CLI flags. Well-implemented.
- **`NO_COLOR` compliance**: Follows `no-color.org` convention correctly.
- **JSONL event streaming**: `run --all` emits structured events for scripting.

### Gaps

| Finding | Severity | Quick Win? |
|---------|----------|------------|
| `cli/__init__.py` god module -- 1,564 LOC, 15 cmd handlers | High | No (mechanical but large) |
| Business logic in CLI handlers (reconcile, validate, base-ref) | High | No |
| No help text examples / epilog on any command | Medium | Yes |
| `--json` silently ignored by 9/20 commands | Medium | Per-command |
| No `--version` flag | Medium | Yes |
| No `prd show PRD-NNN` single-entity inspection command | Medium | Yes |
| No shell completion support | Medium | Medium effort |
| `rework --execute` is a non-functional stub | Medium | Flag as not-implemented |
| `cleanup --all` has no `--yes` flag for scripts | Medium | Yes |
| Top-level description says "Pumice PRD harness CLI" | Low | Yes |

### Command Hierarchy Assessment

20 subcommands in a flat namespace, nearing the ceiling for discoverability. Natural clusters exist:
- **Inspection**: status, tree, children, orphans, undecomposed, conflicts, next
- **Execution**: plan, run, rework, reconcile
- **Maintenance**: cleanup, normalize, validate
- **Configuration**: list-workflows, assign, init, new

The `system` subcommand demonstrates the nested pattern that could be replicated for these groups.

---

## 5. Core Architecture & Control Flow

### Execution Pipeline

```
main() -> build_parser -> cmd_run(args)
  -> load_all(prd_dir)      [dict[str, PRD]]
  -> load_workflows()        [dict[str, Workflow]]
  -> assign_workflow()       [PRD -> Workflow]
  -> execute_graph() or run_workflow()
       -> for each Task:
            BuiltIn  -> BUILTINS[name](ctx, **kwargs)
            Agent    -> compose_prompt -> invoke_claude -> sentinel parse
            Shell    -> subprocess.run(cmd, shell=True) -> retry logic
       -> return RunResult
```

### Key Design Patterns
1. **Strategy Pattern**: `CandidateStrategy` Protocol with `RootedStrategy` / `QueueStrategy`
2. **Registry Pattern**: `BUILTINS` dict + `@builtin` decorator
3. **Template Method**: `WorkflowTemplate.compose()` enforces open/close invariants
4. **Context Object**: `ExecutionContext` threads mutable state through task sequences
5. **Cascade**: Config, timeout, and workflow resolution through priority chains
6. **Protocol-based Injection**: `GitStateAdapter`, `EventSink`, injectable `run_workflow_fn`

### Architectural Hotspots

**Hotspot 1: `cli/__init__.py`** (1,564 LOC, fan-out to 17 modules). God module housing 15 command handlers. Three already extracted (status, cleanup, children); 15 remain. The file's own docstring acknowledges this is temporary.

**Hotspot 2: Dual Runner** (`runner.py` 572 LOC + `system_runner.py` 373 LOC). `_run_shell_once` is copy-pasted verbatim (21 lines). Overall structural similarity is ~60-80 lines, not the ~250 initially claimed by reviewers. The `SystemContext` differs materially from `ExecutionContext` in its `_shared_state`, `report`, and `format_string` behavior.

**Hotspot 3: `invoke.py`** (678 LOC). Handles subprocess management, stream processing, JSON event parsing, sentinel detection, timeout watchdog threads, and styled output -- all in one file. The 200+ line `invoke_claude` function has 13 parameters.

---

## 6. Domain Modeling & Internal APIs

### Data Model Quality

| Dataclass | LOC | Cohesion | Assessment |
|-----------|-----|----------|------------|
| `PRD` | 65 | High | Well-typed, clean fields, `raw_frontmatter` escape hatch is pragmatic |
| `Workflow` | 20 | High | Pure data, no I/O, `applies_to` predicate is elegant |
| `Task` hierarchy | 90 | High | BuiltIn/AgentTask/ShellTask -- 3 types, stable, isinstance dispatch is fine |
| `ExecutionContext` | 70 | Medium | Mutable god-object but justified for sequential execution |
| `RunResult` | 15 | High | Clean outcome record with step list |
| `RunEvent` | 10 | High | Serializable event for streaming |

### Internal API Quality

The strongest abstraction is `WorkflowTemplate.compose()` -- it prevents workflow authors from forgetting critical lifecycle steps while giving full control over the implementation section.

The weakest API boundary is `BuiltInFunc = Callable[..., None]` with `task.kwargs: dict[str, Any]`. This erases builtin signatures, making workflow definition typos invisible to mypy until runtime.

---

## 7. State, Configuration & Side Effects

### State Locations

| State | Storage | Access Pattern |
|-------|---------|---------------|
| PRD metadata | YAML-frontmatter Markdown files | `load_all()` on every invocation, re-loaded mid-run for DAG growth |
| Workflows | Python modules (`importlib` dynamic load) | 3-layer cascade: built-in, user, project |
| Events | JSONL files in `.darkfactory/events/` | Append-only via `EventWriter` |
| Config | TOML files (user + project) + env vars + CLI flags | Cascade resolution |
| Git worktrees | `.worktrees/` directory | Created by `ensure_worktree`, locked by `filelock` |

### Side Effect Concerns

1. **No crash recovery in `_create_reconcile_pr`**: 6 sequential `subprocess.run(check=True)` calls (branch -D, checkout -b, add, commit, push, pr create) with zero rollback. A network failure after commit leaves the repo stranded on a non-main branch.

2. **`EventWriter` file handle leak on crash**: Context manager protocol defined (`__enter__`/`__exit__`) but never used in production code. `KeyboardInterrupt` between construction and `close()` leaks the handle.

3. **Race between workflow completion and status update**: `graph_execution.py` writes `set_status_at` after `run_workflow` returns. A `KeyboardInterrupt` between these calls leaves the PRD in stale status. Next invocation re-runs already-completed work.

---

## 8. Error Handling & Observability

### Error Model
- All CLI errors use `raise SystemExit("message")` -- valid Python pattern but no structured error types.
- Builtins signal failure via bare `RuntimeError` or uncaught `CalledProcessError`. Runner catches `Exception` (BLE001).
- Error messages are generally actionable but inconsistently prefixed (some have "ERROR: ", some don't).
- `--json` mode gets bare stderr strings for errors, not structured JSON error objects.

### Observability
- `EventWriter` emits JSONL at DAG, workflow, and task granularity -- well-structured.
- `--verbose` flag is declared globally but used by exactly 1 command (`validate`).
- Logging via `logging.getLogger("darkfactory.*")` throughout but no user-visible log control beyond the single verbose flag.

---

## 9. Testing & Quality Posture

### Coverage
- **38 integration test files** in `tests/` covering all major modules
- **18 colocated unit test files** (`*_test.py`) alongside implementations
- **Test-to-code ratio: 1.29:1** -- healthy

### Gaps
| Module | LOC | Test Status |
|--------|-----|-------------|
| `style.py` | 499 | **No tests** -- largest untested module |
| `cmd_tree` / `cmd_orphans` / `cmd_undecomposed` | ~100 | **No dedicated tests** |
| `prd_test.py` (colocated) | 10 | Minimal -- bulk coverage in `tests/test_prd.py` |

### Quality Gates
- `mypy --strict` across all source + tests (1 error)
- `ruff check` locally (default rules only)
- CI runs: `pytest` + `mypy` (missing: ruff, format check, wheel build)

---

## 10. Performance & Scalability

### Performance Profile

| Activity | Bound Type | Wall-Clock Share |
|----------|-----------|-----------------|
| Claude Code agent invocation | Subprocess/API | >95% |
| git subprocess calls | Subprocess | 2-4% |
| gh CLI calls | Subprocess/Net | 1-2% |
| PRD YAML parsing | I/O + PyYAML | <0.5% |
| DAG computation | CPU (trivial) | <0.01% |

**The tool is subprocess-bound, not compute-bound.** Python overhead is negligible relative to agent invocation times (30s-45min per task). Startup latency is estimated at 100-300ms (unmeasured); the import chain through `cli/__init__.py` (42 imports) is the likely bottleneck, not `rich` alone.

### Scalability Limits
- **PRD count**: `load_all()` re-parses every PRD file on every invocation and mid-run iteration. Acceptable at hundreds of PRDs; would need caching at thousands.
- **`gh pr list --limit 200`** in reconcile silently truncates results. No pagination. Projects with 200+ merged PRD PRs will miss older ones.
- **Sequential execution only** (PRD-551 for parallel is planned).

---

## 11. Security & Safety

### Findings

| Issue | Severity | Status |
|-------|----------|--------|
| Shell injection via PRD titles in `ShellTask` | Medium-High | `format_string` interpolates `{prd_title}` into `shell=True` commands. No shell escaping applied. |
| Dynamic workflow loading executes arbitrary Python | Medium | `loader.py` calls `exec_module()` on any `.py` in workflow dirs, including user-global `~/.config/darkfactory/workflows/`. |
| Reconcile function has no rollback on partial failure | Medium | `_create_reconcile_pr` runs 6 destructive git operations with zero error recovery. |
| `yaml.safe_load` used throughout | Low (positive) | No CVE exposure from PyYAML. |
| `builtins` use explicit argv lists (no `shell=True`) | Low (positive) | Only `ShellTask` dispatch uses `shell=True`, by design. |

### Recommendation
Shell-escape `{prd_title}` and `{prd_slug}` in `ExecutionContext.format_string()` before they reach `shell=True` subprocess calls. This is the single highest-priority security fix.

---

## 12. Rust Migration Readiness

### Verdict: Not Justified

DarkFactory's runtime is overwhelmingly subprocess-bound. There is no compute-bound hotspot where Rust would provide measurable user-facing improvement.

| Candidate | Benefit | Cost | Verdict |
|-----------|---------|------|---------|
| DAG algorithms (`graph.py`, 155 LOC) | Microsecond savings on <1ms computation | Weeks of FFI setup + maintenance | Reject |
| YAML parsing | Marginal speedup on I/O-bound operation | PyYAML replacement + frontmatter compat | Reject |
| Template substitution | Microsecond savings | regex crate FFI for simple `.format()` | Reject |
| Impact overlap detection | Negligible at current scale | Set-intersection reimplementation | Reject |
| Sentinel parsing | Trivial string search | No measurable gain | Reject |

### Migration Blockers
1. Subprocess-dominated architecture -- Rust can't make `git push` faster
2. Python-native workflow plugin model via `importlib.exec_module()`
3. PyYAML serialization contract with byte-preservation guarantees
4. Single-developer project -- mixed codebase maintenance cost is prohibitive

### Alternatives That Would Actually Help
1. **Lazy imports** for `cli/__init__.py` transitive closure -- reduce startup time
2. **Parallel graph execution** (PRD-551, already planned) -- the real performance win
3. **PRD caching** -- avoid re-parsing unchanged files on every invocation
4. **PyInstaller/Nuitka** -- for distribution, not runtime performance

---

## 13. Frontend Readiness

### Current State: Moderately Well-Positioned

**What's already good:**
- Domain layer (`prd.py`, `graph.py`, `containment.py`, `workflow.py`, `assign.py`) is pure data/logic with injectable dependencies
- `run_workflow()` and `execute_graph()` accept all dependencies as parameters and return structured results
- `EventWriter` + `EventSink` callback pattern is the right abstraction for push-based streaming
- `Styler` is properly isolated -- no presentation leakage into domain code
- ~60% of commands have `--json` output paths

**What needs work:**
- `cli/__init__.py` mixes argument resolution, subprocess orchestration, and presentation
- No service/use-case layer between CLI handlers and domain modules
- All state is filesystem-only with no caching
- 9 commands ignore `--json` silently
- `SystemExit` as universal error mechanism (correct for CLI, unusable by a server)

### Frontend-Enabling Seams to Introduce Now

These are low-cost, high-optionality changes that benefit the CLI today:

| Seam | Effort | CLI Benefit | Frontend Benefit |
|------|--------|-------------|-----------------|
| Add `--json` to `validate`, `tree` | Small | CI gets structured errors; `tree` becomes pipeable | Direct API responses |
| Extract `cmd_run` argument resolution to function | Medium | Testable without CLI context | Server can call same function |
| Extract reconcile logic from CLI handler | Medium | Testable, crash-recoverable | Service function for API |
| Add `--version` flag | Trivial | Bug reports, version checking | API metadata endpoint |

**Explicitly deferred** (premature for CLI-only reality):
- Service layer for all 15 commands
- JSON response envelopes
- Custom error hierarchy
- `to_dict()` on all dataclasses

---

## 14. Architectural Risks

### Critical (Fix Now)

1. **Reconcile function crash recovery** (`cli/__init__.py:1441-1478`). Six sequential destructive git operations with `check=True` and zero rollback. A network failure after `git commit` leaves the repo stranded on a non-main branch. Add `try/finally` to return to original branch on any failure.

2. **Shell injection via PRD frontmatter** (`workflow.py:269`, `runner.py:564`). `{prd_title}` from YAML frontmatter is interpolated into `shell=True` commands without escaping. A title containing `$(command)` or backticks would execute. Shell-escape these values in `format_string()`.

### High (Fix Soon)

3. **Ruff not in CI**. Lint violations and formatting drift can merge undetected. Single highest-impact DevOps change.

4. **CLI god module**. 1,564 LOC with 15 handlers. Every feature addition touches this file. The extraction pattern is established (status, cleanup, children already done); completion is mechanical.

### Medium (Plan For)

5. **Dual runner duplication**. `_run_shell_once` is copy-pasted between `runner.py` and `system_runner.py`. Extract to shared module.

6. **`setattr` side channel in runner**. `_last_agent_result` stored via `setattr/getattr` at `runner.py:423/235`. The fix is to use the existing typed `last_invoke_result` field and remove the redundant side channel.

7. **Silent workflow loading failures**. `loader.py:113` catches `Exception` and logs a warning. A broken project workflow silently falls back to a lower-priority built-in. Consider failing loudly for project-level workflow errors.

8. **`gh pr list --limit 200` truncation**. Reconcile silently misses PRs beyond the first 200. Add pagination or at minimum warn when results are at the limit.

---

## 15. Reviewer Disagreements and Resolutions

### Disagreement 1: Subprocess Abstraction

- **Architecture Reviewer**: "94 subprocess.run calls across 26 files. Create a GitClient abstraction."
- **Adversarial Reviewer**: Count inflated by ~50% from test code. Builtins ARE the abstraction layer. Each is a named, tested, encapsulated git/gh operation.
- **Resolution**: The builtins registry is the correct abstraction. The real problem is that `checks.py` and `cli/__init__.py` (reconcile) bypass builtins and shell out directly. Fix: move reconcile git operations into builtins or a utility module. Do not create a separate `GitClient` class.

### Disagreement 2: Dual Runner Duplication Severity

- **Repo Mapper + Architecture Reviewer**: "~250 lines of near-identical code."
- **Adversarial Reviewer**: Actual copy-paste is ~21 lines (`_run_shell_once`). Structural similarity is ~60-80 lines. The contexts differ materially.
- **Resolution**: Extract `_run_shell_once` to a shared module (trivial). Defer generic dispatch engine until a third runner type is needed. The claim of "~250 lines" is overstated.

### Disagreement 3: `_resolve_base_ref` Placement

- **CLI Reviewer**: "Business logic that belongs in `runner.py` or `git_utils.py`."
- **Adversarial Reviewer**: Runner accepts `base_ref: str` as resolved parameter. Resolution logic is inherently a CLI/orchestration concern (reads --base, env vars, probes git state). Moving it to runner would violate runner's clean interface.
- **Resolution**: `_resolve_base_ref` is correctly placed in the CLI orchestration layer. When extracted, it goes to `cli/run.py` or a CLI utility, not to the runner.

### Disagreement 4: Frontend Readiness of Runner

- **Frontend Reviewer (section 1.2)**: "run_workflow() is well-scoped, a server could call it directly."
- **Frontend Reviewer (section 2.2)**: "Run single PRD: High complexity. Needs significant refactoring."
- **Resolution**: Self-contradiction. `run_workflow()` and `execute_graph()` have clean injectable interfaces. What needs extraction is the argument resolution in `cmd_run`. The runner IS the service layer for execution.

### Disagreement 5: Help Text Risk Rating

- **CLI Reviewer**: Rated "no help text examples" as High risk.
- **Adversarial Reviewer**: Missing epilog examples are a UX improvement, not a risk. Business logic in handlers (same review) is the genuine High risk.
- **Resolution**: Downgraded to Medium. Help text is a usability improvement. Business logic leakage and reconcile crash safety are the actual High-risk items.

---

## 16. Refactoring & Evolution Roadmap

### Phase 1: Safety & Correctness (Immediate)

| Task | Effort | Impact |
|------|--------|--------|
| Fix reconcile crash recovery (add try/finally branch rollback) | S | Prevents repo corruption |
| Shell-escape `{prd_title}` and `{prd_slug}` in `format_string()` | S | Closes injection surface |
| Remove `setattr` side channel; use existing `last_invoke_result` | XS | Removes type-safety gap |
| Add ruff to CI (`ruff check` + `ruff format --check`) | XS | Prevents lint drift |

### Phase 2: CLI Modularization (Short-term)

| Task | Effort | Impact |
|------|--------|--------|
| Extract `cmd_run` + graph/queue helpers to `cli/run.py` | M | Largest, most complex handler |
| Extract `cmd_reconcile` + all reconcile helpers to `cli/reconcile.py` | M | Most dangerous handler |
| Extract `cmd_plan` to `cli/plan.py` | S | Shares helpers with run |
| Extract `cmd_rework` to `cli/rework.py` | S | Self-contained |
| Extract `cmd_new` + template to `cli/new.py` | S | Self-contained |
| Extract remaining 10 simple handlers | M | Mechanical |
| Delete dead `cli.py` stub | XS | Cleanup |

### Phase 3: Tooling & Quality (Short-term)

| Task | Effort | Impact |
|------|--------|--------|
| Configure ruff rule set (`I,UP,B,S,RUF,SIM,PT`) | S | Broader lint coverage |
| Add `pytest-cov` + coverage floor | S | Visibility into untested code |
| Add tests for `style.py` | M | Largest untested module (499 LOC) |
| Add `--version` flag | XS | Bug reports, CI |
| Single-source version with `hatch-regex-version` | S | Eliminates version drift |
| Add Python 3.13 to CI matrix | XS | Tests claimed >=3.12 support |

### Phase 4: Operational Hardening (Medium-term)

| Task | Effort | Impact |
|------|--------|--------|
| Extract `_run_shell_once` to shared module | XS | Eliminates runner duplication |
| Add `--json` to `validate` and `tree` | S | CI and scripting |
| Warn or fail when `--json` is ignored by a command | S | Honest CLI behavior |
| Add `--yes` flag to `cleanup --all` | XS | Scriptability |
| Add help text epilog/examples to top 5 commands | S | UX improvement |
| Add `prd show PRD-NNN` command | S | Inspection primitive |
| Make silent workflow loading failures loud for project-level | S | Prevents silent fallback |
| Add pagination to reconcile PR fetching | S | Scalability |

### Phase 5: Frontend Optionality (When Needed)

| Task | Effort | Impact |
|------|--------|--------|
| Extract `cmd_run` argument resolution to standalone function | M | Testable, server-callable |
| Extract reconcile domain logic from CLI handler | M | Service function |
| Add `--json` to remaining read commands | M | Complete structured output |
| Introduce `HarnessError` exception hierarchy | M | Replace `SystemExit` for server use |
| Add service functions for top 5 read commands | L | API-ready domain logic |

---

## 17. Task Decomposition Backlog

### Immediate Priority (Safety)

- [ ] **PRD-600.1**: Fix `_create_reconcile_pr` crash recovery -- add try/finally to restore original branch on failure
- [ ] **PRD-600.2**: Shell-escape user-controlled values in `ExecutionContext.format_string()` before `shell=True` execution
- [ ] **PRD-600.3**: Remove `setattr` side channel in runner; use existing `last_invoke_result` field
- [ ] **PRD-600.4**: Add `ruff check` and `ruff format --check` to CI workflow

### Short-term Priority (Maintainability)

- [ ] **PRD-600.5**: Extract `cmd_run` + graph/queue helpers to `cli/run.py`
- [ ] **PRD-600.6**: Extract `cmd_reconcile` + all reconcile helpers to `cli/reconcile.py`
- [ ] **PRD-600.7**: Configure ruff rule set (`I,UP,B,S,RUF,SIM,PT`) with per-file-ignores
- [ ] **PRD-600.8**: Add `pytest-cov` and coverage reporting to CI
- [ ] **PRD-600.9**: Add `--version` flag and single-source version
- [ ] **PRD-600.10**: Add Python 3.13 to CI matrix

### Medium-term Priority (Quality)

- [ ] **PRD-600.11**: Extract `_run_shell_once` to shared runner utility module
- [ ] **PRD-600.12**: Add `--json` to `validate` and `tree` commands
- [ ] **PRD-600.13**: Add help text examples to `run`, `plan`, `new`, `status`, `cleanup`
- [ ] **PRD-600.14**: Add `prd show PRD-NNN` inspection command
- [ ] **PRD-600.15**: Add tests for `style.py`
- [ ] **PRD-600.16**: Make project-level workflow loading failures loud (not silent fallback)

### Deferred (Not Now)

- Rust migration -- not justified (see section 12)
- Service layer extraction for all commands -- premature (see section 13)
- JSON response envelopes -- web API convention, not CLI convention
- `to_dict()` on all dataclasses -- `dataclasses.asdict()` + per-command dicts are sufficient
- Typed args protocol per subcommand -- marginal benefit for 20 commands
- `heapq` optimization for topo sort -- microsecond savings on sub-millisecond operations

---

## Review Methodology

This analysis was conducted by 8 specialized reviewers operating in parallel:

1. **Repository Mapper** -- Structure, entry points, dependency graph, execution flow, hotspots
2. **Python Architecture Reviewer** -- Module boundaries, abstractions, patterns, technical debt
3. **CLI & UX Reviewer** -- Command hierarchy, flags, help text, ergonomics, scripting
4. **Tooling & Dependency Reviewer** -- Build system, deps, linting, CI/CD, developer experience
5. **Rust Migration Strategist** -- Performance profile, FFI seams, migration candidates
6. **Frontend Readiness Reviewer** -- Separation of concerns, API surfaces, state management
7. **Adversarial Reviewer** -- Challenged 11 assertions, identified 6 blind spots, flagged 5 unjustified recommendations
8. **Synthesizer** -- Integrated findings, resolved disagreements, produced this document

The adversarial reviewer verified claims against actual source code and identified that the collective findings have a signal-to-noise ratio of approximately 20-25% (25 high-signal findings out of ~120 total). The most impactful blind spots identified were the reconcile crash recovery gap and shell injection via PRD frontmatter.

---

## References

- [[PRD-549-builtins-package-split]] -- Prior modularization pattern (builtins)
- [[PRD-556-modularize-cli]] -- CLI modularization epic (in-progress, overlaps Phase 2)
- [[PRD-557-modularize-runner]] -- Runner modularization (overlaps Phase 4)
- [[PRD-551-parallel-graph-execution]] -- Parallel execution (the real performance win)
- [[PRD-552-merge-upstream-task]] -- Multi-dep stacking prerequisite
- [[PRD-559-transcript-analysis-step]] -- Transcript analysis (builtins extension)
- [[PRD-566-unified-event-log]] -- Event system consolidation

## Assessment (2026-04-11)

This epic is a high-signal snapshot of the codebase at 2026-04-09 plus a
prioritised backlog of 24 children under 4 sub-epics. The review itself
is the value; the backlog is the deliverable.

- **Value of the epic as a planning document**: 5/5 — the single
  highest-ROI planning artifact in the backlog. Its Phase 1 list is
  correct, its Phase 5 deferrals are correct, and its Rust-migration
  section has saved weeks of speculative work.
- **Value of the children as a whole**: 3/5 — distribution is bimodal.
  The 600.1 safety children and ~6 of the 600.3 operational children
  are high-value quick wins. The 600.2 tooling children are
  quality-of-life. 600.4 is defensive and should remain deferred.
- **Effort for the full epic**: l (as a project) — realistically 2–3
  focused sprints. Effort for the recommended do-now subset (below):
  m across maybe 8 child PRDs.
- **Current state**: partially landed. PRD-600.2.7 (delete dead cli stub)
  is already done (survey confirms `src/darkfactory/cli.py` is gone).
  PRD-600.2.4 (single-source version) is landed via PRD-622's
  `[tool.hatch.version]` configuration — supersede. Nothing else in
  the 600.x tree has landed.
- **Recommendation**: treat PRD-600 as a reference document, not an
  execution target. Plan the recommended subset instead:
  - **Phase 1 (safety)** — all four 600.1 children (keep 600.1.2, the
    shell-escape PRD — see its assessment; the earlier "moot" claim
    was a research miss).
  - **Phase 2 (tooling)** — 600.2.1 (ruff rules), 600.2.2 (pytest-cov),
    600.2.3 (`--version`), 600.2.5 (3.13 matrix), 600.2.6 (style.py
    tests). Skip 600.2.4 (already done) and 600.2.7 (already done).
  - **Phase 3 (operational)** — 600.3.1 (`_run_shell_once` extraction —
    overlaps heavily with PRD-621 and should probably land there),
    600.3.2 (`validate --json`), 600.3.3 (`tree --json`), 600.3.5
    (`cleanup --yes`), 600.3.6 (help epilogs), 600.3.7 (`prd show`),
    600.3.8 (loud workflow loading failures), 600.3.9 (reconcile
    pagination).
  - **Phase 4 (frontend optionality)** — defer entirely until a real
    frontend consumer appears. PRD-600.4.4 (HarnessError hierarchy)
    can land opportunistically alongside the first command that needs
    structured errors.
  - **Close the epic** once the do-now subset lands; don't let it
    become a roadmap black hole.

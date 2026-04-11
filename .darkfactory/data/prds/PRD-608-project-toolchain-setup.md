---
id: PRD-608
title: Project Toolchain Setup Wizard
kind: epic
status: draft
priority: medium
effort: l
capability: complex
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/init.py
  - src/darkfactory/toolchain/__init__.py
  - src/darkfactory/cli/main.py
  - src/darkfactory/cli/setup.py
  - src/darkfactory/templates_builtin.py
  - src/darkfactory/runner.py
  - src/darkfactory/workflow.py
  - src/darkfactory/config.py
workflow:
assignee:
reviewers: []
target_version:
created: 2026-04-10
updated: 2026-04-10
tags:
  - onboarding
  - adoption
  - configuration
  - cli
  - toolchain
value: 8
---

# Project Toolchain Setup Wizard

## Summary

Make DarkFactory's deterministic workflow steps (lint, test, format, typecheck, prepare) configuration-driven rather than hardcoded. Add a setup wizard to `prd init` that detects the project's toolchain, maps detected tools to standard SDLC slots, and writes the results to `config.toml`. Workflows use a new `SdlcSlotTask` type that resolves slot names to configured commands at runtime via `ExecutionContext`.

## Motivation

Today, DarkFactory's built-in workflow templates hardcode check commands like `just lint`, `just test`, and `just typecheck`. This works for projects that use `just` with those exact recipe names, but breaks for everyone else. A new adopter using `npm run test` or `cargo clippy` has to either:

1. Create a `justfile` with wrapper recipes that call their real tools (friction, indirection)
2. Write custom workflow definitions from scratch (steep learning curve)

Neither is a good onboarding experience. The fix is to make workflows reference **standard SDLC slots** that are resolved to project-specific commands via `config.toml`. The setup wizard populates this config automatically by detecting the project's toolchain.

This also lays groundwork for:
- Agent fallback and substitution in workflows (separate PRD — queued)
- Conditional checks based on which files changed (separate PRD — queued)
- Agent-assisted detection for unusual projects (separate PRD — queued)

## Requirements

### R1: Standard SDLC Slots

Define a set of standard SDLC slots that workflows reference by name:

| Slot | Purpose | Example commands |
|------|---------|-----------------|
| `prepare` | Prep a worktree for work (dependency install, codegen) | `uv sync`, `npm install`, `cargo fetch` |
| `lint` | Static analysis / linting | `ruff check .`, `eslint .`, `golangci-lint run` |
| `format` | Code formatting verification | `ruff format --check .`, `prettier --check .` |
| `test` | Unit/integration test suite | `pytest`, `npm test`, `cargo test` |
| `typecheck` | Static type checking | `mypy .`, `tsc --noEmit`, `pyright` |
| `build` | Compilation / build verification | `npm run build`, `cargo build`, `go build ./...` |

1. Each slot is optional — a project may not have a type checker
2. Each slot maps to one or more shell commands (list of strings)
3. Slots can be explicitly disabled (`false`)
4. Workflows reference slots by name via `SdlcSlotTask`, never by raw command string
5. Each `SdlcSlotTask` declares a `critical: bool` flag. This is set by the workflow template author, not by the user.
6. Default workflow templates mark `lint` and `test` as critical. Start strict — relax based on user feedback.
7. A slot set to `false` in config is always skipped, regardless of the task's `critical` flag — the user explicitly opted out.
8. An absent slot (not in config at all) fails the workflow if `critical=True`, skips silently if `critical=False`.

### R2: Config Schema

The `[sdlc-slots]` section in `config.toml`:

```toml
[sdlc-slots]
# Single command
lint = "ruff check ."

# Multiple commands for one slot (all must pass)
format = ["ruff format --check .", "prettier --check ."]

# Worktree preparation
prepare = "uv sync"

test = "pytest"
typecheck = "mypy ."

# Explicitly disabled
build = false
```

1. String value: single shell command
2. List of strings: multiple commands, all executed in order, all must pass
3. `false`: explicitly disabled (slot is known but skipped)
4. Absent key: not configured — workflow behavior depends on whether the slot is critical

### R3: Config Validation via Pydantic

1. Define a Pydantic model for the full `config.toml` schema, including the `[sdlc-slots]` section
2. Config is validated at load time — parse errors fail fast with clear messages
3. Prefer parsing errors over runtime shape checks (validate once at the boundary, trust the types internally)
4. No backwards compatibility shims — if a project has broken or outdated config, fail with a clear message explaining what needs to change and how

### R4: `SdlcSlotTask` Workflow Task Type

1. New task type alongside `BuiltIn`, `AgentTask`, and `ShellTask`
2. References a slot by name and declares criticality (e.g., `SdlcSlotTask(slot="lint", critical=True)`)
3. At execution time, `ExecutionContext` resolves the slot name to command(s) from config
4. Resolution logic lives in `ExecutionContext`, not in the task itself
5. If the slot maps to multiple commands, they run sequentially and all must pass
6. Resolution precedence for a slot at runtime:
   - Config value is a string or list → execute the command(s)
   - Config value is `false` → skip (user explicitly opted out, even if `critical=True`)
   - Slot absent from config + `critical=True` → fail with actionable error
   - Slot absent from config + `critical=False` → skip silently

### R5: Workflow Template Migration

1. Modify built-in workflow templates to use `SdlcSlotTask` instead of hardcoded `ShellTask` commands
2. The `prepare` slot is invoked during worktree setup (before implementation begins)
3. `lint`, `format`, `test`, `typecheck` slots are invoked during the verification phase (after implementation)
4. `build` slot is invoked where applicable (e.g., compiled languages)
5. Remove hardcoded `just` commands from templates entirely — no fallback to old behavior

### R6: Toolchain Detection Engine

A detection engine that statically analyzes the project to identify tools. Structured as a `toolchain/` package with per-ecosystem detector modules and peer test files.

**Package structure:**
```
src/darkfactory/toolchain/
    __init__.py          # ToolchainDetector, DetectionResult, public API
    _python.py           # Python ecosystem detector
    _python_test.py      # Python detector tests
    _node.py             # Node.js ecosystem detector
    _node_test.py        # Node detector tests
    _rust.py             # Rust ecosystem detector
    _rust_test.py        # Rust detector tests
    _go.py               # Go ecosystem detector
    _go_test.py          # Go detector tests
    _jvm.py              # JVM ecosystem detector
    _jvm_test.py         # JVM detector tests
    _task_runners.py     # Cross-ecosystem task runner scanner (justfile, Makefile, etc.)
    _task_runners_test.py
    _ci.py               # CI config scanner (GitHub Actions, GitLab CI, etc.)
    _ci_test.py
```

**Detection sources (in priority order):**
1. **Task runners**: `justfile`, `Makefile`, `package.json` scripts, `Taskfile.yml` — extract recipe/script names that map to standard slots
2. **CI configs**: `.github/workflows/*.yml`, `.gitlab-ci.yml`, `.circleci/config.yml` — extract check commands from CI steps
3. **Tool configs**: `ruff.toml`, `.eslintrc.*`, `mypy.ini`, `tsconfig.json`, `.prettierrc` — presence implies the tool is in use
4. **Lock files / dependencies**: `uv.lock`, `package-lock.json`, `Cargo.lock` — confirm tool availability

**Detection algorithm:**
1. Identify project language(s) from manifest files
2. Scan task runner configs for recipes matching standard slot names
3. Scan CI configs for commands that fulfill standard slots
4. Fall back to tool config file presence
5. For each slot, pick the highest-confidence match
6. Optionally run an LLM summarizer/checker over detection results to flag inconsistencies or suggest corrections (opt-in, not default)

**Each detector:**
- Is a separate module file within the `toolchain/` package
- Has a peer test file in the same directory
- Implements a common interface: `detect(project_root: Path) -> dict[str, str | list[str]]`
- Returns a mapping of slot names to suggested commands
- Is independently testable with fixture-based project layouts

### R7: Setup Wizard Flow

The wizard runs as part of `prd init` and can be re-invoked via `prd setup`:

```
$ prd init
Initializing .darkfactory/ ... done

Detecting project toolchain...

  Detected:
    Language:   Python (pyproject.toml)
    Prepare:    uv sync               (from uv.lock)
    Lint:       ruff check .          (from justfile recipe 'lint')
    Format:     ruff format --check . (from justfile recipe 'fmt')
    Test:       pytest                (from justfile recipe 'test')
    Typecheck:  mypy .                (from justfile recipe 'typecheck')
    Build:      (not detected)

  Accept these defaults? [Y/n/edit]
```

1. **One-shot presentation**: Show all detected tools and their mappings at once
2. **Accept** (`Y` or Enter): Write all to `config.toml`
3. **Reject** (`n`): Skip toolchain config — user can run `prd setup` later
4. **Edit** (`e`): Walk through each slot interactively:
   - Confirm or change the detected command
   - Add commands for undetected slots
   - Disable detected slots
5. **Undetected slot prompts**: For slots that were not detected but are used by standard workflows, the wizard asks explicitly:

```
  No type checker detected.
    [c] Configure manually  [x] Exclude from workflows  [s] Skip for now
```

   - **Configure** (`c`): User enters the command
   - **Exclude** (`x`): Writes `typecheck = false` to config — workflows will skip this step
   - **Skip** (`s`): Leave absent — workflows with `critical=True` for this slot will fail at runtime (forcing the user to decide later)

6. Summary: Shows what was written to `config.toml`, including any excluded slots

### R8: Re-run Behavior

When `prd setup` is run on a project that already has `[sdlc-slots]` configured:

1. Run detection again (toolchain may have changed)
2. Show current config vs. new detection side-by-side
3. Highlight additions (newly detected tools), removals (tools no longer detected), and changes
4. User can accept updates, keep current, or edit

## Technical Approach

### Architecture

```
prd init / prd setup
      │
      ▼
  ToolchainDetector
      │
      ├── _python.detect()         → {lint: "ruff check .", ...}
      ├── _node.detect()           → {test: "npm test", ...}
      ├── _task_runners.detect()   → {lint: "just lint", ...}
      ├── _ci.detect()             → {test: "pytest", ...}
      └── resolve_slots()          → merge by priority, deduplicate
      │
      ▼
  SetupWizard (interactive)
      │
      ▼
  config.toml [sdlc-slots] section
      │
      ▼
  ExecutionContext resolves slots → SdlcSlotTask executes commands
```

### Key Design Decisions

- **Config is the source of truth, not detection.** Detection populates config; config drives workflows. Users can always override.
- **No backwards compatibility.** Old hardcoded `just` commands are removed from templates. Projects with broken or missing config get a clear error message explaining what to configure.
- **Parse errors at the boundary.** Config is validated via Pydantic at load time. Once loaded, code trusts the types — no defensive shape checks at every call site.
- **Hard failures for critical slots.** Default workflow templates require `lint` and `test` to be configured. Missing critical slots = workflow fails with an actionable error. This can be relaxed based on user experience.
- **Module-per-detector.** Each ecosystem detector lives in its own file with a peer test file. This fights file bloat and keeps context small for both humans and agents.

## Acceptance Criteria

- [ ] `prd init` runs toolchain detection and presents the setup wizard
- [ ] `prd setup` can be run independently to (re)configure SDLC slots
- [ ] Detection correctly identifies Python, Node.js, Rust, and Go projects
- [ ] Detection extracts commands from `justfile`, `Makefile`, and `package.json` scripts
- [ ] Detection extracts commands from GitHub Actions workflow files
- [ ] Detection infers tools from config file presence (e.g., `ruff.toml` → `ruff check .`)
- [ ] Each ecosystem detector is a separate module with peer test file
- [ ] One-shot presentation shows all detected tools with accept/reject/edit options
- [ ] Edit mode walks through each slot interactively
- [ ] Results written to `[sdlc-slots]` section in `config.toml`
- [ ] Re-running `prd setup` shows current vs. detected diff
- [ ] Config validated via Pydantic model at load time with clear parse errors
- [ ] `SdlcSlotTask` resolves slot names via `ExecutionContext` from config
- [ ] Multi-command slots execute all commands sequentially, all must pass
- [ ] Built-in workflow templates use `SdlcSlotTask` instead of hardcoded commands
- [ ] `SdlcSlotTask` declares `critical` flag per slot usage in workflow templates
- [ ] Absent + critical slot fails the workflow with actionable error
- [ ] Absent + non-critical slot skips silently
- [ ] Disabled slots (`false`) always skip regardless of criticality
- [ ] Wizard prompts for undetected slots: configure manually, exclude, or skip
- [ ] `prepare` slot runs during worktree setup
- [ ] Projects with broken config get a clear error message (no silent fallback)
- [ ] All new code has tests
- [ ] `prd setup --help` shows usage with examples

## Deferred / Follow-up Items

These are explicitly out of scope but queued as separate PRDs:

1. **Agent fallback and substitution in workflows** — When a deterministic check fails, optionally invoke an agent to diagnose or fix. Also: allow agent tasks to substitute for missing deterministic checks (e.g., no linter configured → agent does a lint-like review).

2. **Conditional checks by file path** — Run additional or different checks when file changes intersect with certain directories (e.g., `npm test` only when `frontend/` changes). Requires `[sdlc-slots]` config to become hierarchical with path predicates.

3. **Agent-assisted detection** — When static detection can't determine the right commands, use an agent to analyze the project and suggest check commands.

## Resolved Decisions

1. **Command placement**: Part of `prd init` flow, also standalone as `prd setup`.
2. **Detection approach**: Static/deterministic in v1, with optional LLM summarizer/checker.
3. **Config section name**: `[sdlc-slots]` in `config.toml`.
4. **Config validation**: Pydantic models, fail fast at parse time.
5. **Backwards compatibility**: None. Clear error messages for broken config.
6. **Failure mode**: `critical` flag on `SdlcSlotTask` determines behavior for absent slots. `false` in config always means skip (user override). Hard failures for absent+critical. Relax based on user feedback.
7. **Multi-command slots**: List of strings, all must pass.
8. **Module structure**: `toolchain/` package with per-ecosystem modules and peer test files.
9. **Interactive flow**: One-shot presentation, optional per-slot walkthrough on "edit".
10. **Slot resolution**: `ExecutionContext` resolves slot → command(s). `SdlcSlotTask` is the workflow task type.

## Open Questions

(None remaining.)

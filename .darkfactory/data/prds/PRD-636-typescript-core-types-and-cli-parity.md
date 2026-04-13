---
id: PRD-636
title: TypeScript core types and CLI parity
kind: task
status: draft
priority: high
effort: m
capability: complex
parent:
depends_on:
  - "[[PRD-635-typescript-scaffold-and-core-types]]"
blocks: []
impacts:
  - ts/src/
workflow: task
assignee:
reviewers: []
target_version:
created: 2026-04-13
updated: '2026-04-13'
tags:
  - infrastructure
  - typescript
---

# TypeScript core types and CLI parity

## Summary

Seed the three hardest-to-port type constructs (PhaseState registry, payload classes, Result union) and wire up a no-op CLI that mirrors every Python subcommand. This validates the core type design and establishes CLI surface parity before bulk porting begins.

## Motivation

The type-keyed PhaseState registry is the single architectural hotspot in the TypeScript port. Implementing it first — along with all payload classes and the Result discriminated union — validates the core design decision (class constructors as map keys) before bulk porting begins. The no-op CLI establishes the full command surface so subsequent PRDs can fill in implementations one command at a time.

## Requirements

### Core type system

#### 1. `engine/phase-state.ts` — type-keyed registry

Class-constructor-keyed registry with generic `.get<T>(key)` returning `T`. Uses `new (...args: any[]) => T` as key type so TypeScript infers return type from the constructor argument.

Methods matching Python semantics:
- `put(value)` — stores value keyed by its constructor
- `get(key)` — returns typed value or throws
- `get(key, default)` — returns typed value or default
- `has(key)` — boolean check

The `Map<Function, unknown>` internal store is the one place `any` is permitted.

#### 2. `engine/payloads.ts` — frozen payload classes

All 10 payload classes as TypeScript classes with `readonly` fields:

| Class | Fields |
|-------|--------|
| `CodeEnv` | `repoRoot: string`, `cwd: string` |
| `PrdWorkflowRun` | `prd: PRD`, `workflow: Workflow`, `runSummary?: string` |
| `ProjectRun` | `workflow: Workflow`, `prds: Map<string, PRD>`, `targets: readonly string[]`, `targetPrd?: string` |
| `WorktreeState` | `branch: string`, `baseRef: string`, `worktreePath?: string` |
| `PrRequest` | `title: string`, `body: string` |
| `PrResult` | `url?: string` |
| `PrdContext` | `summary: string`, `body: string`, `parentRef?: string`, `dependencyRefs: readonly string[]` |
| `AgentResult` | `stdout: string`, `stderr: string`, `exitCode: number`, `success: boolean`, `failureReason?: string`, `toolCounts: Map<string, number>`, `sentinel?: string`, `model: string`, `invokeCount: number` |
| `CandidateList` | `prdIds: readonly string[]` |
| `ReworkState` | `prNumber?: number`, `reviewThreads?: readonly ReviewThread[]`, `replyToComments: boolean`, `commentFilters?: CommentFilters` |

Supporting types to define alongside:
- `ReviewThread` — interface matching Python dataclass
- `CommentFilters` — interface matching Python dataclass
- `PRD` — forward-reference interface (minimal shape, refined in later PRD)
- `Workflow` — forward-reference interface (minimal shape, refined in later PRD)

#### 3. `utils/result.ts` — discriminated union

Generic `Result<T, E>` pattern:

```typescript
interface Ok<T> { readonly kind: "ok"; readonly value: T; readonly stdout: string }
interface Err<E> { readonly kind: "err"; readonly error: E }
type Result<T, E> = Ok<T> | Err<E>
```

Domain-specific error types:
- `GitErr` — `returncode`, `stdout`, `stderr`, `cmd`
- `GhErr` — `returncode`, `stdout`, `stderr`, `cmd`
- `Timeout` — `cmd`, `timeout`

Convenience type aliases:
- `GitResult<T> = Result<T, GitErr>`
- `GhResult<T> = Result<T, GhErr>`
- `CheckResult = Result<null, GitErr | Timeout>`
- `GhCheckResult = Result<null, GhErr | Timeout>`

Type guard functions: `isOk()`, `isErr()`, plus constructor helpers `ok()`, `err()`.

### CLI parity — no-op commands

Register every Python CLI subcommand as a no-op in the TypeScript CLI. Each command should:
- Accept the same positional/flag arguments as the Python version
- Print `"not yet implemented"` and exit 0
- Be wired into a root command parser

Commands to register:

| Command | Description |
|---------|-------------|
| `init` | Scaffold .darkfactory/ in the current project |
| `new` | Create a new draft PRD from a template |
| `discuss` | Open interactive discussion for a PRD |
| `archive` | Move a completed PRD to the archive |
| `status` | DAG overview and counts |
| `next` | List actionable PRDs |
| `validate` | Cycle/missing-dep/orphan checks |
| `tree` | Show containment tree |
| `children` | Direct children of a PRD |
| `orphans` | Top-level PRDs (no parent) |
| `undecomposed` | Epics/features lacking task children |
| `conflicts` | Show file impact overlaps |
| `list-workflows` | Show loaded workflows with priorities |
| `assign` | Compute workflow assignment per PRD |
| `normalize` | Canonicalize list fields |
| `plan` | Show the execution plan for a PRD |
| `run` | Run a workflow against a PRD |
| `rework` | Address PR review feedback for a PRD |
| `rework-watch` | Polling daemon: auto-trigger rework on new PR comments |
| `reconcile` | Find merged-but-not-flipped PRDs |
| `cleanup` | Remove worktrees for completed PRDs |
| `reset` | Reset outstanding work on a PRD |
| `project list` | List all available project operations |
| `project describe` | Show metadata for a project operation |
| `project run` | Run a project operation |

CLI parser library choice is open — `commander`, `yargs`, or Bun-native arg parsing are all acceptable. Prefer whichever is lightest.

### Colocated tests

Each core type file must have a `.test.ts` peer:
- `engine/phase-state.test.ts` — put/get/has, type inference, missing key throws, default value
- `engine/payloads.test.ts` — construction, readonly enforcement, PhaseState round-trip
- `utils/result.test.ts` — ok/err construction, type guards, type narrowing
- `cli/index.test.ts` — smoke test that each command is registered

## Acceptance criteria

- [ ] `ts/src/engine/phase-state.ts` implements type-keyed registry with generic get
- [ ] `ts/src/engine/payloads.ts` defines all 10 payload classes with readonly fields
- [ ] `ts/src/utils/result.ts` defines `Result<T, E>` discriminated union with type guards
- [ ] `GitErr`, `GhErr`, `Timeout` and convenience aliases defined
- [ ] `ReviewThread`, `CommentFilters`, `PRD`, `Workflow` interfaces defined
- [ ] CLI registers all 25 commands as no-ops
- [ ] Each core file has a colocated `.test.ts` with passing tests
- [ ] `bun test` and `bun run typecheck` pass
- [ ] No `any` types except in PhaseState internals (`Map<Function, unknown>` store)

## Out of scope

- Implementing any CLI command behavior
- Porting operations, builtins, or workflow definitions
- npm publishing or CI pipeline
- Making the TS CLI the default entry point

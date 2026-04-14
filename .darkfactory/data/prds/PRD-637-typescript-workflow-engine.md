---
id: PRD-637
title: TypeScript workflow engine and security-review workflow
kind: task
status: ready
priority: high
effort: l
capability: complex
parent:
depends_on:
  - "[[PRD-636-typescript-utils-layer]]"
blocks: []
impacts:
  - ts/src/engine/
  - ts/src/workflow/
  - ts/src/cli/
workflow: task
assignee:
reviewers: []
target_version:
created: 2026-04-13
updated: 2026-04-14
tags:
  - infrastructure
  - typescript
---

# TypeScript workflow engine and security-review workflow

## Summary

Build the generic workflow execution engine on top of the utils layer ([[PRD-636-typescript-utils-layer]]) and prove it works end-to-end with a real `security-review` workflow that scans the codebase, proposes fixes, and opens a PR — all without depending on the PRD/SDLC data model.

## Motivation

The workflow engine is the core orchestration layer. It must be generic — know nothing about PRDs or SDLC status. Domain-specific adapters seed context and plug in specialized task factories later. Building the engine first with a real workflow validates the TypeScript architecture before layering SDLC modeling on top.

The `security-review` workflow exercises the full pipeline — discovery, loading, worktree creation, agent invocation, git operations, shell verification, PR creation — while being independently useful.

## Architecture overview

```
┌─────────────────────────────────────────────────┐
│  CLI: list-workflows, run <workflow>             │
├─────────────────────────────────────────────────┤
│  Discovery: scan dirs for workflow.ts modules    │
├─────────────────────────────────────────────────┤
│  WorkflowBuilder: compile-time context wiring    │
├─────────────────────────────────────────────────┤
│  Engine: runTasks() — resolve inputs, dispatch,  │
│          store outputs, short-circuit on failure  │
├─────────────────────────────────────────────────┤
│  Task<TReads, TWrites> factories:                │
│  createWorktree, enterWorktree, agentTask,       │
│  shellTask, commitTask, pushBranch, createPr     │
├─────────────────────────────────────────────────┤
│  Branded payloads + PhaseState registry          │
├─────────────────────────────────────────────────┤
│  utils/ (PRD-636): subprocess, git, gh, claude   │
└─────────────────────────────────────────────────┘
```

SDLC modeling (PRD model, status tracking, predicate routing) is **not in this PRD** — it layers on top via adapters that seed context and provide domain-specific task factories.

## Design

### Branded payloads with compile-time context validation

Every payload class carries a phantom `_brand` type (erased at runtime, enforced at compile time via `declare readonly`). The `WorkflowBuilder` accumulates brands as tasks are added. TypeScript enforces at compile time that every task's reads are satisfied by the accumulated context — a missing dependency is a compile error, not a runtime crash.

```typescript
// Compile error — agentTask reads "CodeEnv" but nothing provides it
const bad = workflow("broken", "")
  .add(agentTask({ name: "x", prompt: "...", tools: [] }))  // ERROR: "CodeEnv" not in never
  .build();
```

`declare readonly _brand` fields are compatible with `erasableSyntaxOnly: true` — they are phantom types that exist only in TypeScript's type system, not emitted to JavaScript.

### Unified Task interface with single-output decomposition

All tasks implement `Task<TReads, TWrites>` — a single interface with branded phantom type parameters. Each task type is a **factory function** that returns a `Task` with typed config captured in the closure. The engine doesn't dispatch by type — it resolves inputs from declared `reads`, calls `task.run()`, and stores outputs via declared `writes`.

This eliminates class hierarchies, runtime registries, `instanceof` dispatch, and untyped kwargs bags. A missing import is a compile error.

Each task factory has a **single output type**. Operations that would write multiple payload types are decomposed into separate single-output tasks (e.g., `createWorktree()` + `enterWorktree()` instead of a combined `ensureWorktree()`), keeping the builder's type algebra simple.

## Requirements

### 1. Core types

#### `engine/phase-state.ts` — composite-keyed registry

Constructor-keyed registry with optional string id for disambiguation. Id defaults to `"default"` so single-instance payloads need no ceremony.

Internal store: `Map<string, unknown>` keyed by `${constructor.name}:${id}`. This is the one place `any` is permitted.

Methods:
- `put(value, id?)` — store value keyed by constructor + id. **Overwrites** if a value for that composite key already exists. Id defaults to `"default"`.
- `get(key, id?)` — return typed value or throw. Id defaults to `"default"`.
- `get(key, id?, default)` — return typed value or default.
- `has(key, id?)` — boolean check. Id defaults to `"default"`.

Uses `new (...args: any[]) => T` as key type so TypeScript infers return type from the constructor argument.

#### `engine/payloads.ts` — branded engine-level payloads

Only the payloads the engine needs — no SDLC-specific types. All classes use `declare readonly _brand` phantom types and manual field assignment in the constructor (compatible with `erasableSyntaxOnly`).

```typescript
class CodeEnv {
  declare readonly _brand: "CodeEnv";
  readonly repoRoot: string;
  readonly cwd: string;
  constructor(init: { repoRoot: string; cwd: string }) {
    this.repoRoot = init.repoRoot;
    this.cwd = init.cwd;
  }
}
```

| Class | Brand | Purpose | Fields |
|-------|-------|---------|--------|
| `CodeEnv` | `"CodeEnv"` | Execution environment | `repoRoot: string`, `cwd: string` |
| `WorktreeState` | `"WorktreeState"` | Git branch context | `branch: string`, `baseRef: string`, `worktreePath?: string` |
| `PrRequest` | `"PrRequest"` | PR creation input | `title: string`, `body: string` |
| `PrResult` | `"PrResult"` | PR creation output | `url?: string` |
| `AgentResult` | `"AgentResult"` | Agent invocation result | `stdout: string`, `stderr: string`, `exitCode: number`, `success: boolean`, `failureReason?: string`, `toolCounts: Readonly<Record<string, number>>`, `sentinel?: string`, `model: string`, `invokeCount: number` |

SDLC payloads (`PrdWorkflowRun`, `ProjectRun`, `PrdContext`, `CandidateList`, `ReworkState`) are deferred to the SDLC modeling PRD.

#### `engine/types.ts` — execution and wiring types

```typescript
interface TaskEnv {
  readonly dryRun: boolean;
}

interface TaskOutput<T = void> {
  readonly success: boolean;
  readonly failureReason?: string;
  readonly value?: T;
}

interface TaskStepResult {
  readonly name: string;
  readonly success: boolean;
  readonly failureReason?: string;
}

interface RunResult {
  readonly success: boolean;
  readonly failureReason?: string;
  readonly steps: readonly TaskStepResult[];
}

type InputMapping = Record<string, string | ((state: PhaseState) => string)>;

interface WrappedTask {
  readonly task: Task;
  readonly inputMapping?: InputMapping;
  readonly outputId?: string;
}
```

`RunResult.steps` is `readonly` in the public interface. The engine builds a mutable array internally and returns it — standard TypeScript widening.

### 2. Task interface and factories

#### `engine/task.ts` — unified task interface

```typescript
type PayloadClass<T = unknown> = new (...args: any[]) => T;

type BrandOf<T> = T extends { readonly _brand: infer B extends string } ? B : never;

// Type-safe resolver — generic on the class constructor
type InputResolver = <T>(cls: PayloadClass<T>, id?: string) => T;

interface Task<
  TReads extends string = string,
  TWrites extends string = never,
> {
  readonly name: string;
  readonly reads: readonly PayloadClass[];
  readonly writes?: PayloadClass;
  run(env: TaskEnv, resolve: InputResolver): Promise<TaskOutput>;
}
```

`TReads` and `TWrites` are phantom type parameters — they exist purely for the builder's compile-time constraint checking. The engine uses the runtime `reads` and `writes` fields for pre-validation.

Tasks pull inputs via `resolve(Class)`, which returns a value typed by the class constructor's return type. The engine builds the resolver from `PhaseState` + the task's `inputMapping` (from `from()`). Resolution order:

1. Task passes explicit `id` → use it directly
2. `inputMapping` has entry for this class → use mapped id
3. Neither → `"default"`

This eliminates positional ordering bugs — tasks resolve inputs by type, not position.

#### Task factory functions

Individual files under `engine/tasks/` with a barrel `index.ts`:

```
engine/tasks/
  index.ts              # re-exports all factories
  agent-task.ts
  agent-task.test.ts
  shell-task.ts
  shell-task.test.ts
  git-tasks.ts          # createWorktree, enterWorktree, commitTask, pushBranch, createPr
  git-tasks.test.ts
```

All task factories:
- Return correctly branded `Task<TReads, TWrites>`
- Honor `env.dryRun` (log what they would do, return success)
- Call through the utils layer — never import `child_process` or `Bun` directly
- Handle `Result` values from utils-layer calls explicitly (via `ts-pattern` or type guards) — no ignored error paths

| Factory | Config | Reads (brands) | Writes (brand) |
|---------|--------|----------------|----------------|
| `createWorktree()` | — | `"WorktreeState" \| "CodeEnv"` | `"WorktreeState"` |
| `enterWorktree()` | — | `"WorktreeState"` | `"CodeEnv"` |
| `agentTask({...})` | `name`, `prompt`, `tools`, `model?`, `sentinelSuccess?`, `sentinelFailure?` | `"CodeEnv"` | `"AgentResult"` |
| `shellTask({...})` | `name`, `cmd`, `onFailure: "fail" \| "ignore"`, `env?` | `"CodeEnv"` | `never` |
| `commitTask({...})` | `message`, `files?: string[]` (defaults to `["."]`) | `"CodeEnv"` | `never` |
| `pushBranch()` | — | `"WorktreeState"` | `never` |
| `createPr()` | — | `"PrRequest" \| "WorktreeState"` | `"PrResult"` |

**`agentTask` — representative implementation:**

```typescript
function agentTask(config: {
  name: string;
  prompt: string;
  tools: string[];
  model?: string;
  sentinelSuccess?: string;
  sentinelFailure?: string;
}): Task<"CodeEnv", "AgentResult"> {
  return {
    name: config.name,
    reads: [CodeEnv] as const,
    writes: AgentResult,
    async run(env, resolve) {
      const codeEnv = resolve(CodeEnv);
      if (env.dryRun) {
        return { success: true, value: /* dry-run AgentResult */ };
      }

      const result = await invokeClaude({
        cwd: codeEnv.cwd,
        prompt: config.prompt,
        tools: config.tools,
        model: config.model,
      });

      return match(result)
        .with({ kind: "ok" }, ({ value: inv }) => {
          const sentinels = parseSentinels(inv.stdout, {
            success: config.sentinelSuccess,
            failure: config.sentinelFailure,
          });

          // Failure sentinel wins over success sentinel
          if (sentinels.failure) {
            return {
              success: false,
              failureReason: "Failure sentinel found in agent output",
              value: new AgentResult({ ...inv, success: false }),
            };
          }
          if (sentinels.success) {
            return {
              success: true,
              value: new AgentResult({ ...inv, success: true }),
            };
          }

          // No sentinels matched — fall back to exit code
          const ok = inv.exitCode === 0;
          return {
            success: ok,
            failureReason: ok ? undefined : `Agent exited with code ${inv.exitCode}`,
            value: new AgentResult({ ...inv, success: ok }),
          };
        })
        .with({ kind: "err" }, ({ error }) => ({
          success: false,
          failureReason: `Agent invocation failed: ${error.message}`,
        }))
        .exhaustive();
    },
  };
}
```

**Sentinel resolution order:**
1. `sentinelFailure` found → **failure** (wins over sentinelSuccess)
2. `sentinelSuccess` found → **success**
3. Neither found, exit code 0 → **success**
4. Neither found, exit code non-zero → **failure**
5. No sentinels configured → exit code determines outcome

**`commitTask` — representative git task:**

```typescript
function commitTask(config: {
  message: string;
  files?: string[];
}): Task<"CodeEnv", never> {
  const filesToStage = config.files ?? ["."];
  return {
    name: "commit",
    reads: [CodeEnv] as const,
    async run(env, resolve) {
      const codeEnv = resolve(CodeEnv);
      if (env.dryRun) return { success: true };

      const addResult = await gitAdd(filesToStage, { cwd: codeEnv.cwd });
      if (isErr(addResult)) {
        return { success: false, failureReason: `git add failed: ${addResult.error.message}` };
      }

      const commitResult = await gitCommit(config.message, { cwd: codeEnv.cwd });
      if (isErr(commitResult)) {
        return { success: false, failureReason: `git commit failed: ${commitResult.error.message}` };
      }

      return { success: true };
    },
  };
}
```

`gitAdd(".")` is the correct default for workflow-managed worktrees — the worktree exists solely for the workflow's changes. The optional `files` config supports selective staging when needed.

Defer `InteractiveTask` and `onFailure: "retry_agent"`.

### 3. Workflow interface

#### `workflow/core.ts`

```typescript
interface Workflow {
  readonly name: string;
  readonly description: string;
  readonly seeds: readonly unknown[];
  readonly tasks: readonly WrappedTask[];
}
```

`seeds` carries the raw payload values accumulated by the builder. The runner creates a `PhaseState`, puts each seed, then executes tasks. This keeps `Workflow` a plain data object — no methods, no state ownership.

### 4. WorkflowBuilder

#### `workflow/builder.ts`

The builder tracks available payload brands as a type parameter. Each `.seed()` and `.add()` returns a new builder with the brand union extended. `.add()` enforces at compile time that all task reads are a subset of the accumulated context.

```typescript
class WorkflowBuilder<Ctx extends string = never> {
  private readonly _name: string;
  private readonly _description: string;
  private readonly _seeds: Array<{ value: unknown }>;
  private readonly _tasks: WrappedTask[];

  constructor(name: string, description: string) { ... }

  // Seed initial context — adds the value's brand to Ctx
  seed<T extends { readonly _brand: string }>(
    value: T,
  ): WorkflowBuilder<Ctx | BrandOf<T>> {
    this._seeds.push({ value });
    return this as unknown as WorkflowBuilder<Ctx | BrandOf<T>>;
  }

  // Add a task — TReads must be a subset of Ctx
  add<R extends Ctx, W extends string>(
    task: Task<R, W>,
  ): WorkflowBuilder<Ctx | W> {
    this._tasks.push({ task, inputMapping: undefined, outputId: undefined });
    return this as unknown as WorkflowBuilder<Ctx | W>;
  }

  // Add a task with named output — for disambiguation when multiple
  // tasks produce the same payload type
  named<R extends Ctx, W extends string>(
    id: string,
    task: Task<R, W>,
  ): WorkflowBuilder<Ctx | `${W}:${string}`> {
    this._tasks.push({ task, inputMapping: undefined, outputId: id });
    return this as unknown as WorkflowBuilder<Ctx | `${W}:${string}`>;
  }

  // Add a task with explicit input mapping — resolves reads from
  // specific named ids instead of "default"
  from<R extends Ctx, W extends string>(
    mapping: InputMapping,
    task: Task<R, W>,
  ): WorkflowBuilder<Ctx | W> {
    this._tasks.push({ task, inputMapping: mapping, outputId: undefined });
    return this as unknown as WorkflowBuilder<Ctx | W>;
  }

  build(): Workflow {
    return {
      name: this._name,
      description: this._description,
      seeds: this._seeds.map((s) => s.value),
      tasks: this._tasks,
    };
  }
}

// Convenience entry point
function workflow(name: string, description: string): WorkflowBuilder<never> {
  return new WorkflowBuilder(name, description);
}
```

**Multi-agent example — named outputs and `from()`:**

```typescript
export function create(cwd: string): Workflow {
  return workflow("scan-and-fix", "Scan, fix, verify")
    .seed(new CodeEnv({ repoRoot: cwd, cwd }))
    .seed(new WorktreeState({ branch: `scan-fix/${today()}`, baseRef: "main" }))
    .seed(new PrRequest({ title: "Security Fixes", body: "Automated scan and fix" }))
    .add(createWorktree())
    .add(enterWorktree())
    .named("scan", agentTask({ name: "scan", prompt: scanPrompt, tools: readOnlyTools }))
    .named("fix",  agentTask({ name: "fix",  prompt: fixPrompt,  tools: editTools }))
    .add(shellTask({ name: "verify", cmd: "just test", onFailure: "fail" }))
    .add(commitTask({ message: "security fixes" }))
    .add(pushBranch())
    .add(createPr())
    .build();
}
```

Both `AgentResult` values coexist in state under ids `"scan"` and `"fix"`. A downstream task can read from a specific id:

```typescript
// Static: always read AgentResult from id "fix"
.from({ AgentResult: "fix" }, customTask({ name: "summarize" }))

// Dynamic: resolve id at runtime based on state
.from(
  { AgentResult: (state) => state.has(AgentResult, "fix") ? "fix" : "scan" },
  customTask({ name: "report" }),
)
```

`from()` mappings are validated at runtime only — the builder cannot verify at compile time that a named id exists. The engine raises a clear error if a `from()` mapping references a nonexistent id.

### 5. Engine

#### `engine/runner.ts`

`runWorkflow` creates a `PhaseState` from the workflow's seeds, then delegates to `runTasks` which resolves inputs, dispatches, stores outputs, and short-circuits on failure.

```typescript
async function runWorkflow(
  wf: Workflow,
  env: TaskEnv,
): Promise<RunResult> {
  const state = new PhaseState();
  for (const seed of wf.seeds) {
    state.put(seed);
  }
  return runTasks(wf.tasks, state, env);
}

async function runTasks(
  tasks: readonly WrappedTask[],
  state: PhaseState,
  env: TaskEnv,
): Promise<RunResult> {
  const steps: TaskStepResult[] = [];

  for (const wrapped of tasks) {
    // 1. Build resolver with inputMapping baked in
    const resolve: InputResolver = (cls, id) => {
      if (id != null) return state.get(cls, id);
      const mapped = wrapped.inputMapping?.[cls.name];
      if (mapped != null) {
        const resolvedId = typeof mapped === "function" ? mapped(state) : mapped;
        return state.get(cls, resolvedId);
      }
      return state.get(cls, "default");
    };

    // 2. Run task — it pulls what it needs via resolve()
    const output = await wrapped.task.run(env, resolve);
    steps.push({
      name: wrapped.task.name,
      success: output.success,
      failureReason: output.failureReason,
    });

    // 3. Store output in state if task declares writes
    if (output.value != null && wrapped.task.writes != null) {
      state.put(output.value, wrapped.outputId ?? "default");
    }

    // 4. Short-circuit on failure
    if (!output.success) {
      return { success: false, failureReason: output.failureReason, steps };
    }
  }

  return { success: true, steps };
}
```

Input resolution errors (missing payload for a `reads` entry, or `from()` mapping referencing a nonexistent id) cause the task to fail with a descriptive error message naming the task, the expected payload type, and the missing key.

### 6. Workflow discovery

#### `workflow/loader.ts`

Scan directories for `workflow.ts` modules. Two layers:

1. **Built-in** — shipped with the package at `ts/src/workflow/definitions/`
2. **Project** — `<project>/.darkfactory/workflows/` (or configurable path)

Each direct subdirectory containing a `workflow.ts` is loaded via dynamic `import()`. The loader checks for:
- A `create(cwd: string): Workflow` factory function export (preferred), or
- A `workflow` constant export

The loader validates at runtime that the resolved workflow has `name` (string), `description` (string), and `tasks` (non-empty array).

Name collisions across layers raise an error. Import failures log a warning and skip.

Uses `import.meta.dirname` for built-in path resolution (compatible with Bun and Node 21.2+).

Defer user-layer discovery (`~/.config/darkfactory/workflows/`) — two layers are sufficient.

### 7. CLI

Two commands, manual `process.argv` parsing (no CLI library dependency):

#### `list-workflows`

Discover all workflows across both layers and display:
```
Available workflows:
  security-review    Scan codebase for security issues, propose fixes, open a PR
```

#### `run <workflow> [--dry-run]`

1. Discover workflows
2. Look up by name — fail with error and exit 1 if not found
3. If workflow module exports `create`, call `create(process.cwd())` to get a `Workflow` with seeds populated
4. Call `runWorkflow(workflow, { dryRun: options.dryRun })`
5. Report result

For constant exports (no `create`), the CLI constructs the `Workflow` directly, providing seeds for `CodeEnv` (from cwd) and `WorktreeState` (from workflow name + date).

### 8. Security-review workflow

Built-in workflow at `ts/src/workflow/definitions/security-review/`:

```
security-review/
  workflow.ts       # Workflow definition (exports create)
  scan.md           # Agent prompt
```

**Workflow definition (`workflow.ts`):**

```typescript
import { readFileSync } from "fs";
import { join } from "path";
import { workflow } from "../../workflow/builder";
import {
  createWorktree, enterWorktree, agentTask, shellTask,
  commitTask, pushBranch, createPr,
} from "../../engine/tasks";
import { CodeEnv, WorktreeState, PrRequest } from "../../engine/payloads";
import type { Workflow } from "../../workflow/core";

const scanPrompt = readFileSync(join(import.meta.dirname, "scan.md"), "utf-8");

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function create(cwd: string): Workflow {
  return workflow(
    "security-review",
    "Scan codebase for security issues, propose fixes, open a PR",
  )
    .seed(new CodeEnv({ repoRoot: cwd, cwd }))
    .seed(new WorktreeState({
      branch: `security-review/${today()}`,
      baseRef: "main",
    }))
    .seed(new PrRequest({
      title: `Security Review — ${today()}`,
      body: "Automated security scan findings",
    }))
    .add(createWorktree())
    .add(enterWorktree())
    .add(agentTask({
      name: "scan",
      prompt: scanPrompt,
      tools: ["Read", "Glob", "Grep", "Write", "Edit"],
      sentinelSuccess: "PRD_EXECUTE_OK",
    }))
    .add(shellTask({ name: "verify", cmd: "just test", onFailure: "ignore" }))
    .add(commitTask({ message: "chore: security review findings" }))
    .add(pushBranch())
    .add(createPr())
    .build();
}
```

Note: the `verify` step uses `just test` which assumes the project uses `just` as a task runner. `onFailure: "ignore"` makes this best-effort — the workflow proceeds regardless.

**Prompt (`scan.md`):**

```markdown
# Security Review

Scan this codebase for security vulnerabilities. Focus on:

## OWASP Top 10

- **Injection** — SQL injection, command injection, template injection in any language
- **Broken Authentication** — hardcoded credentials, weak token generation, missing auth checks
- **Sensitive Data Exposure** — secrets in source, unencrypted storage, verbose error messages leaking internals
- **XML External Entities (XXE)** — unsafe XML parsing configurations
- **Broken Access Control** — missing authorization checks, IDOR vulnerabilities, privilege escalation paths
- **Security Misconfiguration** — debug modes enabled, default credentials, overly permissive CORS
- **Cross-Site Scripting (XSS)** — unsanitized user input in HTML/template output
- **Insecure Deserialization** — untrusted data passed to deserializers (pickle, yaml.load, JSON.parse with reviver)
- **Using Components with Known Vulnerabilities** — check dependency files for known-vulnerable versions
- **Insufficient Logging & Monitoring** — sensitive operations without audit trails

## Additional checks

- Hardcoded secrets: API keys, passwords, tokens, private keys in source files
- Path traversal: user-controlled input used in file paths without sanitization
- Race conditions: TOCTOU bugs, shared mutable state without synchronization
- Subprocess injection: shell commands built from user input

## Instructions

1. Use Glob to discover all source files
2. Use Grep to search for vulnerability patterns
3. Use Read to examine suspicious files in detail
4. For each confirmed finding:
   - Identify the file and line number
   - Describe the vulnerability and its severity (critical/high/medium/low)
   - Apply a fix using Edit or Write
5. If no findings are discovered, that is a valid outcome — report it

Emit `PRD_EXECUTE_OK` when the scan is complete.
```

### 9. Tests

Colocated `.test.ts` for every module. All tests use `ts-pattern` matching on `Result` values where applicable.

| Test file | Coverage |
|-----------|----------|
| `engine/phase-state.test.ts` | put/get/has, put overwrites, type inference, missing key throws, default, composite keys with explicit id, default id fallback |
| `engine/payloads.test.ts` | construction, readonly, brand phantom types, PhaseState round-trip |
| `engine/runner.test.ts` | resolver builds correctly per task, inputMapping precedence, explicit id override, output storage via writes, failure short-circuits, step recording, missing-key error messages |
| `engine/tasks/agent-task.test.ts` | invokeClaude call, ts-pattern on Result, sentinel resolution (all 5 cases), AgentResult stored in state, dry-run |
| `engine/tasks/shell-task.test.ts` | command execution, onFailure "fail" vs "ignore", dry-run |
| `engine/tasks/git-tasks.test.ts` | createWorktree, enterWorktree, commitTask (default + explicit files), pushBranch, createPr — dry-run behavior, state reads/writes, Result handling |
| `workflow/builder.test.ts` | seed/add/named/from/build, compile-time constraint errors (manual type assertions) |
| `workflow/core.test.ts` | Workflow interface conformance |
| `workflow/loader.test.ts` | discovery from fixture directories, create() vs constant, name collision, malformed export |
| `cli/index.test.ts` | list-workflows output, run with dry-run |

Task factory tests pass a mock or real `InputResolver` — no positional arg ordering to validate.

## Acceptance criteria

### Core types
- [ ] All payload classes use `declare readonly _brand` phantom types for compile-time tracking
- [ ] Payload construction via manual field assignment (compatible with `erasableSyntaxOnly`)
- [ ] `PhaseState` implements composite-keyed registry (`constructor.name:id`), `put`/`get`/`has` with optional id (defaults to `"default"`)
- [ ] `RunResult` and `TaskStepResult` types with `readonly` public interface
- [ ] `TaskEnv` carries `dryRun` flag only
- [ ] `TaskOutput<T>` carries `success`, `failureReason?`, `value?: T`

### Task system
- [ ] `Task<TReads, TWrites>` interface with branded phantom type parameters and `run(env, resolve)` signature
- [ ] `InputResolver` type: generic `<T>(cls: PayloadClass<T>, id?: string) => T`
- [ ] Factory functions: `agentTask()`, `shellTask()`, `createWorktree()`, `enterWorktree()`, `commitTask()`, `pushBranch()`, `createPr()`
- [ ] All task factories have typed config (no `Record<string, unknown>` kwargs)
- [ ] Each task factory has single output type (multi-write decomposed into separate tasks)
- [ ] All task factories honor `env.dryRun` and call through utils layer
- [ ] All task factories resolve inputs via `resolve(Class)` — no positional parameter contracts
- [ ] All task factories handle `Result` values from utils-layer calls explicitly — no ignored error paths
- [ ] `agentTask` uses `ts-pattern` exhaustive matching on `Result` and sentinel logic
- [ ] Sentinel behavior: failure sentinel wins, exit code fallback when no sentinels configured
- [ ] `commitTask` accepts optional `files?: string[]`, defaults to `["."]`
- [ ] Task factories in individual files under `engine/tasks/` with barrel `index.ts`

### Builder
- [ ] `WorkflowBuilder<Ctx>` accumulates payload brands via `.seed()` and `.add()`
- [ ] `.add()` enforces `R extends Ctx` — compile error if task reads unsatisfied context
- [ ] `.named(id, task)` stores output under specific id
- [ ] `.from(mapping, task)` resolves inputs from specific ids (static string or dynamic function)
- [ ] `.build()` returns `Workflow` with seeds and tasks populated

### Workflow and engine
- [ ] `Workflow` as plain interface with `name`, `description`, `seeds: readonly unknown[]`, `tasks: readonly WrappedTask[]`
- [ ] `runWorkflow()` creates `PhaseState` from seeds, delegates to `runTasks()`
- [ ] `runTasks()` engine loop builds `InputResolver` per task (incorporating `inputMapping`), calls `task.run(env, resolve)`, stores outputs via `writes`, short-circuits on failure
- [ ] Resolver precedence: explicit id arg > `inputMapping` entry > `"default"`
- [ ] Engine raises clear error when resolution fails — message names the task, expected payload type, and missing key
- [ ] Workflow discovery from built-in and project layers
- [ ] Loader supports `create(cwd)` factory function or `workflow` constant export
- [ ] Loader validates exports at runtime (name, description, tasks array)
- [ ] Name collisions across layers raise error
- [ ] Uses `import.meta.dirname` (Bun + Node compatible)

### CLI
- [ ] `list-workflows` shows discovered workflows
- [ ] `run <name> [--dry-run]` executes full pipeline
- [ ] Manual `process.argv` parsing, no CLI library dependency
- [ ] `run security-review --dry-run` exercises full pipeline in dry-run

### Security-review workflow
- [ ] `scan.md` prompt with full OWASP Top 10 coverage
- [ ] Workflow defined via builder: `seed → createWorktree → enterWorktree → agentTask → shellTask → commitTask → pushBranch → createPr`
- [ ] Exported as `create(cwd)` factory function

### Quality
- [ ] `bun test` and `bun run typecheck` pass
- [ ] No `any` types except PhaseState internals
- [ ] Colocated `.test.ts` for every module

## Deferred

- `InteractiveTask` factory — add when discussion workflows are ported
- `onFailure: "retry_agent"` — add when verification retry is needed
- `WorkflowTemplate` (open/middle/close enforcement) — add when multiple workflows share structure
- Event logging (`EventWriter`) — add when observability is needed
- Worktree cleanup and locking — add when real (non-dry-run) execution is primary use case
- Sync task support — `run()` currently async-only, may support sync later
- User-layer workflow discovery (`~/.config/darkfactory/workflows/`)
- SDLC payloads, PRD model, predicate routing, status tracking — separate PRD
- SDLC-aware task factories (`prdAgentTask` etc.) — separate PRD
- Prompt template infrastructure (`{{PLACEHOLDER}}` substitution) — add as utility if workflows need it
- Integration tests for actual git/gh operations
- Timeout configuration system
- Pre-run wiring validation (`validateWiring()`) — compile-time builder checking handles the common case; runtime validation adds defense-in-depth for dynamically loaded project workflows

## Dependencies

- [[PRD-636-typescript-utils-layer]]: subprocess, git, gh, claude, Result types, `ts-pattern` matching

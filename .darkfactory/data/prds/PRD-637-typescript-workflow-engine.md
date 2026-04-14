---
id: PRD-637
title: TypeScript workflow engine and security-review workflow
kind: task
status: draft
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
  - ts/src/operations/
  - ts/src/cli/
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

# TypeScript workflow engine and security-review workflow

## Summary

Build the generic workflow execution engine on top of the utils layer ([[PRD-636-typescript-utils-layer]]) and prove it works end-to-end with a real `security-review` workflow that scans the codebase, proposes fixes, and opens a PR — all without depending on the PRD/SDLC data model.

## Motivation

The Python architecture cleanly separates the workflow engine from SDLC concepts. The engine (`run_tasks`, `PhaseState`, task dispatch) knows nothing about PRDs — adapters seed the context and plug in domain-specific builtins. Porting the engine first validates the TypeScript architecture with a real, useful workflow before layering SDLC modeling on top.

The `security-review` workflow exercises the full pipeline — discovery, loading, agent invocation, git operations, shell verification, PR creation — while being independently useful.

## Architecture overview

```
┌─────────────────────────────────────────────────┐
│  CLI: list-workflows, run <workflow>             │
├─────────────────────────────────────────────────┤
│  Discovery: scan dirs for workflow.ts modules    │
├─────────────────────────────────────────────────┤
│  Engine: runTasks() dispatch loop                │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ BuiltIn  │ │AgentTask │ │   ShellTask      │ │
│  │ dispatch │ │ compose  │ │   exec + policy  │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
├─────────────────────────────────────────────────┤
│  PhaseState: type-keyed inter-task registry      │
├─────────────────────────────────────────────────┤
│  utils/ (PRD-636): subprocess, git, gh, claude   │
└─────────────────────────────────────────────────┘
```

SDLC modeling (PRD model, status tracking, predicate routing) is **not in this PRD** — it layers on top via the same adapter pattern Python uses.

## Requirements

### 1. Core types

#### `engine/phase-state.ts` — type-keyed registry

Class-constructor-keyed registry. Uses `new (...args: any[]) => T` as key type so TypeScript infers return type from the constructor argument.

Methods matching Python semantics:
- `put(value)` — store value keyed by its constructor
- `get(key)` — return typed value or throw
- `get(key, default)` — return typed value or default
- `has(key)` — boolean check

The `Map<Function, unknown>` internal store is the one place `any` is permitted.

#### `engine/payloads.ts` — engine-level payloads only

Only the payloads the engine needs — no SDLC-specific types:

| Class | Purpose | Fields |
|-------|---------|--------|
| `CodeEnv` | Execution environment | `repoRoot: string`, `cwd: string` |
| `WorktreeState` | Git branch context | `branch: string`, `baseRef: string`, `worktreePath?: string` |
| `PrRequest` | PR creation input | `title: string`, `body: string` |
| `PrResult` | PR creation output | `url?: string` |
| `AgentResult` | Agent invocation result | `stdout`, `stderr`, `exitCode`, `success`, `failureReason?`, `toolCounts`, `sentinel?`, `model`, `invokeCount` |

All classes: `readonly` fields, constructed via constructor args.

SDLC payloads (`PrdWorkflowRun`, `ProjectRun`, `PrdContext`, `CandidateList`, `ReworkState`) are deferred to the SDLC modeling PRD.

### 2. Workflow types

#### `workflow/core.ts` — task types and workflow definition

Port from Python's `workflow/_core.py`. Pure data, no I/O.

**Task types:**

| Type | Key fields |
|------|-----------|
| `BuiltIn` | `name`, `kwargs: Record<string, unknown>` |
| `AgentTask` | `name`, `prompts: string[]`, `tools: string[]`, `model?`, `retries`, `verifyPrompts`, `sentinelSuccess`, `sentinelFailure` |
| `ShellTask` | `name`, `cmd`, `onFailure: "fail" \| "ignore"`, `env: Record<string, string>` |

Defer `InteractiveTask` — not needed for the security-review workflow.

Defer `onFailure: "retry_agent"` — start with `"fail"` and `"ignore"` only.

**Workflow:**

```typescript
class Workflow {
  readonly name: string;
  readonly description: string;
  readonly tasks: readonly Task[];
  workflowDir?: string;  // set by loader at discovery time
}
```

The `appliesTo` predicate and `priority` fields are SDLC-specific (predicate routing) — defer them.

**RunContext:**

```typescript
class RunContext {
  readonly dryRun: boolean;
  readonly state: PhaseState;
  readonly report: string[];

  get cwd(): string       // from CodeEnv
  get repoRoot(): string  // from CodeEnv

  formatString(template: string): string  // expand {placeholder} tokens
}
```

`formatString` resolves from all registered payloads: `{cwd}`, `{repo_root}`, `{branch}`, `{base_ref}`, `{worktree}`.

### 3. Engine

#### `engine/runner.ts` — task dispatch loop

The engine walks a task list and dispatches each task by type. It does **not** know what kind of workflow it's running — prompt composition and model selection are injected as callbacks so the same engine serves any workflow type.

**Callback signatures:**

```typescript
// How to turn an AgentTask's prompt file list into a final prompt string
type ComposePromptFn = (
  task: AgentTask,
  ctx: RunContext,
  extras?: Record<string, string>,
) => string;

// How to decide which Claude model to use for an AgentTask
type PickModelFn = (task: AgentTask, override?: string) => string;
```

**The dispatch loop:**

```typescript
function runTasks(
  tasks: readonly Task[],
  ctx: RunContext,
  builtins: Map<string, BuiltinFn>,
  composePrompt: ComposePromptFn,
  pickModel: PickModelFn,
): RunResult {
  const result: RunResult = { success: true, steps: [] };

  for (const task of tasks) {
    if (task instanceof BuiltIn) {
      // Look up name in registry, call with ctx + formatted kwargs
      const fn = builtins.get(task.name);
      if (!fn) { /* fail with "no builtin registered" */ }
      const formattedKwargs = formatKwargs(task.kwargs, ctx);
      fn(ctx, formattedKwargs);
    }

    else if (task instanceof AgentTask) {
      // Delegate prompt/model decisions to the injected callbacks
      const prompt = composePrompt(task, ctx);
      const model = pickModel(task);

      // Invoke claude via utils/claude-code.ts
      const invokeResult = await invokeClaude({
        prompt,
        model,
        tools: task.tools,
        cwd: ctx.cwd,
        dryRun: ctx.dryRun,
      });

      // Match on Result from the utils layer
      match(invokeResult)
        .with({ kind: "ok" }, ({ value }) => {
          ctx.state.put(new AgentResult({ /* ...from value */ }));
        })
        .with({ kind: "err" }, ({ error }) => {
          result.success = false;
          result.failureReason = error.reason;
        })
        .exhaustive();
    }

    else if (task instanceof ShellTask) {
      const cmd = ctx.formatString(task.cmd);
      const shellResult = await runShell(cmd, ctx.cwd, task.env);
      if (shellResult.exitCode !== 0) {
        if (task.onFailure === "ignore") { continue; }
        result.success = false;
        break;
      }
    }

    result.steps.push({ name: task.name, kind: taskKind(task), success: true });
  }

  return result;
}
```

**Why callbacks instead of hardcoded logic?** Different workflow types compose prompts differently. The engine doesn't need to know the differences — callers inject the right strategy:

**For this PRD — default (non-SDLC) implementations:**

```typescript
// Default prompt composer: load files, substitute basic placeholders.
// This is what the `run` CLI command uses for generic workflows.
function defaultComposePrompt(
  task: AgentTask,
  ctx: RunContext,
  extras?: Record<string, string>,
): string {
  // Read prompt files relative to the workflow's directory on disk
  // e.g., task.prompts = ["scan.md"], workflowDir = ".../security-review/"
  // → reads and concatenates ".../security-review/scan.md"
  const raw = loadPromptFiles(ctx.workflowDir, task.prompts);

  // Replace {{PLACEHOLDER}} tokens with context values
  return substitutePlaceholders(raw, {
    REPO_ROOT: ctx.repoRoot,
    CWD: ctx.cwd,
    ...extras,
  });
}

// Default model picker: explicit model on task, or fall back to sonnet.
function defaultPickModel(task: AgentTask, override?: string): string {
  if (override) return override;
  if (task.model) return task.model;
  return "sonnet";
}
```

**Future (SDLC layer, NOT in this PRD) — PRD-aware implementations:**

```typescript
// PRD-aware prompt composer — injected by the future SDLC adapter.
// Same signature, different behavior. Engine code does not change.
function prdComposePrompt(
  task: AgentTask,
  ctx: RunContext,
  extras?: Record<string, string>,
): string {
  const raw = loadPromptFiles(ctx.workflowDir, task.prompts);
  const prdRun = ctx.state.get(PrdWorkflowRun);  // SDLC payload

  const context: Record<string, string> = {
    PRD_ID: prdRun.prd.id,
    PRD_TITLE: prdRun.prd.title,
    PRD_BODY: prdRun.prd.body,
    ...extras,
  };

  // Inject review feedback if this is a rework cycle
  if (ctx.state.has(ReworkState)) {
    context.REWORK_FEEDBACK = renderReviewThreads(
      ctx.state.get(ReworkState).reviewThreads,
    );
  }

  return substitutePlaceholders(raw, context);
}

// PRD-aware model picker — derives model from PRD capability field.
function prdPickModel(task: AgentTask, override?: string): string {
  if (override) return override;
  if (task.model) return task.model;
  // "complex" → opus, "simple" → haiku, default → sonnet
  return capabilityToModel(ctx.state.get(PrdWorkflowRun).prd.capability);
}
```

**Wiring it together — the `run` CLI command:**

```typescript
// cli/run.ts — what happens when user runs `darkfactory run security-review`
const workflow = discoverWorkflows().get("security-review");

const ctx = new RunContext({ dryRun: options.dryRun });
ctx.state.put(new CodeEnv({ repoRoot: cwd, cwd }));
ctx.state.put(new WorktreeState({
  branch: `security-review/${today()}`,
  baseRef: "main",
}));
ctx.state.put(new PrRequest({
  title: `Security Review — ${today()}`,
  body: "Automated security scan findings",
}));

const result = runTasks(
  workflow.tasks,
  ctx,
  GIT_BUILTINS,          // only git builtins available
  defaultComposePrompt,   // simple file-loading strategy
  defaultPickModel,       // task.model ?? "sonnet"
);
// Future SDLC `run-prd-workflow` would pass prdComposePrompt,
// prdPickModel, and { ...GIT_BUILTINS, ...SDLC_BUILTINS } instead.
```

### 4. Builtin registry and git operations

#### `operations/registry.ts` — registration mechanism

```typescript
type BuiltinFn = (ctx: RunContext, kwargs: Record<string, unknown>) => void | Promise<void>;

const BUILTINS = new Map<string, BuiltinFn>();

function registerBuiltin(name: string, fn: BuiltinFn): void;
```

#### Git builtins

These are the generic git operations shared between both Python registries. They call through `utils/git.ts` and `utils/github.ts` (from [[PRD-636-typescript-utils-layer]]) and read/write engine-level payloads only — no SDLC dependencies:

| Builtin | Reads from state | Writes to state | Calls |
|---------|-----------------|----------------|-------|
| `ensure_worktree` | `WorktreeState` | `WorktreeState` (updates `worktreePath`), `CodeEnv` (updates `cwd`) | `utils/git.worktreeAdd` |
| `commit` | `CodeEnv` | — | `utils/git.add`, `utils/git.commit` |
| `push_branch` | `WorktreeState` | — | `utils/git.gitRun(["push", ...])` |
| `create_pr` | `PrRequest`, `WorktreeState` | `PrResult` | `utils/github.createPr` |

All builtins must honor `ctx.dryRun`. All subprocess calls go through the utils layer — builtins never call `subprocess.exec` directly.

### 5. Prompt composition

#### `workflow/prompts.ts`

- `loadPromptFiles(workflowDir, filenames)` — read and concatenate prompt files relative to workflow directory
- `substitutePlaceholders(raw, context)` — replace `{{PLACEHOLDER}}` tokens with values from a context object

The `{{PLACEHOLDER}}` syntax (double-brace) is for prompt templates. The `{placeholder}` syntax (single-brace) is for `RunContext.formatString()` in shell commands and builtin kwargs. Keep them distinct as Python does.

### 6. Workflow discovery

#### `workflow/loader.ts`

Scan directories for `workflow.ts` modules. Two layers:

1. **Built-in** — shipped with the package at `ts/src/workflow/definitions/`
2. **Project** — `<project>/.darkfactory/workflows/` (or configurable path)

Each direct subdirectory containing a `workflow.ts` that exports a `workflow` constant is loaded via dynamic `import()`. Loader sets `workflow.workflowDir` for prompt path resolution.

Name collisions across layers raise an error. Import failures log a warning and skip.

Defer the user layer (`~/.config/darkfactory/workflows/`) — two layers are sufficient to validate the pattern.

### 7. CLI

Two working commands:

#### `list-workflows`

Discover all workflows across both layers and display:
```
Available workflows:
  security-review    Scan codebase for security issues, propose fixes, open a PR
```

#### `run <workflow> [--dry-run]`

1. Discover workflows
2. Look up by name
3. Seed `PhaseState` with `CodeEnv` (from cwd) and `WorktreeState` (branch derived from workflow name + date)
4. Seed default `PrRequest` from workflow name/description
5. Call `runTasks()` with default prompt composer and model picker
6. Report result

CLI parser: use a lightweight library or Bun's `process.argv` parsing. Keep it minimal.

### 8. Security-review workflow

A built-in workflow at `ts/src/workflow/definitions/security-review/`:

```
security-review/
  workflow.ts       # Workflow definition
  scan.md           # Agent prompt
```

**Task list:**
1. `BuiltIn("ensure_worktree")` — create worktree on `security-review/<date>` branch
2. `AgentTask("scan")` — load `scan.md`, invoke Claude with Read/Glob/Grep/Write/Edit tools
3. `ShellTask("verify")` — run project tests (`just test` or equivalent), `onFailure: "ignore"` (findings may not have tests)
4. `BuiltIn("commit", { message: "chore: security review findings" })`
5. `BuiltIn("push_branch")`
6. `BuiltIn("create_pr")`

**Prompt (`scan.md`):**

Instruct the agent to:
- Scan all source files for OWASP Top 10 vulnerabilities
- Check for hardcoded secrets, injection vectors, auth gaps
- For each finding: identify location, describe the issue, apply a fix
- Emit `PRD_EXECUTE_OK` on completion

This workflow validates: discovery → loading → worktree creation → agent invocation → shell verification → git commit → push → PR creation. The full engine pipeline.

### 9. Tests

Colocated `.test.ts` for every module. Engine tests use `ts-pattern` matching on Results from the utils layer.

| Test file | Coverage |
|-----------|----------|
| `engine/phase-state.test.ts` | put/get/has, type inference, missing key throws, default |
| `engine/payloads.test.ts` | construction, readonly, PhaseState round-trip |
| `workflow/core.test.ts` | task construction, workflow creation |
| `engine/runner.test.ts` | dispatch with mock builtins, dry-run, failure handling, ts-pattern on AgentTask results |
| `operations/registry.test.ts` | register, lookup, missing builtin error |
| `workflow/prompts.test.ts` | file loading, placeholder substitution |
| `workflow/loader.test.ts` | discovery from fixture directories, name collision |
| `cli/index.test.ts` | list-workflows output, run with dry-run |

Git builtins are tested via dry-run mode — they log what they would do without executing. Integration testing of actual git operations deferred.

## Acceptance criteria

- [ ] `PhaseState` implements type-keyed registry with generic get
- [ ] All 5 engine-level payload classes with readonly fields
- [ ] `BuiltIn`, `AgentTask`, `ShellTask` task types
- [ ] `Workflow` and `RunContext` types
- [ ] `runTasks()` dispatch loop handles all three task types
- [ ] `runTasks` uses `ts-pattern` matching on `Result` values from utils layer
- [ ] Prompt file loading and `{{PLACEHOLDER}}` substitution
- [ ] Builtin registry with 4 git operations registered
- [ ] All git builtins honor dry-run and call through utils layer
- [ ] Workflow discovery from built-in and project layers
- [ ] `list-workflows` CLI shows discovered workflows
- [ ] `run security-review --dry-run` executes full pipeline in dry-run
- [ ] `bun test` and `bun run typecheck` pass
- [ ] No `any` types except PhaseState internals

## Deferred

- `InteractiveTask` — add when discussion workflows are ported
- `onFailure: "retry_agent"` — add when verification retry is needed
- `WorkflowTemplate` (open/middle/close enforcement) — add when multiple workflows share structure
- Event logging (`EventWriter`) — add when observability is needed
- User-layer workflow discovery (`~/.config/darkfactory/workflows/`)
- SDLC payloads, PRD model, predicate routing, status tracking — separate PRD
- Integration tests for actual git/gh operations
- Timeout configuration system

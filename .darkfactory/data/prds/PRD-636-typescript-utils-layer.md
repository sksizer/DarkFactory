---
id: PRD-636
title: TypeScript utils layer — subprocess, git, gh, claude, Result types
kind: task
status: done
priority: high
effort: m
capability: moderate
parent:
depends_on:
  - "[[PRD-635-typescript-scaffold-and-core-types]]"
blocks:
  - "[[PRD-637-typescript-workflow-engine]]"
impacts:
  - ts/src/utils/
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

# TypeScript utils layer — subprocess, git, gh, claude, Result types

## Summary

Port all Python utility modules to TypeScript as wrapped functions in `utils/`. Every function that can fail returns a `Result<T, E>` — no exceptions. Tests use `ts-pattern` for exhaustive matching on return values. This establishes the Rust-friendly foundation described in `ts/ARCHITECTURE.md`.

## Motivation

The Python codebase has ~30 utility functions that wrap subprocess calls to git, gh, and claude. Porting these first is trivial, moves a real chunk of code, and establishes the patterns every subsequent module depends on: `Result` types, `ts-pattern` matching, and the subprocess abstraction. The workflow engine ([[PRD-637-typescript-workflow-engine]]) builds directly on top of this layer.

## Requirements

### 1. `utils/result.ts` — Result types and helpers

The foundation type. All fallible functions return this.

```typescript
import { match, P } from "ts-pattern";

// Core discriminated union
interface Ok<T> {
  readonly kind: "ok";
  readonly value: T;
  readonly stdout: string;
}

interface Err<E> {
  readonly kind: "err";
  readonly error: E;
}

type Result<T, E> = Ok<T> | Err<E>;

// Constructor helpers
function ok<T>(value: T, stdout?: string): Ok<T>;
function err<E>(error: E): Err<E>;

// Type guards
function isOk<T, E>(result: Result<T, E>): result is Ok<T>;
function isErr<T, E>(result: Result<T, E>): result is Err<E>;
```

**Domain-specific error types:**

```typescript
// Git CLI errors
interface GitErr {
  readonly kind: "git-err";
  readonly returncode: number;
  readonly stdout: string;
  readonly stderr: string;
  readonly cmd: readonly string[];
}

// GitHub CLI errors
interface GhErr {
  readonly kind: "gh-err";
  readonly returncode: number;
  readonly stdout: string;
  readonly stderr: string;
  readonly cmd: readonly string[];
}

// Subprocess timeout
interface Timeout {
  readonly kind: "timeout";
  readonly cmd: readonly string[];
  readonly timeout: number;
}
```

**Convenience type aliases:**

```typescript
type GitResult<T> = Result<T, GitErr>;
type GhResult<T> = Result<T, GhErr>;
type CheckResult = Result<null, GitErr | Timeout>;
type GhCheckResult = Result<null, GhErr | Timeout>;
```

**ts-pattern usage example (included in test):**

```typescript
import { match } from "ts-pattern";

const result = await gitRun(["status"], { cwd: "/repo" });

const message = match(result)
  .with({ kind: "ok" }, (r) => `clean: ${r.stdout}`)
  .with({ kind: "err", error: { kind: "git-err" } }, (r) =>
    `git failed: ${r.error.stderr}`,
  )
  .with({ kind: "err", error: { kind: "timeout" } }, (r) =>
    `timed out after ${r.error.timeout}ms`,
  )
  .exhaustive();
```

### 2. `utils/subprocess.ts` — process execution abstraction

Single module for all subprocess calls. Uses Bun-optimized APIs when available, falls back to `node:child_process`.

```typescript
interface ExecOptions {
  readonly cwd?: string;
  readonly env?: Record<string, string>;
  readonly stdin?: string;
  readonly timeout?: number; // milliseconds
}

interface ExecResult {
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;
}

// Run command as argv array — preferred for git/gh calls
function exec(cmd: readonly string[], options?: ExecOptions): Promise<ExecResult>;

// Run shell command string — for user-defined shell tasks
function execShell(cmd: string, options?: ExecOptions): Promise<ExecResult>;
```

Runtime detection:

```typescript
const isBun = typeof globalThis.Bun !== "undefined";
// Bun path: Bun.spawn()
// Node path: child_process.execFile / child_process.exec
```

No caller outside this module may import `child_process` or reference `Bun.spawn`.

### 3. `utils/git.ts` — git CLI wrappers

All functions call `exec(["git", ...args])` via `utils/subprocess.ts` and return `Result` types. Port from Python's `utils/git/` package.

**Primitive:**

```typescript
// Gateway — all git operations go through this
function gitRun(
  args: readonly string[],
  options: { cwd: string; timeout?: number },
): Promise<CheckResult>;
```

**Operations:**

| Function | Signature | Returns |
|----------|-----------|---------|
| `branchExistsLocal` | `(repoRoot: string, branch: string)` | `Promise<GitResult<boolean>>` |
| `branchExistsRemote` | `(repoRoot: string, branch: string)` | `Promise<GitResult<boolean>>` |
| `add` | `(paths: string[], cwd: string)` | `Promise<CheckResult>` |
| `commit` | `(message: string, cwd: string)` | `Promise<CheckResult>` |
| `diffQuiet` | `(paths: string[], cwd: string)` | `Promise<CheckResult>` |
| `statusOtherDirty` | `(paths: string[], cwd: string)` | `Promise<GitResult<string[]>>` |
| `resolveCommitTimestamp` | `(commit: string, cwd: string)` | `Promise<GitResult<string>>` |
| `findLocalBranches` | `(pattern: string, repoRoot: string)` | `Promise<GitResult<string[]>>` |
| `findRemoteBranches` | `(pattern: string, repoRoot: string)` | `Promise<GitResult<string[]>>` |

**Worktree operations:**

| Function | Signature | Returns |
|----------|-----------|---------|
| `worktreeList` | `(repoRoot: string)` | `Promise<GitResult<WorktreeEntry[]>>` |
| `worktreeAdd` | `(path: string, branch: string, repoRoot: string)` | `Promise<CheckResult>` |
| `worktreeRemove` | `(path: string, repoRoot: string)` | `Promise<CheckResult>` |

Where `WorktreeEntry` is:

```typescript
interface WorktreeEntry {
  readonly path: string;
  readonly branch: string;
  readonly head: string;
}
```

**API improvement over Python:** The Python code has `branch_exists_local` returning `bool` (swallows errors) and `find_worktree_for_prd` returning `Path | None`. The TS versions return `Result` consistently — callers see the actual error when something goes wrong.

### 4. `utils/github.ts` — GitHub CLI wrappers

All functions call `exec(["gh", ...args])` and return `Result` types. Port from Python's `utils/github/` package.

**Primitives:**

```typescript
// Gateway — all gh operations go through this
function ghRun(
  args: readonly string[],
  options: { cwd: string; timeout?: number },
): Promise<GhCheckResult>;

// Run gh and parse stdout as JSON
function ghJson<T>(
  args: readonly string[],
  options: { cwd: string; timeout?: number },
): Promise<GhResult<T>>;
```

**PR operations:**

| Function | Signature | Returns |
|----------|-----------|---------|
| `getPrState` | `(branch: string, repoRoot: string)` | `Promise<GhResult<PrState>>` |
| `fetchAllPrStates` | `(repoRoot: string)` | `Promise<GhResult<Map<string, PrState>>>` |
| `createPr` | `(options: CreatePrOptions)` | `Promise<GhResult<string>>` (PR URL) |
| `listOpenPrs` | `(repoRoot: string, limit?: number)` | `Promise<GhResult<PrInfo[]>>` |
| `closePr` | `(prNumber: number, repoRoot: string, comment?: string)` | `Promise<GhCheckResult>` |
| `repoNwo` | `(cwd: string)` | `Promise<GhResult<{ owner: string; name: string }>>` |

Where:

```typescript
type PrState = "MERGED" | "OPEN" | "CLOSED" | "NONE";

interface PrInfo {
  readonly number: number;
  readonly headRefName: string;
}

interface CreatePrOptions {
  readonly base: string;
  readonly title: string;
  readonly body: string;
  readonly cwd: string;
}
```

**GraphQL and comment operations:**

| Function | Signature | Returns |
|----------|-----------|---------|
| `graphqlFetch` | `(query: string, variables: Record<string, string>, cwd: string)` | `Promise<GhResult<unknown>>` |
| `postReply` | `(endpoint: string, body: string, cwd: string)` | `Promise<GhCheckResult>` |
| `fetchPrComments` | `(prNumber: number, cwd: string, filters?: CommentFilters)` | `Promise<GhResult<ReviewThread[]>>` |
| `postCommentReplies` | `(prNumber: number, replies: CommentReply[], threads: ReviewThread[], commitSha: string, cwd: string)` | `Promise<GhResult<ReplyResult[]>>` |

Supporting types (`ReviewThread`, `ReviewComment`, `CommentFilters`, `CommentReply`) mirror the Python dataclasses with `readonly` fields.

**API improvement over Python:** `fetch_pr_comments` in Python raises exceptions on GraphQL errors. The TS version returns `GhResult<ReviewThread[]>` — the error path is typed and matchable.

### 5. `utils/claude-code.ts` — Claude Code invocation

Port from Python's `utils/claude_code/` package.

```typescript
type EffortLevel = "low" | "medium" | "high" | "max";

interface InvokeOptions {
  readonly prompt: string;
  readonly tools: readonly string[];
  readonly model: string;
  readonly cwd: string;
  readonly sentinelSuccess?: string;  // default: "PRD_EXECUTE_OK"
  readonly sentinelFailure?: string;  // default: "PRD_EXECUTE_FAILED"
  readonly timeout?: number;          // ms, default: 600_000
  readonly effortLevel?: EffortLevel;
  readonly dryRun?: boolean;
}

interface InvokeResult {
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;
  readonly success: boolean;
  readonly failureReason?: string;
  readonly toolCounts: ReadonlyMap<string, number>;
  readonly sentinel?: string;
}

interface InvokeErr {
  readonly kind: "invoke-err";
  readonly exitCode: number;
  readonly stderr: string;
  readonly reason: string;
}

// Headless invocation — runs claude --print, parses sentinels
function invokeClaude(options: InvokeOptions): Promise<Result<InvokeResult, InvokeErr>>;

// Interactive invocation — hands terminal to user
function spawnClaude(
  prompt: string,
  cwd: string,
  effortLevel?: EffortLevel,
): Promise<Result<number, InvokeErr>>;  // exit code

// Pure logic — lookup table
function capabilityToModel(capability: string): string;
```

Sentinel parsing is a pure function extracted for testability:

```typescript
function parseSentinels(
  stdout: string,
  success: string,
  failure: string,
): { success: boolean; sentinel?: string; failureReason?: string };
```

Both `invokeClaude` and `spawnClaude` call through `utils/subprocess.ts`.

### 6. `utils/shell.ts` — shell command execution

```typescript
// Run shell command, capture output
function runShell(
  cmd: string,
  cwd: string,
  env?: Record<string, string>,
): Promise<ExecResult>;

// Run command in foreground, stream to terminal
function runForeground(
  cmd: readonly string[],
  cwd?: string,
): Promise<Result<number, ExecErr>>;  // exit code
```

Both delegate to `utils/subprocess.ts`.

### 7. `utils/secrets.ts` — secrets scanning (pure logic)

```typescript
interface RedactionResult {
  readonly text: string;
  readonly redactionCount: number;
  readonly patternsMatched: readonly string[];
}

// Scan text for secret patterns
function scan(text: string): Array<{ pattern: string; match: string }>;

// Redact secrets in text
function redact(text: string): RedactionResult;
```

Port all 11 Python patterns (AWS keys, GitHub tokens, API keys, private keys, connection strings, bearer tokens). No subprocess calls — pure regex.

### 8. `utils/system.ts` — prerequisite checks

```typescript
interface PrerequisiteErr {
  readonly kind: "prerequisite-err";
  readonly missing: readonly string[];
  readonly message: string;
}

function checkPrerequisites(
  cwd: string,
  options?: { requireClaude?: boolean },
): Result<null, PrerequisiteErr>;
```

Checks `git`, `gh`, and optionally `claude` are on PATH. Returns `Result` instead of Python's `SystemExit`.

### 9. Tests — all use `ts-pattern`

Every test file demonstrates `ts-pattern` matching on `Result` values. This validates both the util under test and the ergonomics of the Result + ts-pattern combination.

| Test file | Coverage |
|-----------|----------|
| `utils/result.test.ts` | ok/err construction, type guards, ts-pattern exhaustive matching |
| `utils/subprocess.test.ts` | exec/execShell, timeout handling, runtime detection |
| `utils/git.test.ts` | gitRun, all operations via mock subprocess, error paths |
| `utils/github.test.ts` | ghRun, ghJson, PR operations via mock subprocess |
| `utils/claude-code.test.ts` | invokeClaude dry-run, sentinel parsing, capabilityToModel |
| `utils/shell.test.ts` | runShell, runForeground |
| `utils/secrets.test.ts` | all 11 patterns, redaction, clean input |
| `utils/system.test.ts` | missing prerequisite detection |

**Test pattern — ts-pattern on Results:**

```typescript
import { describe, it, expect } from "bun:test";
import { match } from "ts-pattern";
import { gitRun } from "./git.js";

describe("gitRun", () => {
  it("returns Ok on success", async () => {
    const result = await gitRun(["status"], { cwd: "/repo" });

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(r.stdout).toContain("On branch");
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });

  it("returns GitErr on bad repo", async () => {
    const result = await gitRun(["status"], { cwd: "/nonexistent" });

    match(result)
      .with({ kind: "err", error: { kind: "git-err" } }, (r) => {
        expect(r.error.returncode).not.toBe(0);
      })
      .with({ kind: "err", error: { kind: "timeout" } }, () => {
        throw new Error("unexpected timeout");
      })
      .with({ kind: "ok" }, () => {
        throw new Error("expected error");
      })
      .exhaustive();
  });
});
```

## Acceptance criteria

- [ ] `utils/result.ts` defines `Result<T,E>`, `Ok`, `Err`, domain error types, type aliases
- [ ] `utils/subprocess.ts` abstracts all process calls with Bun/Node runtime detection
- [ ] No direct imports of `child_process` or `Bun.spawn` outside `utils/subprocess.ts`
- [ ] `utils/git.ts` wraps all git operations, returning `GitResult`/`CheckResult`
- [ ] `utils/github.ts` wraps all gh operations, returning `GhResult`/`GhCheckResult`
- [ ] `utils/claude-code.ts` implements `invokeClaude`, `spawnClaude`, sentinel parsing
- [ ] `utils/shell.ts` wraps shell execution via subprocess abstraction
- [ ] `utils/secrets.ts` ports all 11 secret detection patterns
- [ ] `utils/system.ts` checks prerequisites, returns `Result` (no exceptions)
- [ ] Every test file uses `ts-pattern` `match().exhaustive()` on Result values
- [ ] No exceptions thrown from any util function (only at test assertions)
- [ ] `bun test` and `bun run typecheck` pass
- [ ] No `any` types

## Out of scope

- PhaseState, payloads, workflow types — see [[PRD-637-typescript-workflow-engine]]
- Workflow engine, discovery, CLI — see [[PRD-637-typescript-workflow-engine]]
- Event logging, TUI display

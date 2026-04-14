# TypeScript Architecture — Rust-Friendly Design Principles

This TypeScript codebase is a waypoint toward a Rust implementation. All patterns are chosen to translate naturally to Rust idioms. Code that feels idiomatic here should feel idiomatic there too.

## Core Principles

### Result types over exceptions

Functions that can fail return `Result<T, E>` — they never throw. `try/catch` is used only at system boundaries (CLI entry point, test harness). Internally, every error path is typed and visible in the function signature.

Use `ts-pattern` for exhaustive matching on Result variants (see PRD-636).

```typescript
// Good
function parseConfig(raw: string): Result<Config, ConfigError> { ... }

// Bad
function parseConfig(raw: string): Config { ... } // throws on failure
```

### Discriminated unions as algebraic types

Model state machines, command outputs, and error hierarchies as tagged unions with a `kind` discriminant. Match exhaustively with `ts-pattern`.

```typescript
type TaskState =
  | { kind: "pending" }
  | { kind: "running"; startedAt: Date }
  | { kind: "done"; result: TaskResult }
  | { kind: "failed"; error: TaskError };
```

### Immutable by default

All data types use `readonly` fields. No mutation after construction — new state means a new object. This maps directly to Rust's ownership model and `&T` vs `&mut T` distinction.

```typescript
interface Config {
  readonly projectRoot: string;
  readonly phases: readonly PhaseConfig[];
}
```

### Composition over inheritance

No class hierarchies. Use interfaces, type unions, and plain functions. Classes are acceptable as data containers (frozen structs), not for polymorphism. Prefer:

```typescript
// Good — plain function composition
function withRetry<T, E>(fn: () => Result<T, E>, retries: number): Result<T, E> { ... }

// Avoid — inheritance for behavior
class RetryableTask extends Task { ... }
```

### Explicit error propagation

Every error path is typed and visible in the return type. Use `Result` chaining rather than `try/catch`. Silent error swallowing is forbidden.

```typescript
// Good — error is explicit in the type
function readFile(path: string): Result<string, IoError> { ... }

// Bad — error is invisible
function readFile(path: string): string { ... } // throws on failure
```

### All subprocess calls behind `utils/subprocess.ts`

A single abstraction for process execution. Callers never import `child_process` or `Bun` APIs directly. This keeps platform-specific code isolated and swappable.

### `ts-pattern` for matching

Use `match()` for dispatching on discriminated unions, Result types, and task types. This ensures exhaustiveness at compile time — the compiler catches unhandled cases, just like Rust's `match` expressions.

```typescript
import { match } from "ts-pattern";

const output = match(state)
  .with({ kind: "pending" }, () => "waiting...")
  .with({ kind: "running" }, ({ startedAt }) => `running since ${startedAt}`)
  .with({ kind: "done" }, ({ result }) => formatResult(result))
  .with({ kind: "failed" }, ({ error }) => formatError(error))
  .exhaustive();
```

## Directory Layout

```
src/
  index.ts        — package entry point, re-exports public API
  engine/         — DAG execution engine
  workflow/       — workflow definition and orchestration
  graph/          — DAG construction and traversal
  model/          — core domain types (PhaseState, TaskResult, etc.)
  config/         — configuration parsing and validation
  cli/            — command-line interface
  utils/          — shared utilities (subprocess, Result helpers, etc.)
```

## Tooling

| Tool | Purpose |
|------|---------|
| Bun | Runtime, test runner, package manager, bundler |
| TypeScript 5.8+ | Type system with strict + erasable-syntax-only mode |
| Biome | Formatting and fast syntactic linting |
| typescript-eslint | Type-aware linting (rules requiring `tsc` type information) |

## What `erasableSyntaxOnly` means

The `erasableSyntaxOnly: true` tsconfig flag bans TypeScript syntax that requires code generation (not just type erasure):

- No `enum` — use `const` objects with `as const` instead
- No parameter properties (`constructor(private x: T)`) — use explicit field declarations
- No `namespace` — use ES modules

This ensures all TypeScript syntax can be stripped by tools that don't run `tsc` (Bun, Deno, `node --experimental-strip-types`), and maps cleanly to Rust where there is no equivalent to TS enums' runtime behavior.

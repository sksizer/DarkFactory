---
id: PRD-635
title: TypeScript scaffold with Bun tooling
kind: task
status: ready
priority: high
effort: s
capability: simple
parent:
depends_on:
  - "[[PRD-634-typescript-dual-source-tree]]"
blocks:
  - "[[PRD-636-typescript-utils-layer]]"
impacts:
  - ts/
  - justfile
  - .github/workflows/ci.yml
workflow: task
assignee:
reviewers: []
target_version:
created: 2026-04-13
updated: 2026-04-13
tags:
  - infrastructure
  - typescript
---

# TypeScript scaffold with Bun tooling

## Summary

Create the `ts/` source tree with production-grade tooling: Bun as the default runtime/builder/test runner, Biome for formatting and syntactic linting, typescript-eslint for type-aware linting, strict TypeScript configuration, and a directory skeleton mirroring the Python module structure. All source code remains Node-compatible.

## Motivation

Before porting any application code, the TypeScript project needs a solid foundation: tooling, configuration, directory structure, and a working build pipeline. Doing this as a standalone step ensures the scaffold is validated in isolation and subsequent PRDs can focus purely on application logic.

## Requirements

### Create `ts/` directory skeleton

```
ts/
  package.json          # Bun-first, Node-compatible
  tsconfig.json         # Strict, cutting-edge TS 5.8+
  biome.json            # Linting + formatting
  src/
    index.ts            # Package entry point
    engine/
      index.ts
    workflow/
      index.ts
    graph/
      index.ts
    model/
      index.ts
    config/
      index.ts
    cli/
      index.ts
    utils/
      index.ts
```

Each `index.ts` should be a valid empty module (`export {}` or similar) so the project compiles from day one.

### `package.json` — source of truth for all build operations

Bun as the default tooling. `just` recipes are convenience wrappers that delegate here.

```jsonc
{
  "name": "darkfactory",
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "test": "bun test",
    "typecheck": "tsc --noEmit",
    "lint": "biome check . && eslint .",
    "lint:biome": "biome check .",
    "lint:eslint": "eslint .",
    "format": "biome format --write .",
    "format:check": "biome format .",
    "build": "bun build src/index.ts --compile --outfile dist/darkfactory"
  }
}
```

Dependencies:
- Runtime: `js-yaml`, `proper-lockfile`, `ts-pattern`
- Dev: `typescript`, `@biomejs/biome`, `eslint`, `typescript-eslint`, `@types/js-yaml`, `@types/proper-lockfile`, `@types/bun`

No vitest, no prettier — Bun's test runner covers testing, Biome covers formatting.

### `tsconfig.json` — maximum strictness

```jsonc
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "verbatimModuleSyntax": true,
    "erasableSyntaxOnly": true,
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "target": "ES2022",
    "outDir": "dist",
    "rootDir": "src",
    "declaration": true,
    "sourceMap": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

Key strictness flags:
- `strict` — enables all strict type-checking options
- `noUncheckedIndexedAccess` — index signatures return `T | undefined`
- `exactOptionalPropertyTypes` — distinguishes `undefined` value from missing property
- `verbatimModuleSyntax` — enforces explicit `import type` for type-only imports
- `erasableSyntaxOnly` — bans `enum`, parameter properties, `namespace` — ensures all TS syntax can be stripped without code generation, enabling `node --experimental-strip-types` and native Bun/Deno execution

### `biome.json` — formatting and syntactic linting

Configure Biome with recommended rules. Enable import sorting. Biome handles formatting and fast syntactic checks.

### `eslint.config.ts` — type-aware linting

`typescript-eslint` flat config (ESLint 9+, TS config file). Biome handles formatting and basic linting; ESLint handles only the rules that require type information from `tsc`. No rule overlap between the two tools.

Key type-aware rules to enable:
- `@typescript-eslint/no-floating-promises` — catch unawaited promises (critical with async Result returns)
- `@typescript-eslint/no-misused-promises` — prevent passing promises where booleans expected
- `@typescript-eslint/await-thenable` — flag awaiting non-promise values
- `@typescript-eslint/require-await` — flag async functions that don't await
- `@typescript-eslint/no-unnecessary-type-assertion` — remove dead `as` casts
- `@typescript-eslint/strict-boolean-expressions` — prevent truthy checks on non-booleans (Rust-friendly: explicit comparisons)

Disable all formatting and syntactic rules — those are Biome's job. Use `typescript-eslint`'s `strictTypeChecked` preset as a starting point, then turn off anything Biome already covers.

### Justfile recipes — thin wrappers over `package.json`

```justfile
ts-test:
    cd ts && bun run test

ts-typecheck:
    cd ts && bun run typecheck

ts-lint:
    cd ts && bun run lint

ts-format:
    cd ts && bun run format

ts-build:
    cd ts && bun run build
```

### CI — `test-ts` job

Add a `test-ts` job to `.github/workflows/ci.yml`, parallel to the existing Python `test` job. Mirrors the same checks the Python CI runs (typecheck, lint, test):

```yaml
  test-ts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
      - run: cd ts && bun install
      - run: cd ts && bun run typecheck
      - run: cd ts && bun run lint
      - run: cd ts && bun test
```

### `ts/ARCHITECTURE.md` — Rust-friendly design principles

Establish the architectural direction for the TypeScript codebase. This project is a waypoint — the long-term target is Rust. All TypeScript code should use patterns that translate naturally to Rust:

- **Result types over exceptions** — functions that can fail return `Result<T, E>`, never throw. `try/catch` only at system boundaries (CLI entry point, test harness). Use `ts-pattern` for exhaustive matching on Result variants.
- **Discriminated unions as algebraic types** — model state machines, command outputs, and error hierarchies as tagged unions with a `kind` discriminant. Match exhaustively with `ts-pattern`.
- **Immutable by default** — all data types use `readonly` fields. No mutation after construction. New state = new object.
- **Composition over inheritance** — no class hierarchies. Use interfaces, type unions, and plain functions. Classes are acceptable as data containers (frozen structs), not for polymorphism.
- **Explicit error propagation** — no silent swallowing. Every error path is typed and visible in the return type. Use `Result` chaining, not `try/catch`.
- **All subprocess calls behind `utils/subprocess.ts`** — a single abstraction for process execution. Callers never import `child_process` or `Bun` directly. Implementation can use Bun-optimized APIs when available.
- **`ts-pattern` for matching** — use `match()` for dispatching on discriminated unions, Result types, and task types. Ensures exhaustiveness at compile time.

### Smoke test

A single `src/index.test.ts` that imports from the package entry point and asserts the import succeeds. This validates the entire toolchain: TypeScript compilation, Bun test runner, and module resolution.

## Acceptance criteria

- [ ] `ts/` scaffold exists with all config files and directory skeleton
- [ ] `bun install` in `ts/` succeeds
- [ ] `bun run typecheck` passes (all placeholder modules compile)
- [ ] `bun test` passes (smoke test green)
- [ ] `bun run lint` passes (both Biome and ESLint)
- [ ] `eslint.config.ts` enables type-aware rules only, no overlap with Biome
- [ ] `bun run build` produces a compiled binary at `ts/dist/darkfactory`
- [ ] `just ts-test`, `just ts-typecheck`, `just ts-lint`, `just ts-build` all work
- [ ] No `any` types anywhere
- [ ] `tsconfig.json` has `erasableSyntaxOnly: true` — no enums, no parameter properties, no namespaces
- [ ] Source code contains no Bun-specific APIs (standard TS only)
- [ ] `ts/ARCHITECTURE.md` documents Rust-friendly design principles
- [ ] `ts-pattern` listed as runtime dependency
- [ ] `test-ts` CI job added to `.github/workflows/ci.yml`
- [ ] CI job runs typecheck, lint, and test using Bun

## Out of scope

- Application types (PhaseState, payloads, Result) — see [[PRD-636-typescript-utils-layer]]
- CLI commands — see [[PRD-637-typescript-workflow-engine]]
- npm publishing

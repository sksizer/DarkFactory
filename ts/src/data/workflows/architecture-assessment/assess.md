# Deep Architecture Assessment

Perform a thorough, read-only architecture and API-usability assessment of this
codebase. Produce a single markdown report at the path provided below.

## Output

Write the full report to: `{{REPORT_PATH}}`

Use **only one** `Write` call (the final report). All other exploration must
use `Read`, `Glob`, and `Grep`. Do not modify, rename, or delete any source
files.

## What to assess

### 1. Module structure & boundaries
- Top-level layout: what each directory is responsible for
- Module-per-concern adherence: are concerns well-isolated, or do files mix
  responsibilities?
- Public vs. internal surface: what's exported, what should be internal-only

### 2. Dependency graph & coupling
- Import graph: hot spots (modules imported by many others)
- Cycles between modules or layers
- Cross-layer leaks (e.g., low-level utilities importing high-level orchestration)
- Hidden coupling via shared mutable state, globals, or singletons

### 3. Layering & abstractions
- Are layers (CLI / core / data / utils) clearly separated?
- Abstraction leaks: implementation details surfacing through public types
- Premature abstraction: indirection that adds no value
- Missing abstraction: repeated patterns that should be consolidated

### 4. API usability (internal & external)
For each significant public API surface (exported functions, classes, CLI
commands, workflow tasks):
- **Discoverability** — can a new contributor find the right entry point?
- **Naming** — do names match what the thing actually does?
- **Parameter ergonomics** — required vs. optional, positional vs. named,
  sensible defaults, easy-to-misuse signatures
- **Error surfaces** — are errors typed/discriminated, or stringly-typed?
  Are failure modes obvious from the signature?
- **Documentation** — is intent captured at the API boundary, or only inside?
- **Composability** — can pieces be combined cleanly, or is glue code required?

### 5. Type safety & contracts
- Use of `any`, `unknown`, type assertions, non-null assertions
- Validation at boundaries (CLI args, file I/O, network) vs. trust internally
- Discriminated unions vs. boolean flags
- Branded/nominal types where structural would be ambiguous

### 6. Code quality signals
- Dead code: exported symbols with no importers, unreachable branches
- Duplication: near-identical blocks across files
- Long files / long functions that should decompose
- Inconsistent patterns for the same problem

### 7. Tests
- Coverage gaps in load-bearing modules
- Test/source colocation consistency
- Brittle tests (over-mocked, snapshot-heavy, time-dependent)

### 8. Build & tooling health
- Lint/format/type-check setup; gaps or disabled rules
- Dependency hygiene: unused deps, version drift, supply-chain risk
- Scripts/justfile/CI consistency

## Method

1. Start with `Glob` on common roots to map the layout
2. Read `README.md`, `CLAUDE.md`, and any architecture docs first to anchor
   intent before judging implementation
3. Read package manifests (`package.json`, `pyproject.toml`, etc.) and entry
   points
4. Sample representative files from each layer; do not read every file
5. Use `Grep` to confirm patterns (e.g., import counts, `any` usage)
6. Form findings, then write the report

## Report format

```markdown
# Architecture Assessment — <date>

## Executive summary
<3–6 bullets: top findings, ranked by impact>

## Codebase shape
<directory tree sketch + one-line purpose per top-level dir>

## Findings

### <Category> — <short title>
- **Severity:** critical | high | medium | low
- **Location:** file paths / line refs
- **Observation:** what is true today
- **Why it matters:** consequence for contributors / users / runtime
- **Suggested direction:** what a fix would look like (no code changes here)

<repeat per finding>

## Strengths
<what the codebase does well — be specific, not generic>

## Open questions
<things you couldn't determine from reading alone>
```

When the report file has been written, emit `PRD_EXECUTE_OK` on its own line.
If you cannot complete the assessment, emit `PRD_EXECUTE_FAILED` with a brief
reason.

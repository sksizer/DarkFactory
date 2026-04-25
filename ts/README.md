# DarkFactory (TypeScript)

DAG orchestration engine and workflow harness for automating SDLC workflows. Combines git operations, shell commands, Claude Code agent invocations, interactive prompts, and automated quality gates into declarative, composable workflows.

## Quick Start

```bash
# Install dependencies
bun install

# Run the CLI
bun src/cli/bin.ts workflow list
bun src/cli/bin.ts workflow run <name> [--dry-run]

# Build standalone binary
bun run build
```

## Architecture

```
src/
├── cli/                  # CLI commands (commander-based)
│   └── subcommand/       # workflow list, workflow run
├── config/               # Configuration types (.darkfactory/config.toml)
├── core/workflow/        # Workflow definition and execution
│   ├── builder.ts        # Fluent WorkflowBuilder API
│   ├── loader.ts         # Dynamic workflow discovery
│   └── engine/           # DAG execution engine
│       ├── runner.ts     # Sequential task executor
│       ├── phase-state.ts# In-memory task output store
│       ├── payloads.ts   # Typed data classes (CodeEnv, WorktreeState, etc.)
│       └── tasks/        # Built-in task implementations
├── data/workflows/       # Built-in workflow definitions
│   ├── dev-session/      # Interactive dev with quality gates + PR creation
│   └── security-review/  # Agent-driven security scan workflow
└── utils/
    ├── result.ts         # Result<T, E> discriminated union
    ├── secrets.ts        # Secret/credential handling
    └── exec/             # Subprocess wrappers (git, gh, claude, shell)
```

### Key Concepts

**Workflows** are declarative sequences of tasks built with the fluent `WorkflowBuilder`:

```typescript
workflow("security-review")
  .category("review")
  .describe("Automated security scan")
  .seed(new CodeEnv({ repoRoot: ".", cwd: "." }))
  .named("worktree", createWorktree({ branch: "security-review/2026-04-15" }))
  .add(agentTask({ prompt: "scan.md", tools: ["Read", "Grep", "Glob"] }))
  .add(commitTask({ message: "security: automated scan findings" }))
  .add(createPr({ title: "Security Review" }))
  .build()
```

**Tasks** declare typed inputs and outputs. The engine resolves dependencies via `PhaseState`, a keyed store that flows data between tasks:

- `agentTask` — invoke Claude Code headlessly with prompt, tools, model
- `shellTask` — run shell commands
- `interactiveClaudeTask` — spawn interactive Claude session
- `confirmTask` / `diffCheckTask` — user interaction prompts
- `createWorktree`, `commitTask`, `pushBranch`, `createPr` — git/GitHub operations

**Workflow discovery** scans two layers:
1. Built-in workflows in `src/data/workflows/`
2. Project workflows in `.darkfactory/workflows/`

### Design Principles

- **Result types over exceptions** — `Result<T, E>` discriminated unions with exhaustive `ts-pattern` matching
- **Parse at the boundary, trust internally** — validate at ingestion, trust types deeper in
- **Single subprocess gateway** — all process execution through `utils/exec/subprocess.ts`
- **Immutability** — `readonly` fields throughout, state changes create new objects
- **Module-per-concern** — focused files with colocated tests

## Development

```bash
bun test              # Run tests
bun run typecheck     # TypeScript strict mode
bun run lint          # Biome + ESLint
bun run format        # Biome auto-format
```

### TypeScript Configuration

- Strict mode with `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`
- `erasableSyntaxOnly` — no enums, parameter properties, or namespaces
- Target: ES2022, module: NodeNext

### Runtime

Primary runtime is **Bun**, with Node.js fallback supported in the subprocess layer.

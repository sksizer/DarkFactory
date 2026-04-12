---
id: PRD-616
title: Interactive PRD discussion via phased Claude Code chain
kind: done
status: review
priority: medium
effort: m
capability: complex
parent:
depends_on: []
blocks: []
impacts:
  - src/darkfactory/cli/discuss.py
  - src/darkfactory/cli/new.py
  - src/darkfactory/cli/_parser.py
  - src/darkfactory/cli/main.py
  - src/darkfactory/commands/__init__.py
  - src/darkfactory/commands/discuss/__init__.py
  - src/darkfactory/commands/discuss/operation.py
  - src/darkfactory/commands/discuss/prompts/discuss.md
  - src/darkfactory/commands/discuss/prompts/critique.md
  - src/darkfactory/builtins/discuss_prd.py
  - src/darkfactory/builtins/gather_prd_context.py
  - src/darkfactory/builtins/commit_prd_changes.py
  - src/darkfactory/builtins/system_builtins.py
  - src/darkfactory/system_runner.py
  - tests/test_cli_discuss.py
  - tests/test_commands_discuss.py
workflow:
target_version:
created: 2026-04-11
updated: 2026-04-11
tags:
  - harness
  - cli
  - agent
---

# Interactive PRD discussion via phased Claude Code chain

## Summary

Add a `prd discuss <prd-id>` command and a `--discuss` flag to `prd new` that drop the user into an interactive Claude Code session with the target PRD's context preloaded. The session is structured as a chain of phases (gather context → discuss → critique → commit) defined as a `SystemOperation`, with each interactive phase ending when the user manually exits Claude Code; control then returns to the harness, which announces the next phase and launches it. The chain ends with a commit prompt that offers to capture any PRD edits the discussion produced — the harness uses git as the canonical PRD store, so a finished discussion should end with a clean working tree (or an explicit "leave it dirty" choice). This is the first member of a new `commands/` subpackage for "rich" CLI commands that are workflow-shaped but don't fit the PRD-implementation lifecycle.

## Problem

PRD authoring today is a solitary editor experience. After `prd new`, the author opens the markdown file and writes against a template, with no structured way to bring an LLM into the loop for development or critique. Practitioners who do want LLM help today either:

- Copy-paste the PRD into a separate Claude conversation (lossy, no codebase context),
- Run `prd run <id>` against a real workflow (overkill — the PRD isn't ready to implement yet), or
- Skip LLM input until review time (too late — the design is set).
- Reference PRD file inline in a conversation

The harness already knows where the PRD lives, what its frontmatter says, what its parents and dependencies are, and where related code might live. None of that context survives into a separate Claude Code session that the user starts manually.

We want a first-class verb for "talk to Claude about this PRD" that pre-loads the context and runs through opinionated phases (collaborator, then critic) so the user gets both kinds of feedback without context-switching.

A second pain point: when an LLM-assisted editor session (or any tool-assisted edit) modifies a PRD, those edits sit uncommitted in the working tree until the user remembers to `git add .darkfactory/prds/...md && git commit`. The harness uses git as its PRD database — uncommitted PRD edits are essentially dropped writes from the harness's point of view. The discuss chain should make committing the natural ending of the session, not a separate manual chore.

## Goals

1. `prd discuss <prd-id>` opens an interactive Claude Code session preloaded with the PRD's context, walks through a fixed phase chain, and exits cleanly when the user finishes the last phase.
2. `prd new --discuss <args>` chains immediately into a discuss session against the just-created PRD (composes with the existing `--open` flag — they're complementary, not exclusive).
3. The discussion chain is implemented as a `SystemOperation` so future commands can reuse the same primitives (interactive task, context gathering, end-of-chain commit) and so additional phases can be added without rewriting the dispatcher.
4. A new `commands/` subpackage establishes the organizational pattern for future "rich" CLI commands (multi-file, prompt-driven, chain-shaped).
5. The chain ends with an explicit commit prompt so PRD edits made during the discussion become durable git history with one keystroke. The PRD store is git; a discussion that ends with uncommitted changes is half-finished.

## Non-Goals

- **No agent autonomy.** The discussion is interactive; Claude Code is not running unattended against the PRD. The PRD file may be edited during the discussion (Claude has whatever tools the user's local config grants in interactive mode), and the chain offers to commit those edits at the end with explicit user confirmation — but the harness never commits without asking, never pushes, and never creates a PR.
- **No transcript capture for v1.** Discussion sessions are ephemeral. Adding transcript capture is a follow-up if user demand appears.
- **No configurable phase chains for v1.** The chain is hard-coded as `gather → discuss → critique → commit`. User-defined chains are a follow-up.
- **No batch / non-interactive mode.** `prd discuss` always blocks on the user. There is no `--print` equivalent.

## Requirements

### Functional

1. **`prd discuss <prd-id>` command.** New subcommand registered in `cli/_parser.py`. Handler in `cli/discuss.py` resolves the PRD by id (using the new `_resolve_prd_or_exit` helper from PRD-615 if it lands first; otherwise inline), loads the discuss `SystemOperation`, builds a `SystemContext` with `target_prd=prd_id`, and dispatches to `system_runner.run_system_operation`.
2. **`prd new --discuss` flag.** New flag on `cli/new.py:cmd_new`. After successful PRD creation, if `--discuss` is set, the command calls into the same code path as `prd discuss <new-id>` (via a shared helper, not by re-invoking the parser). Compatible with `--open`: if both are set, `--open` runs first, then `--discuss` (the editor exits, then the session launches).
3. **`commands/discuss/` module.** New subpackage at `src/darkfactory/commands/discuss/` containing:
   - `__init__.py` — exports `discuss_operation: SystemOperation`
   - `operation.py` — defines the `SystemOperation` and its task list
   - `prompts/discuss.md` — initial-message prompt for the collaborator phase
   - `prompts/critique.md` — initial-message prompt for the critic phase
   - The package exposes `discuss_operation` so `cli/discuss.py` can import it directly without going through the `.darkfactory/operations/` discovery mechanism (this is a built-in command, not a user-defined operation).
4. **`gather_prd_context` builtin.** New system builtin at `src/darkfactory/builtins/gather_prd_context.py`. Reads `ctx.target_prd`'s file from disk, walks parent (`prd.parent`) and direct dependencies (`prd.depends_on`) one level deep, and composes a markdown context block of the form:
   ```
   ## Target PRD
   - id: PRD-616
   - title: ...
   - status: draft
   - kind: feature

   ### Body
   <full PRD body>

   ## Parent
   - PRD-XXX: ... (status: ...) — <one-line summary>

   ## Dependencies
   - PRD-YYY: ... (status: ...) — <one-line summary>
   - PRD-ZZZ: ... (status: ...) — <one-line summary>
   ```
   Stores the block at `ctx._shared_state["prd_context"]`. Pure data — no agent invocation, no subprocess.
5. **`discuss_prd` builtin.** New system builtin at `src/darkfactory/builtins/discuss_prd.py`. Accepts kwargs `phase: str`, `prompt_file: str` (relative to the operation_dir), and `instructions: str | None` (the "exit when done" reminder). Loads the prompt file, substitutes `{PRD_CONTEXT}` with `ctx._shared_state["prd_context"]` and `{PHASE}` with `phase`, prints a phase banner to the terminal (e.g., `── Discuss phase ── (exit Claude with /exit or Ctrl-D when done)`), then spawns `subprocess.run(["claude", composed_prompt], cwd=ctx.cwd, check=False)` and blocks until the subprocess exits. On non-zero exit, log a warning but proceed to the next task (a user pressing Ctrl-C inside Claude Code is not a chain failure).
6. **Discuss `SystemOperation` task list:**
   ```python
   discuss_operation = SystemOperation(
       name="discuss",
       description="Interactive PRD discussion chain — gather, discuss, critique, commit.",
       requires_clean_main=False,
       creates_pr=False,
       accepts_target=True,
       tasks=[
           BuiltIn("gather_prd_context"),
           BuiltIn("discuss_prd", kwargs={
               "phase": "discuss",
               "prompt_file": "prompts/discuss.md",
           }),
           BuiltIn("discuss_prd", kwargs={
               "phase": "critique",
               "prompt_file": "prompts/critique.md",
           }),
           BuiltIn("commit_prd_changes", kwargs={
               "message": "chore(prd): {target_prd} discuss session refinements",
           }),
       ],
   )
   ```
7. **Phase prompt files.** Both `prompts/discuss.md` and `prompts/critique.md` start with a `{PRD_CONTEXT}` placeholder (substituted by `discuss_prd` before launch) and a phase-specific framing:
   - `discuss.md` — collaborator framing: "Help me develop this PRD. Walk through each section, ask clarifying questions, suggest sections I'm missing, surface decisions that need to be made. When you feel the PRD is in good shape, end with a summary of what changed and exit the session."
   - `critique.md` — critic framing: "Critique this PRD. Find ambiguity, hidden assumptions, scope creep, missing acceptance criteria, and risks the author hasn't named. Be direct. When you've covered the major concerns, summarize them and exit the session."
   Each prompt explicitly tells Claude to exit the session when it has finished its phase, so the user is not the only thing keeping the chain moving (though manual exit is always supported).
8. **Phase banner between phases.** Between `gather_prd_context` and `discuss_prd("discuss")`, between the discuss and critique invocations, and between critique and `commit_prd_changes`, print a clear banner to stderr indicating which phase is starting. Format:
   ```
   ─────────────────────────────────────
    Phase: critique
    Press Ctrl-C now to abort the chain.
   ─────────────────────────────────────
   ```
   The runner pauses for ~1 second after printing the banner so the user has time to abort before the subprocess takes over the terminal.
9. **`commit_prd_changes` builtin.** New system builtin at `src/darkfactory/builtins/commit_prd_changes.py`. Signature: `commit_prd_changes(ctx: SystemContext, message: str | None = None, paths: list[str] | None = None) -> None`.
   - Resolves `paths` default to `[<file for ctx.target_prd>]` (uses the same file resolution that `gather_prd_context` does — find the PRD file under the configured PRD directory by id).
   - Resolves `message` default to `f"chore(prd): {ctx.target_prd} discuss session refinements"`. If the supplied `message` template contains `{target_prd}`, substitute via `ctx.format_string`.
   - Runs `git diff --quiet -- <paths>` in `ctx.cwd`. If no changes, prints `No PRD changes to commit.` and returns cleanly without prompting.
   - If there are changes:
     1. Prints a phase banner: `── Commit phase ──`.
     2. Prints a colored `git diff -- <paths>` to the terminal (let git color it; do not capture stdout).
     3. If other files in the working tree are dirty (anything outside `<paths>`), prints a one-line note: `Note: N other file(s) have unstaged changes that will NOT be included.` Lists them inline if N ≤ 5.
     4. Prints the suggested commit message.
     5. Prompts: `Commit these changes? [y/N/e(dit message)]`. Default is **N** (skip) — the conservative choice; the user can always commit manually later.
   - On `y`: `git add -- <paths>` then `git commit -m <message>` via the shared subprocess wrapper introduced by PRD-615 (or a direct `subprocess.run` if PRD-615 hasn't landed yet).
   - On `e`: prompts for the new message via stdin (`Enter new commit message: `), then commits with that message.
   - On `n` or empty input: logs `Skipped commit. Changes left in working tree.` and returns cleanly.
   - Never pushes. Never creates a PR. Never mutates PRD frontmatter directly. Never modifies files other than via the git commands above.

### Non-Functional

1. **No new third-party dependencies.** `subprocess.run` is already used throughout the codebase for the same shape (see `cli/new.py:115`).
2. **mypy strict** across all new code, matching the rest of the project.
3. **Peer test files** for all three new builtins (`discuss_prd_test.py`, `gather_prd_context_test.py`, `commit_prd_changes_test.py`) plus integration tests in `tests/test_cli_discuss.py` and `tests/test_commands_discuss.py`.
4. **Test isolation:** the interactive subprocess and the commit subprocess MUST both be mockable. `discuss_prd` and `commit_prd_changes` should each call a small wrapper function (e.g., `_spawn_discuss_prd`, `_run_git_commit`) that tests can monkeypatch. Tests verify prompt composition, phase banners, dispatch order, and the commit prompt branches without spawning real `claude` or modifying real git history.
5. **Hard failure if `claude` is not on PATH.** Surface a clear error at the start of `prd discuss` (probe `shutil.which("claude")` once before the chain starts). Don't let the user discover the missing binary halfway through phase 2.
6. **Hard failure if `git` is not on PATH or `ctx.cwd` is not a git working tree.** Probe at the start of `prd discuss` alongside the `claude` check, so the commit phase is guaranteed to be reachable if the user reaches it. A discuss session that ends "you can't commit because there's no git repo here" is the worst possible UX.

## Technical Approach

### Architectural decision: SystemOperation, not Workflow

Workflows are PRD-implementation-shaped: they assume the PRD is `ready`, create a worktree, mutate status, and end with a PR. The discuss chain does none of those things — it's read-only against the PRD lifecycle, runs against any PRD regardless of status, and creates no git artifacts other than the optional final commit. `SystemOperation` already supports `requires_clean_main=False`, `creates_pr=False`, and `accepts_target=True`, which is exactly the shape we need.

We will not define discuss as a user-discoverable operation in `.darkfactory/operations/discuss/` because it's a built-in command bound to the CLI verb `prd discuss`. Loading it via the operations-discovery mechanism would mean users could shadow or remove it, and would require the user to have an `.darkfactory/operations/` directory just to use the command. Instead, `commands/discuss/__init__.py` exports `discuss_operation` as a Python value that `cli/discuss.py` imports directly.

### Architectural decision: BuiltIn, not new task type

The cleanest extension to the Task hierarchy would be new `InteractiveTask` and `GitCommitTask` classes that the system runner dispatches differently from `AgentTask`. We are deliberately NOT doing that for v1 because:

1. Adding new task types touches every isinstance check in `runner.py`, `system_runner.py`, `loader.py` validation, and the docs.
2. The interactive launch and the commit prompt are conceptually "primitive operations against the system" — exactly what `BuiltIn` is for. The existing `commit`, `push_branch`, `create_pr`, and `cleanup_worktree` builtins all wrap subprocess invocation; `discuss_prd` and `commit_prd_changes` are the same shape.
3. If a second or third use case for either primitive appears, we can promote it to a task type then. Until then, the BuiltIn approach has zero blast radius outside `system_builtins.py` and the new files.

The consequence is that `BuiltIn("discuss_prd", kwargs={...})` and `BuiltIn("commit_prd_changes", kwargs={...})` are the call site shape, not `InteractiveTask("discuss", prompt="...")` or `GitCommitTask(message="...")`. Slightly less typed, but consistent with how other side-effecting tasks are written.

### Architectural decision: `commands/` subpackage

The user-facing CLI verbs live in `cli/*.py` as small modules that parse args and dispatch. Workflow definitions live in `workflows/<name>/`. There is currently no home for "the implementation of a CLI verb that is large enough to need multiple files and prompt assets". This PRD introduces `src/darkfactory/commands/` as that home. For v1, only `commands/discuss/` exists; the directory pattern is established for future commands of the same shape.

The split between `cli/discuss.py` and `commands/discuss/` is:

- `cli/discuss.py` — argparse wiring, `cmd_discuss` entry point, PRD lookup, error handling. ~30 lines.
- `commands/discuss/` — the operation definition, prompt files, and any helpers specific to the discuss feature. Self-contained.

`cli/discuss.py` imports `discuss_operation` from `commands/discuss` and dispatches via `system_runner.run_system_operation`.

### Phase context flow

```
prd discuss PRD-616
  └─ cli/discuss.py:cmd_discuss
       └─ probe shutil.which("claude") and git availability — fail fast if missing
       └─ load_all() → resolve PRD-616
       └─ build SystemContext(target_prd="PRD-616", ...)
       └─ run_system_operation(discuss_operation, ctx)
            ├─ BuiltIn("gather_prd_context")
            │     └─ reads PRD-616 file + parent + deps
            │     └─ writes context block to ctx._shared_state["prd_context"]
            ├─ phase banner: "Phase: discuss"
            ├─ BuiltIn("discuss_prd", phase="discuss", prompt_file="prompts/discuss.md")
            │     └─ load prompt, substitute {PRD_CONTEXT}, {PHASE}
            │     └─ subprocess.run(["claude", composed_prompt], cwd=...)
            │     └─ blocks until user exits Claude Code
            ├─ phase banner: "Phase: critique"
            ├─ BuiltIn("discuss_prd", phase="critique", prompt_file="prompts/critique.md")
            │     └─ same shape, different prompt file
            ├─ phase banner: "Phase: commit"
            └─ BuiltIn("commit_prd_changes", message="chore(prd): {target_prd} discuss session refinements")
                  └─ git diff --quiet -- <prd file>
                  └─ if clean: log "No PRD changes to commit." and return
                  └─ if dirty: show diff, show message, prompt [y/N/e]
                       ├─ y → git add + git commit
                       ├─ e → prompt for new message → git add + git commit
                       └─ n or default → log "Skipped commit." and return
```

### Commit step at the end of the chain

The discuss chain ends with a commit phase because the PRD store is git: a discussion that ends with PRD edits sitting uncommitted in the working tree is a half-finished operation. Forcing the user to remember `git add .darkfactory/prds/PRD-XXX-...md && git commit` after every discuss session is the kind of friction that erodes the value of the harness — better to make the commit prompt the natural last step.

The builtin commits **only** the target PRD file by default. If the user (or Claude during the session) modified other files, those are surfaced as a note but left in the working tree. The reasoning: surprise commits are worse than incomplete commits — a user can always run `git add -A && git commit` themselves if they want everything in, but they can't easily *undo* a commit that swept up an unrelated file.

The default is **N (skip)**, not Y (commit). A user who wants to commit must explicitly type `y`. This trades one extra keystroke per session for the property that hitting Enter on the prompt is always safe — no accidental commits if the user mashes Enter to dismiss the prompt without reading it.

The builtin does not push and does not create a PR. Pushing PRD discussion commits is a separate operation with different semantics (collaborator review, branch hygiene) and should not be coupled to the discuss chain. A user who wants to push can do so manually (`git push`) after the chain exits.

The "no changes" case is silent-ish: a one-line `No PRD changes to commit.` and a clean exit. No prompt, no banner shenanigans. A discussion that produced no edits is a perfectly valid discussion and should not be punished with extra UI noise.

### `prd new --discuss` integration

Inside `cli/new.py:cmd_new`, after the existing `--open` block:

```python
if args.discuss:
    from darkfactory.cli.discuss import launch_discuss_for_prd
    launch_discuss_for_prd(new_id, args)
```

`launch_discuss_for_prd` is a small helper exported from `cli/discuss.py` that builds the same `SystemContext` as `cmd_discuss` does and calls `run_system_operation`. This avoids re-parsing args and keeps the new command's responsibilities clear.

### Test strategy

- **Builtin peer tests:** unit-test `gather_prd_context` against a tmp PRD dir with parent + deps. Unit-test `discuss_prd` with a monkeypatched `_spawn_discuss_prd` wrapper that records the composed prompt and cwd, verifies the banner, and verifies that a non-zero exit is logged but doesn't raise. Unit-test `commit_prd_changes` against a real-but-tmp git repo (init in tmp, write a PRD, modify it, run the builtin with monkeypatched `input()` for each branch: y / n / default / e + new message). Verify the no-changes early-return path. Verify that unrelated dirty files are surfaced as a note and NOT included in the commit.
- **CLI integration test:** invoke `prd discuss PRD-070` against a fake project and verify the chain dispatches in the right order. The interactive subprocess and the commit subprocess are both mocked.
- **`prd new --discuss` integration test:** invoke `prd new --discuss --title "..."` and verify the PRD is created AND the discuss chain is invoked against the new PRD's id.
- **Missing-binary test:** verify that running `prd discuss <id>` when `shutil.which("claude")` returns None exits with a clear error before any phase runs. Same for the `git` probe.

## Acceptance Criteria

- [ ] AC-1: `prd discuss <prd-id>` is registered in `cli/_parser.py`. Running it on a known PRD launches the chain; running it on an unknown PRD exits cleanly with the standard "unknown PRD id" error.
- [ ] AC-2: `prd new --discuss --title "Some title"` creates the PRD and immediately launches a discuss chain against the new PRD's id. The flag composes correctly with `--open` (editor opens first, then discuss starts after editor exits).
- [ ] AC-3: `src/darkfactory/commands/discuss/` exists with `__init__.py`, `operation.py`, and `prompts/discuss.md` and `prompts/critique.md`. `commands/discuss/__init__.py` exports `discuss_operation: SystemOperation`.
- [ ] AC-4: `gather_prd_context` is registered in `SYSTEM_BUILTINS` and produces the expected markdown context block when run against a fixture PRD with a parent and two dependencies.
- [ ] AC-5: `discuss_prd` is registered in `SYSTEM_BUILTINS`, composes the prompt by substituting `{PRD_CONTEXT}` and `{PHASE}`, prints the phase banner, and spawns the subprocess via a monkeypatchable wrapper. Tests verify all three behaviors.
- [ ] AC-6: The discuss chain runs the four tasks in order: `gather_prd_context`, `discuss_prd(phase="discuss")`, `discuss_prd(phase="critique")`, `commit_prd_changes`. Verified by an integration test that mocks the interactive launches and the commit subprocess and asserts the call order.
- [ ] AC-7: Running `prd discuss <id>` when `claude` is not on PATH exits with a clear error before the gather phase runs. Same for missing `git` or non-git `cwd`.
- [ ] AC-8: A non-zero exit from the interactive `claude` subprocess (e.g., the user Ctrl-C's during the discuss phase) logs a warning and proceeds to the critique phase rather than aborting the chain. Verified by a test.
- [ ] AC-9: All new modules pass `just lint && just typecheck && just test`. mypy strict has no escapes (`# type: ignore` only with comment justification).
- [ ] AC-10: Peer test files exist for `discuss_prd`, `gather_prd_context`, and `commit_prd_changes` in `src/darkfactory/builtins/`. Integration tests exist in `tests/test_cli_discuss.py` (CLI dispatch) and `tests/test_commands_discuss.py` (operation shape and chain order).
- [ ] AC-11: `prd discuss --help` and `prd new --help` describe the new command and flag clearly, including the chain's phases and the manual-exit interaction model.
- [ ] AC-12: `commit_prd_changes` is registered in `SYSTEM_BUILTINS`. Running it when the target PRD file has no working-tree changes prints `No PRD changes to commit.` and returns without prompting.
- [ ] AC-13: Running `commit_prd_changes` when the target PRD file IS dirty prints the diff, prints the suggested commit message, and prompts `[y/N/e]`. Default (Enter) is skip. Pressing `y` results in a single commit containing only the target PRD file. Pressing `e` prompts for a new message and commits with that message. Pressing `n` (or default) leaves the working tree dirty and the chain exits cleanly.
- [ ] AC-14: When the target PRD file is dirty AND other files in the working tree are also dirty, the prompt includes a note about the other files, and the resulting commit (if the user accepts) includes ONLY the target PRD file (the unrelated dirty files remain unstaged after the commit).
- [ ] AC-15: The `commit_prd_changes` step never pushes, never creates a PR, never mutates PRD frontmatter directly, and never bypasses the user prompt. Verified by reading the test suite — there is no code path through the builtin that ends with a PR or a push.

## Open Questions

- **OPEN — phase abort:** Should the user be able to skip the critique phase from inside the discuss session (e.g., by emitting a special sentinel from Claude, or by hitting Ctrl-C during the inter-phase pause)? Recommendation for v1: just the inter-phase Ctrl-C window (already covered by AC-8 spirit). Sentinel-based skip is a nice-to-have but adds parsing complexity that the chain otherwise avoids.
- **OPEN — chain configuration:** v1 hard-codes `gather → discuss → critique → commit`. Should the chain be loadable from the PRD's frontmatter (e.g., `discuss_chain: ["discuss", "critique", "summarize"]`) or from `.darkfactory/config.toml`? Defer to v2 once we know what other phases users want.
- **OPEN — context depth:** `gather_prd_context` walks parent + direct dependencies one level. Should it also include children (dependents) or transitive ancestors? Recommendation: start narrow (parent + direct deps), widen if user feedback says context is missing.
- **OPEN — transcript capture:** Should discuss sessions write a transcript to `.darkfactory/discussions/<prd-id>-<timestamp>.md`? Useful for review, but Claude Code's interactive mode doesn't trivially expose stdout to a parent process. Defer.
- **OPEN — prompt-file location vs operations directory:** `commands/discuss/prompts/` mirrors the `workflows/<name>/prompts/` shape. If we later allow users to override built-in command prompts (e.g., a project ships its own `discuss.md`), where would the override live? Probably `.darkfactory/commands/discuss/prompts/discuss.md` with cascade-resolver semantics. Out of scope for v1, but worth noting before locking in the path.
- **OPEN — naming:** Is `commands/` the right name for the new subpackage, or would `verbs/` / `flows/` / `chains/` be clearer? `commands/` is generic enough that it could absorb future shapes, but vague enough to invite confusion with `cli/`. Revisit after the second `commands/` member appears.
- **OPEN — commit message format:** Is `chore(prd): {target_prd} discuss session refinements` the right default? The repo already uses Conventional Commits style (`chore(prd):`, `docs(prd):` per recent log), but the verb choice ("refinements" vs "discussed" vs "refined") is taste. Ship the default above, accept feedback.
- **OPEN — commit scope (multi-file edits):** v1 commits only the target PRD file. If the discussion produced edits to related PRDs or other files, those are left in the working tree. Should the prompt offer a broader scope (e.g., `[y/N/a(ll)/e]` where `a` includes everything dirty)? Defer until we see whether multi-file discussion edits are common.
- **OPEN — pre-commit hook interaction:** The repo runs pre-commit hooks on `git commit`. If a hook fails (e.g., modified PRD frontmatter triggers `prd validate` and the validator rejects it), what should the chain do? Recommendation: surface the hook output, leave the changes uncommitted, exit non-zero from the chain. Don't try to auto-fix.
- **OPEN — generalization of `commit_prd_changes`:** Future commands (`prd refine`, `prd review`, etc.) will likely want the same end-of-chain commit prompt. Should the builtin be renamed `commit_with_confirmation` to signal reusability, or kept narrow as `commit_prd_changes` until a second use case appears? Recommendation: keep narrow for v1; rename when the second user lands.

## References

- Architectural fit: `src/darkfactory/system.py` (SystemOperation), `src/darkfactory/system_runner.py` (chain dispatcher), `src/darkfactory/cli/new.py:115` (existing pattern for handing the terminal to a subprocess and waiting).
- PRD-615 introduces `_resolve_prd_or_exit` in `cli/_shared.py`, which `cli/discuss.py` should use once it lands (otherwise inline the same check). PRD-615 also introduces the `git_ops.py` wrapper that `commit_prd_changes` should use for its `git diff` / `git add` / `git commit` calls.
- Existing commit builtin shape: `src/darkfactory/builtins/commit.py` (workflow-scoped). `commit_prd_changes` is a sibling system-scoped variant tailored for discussion chains — narrower paths, interactive confirmation, no PRD frontmatter mutation, no push, no PR.

## Assessment (2026-04-11)

- **Value**: n/a (already landed).
- **Effort**: n/a
- **Current state**: drift / done. State survey confirms
  `src/darkfactory/cli/discuss.py` exists and `prd discuss` is
  wired in the parser. The `commands/discuss/` subpackage, the
  three new builtins (`gather_prd_context`, `discuss_prd`,
  `commit_prd_changes`), and the prompt files all appear to
  have landed. Frontmatter `kind: done` is a data-entry error
  (not a valid kind) but likely indicates the author
  intended to mark it done. Status is still `review`.
- **Gaps to fully implement**:
  - Verify every AC against the shipped code. Most likely all
    15 are met.
  - Fix the `kind: done` frontmatter — `kind` should be
    `feature` (not `done`) and `status` should flip to `done`
    after verification.
- **Recommendation**: verify-then-close — ten-minute
  verification pass, then flip status and fix kind. Include
  in the supersede sweep with PRD-556, PRD-563, etc.

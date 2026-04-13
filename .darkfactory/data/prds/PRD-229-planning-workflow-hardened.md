---
id: "PRD-229"
title: "Hardened planning workflow: template + path enforcement + set_blocks builtin"
kind: task
status: draft
priority: medium
effort: m
capability: moderate
parent: null
depends_on:
  - "[[PRD-228-planning-workflow-initial]]"
  - "[[PRD-227-workflow-templates]]"
  - "[[PRD-549-builtins-package-split]]"
blocks: []
impacts:
  - python/darkfactory/workflows/planning/workflow.py
  - python/darkfactory/builtins/**
  - python/darkfactory/templates.py
  - python/darkfactory/model/_persistence.py
workflow: null
target_version: null
created: 2026-04-08
updated: '2026-04-11'
tags:
  - harness
  - workflow
  - planning
  - hardening
---

# Hardened planning workflow: template + path enforcement + set_blocks builtin

## Summary

PRD-228 ships the initial planning workflow using only existing primitives, with constraints enforced by **convention** (tool allowlist + prompt instructions). This PRD upgrades that workflow to use **hard enforcement** once PRD-227's template machinery is in place. Three concrete changes:

1. **Migrate the planning workflow to compose from `PLANNING_TEMPLATE`** (PRD-227 bundle), so its open/close invariants are guaranteed by the template instead of by convention.
2. **Add `forbidden_path_globs` enforcement to the template machinery** so the planning template can guarantee "this workflow's diff stays inside `.darkfactory/data/prds/`" — the agent literally cannot ship code changes through this workflow.
3. **Add a `set_blocks` BuiltIn** so the planning workflow can update the parent epic's `blocks:` field without giving the agent `Edit` access (closing the one honor-system leak in PRD-228).

After this lands, the planning workflow has the full template-enforced invariant set: state honesty (PRD-224), composition order (PRD-227), and path scoping (this PRD). Misuse becomes architecturally impossible, not just discouraged.

## Motivation

PRD-228's planning workflow has three known holes that can't be closed without infrastructure that doesn't exist yet:

1. **Tool allowlist is honor-system.** The allowlist scopes `Bash(git add .darkfactory/data/prds/:*)` but a determined agent could still try `Bash(git add src/foo.py)` and the harness would block it per-call. There's no workflow-level guarantee that the cumulative diff stays in `.darkfactory/data/prds/`.
2. **`Edit` access for the parent epic's `blocks:` field.** PRD-228 added `Edit` to the allowlist as a pragmatic exception so the agent could update the parent. That's a leak — `Edit` lets the agent modify any file it can read, not just `.darkfactory/data/prds/PRD-X.md`.
3. **Open/close convention, not enforcement.** The workflow body in PRD-228 lists the closing tasks (commit, push, create_pr) explicitly. A user editing `workflow.py` could remove `validate-children` or skip `set_status(review)` and break the lifecycle. PRD-227 templates make those positions structural.

These are all real risks but they're acceptable for PRD-228 because the alternative is "no planning workflow at all." This PRD closes them once the supporting infrastructure exists.

## Requirements

### 1. Migrate to `PLANNING_TEMPLATE`

PRD-227 ships `PLANNING_TEMPLATE` as a bundled template. This PRD updates `python/darkfactory/workflows/planning/workflow.py` to compose from it:

```python
from darkfactory.templates_builtin import PLANNING_TEMPLATE
from darkfactory.workflow import AgentTask, BuiltIn, ShellTask

planning_workflow = PLANNING_TEMPLATE.compose(
    name="planning",
    description="Decompose an epic or feature into task PRDs.",
    applies_to=_is_undecomposed_epic_or_feature,  # same predicate as PRD-228
    priority=5,
    middle=[
        AgentTask(
            name="decompose",
            prompts=[
                "prompts/role.md",
                "prompts/decomposition-guide.md",
                "prompts/task.md",
            ],
            tools=[
                "Read", "Glob", "Grep", "Write",
                # No Edit — the parent PRD's blocks field is updated by
                # the set_blocks BuiltIn after the agent finishes (see #3)
                "Bash(uv run prd validate*)",
                "Bash(git add .darkfactory/data/prds/:*)",
                "Bash(git status:*)",
                "Bash(git diff .darkfactory/data/prds/:*)",
            ],
            model="opus",
            model_from_capability=False,
            retries=1,
        ),
        ShellTask(
            "validate-children",
            cmd="uv run prd validate",
            on_failure="retry_agent",
        ),
        BuiltIn(
            "set_blocks",
            kwargs={
                "parent_id": "{prd_id}",
                # Children list comes from agent output via run_summary
                "from_run_summary_field": "created_children",
            },
        ),
    ],
)
```

The template's `open` and `close` lists are unchanged from PRD-227's `PLANNING_TEMPLATE` — the workflow author doesn't see them at all.

### 2. `forbidden_path_globs` template-level enforcement

PRD-227 defines `WorkflowTemplate` with required open/close + customizable middle. This PRD adds an optional field:

```python
@dataclass
class WorkflowTemplate:
    name: str
    open: list[Task]
    middle_kinds: list[type]
    close: list[Task]
    forbidden_path_globs: list[str] = field(default_factory=list)
    # ... existing fields ...
```

Templates can declare paths that must NOT be modified during a run. The runner enforces this via a new closing BuiltIn:

```python
PLANNING_TEMPLATE = WorkflowTemplate(
    name="planning",
    open=[...],
    forbidden_path_globs=[
        "src/**",
        "tests/**",
        "workflows/**",
        ".github/**",
        # Anything outside prds/ is off-limits
    ],
    close=[
        BuiltIn("verify_path_scope"),  # NEW: enforces forbidden_path_globs
        BuiltIn("summarize_agent_run"),
        BuiltIn("commit_transcript"),
        BuiltIn("set_status", kwargs={"to": "review"}),
        BuiltIn("commit", kwargs={"message": "..."}),
        BuiltIn("push_branch"),
        BuiltIn("create_pr"),
    ],
)
```

The new `verify_path_scope` BuiltIn:

```python
@builtin("verify_path_scope")
def verify_path_scope(ctx: ExecutionContext) -> None:
    """Fail the workflow if git status shows changes to forbidden paths.

    Reads `forbidden_path_globs` from the composed workflow's template.
    Runs `git status --porcelain` in the worktree, expands the globs,
    and raises if any matched path appears in the change set.

    This is the hard enforcement layer that turns 'tool allowlist
    discourages' into 'workflow guarantees'. A planning workflow that
    accidentally writes a source file fails here, not at PR review.
    """
    template = ctx.workflow.template
    if not template or not template.forbidden_path_globs:
        return  # nothing to enforce

    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(ctx.cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    changed = [line[3:] for line in result.stdout.strip().split("\n") if line]
    violations = []
    for path in changed:
        for pattern in template.forbidden_path_globs:
            if fnmatch.fnmatch(path, pattern):
                violations.append((path, pattern))
                break

    if violations:
        msg = "\n".join(
            f"  - {path} (matches forbidden glob {pattern!r})"
            for path, pattern in violations
        )
        raise RuntimeError(
            f"Workflow {ctx.workflow.name!r} modified files outside its allowed scope:\n{msg}\n"
            f"This workflow's template forbids changes to: {template.forbidden_path_globs}"
        )
```

### 3. `set_blocks` BuiltIn

Closes the `Edit`-leak from PRD-228. The agent doesn't update the parent's `blocks:` field directly — it returns the list of created children in its run summary, and a closing BuiltIn handles the parent edit deterministically:

```python
@builtin("set_blocks")
def set_blocks(
    ctx: ExecutionContext,
    *,
    parent_id: str,
    from_run_summary_field: str | None = None,
    children: list[str] | None = None,
) -> None:
    """Set the parent PRD's blocks field to the given children list.

    Either `children` is supplied directly (list of PRD ids without
    wikilink wrapping) or `from_run_summary_field` names a field on
    `ctx.run_summary` to read it from.

    Uses update_frontmatter_field_at (PRD-214) so other fields are
    preserved byte-for-byte. Wraps each id in [[PRD-X-slug]] format
    by looking the slug up in ctx.prds.
    """
    parent_id = ctx.format_string(parent_id)
    if children is None:
        if from_run_summary_field is None:
            raise ValueError("set_blocks needs either `children` or `from_run_summary_field`")
        children = ctx.run_summary.get(from_run_summary_field, [])

    if not children:
        ctx.logger.info("set_blocks: no children to set on %s, skipping", parent_id)
        return

    parent = ctx.prds.get(parent_id)
    if not parent:
        raise RuntimeError(f"set_blocks: parent {parent_id!r} not found in PRD set")

    # Convert to wikilink format
    wikilinks = []
    for child_id in sorted(children, key=parse_id_sort_key):
        child = ctx.prds.get(child_id)
        if not child:
            raise RuntimeError(f"set_blocks: child {child_id!r} not in PRD set (was it created?)")
        wikilinks.append(f'"[[{child_id}-{child.slug}]]"')

    parent_path = ctx.cwd / parent.path.relative_to(ctx.repo_root)
    blocks_yaml = "\n".join(f"  - {link}" for link in wikilinks)
    update_frontmatter_block_at(parent_path, "blocks", blocks_yaml)
```

This needs a companion `update_frontmatter_block_at` function in `python/darkfactory/model/_persistence.py` (multi-line variant of `update_frontmatter_field_at`). PRD-216's `normalize_list_field_at` is close to what's needed; this is a related but slightly different operation (replacing the whole list, not just sorting it).

### 4. Update planning agent prompts

The agent no longer manages the parent's `blocks:` field — instead it reports the children it created via a structured tail in its sentinel:

```
PRD_EXECUTE_OK: PRD-222
created: PRD-222.1, PRD-222.2, PRD-222.3, PRD-222.4, PRD-222.5, PRD-222.6
```

The runner parses the `created:` line into `ctx.run_summary["created_children"]`. The `set_blocks` BuiltIn then reads it.

`prompts/task.md` updates to reflect: "do NOT update the parent's blocks: field — the harness handles that. Instead, list the PRD IDs you created on a `created:` line right after the sentinel."

### 5. Tests

- `verify_path_scope` BuiltIn tests: clean diff, in-scope changes, forbidden-path violation
- `set_blocks` BuiltIn tests: from explicit list, from run_summary field, missing parent, missing child, byte-preservation of parent file
- Planning workflow integration test: agent creates 3 children, set_blocks updates parent, verify_path_scope passes
- Negative integration test: stub agent that writes a file outside `prds/`, verify the workflow fails at `verify_path_scope`

## Acceptance Criteria

- [ ] AC-1: `WorkflowTemplate` has a `forbidden_path_globs` field
- [ ] AC-2: `verify_path_scope` BuiltIn exists; raises on forbidden-path changes; no-op when forbidden_path_globs is empty
- [ ] AC-3: `set_blocks` BuiltIn updates the parent PRD's `blocks:` field byte-preserving
- [ ] AC-4: `update_frontmatter_block_at` (or equivalent) exists in `python/darkfactory/model/_persistence.py`
- [ ] AC-5: `PLANNING_TEMPLATE` includes `verify_path_scope` in its close list and lists `forbidden_path_globs` for src/tests/workflows/.github
- [ ] AC-6: `python/darkfactory/workflows/planning/workflow.py` is composed from `PLANNING_TEMPLATE` instead of declaring a flat task list
- [ ] AC-7: Agent allowlist no longer includes `Edit`
- [ ] AC-8: Agent prompts updated to emit `created: PRD-X, PRD-Y, ...` after sentinel; harness parses it into `run_summary`
- [ ] AC-9: Manual end-to-end: re-run planning on a previously-decomposed epic (or a new one); workflow completes; verify no `Edit` was used and `blocks:` was updated by the BuiltIn
- [ ] AC-10: Negative test: a workflow with planning template that tries to write `src/foo.py` fails at `verify_path_scope` before push
- [ ] AC-11: All PRD-228 tests still pass; this PRD adds tests for the new BuiltIns and template field

## Open Questions

- [ ] Should `verify_path_scope` also check **deletions**? An agent could `git rm src/foo.py` and that's outside prds/. Yes — the porcelain check picks up D-status entries too; the implementation needs to include them
- [ ] What about renames? `git status --porcelain` shows renames as `R old new` — both old and new should be checked against forbidden globs
- [ ] Should `forbidden_path_globs` be a deny-list or should we instead have `allowed_path_globs` as an allow-list? Allow-list is stricter (anything not on the list is forbidden) but harder to specify correctly. **Recommendation**: support both, prefer allow-list for templates that have a clear scope (planning), use deny-list for templates that are open-ended
- [ ] Does the run_summary `created` parsing work cleanly with the stream-json output from PRD-218? The sentinel parsing already handles the result event; this is one more line to extract
- [ ] What if the agent claims to have created a child but the file doesn't actually exist? `set_blocks` validates by looking up the child in `ctx.prds` — but `ctx.prds` is loaded at run start, not after the agent finishes. **Recommendation**: re-load PRDs from disk in the closing `set_blocks` step so it sees the agent's new files

## Relationship to other PRDs

- **Depends on PRD-228** — the initial planning workflow this hardens
- **Depends on PRD-227** — the `WorkflowTemplate` machinery and `PLANNING_TEMPLATE` bundle
- **Depends on PRD-214** — `update_frontmatter_field_at`, which the new `update_frontmatter_block_at` extends
- **Related to PRD-216** — `normalize_list_field_at` is the similar-but-distinct list-field helper
- **Closes** the three honor-system leaks documented in PRD-228's "Why we'll re-do parts of this in PRD-229" section
- **Pattern** for future hardened workflows — once `forbidden_path_globs` exists, other workflows can adopt it (e.g. an audit-only workflow with `forbidden_path_globs=["**/*"]` to make it pure-read)

## Why this is a separate PRD instead of merging into PRD-228

- **Speed**: PRD-228 can land and produce value without waiting for the template infrastructure
- **Decoupling**: PRD-227's template work is its own non-trivial epic; binding planning to it would block both
- **Validation**: shipping the convention-based version first surfaces what the hard enforcement actually needs to constrain (we may discover the agent never tries to touch source files in practice, in which case the hardening is more belt-and-suspenders than load-bearing)
- **Reusability**: the `verify_path_scope`, `set_blocks`, and `update_frontmatter_block_at` primitives this PRD adds are useful beyond planning — other future workflows can adopt them

## Assessment (2026-04-11)

- **Value**: 3/5 — this is the hardening pass for PRD-228's planning
  workflow. The honor-system holes it closes (Edit leak, tool-allowlist
  bypass, manual close sequence) are real but not currently causing
  incidents. Value rises to 4/5 in a multi-contributor setting.
- **Effort**: m — three non-trivial primitives
  (`verify_path_scope`, `set_blocks`, `update_frontmatter_block_at`),
  plus `forbidden_path_globs` template field addition, plus migration
  of `workflows/planning/workflow.py` onto the template.
- **Current state**: blocked by design. Depends on PRD-227 (workflow
  template machinery). PRD-227's children appear to be in `done` status
  — check whether `PLANNING_TEMPLATE` actually exists in
  `templates_builtin.py`. If yes, this PRD is unblocked.
- **Gaps to fully implement**:
  - Add `forbidden_path_globs` field to `WorkflowTemplate`.
  - Implement `verify_path_scope` builtin (expand `git status
    --porcelain` + glob match against template field).
  - Implement `set_blocks` builtin with `from_run_summary_field`
    param, plus `update_frontmatter_block_at` helper in
    `model/_persistence.py`.
  - Migrate `workflows/planning/workflow.py` to compose from
    `PLANNING_TEMPLATE`.
  - Update `prompts/task.md` to emit `created: PRD-X, ...` tail.
  - Parse that tail into `ctx.run_summary["created_children"]`.
  - Tests (positive + negative for each new primitive).
- **Recommendation**: do-next AFTER PRD-554 (soft prompt hardening)
  lands. PRD-554 is cheaper and gets most of the real-world reliability
  win. This PRD adds the architectural guarantees on top. Bundle with
  PRD-567.5 (planning template alignment) since both modify the
  same workflow and template field.

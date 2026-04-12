# Value vs. Effort — full PRD table (2026-04-11)
Sorted by `(value desc, effort asc, recommendation, id asc)`. See each PRD's own `## Assessment (2026-04-11)` section for thefull rationale — Value, Effort, Current state, Gaps, Recommendation.

Legend: `v=n/a e=n/a` means the PRD is already delivered / superseded.

| PRD | v | e | rec | status | title |
|---|---|---|---|---|---|
| [PRD-600.1.4](../../../.darkfactory/data/prds/PRD-600.1.4*.md) | 5 | xs | do-now | draft | Add ruff check and format check to CI |
| [PRD-567.1.2](../../../.darkfactory/data/prds/PRD-567.1.2*.md) | 5 | s | do-now | draft | Auto-recovery in ensure_worktree for merged/closed PRs |
| [PRD-600.1](../../../.darkfactory/data/prds/PRD-600.1*.md) | 5 | s | do-now | draft | Safety and correctness fixes identified by architectura… |
| [PRD-567.1](../../../.darkfactory/data/prds/PRD-567.1*.md) | 5 | m | do-now | draft | Worktree lifecycle resilience: auto-recovery and pre-ru… |
| [PRD-567](../../../.darkfactory/data/prds/PRD-567*.md) | 5 | l | do-next | draft | Workflow reliability improvements: auto-recovery, permi… |
| [PRD-563](../../../.darkfactory/data/prds/PRD-563*.md) | 5 | 0 | supersede | in-progress | Drain-ready-queue execution mode: run all ready PRDs wi… |
| [PRD-567.2.1](../../../.darkfactory/data/prds/PRD-567.2.1*.md) | 4 | xs | do-now | draft | Add explicit --disallowed-tools for harness-owned git o… |
| [PRD-567.2.2](../../../.darkfactory/data/prds/PRD-567.2.2*.md) | 4 | xs | do-now | draft | Harden role/task prompts against denial retry loops |
| [PRD-567.6](../../../.darkfactory/data/prds/PRD-567.6*.md) | 4 | xs | do-now | draft | Structured failure context in event logs |
| [PRD-600.3.5](../../../.darkfactory/data/prds/PRD-600.3.5*.md) | 4 | xs | do-now | draft | Add --yes flag to cleanup --all for non-interactive use |
| [PRD-619](../../../.darkfactory/data/prds/PRD-619*.md) | 4 | xs | do-now | draft | decouple reply_pr_comments from push success |
| [PRD-556](../../../.darkfactory/data/prds/PRD-556*.md) | 4 | xs | supersede | in-progress | Split src/darkfactory/cli.py into a package of per-subc… |
| [PRD-543](../../../.darkfactory/data/prds/PRD-543*.md) | 4 | s | do-now | draft | Harden harness create_pr step — surface gh errors and r… |
| [PRD-554](../../../.darkfactory/data/prds/PRD-554*.md) | 4 | s | do-now | draft | Harden the planning workflow prompts for higher-quality… |
| [PRD-567.1.1](../../../.darkfactory/data/prds/PRD-567.1.1*.md) | 4 | s | do-now | draft | Extract safe-branch-cleanup helper into builtins/_share… |
| [PRD-567.2](../../../.darkfactory/data/prds/PRD-567.2*.md) | 4 | s | do-now | draft | Agent permission hygiene: eliminate denial waste and ha… |
| [PRD-600.1.1](../../../.darkfactory/data/prds/PRD-600.1.1*.md) | 4 | s | do-now | draft | Add crash recovery to _create_reconcile_pr |
| [PRD-600.2](../../../.darkfactory/data/prds/PRD-600.2*.md) | 4 | s | do-now | draft | Tooling and CI hardening |
| [PRD-600.3.2](../../../.darkfactory/data/prds/PRD-600.3.2*.md) | 4 | s | do-now | draft | Add --json support to validate command |
| [PRD-600.3.7](../../../.darkfactory/data/prds/PRD-600.3.7*.md) | 4 | s | do-now | draft | Add prd show command for single-PRD inspection |
| [PRD-600.2.1](../../../.darkfactory/data/prds/PRD-600.2.1*.md) | 4 | s | do-next | draft | Configure comprehensive ruff rule set |
| [PRD-558](../../../.darkfactory/data/prds/PRD-558*.md) | 4 | m | do-next | draft | Auto-serialize sibling PRDs with overlapping impacts to… |
| [PRD-600.3](../../../.darkfactory/data/prds/PRD-600.3*.md) | 4 | m | do-next | draft | Operational hardening and CLI quality improvements |
| [PRD-608](../../../.darkfactory/data/prds/PRD-608*.md) | 4 | l | defer | draft | Project Toolchain Setup Wizard |
| [PRD-556.18](../../../.darkfactory/data/prds/PRD-556.18*.md) | 3 | xs | do-now | review | Final cleanup — remove residual cli.py, verify cli/ is … |
| [PRD-559.5](../../../.darkfactory/data/prds/PRD-559.5*.md) | 3 | xs | do-now | ready | Integrate analyze_transcript into workflows |
| [PRD-567.3.1](../../../.darkfactory/data/prds/PRD-567.3.1*.md) | 3 | xs | do-now | draft | Add file deletion permissions to task workflow |
| [PRD-600.2.3](../../../.darkfactory/data/prds/PRD-600.2.3*.md) | 3 | xs | do-now | draft | Add --version flag to CLI |
| [PRD-600.2.5](../../../.darkfactory/data/prds/PRD-600.2.5*.md) | 3 | xs | do-now | draft | Add Python 3.13 to CI test matrix |
| [PRD-605](../../../.darkfactory/data/prds/PRD-605*.md) | 3 | xs | do-now | blocked | Post-modularization code cleanup |
| [PRD-613](../../../.darkfactory/data/prds/PRD-613*.md) | 3 | ? | split | draft | Agent Model Configuration and Fallback |
| [PRD-600.3.1](../../../.darkfactory/data/prds/PRD-600.3.1*.md) | 3 | xs | merge-into | draft | Extract _run_shell_once to shared runner utility |
| [PRD-567.1.3](../../../.darkfactory/data/prds/PRD-567.1.3*.md) | 3 | s | do-now | draft | Pre-run stale worktree cleanup in graph execution |
| [PRD-600.2.2](../../../.darkfactory/data/prds/PRD-600.2.2*.md) | 3 | s | do-now | draft | Add pytest-cov and coverage reporting to CI |
| [PRD-600.3.3](../../../.darkfactory/data/prds/PRD-600.3.3*.md) | 3 | s | do-now | draft | Add --json support to tree command |
| [PRD-600.3.6](../../../.darkfactory/data/prds/PRD-600.3.6*.md) | 3 | s | do-now | draft | Add help text examples to top 5 commands |
| [PRD-603](../../../.darkfactory/data/prds/PRD-603*.md) | 3 | s | do-now | blocked | Transcript analysis robustness and error handling |
| [PRD-604](../../../.darkfactory/data/prds/PRD-604*.md) | 3 | s | do-now | blocked | JSONL transcript validation |
| [PRD-621](../../../.darkfactory/data/prds/PRD-621*.md) | 3 | s | do-now | ready | Refactor common functionality in regards to external sy… |
| [PRD-562](../../../.darkfactory/data/prds/PRD-562*.md) | 3 | s | do-next | draft | Build a skill to review DarkFactory PRDs and look for t… |
| [PRD-567.3](../../../.darkfactory/data/prds/PRD-567.3*.md) | 3 | s | do-next | draft | File operation permissions and workflow specialization |
| [PRD-567.3.2](../../../.darkfactory/data/prds/PRD-567.3.2*.md) | 3 | s | do-next | draft | Create refactor/cleanup workflow with broad file-operat… |
| [PRD-567.4.1](../../../.darkfactory/data/prds/PRD-567.4.1*.md) | 3 | s | do-next | draft | Block absolute-path escapes in invoke.py |
| [PRD-567.4.2](../../../.darkfactory/data/prds/PRD-567.4.2*.md) | 3 | s | do-next | draft | Post-invocation containment verification in runner |
| [PRD-570](../../../.darkfactory/data/prds/PRD-570*.md) | 3 | s | do-next | draft | Rename session_id to worker_id and emit worker lifecycl… |
| [PRD-600.3.8](../../../.darkfactory/data/prds/PRD-600.3.8*.md) | 3 | s | do-next | draft | Make project-level workflow loading failures loud |
| [PRD-225.7](../../../.darkfactory/data/prds/PRD-225.7*.md) | 3 | s | verify-then-close | review | Rework loop detection |
| [PRD-602](../../../.darkfactory/data/prds/PRD-602*.md) | 3 | m | do-now | review | Documentation site accuracy overhaul |
| [PRD-229](../../../.darkfactory/data/prds/PRD-229*.md) | 3 | m | do-next | draft | Hardened planning workflow: template + path enforcement… |
| [PRD-567.4](../../../.darkfactory/data/prds/PRD-567.4*.md) | 3 | m | do-next | draft | Filesystem containment hardening: block absolute-path e… |
| [PRD-550](../../../.darkfactory/data/prds/PRD-550*.md) | 3 | m | merge-into | draft | Flag downstream PRDs when an upstream change invalidate… |
| [PRD-546](../../../.darkfactory/data/prds/PRD-546*.md) | 3 | m | defer | draft | Detect drift between declared impacts and actual diff a… |
| [PRD-551](../../../.darkfactory/data/prds/PRD-551*.md) | 3 | m | defer | draft | Parallel execution of independent PRDs during graph tra… |
| [PRD-555](../../../.darkfactory/data/prds/PRD-555*.md) | 3 | m | defer | draft | backlog_review workflow — audit every ready PRD against… |
| [PRD-561](../../../.darkfactory/data/prds/PRD-561*.md) | 3 | m | defer | draft | Establish a skill to help discuss and create detailed P… |
| [PRD-564](../../../.darkfactory/data/prds/PRD-564*.md) | 3 | m | defer | draft | Interactive project init with configurable prd/workflow… |
| [PRD-545](../../../.darkfactory/data/prds/PRD-545*.md) | 3 | l | split | draft | Harness-driven rebase and conflict resolution for paral… |
| [PRD-607](../../../.darkfactory/data/prds/PRD-607*.md) | 3 | l | defer | draft | Interactive Work Item Discovery |
| [PRD-559.4](../../../.darkfactory/data/prds/PRD-559.4*.md) | 3 | 0 | supersede | review | Implement analyze_transcript builtin entry point |
| [PRD-600.1.3](../../../.darkfactory/data/prds/PRD-600.1.3*.md) | 2 | xs | do-now | draft | Remove setattr side channel in runner |
| [PRD-600.3.4](../../../.darkfactory/data/prds/PRD-600.3.4*.md) | 2 | xs | defer | draft | Warn when --json is passed to unsupported command |
| [PRD-600.1.2](../../../.darkfactory/data/prds/PRD-600.1.2*.md) | 2 | s | do-next | draft | Shell-escape user-controlled values in format_string |
| [PRD-540](../../../.darkfactory/data/prds/PRD-540*.md) | 2 | s | defer | draft | Set up PyPI publishing for darkfactory |
| [PRD-553](../../../.darkfactory/data/prds/PRD-553*.md) | 2 | s | defer | draft |  |
| [PRD-567.5](../../../.darkfactory/data/prds/PRD-567.5*.md) | 2 | s | defer | draft | Align planning workflow with WorkflowTemplate |
| [PRD-600.3.9](../../../.darkfactory/data/prds/PRD-600.3.9*.md) | 2 | s | defer | draft | Add pagination or warning to reconcile PR fetching |
| [PRD-612](../../../.darkfactory/data/prds/PRD-612*.md) | 2 | s | defer | draft | Agent-Assisted Toolchain Detection |
| [PRD-552](../../../.darkfactory/data/prds/PRD-552*.md) | 2 | m | defer | draft | Merge-upstream task for PRDs with multiple dependencies |
| [PRD-557](../../../.darkfactory/data/prds/PRD-557*.md) | 2 | m | defer | draft | Split src/darkfactory/runner.py into per-dispatcher mod… |
| [PRD-600.2.6](../../../.darkfactory/data/prds/PRD-600.2.6*.md) | 2 | m | defer | draft | Add tests for style.py |
| [PRD-600.4.2](../../../.darkfactory/data/prds/PRD-600.4.2*.md) | 2 | m | defer | draft | Extract reconcile domain logic from CLI handler |
| [PRD-600.4.3](../../../.darkfactory/data/prds/PRD-600.4.3*.md) | 2 | m | defer | draft | Add --json to remaining read commands |
| [PRD-600.4.4](../../../.darkfactory/data/prds/PRD-600.4.4*.md) | 2 | m | defer | draft | Introduce HarnessError exception hierarchy |
| [PRD-610](../../../.darkfactory/data/prds/PRD-610*.md) | 2 | m | defer | draft | Agent Substitution for SDLC Slots |
| [PRD-611](../../../.darkfactory/data/prds/PRD-611*.md) | 2 | m | defer | draft | Conditional SDLC Checks by File Path |
| [PRD-618](../../../.darkfactory/data/prds/PRD-618*.md) | 2 | m | defer | draft | interactive sync_branch builtin |
| [PRD-547](../../../.darkfactory/data/prds/PRD-547*.md) | 2 | l | defer | draft | Cross-epic scheduler coordination — coordinate parallel… |
| [PRD-609](../../../.darkfactory/data/prds/PRD-609*.md) | 2 | l | defer | draft | Workflow Retry and Recovery Expansion |
| [PRD-226](../../../.darkfactory/data/prds/PRD-226*.md) | 2 | xl | defer | draft | Derive PRD status from event log + git history (elimina… |
| [PRD-600.4.1](../../../.darkfactory/data/prds/PRD-600.4.1*.md) | 1 | m | defer | draft | Extract cmd_run argument resolution to standalone funct… |
| [PRD-600.4](../../../.darkfactory/data/prds/PRD-600.4*.md) | 1 | l | defer | draft | Frontend optionality seams |
| [PRD-616](../../../.darkfactory/data/prds/PRD-616*.md) | n/a | n/a | verify-then-close | review | Interactive PRD discussion via phased Claude Code chain |
| [PRD-600.2.4](../../../.darkfactory/data/prds/PRD-600.2.4*.md) | n/a | n/a | supersede | draft | Single-source the package version |
| [PRD-600.2.7](../../../.darkfactory/data/prds/PRD-600.2.7*.md) | n/a | n/a | supersede | draft | Delete dead cli.py stub file |
| [PRD-601](../../../.darkfactory/data/prds/PRD-601*.md) | n/a | xs | supersede | blocked | YAML date quoting consistency |
| [PRD-625](../../../.darkfactory/data/prds/PRD-625*.md) | n/a | n/a | supersede | ready | Archive Command |
| [PRD-600](../../../.darkfactory/data/prds/PRD-600*.md) | None | ? | treat | draft | Architectural Review and Code Quality Roadmap |

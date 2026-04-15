/**
 * dev-session workflow — interactive Claude session with quality gates and optional PR.
 *
 * 1. Opens an interactive Claude session (hands terminal to user)
 * 2. Runs quality checks (format, test, lint) — non-blocking
 * 3. Checks for uncommitted changes — stops if clean
 * 4. Asks user whether to create a PR — stops if declined
 * 5. Commits, pushes, and opens a PR
 */

import { execFileSync } from "node:child_process";
import {
  CodeEnv,
  PrRequest,
  WorktreeState,
} from "../../../core/workflow/engine/payloads.js";
import {
  commitTask,
  confirmTask,
  createPr,
  diffCheckTask,
  interactiveClaudeTask,
  pushBranch,
  shellTask,
} from "../../../core/workflow/engine/tasks/index.js";
import { workflow } from "../../../core/workflow/builder.js";
import type { Workflow } from "../../../core/workflow/types.js";

function currentBranch(cwd: string): string {
  return execFileSync("git", ["branch", "--show-current"], {
    cwd,
    encoding: "utf-8",
  }).trim();
}

export function create(cwd: string): Workflow {
  const branch = currentBranch(cwd);

  return workflow(
    "dev-session",
    "Interactive Claude session with quality checks and optional PR",
    "dev"
  )
    .seed(new CodeEnv({ repoRoot: cwd, cwd }))
    .seed(
      new WorktreeState({
        branch,
        baseRef: "main",
        worktreePath: cwd,
      })
    )
    .seed(
      new PrRequest({
        title: branch,
        body: "Changes from interactive dev session",
      })
    )
    .add(interactiveClaudeTask({ name: "claude-session" }))
    .add(shellTask({ name: "format", cmd: "just format", onFailure: "ignore" }))
    .add(shellTask({ name: "test", cmd: "just test", onFailure: "ignore" }))
    .add(shellTask({ name: "lint", cmd: "just lint", onFailure: "ignore" }))
    .add(diffCheckTask())
    .add(
      confirmTask({
        name: "confirm-pr",
        message: "Create a PR with these changes?",
      })
    )
    .add(commitTask({ message: `feat: dev session changes` }))
    .add(pushBranch())
    .add(createPr())
    .build();
}

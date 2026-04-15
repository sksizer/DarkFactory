/**
 * dev-session workflow — interactive Claude session with quality gates and optional PR.
 *
 * 1. Opens an interactive Claude session (hands terminal to user)
 * 2. Runs quality checks from project config — if any fail, an agent
 *    attempts to fix them (up to 3 retries)
 * 3. Checks for uncommitted changes — stops if clean
 * 4. Asks user whether to create a PR — stops if declined
 * 5. Commits, pushes, and opens a PR
 */

import { tryLoadConfig } from "../../../config/index.js";
import {
  CodeEnv,
  PrRequest,
  ProjectConfig,
  QualityResult,
  WorktreeState,
} from "../../../core/workflow/engine/payloads.js";
import {
  agentTask,
  codeQualityTask,
  commitTask,
  confirmTask,
  createPr,
  diffCheckTask,
  interactiveClaudeTask,
  pushBranch,
} from "../../../core/workflow/engine/tasks/index.js";
import { workflow } from "../../../core/workflow/builder.js";
import type { Workflow } from "../../../core/workflow/types.js";
import { currentBranch } from "../../../utils/exec/git.js";

function qualityFixPrompt(resolve: import("../../../core/workflow/engine/task.js").InputResolver): string {
  const qr = resolve(QualityResult);
  const failures = qr.checks
    .filter((c) => !c.success)
    .map((c) => `- ${c.name}: \`${c.cmd}\` exited ${String(c.exitCode)}\n  stderr: ${c.stderr.slice(0, 500)}`)
    .join("\n");

  return `You are a code quality fixer. The following quality checks failed:

${failures}

Fix the issues by editing the relevant source files. Common fixes:
- Format errors: run the formatter or fix formatting manually
- Type errors: fix type annotations, imports, or missing types
- Test failures: fix broken tests or the code they test
- Lint errors: fix the specific lint violations reported

Focus only on fixing the reported issues. Do not refactor or improve unrelated code.`;
}

export function create(cwd: string): Workflow {
  const branchResult = currentBranch(cwd);
  if (branchResult.kind === "err") {
    throw new Error(`Cannot determine current branch: ${branchResult.error.stderr}`);
  }
  const branch = branchResult.value;
  const config = tryLoadConfig(cwd);

  return workflow(
    "dev-session",
    "Interactive Claude session with quality checks and optional PR",
    "dev"
  )
    .seed(new CodeEnv({ repoRoot: cwd, cwd }))
    .seed(new ProjectConfig(config))
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
    .add(codeQualityTask(), {
      onFailure: {
        task: agentTask({
          name: "fix-quality",
          prompt: qualityFixPrompt,
          tools: ["Read", "Glob", "Grep", "Write", "Edit", "Bash"],
        }),
        retry: 3,
      },
    })
    .add(diffCheckTask())
    .add(
      confirmTask({
        name: "confirm-pr",
        message: "Create a PR with these changes?",
      })
    )
    .add(commitTask({ message: "feat: dev session changes" }))
    .add(pushBranch())
    .add(createPr())
    .build();
}

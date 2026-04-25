import { readFileSync } from "node:fs";
import { join } from "node:path";
import { workflow } from "../../../core/workflow/builder.js";
import {
  CodeEnv,
  PrRequest,
  WorktreeState,
} from "../../../core/workflow/engine/payloads.js";
import {
  agentTask,
  commitTask,
  createPr,
  createWorktree,
  enterWorktree,
  pushBranch,
  shellTask,
} from "../../../core/workflow/engine/tasks/index.js";
import type { Workflow } from "../../../core/workflow/types.js";
import { capabilityToModel } from "../../../utils/index.js";

const scanPrompt = readFileSync(join(import.meta.dirname, "scan.md"), "utf-8");

function timestamp(): string {
  return new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
}

export function create(cwd: string): Workflow {
  return workflow(
    "security-review",
    "Scan codebase for security issues, propose fixes, open a PR",
    "project"
  )
    .seed(new CodeEnv({ repoRoot: cwd, cwd }))
    .seed(
      new WorktreeState({
        branch: `security-review/${timestamp()}`,
        baseRef: "main",
      })
    )
    .seed(
      new PrRequest({
        title: `Security Review — ${timestamp()}`,
        body: "Automated security scan findings",
      })
    )
    .add(createWorktree())
    .add(enterWorktree())
    .add(
      agentTask({
        name: "scan",
        prompt: scanPrompt,
        tools: ["Read", "Glob", "Grep", "Write", "Edit"],
        sentinelSuccess: "PRD_EXECUTE_OK",
      })
    )
    .add(shellTask({ name: "format", cmd: "just format", onFailure: "fail" }))
    .add(shellTask({ name: "test", cmd: "just test", onFailure: "fail" }))
    .add(shellTask({ name: "lint", cmd: "just lint", onFailure: "fail" }))
    .add(commitTask({ message: "chore: security review findings" }))
    .add(pushBranch())
    .add(createPr())
    .build();
}

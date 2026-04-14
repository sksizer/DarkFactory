import { readFileSync } from "node:fs";
import { join } from "node:path";
import { workflow } from "../../builder.js";
import {
  createWorktree,
  enterWorktree,
  agentTask,
  shellTask,
  commitTask,
  pushBranch,
  createPr,
} from "../../../engine/tasks/index.js";
import { CodeEnv, WorktreeState, PrRequest } from "../../../engine/payloads.js";
import type { Workflow } from "../../core.js";

const scanPrompt = readFileSync(join(import.meta.dirname, "scan.md"), "utf-8");

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function create(cwd: string): Workflow {
  return workflow(
    "security-review",
    "Scan codebase for security issues, propose fixes, open a PR"
  )
    .seed(new CodeEnv({ repoRoot: cwd, cwd }))
    .seed(
      new WorktreeState({
        branch: `security-review/${today()}`,
        baseRef: "main",
      })
    )
    .seed(
      new PrRequest({
        title: `Security Review — ${today()}`,
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
    .add(shellTask({ name: "verify", cmd: "just test", onFailure: "ignore" }))
    .add(commitTask({ message: "chore: security review findings" }))
    .add(pushBranch())
    .add(createPr())
    .build();
}

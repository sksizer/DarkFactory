/**
 * architecture-assessment workflow — read-only deep architecture and
 * API-usability assessment of the current working directory.
 *
 * 1. Creates a worktree off main
 * 2. Runs a Claude agent restricted to Read/Glob/Grep + a single Write
 *    that produces ARCHITECTURE-ASSESSMENT-YYYY-MM-DD.md
 * 3. Commits the report and opens a PR
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { z } from "zod";
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
} from "../../../core/workflow/engine/tasks/index.js";
import type { Workflow } from "../../../core/workflow/types.js";

export const params = z.object({
  additionalContext: z
    .string()
    .optional()
    .describe(
      "Free-form context to inject into the assessment prompt (focus areas, known issues, audience, constraints)"
    ),
});

export type Params = z.infer<typeof params>;

const promptTemplate = readFileSync(
  join(import.meta.dirname, "assess.md"),
  "utf-8"
);

function timestamp(): string {
  // YYYY-MM-DD-HHMMSS (UTC) — sortable, filename-safe, distinguishes
  // multiple runs on the same day.
  const iso = new Date().toISOString();
  const date = iso.slice(0, 10);
  const time = iso.slice(11, 19).replace(/:/g, "");
  return `${date}-${time}`;
}

function renderAdditionalContext(text: string | undefined): string {
  const trimmed = text?.trim() ?? "";
  if (trimmed === "") return "";
  return [
    "## Additional context from caller",
    "",
    "The user supplied this context when invoking the assessment. Treat it as",
    "high-signal direction about focus areas, known issues, or constraints —",
    "but still cover the categories below as the baseline.",
    "",
    trimmed,
    "",
  ].join("\n");
}

export function create(cwd: string, opts?: Params): Workflow {
  const stamp = timestamp();
  const reportPath = `ARCHITECTURE-ASSESSMENT-${stamp}.md`;
  const additionalContextBlock = renderAdditionalContext(
    opts?.additionalContext
  );
  const prompt = promptTemplate
    .replaceAll("{{REPORT_PATH}}", reportPath)
    .replaceAll("{{ADDITIONAL_CONTEXT}}", additionalContextBlock);

  return workflow(
    "architecture-assessment",
    "Read-only deep architecture and API-usability assessment, written to a dated report and opened as a PR",
    "project"
  )
    .seed(new CodeEnv({ repoRoot: cwd, cwd }))
    .seed(
      new WorktreeState({
        branch: `architecture-assessment/${stamp}`,
        baseRef: "main",
      })
    )
    .seed(
      new PrRequest({
        title: `Architecture Assessment — ${stamp}`,
        body: `Read-only architecture and API-usability assessment.\n\nReport: \`${reportPath}\``,
      })
    )
    .add(createWorktree())
    .add(enterWorktree())
    .add(
      agentTask({
        name: "assess",
        prompt,
        tools: ["Read", "Glob", "Grep", "Write"],
        sentinelSuccess: "PRD_EXECUTE_OK",
        sentinelFailure: "PRD_EXECUTE_FAILED",
      })
    )
    .add(commitTask({ message: `docs: architecture assessment ${stamp}` }))
    .add(pushBranch())
    .add(createPr())
    .build();
}

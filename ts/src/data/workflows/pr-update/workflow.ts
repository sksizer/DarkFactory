/**
 * pr-update workflow — bring open PRs up-to-date with their target branches.
 *
 * 1. Lists open PRs authored by the current user.
 * 2. For each PR, fetches the base branch and attempts `git merge origin/<base>`
 *    in an isolated worktree.
 * 3. If the merge is clean, pushes. If conflicts arise, hands the worktree to
 *    a Claude agent that resolves the conflicts, then pushes.
 * 4. Records per-PR outcomes in a PrUpdateSummary.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { workflow } from "../../../core/workflow/builder.js";
import { CodeEnv } from "../../../core/workflow/engine/payloads.js";
import {
  listOpenPrsForUpdate,
  updateOpenPrs,
} from "../../../core/workflow/engine/tasks/index.js";
import type { Workflow } from "../../../core/workflow/types.js";

const conflictPrompt = readFileSync(
  join(import.meta.dirname, "resolve-conflicts.md"),
  "utf-8"
);

export function create(cwd: string): Workflow {
  return workflow(
    "pr-update",
    "Bring open PRs up-to-date with their base branches, using an agent for conflict resolution",
    "maintenance"
  )
    .seed(new CodeEnv({ repoRoot: cwd, cwd }))
    .add(listOpenPrsForUpdate({ author: "@me", excludeDrafts: true }))
    .add(updateOpenPrs({ conflictPrompt }))
    .build();
}

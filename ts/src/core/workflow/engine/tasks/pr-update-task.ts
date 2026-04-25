/**
 * pr-update-task.ts — tasks that bring open PRs up-to-date with their base branches.
 *
 * `listOpenPrsForUpdate` discovers candidate PRs and writes an OpenPrList.
 * `updateOpenPrs` iterates each PR: fetches the base, merges it into the PR branch
 * in an isolated worktree, and — if conflicts arise — invokes a Claude agent to
 * resolve them. Writes a PrUpdateSummary with per-PR outcomes.
 */

import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { match } from "ts-pattern";
import { getLogger } from "../../../../logger/index.js";
import { invokeClaude } from "../../../../utils/exec/claude-code.js";
import {
  add,
  commit,
  fetchRef,
  gitRun,
  isAncestor,
  mergeAbort,
  mergeInProgress,
  mergeRef,
  unmergedPaths,
  worktreeAdd,
  worktreeRemove,
} from "../../../../utils/exec/git.js";
import { listOpenPrDetails } from "../../../../utils/exec/github.js";
import {
  CodeEnv,
  type OpenPrInfo,
  OpenPrList,
  type PrUpdateEntry,
  type PrUpdateOutcome,
  PrUpdateSummary,
} from "../payloads.js";
import type { Task } from "../task.js";

const log = getLogger("pr-update");

export interface ListOpenPrsForUpdateConfig {
  readonly name?: string;
  /** gh author filter. Default: "@me" (the current user's PRs only). */
  readonly author?: string | undefined;
  readonly excludeDrafts?: boolean;
  readonly limit?: number;
}

export function listOpenPrsForUpdate(
  config: ListOpenPrsForUpdateConfig = {}
): Task<"CodeEnv", "OpenPrList"> {
  const author = config.author ?? "@me";
  const excludeDrafts = config.excludeDrafts ?? true;
  return {
    name: config.name ?? "list-open-prs",
    reads: [CodeEnv] as const,
    writes: OpenPrList,
    async run(env, resolve) {
      const codeEnv = resolve(CodeEnv);

      if (env.dryRun) {
        return {
          success: true,
          value: new OpenPrList({ prs: [] }),
        };
      }

      const result = await listOpenPrDetails(codeEnv.repoRoot, {
        author,
        excludeDrafts,
        ...(config.limit !== undefined ? { limit: config.limit } : {}),
      });
      if (result.kind === "err") {
        return {
          success: false,
          failureReason: `gh pr list failed: ${result.error.stderr}`,
        };
      }
      const prs: OpenPrInfo[] = result.value.map((pr) => ({
        number: pr.number,
        headRefName: pr.headRefName,
        baseRefName: pr.baseRefName,
        title: pr.title,
        isDraft: pr.isDraft,
      }));
      log.info({ count: prs.length, author }, "discovered open PRs");
      return { success: true, value: new OpenPrList({ prs }) };
    },
  };
}

export interface UpdateOpenPrsConfig {
  readonly name?: string;
  /** Prompt handed to the agent when resolving merge conflicts. */
  readonly conflictPrompt: string;
  /** Tools the conflict-resolution agent may use. */
  readonly conflictAgentTools?: readonly string[];
  /** Model for the conflict-resolution agent. Default: "sonnet". */
  readonly conflictAgentModel?: string;
  /** Per-invocation agent timeout in ms. Default: 600_000. */
  readonly conflictAgentTimeout?: number;
  /**
   * When true, failures on individual PRs abort the workflow. When false,
   * we record the failure and continue. Default: false.
   */
  readonly stopOnFailure?: boolean;
}

const DEFAULT_CONFLICT_TOOLS: readonly string[] = [
  "Read",
  "Write",
  "Edit",
  "Grep",
  "Glob",
  "Bash",
];

interface PrContext {
  readonly pr: OpenPrInfo;
  readonly worktreePath: string;
}

async function tryMergeOnePr(
  pr: OpenPrInfo,
  repoRoot: string,
  config: UpdateOpenPrsConfig
): Promise<PrUpdateOutcome> {
  const remoteBase = `origin/${pr.baseRefName}`;

  const fetchBase = await fetchRef(pr.baseRefName, repoRoot);
  if (fetchBase.kind === "err") {
    return {
      kind: "failed",
      reason: `fetch ${pr.baseRefName} failed`,
    };
  }

  const fetchHead = await fetchRef(pr.headRefName, repoRoot);
  if (fetchHead.kind === "err") {
    return {
      kind: "failed",
      reason: `fetch ${pr.headRefName} failed`,
    };
  }

  const ancestor = await isAncestor(
    remoteBase,
    `origin/${pr.headRefName}`,
    repoRoot
  );
  if (ancestor.kind === "ok" && ancestor.value) {
    return { kind: "already-up-to-date" };
  }

  return runMergeInWorktree(pr, repoRoot, config);
}

async function runMergeInWorktree(
  pr: OpenPrInfo,
  repoRoot: string,
  config: UpdateOpenPrsConfig
): Promise<PrUpdateOutcome> {
  const worktreePath = join(repoRoot, ".worktrees", `pr-${String(pr.number)}`);
  await mkdir(join(repoRoot, ".worktrees"), { recursive: true });

  const addWt = await worktreeAdd(worktreePath, pr.headRefName, repoRoot);
  if (addWt.kind === "err") {
    return {
      kind: "failed",
      reason: `worktree add failed for ${pr.headRefName}`,
    };
  }

  const ctx: PrContext = { pr, worktreePath };
  try {
    return await attemptMerge(ctx, config);
  } finally {
    const rm = await worktreeRemove(worktreePath, repoRoot);
    if (rm.kind === "err") {
      log.warn(
        { pr: pr.number, path: worktreePath },
        "worktree remove failed; leaving in place"
      );
    }
  }
}

async function attemptMerge(
  ctx: PrContext,
  config: UpdateOpenPrsConfig
): Promise<PrUpdateOutcome> {
  const remoteBase = `origin/${ctx.pr.baseRefName}`;
  const mergeResult = await mergeRef(remoteBase, ctx.worktreePath);
  if (mergeResult.kind === "err") {
    return {
      kind: "failed",
      reason: `git merge failed: ${mergeResult.error.stderr.slice(0, 200)}`,
    };
  }

  return match(mergeResult.value)
    .with({ kind: "already-up-to-date" }, () =>
      Promise.resolve({ kind: "already-up-to-date" } as PrUpdateOutcome)
    )
    .with({ kind: "fast-forward" }, async () => {
      const pushed = await pushHead(ctx);
      return pushed.success
        ? ({ kind: "fast-forward-merged" } as PrUpdateOutcome)
        : ({ kind: "failed", reason: pushed.reason } as PrUpdateOutcome);
    })
    .with({ kind: "merge-commit" }, async () => {
      const pushed = await pushHead(ctx);
      return pushed.success
        ? ({ kind: "merged-clean" } as PrUpdateOutcome)
        : ({ kind: "failed", reason: pushed.reason } as PrUpdateOutcome);
    })
    .with({ kind: "conflict" }, async () => resolveWithAgent(ctx, config))
    .exhaustive();
}

async function pushHead(
  ctx: PrContext
): Promise<{ success: true } | { success: false; reason: string }> {
  const result = await gitRun(["push", "origin", ctx.pr.headRefName], {
    cwd: ctx.worktreePath,
  });
  if (result.kind === "err") {
    const reason =
      result.error.kind === "git-err"
        ? result.error.stderr.slice(0, 200)
        : `timeout after ${String(result.error.timeout)}ms`;
    return { success: false, reason: `git push failed: ${reason}` };
  }
  return { success: true };
}

async function resolveWithAgent(
  ctx: PrContext,
  config: UpdateOpenPrsConfig
): Promise<PrUpdateOutcome> {
  const tools = config.conflictAgentTools ?? DEFAULT_CONFLICT_TOOLS;
  const model = config.conflictAgentModel ?? "sonnet";
  const timeout = config.conflictAgentTimeout ?? 600_000;

  const prompt = buildConflictPrompt(ctx.pr, config.conflictPrompt);
  log.info(
    { pr: ctx.pr.number, head: ctx.pr.headRefName },
    "conflicts detected, invoking agent"
  );

  const invocation = await invokeClaude({
    cwd: ctx.worktreePath,
    prompt,
    tools,
    model,
    timeout,
  });

  if (invocation.kind === "err") {
    await safelyAbortMerge(ctx);
    return {
      kind: "failed",
      reason: `agent invoke failed: ${invocation.error.reason}`,
    };
  }

  const inv = invocation.value;
  const unmerged = await unmergedPaths(ctx.worktreePath);
  if (unmerged.kind === "err") {
    await safelyAbortMerge(ctx);
    return {
      kind: "failed",
      reason: `git status failed after agent: ${unmerged.error.stderr.slice(0, 200)}`,
    };
  }

  if (unmerged.value.length > 0 || !inv.success) {
    await safelyAbortMerge(ctx);
    const reason =
      unmerged.value.length > 0
        ? `agent left unmerged files: ${unmerged.value.slice(0, 5).join(", ")}`
        : (inv.failureReason ?? "agent reported failure");
    return { kind: "failed", reason };
  }

  const inMerge = await mergeInProgress(ctx.worktreePath);
  if (inMerge.kind === "ok" && inMerge.value) {
    const staged = await add(["."], ctx.worktreePath);
    if (staged.kind === "err") {
      await safelyAbortMerge(ctx);
      return { kind: "failed", reason: "failed to stage resolved files" };
    }
    const committed = await commit(
      `merge: resolve conflicts from ${ctx.pr.baseRefName}`,
      ctx.worktreePath
    );
    if (committed.kind === "err") {
      await safelyAbortMerge(ctx);
      return { kind: "failed", reason: "failed to create merge commit" };
    }
  }

  const pushed = await pushHead(ctx);
  if (!pushed.success) {
    return { kind: "failed", reason: pushed.reason };
  }
  return { kind: "merged-with-agent", sentinel: inv.sentinel };
}

function buildConflictPrompt(pr: OpenPrInfo, basePrompt: string): string {
  const header = [
    `You are resolving merge conflicts for PR #${String(pr.number)}: ${pr.title}`,
    `Branch: ${pr.headRefName}  Base: ${pr.baseRefName}`,
    `Working directory is a git worktree with 'git merge origin/${pr.baseRefName}' in progress.`,
    "",
  ].join("\n");
  return `${header}${basePrompt}`;
}

async function safelyAbortMerge(ctx: PrContext): Promise<void> {
  const aborted = await mergeAbort(ctx.worktreePath);
  if (aborted.kind === "err") {
    log.warn(
      { pr: ctx.pr.number, path: ctx.worktreePath },
      "merge --abort failed; worktree will be force-removed"
    );
  }
}

export function updateOpenPrs(
  config: UpdateOpenPrsConfig
): Task<"CodeEnv" | "OpenPrList", "PrUpdateSummary"> {
  const stopOnFailure = config.stopOnFailure ?? false;
  return {
    name: config.name ?? "update-open-prs",
    reads: [CodeEnv, OpenPrList] as const,
    writes: PrUpdateSummary,
    async run(env, resolve) {
      const codeEnv = resolve(CodeEnv);
      const list = resolve(OpenPrList);

      if (env.dryRun) {
        const entries: PrUpdateEntry[] = list.prs.map((pr) => ({
          number: pr.number,
          headRefName: pr.headRefName,
          baseRefName: pr.baseRefName,
          outcome: { kind: "skipped", reason: "dry-run" },
        }));
        return {
          success: true,
          value: new PrUpdateSummary({ entries }),
        };
      }

      const entries: PrUpdateEntry[] = [];
      for (const pr of list.prs) {
        log.info(
          {
            pr: pr.number,
            head: pr.headRefName,
            base: pr.baseRefName,
          },
          "updating PR"
        );

        let outcome: PrUpdateOutcome;
        try {
          outcome = await tryMergeOnePr(pr, codeEnv.repoRoot, config);
        } catch (e) {
          outcome = {
            kind: "failed",
            reason: `unexpected error: ${e instanceof Error ? e.message : String(e)}`,
          };
        }

        entries.push({
          number: pr.number,
          headRefName: pr.headRefName,
          baseRefName: pr.baseRefName,
          outcome,
        });

        log.info({ pr: pr.number, outcome }, "PR update outcome");

        if (outcome.kind === "failed" && stopOnFailure) {
          return {
            success: false,
            failureReason: `PR #${String(pr.number)} failed: ${outcome.reason}`,
            value: new PrUpdateSummary({ entries }),
          };
        }
      }

      return {
        success: true,
        value: new PrUpdateSummary({ entries }),
      };
    },
  };
}

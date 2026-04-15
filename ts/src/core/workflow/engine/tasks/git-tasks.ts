import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import {
  add,
  branchExistsLocal,
  commit,
  gitRun,
  worktreeAdd,
} from "../../../../utils/exec/git.js";
import { createPr as ghCreatePr } from "../../../../utils/exec/github.js";
import { CodeEnv, PrRequest, PrResult, WorktreeState } from "../payloads.js";
import type { Task } from "../task.js";

function sanitizeBranch(branch: string): string {
  return branch.replace(/\//g, "-");
}

function gitErrMsg(error: {
  kind: string;
  stderr?: string;
  timeout?: number;
}): string {
  if (error.kind === "git-err") {
    return (error as { stderr: string }).stderr;
  }
  return `timeout after ${String((error as { timeout: number }).timeout)}ms`;
}

export function createWorktree(): Task<
  "WorktreeState" | "CodeEnv",
  "WorktreeState"
> {
  return {
    name: "create-worktree",
    reads: [WorktreeState, CodeEnv] as const,
    writes: WorktreeState,
    async run(env, resolve) {
      const ws = resolve(WorktreeState);
      const codeEnv = resolve(CodeEnv);
      const wtPath = join(
        codeEnv.repoRoot,
        ".worktrees",
        sanitizeBranch(ws.branch)
      );

      if (env.dryRun) {
        return {
          success: true,
          value: new WorktreeState({
            branch: ws.branch,
            baseRef: ws.baseRef,
            worktreePath: wtPath,
          }),
        };
      }

      const existsResult = await branchExistsLocal(codeEnv.repoRoot, ws.branch);
      if (existsResult.kind === "err") {
        return {
          success: false,
          failureReason: `Failed to check branch existence: ${existsResult.error.stderr}`,
        };
      }

      if (!existsResult.value) {
        const createResult = await gitRun(["branch", ws.branch, ws.baseRef], {
          cwd: codeEnv.repoRoot,
        });
        if (createResult.kind === "err") {
          return {
            success: false,
            failureReason: `Failed to create branch ${ws.branch}: ${gitErrMsg(createResult.error)}`,
          };
        }
      }

      await mkdir(join(codeEnv.repoRoot, ".worktrees"), { recursive: true });

      const addResult = await worktreeAdd(wtPath, ws.branch, codeEnv.repoRoot);
      if (addResult.kind === "err") {
        return {
          success: false,
          failureReason: `Failed to add worktree: ${gitErrMsg(addResult.error)}`,
        };
      }

      return {
        success: true,
        value: new WorktreeState({
          branch: ws.branch,
          baseRef: ws.baseRef,
          worktreePath: wtPath,
        }),
      };
    },
  };
}

export function enterWorktree(): Task<"WorktreeState", "CodeEnv"> {
  return {
    name: "enter-worktree",
    reads: [WorktreeState] as const,
    writes: CodeEnv,
    run(env, resolve) {
      const ws = resolve(WorktreeState);
      if (env.dryRun) {
        return {
          success: true,
          value: new CodeEnv({
            repoRoot: ws.worktreePath ?? ".",
            cwd: ws.worktreePath ?? ".",
          }),
        };
      }

      if (ws.worktreePath === undefined) {
        return {
          success: false,
          failureReason:
            "enterWorktree: WorktreeState has no worktreePath — was createWorktree run first?",
        };
      }

      return {
        success: true,
        value: new CodeEnv({
          repoRoot: ws.worktreePath,
          cwd: ws.worktreePath,
        }),
      };
    },
  };
}

export function commitTask(config: {
  message: string;
  files?: string[] | undefined;
}): Task<"CodeEnv"> {
  const filesToStage = config.files ?? ["."];
  return {
    name: "commit",
    reads: [CodeEnv] as const,
    async run(env, resolve) {
      const codeEnv = resolve(CodeEnv);
      if (env.dryRun) return { success: true };

      const addResult = await add(filesToStage, codeEnv.cwd);
      if (addResult.kind === "err") {
        return {
          success: false,
          failureReason: `git add failed: ${gitErrMsg(addResult.error)}`,
        };
      }

      const commitResult = await commit(config.message, codeEnv.cwd);
      if (commitResult.kind === "err") {
        return {
          success: false,
          failureReason: `git commit failed: ${gitErrMsg(commitResult.error)}`,
        };
      }

      return { success: true };
    },
  };
}

export function pushBranch(): Task<"WorktreeState"> {
  return {
    name: "push-branch",
    reads: [WorktreeState] as const,
    async run(env, resolve) {
      const ws = resolve(WorktreeState);
      if (env.dryRun) return { success: true };

      if (ws.worktreePath === undefined) {
        return {
          success: false,
          failureReason: "pushBranch: WorktreeState has no worktreePath",
        };
      }

      const result = await gitRun(["push", "-u", "origin", ws.branch], {
        cwd: ws.worktreePath,
      });
      if (result.kind === "err") {
        return {
          success: false,
          failureReason: `git push failed: ${gitErrMsg(result.error)}`,
        };
      }

      return { success: true };
    },
  };
}

export function createPr(): Task<"PrRequest" | "WorktreeState", "PrResult"> {
  return {
    name: "create-pr",
    reads: [PrRequest, WorktreeState] as const,
    writes: PrResult,
    async run(env, resolve) {
      const pr = resolve(PrRequest);
      const ws = resolve(WorktreeState);

      if (env.dryRun) {
        return {
          success: true,
          value: new PrResult({ url: "[dry-run] would create PR" }),
        };
      }

      if (ws.worktreePath === undefined) {
        return {
          success: false,
          failureReason: "createPr: WorktreeState has no worktreePath",
        };
      }

      const result = await ghCreatePr({
        base: ws.baseRef,
        title: pr.title,
        body: pr.body,
        cwd: ws.worktreePath,
      });

      if (result.kind === "err") {
        return {
          success: false,
          failureReason: `gh pr create failed: ${result.error.stderr}`,
        };
      }

      return {
        success: true,
        value: new PrResult({ url: result.value }),
      };
    },
  };
}

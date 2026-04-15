/**
 * git.ts — git CLI wrappers.
 *
 * All functions call exec(["git", ...args]) via utils/subprocess.ts
 * and return Result types. Never throws.
 */

import { execFileSync } from "node:child_process";
import { type Result, err, ok } from "../result.js";
import { type Timeout, ProcessTimeoutError, exec } from "./subprocess.js";

// ---------- Types ----------

/** Non-zero git CLI exit. */
export interface GitErr {
  readonly kind: "git-err";
  readonly returncode: number;
  readonly stdout: string;
  readonly stderr: string;
  readonly cmd: readonly string[];
}

export type GitResult<T> = Result<T, GitErr>;
export type CheckResult = Result<null, GitErr | Timeout>;

export interface WorktreeEntry {
  readonly path: string;
  readonly branch: string;
  readonly head: string;
}

// ---------- Internal helpers ----------

function makeGitErr(
  returncode: number,
  stdout: string,
  stderr: string,
  cmd: readonly string[]
): GitErr {
  return { kind: "git-err", returncode, stdout, stderr, cmd };
}

function makeTimeout(cmd: readonly string[], timeout: number): Timeout {
  return { kind: "timeout", cmd, timeout };
}

// ---------- Gateway ----------

/**
 * Run git with the given args. Returns CheckResult — never throws.
 * This is the single entry point for all git subprocess calls.
 */
export async function gitRun(
  args: readonly string[],
  options: { cwd: string; timeout?: number }
): Promise<CheckResult> {
  const cmd = ["git", ...args] as const;
  try {
    const result = await exec(cmd, {
      cwd: options.cwd,
      ...(options.timeout !== undefined ? { timeout: options.timeout } : {}),
    });
    if (result.exitCode !== 0) {
      return err(
        makeGitErr(result.exitCode, result.stdout, result.stderr, cmd)
      );
    }
    return ok(null, result.stdout);
  } catch (e) {
    if (e instanceof ProcessTimeoutError) {
      return err(makeTimeout(cmd, e.timeoutMs));
    }
    return err(makeGitErr(-1, "", String(e), cmd));
  }
}

// ---------- Branch operations ----------

/**
 * Return whether branch exists in the local repo's refs.
 * Returns GitResult<boolean> so callers see the actual error on failure.
 */
export async function branchExistsLocal(
  repoRoot: string,
  branch: string
): Promise<GitResult<boolean>> {
  const result = await gitRun(
    ["rev-parse", "--verify", "--quiet", `refs/heads/${branch}`],
    { cwd: repoRoot }
  );
  if (result.kind === "ok") {
    return ok(true, result.stdout);
  }
  if (result.error.kind === "timeout") {
    return err(
      makeGitErr(
        -1,
        "",
        `timed out after ${String(result.error.timeout)}ms`,
        result.error.cmd
      )
    );
  }
  // Git returns exit 1 when the ref doesn't exist — that's "false", not an error
  if (result.error.returncode === 1) {
    return ok(false, "");
  }
  return err(result.error);
}

/**
 * Return whether branch exists on origin. Best-effort: network timeouts
 * return a GitResult<boolean> with the error so callers can decide how to proceed.
 */
export async function branchExistsRemote(
  repoRoot: string,
  branch: string
): Promise<GitResult<boolean>> {
  const result = await gitRun(
    ["ls-remote", "--exit-code", "origin", `refs/heads/${branch}`],
    { cwd: repoRoot, timeout: 10_000 }
  );
  if (result.kind === "ok") {
    return ok(true, result.stdout);
  }
  if (result.error.kind === "timeout") {
    return err(
      makeGitErr(
        -1,
        "",
        `timed out after ${String(result.error.timeout)}ms`,
        result.error.cmd
      )
    );
  }
  if (result.error.returncode === 2) {
    // ls-remote --exit-code returns 2 when ref not found
    return ok(false, "");
  }
  return err(result.error);
}

/**
 * Find local branches matching a glob pattern.
 */
export async function findLocalBranches(
  pattern: string,
  repoRoot: string
): Promise<GitResult<string[]>> {
  const result = await gitRun(["branch", "--list", pattern], { cwd: repoRoot });
  if (result.kind === "err") {
    if (result.error.kind === "timeout") {
      return err(
        makeGitErr(
          -1,
          "",
          `timed out after ${String(result.error.timeout)}ms`,
          result.error.cmd
        )
      );
    }
    return err(result.error);
  }
  const branches = result.stdout
    .split("\n")
    .map((line) => line.trim().replace(/^\* /, ""))
    .filter(Boolean);
  return ok(branches, result.stdout);
}

/**
 * Find remote branches matching a glob pattern (origin/ prefix).
 */
export async function findRemoteBranches(
  pattern: string,
  repoRoot: string
): Promise<GitResult<string[]>> {
  const result = await gitRun(["branch", "-r", "--list", `origin/${pattern}`], {
    cwd: repoRoot,
  });
  if (result.kind === "err") {
    if (result.error.kind === "timeout") {
      return err(
        makeGitErr(
          -1,
          "",
          `timed out after ${String(result.error.timeout)}ms`,
          result.error.cmd
        )
      );
    }
    return err(result.error);
  }
  const branches = result.stdout
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  return ok(branches, result.stdout);
}

// ---------- Staging and committing ----------

/** Stage specific paths. */
export async function add(paths: string[], cwd: string): Promise<CheckResult> {
  return gitRun(["add", "--", ...paths], { cwd });
}

/** Create a commit with the given message. */
export async function commit(
  message: string,
  cwd: string
): Promise<CheckResult> {
  return gitRun(["commit", "-m", message], { cwd });
}

// ---------- Diff and status ----------

/**
 * Return Ok(null) if there are NO changes (clean), Err(GitErr) if dirty.
 */
export async function diffQuiet(
  paths: string[],
  cwd: string
): Promise<CheckResult> {
  return gitRun(["diff", "--quiet", "--", ...paths], { cwd });
}

/**
 * Return the list of dirty files NOT in the given paths list.
 */
export async function statusOtherDirty(
  paths: string[],
  cwd: string
): Promise<GitResult<string[]>> {
  const result = await gitRun(["status", "--porcelain"], { cwd });
  if (result.kind === "err") {
    if (result.error.kind === "timeout") {
      return err(
        makeGitErr(
          -1,
          "",
          `timed out after ${String(result.error.timeout)}ms`,
          result.error.cmd
        )
      );
    }
    return err(result.error);
  }
  const pathSet = new Set(paths);
  const dirty = result.stdout
    .split("\n")
    .filter(Boolean)
    .map((line) => line.slice(3).trim())
    .filter((f) => !pathSet.has(f));
  return ok(dirty, result.stdout);
}

/** Resolve a commit SHA or ref to an ISO-8601 author timestamp. */
export async function resolveCommitTimestamp(
  commit: string,
  cwd: string
): Promise<GitResult<string>> {
  const result = await gitRun(["log", "-1", "--format=%aI", commit], { cwd });
  if (result.kind === "err") {
    if (result.error.kind === "timeout") {
      return err(
        makeGitErr(
          -1,
          "",
          `timed out after ${String(result.error.timeout)}ms`,
          result.error.cmd
        )
      );
    }
    return err(result.error);
  }
  return ok(result.stdout.trim(), result.stdout);
}

// ---------- Worktree operations ----------

/**
 * List all registered worktrees. Parses git worktree list --porcelain output.
 */
export async function worktreeList(
  repoRoot: string
): Promise<GitResult<WorktreeEntry[]>> {
  const result = await gitRun(["worktree", "list", "--porcelain"], {
    cwd: repoRoot,
  });
  if (result.kind === "err") {
    if (result.error.kind === "timeout") {
      return err(
        makeGitErr(
          -1,
          "",
          `timed out after ${String(result.error.timeout)}ms`,
          result.error.cmd
        )
      );
    }
    return err(result.error);
  }

  const entries: WorktreeEntry[] = [];
  let currentPath: string | null = null;
  let currentHead: string | null = null;
  let currentBranch: string | null = null;

  for (const rawLine of result.stdout.split("\n")) {
    const line = rawLine.trim();
    if (line.startsWith("worktree ")) {
      currentPath = line.slice("worktree ".length);
      currentHead = null;
      currentBranch = null;
    } else if (line.startsWith("HEAD ")) {
      currentHead = line.slice("HEAD ".length);
    } else if (line.startsWith("branch ")) {
      currentBranch = line.slice("branch ".length).replace("refs/heads/", "");
    } else if (line === "") {
      if (
        currentPath !== null &&
        currentHead !== null &&
        currentBranch !== null
      ) {
        entries.push({
          path: currentPath,
          branch: currentBranch,
          head: currentHead,
        });
      }
      currentPath = null;
      currentHead = null;
      currentBranch = null;
    }
  }
  // Handle last entry (no trailing blank line)
  if (currentPath !== null && currentHead !== null && currentBranch !== null) {
    entries.push({
      path: currentPath,
      branch: currentBranch,
      head: currentHead,
    });
  }

  return ok(entries, result.stdout);
}

/** Add a new worktree at path on the given branch. */
export async function worktreeAdd(
  wtPath: string,
  branch: string,
  repoRoot: string
): Promise<CheckResult> {
  return gitRun(["worktree", "add", wtPath, branch], { cwd: repoRoot });
}

/** Remove a worktree (force). */
export async function worktreeRemove(
  wtPath: string,
  repoRoot: string
): Promise<CheckResult> {
  return gitRun(["worktree", "remove", "--force", wtPath], { cwd: repoRoot });
}

// ---------- Sync helpers ----------

/** Return the current branch name. Sync. */
export function currentBranch(cwd: string): GitResult<string> {
  try {
    const branch = execFileSync("git", ["branch", "--show-current"], {
      cwd,
      encoding: "utf-8",
    }).trim();
    if (branch === "") {
      return err(
        makeGitErr(0, "", "detached HEAD — no current branch", [
          "git",
          "branch",
          "--show-current",
        ])
      );
    }
    return ok(branch);
  } catch (e) {
    const stderr = e instanceof Error ? e.message : String(e);
    return err(makeGitErr(-1, "", stderr, ["git", "branch", "--show-current"]));
  }
}

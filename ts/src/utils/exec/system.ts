/**
 * system.ts — prerequisite checks.
 *
 * Returns Result instead of throwing SystemExit like the Python version.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { type Result, err, ok } from "../result.js";
import { which } from "./subprocess.js";

export interface PrerequisiteErr {
  readonly kind: "prerequisite-err";
  readonly missing: readonly string[];
  readonly message: string;
}

/**
 * Check that git, gh, and optionally claude are on PATH, and that
 * cwd is inside a git working tree.
 *
 * Returns Result<null, PrerequisiteErr> — no exceptions.
 */
export function checkPrerequisites(
  cwd: string,
  options?: { requireClaude?: boolean }
): Result<null, PrerequisiteErr> {
  const missing: string[] = [];

  if (which("git") === null) {
    missing.push("git");
  }

  if (which("gh") === null) {
    missing.push("gh");
  }

  if ((options?.requireClaude ?? true) && which("claude") === null) {
    missing.push("claude");
  }

  if (missing.length > 0) {
    const list = missing.map((m) => `'${m}'`).join(", ");
    return err({
      kind: "prerequisite-err",
      missing,
      message: `error: required tools not on PATH: ${list}`,
    });
  }

  // Check that cwd is inside a git working tree
  if (!isInsideGitWorkTree(cwd)) {
    return err({
      kind: "prerequisite-err",
      missing: [],
      message: "error: current directory is not inside a git working tree.",
    });
  }

  return ok(null);
}

/**
 * Walk up directory tree to find a .git file or directory.
 */
function isInsideGitWorkTree(startDir: string): boolean {
  let current = path.resolve(startDir);
  const root = path.parse(current).root;

  while (current !== root) {
    const gitPath = path.join(current, ".git");
    try {
      fs.accessSync(gitPath);
      return true;
    } catch {
      // Not found here — walk up
    }
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }

  return false;
}

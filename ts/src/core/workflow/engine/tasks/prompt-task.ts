/**
 * prompt-task.ts — interactive user prompts and precondition checks.
 */

import * as readline from "node:readline";
import { gitRun } from "../../../../utils/exec/git.js";
import { CodeEnv } from "../payloads.js";
import type { Task } from "../task.js";

function ask(message: string): Promise<string> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    rl.question(message, (answer) => {
      rl.close();
      resolve(answer);
    });
  });
}

/**
 * Prompt the user with a yes/no question.
 * Returns success if user answers yes, failure (with reason) if no.
 */
export function confirmTask(config: {
  name: string;
  message: string;
}): Task<never> {
  return {
    name: config.name,
    reads: [] as const,
    async run(env) {
      if (env.dryRun) return { success: true };

      const answer = await ask(`${config.message} [y/N] `);
      if (answer.toLowerCase().startsWith("y")) {
        return { success: true };
      }
      return { success: false, failureReason: "User declined" };
    },
  };
}

/**
 * Check whether the working tree has uncommitted changes.
 * Returns success if dirty (there are changes to commit),
 * failure if clean (nothing to do).
 */
export function diffCheckTask(): Task<"CodeEnv"> {
  return {
    name: "check-diffs",
    reads: [CodeEnv] as const,
    async run(env, resolve) {
      if (env.dryRun) return { success: true };

      const codeEnv = resolve(CodeEnv);
      const result = await gitRun(["status", "--porcelain"], {
        cwd: codeEnv.cwd,
      });

      if (result.kind === "err") {
        const msg =
          result.error.kind === "git-err"
            ? result.error.stderr
            : `timeout after ${String(result.error.timeout)}ms`;
        return { success: false, failureReason: `git status failed: ${msg}` };
      }

      if (result.stdout.trim().length === 0) {
        return { success: false, failureReason: "No changes detected" };
      }

      // Show the user what changed
      console.log("\nChanged files:");
      for (const line of result.stdout.trim().split("\n")) {
        console.log(`  ${line}`);
      }
      console.log();

      return { success: true };
    },
  };
}

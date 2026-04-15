/**
 * interactive-task.ts — spawn an interactive Claude session.
 *
 * Hands the terminal to the user. Resumes workflow after exit.
 */

import { spawnClaude } from "../../../../utils/exec/claude-code.js";
import { CodeEnv } from "../payloads.js";
import type { Task } from "../task.js";

export function interactiveClaudeTask(config: {
  name: string;
  prompt?: string;
}): Task<"CodeEnv"> {
  return {
    name: config.name,
    reads: [CodeEnv] as const,
    async run(env, resolve) {
      if (env.dryRun) return { success: true };

      const codeEnv = resolve(CodeEnv);
      const result = await spawnClaude(codeEnv.cwd, {
        prompt: config.prompt,
      });

      if (result.kind === "err") {
        return { success: false, failureReason: result.error.reason };
      }

      if (result.value !== 0) {
        return {
          success: false,
          failureReason: `claude exited with code ${String(result.value)}`,
        };
      }

      return { success: true };
    },
  };
}

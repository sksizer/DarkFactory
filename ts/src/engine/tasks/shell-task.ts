import { runShell } from "../../utils/exec/shell.js";
import { CodeEnv } from "../payloads.js";
import type { Task } from "../task.js";

export function shellTask(config: {
  name: string;
  cmd: string;
  onFailure: "fail" | "ignore";
  env?: Record<string, string> | undefined;
}): Task<"CodeEnv"> {
  return {
    name: config.name,
    reads: [CodeEnv] as const,
    async run(env, resolve) {
      const codeEnv = resolve(CodeEnv);
      if (env.dryRun) {
        return { success: true };
      }

      try {
        const result = await runShell(config.cmd, codeEnv.cwd, config.env);
        if (result.exitCode !== 0) {
          if (config.onFailure === "ignore") {
            return { success: true };
          }
          return {
            success: false,
            failureReason: `Shell command "${config.cmd}" exited with code ${String(result.exitCode)}: ${result.stderr.slice(0, 200)}`,
          };
        }
        return { success: true };
      } catch (e) {
        if (config.onFailure === "ignore") {
          return { success: true };
        }
        return {
          success: false,
          failureReason: `Shell command "${config.cmd}" failed: ${e instanceof Error ? e.message : String(e)}`,
        };
      }
    },
  };
}

import { match } from "ts-pattern";
import { CodeEnv, AgentResult } from "../payloads.js";
import type { Task } from "../task.js";
import { invokeClaude } from "../../utils/claude-code.js";

export function agentTask(config: {
  name: string;
  prompt: string;
  tools: string[];
  model?: string | undefined;
  sentinelSuccess?: string | undefined;
  sentinelFailure?: string | undefined;
}): Task<"CodeEnv", "AgentResult"> {
  return {
    name: config.name,
    reads: [CodeEnv] as const,
    writes: AgentResult,
    async run(env, resolve) {
      const codeEnv = resolve(CodeEnv);
      if (env.dryRun) {
        return {
          success: true,
          value: new AgentResult({
            stdout: `[dry-run] would invoke agent "${config.name}"`,
            stderr: "",
            exitCode: 0,
            success: true,
            toolCounts: {},
            model: config.model ?? "sonnet",
            invokeCount: 1,
          }),
        };
      }

      const result = await invokeClaude({
        cwd: codeEnv.cwd,
        prompt: config.prompt,
        tools: config.tools,
        model: config.model ?? "sonnet",
      });

      return match(result)
        .with({ kind: "ok" }, ({ value: inv }) => {
          const toolCounts: Record<string, number> = {};
          for (const [k, v] of inv.toolCounts) {
            toolCounts[k] = v;
          }

          const base = {
            stdout: inv.stdout,
            stderr: inv.stderr,
            exitCode: inv.exitCode,
            toolCounts,
            model: config.model ?? "sonnet",
            invokeCount: 1,
          };

          const hasSentinelConfig =
            config.sentinelSuccess !== undefined ||
            config.sentinelFailure !== undefined;

          if (hasSentinelConfig) {
            const failureMarker =
              config.sentinelFailure ?? "PRD_EXECUTE_FAILED";
            const successMarker =
              config.sentinelSuccess ?? "PRD_EXECUTE_OK";

            if (inv.stdout.includes(failureMarker)) {
              return {
                success: false,
                failureReason: "Failure sentinel found in agent output",
                value: new AgentResult({
                  ...base,
                  success: false,
                  failureReason: "Failure sentinel found in agent output",
                }),
              };
            }

            if (inv.stdout.includes(successMarker)) {
              return {
                success: true,
                value: new AgentResult({
                  ...base,
                  success: true,
                  sentinel: successMarker,
                }),
              };
            }
          }

          const ok = inv.exitCode === 0;
          return {
            success: ok,
            failureReason: ok
              ? undefined
              : `Agent exited with code ${String(inv.exitCode)}`,
            value: new AgentResult({
              ...base,
              success: ok,
              failureReason: ok
                ? undefined
                : `Agent exited with code ${String(inv.exitCode)}`,
            }),
          };
        })
        .with({ kind: "err" }, ({ error }) => ({
          success: false,
          failureReason: `Agent invocation failed: ${error.reason}`,
        }))
        .exhaustive();
    },
  };
}

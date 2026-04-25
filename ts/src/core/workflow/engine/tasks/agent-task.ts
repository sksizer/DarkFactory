import { match } from "ts-pattern";
import {
  type InvokeResult,
  invokeClaude,
} from "../../../../utils/exec/claude-code.js";
import { AgentResult, CodeEnv } from "../payloads.js";
import type { Task } from "../task.js";

function tailLines(text: string, n: number): string {
  const lines = text.trim().split("\n");
  return lines.slice(-n).join("\n");
}

function describeExitCode(
  exitCode: number,
  invFailureReason: string | undefined
): string {
  if (invFailureReason !== undefined && invFailureReason !== "") {
    return invFailureReason;
  }
  if (exitCode === -1) {
    return "claude process did not produce an exit code (likely timeout, signal, or spawn failure)";
  }
  return `claude exited with code ${String(exitCode)}`;
}

function enrichFailureReason(args: {
  primary: string;
  inv: InvokeResult;
}): string {
  const { primary, inv } = args;
  const parts: string[] = [primary];
  const stderrTail = tailLines(inv.stderr, 10);
  if (stderrTail !== "") {
    parts.push(`--- stderr ---\n${stderrTail}`);
  }
  // For unexpected failures (no sentinel found, non-zero exit), include a
  // tail of stdout to surface what the agent actually said before dying.
  const stdoutTail = tailLines(inv.stdout, 10);
  if (
    stdoutTail !== "" &&
    !primary.startsWith("Failure sentinel") &&
    inv.exitCode !== 0
  ) {
    parts.push(`--- stdout (last 10 lines) ---\n${stdoutTail}`);
  }
  return parts.join("\n");
}

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
            const successMarker = config.sentinelSuccess ?? "PRD_EXECUTE_OK";

            if (inv.stdout.includes(failureMarker)) {
              const reason = enrichFailureReason({
                primary: `Failure sentinel "${failureMarker}" found in agent output`,
                inv,
              });
              return {
                success: false,
                failureReason: reason,
                value: new AgentResult({
                  ...base,
                  success: false,
                  failureReason: reason,
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
          const failureReason = ok
            ? undefined
            : enrichFailureReason({
                primary: describeExitCode(inv.exitCode, inv.failureReason),
                inv,
              });
          return {
            success: ok,
            failureReason,
            value: new AgentResult({
              ...base,
              success: ok,
              failureReason,
            }),
          };
        })
        .with({ kind: "err" }, ({ error }) => ({
          success: false,
          failureReason: `Agent invocation failed (exit ${String(error.exitCode)}): ${error.reason}${
            error.stderr.trim() !== ""
              ? `\n--- stderr ---\n${tailLines(error.stderr, 10)}`
              : ""
          }`,
        }))
        .exhaustive();
    },
  };
}

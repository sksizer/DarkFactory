/**
 * claude-code.ts — Claude Code CLI invocation.
 *
 * Headless invocation (invokeClaude) and interactive invocation (spawnClaude).
 * All fallible operations return Result types — never throws.
 */

import { type Result, err, ok } from "../result.js";
import { ProcessTimeoutError, exec, execForeground } from "./subprocess.js";

// ---------- Types ----------

export type EffortLevel = "low" | "medium" | "high" | "max";

export interface InvokeOptions {
  readonly prompt: string;
  readonly tools: readonly string[];
  readonly model: string;
  readonly cwd: string;
  readonly sentinelSuccess?: string; // default: "PRD_EXECUTE_OK"
  readonly sentinelFailure?: string; // default: "PRD_EXECUTE_FAILED"
  readonly timeout?: number; // ms, default: 600_000
  readonly effortLevel?: EffortLevel;
  readonly dryRun?: boolean;
}

export interface InvokeResult {
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;
  readonly success: boolean;
  readonly failureReason?: string;
  readonly toolCounts: ReadonlyMap<string, number>;
  readonly sentinel?: string;
}

export interface InvokeErr {
  readonly kind: "invoke-err";
  readonly exitCode: number;
  readonly stderr: string;
  readonly reason: string;
}

// ---------- Capability -> model mapping ----------

const CAPABILITY_MODELS: Record<string, string> = {
  trivial: "haiku",
  simple: "sonnet",
  moderate: "sonnet",
  complex: "opus",
};

/**
 * Return the default model for a PRD capability tier.
 * Unknown capabilities fall back to "sonnet".
 */
export function capabilityToModel(capability: string): string {
  return CAPABILITY_MODELS[capability] ?? "sonnet";
}

// ---------- Sentinel parsing ----------

const _SENTINEL_SUCCESS_RE = /PRD_EXECUTE_OK:\s*(\S[^\n`]*)/;
const _SENTINEL_FAILURE_RE = /PRD_EXECUTE_FAILED:\s*(\S[^\n`]*)/;

/**
 * Scan stdout for sentinel lines. Returns success status and optional details.
 *
 * Precedence: failure beats success. If both sentinels appear, treat as failure.
 */
export function parseSentinels(
  stdout: string,
  success: string,
  failure: string
): { success: boolean; sentinel?: string; failureReason?: string } {
  // Pre-filter: remove darkfactory envelope lines to avoid false sentinel matches
  const filtered = stdout
    .split("\n")
    .filter((line) => {
      const stripped = line.trim();
      if (!stripped.startsWith("{")) return true;
      try {
        const parsed = JSON.parse(stripped) as { type?: string };
        if (
          typeof parsed.type === "string" &&
          parsed.type.startsWith("darkfactory_")
        ) {
          return false;
        }
      } catch {
        // Not JSON — keep the line
      }
      return true;
    })
    .join("\n");

  // Custom marker fast path
  if (success !== "PRD_EXECUTE_OK" || failure !== "PRD_EXECUTE_FAILED") {
    const failureHit = filtered.includes(`${failure}:`);
    const successHit = filtered.includes(`${success}:`);
    if (failureHit) {
      for (const line of filtered.split("\n")) {
        if (line.startsWith(`${failure}:`)) {
          const reason = line.slice(failure.length + 1).trim();
          return {
            success: false,
            failureReason: reason !== "" ? reason : "unspecified failure",
          };
        }
      }
      return { success: false, failureReason: "unspecified failure" };
    }
    if (successHit) {
      return { success: true };
    }
    return {
      success: false,
      failureReason: `agent output contained no ${success} or ${failure} sentinel`,
    };
  }

  // Default marker path: use precompiled regexes
  const failureMatch = _SENTINEL_FAILURE_RE.exec(filtered);
  if (failureMatch !== null) {
    const reason = failureMatch[1]?.trim();
    return reason !== undefined
      ? { success: false, failureReason: reason }
      : { success: false };
  }

  const successMatch = _SENTINEL_SUCCESS_RE.exec(filtered);
  if (successMatch !== null) {
    const sentinel = successMatch[1]?.trim();
    return sentinel !== undefined
      ? { success: true, sentinel }
      : { success: true };
  }

  return {
    success: false,
    failureReason:
      "agent output contained no PRD_EXECUTE_OK or PRD_EXECUTE_FAILED sentinel",
  };
}

// ---------- Tool count extraction ----------

function extractToolCounts(stdout: string): ReadonlyMap<string, number> {
  const counts = new Map<string, number>();
  for (const line of stdout.split("\n")) {
    const stripped = line.trim();
    if (!stripped.startsWith("{")) continue;
    try {
      const event = JSON.parse(stripped) as {
        type?: string;
        message?: { content?: Array<{ type?: string; name?: string }> };
      };
      if (event.type === "assistant") {
        const content = event.message?.content ?? [];
        for (const block of content) {
          if (block.type === "tool_use" && typeof block.name === "string") {
            counts.set(block.name, (counts.get(block.name) ?? 0) + 1);
          }
        }
      }
    } catch {
      // Not JSON — skip
    }
  }
  return counts;
}

// ---------- Invocation ----------

/**
 * Headless invocation — runs claude --print, parses sentinels.
 * Returns Result<InvokeResult, InvokeErr>.
 */
export async function invokeClaude(
  options: InvokeOptions
): Promise<Result<InvokeResult, InvokeErr>> {
  const sentinelSuccess = options.sentinelSuccess ?? "PRD_EXECUTE_OK";
  const sentinelFailure = options.sentinelFailure ?? "PRD_EXECUTE_FAILED";
  const timeoutMs = options.timeout ?? 600_000;

  if (options.dryRun === true) {
    const dryRunMsg = `[dry-run] would invoke claude with model=${options.model}, ${String(options.tools.length)} tools, prompt=${String(options.prompt.length)} chars${
      options.effortLevel !== undefined ? `, effort=${options.effortLevel}` : ""
    }`;
    return ok({
      stdout: dryRunMsg,
      stderr: "",
      exitCode: 0,
      success: true,
      toolCounts: new Map(),
    });
  }

  const cmd: string[] = [
    "claude",
    "--print",
    "--verbose",
    "--output-format",
    "stream-json",
    "--model",
    options.model,
    "--allowed-tools",
    options.tools.join(","),
    "--disallowed-tools",
    "Edit(../)",
    "--disallowed-tools",
    "Write(../)",
    "--disallowed-tools",
    "Read(../)",
  ];

  if (options.effortLevel !== undefined) {
    cmd.push("--effort", options.effortLevel);
  }

  try {
    const result = await exec(cmd, {
      cwd: options.cwd,
      stdin: options.prompt,
      timeout: timeoutMs,
    });

    const toolCounts = extractToolCounts(result.stdout);
    const parsed = parseSentinels(
      result.stdout,
      sentinelSuccess,
      sentinelFailure
    );

    let success = parsed.success;
    let failureReason = parsed.failureReason;

    // Non-zero exit overrides a success sentinel
    if (result.exitCode !== 0 && success) {
      success = false;
      failureReason = `claude exited non-zero (${String(result.exitCode)}) despite success sentinel; stderr: ${result.stderr.trim().slice(0, 200)}`;
    }

    const invokeResult: InvokeResult = {
      stdout: result.stdout,
      stderr: result.stderr,
      exitCode: result.exitCode,
      success,
      toolCounts,
      ...(failureReason !== undefined ? { failureReason } : {}),
      ...(parsed.sentinel !== undefined ? { sentinel: parsed.sentinel } : {}),
    };
    return ok(invokeResult);
  } catch (e) {
    if (e instanceof ProcessTimeoutError) {
      return ok({
        stdout: "",
        stderr: "",
        exitCode: -1,
        success: false,
        failureReason: `timeout after ${String(timeoutMs)}ms`,
        toolCounts: new Map(),
      });
    }
    return err({
      kind: "invoke-err",
      exitCode: -1,
      stderr: String(e),
      reason: `executable not found or spawn failed: ${String(e)}`,
    });
  }
}

/**
 * Interactive invocation — hands terminal to user.
 * Returns the exit code on success, InvokeErr on spawn failure.
 */
export async function spawnClaude(
  prompt: string,
  cwd: string,
  effortLevel?: EffortLevel
): Promise<Result<number, InvokeErr>> {
  const cmd: string[] = ["claude"];
  if (effortLevel !== undefined) {
    cmd.push("--effort", effortLevel);
  }
  // For interactive mode, we pass the prompt as a positional argument
  cmd.push(prompt);

  try {
    const exitCode = await execForeground(cmd, cwd);
    return ok(exitCode);
  } catch (e) {
    return err({
      kind: "invoke-err",
      exitCode: -1,
      stderr: String(e),
      reason: `spawn failed: ${String(e)}`,
    });
  }
}

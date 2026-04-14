/**
 * shell.ts — shell command execution helpers.
 *
 * Both functions delegate to utils/subprocess.ts.
 */

import { type Result, err, ok } from "./result.js";
import {
  type ExecErr,
  type ExecResult,
  execForeground,
  execShell,
} from "./subprocess.js";

export type { ExecResult };

/**
 * Run shell command string, capture output.
 */
export async function runShell(
  cmd: string,
  cwd: string,
  env?: Record<string, string>
): Promise<ExecResult> {
  return execShell(cmd, env !== undefined ? { cwd, env } : { cwd });
}

/**
 * Run command in foreground, stream to terminal.
 * Returns exit code on success, ExecErr on spawn failure.
 */
export async function runForeground(
  cmd: readonly string[],
  cwd?: string
): Promise<Result<number, ExecErr>> {
  try {
    const exitCode = await execForeground(cmd, cwd);
    return ok(exitCode);
  } catch (e) {
    const execErr: ExecErr = {
      kind: "exec-err",
      exitCode: -1,
      stderr: String(e),
      cmd,
    };
    return err(execErr);
  }
}

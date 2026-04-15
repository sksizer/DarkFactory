/**
 * subprocess.ts — single gateway for all process execution.
 *
 * Uses Bun-native APIs when available, falls back to node:child_process.
 * No caller outside this module may import child_process or use Bun.spawn.
 */

import * as childProcess from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

export interface ExecOptions {
  readonly cwd?: string;
  readonly env?: Record<string, string>;
  readonly stdin?: string;
  readonly timeout?: number; // milliseconds
}

export interface ExecResult {
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;
}

/** Error thrown by exec/execShell when a timeout is exceeded. */
export class ProcessTimeoutError extends Error {
  readonly cmd: readonly string[];
  readonly timeoutMs: number;

  constructor(cmd: readonly string[], timeoutMs: number) {
    super(`Command timed out after ${String(timeoutMs)}ms: ${cmd.join(" ")}`);
    this.name = "ProcessTimeoutError";
    this.cmd = cmd;
    this.timeoutMs = timeoutMs;
  }
}

/** Subprocess timeout. */
export interface Timeout {
  readonly kind: "timeout";
  readonly cmd: readonly string[];
  readonly timeout: number;
}

/** Error for exec-level failures (non-zero exit, spawn failure) used by shell.ts */
export interface ExecErr {
  readonly kind: "exec-err";
  readonly exitCode: number;
  readonly stderr: string;
  readonly cmd: readonly string[];
}

export const isBun = typeof globalThis.Bun !== "undefined";

// ---------- Bun-specific type helpers ----------

interface BunSpawnOptions {
  readonly cwd?: string | undefined;
  readonly env?: Record<string, string | undefined>;
  readonly stdin?: "pipe" | "inherit" | null | Uint8Array;
  readonly stdout: "pipe";
  readonly stderr: "pipe";
}

interface BunProcess {
  readonly stdout: ReadableStream<Uint8Array>;
  readonly stderr: ReadableStream<Uint8Array>;
  readonly exited: Promise<number>;
  kill(): void;
}

interface BunGlobal {
  spawn(cmd: readonly string[], opts: BunSpawnOptions): BunProcess;
  readableStreamToText(stream: ReadableStream<Uint8Array>): Promise<string>;
  which(name: string): string | null;
}

function getBun(): BunGlobal {
  return globalThis.Bun as BunGlobal;
}

// ---------- Bun implementation ----------

async function execBun(
  cmd: readonly string[],
  options?: ExecOptions
): Promise<ExecResult> {
  const bun = getBun();
  const stdinData =
    options?.stdin !== undefined ? Buffer.from(options.stdin) : null;

  const mergedEnv: Record<string, string | undefined> = {
    ...process.env,
    ...(options?.env ?? {}),
  };

  const proc = bun.spawn(cmd, {
    cwd: options?.cwd,
    env: mergedEnv,
    stdin: stdinData ?? null,
    stdout: "pipe",
    stderr: "pipe",
  });

  const state = { killed: false };
  let timeoutHandle: ReturnType<typeof setTimeout> | undefined;

  if (options?.timeout !== undefined) {
    const timeoutMs = options.timeout;
    timeoutHandle = setTimeout(() => {
      state.killed = true;
      proc.kill();
    }, timeoutMs);
  }

  const [stdout, stderr, exitCode] = await Promise.all([
    bun.readableStreamToText(proc.stdout),
    bun.readableStreamToText(proc.stderr),
    proc.exited,
  ]);

  if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);

  if (state.killed) {
    throw new ProcessTimeoutError(cmd, options?.timeout ?? 0);
  }

  return { stdout, stderr, exitCode };
}

// ---------- Node.js implementation ----------

async function execNode(
  cmd: readonly string[],
  options?: ExecOptions
): Promise<ExecResult> {
  const [file, ...args] = cmd as string[];
  if (file === undefined) {
    return { stdout: "", stderr: "empty command", exitCode: 1 };
  }

  const mergedEnv: NodeJS.ProcessEnv = {
    ...process.env,
    ...(options?.env ?? {}),
  };

  return new Promise<ExecResult>((resolve) => {
    let killed = false;

    const proc = childProcess.execFile(
      file,
      args,
      {
        cwd: options?.cwd,
        env: mergedEnv,
        timeout: options?.timeout,
        maxBuffer: 100 * 1024 * 1024, // 100 MB
      },
      (error, stdout, stderr) => {
        if (killed) {
          resolve({ stdout, stderr, exitCode: -1 });
          return;
        }
        const exitCode =
          error !== null && error.code !== undefined
            ? typeof error.code === "number"
              ? error.code
              : 1
            : 0;
        resolve({ stdout, stderr, exitCode });
      }
    );

    if (options?.stdin !== undefined) {
      proc.stdin?.write(options.stdin);
      proc.stdin?.end();
    }

    if (options?.timeout !== undefined) {
      const timeoutMs = options.timeout;
      proc.on("close", (code, signal) => {
        if (signal === "SIGTERM" || signal === "SIGKILL") {
          killed = true;
        }
      });
      setTimeout(() => {
        if (proc.exitCode === null) {
          killed = true;
          proc.kill();
          throw new ProcessTimeoutError(cmd, timeoutMs);
        }
      }, timeoutMs);
    }
  });
}

async function execShellNode(
  cmd: string,
  options?: ExecOptions
): Promise<ExecResult> {
  const mergedEnv: NodeJS.ProcessEnv = {
    ...process.env,
    ...(options?.env ?? {}),
  };

  return new Promise<ExecResult>((resolve) => {
    let killed = false;

    const proc = childProcess.exec(
      cmd,
      {
        cwd: options?.cwd,
        env: mergedEnv,
        timeout: options?.timeout,
        maxBuffer: 100 * 1024 * 1024,
      },
      (error, stdout, stderr) => {
        if (killed) {
          resolve({ stdout, stderr, exitCode: -1 });
          return;
        }
        const exitCode =
          error !== null && error.code !== undefined
            ? typeof error.code === "number"
              ? error.code
              : 1
            : 0;
        resolve({ stdout, stderr, exitCode });
      }
    );

    if (options?.stdin !== undefined) {
      proc.stdin?.write(options.stdin);
      proc.stdin?.end();
    }

    if (options?.timeout !== undefined) {
      const timeoutMs = options.timeout;
      setTimeout(() => {
        if (proc.exitCode === null) {
          killed = true;
          proc.kill();
          throw new ProcessTimeoutError([cmd], timeoutMs);
        }
      }, timeoutMs);
    }
  });
}

async function execShellBun(
  cmd: string,
  options?: ExecOptions
): Promise<ExecResult> {
  // For shell commands, spawn via sh -c
  return execBun(["sh", "-c", cmd], options);
}

// ---------- Public API ----------

/**
 * Run command as argv array — preferred for git/gh/claude calls.
 * Throws ProcessTimeoutError if timeout is exceeded.
 */
export async function exec(
  cmd: readonly string[],
  options?: ExecOptions
): Promise<ExecResult> {
  return isBun ? execBun(cmd, options) : execNode(cmd, options);
}

/**
 * Run shell command string — for user-defined shell tasks.
 * Throws ProcessTimeoutError if timeout is exceeded.
 */
export async function execShell(
  cmd: string,
  options?: ExecOptions
): Promise<ExecResult> {
  return isBun ? execShellBun(cmd, options) : execShellNode(cmd, options);
}

/**
 * Run command with stdio inherited (for interactive/foreground use).
 * Returns exit code.
 */
export async function execForeground(
  cmd: readonly string[],
  cwd?: string
): Promise<number> {
  if (isBun) {
    // Bun foreground: spawn with inherit stdio
    const bunForeground = globalThis.Bun as unknown as {
      spawn: (
        cmd: readonly string[],
        opts: {
          cwd?: string | undefined;
          stdin: "inherit";
          stdout: "inherit";
          stderr: "inherit";
        }
      ) => { exited: Promise<number> };
    };
    const proc = bunForeground.spawn(cmd, {
      cwd,
      stdin: "inherit",
      stdout: "inherit",
      stderr: "inherit",
    });
    return proc.exited;
  }

  // Node.js: spawn with stdio: "inherit"
  return new Promise<number>((resolve) => {
    const [file, ...args] = cmd as string[];
    if (file === undefined) {
      resolve(1);
      return;
    }
    const proc = childProcess.spawn(file, args, {
      cwd,
      stdio: "inherit",
    });
    proc.on("close", (code) => {
      resolve(code ?? 1);
    });
  });
}

/**
 * Check if an executable is on PATH. Returns the full path or null.
 * Synchronous — uses Bun.which in Bun, scans PATH in Node.
 */
export function which(name: string): string | null {
  if (isBun) {
    return getBun().which(name);
  }
  // Node.js: scan PATH directories
  const pathEnv = process.env.PATH ?? "";
  const pathDirs = pathEnv.split(path.delimiter).filter(Boolean);
  for (const dir of pathDirs) {
    const full = path.join(dir, name);
    try {
      fs.accessSync(full, fs.constants.X_OK);
      return full;
    } catch {
      // not found or not executable — try next
    }
  }
  return null;
}

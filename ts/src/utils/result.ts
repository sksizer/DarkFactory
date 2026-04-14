/**
 * Result types and helpers — foundation for all fallible operations.
 *
 * All fallible functions return Result<T, E> instead of throwing. Callers
 * use ts-pattern match().exhaustive() to handle every branch safely.
 */

// ---------- Core discriminated union ----------

export interface Ok<T> {
  readonly kind: "ok";
  readonly value: T;
  readonly stdout: string;
}

export interface Err<E> {
  readonly kind: "err";
  readonly error: E;
}

export type Result<T, E> = Ok<T> | Err<E>;

// ---------- Constructor helpers ----------

export function ok<T>(value: T, stdout?: string): Ok<T> {
  return { kind: "ok", value, stdout: stdout ?? "" };
}

export function err<E>(error: E): Err<E> {
  return { kind: "err", error };
}

// ---------- Type guards ----------

export function isOk<T, E>(result: Result<T, E>): result is Ok<T> {
  return result.kind === "ok";
}

export function isErr<T, E>(result: Result<T, E>): result is Err<E> {
  return result.kind === "err";
}

// ---------- Domain-specific error types ----------

/** Non-zero git CLI exit. */
export interface GitErr {
  readonly kind: "git-err";
  readonly returncode: number;
  readonly stdout: string;
  readonly stderr: string;
  readonly cmd: readonly string[];
}

/** Non-zero gh CLI exit. */
export interface GhErr {
  readonly kind: "gh-err";
  readonly returncode: number;
  readonly stdout: string;
  readonly stderr: string;
  readonly cmd: readonly string[];
}

/** Subprocess timeout. */
export interface Timeout {
  readonly kind: "timeout";
  readonly cmd: readonly string[];
  readonly timeout: number;
}

// ---------- Convenience type aliases ----------

export type GitResult<T> = Result<T, GitErr>;
export type GhResult<T> = Result<T, GhErr>;
export type CheckResult = Result<null, GitErr | Timeout>;
export type GhCheckResult = Result<null, GhErr | Timeout>;

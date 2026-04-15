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


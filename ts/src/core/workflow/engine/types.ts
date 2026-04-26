import type { PhaseState } from "./phase-state.js";
import type { Task } from "./task.js";

export interface TaskEnv {
  readonly dryRun: boolean;
}

export interface TaskOutput<T = unknown> {
  readonly success: boolean;
  readonly failureReason?: string | undefined;
  readonly value?: T | undefined;
}

export interface TaskStepResult {
  readonly name: string;
  readonly success: boolean;
  readonly failureReason?: string | undefined;
}

export interface RunResult {
  readonly success: boolean;
  readonly failureReason?: string | undefined;
  readonly steps: readonly TaskStepResult[];
}

export type InputMapping = Record<
  string,
  string | ((state: PhaseState) => string)
>;

export interface FailureHandler {
  /** Recovery task to run when the parent task fails. */
  readonly task: Task;
  /** Max times to run recovery + re-try the original task. */
  readonly retry: number;
  /**
   * Optional input mapping for the recovery task. Same semantics as
   * {@link WrappedTask.inputMapping}: lets the recovery read non-default
   * payload slots — e.g. an upstream task's named output, or the failing
   * parent's own named output. Without this, the recovery's `resolve(cls)`
   * only reads the `default` slot.
   */
  readonly inputMapping?: InputMapping | undefined;
  /**
   * Optional output id for the recovery's `writes`. Defaults to the
   * `default` slot, mirroring `.add()` vs `.named()` semantics for
   * normal tasks.
   */
  readonly outputId?: string | undefined;
}

export interface WrappedTask {
  readonly task: Task;
  readonly inputMapping?: InputMapping | undefined;
  readonly outputId?: string | undefined;
  readonly onFailure?: FailureHandler | undefined;
}

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
}

export interface WrappedTask {
  readonly task: Task;
  readonly inputMapping?: InputMapping | undefined;
  readonly outputId?: string | undefined;
  readonly onFailure?: FailureHandler | undefined;
}

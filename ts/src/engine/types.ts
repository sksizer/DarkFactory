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

export interface WrappedTask {
  readonly task: Task;
  readonly inputMapping?: InputMapping | undefined;
  readonly outputId?: string | undefined;
}

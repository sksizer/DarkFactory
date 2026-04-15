import type { WrappedTask } from "../engine/types.js";

export interface Workflow {
  readonly name: string;
  readonly description: string;
  readonly seeds: readonly unknown[];
  readonly tasks: readonly WrappedTask[];
}

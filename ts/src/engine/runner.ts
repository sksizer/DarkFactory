import { PhaseState } from "./phase-state.js";
import type { InputResolver, PayloadClass } from "./task.js";
import type {
  RunResult,
  TaskEnv,
  TaskOutput,
  TaskStepResult,
  WrappedTask,
} from "./types.js";

export interface Workflow {
  readonly name: string;
  readonly description: string;
  readonly seeds: readonly unknown[];
  readonly tasks: readonly WrappedTask[];
}

export async function runWorkflow(
  wf: Workflow,
  env: TaskEnv
): Promise<RunResult> {
  const state = new PhaseState();
  for (const seed of wf.seeds) {
    state.put(seed as object);
  }
  return runTasks(wf.tasks, state, env);
}

export async function runTasks(
  tasks: readonly WrappedTask[],
  state: PhaseState,
  env: TaskEnv
): Promise<RunResult> {
  const steps: TaskStepResult[] = [];

  for (const wrapped of tasks) {
    const resolve: InputResolver = <T>(
      cls: PayloadClass<T>,
      id?: string
    ): T => {
      if (id != null) return state.get(cls, id);
      const mapped = wrapped.inputMapping?.[cls.name];
      if (mapped != null) {
        const resolvedId =
          typeof mapped === "function" ? mapped(state) : mapped;
        return state.get(cls, resolvedId);
      }
      return state.get(cls);
    };

    let output: TaskOutput;
    try {
      output = await wrapped.task.run(env, resolve);
    } catch (e) {
      const failureReason = `Task "${wrapped.task.name}" threw: ${e instanceof Error ? e.message : String(e)}`;
      steps.push({ name: wrapped.task.name, success: false, failureReason });
      return { success: false, failureReason, steps };
    }

    steps.push({
      name: wrapped.task.name,
      success: output.success,
      failureReason: output.failureReason,
    });

    if (output.value != null && wrapped.task.writes != null) {
      state.put(output.value as object, wrapped.outputId ?? "default");
    }

    if (!output.success) {
      return { success: false, failureReason: output.failureReason, steps };
    }
  }

  return { success: true, steps };
}

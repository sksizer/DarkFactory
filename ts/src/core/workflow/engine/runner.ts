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

/**
 * Build the `resolve` function that a task receives as its second argument
 * for reading payloads out of the shared {@link PhaseState}.
 *
 * Resolution rules, in priority order:
 * 1. Explicit id passed at the call site (`resolve(Payload, "my-id")`) —
 *    looked up directly in state, bypassing any mapping.
 * 2. A per-task `inputMapping` entry keyed by the payload class name. The
 *    mapping value can be either a literal id string or a function that
 *    derives one from the current state (used when the id depends on
 *    runtime data).
 * 3. Default lookup with no id — returns the most recently written
 *    instance of that payload class.
 *
 * The resolver is created fresh for each task so its `wrapped` closure
 * carries that task's specific input mapping.
 */
function makeResolver(wrapped: WrappedTask, state: PhaseState): InputResolver {
  return <T>(cls: PayloadClass<T>, id?: string): T => {
    if (id != null) return state.get(cls, id);
    const mapped = wrapped.inputMapping?.[cls.name];
    if (mapped != null) {
      const resolvedId = typeof mapped === "function" ? mapped(state) : mapped;
      return state.get(cls, resolvedId);
    }
    return state.get(cls);
  };
}

async function executeTask(
  wrapped: WrappedTask,
  state: PhaseState,
  env: TaskEnv
): Promise<TaskOutput> {
  const resolve = makeResolver(wrapped, state);
  return wrapped.task.run(env, resolve);
}

export async function runTasks(
  tasks: readonly WrappedTask[],
  state: PhaseState,
  env: TaskEnv
): Promise<RunResult> {
  const steps: TaskStepResult[] = [];

  for (const wrapped of tasks) {
    let output: TaskOutput;
    try {
      output = await executeTask(wrapped, state, env);
    } catch (e) {
      const failureReason = `Task "${wrapped.task.name}" threw: ${e instanceof Error ? e.message : String(e)}`;
      steps.push({ name: wrapped.task.name, success: false, failureReason });
      return { success: false, failureReason, steps };
    }

    // Write output to state (even on failure — recovery tasks need it)
    if (output.value != null && wrapped.task.writes != null) {
      state.put(output.value as object, wrapped.outputId ?? "default");
    }

    if (!output.success && wrapped.onFailure !== undefined) {
      // Recovery loop: run recovery task, then re-try the original
      const handler = wrapped.onFailure;
      let recovered = false;

      for (let attempt = 0; attempt < handler.retry; attempt++) {
        steps.push({
          name: wrapped.task.name,
          success: false,
          failureReason: output.failureReason,
        });

        // Run recovery task
        const recoveryWrapped: WrappedTask = {
          task: handler.task,
          inputMapping: undefined,
          outputId: undefined,
        };

        let recoveryOutput: TaskOutput;
        try {
          recoveryOutput = await executeTask(recoveryWrapped, state, env);
        } catch (e) {
          const reason = `Recovery task "${handler.task.name}" threw: ${e instanceof Error ? e.message : String(e)}`;
          steps.push({
            name: handler.task.name,
            success: false,
            failureReason: reason,
          });
          return { success: false, failureReason: reason, steps };
        }

        steps.push({
          name: handler.task.name,
          success: recoveryOutput.success,
          failureReason: recoveryOutput.failureReason,
        });

        if (!recoveryOutput.success) {
          return {
            success: false,
            failureReason: `Recovery task "${handler.task.name}" failed: ${recoveryOutput.failureReason ?? "unknown"}`,
            steps,
          };
        }

        // Re-try the original task
        try {
          output = await executeTask(wrapped, state, env);
        } catch (e) {
          const reason = `Task "${wrapped.task.name}" threw on retry: ${e instanceof Error ? e.message : String(e)}`;
          steps.push({
            name: wrapped.task.name,
            success: false,
            failureReason: reason,
          });
          return { success: false, failureReason: reason, steps };
        }

        // Update state with new output
        if (output.value != null && wrapped.task.writes != null) {
          state.put(output.value as object, wrapped.outputId ?? "default");
        }

        if (output.success) {
          recovered = true;
          break;
        }
      }

      if (!recovered && !output.success) {
        steps.push({
          name: wrapped.task.name,
          success: false,
          failureReason: output.failureReason,
        });
        return {
          success: false,
          failureReason: `Task "${wrapped.task.name}" failed after ${String(handler.retry)} recovery attempts`,
          steps,
        };
      }
    }

    steps.push({
      name: wrapped.task.name,
      success: output.success,
      failureReason: output.failureReason,
    });

    if (!output.success) {
      return { success: false, failureReason: output.failureReason, steps };
    }
  }

  return { success: true, steps };
}

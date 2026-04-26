import { describe, expect, it } from "bun:test";
import { runWorkflow } from "./runner.js";
import type { InputResolver } from "./task.js";
import type { TaskEnv, TaskOutput } from "./types.js";

// ---------- Helpers ----------

class Counter {
  declare readonly _brand: "Counter";
  readonly count: number;
  constructor(count: number) {
    this.count = count;
  }
}

function succeedingTask(name: string) {
  return {
    name,
    reads: [] as const,
    run(): TaskOutput {
      return { success: true };
    },
  };
}

function failingTask(name: string, reason: string) {
  return {
    name,
    reads: [] as const,
    run(): TaskOutput {
      return { success: false, failureReason: reason };
    },
  };
}

const dryRunOff: TaskEnv = { dryRun: false };

// ---------- Tests ----------

describe("runWorkflow", () => {
  it("runs tasks in sequence and returns success", async () => {
    const result = await runWorkflow(
      {
        name: "test-wf",
        description: "test",
        seeds: [],
        tasks: [
          {
            task: succeedingTask("a"),
            inputMapping: undefined,
            outputId: undefined,
          },
          {
            task: succeedingTask("b"),
            inputMapping: undefined,
            outputId: undefined,
          },
        ],
      },
      dryRunOff
    );

    expect(result.success).toBe(true);
    expect(result.steps).toHaveLength(2);
  });

  it("stops on first failure without onFailure", async () => {
    const result = await runWorkflow(
      {
        name: "test-wf",
        description: "test",
        seeds: [],
        tasks: [
          {
            task: succeedingTask("a"),
            inputMapping: undefined,
            outputId: undefined,
          },
          {
            task: failingTask("b", "broke"),
            inputMapping: undefined,
            outputId: undefined,
          },
          {
            task: succeedingTask("c"),
            inputMapping: undefined,
            outputId: undefined,
          },
        ],
      },
      dryRunOff
    );

    expect(result.success).toBe(false);
    expect(result.steps).toHaveLength(2);
    expect(result.steps[1]?.failureReason).toBe("broke");
  });
});

describe("onFailure recovery", () => {
  it("recovers when recovery task fixes the issue", async () => {
    let callCount = 0;

    const flakyTask = {
      name: "flaky",
      reads: [] as const,
      run(): TaskOutput {
        callCount++;
        if (callCount === 1) {
          return { success: false, failureReason: "first attempt failed" };
        }
        return { success: true };
      },
    };

    const recoveryTask = {
      name: "fix-it",
      reads: [] as const,
      run(): TaskOutput {
        return { success: true };
      },
    };

    const result = await runWorkflow(
      {
        name: "test-wf",
        description: "test",
        seeds: [],
        tasks: [
          {
            task: flakyTask,
            inputMapping: undefined,
            outputId: undefined,
            onFailure: { task: recoveryTask, retry: 3 },
          },
          {
            task: succeedingTask("after"),
            inputMapping: undefined,
            outputId: undefined,
          },
        ],
      },
      dryRunOff
    );

    expect(result.success).toBe(true);
    expect(callCount).toBe(2);
    // Steps: flaky(fail), fix-it(ok), flaky(ok), after(ok)
    expect(result.steps).toHaveLength(4);
  });

  it("fails after exhausting retries", async () => {
    const alwaysFails = {
      name: "stubborn",
      reads: [] as const,
      run(): TaskOutput {
        return { success: false, failureReason: "still broken" };
      },
    };

    const recoveryTask = {
      name: "fix-it",
      reads: [] as const,
      run(): TaskOutput {
        return { success: true };
      },
    };

    const result = await runWorkflow(
      {
        name: "test-wf",
        description: "test",
        seeds: [],
        tasks: [
          {
            task: alwaysFails,
            inputMapping: undefined,
            outputId: undefined,
            onFailure: { task: recoveryTask, retry: 2 },
          },
        ],
      },
      dryRunOff
    );

    expect(result.success).toBe(false);
    expect(result.failureReason).toContain("after 2 recovery attempts");
  });

  it("fails immediately when recovery task itself fails", async () => {
    const result = await runWorkflow(
      {
        name: "test-wf",
        description: "test",
        seeds: [],
        tasks: [
          {
            task: failingTask("main", "main broke"),
            inputMapping: undefined,
            outputId: undefined,
            onFailure: {
              task: failingTask("recovery", "recovery broke"),
              retry: 3,
            },
          },
        ],
      },
      dryRunOff
    );

    expect(result.success).toBe(false);
    expect(result.failureReason).toContain("Recovery task");
    expect(result.failureReason).toContain("recovery broke");
  });

  it("writes recovery task's output value into state for downstream tasks", async () => {
    let downstreamSeenValue: number | undefined;
    let parentCalls = 0;

    // Flaky parent: fails first attempt, succeeds on retry. The retry
    // path is what lets the workflow continue to the downstream task.
    const flakyParent = {
      name: "flaky-parent",
      reads: [] as const,
      run(): TaskOutput {
        parentCalls++;
        return parentCalls === 1
          ? { success: false, failureReason: "first attempt" }
          : { success: true };
      },
    };

    // Recovery task declares it writes Counter — runner must persist it.
    const recoveryProducer = {
      name: "recovery",
      reads: [] as const,
      writes: Counter,
      run(): TaskOutput {
        return { success: true, value: new Counter(7) };
      },
    };

    const downstream = {
      name: "downstream",
      reads: [Counter] as const,
      run(_env: TaskEnv, resolve: InputResolver): TaskOutput {
        downstreamSeenValue = resolve(Counter).count;
        return { success: true };
      },
    };

    const result = await runWorkflow(
      {
        name: "test-wf",
        description: "test",
        seeds: [],
        tasks: [
          {
            task: flakyParent,
            inputMapping: undefined,
            outputId: undefined,
            onFailure: { task: recoveryProducer, retry: 1 },
          },
          {
            task: downstream,
            inputMapping: undefined,
            outputId: undefined,
          },
        ],
      },
      dryRunOff
    );

    expect(result.success).toBe(true);
    expect(downstreamSeenValue).toBe(7);
  });

  it("writes value to state on failure so recovery task can read it", async () => {
    let recoverySeenValue: number | undefined;

    const failWithValue = {
      name: "produce-and-fail",
      reads: [] as const,
      writes: Counter,
      run(): TaskOutput {
        return {
          success: false,
          failureReason: "check failed",
          value: new Counter(42),
        };
      },
    };

    const recoveryTask = {
      name: "read-and-fix",
      reads: [Counter] as const,
      run(_env: TaskEnv, resolve: InputResolver): TaskOutput {
        const counter = resolve(Counter);
        recoverySeenValue = counter.count;
        return { success: true };
      },
    };

    // Fail-with-value will always fail, but we verify state was written
    await runWorkflow(
      {
        name: "test-wf",
        description: "test",
        seeds: [],
        tasks: [
          {
            task: failWithValue,
            inputMapping: undefined,
            outputId: undefined,
            onFailure: { task: recoveryTask, retry: 1 },
          },
        ],
      },
      dryRunOff
    );

    expect(recoverySeenValue).toBe(42);
  });

  it("recovery uses FailureHandler.inputMapping to read named upstream outputs", async () => {
    let recoverySeenValue: number | undefined;

    // Upstream task writes Counter to Counter:upstream-id
    const upstream = {
      name: "upstream",
      reads: [] as const,
      writes: Counter,
      run(): TaskOutput {
        return { success: true, value: new Counter(99) };
      },
    };

    // Parent task fails — its recovery wants to read upstream's value, but
    // it lives at Counter:upstream-id, not Counter:default. Without
    // FailureHandler.inputMapping, recovery's resolve(Counter) would throw.
    const failingParent = failingTask("parent", "parent broke");

    const recoveryReader = {
      name: "recovery-reader",
      reads: [Counter] as const,
      run(_env: TaskEnv, resolve: InputResolver): TaskOutput {
        recoverySeenValue = resolve(Counter).count;
        return { success: true };
      },
    };

    await runWorkflow(
      {
        name: "test-wf",
        description: "test",
        seeds: [],
        tasks: [
          {
            task: upstream,
            inputMapping: undefined,
            outputId: "upstream-id",
          },
          {
            task: failingParent,
            inputMapping: undefined,
            outputId: undefined,
            onFailure: {
              task: recoveryReader,
              retry: 1,
              inputMapping: { Counter: "upstream-id" },
            },
          },
        ],
      },
      dryRunOff
    );

    expect(recoverySeenValue).toBe(99);
  });

  it("recovery's output lands at FailureHandler.outputId when set", async () => {
    let downstreamSeenValue: number | undefined;
    let parentCalls = 0;

    const flakyParent = {
      name: "flaky-parent",
      reads: [] as const,
      run(): TaskOutput {
        parentCalls++;
        return parentCalls === 1
          ? { success: false, failureReason: "first attempt" }
          : { success: true };
      },
    };

    const recoveryProducer = {
      name: "recovery",
      reads: [] as const,
      writes: Counter,
      run(): TaskOutput {
        return { success: true, value: new Counter(123) };
      },
    };

    // Downstream task explicitly reads Counter from "recovery-slot" via
    // its own inputMapping — proving the recovery wrote to that named slot.
    const downstream = {
      name: "downstream",
      reads: [Counter] as const,
      run(_env: TaskEnv, resolve: InputResolver): TaskOutput {
        downstreamSeenValue = resolve(Counter).count;
        return { success: true };
      },
    };

    const result = await runWorkflow(
      {
        name: "test-wf",
        description: "test",
        seeds: [],
        tasks: [
          {
            task: flakyParent,
            inputMapping: undefined,
            outputId: undefined,
            onFailure: {
              task: recoveryProducer,
              retry: 1,
              outputId: "recovery-slot",
            },
          },
          {
            task: downstream,
            inputMapping: { Counter: "recovery-slot" },
            outputId: undefined,
          },
        ],
      },
      dryRunOff
    );

    expect(result.success).toBe(true);
    expect(downstreamSeenValue).toBe(123);
  });
});

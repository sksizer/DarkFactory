import { describe, expect, it } from "bun:test";
import { runWorkflow, runTasks } from "./runner.js";
import { PhaseState } from "./phase-state.js";
import type { Task, PayloadClass, InputResolver } from "./task.js";
import type { TaskEnv, TaskOutput, WrappedTask } from "./types.js";

class TestPayloadA {
  declare readonly _brand: "TestPayloadA";
  readonly val: string;
  constructor(val: string) {
    this.val = val;
  }
}

class TestPayloadB {
  declare readonly _brand: "TestPayloadB";
  readonly num: number;
  constructor(num: number) {
    this.num = num;
  }
}

function mockTask(config: {
  name: string;
  reads: PayloadClass[];
  writes?: PayloadClass | undefined;
  result: TaskOutput;
}): Task {
  return {
    name: config.name,
    reads: config.reads,
    writes: config.writes,
    async run(_env: TaskEnv, resolve: InputResolver) {
      for (const cls of config.reads) {
        resolve(cls);
      }
      return config.result;
    },
  };
}

describe("runWorkflow", () => {
  it("seeds state and runs tasks", async () => {
    const task = mockTask({
      name: "step1",
      reads: [TestPayloadA],
      result: { success: true },
    });

    const wf = {
      name: "test-wf",
      description: "test",
      seeds: [new TestPayloadA("seeded")],
      tasks: [{ task, inputMapping: undefined, outputId: undefined }],
    };

    const result = await runWorkflow(wf, { dryRun: false });
    expect(result.success).toBe(true);
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0]?.name).toBe("step1");
    expect(result.steps[0]?.success).toBe(true);
  });
});

describe("runTasks", () => {
  it("stores task output in state via writes", async () => {
    const state = new PhaseState();
    state.put(new TestPayloadA("input"));

    const producerTask = mockTask({
      name: "producer",
      reads: [TestPayloadA],
      writes: TestPayloadB,
      result: { success: true, value: new TestPayloadB(42) },
    });

    const consumerTask = mockTask({
      name: "consumer",
      reads: [TestPayloadB],
      result: { success: true },
    });

    const tasks: WrappedTask[] = [
      { task: producerTask, inputMapping: undefined, outputId: undefined },
      { task: consumerTask, inputMapping: undefined, outputId: undefined },
    ];

    const result = await runTasks(tasks, state, { dryRun: false });
    expect(result.success).toBe(true);
    expect(result.steps).toHaveLength(2);
  });

  it("short-circuits on failure", async () => {
    const state = new PhaseState();
    state.put(new TestPayloadA("input"));

    const failTask = mockTask({
      name: "fail-step",
      reads: [TestPayloadA],
      result: { success: false, failureReason: "broken" },
    });

    const neverTask = mockTask({
      name: "never-reached",
      reads: [TestPayloadA],
      result: { success: true },
    });

    const tasks: WrappedTask[] = [
      { task: failTask, inputMapping: undefined, outputId: undefined },
      { task: neverTask, inputMapping: undefined, outputId: undefined },
    ];

    const result = await runTasks(tasks, state, { dryRun: false });
    expect(result.success).toBe(false);
    expect(result.failureReason).toBe("broken");
    expect(result.steps).toHaveLength(1);
  });

  it("records all step results", async () => {
    const state = new PhaseState();
    state.put(new TestPayloadA("input"));

    const task1 = mockTask({
      name: "step-1",
      reads: [TestPayloadA],
      result: { success: true },
    });

    const task2 = mockTask({
      name: "step-2",
      reads: [TestPayloadA],
      result: { success: true },
    });

    const tasks: WrappedTask[] = [
      { task: task1, inputMapping: undefined, outputId: undefined },
      { task: task2, inputMapping: undefined, outputId: undefined },
    ];

    const result = await runTasks(tasks, state, { dryRun: false });
    expect(result.steps).toHaveLength(2);
    expect(result.steps[0]?.name).toBe("step-1");
    expect(result.steps[1]?.name).toBe("step-2");
  });

  it("raises clear error on missing key", async () => {
    const state = new PhaseState();

    const task = mockTask({
      name: "needs-input",
      reads: [TestPayloadA],
      result: { success: true },
    });

    const tasks: WrappedTask[] = [
      { task, inputMapping: undefined, outputId: undefined },
    ];

    const result = await runTasks(tasks, state, { dryRun: false });
    expect(result.success).toBe(false);
    expect(result.failureReason).toContain("TestPayloadA");
    expect(result.failureReason).toContain("needs-input");
  });

  it("uses inputMapping for resolution", async () => {
    const state = new PhaseState();
    state.put(new TestPayloadA("default-val"));
    state.put(new TestPayloadA("mapped-val"), "special");

    let resolved = "";
    const task: Task = {
      name: "mapped-task",
      reads: [TestPayloadA],
      async run(_env, resolve) {
        const a = resolve(TestPayloadA);
        resolved = a.val;
        return { success: true };
      },
    };

    const tasks: WrappedTask[] = [
      {
        task,
        inputMapping: { TestPayloadA: "special" },
        outputId: undefined,
      },
    ];

    const result = await runTasks(tasks, state, { dryRun: false });
    expect(result.success).toBe(true);
    expect(resolved).toBe("mapped-val");
  });

  it("explicit id in resolve overrides inputMapping", async () => {
    const state = new PhaseState();
    state.put(new TestPayloadA("mapped"), "mapped-id");
    state.put(new TestPayloadA("explicit"), "explicit-id");

    let resolved = "";
    const task: Task = {
      name: "override-task",
      reads: [TestPayloadA],
      async run(_env, resolve) {
        const a = resolve(TestPayloadA, "explicit-id");
        resolved = a.val;
        return { success: true };
      },
    };

    const tasks: WrappedTask[] = [
      {
        task,
        inputMapping: { TestPayloadA: "mapped-id" },
        outputId: undefined,
      },
    ];

    const result = await runTasks(tasks, state, { dryRun: false });
    expect(result.success).toBe(true);
    expect(resolved).toBe("explicit");
  });

  it("stores output under named id", async () => {
    const state = new PhaseState();
    state.put(new TestPayloadA("input"));

    const producerTask = mockTask({
      name: "producer",
      reads: [TestPayloadA],
      writes: TestPayloadB,
      result: { success: true, value: new TestPayloadB(99) },
    });

    const tasks: WrappedTask[] = [
      { task: producerTask, inputMapping: undefined, outputId: "special" },
    ];

    await runTasks(tasks, state, { dryRun: false });
    expect(state.has(TestPayloadB, "special")).toBe(true);
    expect(state.get(TestPayloadB, "special").num).toBe(99);
  });

  it("dynamic inputMapping resolves at runtime", async () => {
    const state = new PhaseState();
    state.put(new TestPayloadA("a-val"), "a");
    state.put(new TestPayloadA("b-val"), "b");

    let resolved = "";
    const task: Task = {
      name: "dynamic-task",
      reads: [TestPayloadA],
      async run(_env, resolve) {
        const a = resolve(TestPayloadA);
        resolved = a.val;
        return { success: true };
      },
    };

    const tasks: WrappedTask[] = [
      {
        task,
        inputMapping: {
          TestPayloadA: (s) => (s.has(TestPayloadA, "b") ? "b" : "a"),
        },
        outputId: undefined,
      },
    ];

    const result = await runTasks(tasks, state, { dryRun: false });
    expect(result.success).toBe(true);
    expect(resolved).toBe("b-val");
  });
});

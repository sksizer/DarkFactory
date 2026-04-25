import { describe, expect, it } from "bun:test";
import { WorkflowBuilder, workflow } from "./builder.js";
import { AgentResult, CodeEnv, WorktreeState } from "./engine/payloads.js";
import type { PayloadClass, Task } from "./engine/task.js";

function fakeTask<R extends string, W extends string>(
  name: string,
  reads: PayloadClass[],
  writes?: PayloadClass
): Task<R, W> {
  return {
    name,
    reads,
    writes,
    run() {
      return { success: true };
    },
  } as Task<R, W>;
}

describe("WorkflowBuilder", () => {
  it("builds a workflow with name and description", () => {
    const wf = workflow("test", "A test").build();
    expect(wf.name).toBe("test");
    expect(wf.description).toBe("A test");
    expect(wf.seeds).toEqual([]);
    expect(wf.tasks).toEqual([]);
  });

  it("seeds populate the seeds array", () => {
    const env = new CodeEnv({ repoRoot: "/r", cwd: "/r" });
    const wf = workflow("test", "desc").seed(env).build();
    expect(wf.seeds).toHaveLength(1);
    expect(wf.seeds[0]).toBe(env);
  });

  it("add populates tasks", () => {
    const task = fakeTask<"CodeEnv", never>("t1", [CodeEnv]);
    const wf = workflow("test", "desc")
      .seed(new CodeEnv({ repoRoot: "/r", cwd: "/r" }))
      .add(task)
      .build();
    expect(wf.tasks).toHaveLength(1);
    expect(wf.tasks[0]?.task).toBe(task);
    expect(wf.tasks[0]?.inputMapping).toBeUndefined();
    expect(wf.tasks[0]?.outputId).toBeUndefined();
  });

  it("named sets outputId on task", () => {
    const task = fakeTask<"CodeEnv", "AgentResult">(
      "agent",
      [CodeEnv],
      AgentResult
    );
    const wf = workflow("test", "desc")
      .seed(new CodeEnv({ repoRoot: "/r", cwd: "/r" }))
      .named("scan", task)
      .build();
    expect(wf.tasks[0]?.outputId).toBe("scan");
  });

  it("from sets inputMapping on task", () => {
    const task = fakeTask<"CodeEnv", never>("mapped", [CodeEnv]);
    const mapping = { CodeEnv: "custom-id" };
    const wf = workflow("test", "desc")
      .seed(new CodeEnv({ repoRoot: "/r", cwd: "/r" }))
      .from(mapping, task)
      .build();
    expect(wf.tasks[0]?.inputMapping).toEqual(mapping);
  });

  it("chains seed and add correctly", () => {
    const env = new CodeEnv({ repoRoot: "/r", cwd: "/r" });
    const ws = new WorktreeState({ branch: "b", baseRef: "main" });
    const t1 = fakeTask<"CodeEnv", "WorktreeState">(
      "t1",
      [CodeEnv],
      WorktreeState
    );
    const t2 = fakeTask<"WorktreeState", never>("t2", [WorktreeState]);

    const wf = workflow("chain", "chained workflow")
      .seed(env)
      .seed(ws)
      .add(t1)
      .add(t2)
      .build();

    expect(wf.seeds).toHaveLength(2);
    expect(wf.tasks).toHaveLength(2);
  });

  it("workflow() is a convenience for new WorkflowBuilder()", () => {
    const wf = workflow("conv", "convenience");
    expect(wf).toBeInstanceOf(WorkflowBuilder);
    const built = wf.build();
    expect(built.name).toBe("conv");
  });
});

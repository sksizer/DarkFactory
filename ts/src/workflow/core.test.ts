import { describe, expect, it } from "bun:test";
import type { Workflow } from "./core.js";

describe("Workflow interface", () => {
  it("accepts a conforming plain object", () => {
    const wf: Workflow = {
      name: "test",
      description: "A test workflow",
      seeds: [{ value: 1 }],
      tasks: [
        {
          task: {
            name: "noop",
            reads: [],
            run() {
              return { success: true };
            },
          },
          inputMapping: undefined,
          outputId: undefined,
        },
      ],
    };
    expect(wf.name).toBe("test");
    expect(wf.description).toBe("A test workflow");
    expect(wf.seeds).toHaveLength(1);
    expect(wf.tasks).toHaveLength(1);
  });

  it("enforces readonly seeds and tasks arrays", () => {
    const wf: Workflow = {
      name: "ro",
      description: "readonly",
      seeds: [],
      tasks: [],
    };
    expect(wf.seeds).toEqual([]);
    expect(wf.tasks).toEqual([]);
  });
});

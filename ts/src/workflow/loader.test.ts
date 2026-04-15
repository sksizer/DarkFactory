import { describe, expect, it } from "bun:test";
import { discoverWorkflows } from "./loader.js";

describe("discoverWorkflows", () => {
  it("discovers built-in security-review workflow", async () => {
    const workflows = await discoverWorkflows();
    const names = workflows.map((w) => w.name);
    expect(names).toContain("security-review");
  });

  it("security-review has correct description", async () => {
    const workflows = await discoverWorkflows();
    const sr = workflows.find((w) => w.name === "security-review");
    expect(sr).toBeDefined();
    expect(sr?.description).toContain("security");
  });

  it("security-review resolve returns a valid workflow", async () => {
    const workflows = await discoverWorkflows();
    const sr = workflows.find((w) => w.name === "security-review");
    if (sr === undefined) throw new Error("security-review workflow not found");

    const wf = sr.resolve(process.cwd());
    expect(wf.name).toBe("security-review");
    expect(wf.tasks.length).toBeGreaterThan(0);
    expect(wf.seeds.length).toBeGreaterThan(0);
  });

  it("handles nonexistent project directory gracefully", async () => {
    const workflows = await discoverWorkflows("/nonexistent/path/to/workflows");
    expect(workflows.length).toBeGreaterThanOrEqual(1);
  });

  it("reports builtin source", async () => {
    const workflows = await discoverWorkflows();
    const sr = workflows.find((w) => w.name === "security-review");
    expect(sr?.source).toBe("builtin");
  });
});

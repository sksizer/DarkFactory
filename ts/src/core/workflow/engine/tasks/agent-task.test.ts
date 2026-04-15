import { describe, expect, it } from "bun:test";
import { AgentResult, CodeEnv } from "../payloads.js";
import type { InputResolver } from "../task.js";
import { agentTask } from "./agent-task.js";

function makeResolver(codeEnv: CodeEnv): InputResolver {
  return <T>(cls: new (...args: unknown[]) => T): T => {
    if (cls === CodeEnv) return codeEnv as unknown as T;
    throw new Error(`Unexpected resolve for ${cls.name}`);
  };
}

describe("agentTask", () => {
  it("returns task with correct name, reads, writes", () => {
    const task = agentTask({
      name: "test-agent",
      prompt: "do stuff",
      tools: ["Read"],
    });
    expect(task.name).toBe("test-agent");
    expect(task.reads).toEqual([CodeEnv]);
    expect(task.writes).toBe(AgentResult);
  });

  it("dry-run returns success with AgentResult", async () => {
    const task = agentTask({
      name: "dry-agent",
      prompt: "test",
      tools: ["Read"],
      model: "opus",
    });

    const codeEnv = new CodeEnv({ repoRoot: "/repo", cwd: "/repo" });
    const result = await task.run({ dryRun: true }, makeResolver(codeEnv));

    expect(result.success).toBe(true);
    expect(result.value).toBeInstanceOf(AgentResult);
    const ar = result.value as AgentResult;
    expect(ar.model).toBe("opus");
    expect(ar.invokeCount).toBe(1);
    expect(ar.success).toBe(true);
    expect(ar.stdout).toContain("[dry-run]");
  });

  it("defaults model to sonnet", async () => {
    const task = agentTask({
      name: "default-model",
      prompt: "test",
      tools: [],
    });

    const codeEnv = new CodeEnv({ repoRoot: "/repo", cwd: "/repo" });
    const result = await task.run({ dryRun: true }, makeResolver(codeEnv));
    const ar = result.value as AgentResult;
    expect(ar.model).toBe("sonnet");
  });

  it("uses configured sentinel markers in name", () => {
    const task = agentTask({
      name: "sentinel-agent",
      prompt: "test",
      tools: [],
      sentinelSuccess: "CUSTOM_OK",
      sentinelFailure: "CUSTOM_FAIL",
    });
    expect(task.name).toBe("sentinel-agent");
  });
});

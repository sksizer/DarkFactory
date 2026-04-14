import { describe, expect, it } from "bun:test";
import { shellTask } from "./shell-task.js";
import { CodeEnv } from "../payloads.js";
import type { InputResolver } from "../task.js";

function makeResolver(codeEnv: CodeEnv): InputResolver {
  return <T>(cls: new (...args: unknown[]) => T): T => {
    if (cls === CodeEnv) return codeEnv as unknown as T;
    throw new Error(`Unexpected resolve for ${cls.name}`);
  };
}

describe("shellTask", () => {
  it("returns task with correct name and reads", () => {
    const task = shellTask({
      name: "lint",
      cmd: "npm run lint",
      onFailure: "fail",
    });
    expect(task.name).toBe("lint");
    expect(task.reads).toEqual([CodeEnv]);
    expect(task.writes).toBeUndefined();
  });

  it("dry-run returns success without running command", async () => {
    const task = shellTask({
      name: "test",
      cmd: "exit 1",
      onFailure: "fail",
    });

    const codeEnv = new CodeEnv({ repoRoot: "/repo", cwd: "/repo" });
    const result = await task.run({ dryRun: true }, makeResolver(codeEnv));
    expect(result.success).toBe(true);
  });

  it("succeeds on exit code 0", async () => {
    const task = shellTask({
      name: "echo",
      cmd: "echo hello",
      onFailure: "fail",
    });

    const codeEnv = new CodeEnv({ repoRoot: process.cwd(), cwd: process.cwd() });
    const result = await task.run({ dryRun: false }, makeResolver(codeEnv));
    expect(result.success).toBe(true);
  });

  it("fails on non-zero exit when onFailure is fail", async () => {
    const task = shellTask({
      name: "bad-cmd",
      cmd: "exit 1",
      onFailure: "fail",
    });

    const codeEnv = new CodeEnv({ repoRoot: process.cwd(), cwd: process.cwd() });
    const result = await task.run({ dryRun: false }, makeResolver(codeEnv));
    expect(result.success).toBe(false);
    expect(result.failureReason).toContain("exit 1");
  });

  it("succeeds on non-zero exit when onFailure is ignore", async () => {
    const task = shellTask({
      name: "ignored-fail",
      cmd: "exit 1",
      onFailure: "ignore",
    });

    const codeEnv = new CodeEnv({ repoRoot: process.cwd(), cwd: process.cwd() });
    const result = await task.run({ dryRun: false }, makeResolver(codeEnv));
    expect(result.success).toBe(true);
  });
});

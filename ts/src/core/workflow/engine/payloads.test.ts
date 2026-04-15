import { describe, expect, it } from "bun:test";
import {
  AgentResult,
  CodeEnv,
  PrRequest,
  PrResult,
  WorktreeState,
} from "./payloads.js";
import { PhaseState } from "./phase-state.js";

describe("CodeEnv", () => {
  it("constructs with required fields", () => {
    const env = new CodeEnv({ repoRoot: "/repo", cwd: "/repo/sub" });
    expect(env.repoRoot).toBe("/repo");
    expect(env.cwd).toBe("/repo/sub");
  });

  it("round-trips through PhaseState", () => {
    const state = new PhaseState();
    const env = new CodeEnv({ repoRoot: "/r", cwd: "/r" });
    state.put(env);
    const retrieved = state.get(CodeEnv);
    expect(retrieved.repoRoot).toBe("/r");
    expect(retrieved.cwd).toBe("/r");
  });
});

describe("WorktreeState", () => {
  it("constructs with required fields", () => {
    const ws = new WorktreeState({ branch: "feat/x", baseRef: "main" });
    expect(ws.branch).toBe("feat/x");
    expect(ws.baseRef).toBe("main");
    expect(ws.worktreePath).toBeUndefined();
  });

  it("constructs with optional worktreePath", () => {
    const ws = new WorktreeState({
      branch: "feat/x",
      baseRef: "main",
      worktreePath: "/tmp/wt",
    });
    expect(ws.worktreePath).toBe("/tmp/wt");
  });

  it("round-trips through PhaseState", () => {
    const state = new PhaseState();
    state.put(new WorktreeState({ branch: "b", baseRef: "main" }));
    expect(state.get(WorktreeState).branch).toBe("b");
  });
});

describe("PrRequest", () => {
  it("constructs with title and body", () => {
    const pr = new PrRequest({ title: "Fix", body: "Details" });
    expect(pr.title).toBe("Fix");
    expect(pr.body).toBe("Details");
  });
});

describe("PrResult", () => {
  it("constructs with url", () => {
    const pr = new PrResult({ url: "https://github.com/pr/1" });
    expect(pr.url).toBe("https://github.com/pr/1");
  });

  it("constructs without url", () => {
    const pr = new PrResult({});
    expect(pr.url).toBeUndefined();
  });
});

describe("AgentResult", () => {
  it("constructs with all fields", () => {
    const ar = new AgentResult({
      stdout: "output",
      stderr: "err",
      exitCode: 0,
      success: true,
      toolCounts: { Read: 5, Write: 2 },
      model: "sonnet",
      invokeCount: 1,
    });
    expect(ar.stdout).toBe("output");
    expect(ar.stderr).toBe("err");
    expect(ar.exitCode).toBe(0);
    expect(ar.success).toBe(true);
    expect(ar.toolCounts).toEqual({ Read: 5, Write: 2 });
    expect(ar.model).toBe("sonnet");
    expect(ar.invokeCount).toBe(1);
    expect(ar.failureReason).toBeUndefined();
    expect(ar.sentinel).toBeUndefined();
  });

  it("constructs with optional fields", () => {
    const ar = new AgentResult({
      stdout: "",
      stderr: "",
      exitCode: 1,
      success: false,
      failureReason: "bad",
      toolCounts: {},
      sentinel: "PRD_EXECUTE_FAILED",
      model: "opus",
      invokeCount: 2,
    });
    expect(ar.failureReason).toBe("bad");
    expect(ar.sentinel).toBe("PRD_EXECUTE_FAILED");
  });

  it("round-trips through PhaseState", () => {
    const state = new PhaseState();
    const ar = new AgentResult({
      stdout: "ok",
      stderr: "",
      exitCode: 0,
      success: true,
      toolCounts: {},
      model: "sonnet",
      invokeCount: 1,
    });
    state.put(ar);
    expect(state.get(AgentResult).stdout).toBe("ok");
  });
});

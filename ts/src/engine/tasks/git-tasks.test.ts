import { describe, expect, it } from "bun:test";
import {
  createWorktree,
  enterWorktree,
  commitTask,
  pushBranch,
  createPr,
} from "./git-tasks.js";
import {
  CodeEnv,
  WorktreeState,
  PrRequest,
  PrResult,
} from "../payloads.js";
import type { InputResolver } from "../task.js";
import { PhaseState } from "../phase-state.js";

function makeResolver(state: PhaseState): InputResolver {
  return <T>(cls: new (...args: unknown[]) => T, id?: string): T => {
    return state.get(cls as new (...args: unknown[]) => T, id);
  };
}

describe("createWorktree", () => {
  it("has correct reads and writes", () => {
    const task = createWorktree();
    expect(task.name).toBe("create-worktree");
    expect(task.reads).toEqual([WorktreeState, CodeEnv]);
    expect(task.writes).toBe(WorktreeState);
  });

  it("dry-run returns WorktreeState with worktreePath", async () => {
    const state = new PhaseState();
    state.put(new CodeEnv({ repoRoot: "/repo", cwd: "/repo" }));
    state.put(new WorktreeState({ branch: "feat/x", baseRef: "main" }));

    const task = createWorktree();
    const result = await task.run({ dryRun: true }, makeResolver(state));
    expect(result.success).toBe(true);
    expect(result.value).toBeInstanceOf(WorktreeState);
    const ws = result.value as WorktreeState;
    expect(ws.branch).toBe("feat/x");
    expect(ws.baseRef).toBe("main");
    expect(ws.worktreePath).toContain("feat-x");
  });
});

describe("enterWorktree", () => {
  it("has correct reads and writes", () => {
    const task = enterWorktree();
    expect(task.name).toBe("enter-worktree");
    expect(task.reads).toEqual([WorktreeState]);
    expect(task.writes).toBe(CodeEnv);
  });

  it("dry-run returns CodeEnv", async () => {
    const state = new PhaseState();
    state.put(new WorktreeState({ branch: "b", baseRef: "main", worktreePath: "/tmp/wt" }));

    const task = enterWorktree();
    const result = await task.run({ dryRun: true }, makeResolver(state));
    expect(result.success).toBe(true);
    expect(result.value).toBeInstanceOf(CodeEnv);
    const env = result.value as CodeEnv;
    expect(env.cwd).toBe("/tmp/wt");
  });

  it("fails when worktreePath is undefined (non-dry-run)", async () => {
    const state = new PhaseState();
    state.put(new WorktreeState({ branch: "b", baseRef: "main" }));

    const task = enterWorktree();
    const result = await task.run({ dryRun: false }, makeResolver(state));
    expect(result.success).toBe(false);
    expect(result.failureReason).toContain("worktreePath");
  });
});

describe("commitTask", () => {
  it("has correct name and reads", () => {
    const task = commitTask({ message: "test commit" });
    expect(task.name).toBe("commit");
    expect(task.reads).toEqual([CodeEnv]);
    expect(task.writes).toBeUndefined();
  });

  it("dry-run returns success", async () => {
    const state = new PhaseState();
    state.put(new CodeEnv({ repoRoot: "/repo", cwd: "/repo" }));

    const task = commitTask({ message: "test" });
    const result = await task.run({ dryRun: true }, makeResolver(state));
    expect(result.success).toBe(true);
  });

  it("accepts custom files list", () => {
    const task = commitTask({ message: "test", files: ["a.ts", "b.ts"] });
    expect(task.name).toBe("commit");
  });
});

describe("pushBranch", () => {
  it("has correct reads", () => {
    const task = pushBranch();
    expect(task.name).toBe("push-branch");
    expect(task.reads).toEqual([WorktreeState]);
    expect(task.writes).toBeUndefined();
  });

  it("dry-run returns success", async () => {
    const state = new PhaseState();
    state.put(new WorktreeState({ branch: "b", baseRef: "main" }));

    const task = pushBranch();
    const result = await task.run({ dryRun: true }, makeResolver(state));
    expect(result.success).toBe(true);
  });
});

describe("createPr", () => {
  it("has correct reads and writes", () => {
    const task = createPr();
    expect(task.name).toBe("create-pr");
    expect(task.reads).toEqual([PrRequest, WorktreeState]);
    expect(task.writes).toBe(PrResult);
  });

  it("dry-run returns PrResult with placeholder url", async () => {
    const state = new PhaseState();
    state.put(new PrRequest({ title: "PR", body: "body" }));
    state.put(new WorktreeState({ branch: "b", baseRef: "main" }));

    const task = createPr();
    const result = await task.run({ dryRun: true }, makeResolver(state));
    expect(result.success).toBe(true);
    expect(result.value).toBeInstanceOf(PrResult);
    const pr = result.value as PrResult;
    expect(pr.url).toContain("dry-run");
  });
});

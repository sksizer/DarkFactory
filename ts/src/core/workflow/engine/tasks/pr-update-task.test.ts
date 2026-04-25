import { describe, expect, it } from "bun:test";
import { CodeEnv, OpenPrList, PrUpdateSummary } from "../payloads.js";
import { PhaseState } from "../phase-state.js";
import type { InputResolver } from "../task.js";
import { listOpenPrsForUpdate, updateOpenPrs } from "./pr-update-task.js";

function makeResolver(state: PhaseState): InputResolver {
  return <T>(cls: new (...args: unknown[]) => T, id?: string): T => {
    return state.get(cls as new (...args: unknown[]) => T, id);
  };
}

describe("listOpenPrsForUpdate", () => {
  it("has correct name, reads, writes", () => {
    const task = listOpenPrsForUpdate();
    expect(task.name).toBe("list-open-prs");
    expect(task.reads).toEqual([CodeEnv]);
    expect(task.writes).toBe(OpenPrList);
  });

  it("accepts overridden name", () => {
    const task = listOpenPrsForUpdate({ name: "discover" });
    expect(task.name).toBe("discover");
  });

  it("dry-run returns empty OpenPrList without calling gh", async () => {
    const state = new PhaseState();
    state.put(new CodeEnv({ repoRoot: "/repo", cwd: "/repo" }));

    const task = listOpenPrsForUpdate();
    const result = await task.run({ dryRun: true }, makeResolver(state));
    expect(result.success).toBe(true);
    expect(result.value).toBeInstanceOf(OpenPrList);
    expect((result.value as OpenPrList).prs).toEqual([]);
  });
});

describe("updateOpenPrs", () => {
  it("has correct name, reads, writes", () => {
    const task = updateOpenPrs({ conflictPrompt: "resolve it" });
    expect(task.name).toBe("update-open-prs");
    expect(task.reads).toEqual([CodeEnv, OpenPrList]);
    expect(task.writes).toBe(PrUpdateSummary);
  });

  it("accepts overridden name", () => {
    const task = updateOpenPrs({
      name: "bring-up-to-date",
      conflictPrompt: "x",
    });
    expect(task.name).toBe("bring-up-to-date");
  });

  it("dry-run marks every PR as skipped without touching git", async () => {
    const state = new PhaseState();
    state.put(new CodeEnv({ repoRoot: "/repo", cwd: "/repo" }));
    state.put(
      new OpenPrList({
        prs: [
          {
            number: 1,
            headRefName: "feat/a",
            baseRefName: "main",
            title: "A",
            isDraft: false,
          },
          {
            number: 2,
            headRefName: "feat/b",
            baseRefName: "main",
            title: "B",
            isDraft: false,
          },
        ],
      })
    );

    const task = updateOpenPrs({ conflictPrompt: "resolve" });
    const result = await task.run({ dryRun: true }, makeResolver(state));
    expect(result.success).toBe(true);
    expect(result.value).toBeInstanceOf(PrUpdateSummary);
    const summary = result.value as PrUpdateSummary;
    expect(summary.entries).toHaveLength(2);
    expect(summary.entries[0]?.outcome.kind).toBe("skipped");
    expect(summary.entries[1]?.outcome.kind).toBe("skipped");
  });

  it("dry-run with empty PR list returns empty summary", async () => {
    const state = new PhaseState();
    state.put(new CodeEnv({ repoRoot: "/repo", cwd: "/repo" }));
    state.put(new OpenPrList({ prs: [] }));

    const task = updateOpenPrs({ conflictPrompt: "x" });
    const result = await task.run({ dryRun: true }, makeResolver(state));
    expect(result.success).toBe(true);
    expect((result.value as PrUpdateSummary).entries).toEqual([]);
  });
});

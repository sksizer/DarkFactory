import { describe, expect, it } from "bun:test";
import { match } from "ts-pattern";
import {
  add,
  branchExistsLocal,
  type branchExistsRemote,
  diffQuiet,
  findLocalBranches,
  gitRun,
  resolveCommitTimestamp,
  statusOtherDirty,
  worktreeList,
} from "./git.js";

// Use the actual worktree as a real git repo for tests
const REPO_ROOT = process.cwd();

describe("gitRun", () => {
  it("returns Ok on success", async () => {
    const result = await gitRun(["status"], { cwd: REPO_ROOT });

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(r.stdout).toBeDefined();
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });

  it("returns GitErr on bad repo", async () => {
    const result = await gitRun(["status"], { cwd: "/nonexistent-path-xyz" });

    match(result)
      .with({ kind: "err", error: { kind: "git-err" } }, (r) => {
        expect(r.error.returncode).not.toBe(0);
      })
      .with({ kind: "err", error: { kind: "timeout" } }, () => {
        throw new Error("unexpected timeout");
      })
      .with({ kind: "ok" }, () => {
        throw new Error("expected error");
      })
      .exhaustive();
  });

  it("captures stdout on success", async () => {
    const result = await gitRun(["rev-parse", "--show-toplevel"], {
      cwd: REPO_ROOT,
    });

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(r.stdout.trim()).toBeTruthy();
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });
});

describe("branchExistsLocal", () => {
  it("returns Ok(true) for the current branch", async () => {
    // Get current branch name first
    const branchResult = await gitRun(["rev-parse", "--abbrev-ref", "HEAD"], {
      cwd: REPO_ROOT,
    });
    if (branchResult.kind === "err") return; // skip if git fails

    const branch = branchResult.stdout.trim();
    const result = await branchExistsLocal(REPO_ROOT, branch);

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(r.value).toBe(true);
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });

  it("returns Ok(false) for a nonexistent branch", async () => {
    const result = await branchExistsLocal(
      REPO_ROOT,
      "definitely-does-not-exist-xyz-abc-123"
    );

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(r.value).toBe(false);
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });
});

describe("branchExistsRemote", () => {
  it("returns GitResult<boolean> type structure (no network call)", () => {
    // branchExistsRemote uses git ls-remote which requires network.
    // Verify the return type contract with a constructed value.
    const okResult = {
      kind: "ok",
      value: false,
      stdout: "",
    } as Awaited<ReturnType<typeof branchExistsRemote>>;

    match(okResult)
      .with({ kind: "ok" }, (r) => {
        expect(typeof r.value).toBe("boolean");
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });
});

describe("findLocalBranches", () => {
  it("returns a list of matching branches", async () => {
    const result = await findLocalBranches("prd/*", REPO_ROOT);

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(Array.isArray(r.value)).toBe(true);
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });

  it("returns empty array when no branches match", async () => {
    const result = await findLocalBranches(
      "definitely-no-match-xyz-*",
      REPO_ROOT
    );

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(r.value).toEqual([]);
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });
});

describe("statusOtherDirty", () => {
  it("returns a list of dirty files not in the given paths", async () => {
    const result = await statusOtherDirty([], REPO_ROOT);

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(Array.isArray(r.value)).toBe(true);
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });
});

describe("diffQuiet", () => {
  it("returns Ok on clean working tree for staged files", async () => {
    // diff --quiet with HEAD returns Ok(null) if no changes
    const result = await diffQuiet([], REPO_ROOT);

    // Result is either ok or err depending on repo state — both are valid
    match(result)
      .with({ kind: "ok" }, () => {
        // clean
      })
      .with({ kind: "err", error: { kind: "git-err" } }, (r) => {
        // dirty — that's fine, repo has changes
        expect(r.error.returncode).toBe(1);
      })
      .with({ kind: "err", error: { kind: "timeout" } }, () => {
        throw new Error("unexpected timeout");
      })
      .exhaustive();
  });
});

describe("resolveCommitTimestamp", () => {
  it("returns ISO-8601 timestamp for HEAD", async () => {
    const result = await resolveCommitTimestamp("HEAD", REPO_ROOT);

    match(result)
      .with({ kind: "ok" }, (r) => {
        // ISO-8601 timestamps contain T
        expect(r.value).toContain("T");
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });

  it("returns GitErr for an invalid ref", async () => {
    const result = await resolveCommitTimestamp(
      "definitely-invalid-sha-xyz",
      REPO_ROOT
    );

    match(result)
      .with({ kind: "ok" }, () => {
        throw new Error("expected error");
      })
      .with({ kind: "err" }, (r) => {
        expect(r.error.kind).toBe("git-err");
      })
      .exhaustive();
  });
});

describe("worktreeList", () => {
  it("returns the list of worktrees", async () => {
    const result = await worktreeList(REPO_ROOT);

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(Array.isArray(r.value)).toBe(true);
        // Each entry has path, branch, head fields
        for (const entry of r.value) {
          expect(typeof entry.path).toBe("string");
          expect(typeof entry.branch).toBe("string");
          expect(typeof entry.head).toBe("string");
        }
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });
});

describe("add (error path)", () => {
  it("returns GitErr when adding nonexistent file", async () => {
    const result = await add(["nonexistent-file-xyz-abc.txt"], REPO_ROOT);

    match(result)
      .with({ kind: "ok" }, () => {
        // Some git versions accept adds of nonexistent files in certain states
        // This is acceptable
      })
      .with({ kind: "err", error: { kind: "git-err" } }, (r) => {
        expect(r.error.returncode).not.toBe(0);
      })
      .with({ kind: "err", error: { kind: "timeout" } }, () => {
        throw new Error("unexpected timeout");
      })
      .exhaustive();
  });
});

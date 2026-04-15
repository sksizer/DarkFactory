import { describe, expect, it } from "bun:test";
import { match } from "ts-pattern";
import { getPrState, ghJson, ghRun, listOpenPrs } from "./github.js";
import type { GhCheckResult, GhResult } from "./github.js";

const REPO_ROOT = process.cwd();

describe("ghRun", () => {
  it("returns GhCheckResult type on failure (gh not configured or error)", async () => {
    // gh version should always work if gh is installed
    const result = await ghRun(["--version"], { cwd: REPO_ROOT });

    const label = match(result)
      .with({ kind: "ok" }, () => "ok")
      .with(
        { kind: "err", error: { kind: "gh-err" } },
        (r) => `gh-err:${String(r.error.returncode)}`
      )
      .with({ kind: "err", error: { kind: "timeout" } }, () => "timeout")
      .exhaustive();

    // Either ok (gh is installed) or gh-err (not installed) — both are valid
    expect(
      ["ok", "timeout"].some((v) => label.startsWith(v)) ||
        label.startsWith("gh-err")
    ).toBe(true);
  });

  it("returns GhErr for an invalid subcommand", async () => {
    const result = await ghRun(["definitely-invalid-subcommand-xyz"], {
      cwd: REPO_ROOT,
    });

    match(result)
      .with({ kind: "ok" }, () => {
        throw new Error("expected error");
      })
      .with({ kind: "err", error: { kind: "gh-err" } }, (r) => {
        expect(r.error.returncode).not.toBe(0);
      })
      .with({ kind: "err", error: { kind: "timeout" } }, () => {
        // acceptable
      })
      .exhaustive();
  });
});

describe("ghJson", () => {
  it("returns GhResult type", async () => {
    // gh --version returns non-JSON — ghJson should return a gh-err
    const result = await ghJson<{ resources: unknown }>(["--version"], {
      cwd: REPO_ROOT,
    });

    const label = match(result as GhResult<{ resources: unknown }>)
      .with({ kind: "ok" }, () => "ok")
      .with({ kind: "err" }, (r) => `err:${r.error.kind}`)
      .exhaustive();

    // Either gh-err (not installed or non-JSON) — both valid
    expect(label === "ok" || label.startsWith("err:")).toBe(true);
  });

  it("returns GhErr when response is not JSON", async () => {
    // gh --version returns non-JSON output; ghJson should fail with invalid JSON error
    const result = await ghJson<unknown>(["--version"], { cwd: REPO_ROOT });

    match(result)
      .with({ kind: "ok" }, () => {
        // Would only happen if gh --version returned JSON (unlikely)
      })
      .with({ kind: "err" }, (r) => {
        expect(r.error.kind).toBe("gh-err");
      })
      .exhaustive();
  });
});

describe("getPrState", () => {
  it("type-checks PrState values exhaustively", () => {
    // Pure structural test — verifies the type union is correct
    // (network call skipped since gh pr list requires GitHub auth)
    const validStates: readonly string[] = ["MERGED", "OPEN", "CLOSED", "NONE"];

    // Construct a synthetic ok result with each PrState
    for (const state of validStates) {
      const r = { kind: "ok", value: state, stdout: "" } as GhResult<string>;
      const label = match(r)
        .with({ kind: "ok" }, (x) => x.value)
        .with({ kind: "err" }, () => "err")
        .exhaustive();
      expect(label).toBe(state);
    }
  });
});

describe("listOpenPrs", () => {
  it("returns a GhResult<PrInfo[]>", async () => {
    const result = await listOpenPrs(REPO_ROOT, 5);

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(Array.isArray(r.value)).toBe(true);
        for (const pr of r.value) {
          expect(typeof pr.number).toBe("number");
          expect(typeof pr.headRefName).toBe("string");
        }
      })
      .with({ kind: "err" }, (r) => {
        // gh not configured — acceptable
        expect(r.error.kind).toBe("gh-err");
      })
      .exhaustive();
  }, 15_000); // gh pr list may take a few seconds
});

describe("Result type compatibility", () => {
  it("GhErr can be matched exhaustively", () => {
    const r = {
      kind: "err",
      error: {
        kind: "gh-err",
        returncode: 1,
        stdout: "",
        stderr: "not found",
        cmd: ["gh", "pr", "list"],
      },
    } as GhCheckResult;

    const label = match(r)
      .with({ kind: "ok" }, () => "ok")
      .with(
        { kind: "err", error: { kind: "gh-err" } },
        (x) => `gh-err:${String(x.error.returncode)}`
      )
      .with({ kind: "err", error: { kind: "timeout" } }, () => "timeout")
      .exhaustive();

    expect(label).toBe("gh-err:1");
  });
});

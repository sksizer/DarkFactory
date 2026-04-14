import { describe, expect, it } from "bun:test";
import { match } from "ts-pattern";
import {
  type CheckResult,
  type GhCheckResult,
  type GitResult,
  type Result,
  err,
  isErr,
  isOk,
  ok,
} from "./result.js";

describe("ok / err constructors", () => {
  it("ok sets kind=ok, value, and stdout", () => {
    const r = ok(42, "some output");
    expect(r.kind).toBe("ok");
    expect(r.value).toBe(42);
    expect(r.stdout).toBe("some output");
  });

  it("ok defaults stdout to empty string", () => {
    const r = ok("hello");
    expect(r.stdout).toBe("");
  });

  it("err sets kind=err and error", () => {
    const r = err({
      kind: "git-err" as const,
      returncode: 1,
      stdout: "",
      stderr: "oops",
      cmd: [],
    });
    expect(r.kind).toBe("err");
    expect(r.error.returncode).toBe(1);
  });
});

describe("isOk / isErr type guards", () => {
  it("isOk returns true for Ok", () => {
    const r: Result<number, string> = ok(1);
    expect(isOk(r)).toBe(true);
    expect(isErr(r)).toBe(false);
  });

  it("isErr returns true for Err", () => {
    const r: Result<number, string> = err("boom");
    expect(isErr(r)).toBe(true);
    expect(isOk(r)).toBe(false);
  });
});

describe("ts-pattern exhaustive matching on Result", () => {
  it("matches Ok branch", () => {
    const result = ok("output", "stdout text") as Result<
      string,
      { kind: "git-err" }
    >;

    const message = match(result)
      .with({ kind: "ok" }, (r) => `clean: ${r.stdout}`)
      .with({ kind: "err" }, () => "error")
      .exhaustive();

    expect(message).toBe("clean: stdout text");
  });

  it("matches Err branch", () => {
    const result = err({
      kind: "git-err" as const,
      returncode: 128,
    }) as Result<string, { kind: "git-err"; returncode: number }>;

    const message = match(result)
      .with({ kind: "ok" }, () => "ok")
      .with({ kind: "err" }, (r) => `failed: ${String(r.error.returncode)}`)
      .exhaustive();

    expect(message).toBe("failed: 128");
  });

  it("matches GitErr vs Timeout in CheckResult", () => {
    const gitErrResult = err({
      kind: "git-err" as const,
      returncode: 1,
      stdout: "",
      stderr: "not a repo",
      cmd: ["git", "status"],
    }) as CheckResult;

    const label = match(gitErrResult)
      .with({ kind: "ok" }, () => "ok")
      .with(
        { kind: "err", error: { kind: "git-err" } },
        (r) => `git-err:${String(r.error.returncode)}`
      )
      .with({ kind: "err", error: { kind: "timeout" } }, () => "timeout")
      .exhaustive();

    expect(label).toBe("git-err:1");

    const timeoutResult = err({
      kind: "timeout" as const,
      cmd: ["git", "fetch"],
      timeout: 5000,
    }) as CheckResult;

    const label2 = match(timeoutResult)
      .with({ kind: "ok" }, () => "ok")
      .with({ kind: "err", error: { kind: "git-err" } }, () => "git-err")
      .with(
        { kind: "err", error: { kind: "timeout" } },
        (r) => `timeout:${String(r.error.timeout)}`
      )
      .exhaustive();

    expect(label2).toBe("timeout:5000");
  });

  it("matches GhErr vs Timeout in GhCheckResult", () => {
    const ghErrResult = err({
      kind: "gh-err" as const,
      returncode: 1,
      stdout: "",
      stderr: "gh: not found",
      cmd: ["gh", "pr", "list"],
    }) as GhCheckResult;

    const label = match(ghErrResult)
      .with({ kind: "ok" }, () => "ok")
      .with(
        { kind: "err", error: { kind: "gh-err" } },
        (r) => `gh-err:${String(r.error.returncode)}`
      )
      .with({ kind: "err", error: { kind: "timeout" } }, () => "timeout")
      .exhaustive();

    expect(label).toBe("gh-err:1");
  });

  it("matches GitResult<boolean>", () => {
    const r = ok(true, "") as GitResult<boolean>;

    const msg = match(r)
      .with({ kind: "ok" }, (result) => `exists:${String(result.value)}`)
      .with({ kind: "err" }, () => "error")
      .exhaustive();

    expect(msg).toBe("exists:true");
  });
});

describe("domain error types", () => {
  it("GitErr has required fields", () => {
    const e = err({
      kind: "git-err" as const,
      returncode: 128,
      stdout: "out",
      stderr: "err",
      cmd: ["git", "status"] as readonly string[],
    });
    expect(e.error.kind).toBe("git-err");
    expect(e.error.cmd).toEqual(["git", "status"]);
  });

  it("GhErr has required fields", () => {
    const e = err({
      kind: "gh-err" as const,
      returncode: 1,
      stdout: "",
      stderr: "unauthorized",
      cmd: ["gh", "pr", "list"] as readonly string[],
    });
    expect(e.error.kind).toBe("gh-err");
  });

  it("Timeout has required fields", () => {
    const e = err({
      kind: "timeout" as const,
      cmd: ["git", "fetch"] as readonly string[],
      timeout: 10000,
    });
    expect(e.error.kind).toBe("timeout");
    expect(e.error.timeout).toBe(10000);
  });
});

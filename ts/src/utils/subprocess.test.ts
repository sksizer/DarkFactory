import { describe, expect, it } from "bun:test";
import { match } from "ts-pattern";
import {
  type ExecResult,
  ProcessTimeoutError,
  exec,
  execShell,
  isBun,
} from "./subprocess.js";

describe("exec", () => {
  it("runs a simple command and returns stdout", async () => {
    const result = await exec(["echo", "hello"]);

    const message = match(result)
      .when(
        (r) => r.exitCode === 0,
        (r) => `ok:${r.stdout.trim()}`
      )
      .otherwise((r) => `fail:${String(r.exitCode)}`);

    expect(message).toBe("ok:hello");
    expect(result.exitCode).toBe(0);
    expect(result.stdout.trim()).toBe("hello");
  });

  it("returns non-zero exitCode on failure", async () => {
    const result = await exec(["false"]);

    expect(result.exitCode).not.toBe(0);
  });

  it("passes cwd option", async () => {
    const result = await exec(["pwd"], { cwd: "/tmp" });

    expect(result.exitCode).toBe(0);
    // On macOS /tmp is a symlink to /private/tmp — check containment
    expect(result.stdout.trim()).toContain("tmp");
  });

  it("passes env option", async () => {
    const result = await exec(["sh", "-c", "echo $MY_VAR"], {
      env: { MY_VAR: "test-value" },
    });

    expect(result.stdout.trim()).toBe("test-value");
  });

  it("pipes stdin to process", async () => {
    const result = await exec(["cat"], { stdin: "hello stdin" });

    expect(result.stdout).toBe("hello stdin");
  });

  it("throws ProcessTimeoutError when timeout is exceeded", async () => {
    let threw = false;
    try {
      await exec(["sleep", "10"], { timeout: 50 });
    } catch (e) {
      if (e instanceof ProcessTimeoutError) {
        threw = true;
        expect(e.timeoutMs).toBe(50);
      }
    }
    expect(threw).toBe(true);
  });

  it("captures stderr", async () => {
    const result = await exec(["sh", "-c", "echo error >&2; exit 1"]);

    expect(result.exitCode).not.toBe(0);
    expect(result.stderr.trim()).toBe("error");
  });
});

describe("execShell", () => {
  it("runs a shell command string", async () => {
    const result = await execShell("echo hello from shell");

    const label = match(result)
      .when(
        (r) => r.exitCode === 0,
        (r) => r.stdout.trim()
      )
      .otherwise(() => "failed");

    expect(label).toBe("hello from shell");
  });

  it("supports shell features (pipes)", async () => {
    const result = await execShell("echo foo | tr a-z A-Z");

    expect(result.exitCode).toBe(0);
    expect(result.stdout.trim()).toBe("FOO");
  });

  it("returns non-zero on shell command failure", async () => {
    const result = await execShell("exit 42");

    expect(result.exitCode).not.toBe(0);
  });
});

describe("runtime detection", () => {
  it("isBun reflects the runtime", () => {
    // In Bun test runner this should be true; in Node false
    // Either is valid — just verify it's a boolean
    expect(typeof isBun).toBe("boolean");
  });
});

describe("ProcessTimeoutError", () => {
  it("has the correct name and fields", () => {
    const e = new ProcessTimeoutError(["git", "fetch"], 5000);
    expect(e.name).toBe("ProcessTimeoutError");
    expect(e.cmd).toEqual(["git", "fetch"]);
    expect(e.timeoutMs).toBe(5000);
    expect(e.message).toContain("5000ms");
  });
});

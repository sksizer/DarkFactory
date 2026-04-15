import { describe, expect, it } from "bun:test";
import { match } from "ts-pattern";
import type { Result } from "../result.js";
import { runForeground, runShell } from "./shell.js";
import type { ExecErr } from "./subprocess.js";

describe("runShell", () => {
  it("runs a shell command and captures output", async () => {
    const result = await runShell("echo hello from runShell", process.cwd());

    const label = match(result)
      .when(
        (r) => r.exitCode === 0,
        (r) => r.stdout.trim()
      )
      .otherwise(() => "failed");

    expect(label).toBe("hello from runShell");
    expect(result.exitCode).toBe(0);
  });

  it("passes env variables to shell", async () => {
    const result = await runShell("echo $TEST_VAR", process.cwd(), {
      TEST_VAR: "injected-value",
    });

    expect(result.exitCode).toBe(0);
    expect(result.stdout.trim()).toBe("injected-value");
  });

  it("supports shell pipes and substitution", async () => {
    const result = await runShell("echo foobar | tr a-z A-Z", process.cwd());

    expect(result.exitCode).toBe(0);
    expect(result.stdout.trim()).toBe("FOOBAR");
  });

  it("returns non-zero exitCode on failure", async () => {
    const result = await runShell("exit 2", process.cwd());

    expect(result.exitCode).not.toBe(0);
  });
});

describe("runForeground", () => {
  it("returns exit code as Result<number, ExecErr>", async () => {
    const result = await runForeground(["true"]);

    const label = match(result)
      .with({ kind: "ok" }, (r) => `exit:${String(r.value)}`)
      .with({ kind: "err" }, (r) => `err:${r.error.kind}`)
      .exhaustive();

    expect(label).toBe("exit:0");
  });

  it("returns non-zero exit code for failing command", async () => {
    const result = await runForeground(["false"]);

    match(result)
      .with({ kind: "ok" }, (r) => {
        expect(r.value).not.toBe(0);
      })
      .with({ kind: "err" }, () => {
        // spawn error — acceptable
      })
      .exhaustive();
  });

  it("returns ExecErr for spawn failure", async () => {
    const result = await runForeground([
      "definitely-nonexistent-command-xyz-abc",
    ]);

    match(result)
      .with({ kind: "ok" }, (r) => {
        // Some systems return a non-zero exit code instead of throwing
        expect(r.value).not.toBe(0);
      })
      .with({ kind: "err" }, (r) => {
        expect(r.error.kind).toBe("exec-err");
      })
      .exhaustive();
  });
});

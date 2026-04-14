import { describe, expect, it } from "bun:test";
import { match } from "ts-pattern";
import { type Result } from "./result.js";
import {
  type InvokeErr,
  type InvokeResult,
  capabilityToModel,
  invokeClaude,
  parseSentinels,
} from "./claude-code.js";

describe("capabilityToModel", () => {
  it("maps trivial to haiku", () => {
    expect(capabilityToModel("trivial")).toBe("haiku");
  });

  it("maps simple to sonnet", () => {
    expect(capabilityToModel("simple")).toBe("sonnet");
  });

  it("maps moderate to sonnet", () => {
    expect(capabilityToModel("moderate")).toBe("sonnet");
  });

  it("maps complex to opus", () => {
    expect(capabilityToModel("complex")).toBe("opus");
  });

  it("maps unknown capability to sonnet fallback", () => {
    expect(capabilityToModel("unknown-tier")).toBe("sonnet");
  });
});

describe("parseSentinels", () => {
  it("returns success=true when PRD_EXECUTE_OK is present", () => {
    const result = parseSentinels("PRD_EXECUTE_OK: PRD-123", "PRD_EXECUTE_OK", "PRD_EXECUTE_FAILED");
    expect(result.success).toBe(true);
    expect(result.sentinel).toBe("PRD-123");
  });

  it("returns success=false when PRD_EXECUTE_FAILED is present", () => {
    const result = parseSentinels(
      "PRD_EXECUTE_FAILED: something went wrong",
      "PRD_EXECUTE_OK",
      "PRD_EXECUTE_FAILED",
    );
    expect(result.success).toBe(false);
    expect(result.failureReason).toBe("something went wrong");
  });

  it("failure beats success when both sentinels appear", () => {
    const stdout = "PRD_EXECUTE_OK: PRD-123\nPRD_EXECUTE_FAILED: oops";
    const result = parseSentinels(stdout, "PRD_EXECUTE_OK", "PRD_EXECUTE_FAILED");
    expect(result.success).toBe(false);
  });

  it("returns success=false when neither sentinel is present", () => {
    const result = parseSentinels("no sentinel here", "PRD_EXECUTE_OK", "PRD_EXECUTE_FAILED");
    expect(result.success).toBe(false);
    expect(result.failureReason).toContain("no PRD_EXECUTE_OK");
  });

  it("handles custom sentinel markers", () => {
    const result = parseSentinels("TASK_DONE: task-1", "TASK_DONE", "TASK_FAILED");
    expect(result.success).toBe(true);
  });

  it("handles custom failure marker", () => {
    const result = parseSentinels("TASK_FAILED: bad stuff", "TASK_DONE", "TASK_FAILED");
    expect(result.success).toBe(false);
    expect(result.failureReason).toBe("bad stuff");
  });

  it("filters out darkfactory envelope lines", () => {
    const stdout = [
      '{"type":"darkfactory_stderr","text":"PRD_EXECUTE_FAILED: injected"}',
      "PRD_EXECUTE_OK: PRD-123",
    ].join("\n");
    const result = parseSentinels(stdout, "PRD_EXECUTE_OK", "PRD_EXECUTE_FAILED");
    // The darkfactory_ envelope line should be filtered; only OK sentinel remains
    expect(result.success).toBe(true);
  });

  it("handles sentinel in markdown formatting (backticks)", () => {
    const result = parseSentinels(
      "`PRD_EXECUTE_OK: PRD-456`",
      "PRD_EXECUTE_OK",
      "PRD_EXECUTE_FAILED",
    );
    // The regex is anchorless, should still find it inside backticks
    expect(result.success).toBe(true);
  });
});

describe("invokeClaude dry-run", () => {
  it("returns success result without running claude", async () => {
    const result = await invokeClaude({
      prompt: "hello",
      tools: ["Read", "Write"],
      model: "sonnet",
      cwd: process.cwd(),
      dryRun: true,
    });

    const label = match(result as Result<InvokeResult, InvokeErr>)
      .with({ kind: "ok" }, (r) => {
        expect(r.value.success).toBe(true);
        expect(r.value.stdout).toContain("dry-run");
        expect(r.value.stdout).toContain("sonnet");
        return "ok";
      })
      .with({ kind: "err" }, () => "err")
      .exhaustive();

    expect(label).toBe("ok");
  });

  it("includes tool count in dry-run output description", async () => {
    const result = await invokeClaude({
      prompt: "test",
      tools: ["Read", "Write", "Bash"],
      model: "haiku",
      cwd: process.cwd(),
      dryRun: true,
    });

    match(result as Result<InvokeResult, InvokeErr>)
      .with({ kind: "ok" }, (r) => {
        expect(r.value.stdout).toContain("3 tools");
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });

  it("includes effort level in dry-run output when provided", async () => {
    const result = await invokeClaude({
      prompt: "test",
      tools: ["Read"],
      model: "opus",
      cwd: process.cwd(),
      dryRun: true,
      effortLevel: "high",
    });

    match(result as Result<InvokeResult, InvokeErr>)
      .with({ kind: "ok" }, (r) => {
        expect(r.value.stdout).toContain("high");
      })
      .with({ kind: "err" }, () => {
        throw new Error("expected ok");
      })
      .exhaustive();
  });
});

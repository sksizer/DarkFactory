import { describe, expect, it, spyOn, mock } from "bun:test";
import { main } from "./index.js";

describe("CLI", () => {
  it("list-workflows prints available workflows", async () => {
    const logs: string[] = [];
    const spy = spyOn(console, "log").mockImplementation((...args: unknown[]) => {
      logs.push(args.map(String).join(" "));
    });

    await main(["list-workflows"]);
    spy.mockRestore();

    const output = logs.join("\n");
    expect(output).toContain("Available workflows:");
    expect(output).toContain("security-review");
  });

  it("run with unknown workflow prints error", async () => {
    const errors: string[] = [];
    const errSpy = spyOn(console, "error").mockImplementation(
      (...args: unknown[]) => {
        errors.push(args.map(String).join(" "));
      }
    );
    const exitSpy = spyOn(process, "exit").mockImplementation(
      (_code?: number) => {
        throw new Error("process.exit called");
      }
    );

    try {
      await main(["run", "nonexistent-workflow"]);
    } catch {
      // expected — process.exit throws
    }

    errSpy.mockRestore();
    exitSpy.mockRestore();

    const output = errors.join("\n");
    expect(output).toContain("unknown workflow");
    expect(output).toContain("nonexistent-workflow");
  });

  it("run with --dry-run exercises pipeline", async () => {
    const logs: string[] = [];
    const logSpy = spyOn(console, "log").mockImplementation(
      (...args: unknown[]) => {
        logs.push(args.map(String).join(" "));
      }
    );
    const errSpy = spyOn(console, "error").mockImplementation(() => {});

    const exitSpy = spyOn(process, "exit").mockImplementation(
      (_code?: number) => {
        throw new Error("process.exit called");
      }
    );

    try {
      await main(["run", "security-review", "--dry-run"]);
    } catch {
      // may exit on failure — that's ok for this test
    }

    logSpy.mockRestore();
    errSpy.mockRestore();
    exitSpy.mockRestore();

    const output = logs.join("\n");
    expect(output).toContain("security-review");
    expect(output).toContain("dry-run");
  });

  it("missing run argument prints usage", async () => {
    const errors: string[] = [];
    const errSpy = spyOn(console, "error").mockImplementation(
      (...args: unknown[]) => {
        errors.push(args.map(String).join(" "));
      }
    );
    const exitSpy = spyOn(process, "exit").mockImplementation(
      (_code?: number) => {
        throw new Error("process.exit called");
      }
    );

    try {
      await main(["run"]);
    } catch {
      // expected
    }

    errSpy.mockRestore();
    exitSpy.mockRestore();

    expect(errors.join("\n")).toContain("Usage");
  });

  it("unknown command prints error", async () => {
    const errors: string[] = [];
    const errSpy = spyOn(console, "error").mockImplementation(
      (...args: unknown[]) => {
        errors.push(args.map(String).join(" "));
      }
    );
    const exitSpy = spyOn(process, "exit").mockImplementation(
      (_code?: number) => {
        throw new Error("process.exit called");
      }
    );

    try {
      await main(["bogus"]);
    } catch {
      // expected
    }

    errSpy.mockRestore();
    exitSpy.mockRestore();

    expect(errors.join("\n")).toContain("Unknown command");
  });
});

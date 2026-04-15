import { describe, expect, it, spyOn } from "bun:test";
import { buildProgram, main } from "./index.js";

function silentProgram() {
  return buildProgram()
    .exitOverride()
    .configureOutput({
      writeOut: () => {},
      writeErr: () => {},
    });
}

describe("CLI", () => {
  it("workflow list prints available workflows", async () => {
    const logs: string[] = [];
    const spy = spyOn(console, "log").mockImplementation(
      (...args: unknown[]) => {
        logs.push(args.map(String).join(" "));
      }
    );

    const code = await main(["workflow", "list"]);
    spy.mockRestore();

    expect(code).toBe(0);
    const output = logs.join("\n");
    expect(output).toContain("Available workflows:");
    expect(output).toContain("security-review");
  });

  it("workflow run with unknown workflow returns non-zero", async () => {
    const errSpy = spyOn(console, "error").mockImplementation(() => {});

    const code = await main(["workflow", "run", "nonexistent-workflow"]);
    errSpy.mockRestore();

    expect(code).toBe(1);
  });

  it("workflow run with --dry-run exercises pipeline", async () => {
    const logs: string[] = [];
    const logSpy = spyOn(console, "log").mockImplementation(
      (...args: unknown[]) => {
        logs.push(args.map(String).join(" "));
      }
    );
    const errSpy = spyOn(console, "error").mockImplementation(() => {});

    const code = await main(["workflow", "run", "security-review", "--dry-run"]);

    logSpy.mockRestore();
    errSpy.mockRestore();

    // Workflow may fail (no real worktree), but the CLI should still run
    const output = logs.join("\n");
    expect(output).toContain("security-review");
    expect(output).toContain("dry-run");
  });

  it("--help exits via commander", async () => {
    const program = silentProgram();
    let threw = false;
    try {
      await program.parseAsync(["--help"], { from: "user" });
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
  });
});

import { describe, expect, it, spyOn } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CliError } from "../error.js";
import { resolveCwdOption, splitRunArgs } from "./workflow.js";

describe("resolveCwdOption", () => {
  it("returns process.cwd() when raw is undefined", () => {
    expect(resolveCwdOption(undefined)).toBe(process.cwd());
  });

  it("returns process.cwd() when raw is empty", () => {
    expect(resolveCwdOption("")).toBe(process.cwd());
  });

  it("accepts an absolute path to an existing directory", () => {
    const dir = mkdtempSync(join(tmpdir(), "df-cwd-"));
    try {
      expect(resolveCwdOption(dir)).toBe(dir);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("resolves relative paths against process.cwd()", () => {
    const resolved = resolveCwdOption(".");
    expect(resolved).toBe(process.cwd());
  });

  it("throws CliError when the path does not exist", () => {
    const errSpy = spyOn(console, "error").mockImplementation(() => {});
    const missing = join(tmpdir(), "df-cwd-does-not-exist-xyz");
    try {
      expect(() => resolveCwdOption(missing)).toThrow(CliError);
    } finally {
      errSpy.mockRestore();
    }
  });

  it("throws CliError when the path is a file, not a directory", () => {
    const errSpy = spyOn(console, "error").mockImplementation(() => {});
    const dir = mkdtempSync(join(tmpdir(), "df-cwd-"));
    const file = join(dir, "regular.txt");
    writeFileSync(file, "");
    try {
      expect(() => resolveCwdOption(file)).toThrow(CliError);
    } finally {
      errSpy.mockRestore();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("splitRunArgs", () => {
  function argv(...rest: string[]): string[] {
    return ["bun", "/path/bin.ts", "workflow", "run", ...rest];
  }

  it("captures the workflow name and leaves no extras when nothing else is passed", () => {
    const r = splitRunArgs(argv("security-review"));
    expect(r.name).toBe("security-review");
    expect(r.dryRun).toBe(false);
    expect(r.cwd).toBeUndefined();
    expect(r.extras).toEqual([]);
  });

  it("recognizes --dry-run and --cwd <path> in any order", () => {
    const r = splitRunArgs(
      argv("--dry-run", "--cwd", "/tmp", "architecture-assessment")
    );
    expect(r.name).toBe("architecture-assessment");
    expect(r.dryRun).toBe(true);
    expect(r.cwd).toBe("/tmp");
  });

  it("supports --cwd=value form", () => {
    const r = splitRunArgs(argv("architecture-assessment", "--cwd=/tmp"));
    expect(r.cwd).toBe("/tmp");
  });

  it("passes through unknown flags as extras with their values", () => {
    const r = splitRunArgs(
      argv("architecture-assessment", "--additional-context", "focus on engine")
    );
    expect(r.name).toBe("architecture-assessment");
    expect(r.extras).toEqual(["--additional-context", "focus on engine"]);
  });

  it("interleaves built-in and workflow flags", () => {
    const r = splitRunArgs(
      argv(
        "--dry-run",
        "architecture-assessment",
        "--additional-context",
        "x",
        "--cwd",
        "/tmp"
      )
    );
    expect(r.name).toBe("architecture-assessment");
    expect(r.dryRun).toBe(true);
    expect(r.cwd).toBe("/tmp");
    expect(r.extras).toEqual(["--additional-context", "x"]);
  });

  it("preserves --flag=value form for workflow flags", () => {
    const r = splitRunArgs(
      argv("architecture-assessment", "--additional-context=foo")
    );
    expect(r.extras).toEqual(["--additional-context=foo"]);
  });

  it("throws when no name is supplied", () => {
    expect(() => splitRunArgs(argv("--dry-run"))).toThrow(CliError);
  });

  it("throws when --cwd is given without a value", () => {
    expect(() => splitRunArgs(argv("name", "--cwd"))).toThrow(CliError);
  });
});

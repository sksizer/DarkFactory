import { describe, expect, it, spyOn } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CliError } from "../error.js";
import { resolveCwdOption } from "./workflow.js";

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

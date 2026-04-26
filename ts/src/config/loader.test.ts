import { describe, expect, it } from "bun:test";
import { join } from "node:path";
import { loadConfig } from "./loader.js";

const PROJECT_ROOT = join(import.meta.dirname, "..", "..", "..");

describe("loadConfig", () => {
  it("loads and validates .darkfactory/config.toml", () => {
    const config = loadConfig(PROJECT_ROOT);

    expect(config.v1).toBeDefined();
    expect(config.v1.code).toBeDefined();
    expect(config.v1.code.quality).toBeDefined();
  });

  it("parses quality checks with name and cmds", () => {
    const config = loadConfig(PROJECT_ROOT);
    const quality = config.v1.code.quality;

    const test = quality.test;
    expect(test).toBeDefined();
    expect(test?.name).toBe("test");
    expect(test?.cmds.length).toBeGreaterThan(0);

    const format = quality.format;
    expect(format).toBeDefined();
    expect(format?.name).toBe("format");
  });

  it("throws on missing config file", () => {
    expect(() => loadConfig("/nonexistent")).toThrow();
  });
});

import { describe, expect, test } from "bun:test";

describe("package entry point", () => {
  test("imports successfully", async () => {
    const mod = await import("./index.js");
    expect(mod).toBeDefined();
  });
});

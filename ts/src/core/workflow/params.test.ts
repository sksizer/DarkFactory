import { describe, expect, it } from "bun:test";
import { z } from "zod";
import {
  WorkflowParamsError,
  camelToKebab,
  describeParams,
  formatParamsHelp,
  parseWorkflowParams,
} from "./params.js";

describe("camelToKebab", () => {
  it("converts camelCase to kebab-case", () => {
    expect(camelToKebab("additionalContext")).toBe("additional-context");
    expect(camelToKebab("foo")).toBe("foo");
    expect(camelToKebab("maxDepthLimit")).toBe("max-depth-limit");
  });
});

describe("describeParams", () => {
  it("identifies optional, default, and required fields", () => {
    const schema = z.object({
      req: z.string().describe("required string"),
      opt: z.string().optional().describe("optional string"),
      def: z.string().default("hi"),
      bool: z.boolean().optional(),
      num: z.number().optional(),
    });
    const specs = describeParams(schema);
    const byName = Object.fromEntries(specs.map((s) => [s.name, s]));
    expect(byName.req?.required).toBe(true);
    expect(byName.opt?.required).toBe(false);
    expect(byName.def?.required).toBe(false);
    expect(byName.def?.defaultDisplay).toBe('"hi"');
    expect(byName.bool?.type).toBe("boolean");
    expect(byName.num?.type).toBe("number");
  });
});

describe("parseWorkflowParams", () => {
  const schema = z.object({
    additionalContext: z.string().optional(),
    depth: z.number().optional(),
    verbose: z.boolean().optional(),
    name: z.string(),
  });

  it("parses --flag value pairs", () => {
    const result = parseWorkflowParams(schema, [
      "--name",
      "alice",
      "--additional-context",
      "be thorough",
    ]);
    expect(result.name).toBe("alice");
    expect(result.additionalContext).toBe("be thorough");
  });

  it("parses --flag=value form", () => {
    const result = parseWorkflowParams(schema, ["--name=bob", "--depth=3"]);
    expect(result.name).toBe("bob");
    expect(result.depth).toBe(3);
  });

  it("treats boolean flags as switches", () => {
    const result = parseWorkflowParams(schema, ["--verbose", "--name", "x"]);
    expect(result.verbose).toBe(true);
  });

  it("rejects unknown flags loudly", () => {
    expect(() =>
      parseWorkflowParams(schema, ["--name", "x", "--bogus", "y"])
    ).toThrow(WorkflowParamsError);
  });

  it("rejects missing required params via Zod", () => {
    expect(() => parseWorkflowParams(schema, [])).toThrow(WorkflowParamsError);
  });

  it("rejects positional tokens", () => {
    expect(() => parseWorkflowParams(schema, ["positional"])).toThrow(
      WorkflowParamsError
    );
  });

  it("rejects flag without value", () => {
    expect(() => parseWorkflowParams(schema, ["--name"])).toThrow(
      WorkflowParamsError
    );
  });

  it("rejects non-numeric value for number field", () => {
    expect(() =>
      parseWorkflowParams(schema, ["--name", "x", "--depth", "nope"])
    ).toThrow(WorkflowParamsError);
  });

  it("returns empty object when schema accepts {} and no args given", () => {
    const allOptional = z.object({
      foo: z.string().optional(),
    });
    expect(parseWorkflowParams(allOptional, [])).toEqual({});
  });
});

describe("formatParamsHelp", () => {
  it("notes required vs optional and includes description", () => {
    const schema = z.object({
      a: z.string().describe("the A param"),
      b: z.string().optional().describe("the B param"),
    });
    const lines = formatParamsHelp(schema);
    const joined = lines.join("\n");
    expect(joined).toContain("--a");
    expect(joined).toContain("required");
    expect(joined).toContain("--b");
    expect(joined).toContain("optional");
    expect(joined).toContain("the A param");
  });

  it("returns no-parameters notice for empty schemas", () => {
    const lines = formatParamsHelp(z.object({}));
    expect(lines.join("\n")).toContain("(no parameters)");
  });
});

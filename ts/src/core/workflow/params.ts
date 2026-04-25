/**
 * params.ts — workflow parameter declaration, CLI parsing, and help.
 *
 * Workflows opt into parameters by exporting a Zod object schema named
 * `params` alongside `create`. The CLI parser (parseWorkflowParams)
 * converts camelCase schema keys to kebab-case CLI flags, validates with
 * the Zod schema (so required/optional comes for free), and rejects any
 * unknown flags loudly.
 *
 * Boolean fields are treated as switches (--flag with no value).
 * String, number, enum, and union fields take one value each.
 */

import type { z } from "zod";

export type WorkflowParamsSchema = z.ZodObject<z.ZodRawShape>;

export interface ParamSpec {
  readonly name: string; // camelCase
  readonly cliFlag: string; // kebab-case, e.g. additional-context
  readonly type: "boolean" | "number" | "string";
  readonly required: boolean;
  readonly description: string | undefined;
  readonly defaultDisplay: string | undefined;
}

export function camelToKebab(name: string): string {
  return name.replace(/([A-Z])/g, "-$1").toLowerCase();
}

function unwrapDefaults(schema: z.ZodType): {
  inner: z.ZodType;
  hadDefault: boolean;
  defaultDisplay: string | undefined;
  hadOptional: boolean;
} {
  let current: z.ZodType = schema;
  let hadDefault = false;
  let hadOptional = false;
  let defaultDisplay: string | undefined;

  // Unwrap arbitrarily nested optional/default/nullable wrappers.
  // Zod 4 exposes the inner type via `def.innerType`.
  for (let i = 0; i < 8; i += 1) {
    const def = (
      current as {
        def?: {
          type?: string;
          innerType?: z.ZodType;
          defaultValue?: unknown;
        };
      }
    ).def;
    if (def === undefined) break;
    if (def.type === "default") {
      hadDefault = true;
      const dv = def.defaultValue;
      defaultDisplay =
        typeof dv === "function" ? "<computed>" : JSON.stringify(dv);
      current = def.innerType ?? current;
      continue;
    }
    if (def.type === "optional" || def.type === "nullable") {
      hadOptional = true;
      current = def.innerType ?? current;
      continue;
    }
    break;
  }

  return { inner: current, hadDefault, defaultDisplay, hadOptional };
}

function classifyType(inner: z.ZodType): "boolean" | "number" | "string" {
  const def = (inner as { def?: { type?: string } }).def;
  switch (def?.type) {
    case "boolean":
      return "boolean";
    case "number":
    case "int":
      return "number";
    default:
      return "string";
  }
}

export function describeParams(schema: WorkflowParamsSchema): ParamSpec[] {
  const specs: ParamSpec[] = [];
  const shape = schema.shape;
  for (const [key, raw] of Object.entries(shape)) {
    const field = raw as z.ZodType;
    const { inner, hadDefault, defaultDisplay, hadOptional } =
      unwrapDefaults(field);
    const description = field.description;
    specs.push({
      name: key,
      cliFlag: camelToKebab(key),
      type: classifyType(inner),
      required: !hadOptional && !hadDefault,
      description,
      defaultDisplay,
    });
  }
  return specs;
}

export class WorkflowParamsError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WorkflowParamsError";
  }
}

/**
 * Parse extra CLI tokens against a workflow's params schema.
 *
 * - Unknown flags throw WorkflowParamsError.
 * - Boolean fields are switches (no value); other fields require a value.
 * - Bare positional tokens (not starting with `--`) throw.
 * - Final result is run through schema.parse(), so Zod's required-field
 *   validation produces the user-facing error for missing required params.
 */
export function parseWorkflowParams(
  schema: WorkflowParamsSchema,
  tokens: readonly string[]
): Record<string, unknown> {
  const specs = describeParams(schema);
  const flagToSpec = new Map<string, ParamSpec>();
  for (const spec of specs) {
    flagToSpec.set(spec.cliFlag, spec);
  }

  const collected: Record<string, unknown> = {};
  let i = 0;
  while (i < tokens.length) {
    const tok = tokens[i] as string;
    if (!tok.startsWith("--")) {
      throw new WorkflowParamsError(
        `Unexpected positional argument "${tok}". Workflow params must be passed as --flag <value>.`
      );
    }
    // Support --flag=value as well as --flag value
    const eqIdx = tok.indexOf("=");
    const flagName = (eqIdx === -1 ? tok.slice(2) : tok.slice(2, eqIdx)).trim();
    const inlineValue = eqIdx === -1 ? undefined : tok.slice(eqIdx + 1);

    const spec = flagToSpec.get(flagName);
    if (spec === undefined) {
      const known = specs.map((s) => `--${s.cliFlag}`).join(", ");
      const knownPart =
        known === "" ? "(this workflow takes no params)" : `known: ${known}`;
      throw new WorkflowParamsError(
        `Unknown flag "--${flagName}". ${knownPart}`
      );
    }

    if (spec.type === "boolean") {
      if (inlineValue !== undefined) {
        if (inlineValue === "true") collected[spec.name] = true;
        else if (inlineValue === "false") collected[spec.name] = false;
        else {
          throw new WorkflowParamsError(
            `Flag --${spec.cliFlag} is boolean but got "${inlineValue}"; use true or false.`
          );
        }
      } else {
        collected[spec.name] = true;
      }
      i += 1;
      continue;
    }

    let valueRaw: string;
    if (inlineValue !== undefined) {
      valueRaw = inlineValue;
      i += 1;
    } else {
      const next = tokens[i + 1];
      if (next === undefined || next.startsWith("--")) {
        throw new WorkflowParamsError(
          `Flag --${spec.cliFlag} requires a value.`
        );
      }
      valueRaw = next;
      i += 2;
    }

    if (spec.type === "number") {
      const n = Number(valueRaw);
      if (Number.isNaN(n)) {
        throw new WorkflowParamsError(
          `Flag --${spec.cliFlag} expects a number; got "${valueRaw}".`
        );
      }
      collected[spec.name] = n;
    } else {
      collected[spec.name] = valueRaw;
    }
  }

  const parsed = schema.safeParse(collected);
  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((iss) => {
        const key = iss.path[0];
        const flag =
          typeof key === "string" ? `--${camelToKebab(key)}` : "<root>";
        return `${flag}: ${iss.message}`;
      })
      .join("; ");
    throw new WorkflowParamsError(`Invalid workflow params: ${issues}`);
  }
  return parsed.data;
}

/**
 * Format the params section of `workflow describe <name>` output.
 * Returns lines (no trailing newlines).
 */
export function formatParamsHelp(schema: WorkflowParamsSchema): string[] {
  const specs = describeParams(schema);
  if (specs.length === 0) return ["  (no parameters)"];
  const lines: string[] = [];
  const longest = Math.max(...specs.map((s) => s.cliFlag.length + 2));
  for (const spec of specs) {
    const flag = `--${spec.cliFlag}`.padEnd(longest + 1);
    const required = spec.required ? "required" : "optional";
    const meta = [spec.type, required];
    if (spec.defaultDisplay !== undefined) {
      meta.push(`default ${spec.defaultDisplay}`);
    }
    const desc = spec.description ?? "";
    lines.push(
      `  ${flag} (${meta.join(", ")})${desc !== "" ? `  ${desc}` : ""}`
    );
  }
  return lines;
}

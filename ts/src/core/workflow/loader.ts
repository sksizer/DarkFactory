import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";
import type { Workflow } from "./types.js";

type WorkflowSource = "builtin" | "user" | "project";

export interface DiscoveredWorkflow {
  readonly name: string;
  readonly category: string | undefined;
  readonly description: string;
  readonly source: WorkflowSource;
  readonly resolve: (cwd: string) => Workflow;
}

function validateWorkflow(
  wf: unknown,
  dirName: string
): asserts wf is Workflow {
  const obj = wf as Record<string, unknown>;
  if (typeof obj.name !== "string" || obj.name === "") {
    throw new Error(`Workflow in ${dirName} has invalid or missing name`);
  }
  if (typeof obj.description !== "string" || obj.description === "") {
    throw new Error(
      `Workflow in ${dirName} has invalid or missing description`
    );
  }
  if (!Array.isArray(obj.tasks) || obj.tasks.length === 0) {
    throw new Error(`Workflow in ${dirName} has no tasks`);
  }
}

async function scanLayer(
  dir: string,
  source: "builtin" | "project"
): Promise<DiscoveredWorkflow[]> {
  const results: DiscoveredWorkflow[] = [];

  let entries: string[];
  try {
    entries = await readdir(dir);
  } catch {
    return [];
  }

  for (const entry of entries) {
    const subdir = join(dir, entry);
    let s: Awaited<ReturnType<typeof stat>>;
    try {
      s = await stat(subdir);
    } catch {
      continue;
    }
    if (!s.isDirectory()) continue;

    const workflowFile = join(subdir, "workflow.ts");
    try {
      await stat(workflowFile);
    } catch {
      continue;
    }

    try {
      const mod = (await import(workflowFile)) as Record<string, unknown>;

      if (typeof mod.create === "function") {
        const createFn = mod.create as (cwd: string) => Workflow;
        const probe = createFn(".");
        validateWorkflow(probe, entry);
        results.push({
          name: probe.name,
          category: probe.category,
          description: probe.description,
          source,
          resolve: createFn,
        });
      } else if (mod.workflow != null && typeof mod.workflow === "object") {
        const wf = mod.workflow as Workflow;
        validateWorkflow(wf, entry);
        results.push({
          name: wf.name,
          category: wf.category,
          description: wf.description,
          source,
          resolve: () => wf,
        });
      } else {
        console.warn(
          `Warning: ${entry}/workflow.ts exports neither create() nor workflow`
        );
      }
    } catch (e) {
      console.warn(
        `Warning: failed to load ${workflowFile}: ${e instanceof Error ? e.message : String(e)}`
      );
    }
  }

  return results;
}

export async function discoverWorkflows(
  projectDir?: string
): Promise<DiscoveredWorkflow[]> {
  const builtinDir = join(import.meta.dirname, "..", "..", "data", "workflows");
  const builtins = await scanLayer(builtinDir, "builtin");
  const results = [...builtins];

  if (projectDir !== undefined) {
    const projectWorkflows = await scanLayer(projectDir, "project");
    const builtinNames = new Set(builtins.map((w) => w.name));
    for (const pw of projectWorkflows) {
      if (builtinNames.has(pw.name)) {
        throw new Error(
          `Workflow name collision: "${pw.name}" exists in both builtin and project layers`
        );
      }
      results.push(pw);
    }
  }

  return results;
}

import { join } from "node:path";
import { runWorkflow } from "../core/workflow/engine/runner.js";
import { discoverWorkflows } from "../core/workflow/loader.js";

export async function listWorkflows(): Promise<void> {
  const workflows = await discoverWorkflows(
    join(process.cwd(), ".darkfactory", "workflows")
  );

  const grouped = new Map<string, typeof workflows>();
  for (const wf of workflows) {
    const cat = wf.category ?? "uncategorized";
    const list = grouped.get(cat);
    if (list !== undefined) {
      list.push(wf);
    } else {
      grouped.set(cat, [wf]);
    }
  }

  console.log("Available workflows:");
  for (const [category, wfs] of grouped) {
    console.log(`\n  ${category}`);
    for (const wf of wfs) {
      console.log(`    ${wf.name.padEnd(20)} ${wf.description}`);
    }
  }
}

export async function run(name: string, dryRun: boolean): Promise<void> {
  const workflows = await discoverWorkflows(
    join(process.cwd(), ".darkfactory", "workflows")
  );

  const found = workflows.find((w) => w.name === name);
  if (found === undefined) {
    console.error(`Error: unknown workflow "${name}"`);
    console.error(
      `Available workflows: ${workflows.map((w) => w.name).join(", ")}`
    );
    process.exit(1);
  }

  const wf = found.resolve(process.cwd());
  console.log(`Running workflow: ${wf.name}`);
  if (dryRun) console.log("  (dry-run mode)");

  const result = await runWorkflow(wf, { dryRun });

  for (const step of result.steps) {
    const status = step.success ? "+" : "x";
    const reason =
      step.failureReason !== undefined ? ` -- ${step.failureReason}` : "";
    console.log(`  ${status} ${step.name}${reason}`);
  }

  if (result.success) {
    console.log("Workflow completed successfully.");
  } else {
    console.error(
      `Workflow failed: ${result.failureReason ?? "unknown reason"}`
    );
    process.exit(1);
  }
}

export async function main(args: string[]): Promise<void> {
  console.log("DarkFactory CLI");
  const command = args[0];

  if (command === "list-workflows") {
    await listWorkflows();
    return;
  }

  if (command === "run") {
    const name = args[1];
    if (name === undefined) {
      console.error("Usage: run <workflow> [--dry-run]");
      process.exit(1);
    }
    const dryRun = args.includes("--dry-run");
    await run(name, dryRun);
    return;
  }

  console.error(`Unknown command: ${command ?? "(none)"}`);
  console.error("Usage: <list-workflows | run <workflow> [--dry-run]>");
  process.exit(1);
}

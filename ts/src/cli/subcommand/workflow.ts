import { join } from "node:path";
import { Command } from "commander";
import { runWorkflow } from "../../core/workflow/engine/runner.js";
import { discoverWorkflows } from "../../core/workflow/loader.js";
import { CliError } from "../error.js";

function projectWorkflowDir(): string {
  return join(process.cwd(), ".darkfactory", "workflows");
}

async function listWorkflows(): Promise<void> {
  const workflows = await discoverWorkflows(projectWorkflowDir());

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

async function runByName(
  name: string,
  opts: { dryRun: boolean }
): Promise<void> {
  const workflows = await discoverWorkflows(projectWorkflowDir());

  const found = workflows.find((w) => w.name === name);
  if (found === undefined) {
    console.error(`Error: unknown workflow "${name}"`);
    console.error(
      `Available workflows: ${workflows.map((w) => w.name).join(", ")}`
    );
    throw new CliError(`unknown workflow "${name}"`);
  }

  const wf = found.resolve(process.cwd());
  console.log(`Running workflow: ${wf.name}`);
  if (opts.dryRun) console.log("  (dry-run mode)");

  const result = await runWorkflow(wf, { dryRun: opts.dryRun });

  for (const step of result.steps) {
    const status = step.success ? "+" : "x";
    const reason =
      step.failureReason !== undefined ? ` -- ${step.failureReason}` : "";
    console.log(`  ${status} ${step.name}${reason}`);
  }

  if (result.success) {
    console.log("Workflow completed successfully.");
  } else {
    const msg = result.failureReason ?? "unknown reason";
    console.error(`Workflow failed: ${msg}`);
    throw new CliError(msg);
  }
}

export function workflowCommand(): Command {
  const cmd = new Command("workflow").description("Manage and run workflows");

  cmd
    .command("list")
    .description("List available workflows grouped by category")
    .action(async () => {
      await listWorkflows();
    });

  cmd
    .command("run")
    .description("Run a workflow by name")
    .argument("<name>", "Workflow name")
    .option("--dry-run", "Run in dry-run mode", false)
    .action(async (name: string, opts: { dryRun: boolean }) => {
      await runByName(name, opts);
    });

  return cmd;
}

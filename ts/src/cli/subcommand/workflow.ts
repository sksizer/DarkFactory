import { statSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";
import { Command } from "commander";
import { runWorkflow } from "../../core/workflow/engine/runner.js";
import { discoverWorkflows } from "../../core/workflow/loader.js";
import { CliError } from "../error.js";

function projectWorkflowDir(cwd: string): string {
  return join(cwd, ".darkfactory", "workflows");
}

/**
 * Resolve a user-supplied --cwd to an absolute path and verify it is a directory.
 * Relative paths are resolved against the current process cwd.
 */
export function resolveCwdOption(raw: string | undefined): string {
  if (raw === undefined || raw === "") return process.cwd();
  const abs = isAbsolute(raw) ? raw : resolve(process.cwd(), raw);
  let stat: ReturnType<typeof statSync>;
  try {
    stat = statSync(abs);
  } catch {
    const msg = `--cwd path does not exist: ${abs}`;
    console.error(`Error: ${msg}`);
    throw new CliError(msg);
  }
  if (!stat.isDirectory()) {
    const msg = `--cwd path is not a directory: ${abs}`;
    console.error(`Error: ${msg}`);
    throw new CliError(msg);
  }
  return abs;
}

async function listWorkflows(): Promise<void> {
  const workflows = await discoverWorkflows(projectWorkflowDir(process.cwd()));

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
  opts: { dryRun: boolean; cwd?: string | undefined }
): Promise<void> {
  const cwd = resolveCwdOption(opts.cwd);
  const workflows = await discoverWorkflows(projectWorkflowDir(cwd));

  const found = workflows.find((w) => w.name === name);
  if (found === undefined) {
    console.error(`Error: unknown workflow "${name}"`);
    console.error(
      `Available workflows: ${workflows.map((w) => w.name).join(", ")}`
    );
    throw new CliError(`unknown workflow "${name}"`);
  }

  const wf = found.resolve(cwd);
  console.log(`Running workflow: ${wf.name}`);
  if (cwd !== process.cwd()) console.log(`  (cwd: ${cwd})`);
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
    .option(
      "--cwd <path>",
      "Target directory to run the workflow in (defaults to current directory)"
    )
    .action(
      async (
        name: string,
        opts: { dryRun: boolean; cwd?: string | undefined }
      ) => {
        await runByName(name, opts);
      }
    );

  return cmd;
}

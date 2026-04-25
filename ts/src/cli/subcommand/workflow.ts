import { statSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";
import { Command } from "commander";
import { runWorkflow } from "../../core/workflow/engine/runner.js";
import {
  type DiscoveredWorkflow,
  discoverWorkflows,
} from "../../core/workflow/loader.js";
import {
  WorkflowParamsError,
  describeParams,
  formatParamsHelp,
  parseWorkflowParams,
} from "../../core/workflow/params.js";
import { CliError } from "../error.js";

function projectWorkflowDir(cwd: string): string {
  return join(cwd, ".darkfactory", "workflows");
}

interface SplitRunArgs {
  readonly name: string;
  readonly dryRun: boolean;
  readonly cwd: string | undefined;
  readonly extras: readonly string[];
}

/**
 * Walk argv, peeling off built-in run flags (--cwd, --dry-run) and the
 * required <name> positional. Anything left over is returned as extras —
 * to be parsed by the workflow's own params schema.
 *
 * Supports --flag value and --flag=value, with built-ins and workflow
 * flags interleaved in any order.
 */
export function splitRunArgs(argv: readonly string[]): SplitRunArgs {
  // Locate the "run" subcommand token in argv. Layout from `bun bin.ts
  // workflow run ...` is roughly: [bun, /path/to/bin.ts, "workflow",
  // "run", ...]. Be defensive: just find the last "run" before any "--".
  const runIdx = argv.lastIndexOf("run");
  const tokens = runIdx === -1 ? argv.slice(2) : argv.slice(runIdx + 1);

  let dryRun = false;
  let cwd: string | undefined;
  let name: string | undefined;
  const extras: string[] = [];

  let i = 0;
  while (i < tokens.length) {
    const tok = tokens[i] as string;

    if (!tok.startsWith("--")) {
      if (name === undefined) {
        name = tok;
        i += 1;
        continue;
      }
      // Subsequent positional → leave for the workflow params parser to
      // reject with a clear message.
      extras.push(tok);
      i += 1;
      continue;
    }

    const eqIdx = tok.indexOf("=");
    const flag = (eqIdx === -1 ? tok : tok.slice(0, eqIdx)).slice(2);
    const inline = eqIdx === -1 ? undefined : tok.slice(eqIdx + 1);

    if (flag === "dry-run") {
      dryRun = inline === undefined ? true : inline !== "false";
      i += 1;
      continue;
    }
    if (flag === "cwd") {
      if (inline !== undefined) {
        cwd = inline;
        i += 1;
      } else {
        const next = tokens[i + 1];
        if (next === undefined || next.startsWith("--")) {
          throw new CliError("--cwd requires a value");
        }
        cwd = next;
        i += 2;
      }
      continue;
    }

    // Workflow-specific flag — preserve original token shape so the
    // workflow params parser sees exactly what the user typed.
    extras.push(tok);
    if (inline === undefined) {
      // Capture the next token as the value if it's not another flag.
      // Keeps boolean switches (no following value) working.
      const next = tokens[i + 1];
      if (next !== undefined && !next.startsWith("--")) {
        extras.push(next);
        i += 2;
        continue;
      }
    }
    i += 1;
  }

  if (name === undefined) {
    throw new CliError("workflow run requires a workflow name");
  }
  return { name, dryRun, cwd, extras };
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

function paramSummary(wf: DiscoveredWorkflow): string {
  if (wf.params === undefined) return "";
  const specs = describeParams(wf.params);
  if (specs.length === 0) return "";
  const flags = specs
    .map((s) => (s.required ? `--${s.cliFlag}` : `[--${s.cliFlag}]`))
    .join(" ");
  return `  params: ${flags}`;
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
      const summary = paramSummary(wf);
      if (summary !== "") {
        console.log(`    ${" ".repeat(20)}${summary}`);
      }
    }
  }
}

async function describeWorkflow(name: string): Promise<void> {
  const cwd = process.cwd();
  const workflows = await discoverWorkflows(projectWorkflowDir(cwd));
  const found = workflows.find((w) => w.name === name);
  if (found === undefined) {
    console.error(`Error: unknown workflow "${name}"`);
    console.error(
      `Available workflows: ${workflows.map((w) => w.name).join(", ")}`
    );
    throw new CliError(`unknown workflow "${name}"`);
  }

  console.log(`Workflow: ${found.name}`);
  console.log(`  category:    ${found.category ?? "uncategorized"}`);
  console.log(`  source:      ${found.source}`);
  console.log(`  description: ${found.description}`);
  console.log("");
  console.log("Parameters:");
  if (found.params === undefined) {
    console.log("  (no parameters)");
    return;
  }
  for (const line of formatParamsHelp(found.params)) {
    console.log(line);
  }
}

async function runByName(
  name: string,
  opts: { dryRun: boolean; cwd?: string | undefined },
  extras: readonly string[]
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

  let parsedParams: Record<string, unknown> | undefined;
  if (found.params !== undefined) {
    try {
      parsedParams = parseWorkflowParams(found.params, extras);
    } catch (e) {
      if (e instanceof WorkflowParamsError) {
        console.error(`Error: ${e.message}`);
        console.error(
          `Run \`workflow describe ${name}\` to see available parameters.`
        );
        throw new CliError(e.message);
      }
      throw e;
    }
  } else if (extras.length > 0) {
    const msg = `Workflow "${name}" takes no parameters but received: ${extras.join(" ")}`;
    console.error(`Error: ${msg}`);
    throw new CliError(msg);
  }

  const wf = found.resolve(cwd, parsedParams);
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
    .description(
      "Run a workflow by name. Workflow-specific flags can follow; use `workflow describe <name>` to see them."
    )
    .argument("<name>", "Workflow name")
    .option("--dry-run", "Run in dry-run mode", false)
    .option(
      "--cwd <path>",
      "Target directory to run the workflow in (defaults to current directory)"
    )
    // We do our own argv split so that built-in flags (--cwd, --dry-run)
    // and workflow-specific flags can interleave with the workflow name in
    // any order. Commander's `allowUnknownOption` only suppresses the error
    // for unknown flags but still treats their values as positional, which
    // overflows the single <name> argument. Bypass by parsing manually.
    .allowUnknownOption(true)
    .allowExcessArguments(true)
    .action(async (_name, _opts, command: Command) => {
      // Walk up to the root program to read rawArgs (Commander sets this
      // on the root after parseAsync; it is not exposed in the public TS
      // types so we cast). Aliasing `this` to a local would trip the
      // no-this-alias lint, so we accept the action's `command` arg
      // instead.
      let root: Command = command;
      while (root.parent !== null) {
        root = root.parent;
      }
      const rawArgs =
        (root as unknown as { rawArgs?: string[] }).rawArgs ?? process.argv;
      const split = splitRunArgs(rawArgs);
      await runByName(
        split.name,
        { dryRun: split.dryRun, cwd: split.cwd },
        split.extras
      );
    });

  cmd
    .command("describe")
    .description("Show full details for a workflow, including its parameters")
    .argument("<name>", "Workflow name")
    .action(async (name: string) => {
      await describeWorkflow(name);
    });

  return cmd;
}

import { Command } from "commander";
import { CliError } from "./error.js";
import { workflowCommand } from "./subcommand/workflow.js";

export function buildProgram(): Command {
  const program = new Command()
    .name("darkfactory")
    .description("DarkFactory CLI")
    .version("0.0.1");

  program.addCommand(workflowCommand());

  return program;
}

export async function main(args: string[]): Promise<number> {
  const program = buildProgram();
  try {
    await program.parseAsync(args, { from: "user" });
    return 0;
  } catch (e) {
    if (e instanceof CliError) {
      return e.exitCode;
    }
    throw e;
  }
}

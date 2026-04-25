import { Command } from "commander";
import { tryLoadConfig } from "../config/index.js";
import { initLogger, resolveLogLevel } from "../logger/index.js";
import { CliError } from "./error.js";
import { workflowCommand } from "./subcommand/workflow.js";

export function buildProgram(): Command {
  const program = new Command()
    .name("darkfactory")
    .description("DarkFactory CLI")
    .version("0.0.1")
    .option(
      "--log-level <level>",
      "Log level (trace, debug, info, warn, error, fatal, silent)"
    );

  program.addCommand(workflowCommand());

  program.hook("preAction", () => {
    const opts = program.opts<{ logLevel?: string }>();
    const config = tryLoadConfig(process.cwd());
    const level = resolveLogLevel({
      cli: opts.logLevel,
      config: config.v1.log_level,
    });
    initLogger(level);
  });

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

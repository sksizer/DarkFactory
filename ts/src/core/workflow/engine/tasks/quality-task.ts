/**
 * quality-task.ts — run project quality checks from config.
 *
 * Reads quality check definitions from ProjectConfig, executes each one,
 * and produces a QualityResult payload with per-check outcomes.
 * All commands in a check must pass. Fails if any check fails, but always
 * writes QualityResult to state so recovery tasks can read it.
 */

import { runShell } from "../../../../utils/exec/shell.js";
import {
  CodeEnv,
  ProjectConfig,
  type QualityCheckOutcome,
  QualityResult,
} from "../payloads.js";
import type { Task } from "../task.js";

/**
 * Run all quality checks defined in config.
 * Every command in each check must succeed. Returns failure with
 * QualityResult attached when any check fails — the runner writes
 * the value to state so onFailure recovery tasks can inspect it.
 */
export function codeQualityTask(): Task<
  "CodeEnv" | "ProjectConfig",
  "QualityResult"
> {
  return {
    name: "code-quality",
    reads: [CodeEnv, ProjectConfig] as const,
    writes: QualityResult,
    async run(env, resolve) {
      const codeEnv = resolve(CodeEnv);
      const projectConfig = resolve(ProjectConfig);
      const checks = projectConfig.config.v1.code.quality;

      if (env.dryRun) {
        const dryChecks = Object.entries(checks).map(
          ([, check]): QualityCheckOutcome => ({
            name: check.name,
            success: true,
            exitCode: 0,
            cmd: check.cmds[0] ?? "",
            stderr: "",
          })
        );
        return { success: true, value: new QualityResult(dryChecks) };
      }

      const outcomes: QualityCheckOutcome[] = [];

      for (const [, check] of Object.entries(checks)) {
        for (const cmd of check.cmds) {
          let outcome: QualityCheckOutcome;
          try {
            const result = await runShell(cmd, codeEnv.cwd);
            outcome = {
              name: check.name,
              success: result.exitCode === 0,
              exitCode: result.exitCode,
              cmd,
              stderr: result.stderr,
            };
          } catch (e) {
            outcome = {
              name: check.name,
              success: false,
              exitCode: -1,
              cmd,
              stderr: e instanceof Error ? e.message : String(e),
            };
          }
          outcomes.push(outcome);
          const icon = outcome.success ? "+" : "x";
          console.log(`  ${icon} ${check.name}: ${cmd}`);
        }
      }

      const qualityResult = new QualityResult(outcomes);

      if (!qualityResult.allPassed) {
        const failed = outcomes
          .filter((o) => !o.success)
          .map((o) => `${o.name} (${o.cmd})`);
        return {
          success: false,
          failureReason: `Quality checks failed: ${failed.join(", ")}`,
          value: qualityResult,
        };
      }

      return { success: true, value: qualityResult };
    },
  };
}

/**
 * Config schema — single source of truth for .darkfactory/config.toml structure.
 * Types are derived from the schema via z.infer.
 */

import { z } from "zod/v4";

const QualityCheckSchema = z.object({
  name: z.string(),
  cmds: z
    .union([z.string(), z.array(z.string())])
    .transform((v) => (typeof v === "string" ? [v] : v)),
});

const CodeConfigSchema = z.object({
  dev: z.string().optional(),
  quality: z.record(z.string(), QualityCheckSchema).default({}),
});

const LogLevelSchema = z.enum([
  "trace",
  "debug",
  "info",
  "warn",
  "error",
  "fatal",
  "silent",
]);

const ConfigV1Schema = z.object({
  code: CodeConfigSchema.default({ quality: {} }),
  log_level: LogLevelSchema.optional(),
  workflow: z
    .object({
      directories: z.array(z.string()).optional(),
    })
    .optional(),
});

export const DarkFactoryConfigSchema = z.object({
  v1: ConfigV1Schema.default({ code: { quality: {} } }),
});

export type QualityCheck = z.infer<typeof QualityCheckSchema>;
export type CodeConfig = z.infer<typeof CodeConfigSchema>;
export type ConfigV1 = z.infer<typeof ConfigV1Schema>;
export type DarkFactoryConfig = z.infer<typeof DarkFactoryConfigSchema>;

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { type DarkFactoryConfig, DarkFactoryConfigSchema } from "./types.js";

export type { DarkFactoryConfig, ConfigV1, CodeConfig, QualityCheck } from "./types.js";
export { DarkFactoryConfigSchema } from "./types.js";

export function loadConfig(projectRoot: string): DarkFactoryConfig {
  const configPath = join(projectRoot, ".darkfactory", "config.toml");
  const text = readFileSync(configPath, "utf-8");
  // Dynamic import to avoid hard dep if smol-toml isn't installed
  const { parse } = require("smol-toml") as { parse: (s: string) => unknown };
  const raw = parse(text);
  return DarkFactoryConfigSchema.parse(raw);
}

const EMPTY_CONFIG: DarkFactoryConfig = { v1: { code: { quality: {} } } };

export function tryLoadConfig(projectRoot: string): DarkFactoryConfig {
  try {
    return loadConfig(projectRoot);
  } catch {
    return EMPTY_CONFIG;
  }
}

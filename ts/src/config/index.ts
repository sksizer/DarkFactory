import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parse } from "smol-toml";
import { type DarkFactoryConfig, DarkFactoryConfigSchema } from "./types.js";

export type {
  DarkFactoryConfig,
  ConfigV1,
  CodeConfig,
  QualityCheck,
} from "./types.js";
export { DarkFactoryConfigSchema } from "./types.js";

export function loadConfig(projectRoot: string): DarkFactoryConfig {
  const configPath = join(projectRoot, ".darkfactory", "config.toml");
  const text = readFileSync(configPath, "utf-8");
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

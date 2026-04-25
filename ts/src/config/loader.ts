/**
 * Config loader — reads and validates .darkfactory/config.toml.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { type DarkFactoryConfig, DarkFactoryConfigSchema } from "./types.js";

/**
 * Load and validate .darkfactory/config.toml from a project root.
 * Throws on missing file or invalid structure.
 */
export function loadConfig(projectRoot: string): DarkFactoryConfig {
  const configPath = join(projectRoot, ".darkfactory", "config.toml");
  const text = readFileSync(configPath, "utf-8");
  const raw = Bun.TOML.parse(text);
  return DarkFactoryConfigSchema.parse(raw);
}

const EMPTY_CONFIG: DarkFactoryConfig = { v1: { code: { quality: {} } } };

/**
 * Load config, returning a safe default if the file is missing or invalid.
 */
export function tryLoadConfig(projectRoot: string): DarkFactoryConfig {
  try {
    return loadConfig(projectRoot);
  } catch {
    return EMPTY_CONFIG;
  }
}

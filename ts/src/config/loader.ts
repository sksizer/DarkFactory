/**
 * Config loader — reads and validates .darkfactory/config.toml.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parse } from "smol-toml";
import { type DarkFactoryConfig, DarkFactoryConfigSchema } from "./types.js";

/**
 * Load and validate .darkfactory/config.toml from a project root.
 * Throws on missing file or invalid structure.
 */
export function loadConfig(projectRoot: string): DarkFactoryConfig {
  const configPath = join(projectRoot, ".darkfactory", "config.toml");
  const text = readFileSync(configPath, "utf-8");
  const raw = parse(text);
  return DarkFactoryConfigSchema.parse(raw);
}

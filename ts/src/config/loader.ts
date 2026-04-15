/**
 * Config loader — reads and validates .darkfactory/config.toml.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import type {
  CodeConfig,
  ConfigV1,
  DarkFactoryConfig,
  QualityCheck,
} from "./types.js";

interface BunTOML {
  parse(input: string): unknown;
}

function parseTOML(text: string): unknown {
  const bun = globalThis.Bun as { TOML: BunTOML } | undefined;
  if (bun?.TOML !== undefined) {
    return bun.TOML.parse(text);
  }
  throw new Error(
    "TOML parsing requires Bun runtime (Bun.TOML.parse). No fallback available."
  );
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function validateQualityCheck(
  key: string,
  raw: unknown
): QualityCheck {
  if (!isRecord(raw)) {
    throw new Error(`quality.${key}: expected object`);
  }
  const name = typeof raw.name === "string" ? raw.name : key;

  let cmds: string[];
  if (typeof raw.cmds === "string") {
    cmds = [raw.cmds];
  } else if (Array.isArray(raw.cmds) && raw.cmds.length > 0) {
    for (const cmd of raw.cmds) {
      if (typeof cmd !== "string") {
        throw new Error(`quality.${key}: each cmd must be a string`);
      }
    }
    cmds = raw.cmds as string[];
  } else {
    throw new Error(
      `quality.${key}: cmds must be a string or non-empty array of strings`
    );
  }

  return { name, cmds };
}

function validateCodeConfig(raw: unknown): CodeConfig {
  if (!isRecord(raw)) {
    return { quality: {} };
  }
  const dev = typeof raw.dev === "string" ? raw.dev : undefined;
  const quality: Record<string, QualityCheck> = {};

  if (isRecord(raw.quality)) {
    for (const [key, value] of Object.entries(raw.quality)) {
      quality[key] = validateQualityCheck(key, value);
    }
  }

  return { dev, quality };
}

function validateConfig(raw: unknown): DarkFactoryConfig {
  if (!isRecord(raw)) {
    throw new Error("config.toml: expected top-level object");
  }

  const rawV1 = isRecord(raw.v1) ? raw.v1 : {};
  const code = validateCodeConfig(
    isRecord(rawV1) ? rawV1.code : undefined
  );

  const workflow = isRecord(rawV1.workflow)
    ? {
        directories: Array.isArray(rawV1.workflow.directories)
          ? (rawV1.workflow.directories as string[])
          : undefined,
      }
    : undefined;

  const v1: ConfigV1 = { code, ...(workflow !== undefined ? { workflow } : {}) };
  return { v1 };
}

/**
 * Load and validate .darkfactory/config.toml from a project root.
 * Throws on missing file or invalid structure.
 */
export function loadConfig(projectRoot: string): DarkFactoryConfig {
  const configPath = join(projectRoot, ".darkfactory", "config.toml");
  const text = readFileSync(configPath, "utf-8");
  const raw = parseTOML(text);
  return validateConfig(raw);
}

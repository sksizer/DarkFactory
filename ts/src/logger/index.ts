import pino from "pino";

export type LogLevel =
  | "trace"
  | "debug"
  | "info"
  | "warn"
  | "error"
  | "fatal"
  | "silent";

const LOG_LEVELS: ReadonlySet<string> = new Set([
  "trace",
  "debug",
  "info",
  "warn",
  "error",
  "fatal",
  "silent",
]);

export function isLogLevel(value: string): value is LogLevel {
  return LOG_LEVELS.has(value);
}

const DEFAULT_LEVEL: LogLevel = "info";

let rootLogger: pino.Logger = pino({
  level: DEFAULT_LEVEL,
  transport: {
    target: "pino-pretty",
    options: { colorize: true },
  },
});

/**
 * Resolve log level from sources in priority order:
 *   1. Explicit CLI flag (if provided)
 *   2. DARKFACTORY_LOG_LEVEL env var
 *   3. Config file value (if provided)
 *   4. Default ("info")
 */
export function resolveLogLevel(opts: {
  cli?: string | undefined;
  config?: string | undefined;
}): LogLevel {
  const sources = [opts.cli, process.env.DARKFACTORY_LOG_LEVEL, opts.config];

  for (const src of sources) {
    if (src !== undefined && isLogLevel(src)) {
      return src;
    }
  }

  return DEFAULT_LEVEL;
}

/**
 * Initialize the root logger with a resolved level.
 * Call once at startup after config + CLI args are known.
 */
export function initLogger(level: LogLevel): void {
  rootLogger = pino({
    level,
    transport: {
      target: "pino-pretty",
      options: { colorize: true },
    },
  });
}

/**
 * Get a child logger for a category.
 */
export function getLogger(category: string): pino.Logger {
  return rootLogger.child({ category });
}

/**
 * Get the root logger directly.
 */
export function getRootLogger(): pino.Logger {
  return rootLogger;
}

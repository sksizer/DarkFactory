/**
 * secrets.ts — secrets scanning and redaction.
 *
 * Pure regex — no subprocess calls. Ports all Python patterns plus
 * Anthropic API key detection (11 patterns total).
 */

// ---------- Pattern registry ----------

interface PatternEntry {
  readonly name: string;
  readonly pattern: RegExp;
}

const _PATTERNS: PatternEntry[] = [];

function register(name: string, source: string, flags = ""): void {
  _PATTERNS.push({ name, pattern: new RegExp(source, flags) });
}

// AWS
register("aws_access_key", "(?<![A-Z0-9])(AKIA[0-9A-Z]{16})(?![A-Z0-9])");
register(
  "aws_secret_key",
  "(?<![A-Za-z0-9/+=])([A-Za-z0-9/+=]{40})(?![A-Za-z0-9/+=])",
);

// GitHub tokens
register("github_token", "(ghp_[A-Za-z0-9]{36,})");
register("github_oauth", "(gho_[A-Za-z0-9]{36,})");
register("github_app_token", "(ghs_[A-Za-z0-9]{36,})");
register("github_fine_grained", "(github_pat_[A-Za-z0-9_]{22,})");

// Anthropic API key (sk-ant-...)
register("anthropic_api_key", "(sk-ant-[A-Za-z0-9\\-_]{40,})");

// Generic high-entropy secrets
register(
  "generic_api_key",
  "(?:api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token|secret[_-]?key)\\s*[:=]\\s*['\"]?([A-Za-z0-9\\-_.]{20,})['\"]?",
  "i",
);

// Private keys
register(
  "private_key",
  "(-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----)",
  "m",
);

// Connection strings
register(
  "connection_string",
  "((?:postgres|mysql|mongodb|redis)://[^\\s'\"]+)",
  "i",
);

// Bearer tokens in headers
register("bearer_token", "(?:bearer\\s+)([A-Za-z0-9\\-_.~+/]+=*)", "i");

// ---------- Public API ----------

export interface RedactionResult {
  readonly text: string;
  readonly redactionCount: number;
  readonly patternsMatched: readonly string[];
}

/**
 * Scan text for secret patterns.
 * Returns list of { pattern, match } for all matches found.
 */
export function scan(text: string): Array<{ pattern: string; match: string }> {
  const hits: Array<{ pattern: string; match: string }> = [];
  for (const { name, pattern } of _PATTERNS) {
    const re = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g");
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      const matched = m[1] !== undefined ? m[1] : m[0];
      hits.push({ pattern: name, match: matched });
    }
  }
  return hits;
}

/**
 * Redact secrets in text. Replaces each match with [REDACTED:pattern_name].
 */
export function redact(text: string): RedactionResult {
  let result = text;
  let count = 0;
  const matched: string[] = [];

  for (const { name, pattern } of _PATTERNS) {
    const re = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g");
    const before = result;
    result = result.replace(re, `[REDACTED:${name}]`);
    if (result !== before) {
      const replacements = (before.match(re) ?? []).length;
      count += replacements > 0 ? replacements : 1;
      matched.push(name);
    }
  }

  return { text: result, redactionCount: count, patternsMatched: matched };
}

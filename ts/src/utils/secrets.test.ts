import { describe, expect, it } from "bun:test";
import { match } from "ts-pattern";
import { type RedactionResult, redact, scan } from "./secrets.js";

// Helper to verify scan finds a pattern
function hasScan(text: string, patternName: string): boolean {
  return scan(text).some((h) => h.pattern === patternName);
}

describe("scan — all 11 patterns", () => {
  it("detects AWS access key", () => {
    expect(hasScan("key: AKIAIOSFODNN7EXAMPLE", "aws_access_key")).toBe(true);
  });

  it("detects AWS secret key (40-char base64)", () => {
    // 40 chars of base64 chars, surrounded by non-matching chars
    expect(
      hasScan(" wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY ", "aws_secret_key")
    ).toBe(true);
  });

  it("detects GitHub personal access token (ghp_)", () => {
    const token = `ghp_${"A".repeat(36)}`;
    expect(hasScan(`token: ${token}`, "github_token")).toBe(true);
  });

  it("detects GitHub OAuth token (gho_)", () => {
    const token = `gho_${"B".repeat(36)}`;
    expect(hasScan(token, "github_oauth")).toBe(true);
  });

  it("detects GitHub App token (ghs_)", () => {
    const token = `ghs_${"C".repeat(36)}`;
    expect(hasScan(token, "github_app_token")).toBe(true);
  });

  it("detects GitHub fine-grained PAT (github_pat_)", () => {
    const token = `github_pat_${"D".repeat(22)}`;
    expect(hasScan(token, "github_fine_grained")).toBe(true);
  });

  it("detects Anthropic API key (sk-ant-)", () => {
    const token = `sk-ant-${"E".repeat(40)}`;
    expect(hasScan(`api_key=${token}`, "anthropic_api_key")).toBe(true);
  });

  it("detects generic API key", () => {
    expect(
      hasScan("api_key: abcdefghijklmnopqrstuvwxyz", "generic_api_key")
    ).toBe(true);
  });

  it("detects private key header", () => {
    expect(hasScan("-----BEGIN RSA PRIVATE KEY-----", "private_key")).toBe(
      true
    );
    expect(hasScan("-----BEGIN PRIVATE KEY-----", "private_key")).toBe(true);
  });

  it("detects connection strings", () => {
    expect(hasScan("postgres://user:pass@host/db", "connection_string")).toBe(
      true
    );
    expect(hasScan("mongodb://localhost:27017/mydb", "connection_string")).toBe(
      true
    );
  });

  it("detects bearer tokens", () => {
    expect(
      hasScan(
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
        "bearer_token"
      )
    ).toBe(true);
  });
});

describe("scan — clean input", () => {
  it("returns empty array for clean text", () => {
    const hits = scan("This is a completely clean text with no secrets.");
    expect(hits).toEqual([]);
  });

  it("returns all matches for text with multiple secrets", () => {
    const text = [
      "aws_key=AKIAIOSFODNN7EXAMPLE",
      `token: ghp_${"A".repeat(36)}`,
    ].join("\n");
    const hits = scan(text);
    expect(hits.length).toBeGreaterThanOrEqual(2);
  });
});

describe("redact", () => {
  it("replaces secrets with [REDACTED:pattern_name]", () => {
    const token = `ghp_${"A".repeat(36)}`;
    const result = redact(`my token is ${token}`);

    const label = match(result)
      .when(
        (r) => r.redactionCount > 0,
        (r) => `redacted:${String(r.redactionCount)}`
      )
      .otherwise(() => "clean");

    expect(label).toBe("redacted:1");
    expect(result.text).toContain("[REDACTED:github_token]");
    expect(result.text).not.toContain(token);
  });

  it("tracks which patterns matched", () => {
    const text = `ghp_${"B".repeat(36)}`;
    const result = redact(text);
    expect(result.patternsMatched).toContain("github_token");
  });

  it("returns unchanged text for clean input", () => {
    const text = "nothing secret here";
    const result = redact(text);

    match(result)
      .when(
        (r) => r.redactionCount === 0,
        (r) => {
          expect(r.text).toBe(text);
          expect(r.patternsMatched).toEqual([]);
        }
      )
      .otherwise(() => {
        throw new Error("expected clean result");
      });
  });

  it("handles multiple patterns in same text", () => {
    const awsKey = "AKIAIOSFODNN7EXAMPLE";
    const ghToken = `ghp_${"C".repeat(36)}`;
    const text = `${awsKey} and ${ghToken}`;
    const result = redact(text);

    expect(result.redactionCount).toBeGreaterThanOrEqual(2);
    expect(result.text).not.toContain(awsKey);
    expect(result.text).not.toContain(ghToken);
  });
});

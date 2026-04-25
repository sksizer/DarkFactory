import type { DarkFactoryConfig } from "../../../config/types.js";

export class CodeEnv {
  declare readonly _brand: "CodeEnv";
  readonly repoRoot: string;
  readonly cwd: string;
  constructor(init: { repoRoot: string; cwd: string }) {
    this.repoRoot = init.repoRoot;
    this.cwd = init.cwd;
  }
}

export class WorktreeState {
  declare readonly _brand: "WorktreeState";
  readonly branch: string;
  readonly baseRef: string;
  readonly worktreePath: string | undefined;
  constructor(init: {
    branch: string;
    baseRef: string;
    worktreePath?: string | undefined;
  }) {
    this.branch = init.branch;
    this.baseRef = init.baseRef;
    this.worktreePath = init.worktreePath;
  }
}

export class PrRequest {
  declare readonly _brand: "PrRequest";
  readonly title: string;
  readonly body: string;
  constructor(init: { title: string; body: string }) {
    this.title = init.title;
    this.body = init.body;
  }
}

export class PrResult {
  declare readonly _brand: "PrResult";
  readonly url: string | undefined;
  constructor(init: { url?: string | undefined }) {
    this.url = init.url;
  }
}

export class ProjectConfig {
  declare readonly _brand: "ProjectConfig";
  readonly config: DarkFactoryConfig;
  constructor(config: DarkFactoryConfig) {
    this.config = config;
  }
}

export interface QualityCheckOutcome {
  readonly name: string;
  readonly success: boolean;
  readonly exitCode: number;
  readonly cmd: string;
  readonly stderr: string;
}

export class QualityResult {
  declare readonly _brand: "QualityResult";
  readonly checks: readonly QualityCheckOutcome[];
  readonly allPassed: boolean;
  constructor(checks: readonly QualityCheckOutcome[]) {
    this.checks = checks;
    this.allPassed = checks.every((c) => c.success);
  }
}

export class AgentResult {
  declare readonly _brand: "AgentResult";
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;
  readonly success: boolean;
  readonly failureReason: string | undefined;
  readonly toolCounts: Readonly<Record<string, number>>;
  readonly sentinel: string | undefined;
  readonly model: string;
  readonly invokeCount: number;
  constructor(init: {
    stdout: string;
    stderr: string;
    exitCode: number;
    success: boolean;
    failureReason?: string | undefined;
    toolCounts: Readonly<Record<string, number>>;
    sentinel?: string | undefined;
    model: string;
    invokeCount: number;
  }) {
    this.stdout = init.stdout;
    this.stderr = init.stderr;
    this.exitCode = init.exitCode;
    this.success = init.success;
    this.failureReason = init.failureReason;
    this.toolCounts = init.toolCounts;
    this.sentinel = init.sentinel;
    this.model = init.model;
    this.invokeCount = init.invokeCount;
  }
}

export interface OpenPrInfo {
  readonly number: number;
  readonly headRefName: string;
  readonly baseRefName: string;
  readonly title: string;
  readonly isDraft: boolean;
}

export class OpenPrList {
  declare readonly _brand: "OpenPrList";
  readonly prs: readonly OpenPrInfo[];
  constructor(init: { prs: readonly OpenPrInfo[] }) {
    this.prs = init.prs;
  }
}

export type PrUpdateOutcome =
  | { kind: "already-up-to-date" }
  | { kind: "fast-forward-merged" }
  | { kind: "merged-clean" }
  | { kind: "merged-with-agent"; sentinel: string | undefined }
  | { kind: "skipped"; reason: string }
  | { kind: "failed"; reason: string };

export interface PrUpdateEntry {
  readonly number: number;
  readonly headRefName: string;
  readonly baseRefName: string;
  readonly outcome: PrUpdateOutcome;
}

export class PrUpdateSummary {
  declare readonly _brand: "PrUpdateSummary";
  readonly entries: readonly PrUpdateEntry[];
  constructor(init: { entries: readonly PrUpdateEntry[] }) {
    this.entries = init.entries;
  }
}

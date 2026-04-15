/**
 * github.ts — GitHub CLI (gh) wrappers.
 *
 * All functions call exec(["gh", ...args]) via utils/subprocess.ts
 * and return Result types. Never throws.
 */

import { type Result, err, ok } from "../result.js";
import { type Timeout, ProcessTimeoutError, exec } from "./subprocess.js";

// ---------- Error and result types ----------

/** Non-zero gh CLI exit. */
export interface GhErr {
  readonly kind: "gh-err";
  readonly returncode: number;
  readonly stdout: string;
  readonly stderr: string;
  readonly cmd: readonly string[];
}

export type GhResult<T> = Result<T, GhErr>;
export type GhCheckResult = Result<null, GhErr | Timeout>;

// ---------- Supporting types ----------

export type PrState = "MERGED" | "OPEN" | "CLOSED" | "NONE";

export interface PrInfo {
  readonly number: number;
  readonly headRefName: string;
}

export interface CreatePrOptions {
  readonly base: string;
  readonly title: string;
  readonly body: string;
  readonly cwd: string;
}

export interface ReviewComment {
  readonly author: string;
  readonly body: string;
  readonly postedAt: string;
}

export interface ReviewThread {
  readonly threadId: string;
  readonly author: string;
  readonly path: string | null;
  readonly line: number | null;
  readonly body: string;
  readonly postedAt: string;
  readonly isResolved: boolean;
  readonly replies: readonly ReviewComment[];
  readonly reviewState: string | null;
  readonly replyTargetId: string | null;
}

export interface CommentFilters {
  readonly includeResolved?: boolean;
  readonly sinceCommit?: string;
  readonly reviewer?: string;
  readonly singleCommentId?: string;
  readonly botUsernames?: readonly string[];
}

export interface CommentReply {
  readonly threadId: string;
  readonly body: string;
}

export interface ReplyResult {
  readonly threadId: string;
  readonly success: boolean;
}

// ---------- Internal helpers ----------

function makeGhErr(
  returncode: number,
  stdout: string,
  stderr: string,
  cmd: readonly string[]
): GhErr {
  return { kind: "gh-err", returncode, stdout, stderr, cmd };
}

function timeoutToGhErr(t: Timeout): GhErr {
  return makeGhErr(-1, "", `timed out after ${String(t.timeout)}ms`, t.cmd);
}

// ---------- Gateway ----------

/**
 * Run gh with the given args. Returns GhCheckResult — never throws.
 * This is the single entry point for all gh subprocess calls.
 */
export async function ghRun(
  args: readonly string[],
  options: { cwd: string; timeout?: number }
): Promise<GhCheckResult> {
  const cmd = ["gh", ...args] as const;
  try {
    const result = await exec(cmd, {
      cwd: options.cwd,
      ...(options.timeout !== undefined ? { timeout: options.timeout } : {}),
    });
    if (result.exitCode !== 0) {
      return err(makeGhErr(result.exitCode, result.stdout, result.stderr, cmd));
    }
    return ok(null, result.stdout);
  } catch (e) {
    if (e instanceof ProcessTimeoutError) {
      return err({ kind: "timeout", cmd, timeout: e.timeoutMs } as Timeout);
    }
    return err(makeGhErr(-1, "", String(e), cmd));
  }
}

/**
 * Run gh and parse stdout as JSON on success.
 */
export async function ghJson<T>(
  args: readonly string[],
  options: { cwd: string; timeout?: number }
): Promise<GhResult<T>> {
  const result = await ghRun(args, options);
  if (result.kind === "err") {
    if (result.error.kind === "timeout") {
      return err(timeoutToGhErr(result.error));
    }
    return err(result.error);
  }
  try {
    const parsed = JSON.parse(result.stdout) as T;
    return ok(parsed, result.stdout);
  } catch {
    return err(
      makeGhErr(-1, result.stdout, "invalid JSON in stdout", ["gh", ...args])
    );
  }
}

// ---------- PR operations ----------

/**
 * Get the PR state for a branch. Returns "NONE" if no PRs found.
 */
export async function getPrState(
  branch: string,
  repoRoot: string
): Promise<GhResult<PrState>> {
  const result = await ghJson<Array<{ state: string }>>(
    ["pr", "list", "--head", branch, "--state", "all", "--json", "state"],
    { cwd: repoRoot }
  );
  if (result.kind === "err") return result;
  const prs = result.value;
  if (!Array.isArray(prs) || prs.length === 0) {
    return ok("NONE" as PrState, result.stdout);
  }
  const state = (prs[0]?.state ?? "NONE") as PrState;
  return ok(state, result.stdout);
}

/**
 * Fetch PR states for all branches in a single gh call.
 * Returns a Map from headRefName to PrState with precedence MERGED > CLOSED > OPEN.
 */
export async function fetchAllPrStates(
  repoRoot: string
): Promise<GhResult<Map<string, PrState>>> {
  const result = await ghJson<Array<{ headRefName: string; state: string }>>(
    [
      "pr",
      "list",
      "--state",
      "all",
      "--limit",
      "500",
      "--json",
      "headRefName,state",
    ],
    { cwd: repoRoot }
  );
  if (result.kind === "err") return result;
  const prs = result.value;
  if (!Array.isArray(prs)) {
    return err(
      makeGhErr(-1, result.stdout, "unexpected response format", [
        "gh",
        "pr",
        "list",
      ])
    );
  }
  const priority: Record<string, number> = { MERGED: 2, CLOSED: 1, OPEN: 0 };
  const states = new Map<string, PrState>();
  for (const pr of prs) {
    const branch = pr.headRefName;
    const state = pr.state;
    if (branch === "" || state === "") continue;
    const existing = states.get(branch);
    const newPriority = priority[state] ?? -1;
    const existingPriority =
      existing !== undefined ? (priority[existing] ?? -1) : -2;
    if (newPriority > existingPriority) {
      states.set(branch, state as PrState);
    }
  }
  return ok(states, result.stdout);
}

/**
 * Create a PR via gh pr create. Returns the PR URL on success.
 */
export async function createPr(
  options: CreatePrOptions
): Promise<GhResult<string>> {
  const result = await ghRun(
    [
      "pr",
      "create",
      "--base",
      options.base,
      "--title",
      options.title,
      "--body",
      options.body,
    ],
    { cwd: options.cwd }
  );
  if (result.kind === "err") {
    if (result.error.kind === "timeout") {
      return err(timeoutToGhErr(result.error));
    }
    return err(result.error);
  }
  const urlLine = result.stdout.trim().split("\n").pop() ?? "";
  return ok(urlLine, result.stdout);
}

/**
 * List open PRs as typed PrInfo records.
 */
export async function listOpenPrs(
  repoRoot: string,
  limit = 100
): Promise<GhResult<PrInfo[]>> {
  const result = await ghJson<Array<{ number: number; headRefName: string }>>(
    [
      "pr",
      "list",
      "--state",
      "open",
      "--limit",
      String(limit),
      "--json",
      "number,headRefName",
    ],
    { cwd: repoRoot }
  );
  if (result.kind === "err") return result;
  const prs = result.value;
  if (!Array.isArray(prs)) {
    return err(
      makeGhErr(-1, result.stdout, "unexpected response format", [
        "gh",
        "pr",
        "list",
      ])
    );
  }
  const infos: PrInfo[] = prs.map((pr) => ({
    number: pr.number,
    headRefName: pr.headRefName,
  }));
  return ok(infos, result.stdout);
}

/**
 * Close a PR by number, optionally posting a comment.
 */
export async function closePr(
  prNumber: number,
  repoRoot: string,
  comment?: string
): Promise<GhCheckResult> {
  const args: string[] = ["pr", "close", String(prNumber)];
  if (comment !== undefined && comment !== "") args.push("--comment", comment);
  return ghRun(args, { cwd: repoRoot });
}

/**
 * Return { owner, name } for the current repo via gh repo view.
 */
export async function repoNwo(
  cwd: string
): Promise<GhResult<{ owner: string; name: string }>> {
  const result = await ghRun(
    ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
    { cwd }
  );
  if (result.kind === "err") {
    if (result.error.kind === "timeout") {
      return err(timeoutToGhErr(result.error));
    }
    return err(result.error);
  }
  const nwo = result.stdout.trim();
  const slashIdx = nwo.indexOf("/");
  if (slashIdx === -1) {
    return err(
      makeGhErr(-1, result.stdout, "unexpected nameWithOwner format", [
        "gh",
        "repo",
        "view",
      ])
    );
  }
  const owner = nwo.slice(0, slashIdx);
  const name = nwo.slice(slashIdx + 1);
  return ok({ owner, name }, result.stdout);
}

// ---------- GraphQL and comment operations ----------

/**
 * Run a gh api graphql call and return parsed JSON.
 */
export async function graphqlFetch(
  query: string,
  variables: Record<string, string>,
  cwd: string
): Promise<GhResult<unknown>> {
  const args: string[] = ["api", "graphql"];
  for (const [key, value] of Object.entries(variables)) {
    args.push("-F", `${key}=${value}`);
  }
  args.push("-f", `query=${query}`);
  return ghJson<unknown>(args, { cwd });
}

/**
 * POST a reply to a PR comment via gh api.
 */
export async function postReply(
  endpoint: string,
  body: string,
  cwd: string
): Promise<GhCheckResult> {
  return ghRun(["api", "--method", "POST", endpoint, "-f", `body=${body}`], {
    cwd,
  });
}

// ---------- PR comment fetching ----------

const _GRAPHQL_QUERY = `
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          isResolved
          path
          line
          originalLine
          comments(first: 100) {
            nodes {
              id
              databaseId
              body
              createdAt
              author { login }
            }
          }
        }
      }
      reviews(first: 100) {
        nodes {
          id
          body
          submittedAt
          state
          author { login }
        }
      }
      comments(first: 100) {
        nodes {
          id
          body
          createdAt
          author { login }
        }
      }
    }
  }
}
`;

interface GhComment {
  id?: string;
  databaseId?: number;
  body?: string;
  createdAt?: string;
  author?: { login?: string };
}

interface GhReviewThread {
  isResolved?: boolean;
  path?: string;
  line?: number;
  originalLine?: number;
  comments?: { nodes?: GhComment[] };
}

interface GhReview {
  id?: string;
  body?: string;
  submittedAt?: string;
  state?: string;
  author?: { login?: string };
}

interface GhPrData {
  data?: {
    repository?: {
      pullRequest?: {
        reviewThreads?: { nodes?: GhReviewThread[] };
        reviews?: { nodes?: GhReview[] };
        comments?: { nodes?: GhComment[] };
      };
    };
  };
}

function parseThreads(raw: {
  reviewThreads: GhReviewThread[];
  reviews: GhReview[];
  comments: GhComment[];
}): ReviewThread[] {
  const threads: ReviewThread[] = [];

  // 1. Inline review threads
  for (let idx = 0; idx < raw.reviewThreads.length; idx++) {
    const rt = raw.reviewThreads[idx];
    if (rt === undefined) continue;
    const comments = rt.comments?.nodes ?? [];
    if (comments.length === 0) continue;
    const first = comments[0];
    if (first === undefined) continue;
    const author = first.author?.login ?? "";
    const body = first.body ?? "";
    const postedAt = first.createdAt ?? "";
    const path = rt.path ?? null;
    const line = rt.line ?? rt.originalLine ?? null;
    const isResolved = rt.isResolved ?? false;
    const replies: ReviewComment[] = comments.slice(1).map((c) => ({
      author: c.author?.login ?? "",
      body: c.body ?? "",
      postedAt: c.createdAt ?? "",
    }));
    const threadId = first.id ?? `rt-${String(idx)}`;
    const replyTargetId =
      first.databaseId !== undefined ? String(first.databaseId) : null;
    threads.push({
      threadId,
      author,
      path,
      line,
      body,
      postedAt,
      isResolved,
      replies,
      reviewState: null,
      replyTargetId,
    });
  }

  // 2. Review summaries
  for (let idx = 0; idx < raw.reviews.length; idx++) {
    const rev = raw.reviews[idx];
    if (rev === undefined) continue;
    const body = rev.body ?? "";
    if (body.trim() === "") continue; // skip empty reviews
    const author = rev.author?.login ?? "";
    const postedAt = rev.submittedAt ?? "";
    const state = rev.state ?? null;
    const threadId = rev.id ?? `review-${String(idx)}`;
    threads.push({
      threadId,
      author,
      path: null,
      line: null,
      body,
      postedAt,
      isResolved: false,
      replies: [],
      reviewState: state,
      replyTargetId: null,
    });
  }

  // 3. Issue-level PR comments
  for (let idx = 0; idx < raw.comments.length; idx++) {
    const c = raw.comments[idx];
    if (c === undefined) continue;
    const body = c.body ?? "";
    const author = c.author?.login ?? "";
    const postedAt = c.createdAt ?? "";
    const threadId = c.id ?? `comment-${String(idx)}`;
    threads.push({
      threadId,
      author,
      path: null,
      line: null,
      body,
      postedAt,
      isResolved: false,
      replies: [],
      reviewState: null,
      replyTargetId: null,
    });
  }

  return threads;
}

function applyFilters(
  threads: ReviewThread[],
  filters: CommentFilters
): ReviewThread[] {
  if (filters.singleCommentId !== undefined) {
    return threads.filter((t) => t.threadId === filters.singleCommentId);
  }

  let result = [...threads];

  if (filters.includeResolved !== true) {
    result = result.filter((t) => !t.isResolved);
  }

  if (filters.reviewer !== undefined) {
    const reviewer = filters.reviewer;
    result = result.filter((t) => t.author === reviewer);
  }

  if (filters.botUsernames !== undefined && filters.botUsernames.length > 0) {
    const bots = new Set(filters.botUsernames);
    result = result.filter((t) => {
      if (bots.has(t.author)) return false;
      if (t.body.trimStart().startsWith("[harness]")) return false;
      return true;
    });
  }

  return result;
}

/**
 * Fetch and filter PR review threads from GitHub.
 */
export async function fetchPrComments(
  prNumber: number,
  cwd: string,
  filters?: CommentFilters
): Promise<GhResult<ReviewThread[]>> {
  const nwoResult = await repoNwo(cwd);
  if (nwoResult.kind === "err") return nwoResult;
  const { owner, name } = nwoResult.value;

  const variables: Record<string, string> = {
    owner,
    name,
    number: String(prNumber),
  };

  const gqlResult = await graphqlFetch(_GRAPHQL_QUERY, variables, cwd);
  if (gqlResult.kind === "err") return gqlResult;

  const payload = gqlResult.value as GhPrData;
  const pr = payload.data?.repository?.pullRequest;
  if (pr === undefined) {
    return err(
      makeGhErr(-1, "", "unexpected GraphQL response shape", [
        "gh",
        "api",
        "graphql",
      ])
    );
  }

  const rawData = {
    reviewThreads: pr.reviewThreads?.nodes ?? [],
    reviews: pr.reviews?.nodes ?? [],
    comments: pr.comments?.nodes ?? [],
  };

  const threads = parseThreads(rawData);
  const filtered = applyFilters(threads, filters ?? {});
  return ok(filtered, "");
}

/**
 * Post replies to PR review comment threads.
 * Returns ReplyResult[] with success/failure for each reply.
 */
export async function postCommentReplies(
  prNumber: number,
  replies: CommentReply[],
  threads: ReviewThread[],
  commitSha: string,
  cwd: string
): Promise<GhResult<ReplyResult[]>> {
  const targetByThreadId = new Map(
    threads.map((t) => [t.threadId, t.replyTargetId])
  );

  const results: ReplyResult[] = [];

  for (const reply of replies) {
    const targetId = targetByThreadId.get(reply.threadId);
    if (targetId === null || targetId === undefined) {
      results.push({ threadId: reply.threadId, success: false });
      continue;
    }

    const prefix = `[harness] addressed in ${commitSha}: `;
    const body = prefix + reply.body;
    const endpoint = `repos/{owner}/{repo}/pulls/${String(prNumber)}/comments/${targetId}/replies`;

    const postResult = await postReply(endpoint, body, cwd);
    results.push({
      threadId: reply.threadId,
      success: postResult.kind === "ok",
    });
  }

  return ok(results, "");
}

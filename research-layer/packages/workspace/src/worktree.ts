/**
 * 本地 Git worktree 管理：为每次实验尝试创建隔离工作区。
 *
 * 设计约束：
 * - 只操作本地 git，不访问远端、不读取或写入长期凭据。
 * - 不使用 `--force`，不自动删除分支，不自动 reset/clean。
 * - 路径由实验 ID 与尝试号派生，禁止路径逃逸。
 * - 所有 git 调用带超时，并以参数数组执行，不经过 shell。
 * - 脏工作树拒绝删除，保证失败现场可追溯。
 */

import { existsSync, mkdirSync, realpathSync, statSync } from "node:fs";
import { dirname, resolve, sep } from "node:path";
import { spawnSync } from "node:child_process";

export type WorktreeState = "created" | "reused" | "removed" | "absent";

export type WorktreeErrorCode =
  | "INVALID_ARGUMENT"
  | "PATH_ESCAPE"
  | "GIT_UNAVAILABLE"
  | "NOT_A_REPOSITORY"
  | "NO_COMMITS"
  | "GIT_FAILED"
  | "TIMEOUT"
  | "EXISTS"
  | "BRANCH_EXISTS"
  | "NOT_FOUND"
  | "DIRTY";

export interface WorktreeError {
  code: WorktreeErrorCode;
  message: string;
  detail?: string;
}

export type WorktreeResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: WorktreeError };

export interface WorktreeRecord {
  worktree_id: string;
  experiment_id: string;
  attempt: number;
  repo_root: string;
  branch: string;
  path: string;
  base_commit: string | null;
  state: WorktreeState;
  recorded_at: string;
}

export interface WorktreeTargetInput {
  repoRoot: string;
  experiment_id: string;
  attempt: number;
  /** 默认 `<repoRoot>/.worktrees`。 */
  baseDir?: string;
}

export interface CreateWorktreeInput extends WorktreeTargetInput {
  /** 默认 HEAD。 */
  baseRef?: string;
  timeoutMs?: number;
  now?: () => Date;
}

export interface RemoveWorktreeInput extends WorktreeTargetInput {
  timeoutMs?: number;
  now?: () => Date;
}

export interface WorktreeLocation {
  branch: string;
  path: string;
  worktree_id: string;
}

interface GitWorktreeEntry {
  path: string;
  head: string | null;
  branch: string | null;
}

interface GitRunSuccess {
  ok: true;
  stdout: string;
}

interface GitRunFailure {
  ok: false;
  error: WorktreeError;
}

type GitRunResult = GitRunSuccess | GitRunFailure;

const DEFAULT_TIMEOUT_MS = 30_000;

function fail(code: WorktreeErrorCode, message: string, detail?: string): GitRunFailure {
  return { ok: false, error: { code, message, detail } };
}

function failResult<T>(code: WorktreeErrorCode, message: string, detail?: string): WorktreeResult<T> {
  return { ok: false, error: { code, message, detail } };
}

function slugifyExperimentId(value: string): string {
  return value
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64)
    .replace(/-+$/g, "");
}

function canonicalPath(value: string): string {
  try {
    return realpathSync(value);
  } catch {
    return resolve(value);
  }
}

/**
 * 计算 worktree 的确定性位置，不访问文件系统。
 *
 * 实验 ID 会被规范化；规范化后为空、尝试号非法或路径逃逸时返回错误。
 */
export function worktreeLocation(input: WorktreeTargetInput): WorktreeResult<WorktreeLocation> {
  if (typeof input.experiment_id !== "string" || input.experiment_id.trim().length === 0) {
    return failResult("INVALID_ARGUMENT", "experiment_id 不能为空");
  }
  if (!Number.isInteger(input.attempt) || input.attempt < 1) {
    return failResult("INVALID_ARGUMENT", "attempt 必须是大于等于 1 的整数");
  }

  const slug = slugifyExperimentId(input.experiment_id);
  if (!slug) {
    return failResult(
      "INVALID_ARGUMENT",
      "experiment_id 规范化后为空，无法生成安全的 branch 或路径",
    );
  }

  const repoRoot = resolve(input.repoRoot);
  const baseDir = resolve(repoRoot, input.baseDir ?? ".worktrees");
  const worktreePath = resolve(baseDir, `${slug}-attempt-${input.attempt}`);

  if (worktreePath === baseDir || !worktreePath.startsWith(`${baseDir}${sep}`)) {
    return failResult("PATH_ESCAPE", "worktree 路径逃逸出 baseDir");
  }

  return {
    ok: true,
    value: {
      branch: `exp/${slug}/attempt-${input.attempt}`,
      path: worktreePath,
      worktree_id: `${input.experiment_id}:attempt-${input.attempt}`,
    },
  };
}

function runGit(args: string[], cwd: string, timeoutMs: number): GitRunResult {
  const result = spawnSync("git", args, {
    cwd,
    encoding: "utf8",
    timeout: timeoutMs,
    maxBuffer: 4 * 1024 * 1024,
    env: {
      ...process.env,
      GIT_TERMINAL_PROMPT: "0",
      GIT_ASKPASS: "echo",
      GIT_OPTIONAL_LOCKS: "0",
      LC_ALL: "C",
    },
  });

  if (result.error) {
    const code = (result.error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") return fail("GIT_UNAVAILABLE", "未找到 git 可执行文件");
    if (code === "ETIMEDOUT") return fail("TIMEOUT", `git ${args[0] ?? ""} 超时`);
    return fail("GIT_FAILED", `git ${args[0] ?? ""} 执行失败`, result.error.message);
  }

  if (result.status !== 0) {
    return fail(
      "GIT_FAILED",
      `git ${args.join(" ")} 返回 ${result.status ?? "unknown"}`,
      String(result.stderr ?? "").trim() || undefined,
    );
  }

  return { ok: true, stdout: String(result.stdout ?? "") };
}

function resolveRepo(repoRoot: string, timeoutMs: number): WorktreeResult<string> {
  const root = resolve(repoRoot);
  if (!existsSync(root)) {
    return failResult("INVALID_ARGUMENT", `仓库路径不存在: ${root}`);
  }
  if (!statSync(root).isDirectory()) {
    return failResult("INVALID_ARGUMENT", `仓库路径不是目录: ${root}`);
  }

  const result = runGit(["rev-parse", "--show-toplevel"], root, timeoutMs);
  if (!result.ok) {
    if (result.error.code === "GIT_UNAVAILABLE" || result.error.code === "TIMEOUT") {
      return { ok: false, error: result.error };
    }
    return failResult("NOT_A_REPOSITORY", "路径不是 git 仓库", result.error.detail);
  }

  try {
    return { ok: true, value: realpathSync(result.stdout.trim()) };
  } catch {
    return { ok: true, value: resolve(result.stdout.trim()) };
  }
}

function parseWorktreeList(text: string): GitWorktreeEntry[] {
  return text
    .split(/\n\s*\n/)
    .map((block) => {
      let path = "";
      let head: string | null = null;
      let branch: string | null = null;
      for (const line of block.split("\n")) {
        if (line.startsWith("worktree ")) path = line.slice("worktree ".length).trim();
        else if (line.startsWith("HEAD ")) head = line.slice("HEAD ".length).trim();
        else if (line.startsWith("branch ")) branch = line.slice("branch ".length).trim();
      }
      return { path, head, branch };
    })
    .filter((entry) => entry.path.length > 0);
}

function listWorktrees(repoRoot: string, timeoutMs: number): WorktreeResult<GitWorktreeEntry[]> {
  const result = runGit(["worktree", "list", "--porcelain"], repoRoot, timeoutMs);
  if (!result.ok) return { ok: false, error: result.error };
  return { ok: true, value: parseWorktreeList(result.stdout) };
}

function findWorktree(
  entries: GitWorktreeEntry[],
  worktreePath: string,
): GitWorktreeEntry | undefined {
  const target = canonicalPath(worktreePath);
  return entries.find((entry) => canonicalPath(entry.path) === target);
}

/**
 * 创建或复用某次实验尝试的 worktree。
 *
 * - 已登记且分支匹配 → `reused`，不执行任何写操作。
 * - 路径被其他分支占用 → `EXISTS`。
 * - 分支已存在但未登记 → `BRANCH_EXISTS`，避免复用来源不明的分支。
 */
export function createExperimentWorktree(
  input: CreateWorktreeInput,
): WorktreeResult<WorktreeRecord> {
  const timeoutMs = input.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const now = input.now ?? (() => new Date());

  const repo = resolveRepo(input.repoRoot, timeoutMs);
  if (!repo.ok) return repo;
  const repoRoot = repo.value;

  const location = worktreeLocation({ ...input, repoRoot });
  if (!location.ok) return location;
  const { branch, path: worktreePath, worktree_id } = location.value;

  const worktrees = listWorktrees(repoRoot, timeoutMs);
  if (!worktrees.ok) return worktrees;

  const existing = findWorktree(worktrees.value, worktreePath);
  if (existing) {
    const expectedBranch = `refs/heads/${branch}`;
    if (existing.branch !== expectedBranch) {
      return failResult(
        "EXISTS",
        "worktree 路径已被其他分支占用",
        existing.branch ?? "detached HEAD",
      );
    }
    if (!existsSync(existing.path)) {
      return failResult(
        "NOT_FOUND",
        "worktree 元数据存在但目录缺失，需要人工执行 git worktree prune",
        existing.path,
      );
    }
    return {
      ok: true,
      value: {
        worktree_id,
        experiment_id: input.experiment_id,
        attempt: input.attempt,
        repo_root: repoRoot,
        branch,
        path: existing.path,
        base_commit: existing.head,
        state: "reused",
        recorded_at: now().toISOString(),
      },
    };
  }

  if (existsSync(worktreePath)) {
    return failResult(
      "EXISTS",
      "worktree 路径已存在，但未登记到当前仓库",
      worktreePath,
    );
  }

  const baseRef = input.baseRef ?? "HEAD";
  if (baseRef.startsWith("-") || /\s/.test(baseRef)) {
    return failResult("INVALID_ARGUMENT", `非法 baseRef: ${baseRef}`);
  }
  const base = runGit(["rev-parse", "--verify", `${baseRef}^{commit}`], repoRoot, timeoutMs);
  if (!base.ok) {
    const detail = base.error.detail ?? "";
    if (baseRef === "HEAD" && /needed a single revision|unknown revision|bad revision/i.test(detail)) {
      return failResult("NO_COMMITS", "仓库没有任何提交，无法创建 worktree");
    }
    return failResult("GIT_FAILED", `无法解析 baseRef: ${baseRef}`, base.error.detail);
  }
  const baseCommit = base.stdout.trim();
  if (!baseCommit) {
    return failResult("NO_COMMITS", "仓库没有任何提交，无法创建 worktree");
  }

  const branchList = runGit(["branch", "--list", branch], repoRoot, timeoutMs);
  if (!branchList.ok) return { ok: false, error: branchList.error };
  if (branchList.stdout.trim().length > 0) {
    return failResult(
      "BRANCH_EXISTS",
      `分支已存在但未登记为 worktree: ${branch}`,
      "请人工确认该分支来源，或改用新的尝试号",
    );
  }

  mkdirSync(dirname(worktreePath), { recursive: true });

  const added = runGit(
    ["worktree", "add", "-b", branch, worktreePath, baseCommit],
    repoRoot,
    timeoutMs,
  );
  if (!added.ok) return { ok: false, error: added.error };

  return {
    ok: true,
    value: {
      worktree_id,
      experiment_id: input.experiment_id,
      attempt: input.attempt,
      repo_root: repoRoot,
      branch,
      path: worktreePath,
      base_commit: baseCommit,
      state: "created",
      recorded_at: now().toISOString(),
    },
  };
}

/**
 * 清理某次实验尝试的 worktree。
 *
 * - 脏工作树返回 `DIRTY`，不删除。
 * - 目录缺失但元数据仍在 → `NOT_FOUND`，提示人工执行 `git worktree prune`。
 * - 已不存在 → `absent`，保证清理可重入。
 * - 分支保留，不自动删除，避免丢失证据。
 */
export function removeExperimentWorktree(
  input: RemoveWorktreeInput,
): WorktreeResult<WorktreeRecord> {
  const timeoutMs = input.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const now = input.now ?? (() => new Date());

  const repo = resolveRepo(input.repoRoot, timeoutMs);
  if (!repo.ok) return repo;
  const repoRoot = repo.value;

  const location = worktreeLocation({ ...input, repoRoot });
  if (!location.ok) return location;
  const { branch, path: worktreePath, worktree_id } = location.value;

  const recordBase = {
    worktree_id,
    experiment_id: input.experiment_id,
    attempt: input.attempt,
    repo_root: repoRoot,
    branch,
    path: worktreePath,
  };

  const worktrees = listWorktrees(repoRoot, timeoutMs);
  if (!worktrees.ok) return worktrees;

  const existing = findWorktree(worktrees.value, worktreePath);
  if (!existing) {
    if (existsSync(worktreePath)) {
      return failResult(
        "NOT_FOUND",
        "worktree 路径存在但未登记到当前仓库",
        worktreePath,
      );
    }
    return {
      ok: true,
      value: {
        ...recordBase,
        base_commit: null,
        state: "absent",
        recorded_at: now().toISOString(),
      },
    };
  }

  const expectedBranch = `refs/heads/${branch}`;
  if (existing.branch !== expectedBranch) {
    return failResult(
      "EXISTS",
      "worktree 路径已被其他分支占用",
      existing.branch ?? "detached HEAD",
    );
  }

  if (!existsSync(existing.path)) {
    return failResult(
      "NOT_FOUND",
      "worktree 目录缺失，需要人工执行 git worktree prune",
      existing.path,
    );
  }

  const status = runGit(["-C", existing.path, "status", "--porcelain"], repoRoot, timeoutMs);
  if (!status.ok) return { ok: false, error: status.error };
  if (status.stdout.trim().length > 0) {
    return failResult(
      "DIRTY",
      "worktree 存在未提交变更，拒绝删除",
      status.stdout.trim(),
    );
  }

  const head = runGit(["-C", existing.path, "rev-parse", "HEAD"], repoRoot, timeoutMs);
  const baseCommit = head.ok ? head.stdout.trim() : null;

  const removed = runGit(["worktree", "remove", existing.path], repoRoot, timeoutMs);
  if (!removed.ok) return { ok: false, error: removed.error };

  return {
    ok: true,
    value: {
      ...recordBase,
      path: existing.path,
      base_commit: baseCommit,
      state: "removed",
      recorded_at: now().toISOString(),
    },
  };
}

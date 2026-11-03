/**
 * 失败库：把失败记录整理成可去重、可检索、可统计的条目。
 *
 * 本模块是纯函数，不做 IO。持久化由 pipeline 写入对象存储，
 * 查询索引由上层服务或后续数据库实现替换，接口保持稳定。
 */

import type { DecisionAction } from "./decision.ts";
import type { FailureCategory, FailureRecord, FailureStage } from "./failure.ts";
import { FAILURE_CATEGORIES } from "./failure.ts";

export interface FailureEntry {
  entry_id: string;
  task_id: string;
  experiment_id: string;
  run_id: string;
  category: FailureCategory;
  code: string;
  message: string;
  retryable: boolean;
  stage: FailureStage;
  decision: DecisionAction | null;
  occurred_at: string;
}

export interface FailureCandidate {
  task_id: string;
  experiment_id: string;
  run_id: string;
  failure: FailureRecord;
  decision?: DecisionAction | null;
  occurred_at: string;
}

export interface FailureQuery {
  taskId?: string;
  experimentId?: string;
  category?: FailureCategory;
  stage?: FailureStage;
  code?: string;
  retryable?: boolean;
  /** 在 code、message、category、experiment_id 中做不区分大小写的包含匹配。 */
  text?: string;
  since?: string;
  until?: string;
  limit?: number;
}

export interface FailureStats {
  total: number;
  byCategory: Record<FailureCategory, number>;
  byCode: Record<string, number>;
}

export function failureEntryId(runId: string, failure: FailureRecord): string {
  return `${runId}:${failure.stage}:${failure.code}`;
}

/**
 * 建立失败库条目。
 *
 * 以 `run_id + stage + code` 去重；重复条目保留最后一次写入，
 * 便于同一轮重放时更新消息。结果按发生时间升序排列。
 */
export function buildFailureEntries(candidates: FailureCandidate[]): FailureEntry[] {
  const byId = new Map<string, FailureEntry>();
  for (const candidate of candidates) {
    const entryId = failureEntryId(candidate.run_id, candidate.failure);
    byId.set(entryId, {
      entry_id: entryId,
      task_id: candidate.task_id,
      experiment_id: candidate.experiment_id,
      run_id: candidate.run_id,
      category: candidate.failure.category,
      code: candidate.failure.code,
      message: candidate.failure.message,
      retryable: candidate.failure.retryable,
      stage: candidate.failure.stage,
      decision: candidate.decision ?? null,
      occurred_at: candidate.occurred_at,
    });
  }
  return [...byId.values()].sort((left, right) => {
    const time = left.occurred_at.localeCompare(right.occurred_at);
    return time !== 0 ? time : left.entry_id.localeCompare(right.entry_id);
  });
}

/**
 * 检索失败库。结果按发生时间倒序，便于先看到最近失败。
 */
export function queryFailureLibrary(
  entries: readonly FailureEntry[],
  query: FailureQuery = {},
): FailureEntry[] {
  const text = query.text?.toLowerCase();
  const since = query.since ? Date.parse(query.since) : Number.NaN;
  const until = query.until ? Date.parse(query.until) : Number.NaN;

  const matched = entries.filter((entry) => {
    if (query.taskId && entry.task_id !== query.taskId) return false;
    if (query.experimentId && entry.experiment_id !== query.experimentId) return false;
    if (query.category && entry.category !== query.category) return false;
    if (query.stage && entry.stage !== query.stage) return false;
    if (query.code && entry.code !== query.code) return false;
    if (query.retryable !== undefined && entry.retryable !== query.retryable) return false;

    if (text) {
      const haystack = [
        entry.code,
        entry.message,
        entry.category,
        entry.experiment_id,
        entry.run_id,
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(text)) return false;
    }

    const occurred = Date.parse(entry.occurred_at);
    if (Number.isFinite(since) && occurred < since) return false;
    if (Number.isFinite(until) && occurred > until) return false;
    return true;
  });

  matched.sort((left, right) => {
    const time = right.occurred_at.localeCompare(left.occurred_at);
    return time !== 0 ? time : left.entry_id.localeCompare(right.entry_id);
  });

  if (query.limit !== undefined && query.limit >= 0) {
    return matched.slice(0, query.limit);
  }
  return matched;
}

export function failureStats(entries: readonly FailureEntry[]): FailureStats {
  const byCategory = Object.fromEntries(
    FAILURE_CATEGORIES.map((category) => [category, 0]),
  ) as Record<FailureCategory, number>;
  const byCode: Record<string, number> = {};

  for (const entry of entries) {
    byCategory[entry.category] += 1;
    byCode[entry.code] = (byCode[entry.code] ?? 0) + 1;
  }

  return { total: entries.length, byCategory, byCode };
}

/**
 * 跨循环/跨产物合并失败条目。
 *
 * 以 entry_id 去重；同一 ID 保留 occurred_at 较新的版本（重放可能更新消息），
 * 时间也相同则后写入者优先。返回按时间倒序，便于检索展示。
 */
export function mergeFailureEntries(
  entries: readonly FailureEntry[],
): FailureEntry[] {
  const byId = new Map<string, FailureEntry>();
  for (const entry of entries) {
    const existing = byId.get(entry.entry_id);
    if (!existing) {
      byId.set(entry.entry_id, entry);
      continue;
    }
    if (Date.parse(entry.occurred_at) >= Date.parse(existing.occurred_at)) {
      byId.set(entry.entry_id, entry);
    }
  }
  return [...byId.values()].sort((left, right) => {
    const time = right.occurred_at.localeCompare(left.occurred_at);
    return time !== 0 ? time : left.entry_id.localeCompare(right.entry_id);
  });
}

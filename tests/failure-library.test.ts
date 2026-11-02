import { test } from "node:test";
import assert from "node:assert/strict";

import {
  buildFailureEntries,
  failureStats,
  queryFailureLibrary,
} from "../packages/domain/src/index.ts";
import type { FailureRecord } from "../packages/domain/src/index.ts";

function failure(overrides: Partial<FailureRecord> = {}): FailureRecord {
  return {
    category: "hypothesis",
    code: "E_EFFECT_NOT_REACHED",
    message: "主指标未达到最小可观测效应",
    retryable: false,
    stage: "decision",
    ...overrides,
  };
}

function candidate(
  runId: string,
  occurredAt: string,
  record: FailureRecord = failure(),
) {
  return {
    task_id: "TASK-1",
    experiment_id: "EXP-1",
    run_id: runId,
    failure: record,
    decision: "discard" as const,
    occurred_at: occurredAt,
  };
}

test("失败库：按 run/stage/code 去重并保留最后消息", () => {
  const entries = buildFailureEntries([
    candidate("run-1", "2026-10-30T01:00:00.000Z", failure({ message: "旧消息" })),
    candidate("run-1", "2026-10-30T02:00:00.000Z", failure({ message: "新消息" })),
    candidate(
      "run-2",
      "2026-10-30T03:00:00.000Z",
      failure({ category: "environment", code: "TIMEOUT", stage: "submit", retryable: true }),
    ),
  ]);

  assert.equal(entries.length, 2);
  assert.equal(entries[0].run_id, "run-1");
  assert.equal(entries[0].message, "新消息");
  assert.equal(entries[1].category, "environment");
  assert.equal(entries[1].retryable, true);
  assert.equal(entries[0].entry_id, "run-1:decision:E_EFFECT_NOT_REACHED");
});

test("失败库：按类别、文本、可重试性与时间检索", () => {
  const entries = buildFailureEntries([
    candidate("run-1", "2026-10-30T01:00:00.000Z"),
    candidate(
      "run-2",
      "2026-10-30T02:00:00.000Z",
      failure({ category: "policy", code: "R-DATA-RESIDENCY", message: "受限数据不能离开驻留地" }),
    ),
    candidate(
      "run-3",
      "2026-10-30T03:00:00.000Z",
      failure({ category: "environment", code: "TIMEOUT", stage: "submit", retryable: true }),
    ),
  ]);

  assert.deepEqual(
    queryFailureLibrary(entries, { category: "policy" }).map((entry) => entry.run_id),
    ["run-2"],
  );
  assert.deepEqual(
    queryFailureLibrary(entries, { text: "驻留" }).map((entry) => entry.run_id),
    ["run-2"],
  );
  assert.deepEqual(
    queryFailureLibrary(entries, { retryable: true }).map((entry) => entry.run_id),
    ["run-3"],
  );
  assert.deepEqual(
    queryFailureLibrary(entries, { since: "2026-10-30T01:30:00.000Z" }).map((entry) => entry.run_id),
    ["run-3", "run-2"],
  );
  assert.deepEqual(
    queryFailureLibrary(entries, { limit: 1 }).map((entry) => entry.run_id),
    ["run-3"],
  );
});

test("失败库：统计覆盖全部类别", () => {
  const entries = buildFailureEntries([
    candidate("run-1", "2026-10-30T01:00:00.000Z"),
    candidate("run-2", "2026-10-30T02:00:00.000Z"),
    candidate(
      "run-3",
      "2026-10-30T03:00:00.000Z",
      failure({ category: "unknown", code: "UNKNOWN_EXECUTION", stage: "unknown_execution" }),
    ),
  ]);

  const stats = failureStats(entries);
  assert.equal(stats.total, 3);
  assert.equal(stats.byCategory.hypothesis, 2);
  assert.equal(stats.byCategory.unknown, 1);
  assert.equal(stats.byCategory.policy, 0);
  assert.equal(stats.byCode.E_EFFECT_NOT_REACHED, 2);
  assert.equal(stats.byCode.UNKNOWN_EXECUTION, 1);
});

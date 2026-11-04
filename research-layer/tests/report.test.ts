import { test } from "node:test";
import assert from "node:assert/strict";

import { createStubStack } from "../adapters/stub/src/index.ts";
import { buildDailyReport, writeDailyReport } from "../packages/pipeline/src/index.ts";
import type { LoopAttemptRecord, LoopSummary } from "../packages/pipeline/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

function attempt(overrides: Partial<LoopAttemptRecord> = {}): LoopAttemptRecord {
  return {
    attempt: 1,
    run_id: "loop-1-run-1",
    experiment_id: "EXP-A",
    state: "succeeded",
    decision: "keep",
    reason: "所有预注册条件通过",
    cost: 2,
    currency: "CNY",
    manifest_ref: "stub://artifacts/manifest.json",
    error_code: null,
    started_at: "2026-10-30T01:00:00.000Z",
    finished_at: "2026-10-30T01:10:00.000Z",
    ...overrides,
  };
}

function summary(overrides: Partial<LoopSummary> = {}): LoopSummary {
  return {
    loop_id: "EXP-A-loop-1",
    task_id: "TASK-1",
    experiment_id: "EXP-A",
    stop_reason: "kept",
    stop_detail: "第 1 轮保留",
    attempts: [],
    total_cost: 0,
    currency: "CNY",
    budget_total: 100,
    remaining_budget: 100,
    started_at: "2026-10-30T01:00:00.000Z",
    finished_at: "2026-10-30T01:10:00.000Z",
    ...overrides,
  };
}

const keptLoop = summary({
  attempts: [
    attempt(),
    attempt({
      attempt: 2,
      run_id: "loop-1-run-2",
      state: "failed",
      decision: "discard",
      reason: "主指标未达到最小可观测效应",
      cost: 1,
      failure: {
        category: "hypothesis",
        code: "E_EFFECT_NOT_REACHED",
        message: "主指标未达到最小可观测效应",
        retryable: false,
        stage: "decision",
      },
    }),
  ],
  total_cost: 3,
  remaining_budget: 97,
});

const escalatedLoop = summary({
  loop_id: "EXP-B-loop-1",
  experiment_id: "EXP-B",
  stop_reason: "escalated",
  stop_detail: "执行状态未知，禁止自动重试",
  attempts: [
    attempt({
      attempt: 1,
      run_id: "EXP-B-run-1",
      experiment_id: "EXP-B",
      state: "unknown_execution",
      decision: "escalate",
      reason: "执行状态未知，必须人工对账，禁止重试",
      cost: 0,
      failure: {
        category: "unknown",
        code: "UNKNOWN_EXECUTION",
        message: "供应商未返回可判定证据",
        retryable: false,
        stage: "unknown_execution",
      },
    }),
  ],
});

test("日报：聚合实验、关键结果、负结果、失败与人工决策", () => {
  const report = buildDailyReport({
    date: "2026-10-30",
    generatedAt: "2026-10-30T10:00:00.000Z",
    goals: ["验证预热假设"],
    planned: ["扩展消融实验"],
    loops: [keptLoop, escalatedLoop],
  });

  assert.equal(report.report_id, "daily-2026-10-30");
  assert.equal(report.experiments.length, 2);
  const expA = report.experiments.find((item) => item.experiment_id === "EXP-A");
  assert.ok(expA);
  assert.equal(expA.attempts, 2);
  assert.equal(expA.kept, 1);
  assert.equal(expA.discarded, 1);
  assert.equal(expA.failed, 0);
  assert.equal(expA.costs.CNY, 3);

  assert.equal(report.key_results.length, 1);
  assert.equal(report.key_results[0].run_id, "loop-1-run-1");
  assert.equal(report.negative_results.length, 2);

  assert.deepEqual(
    report.failures.map((group) => [group.category, group.count]),
    [
      ["hypothesis", 1],
      ["unknown", 1],
    ],
  );
  assert.deepEqual(report.costs, { CNY: 3 });
  assert.equal(report.human_decisions.length, 1);
  assert.ok(report.human_decisions[0].includes("EXP-B"));

  assert.ok(report.markdown.includes("## 今日目标"));
  assert.ok(report.markdown.includes("## 完成的实验"));
  assert.ok(report.markdown.includes("## 失败与原因"));
  assert.ok(report.markdown.includes("## 需要人工决策"));
  assert.ok(report.markdown.includes("EXP-A"));
});

test("日报：空输入仍生成合法报告", async () => {
  const report = buildDailyReport({
    date: "2026-10-30",
    generatedAt: "2026-10-30T10:00:00.000Z",
  });
  assert.deepEqual(report.experiments, []);
  assert.deepEqual(report.failures, []);
  assert.ok(report.markdown.includes("无"));

  const errors = validateJsonSchema(report, await loadSchema("daily-report.schema.json"));
  assert.deepEqual(errors, []);
});

test("日报：写入 JSON 与 Markdown 产物", async () => {
  const stack = createStubStack();
  const report = buildDailyReport({
    date: "2026-10-30",
    generatedAt: "2026-10-30T10:00:00.000Z",
    goals: ["验证预热假设"],
    loops: [keptLoop, escalatedLoop],
  });

  const written = await writeDailyReport(
    report,
    { artifacts: stack.artifacts },
    { tenantId: "tenant-demo", projectId: "project-demo" },
  );

  assert.ok(written.jsonRef);
  assert.ok(written.markdownRef);
  assert.deepEqual(written.findings, []);

  const jsonRead = await stack.artifacts.get({
    tenantId: "tenant-demo",
    uri: written.jsonRef!.uri,
  });
  assert.equal(jsonRead.ok, true);
  if (jsonRead.ok) {
    const parsed = JSON.parse(new TextDecoder().decode(jsonRead.value.bytes)) as unknown;
    const errors = validateJsonSchema(
      parsed,
      await loadSchema("daily-report.schema.json"),
    );
    assert.deepEqual(errors, []);
  }

  const markdownRead = await stack.artifacts.get({
    tenantId: "tenant-demo",
    uri: written.markdownRef!.uri,
  });
  assert.equal(markdownRead.ok, true);
  if (markdownRead.ok) {
    const text = new TextDecoder().decode(markdownRead.value.bytes);
    assert.ok(text.startsWith("# 日报 2026-10-30"));
  }
});

import { test } from "node:test";
import assert from "node:assert/strict";

import { createStubStack } from "../adapters/stub/src/index.ts";
import {
  aggregateLoops,
  buildDailyReport,
  buildWeeklyReport,
  writeWeeklyReport,
} from "../packages/pipeline/src/index.ts";
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
    started_at: "2026-11-02T01:00:00.000Z",
    finished_at: "2026-11-02T01:10:00.000Z",
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
    attempts: [attempt()],
    total_cost: 2,
    currency: "CNY",
    budget_total: 100,
    remaining_budget: 98,
    started_at: "2026-11-02T01:00:00.000Z",
    finished_at: "2026-11-02T01:10:00.000Z",
    ...overrides,
  };
}

const escalatedLoop = summary({
  loop_id: "EXP-B-loop-1",
  experiment_id: "EXP-B",
  stop_reason: "escalated",
  stop_detail: "恢复次数达到上限",
  attempts: [
    attempt({
      attempt: 1,
      run_id: "EXP-B-run-1",
      experiment_id: "EXP-B",
      state: "failed",
      decision: "stop",
      reason: "执行失败",
      cost: 1,
      failure: {
        category: "unknown",
        code: "E_EXECUTION_FAILED",
        message: "桩：注入失败",
        retryable: false,
        stage: "execution",
      },
    }),
  ],
});

test("周报：聚合一周的实验结论、失败库、成本与人工决策", async () => {
  const report = buildWeeklyReport({
    week_start: "2026-11-02",
    generatedAt: "2026-11-06T18:00:00.000Z",
    researchDirection: "降低预训练损失",
    literatureProgress: ["结构化 12 篇核心文献"],
    reproductionProgress: ["完成 1 个基线数值复现"],
    planned: ["扩大消融实验"],
    risks: ["数据划分尚未锁定"],
    loops: [summary(), escalatedLoop],
  });

  assert.equal(report.report_id, "weekly-2026-11-02");
  assert.equal(report.research_direction, "降低预训练损失");
  assert.deepEqual(report.decisions, {
    attempts: 2,
    kept: 1,
    discarded: 0,
    extended: 0,
    stopped: 1,
    escalated: 0,
  });
  assert.equal(report.experiments.length, 2);
  assert.equal(report.failures[0].category, "unknown");
  assert.equal(report.human_decisions.length, 1);
  assert.ok(report.human_decisions[0].includes("EXP-B"));

  assert.ok(report.markdown.includes("## 本周研究方向"));
  assert.ok(report.markdown.includes("## 文献进展"));
  assert.ok(report.markdown.includes("## 复现进展"));
  assert.ok(report.markdown.includes("## 实验结论"));
  assert.ok(report.markdown.includes("## 失败库新增"));
  assert.ok(report.markdown.includes("## 周成本"));
  assert.ok(report.markdown.includes("## 风险"));
  assert.ok(report.markdown.includes("EXP-A"));

  const errors = validateJsonSchema(
    report,
    await loadSchema("weekly-report.schema.json"),
  );
  assert.deepEqual(errors, []);
});

test("周报：空输入仍生成合法报告且调用方事项保留", async () => {
  const report = buildWeeklyReport({
    week_start: "2026-11-02",
    generatedAt: "2026-11-06T18:00:00.000Z",
    humanDecisions: ["需要确认下周算力配额"],
  });

  assert.deepEqual(report.experiments, []);
  assert.deepEqual(report.decisions, {
    attempts: 0,
    kept: 0,
    discarded: 0,
    extended: 0,
    stopped: 0,
    escalated: 0,
  });
  assert.deepEqual(report.human_decisions, ["需要确认下周算力配额"]);
  assert.ok(report.markdown.includes("无"));

  const errors = validateJsonSchema(
    report,
    await loadSchema("weekly-report.schema.json"),
  );
  assert.deepEqual(errors, []);
});

test("周报：写入 JSON 与 Markdown 产物", async () => {
  const stack = createStubStack();
  const report = buildWeeklyReport({
    week_start: "2026-11-02",
    generatedAt: "2026-11-06T18:00:00.000Z",
    loops: [summary(), escalatedLoop],
  });

  const written = await writeWeeklyReport(
    report,
    { artifacts: stack.artifacts },
    { tenantId: "tenant-demo", projectId: "project-demo" },
  );

  assert.ok(written.jsonRef);
  assert.ok(written.markdownRef);
  assert.deepEqual(written.findings, []);

  const markdownRead = await stack.artifacts.get({
    tenantId: "tenant-demo",
    uri: written.markdownRef!.uri,
  });
  assert.equal(markdownRead.ok, true);
  if (markdownRead.ok) {
    const text = new TextDecoder().decode(markdownRead.value.bytes);
    assert.ok(text.startsWith("# 周报 2026-11-02"));
  }
});

test("失败库复用：aggregateLoops 与 buildDailyReport 在同一输入下一致", () => {
  const aggregated = aggregateLoops([summary(), escalatedLoop]);
  const daily = buildDailyReport({ date: "2026-11-02", loops: [summary(), escalatedLoop] });

  assert.deepEqual(daily.experiments, aggregated.experiments);
  assert.deepEqual(daily.failures, aggregated.failures);
  assert.deepEqual(daily.costs, aggregated.costs);
  assert.deepEqual(daily.human_decisions, aggregated.human_decisions);
});

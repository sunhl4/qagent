import { test } from "node:test";
import assert from "node:assert/strict";

import { createStubStack } from "../adapters/stub/src/index.ts";
import { emptyCostLedger, summarizeCost } from "../packages/domain/src/index.ts";
import {
  runReproduction,
} from "../packages/pipeline/src/index.ts";
import type {
  DifficultyInput,
  ReproductionJobInput,
  ReproductionRunSpec,
} from "../packages/pipeline/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const START = "2026-11-02T00:00:00.000Z";
const LOCK = "b".repeat(64);

function difficulty(): DifficultyInput {
  return {
    code_available: "official",
    data_available: "public",
    hyperparameters_complete: "complete",
    compute_requirement: "single_gpu",
    dependency_risk: "standard",
    evaluation_clarity: "script_available",
  };
}

function runSpec(overrides: Partial<ReproductionRunSpec> = {}): ReproductionRunSpec {
  return {
    name: "original",
    kind: "gpu",
    wall_clock_seconds: 600,
    max_cost: 5,
    command: "python train.py --config configs/original.yaml",
    seeds: [13, 37, 101],
    metric_name: "val_accuracy",
    ...overrides,
  };
}

function jobInput(overrides: Partial<ReproductionJobInput> = {}): ReproductionJobInput {
  return {
    reproduction_id: "REP-1",
    task_id: "TASK-1",
    tenant_id: "tenant-demo",
    project_id: "project-demo",
    budget: { limit: 100, currency: "CNY" },
    runs: [runSpec()],
    claims: [
      {
        claim_id: "C1",
        claim: "val_accuracy 达到 0.9",
        metric_name: "val_accuracy",
        original_value: 0.9,
        tolerance: 0.05,
      },
    ],
    paper: { title: "示例论文", doi: "10.0/x", arxiv_id: null, code_url: "https://github.com/x" },
    difficulty: difficulty(),
    environment: {
      container: "registry.internal/repro:1",
      python: "3.12",
      framework: "pytorch 2.x",
      cuda: "12.4",
      lockfile_hash: LOCK,
      hardware: "A100-40GB",
    },
    data: { source: "公开数据集", hash: LOCK, split: "8:1:1", preprocessing_notes: [] },
    semantic_checks: [
      { item: "算法实现与论文一致", passed: true, note: null },
      { item: "数据划分一致", passed: true, note: null },
    ],
    generality_checks: [{ setting: "另一数据集", direction_consistent: true, note: null }],
    reusable_assets: ["训练脚本", "配置"],
    open_questions: ["论文未说明某种子设置"],
    ledger: emptyCostLedger(),
    ...overrides,
  };
}

function deps(stack: ReturnType<typeof createStubStack>) {
  return { compute: stack.compute, now: () => new Date(START) };
}

test("复现流水线：多种子完成并生成成功报告", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const result = await runReproduction(jobInput(), deps(stack));

  assert.equal(result.ok, true, JSON.stringify(result.findings));
  assert.ok(result.report);
  assert.equal(result.report!.conclusion, "succeeded");
  assert.deepEqual(result.runs[0].values, [0.9, 0.9, 0.9]);
  assert.equal(result.runs[0].status, "succeeded");
  assert.equal(result.runs[0].lease_ids!.length, 3);

  const totals = summarizeCost(result.ledger)[0];
  assert.equal(totals.committed, 2.4, "3 个种子；桩每轮最多计时 2 分钟，各 0.8");

  const schema = await loadSchema("reproduction-report.schema.json");
  assert.deepEqual(validateJsonSchema(result.report, schema), []);
  assert.equal(result.findings.filter((item) => item.severity === "error").length, 0);
});

test("复现流水线：预算耗尽后剩余种子跳过并保留已有结果", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const result = await runReproduction(
    jobInput({ budget: { limit: 5, currency: "CNY" } }),
    deps(stack),
  );

  assert.equal(result.ok, true, JSON.stringify(result.findings));
  assert.equal(result.runs[0].status, "succeeded");
  assert.deepEqual(result.runs[0].values, [0.9]);
  assert.equal(result.findings.filter((item) => item.code === "W_REPRO_BUDGET").length, 1);
  const totals = summarizeCost(result.ledger)[0];
  assert.equal(totals.committed, 0.8);
});

test("复现流水线：执行未知时转人工，不释放且不重试", async () => {
  const stack = createStubStack({ compute: { scenario: "unknown", baseCostPerHour: 24 } });
  const result = await runReproduction(jobInput({ runs: [runSpec({ seeds: [13, 37] })] }), deps(stack));

  assert.equal(result.ok, false);
  assert.equal(result.error?.code, "UNKNOWN_EXECUTION");
  assert.equal(result.report!.conclusion, "not_attempted");
  assert.equal(result.runs[0].status, "unknown");
  assert.equal(result.runs[0].values.length, 0);
  assert.ok(result.findings.some((item) => item.code === "E_REPRO_UNKNOWN"));

  const totals = summarizeCost(result.ledger)[0];
  assert.equal(totals.reserved, 5, "预留保留等待人工对账");
  assert.equal(totals.actual, 0, "未知执行不做释放结算");
  const jobs = await stack.compute.list({ tenantId: "tenant-demo" });
  assert.equal(jobs.ok, true);
  if (jobs.ok) {
    assert.equal(jobs.value.some((handle) => handle.state === "cancelled"), false, "未知执行不取消");
  }
});

test("复现流水线：运行失败给出 failed 结论并自动补差异归因", async () => {
  const stack = createStubStack({ compute: { scenario: "fail", baseCostPerHour: 24 } });
  const result = await runReproduction(jobInput(), deps(stack));

  assert.equal(result.ok, true, JSON.stringify(result.findings));
  assert.equal(result.report!.conclusion, "failed");
  assert.equal(result.runs[0].status, "failed");
  assert.equal(result.report!.claims_to_verify[0].mean, null);
  assert.ok(
    result.report!.differences.some(
      (entry) => entry.kind === "other" && entry.description.includes("original"),
    ),
  );
  const totals = summarizeCost(result.ledger)[0];
  assert.equal(totals.committed, 2.4);
});

test("复现流水线：多种子跨运行全部完成，各运行汇总各自种子值", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const result = await runReproduction(
    jobInput({
      runs: [
        runSpec({ name: "original", seeds: [13] }),
        runSpec({ name: "ablation-b", seeds: [13, 101], command: "python train.py --config no_b.yaml" }),
      ],
      claims: [
        {
          claim_id: "C1",
          claim: "original accuracy",
          metric_name: "val_accuracy",
          original_value: 0.9,
          tolerance: 0.05,
        },
        {
          claim_id: "C2",
          claim: "ablation accuracy",
          metric_name: "val_accuracy",
          original_value: 0.9,
          tolerance: 0.05,
        },
      ],
    }),
    deps(stack),
  );

  assert.equal(result.ok, true, JSON.stringify(result.findings));
  assert.equal(result.runs.length, 2);
  assert.equal(result.runs[0].status, "succeeded");
  assert.equal(result.runs[1].status, "succeeded");
  assert.deepEqual(result.runs[1].values, [0.9, 0.9]);
  assert.equal(result.report!.conclusion, "succeeded");
  assert.equal(result.report!.claims_to_verify.length, 2);
});

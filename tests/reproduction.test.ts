import { test } from "node:test";
import assert from "node:assert/strict";

import type {
  DifficultyInput,
  ReproductionReportInput,
} from "../packages/domain/src/index.ts";
import { assessDifficulty, buildReproductionReport, evaluateClaim } from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const NOW = new Date("2026-11-02T00:00:00.000Z");
const LOCK = "a".repeat(64);

function difficulty(overrides: Partial<DifficultyInput> = {}): DifficultyInput {
  return {
    code_available: "official",
    data_available: "public",
    hyperparameters_complete: "complete",
    compute_requirement: "single_gpu",
    dependency_risk: "standard",
    evaluation_clarity: "script_available",
    ...overrides,
  };
}

function baseInput(overrides: Partial<ReproductionReportInput> = {}): ReproductionReportInput {
  return {
    reproduction_id: "REP-1",
    task_id: "TASK-1",
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
    runs: [
      {
        run_id: "REP-1-running_a",
        name: "running_a",
        command: "python train.py",
        seeds: [13, 37, 101],
        status: "succeeded",
        metric_name: "accuracy",
        values: [0.9, 0.905, 0.895],
        cost: 12,
        currency: "CNY",
        lease_ids: ["L1", "L2", "L3"],
      },
    ],
    claims: [
      {
        claim_id: "C1",
        claim: "accuracy 达到 0.9",
        metric_name: "accuracy",
        original_value: 0.9,
        tolerance: 0.02,
      },
    ],
    semantic_checks: [
      { item: "算法实现与论文一致", passed: true, note: null },
      { item: "数据划分一致", passed: true, note: null },
    ],
    generality_checks: [{ setting: "另一数据集", direction_consistent: true, note: null }],
    differences: [],
    created_at: NOW,
    ...overrides,
  };
}

test("复现难度：三档评分", () => {
  const low = assessDifficulty(difficulty());
  assert.equal(low.overall, "low");
  assert.equal(low.total, 0);

  const medium = assessDifficulty(
    difficulty({
      code_available: "third_party",
      data_available: "partial",
      hyperparameters_complete: "partial",
      dependency_risk: "medium",
      evaluation_clarity: "described",
    }),
  );
  assert.equal(medium.overall, "medium");
  assert.equal(medium.total, 5);

  const high = assessDifficulty(
    difficulty({
      code_available: "none",
      data_available: "private",
      hyperparameters_complete: "missing",
      compute_requirement: "cluster",
      dependency_risk: "high",
      evaluation_clarity: "text_only",
    }),
  );
  assert.equal(high.overall, "high");
  assert.equal(high.total, 12);
});

test("声明比较：均值落在容差内为 true，无种子值为 null", () => {
  const within = evaluateClaim({ original_value: 0.9, tolerance: 0.02 }, [0.9, 0.905, 0.895]);
  assert.equal(within.within_tolerance, true);
  assert.ok(Math.abs(within.mean! - 0.9) < 1e-9);
  assert.ok(within.std! > 0);

  const beyond = evaluateClaim({ original_value: 0.9, tolerance: 0.02 }, [0.95, 0.94]);
  assert.equal(beyond.within_tolerance, false);
  assert.equal(beyond.count, 2);

  const empty = evaluateClaim({ original_value: 0.9, tolerance: 0.02 }, []);
  assert.equal(empty.mean, null);
  assert.equal(empty.within_tolerance, null);
});

test("复现报告：三层全过判定成功并通过 schema", async () => {
  const result = buildReproductionReport(baseInput());
  assert.equal(result.ok, true, JSON.stringify(result.errors));
  assert.equal(result.conclusion, "succeeded");
  assert.equal(result.report!.claims_to_verify[0].within_tolerance, true);
  assert.equal(result.report!.difficulty.overall, "low");

  const schema = await loadSchema("reproduction-report.schema.json");
  assert.deepEqual(validateJsonSchema(result.report, schema), []);
});

test("复现报告：部分复现必须给出差异归因", () => {
  const missing = buildReproductionReport(
    baseInput({
      runs: [
        {
          run_id: "REP-1-running_a",
          name: "running_a",
          seeds: [13, 37],
          status: "succeeded",
          metric_name: "accuracy",
          values: [0.95, 0.94],
        },
      ],
    }),
  );
  assert.equal(missing.ok, false);
  assert.equal(missing.conclusion, "partial");
  assert.ok(missing.errors.some((item) => item.code === "E_REPRO_NO_DIFFERENCE"));
  assert.ok(missing.errors.some((item) => item.code === "E_REPRO_DIFFERENCE_REQUIRED"));

  const annotated = buildReproductionReport(
    baseInput({
      runs: [
        {
          run_id: "REP-1-running_a",
          name: "running_a",
          seeds: [13, 37],
          status: "succeeded",
          metric_name: "accuracy",
          values: [0.95, 0.94],
        },
      ],
      differences: [
        {
          kind: "implementation",
          description: "论文未公开学习率调度，使用默认调度",
          evidence: "repo/train.py#L120",
        },
      ],
    }),
  );
  assert.equal(annotated.ok, true, JSON.stringify(annotated.errors));
  assert.equal(annotated.conclusion, "partial");
  assert.equal(annotated.report!.claims_to_verify[0].within_tolerance, false);
});

test("复现报告：全部运行失败给出 failed 结论", () => {
  const result = buildReproductionReport(
    baseInput({
      runs: [
        {
          run_id: "REP-1-running_a",
          name: "running_a",
          seeds: [13],
          status: "failed",
          metric_name: "accuracy",
          values: [],
        },
      ],
      differences: [
        { kind: "other", description: "运行失败：running_a", evidence: null },
      ],
    }),
  );
  assert.equal(result.ok, true, JSON.stringify(result.errors));
  assert.equal(result.conclusion, "failed");
  assert.equal(result.report!.claims_to_verify[0].mean, null);
});

test("复现报告：存在未知执行时只给 not_attempted", async () => {
  const result = buildReproductionReport(
    baseInput({
      runs: [
        {
          run_id: "REP-1-running_a",
          name: "running_a",
          seeds: [13],
          status: "unknown",
          metric_name: "accuracy",
          values: [],
        },
      ],
    }),
  );
  assert.equal(result.ok, true, JSON.stringify(result.errors));
  assert.equal(result.conclusion, "not_attempted");
  assert.ok(result.warnings.some((item) => item.code === "W_REPRO_UNKNOWN"));

  const schema = await loadSchema("reproduction-report.schema.json");
  assert.deepEqual(validateJsonSchema(result.report, schema), []);
});

test("复现报告：判定成功但缺少可推广性被拒绝", () => {
  const result = buildReproductionReport(baseInput({ generality_checks: [] }));
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((item) => item.code === "E_REPRO_GENERALITY"));
  assert.equal(result.conclusion, "partial");
});

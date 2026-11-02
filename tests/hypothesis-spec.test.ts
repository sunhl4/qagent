import { test } from "node:test";
import assert from "node:assert/strict";

import {
  checkHypothesis,
  compileExperiment,
  compileHypothesisSpec,
  draftHypothesisFromReproduction,
} from "../packages/domain/src/index.ts";
import type {
  ExperimentSpec,
  HypothesisRecord,
  HypothesisSpecInput,
} from "../packages/domain/src/index.ts";

const NOW = new Date("2026-11-02T00:00:00.000Z");

function hypothesis(
  overrides: Partial<HypothesisRecord> = {},
  record = {} as HypothesisRecord,
): HypothesisRecord {
  return {
    hypothesis_id: "H-2026-042",
    statement: "预热调度在数据子集漂移时降低验证损失",
    origin: { type: "reproduction_anomaly", evidence: ["reproduction:REP-7#claim-3"] },
    falsifiable_by: "若验证损失未下降或训练时间退化超过 10%，则假设不成立",
    expected_effect: "验证损失下降 ≥ 2%",
    minimal_test: { dataset: "dataset-dev-1", metric: "val_loss", budget: "5 CNY", repeats: 3 },
    risks: ["数据漂移 Overse 影响可比性"],
    status: "proposed",
    source_reproduction_id: "REP-7",
    created_at: NOW.toISOString(),
    revision: 1,
    ...overrides,
    ...record,
  };
}

function specInput(overrides: Partial<HypothesisSpecInput> = {}): HypothesisSpecInput {
  return {
    hypothesis: hypothesis(),
    experiment_id: "EXP-H42-1",
    task_id: "TASK-H42",
    baseline: {
      name: "无预热基线",
      source: "内部复现",
      run_id: "REP-7",
      reproduced: true,
      metric_value: 1.0,
      uncertainty: 0.01,
    },
    primary: {
      name: "val_loss",
      direction: "minimize",
      minimum_observable_effect: 0.02,
    },
    guardrails: [{ name: "train_time_seconds", max_degradation: 0.1 }],
    variables: {
      changed: ["src/train/scheduler.py"],
      controlled: ["dataset", "split", "model"],
      allowed_paths: ["src/train/**"],
      forbidden_paths: ["src/eval/**"],
    },
    resources: {
      type: "gpu",
      count: 1,
      max_wall_clock_seconds: 600,
      max_cost: 5,
      currency: "CNY",
      checkpoint_required: true,
    },
    seeds: [7, 11, 13],
    data: { dataset_ref: "dataset-dev-1", leakage_check: "done" },
    ...overrides,
  };
}

test("假设编译：通过质量门的假设生成可执行规格", () => {
  const result = compileHypothesisSpec(specInput());
  assert.equal(result.ok, true, JSON.stringify(result.findings));
  assert.ok(result.spec);

  const spec = result.spec!;
  assert.equal(spec.experiment_id, "EXP-H42-1");
  assert.equal(spec.hypothesis.origin, "reproduction_anomaly");
  assert.deepEqual(spec.hypothesis.evidence_refs, ["reproduction:REP-7#claim-3"]);
  assert.equal(spec.metrics.repeats, 3);
  assert.deepEqual(spec.metrics.seeds, [7, 11, 13]);
  assert.ok(spec.decision.keep_if.includes("H-2026-042"), spec.decision.keep_if);
  assert.ok(spec.decision.discard_if.includes("验证损失未下降"));

  // 最终以 compileExperiment 为准：规格可直接进实验循环
  const compiled = compileExperiment(spec);
  assert.deepEqual(
    compiled.errors.map((error) => error.code),
    [],
    JSON.stringify(compiled.errors),
  );
});

test("假设编译：质量门未通过时拒绝", () => {
  const noBudget = compileHypothesisSpec(
    specInput({
      hypothesis: hypothesis({
        minimal_test: { dataset: null, metric: null, budget: "", repeats: 1 },
      }),
    }),
  );
  assert.equal(noBudget.ok, false);
  assert.ok(noBudget.findings.some((item) => item.code === "E_HYP_BUDGET"));

  const noEvidence = compileHypothesisSpec(
    specInput({
      hypothesis: hypothesis({ origin: { type: "transfer", evidence: [] } }),
    }),
  );
  assert.equal(noEvidence.ok, false);
  assert.ok(noEvidence.findings.some((item) => item.code === "E_HYP_ORIGIN_EVIDENCE"));

  const notFalsifiable = compileHypothesisSpec(
    specInput({ hypothesis: hypothesis({ falsifiable_by: " " }) }),
  );
  assert.equal(notFalsifiable.ok, false);
  assert.ok(notFalsifiable.findings.some((item) => item.code === "E_HYP_FALSIFIABLE"));
});

test("假设编译：未复现基线在规格层被拒绝并被归类", () => {
  const result = compileHypothesisSpec(
    specInput({ baseline: { ...specInput().baseline, reproduced: false } }),
  );
  assert.equal(result.ok, false);
  assert.ok(
    result.findings.some((item) => item.code === "E_BASELINE_NOT_REPRODUCED"),
    JSON.stringify(result.findings),
  );
});

test("假设编译：重复少于 3 只告警，规格仍可执行", () => {
  const result = compileHypothesisSpec(
    specInput({ hypothesis: hypothesis({ minimal_test: { dataset: null, metric: null, budget: "5 CNY", repeats: 1 } }) }),
  );
  assert.equal(result.ok, true);
  assert.ok(result.findings.some((item) => item.code === "E_HYP_REPEATS" || item.code === "W_FEW_REPEATS"));
});

test("假设编译：草拟→编译端到端", () => {
  const draft = draftHypothesisFromReproduction({
    hypothesis_id: "H-2026-043",
    source_reproduction_id: "REP-9",
    statement: "按教程忽略 validation split 缓存导致指标不一致",
    falsifiable_by: "修正缓存后差异消失则假设成立",
    expected_effect: "差异 < 0.1%",
    minimal_test: { budget: "1 CNY", repeats: 1 },
    risks: ["缓存实现与文档不一致"],
    created_at: NOW,
  });
  assert.ok(draft.record, JSON.stringify(draft.findings));

  const spec: ExperimentSpec | undefined = compileHypothesisSpec(
    specInput({
      hypothesis: draft.record!,
      experiment_id: "EXP-H43-1",
      seeds: [3, 5, 9],
    }),
  ).spec;
  assert.ok(spec);
  assert.equal(spec!.hypothesis.origin, "reproduction_anomaly");
  assert.ok(spec!.decision.keep_if.includes("H-2026-043"));
});

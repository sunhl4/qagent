import { test } from "node:test";
import assert from "node:assert/strict";

import type { MethodCard } from "../packages/domain/src/index.ts";
import { compileMethodCard } from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const NOW = "2026-11-02T00:00:00.000Z";

function makeCard(overrides: Partial<MethodCard> = {}): MethodCard {
  return {
    method_card_id: "MC-2026-001",
    paper: {
      paper_id: "P-1",
      title: "示例论文标题",
      authors: ["A. Author", "B. Author"],
      year: 2026,
      doi: "10.0000/example",
      arxiv_id: "2601.00000",
      venue: "Example Venue",
      source: "openalex",
      code_url: "https://github.com/example/repo",
    },
    problem: "示例问题",
    method_summary: "示例方法概述",
    claims: ["方法 A 在数据集 D 上达到指标 M"],
    inputs: ["图像"],
    outputs: ["分类标签"],
    datasets: ["示例数据集"],
    preprocessing: ["标准化"],
    model_or_algorithm: "示例模型",
    hyperparameters: [{ name: "learning_rate", value: 0.001 }],
    baselines: ["基线 B"],
    metrics: [{ name: "accuracy", direction: "maximize" }],
    train_test_split: "按论文 8:1:1",
    hardware: "A100-40GB",
    runtime: "2 GPU-hour",
    reproduction_status: "not_attempted",
    evidence_locations: [
      { type: "table", location: "Table 2", quote: "acc 90.1", ref: null },
    ],
    created_at: NOW,
    ...overrides,
  };
}

test("方法卡：合法记录通过 schema 与编译", async () => {
  const card = makeCard();
  const compiled = compileMethodCard(card);
  assert.equal(compiled.ok, true, JSON.stringify(compiled.errors));
  assert.equal(compiled.warnings.length, 0, JSON.stringify(compiled.warnings));

  const schema = await loadSchema("method-card.schema.json");
  assert.deepEqual(validateJsonSchema(card, schema), []);
});

test("方法卡：缺少证据定位被硬性拒绝", () => {
  const compiled = compileMethodCard(makeCard({ evidence_locations: [] }));
  assert.equal(compiled.ok, false);
  assert.ok(compiled.errors.some((item) => item.code === "E_METHOD_CARD_EVIDENCE"));
});

test("方法卡：缺失基线/代码/数据集/超参给出警告但通过", () => {
  const compiled = compileMethodCard(
    makeCard({
      baselines: [],
      hyperparameters: [],
      datasets: [],
      original_code_url: null,
      paper: { ...makeCard().paper, code_url: null },
    }),
  );
  assert.equal(compiled.ok, true);
  const codes = compiled.warnings.map((item) => item.code);
  assert.ok(codes.includes("W_METHOD_CARD_NO_BASELINES"));
  assert.ok(codes.includes("W_METHOD_CARD_NO_HYPERPARAMS"));
  assert.ok(codes.includes("W_METHOD_CARD_NO_CODE"));
});

test("方法卡：核心字段缺失被逐项拒绝", () => {
  const missingTitle = compileMethodCard(makeCard({ paper: { ...makeCard().paper, title: "" } }));
  assert.equal(missingTitle.ok, false);
  assert.ok(missingTitle.errors.some((item) => item.code === "E_METHOD_CARD_TITLE"));

  const missingSummary = compileMethodCard(makeCard({ method_summary: "" }));
  assert.equal(missingSummary.ok, false);
  assert.ok(missingSummary.errors.some((item) => item.code === "E_METHOD_CARD_SUMMARY"));
});

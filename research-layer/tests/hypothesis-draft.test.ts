import { test } from "node:test";
import assert from "node:assert/strict";

import { draftHypothesisFromReproduction } from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const NOW = new Date("2026-11-02T09:00:00.000Z");

test("假设草拟：证据链接自动指向复现报告与声明", async () => {
  const draft = draftHypothesisFromReproduction({
    hypothesis_id: "H-2026-014",
    statement: "在数据集 D 上把损失调度从 X 换成 Y 可以降低 W 指标",
    falsifiable_by: "如果 W 未下降或护栏退化，则假设不成立",
    expected_effect: "W 下降 ≥ 3%",
    minimal_test: { dataset: "D-small", metric: "loss", budget: "1 GPU-hour", repeats: 3 },
    risks: ["多次恢复失败后需转人工", "数据分布与原文不一致"],
    source_reproduction_id: "REP-1",
    claim_ids: ["C1", "C2"],
    difference_notes: ["difference:implementation:论文未公开调度细节"],
    created_at: NOW,
  });

  assert.equal(draft.ok, true, JSON.stringify(draft.errors));
  assert.equal(draft.record!.origin.type, "reproduction_anomaly");
  assert.deepEqual(draft.record!.origin.evidence, [
    "reproduction:REP-1",
    "reproduction:REP-1#C1",
    "reproduction:REP-1#C2",
    "difference:implementation:论文未公开调度细节",
  ]);
  assert.equal(draft.record!.source_reproduction_id, "REP-1");
  assert.equal(draft.record!.created_at, "2026-11-02T09:00:00.000Z");

  const schema = await loadSchema("hypothesis-record.schema.json");
  assert.deepEqual(validateJsonSchema(draft.record, schema), []);
});

test("假设草拟：内容质量不过关时不返回记录", () => {
  const draft = draftHypothesisFromReproduction({
    hypothesis_id: "H-2026-015",
    statement: "换个调度应该会更好",
    falsifiable_by: "",
    minimal_test: { budget: "1 GPU-hour", repeats: 1 },
    risks: [],
    source_reproduction_id: "REP-2",
    created_at: NOW,
  });

  assert.equal(draft.ok, false);
  assert.equal(draft.record, undefined);
  assert.ok(draft.errors.some((item) => item.code === "E_HYP_FALSIFIABLE"));
  assert.ok(draft.errors.some((item) => item.code === "E_HYP_RISKS"));
});

test("假设草拟：只有复现报告引用也能通过证据要求", () => {
  const draft = draftHypothesisFromReproduction({
    hypothesis_id: "H-2026-016",
    statement: "把评测脚本的对齐方式改成论文定义可消除偏差",
    falsifiable_by: "若两轮对齐修正后偏差不变，则假设不成立",
    minimal_test: { dataset: "标准评测集", metric: "accuracy", budget: "0.5 GPU-hour", repeats: 3 },
    risks: ["评测脚本无版本快照"],
    source_reproduction_id: "REP-3",
    created_at: NOW,
  });

  assert.equal(draft.ok, true, JSON.stringify(draft.errors));
  assert.deepEqual(draft.record!.origin.evidence, ["reproduction:REP-3"]);
});

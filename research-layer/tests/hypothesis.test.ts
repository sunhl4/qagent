import { test } from "node:test";
import assert from "node:assert/strict";

import type { HypothesisRecord } from "../packages/domain/src/index.ts";
import { checkHypothesis } from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const NOW = "2026-11-02T00:00:00.000Z";

function makeHypothesis(overrides: Partial<HypothesisRecord> = {}): HypothesisRecord {
  return {
    hypothesis_id: "H-2026-001",
    statement: "在数据集 D 上用方法 Y 替换片段 Z 可以降低 W 指标",
    origin: {
      type: "reproduction_anomaly",
      evidence: ["paper:10.0/x#Table 3", "reproduction:REP-1"],
    },
    falsifiable_by: "如果 W 未下降或护栏指标退化，则假设不成立",
    expected_effect: "W 下降 ≥ 3%",
    minimal_test: { dataset: "D-small", metric: "loss", budget: "1 GPU-hour", repeats: 3 },
    risks: ["数据分布不匹配", "实现复杂度高"],
    status: "proposed",
    source_reproduction_id: "REP-1",
    created_at: NOW,
    ...overrides,
  };
}

test("假说：合法记录通过质量门与 schema", async () => {
  const record = makeHypothesis();
  const checked = checkHypothesis(record);
  assert.equal(checked.ok, true, JSON.stringify(checked.errors));
  assert.equal(checked.warnings.length, 0, JSON.stringify(checked.warnings));

  const schema = await loadSchema("hypothesis-record.schema.json");
  assert.deepEqual(validateJsonSchema(record, schema), []);
});

test("假说：质量门拒绝可证伪性/依据/风险/最小实验缺失", () => {
  const noFalsifiable = checkHypothesis(makeHypothesis({ falsifiable_by: "  " }));
  assert.equal(noFalsifiable.ok, false);
  assert.ok(noFalsifiable.errors.some((item) => item.code === "E_HYP_FALSIFIABLE"));

  const noEvidence = checkHypothesis(
    makeHypothesis({ origin: { type: "literature_gap", evidence: [] } }),
  );
  assert.ok(noEvidence.errors.some((item) => item.code === "E_HYP_ORIGIN_EVIDENCE"));

  const noBudget = checkHypothesis(
    makeHypothesis({ minimal_test: { repeats: 3, budget: null } }),
  );
  assert.ok(noBudget.errors.some((item) => item.code === "E_HYP_BUDGET"));

  const badRepeats = checkHypothesis(makeHypothesis({ minimal_test: { budget: "1h", repeats: 0 } }));
  assert.ok(badRepeats.errors.some((item) => item.code === "E_HYP_REPEATS"));

  const noRisks = checkHypothesis(makeHypothesis({ risks: [] }));
  assert.ok(noRisks.errors.some((item) => item.code === "E_HYP_RISKS"));
});

test("假说：重复次数少于 3 只告警", () => {
  const checked = checkHypothesis(makeHypothesis({ minimal_test: { budget: "1h", repeats: 2 } }));
  assert.equal(checked.ok, true);
  assert.ok(checked.warnings.some((item) => item.code === "W_HYP_REPEATS"));
});

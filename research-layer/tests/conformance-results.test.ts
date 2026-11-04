import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";
import { parseCases, validateResultsDoc } from "../scripts/conformance.mjs";
import { runStubConformance } from "./conformance-run.ts";

const version = (await readFile(new URL("../contracts/VERSION", import.meta.url), "utf8")).trim();

const sample = JSON.parse(
  await readFile(new URL("../examples/conformance-results.stub.json", import.meta.url), "utf8"),
);
const casesText = await readFile(
  new URL("../contracts/conformance/cases.yaml", import.meta.url),
  "utf8",
);
const cases = parseCases(casesText);

test("结果交换样例符合 schemas/conformance-results.schema.json", async () => {
  const schema = await loadSchema("conformance-results.schema.json");
  assert.deepEqual(validateJsonSchema(sample, schema), []);
  assert.equal(sample.provenance, "stub");
  assert.equal(sample.schema_version, "0.1");
});

test("结果交换样例覆盖全部用例，且与当次桩运行一致", async () => {
  assert.equal(cases.length, 36, "cases.yaml 应解析出 36 条用例");
  assert.equal(cases.filter((item) => item.level === "MUST").length, 35, "MUST 用例应为 35 条");

  const report = validateResultsDoc(sample, cases, sample.contract_version);
  assert.deepEqual(report.errors, [], "样例本身不应有硬错误");
  assert.equal(sample.results.length, cases.length, "样例应覆盖全部用例");
  assert.deepEqual(sample.results, await runStubConformance());
  assert.equal(sample.provenance, "stub");
  assert.equal(
    sample.results.some((item) => item.status === "pending"),
    false,
    "桩运行后不应再留下未判条目",
  );
});

test("结果校验器拒绝未知用例、重复用例与非法状态", () => {
  const bad = {
    ...structuredClone(sample),
    contract_version: "9.9.9",
    results: [
      { ...structuredClone(sample.results[0]), status: "skipped" },
      ...sample.results.slice(1),
      { case_id: "XX-99", port: "object", level: "MUST", status: "passed" },
      { ...structuredClone(sample.results[0]) },
    ],
  };
  const report = validateResultsDoc(bad, cases, version);
  const join = report.errors.join("\n");
  assert.match(join, /status（"skipped"）不在枚举/);
  assert.match(join, /case_id "XX-99" 不在 cases\.yaml 中/);
  assert.match(join, /用例 ID-01 重复/);
  assert.match(join, /contract_version（9\.9\.9）与 contracts\/VERSION（0\.1\.0）不一致/);
});

function cloneSampleWithoutMissing() {
  const doc = structuredClone(sample);
  // 移除一条 MUST 用例，制造覆盖缺口。
  doc.results = doc.results.filter((item) => item.case_id !== "ID-01");
  return doc;
}

test("结果校验器把缺口用例列为未覆盖提示而非硬错误", () => {
  const doc = cloneSampleWithoutMissing();
  const report = validateResultsDoc(doc, cases, doc.contract_version);
  assert.deepEqual(report.errors, []);
  assert.ok(
    report.advisories.some((line) => line.includes("缺少用例结果: ID-01（MUST")),
    "应提示缺少 ID-01",
  );
  assert.equal(report.summary.perLevel.MUST.missing.length, 1);
});

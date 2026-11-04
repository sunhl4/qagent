import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { parseCases } from "../scripts/conformance.mjs";
import { runStubConformance } from "./conformance-run.ts";

const BLOCKED = ["MD-02", "MD-05", "XP-01"];

test("36 条一致性用例在桩上有确定结论", async () => {
  const cases = parseCases(
    await readFile(new URL("../contracts/conformance/cases.yaml", import.meta.url), "utf8"),
  );
  const results = await runStubConformance();

  assert.equal(results.length, cases.length);
  for (const [index, item] of cases.entries()) {
    assert.equal(results[index].case_id, item.id);
    assert.equal(results[index].port, item.port);
    assert.equal(results[index].level, item.level);
  }

  const failed = results.filter((item) => item.status === "failed");
  assert.deepEqual(
    failed.map((item) => `${item.case_id}: ${item.notes ?? ""}`),
    [],
  );
  assert.deepEqual(
    results.filter((item) => item.status === "pending").map((item) => item.case_id),
    [],
  );
  assert.deepEqual(
    results.filter((item) => item.status === "blocked").map((item) => item.case_id),
    BLOCKED,
  );
  for (const item of results) {
    if (item.status === "blocked" || item.status === "failed") {
      assert.equal(typeof item.notes, "string");
      assert.ok((item.notes ?? "").length > 0);
    }
  }
});

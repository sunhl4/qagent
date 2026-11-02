import { test } from "node:test";
import assert from "node:assert/strict";

import {
  buildCostLedgerSnapshot,
  checkBudget,
  emptyCostLedger,
  leaseCostSummary,
  recordActualCost,
  releaseCostReservation,
  reserveCost,
  summarizeCost,
} from "../packages/domain/src/index.ts";
import type { CostLedger } from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const AT = "2026-10-30T00:00:00.000Z";

function costInput(overrides: Partial<Parameters<typeof reserveCost>[1]> = {}) {
  return {
    leaseId: "LEASE-1",
    tenantId: "tenant-1",
    projectId: "project-1",
    taskId: "task-1",
    currency: "CNY",
    amount: 10,
    at: AT,
    ...overrides,
  };
}

function apply(
  ledger: CostLedger,
  mutation: ReturnType<typeof reserveCost>,
): CostLedger {
  assert.equal(mutation.ok, true, JSON.stringify(mutation.findings));
  return mutation.ledger;
}

test("账本：预留、实际与释放后的已承诺成本", () => {
  let ledger = emptyCostLedger();
  ledger = apply(ledger, reserveCost(ledger, costInput({ amount: 10 })));
  assert.deepEqual(summarizeCost(ledger), [
    {
      currency: "CNY",
      reserved: 10,
      actual: 0,
      released: 0,
      committed: 10,
      entries: 1,
    },
  ]);

  ledger = apply(ledger, recordActualCost(ledger, costInput({ amount: 6 })));
  ledger = apply(ledger, releaseCostReservation(ledger, costInput({ amount: 4 })));

  const totals = summarizeCost(ledger)[0];
  assert.equal(totals.reserved, 10);
  assert.equal(totals.actual, 6);
  assert.equal(totals.released, 4);
  assert.equal(totals.committed, 6, "净预留与实际取较大值，不能重复计费");
  assert.equal(totals.entries, 3);

  const lease = leaseCostSummary(ledger, "LEASE-1");
  assert.deepEqual(lease, {
    leaseId: "LEASE-1",
    reserved: 10,
    actual: 6,
    released: 4,
    unusedReservation: 0,
  });
});

test("账本：未释放的预留保持占用", () => {
  let ledger = emptyCostLedger();
  ledger = apply(ledger, reserveCost(ledger, costInput({ amount: 10 })));
  ledger = apply(ledger, recordActualCost(ledger, costInput({ amount: 4 })));

  assert.equal(summarizeCost(ledger)[0].committed, 10);
  assert.equal(leaseCostSummary(ledger, "LEASE-1").unusedReservation, 6);

  ledger = apply(ledger, releaseCostReservation(ledger, costInput({ amount: 6 })));
  assert.equal(summarizeCost(ledger)[0].committed, 4);
});

test("账本：预算检查包含已承诺成本与本次预留", () => {
  let ledger = emptyCostLedger();
  ledger = apply(ledger, reserveCost(ledger, costInput({ amount: 10 })));

  const exact = checkBudget(ledger, { tenantId: "tenant-1", currency: "CNY", limit: 10 });
  assert.equal(exact.ok, true);
  assert.equal(exact.committed, 10);
  assert.equal(exact.remaining, 0);

  const over = checkBudget(
    ledger,
    { tenantId: "tenant-1", currency: "CNY", limit: 10 },
    2,
  );
  assert.equal(over.ok, false);
  assert.equal(over.overBy, 2);
  assert.ok(over.findings.some((item) => item.code === "E_BUDGET_EXCEEDED"));

  ledger = apply(ledger, recordActualCost(ledger, costInput({ amount: 6 })));
  ledger = apply(ledger, releaseCostReservation(ledger, costInput({ amount: 4 })));
  const afterRelease = checkBudget(ledger, {
    tenantId: "tenant-1",
    currency: "CNY",
    limit: 10,
  });
  assert.equal(afterRelease.ok, true);
  assert.equal(afterRelease.committed, 6);
  assert.equal(afterRelease.remaining, 4);
});

test("账本：确定性条目幂等，冲突条目被拒绝", () => {
  const ledger = emptyCostLedger();
  const first = reserveCost(ledger, costInput({ amount: 10 }));
  assert.equal(first.ok, true);
  assert.equal(first.duplicate, false);

  const again = reserveCost(first.ledger, costInput({ amount: 10 }));
  assert.equal(again.ok, true);
  assert.equal(again.duplicate, true);
  assert.equal(again.ledger.entries.length, 1);

  const conflict = reserveCost(first.ledger, costInput({ amount: 11 }));
  assert.equal(conflict.ok, false);
  assert.ok(conflict.findings.some((item) => item.code === "E_COST_DUPLICATE_CONFLICT"));
});

test("账本：按币种与任务过滤", () => {
  let ledger = emptyCostLedger();
  ledger = apply(ledger, reserveCost(ledger, costInput({ amount: 10 })));
  ledger = apply(
    ledger,
    reserveCost(
      ledger,
      costInput({ leaseId: "LEASE-2", currency: "USD", amount: 3, taskId: "task-2" }),
    ),
  );

  assert.equal(summarizeCost(ledger).length, 2);
  assert.deepEqual(
    summarizeCost(ledger, { taskId: "task-2" }).map((item) => [item.currency, item.committed]),
    [["USD", 3]],
  );

  const usd = checkBudget(ledger, { tenantId: "tenant-1", currency: "USD", limit: 5 });
  assert.equal(usd.ok, true);
  assert.equal(usd.committed, 3);
});

test("账本：快照通过 schema", async () => {
  let ledger = emptyCostLedger();
  ledger = apply(ledger, reserveCost(ledger, costInput({ amount: 10 })));
  ledger = apply(ledger, recordActualCost(ledger, costInput({ amount: 6 })));
  ledger = apply(ledger, releaseCostReservation(ledger, costInput({ amount: 4 })));

  const snapshot = buildCostLedgerSnapshot(ledger);
  const schema = await loadSchema("cost-ledger.schema.json");
  assert.deepEqual(validateJsonSchema(snapshot, schema), []);
});

test("账本：非法条目被拒绝", () => {
  const ledger = emptyCostLedger();
  const negative = reserveCost(ledger, costInput({ amount: -1 }));
  assert.equal(negative.ok, false);
  assert.ok(negative.findings.some((item) => item.code === "E_COST_AMOUNT"));

  const badCurrency = reserveCost(ledger, costInput({ currency: "EURO" }));
  assert.equal(badCurrency.ok, false);
  assert.ok(badCurrency.findings.some((item) => item.code === "E_COST_CURRENCY"));

  const badBudget = checkBudget(ledger, {
    tenantId: "tenant-1",
    currency: "CNY",
    limit: -1,
  });
  assert.equal(badBudget.ok, false);
  assert.ok(badBudget.findings.some((item) => item.code === "E_BUDGET_INVALID"));
});

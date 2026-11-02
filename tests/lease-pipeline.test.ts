import { test } from "node:test";
import assert from "node:assert/strict";

import type { ResourceRequest } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";
import {
  emptyCostLedger,
  summarizeCost,
} from "../packages/domain/src/index.ts";
import type { CostLedger } from "../packages/domain/src/index.ts";
import { acquireLease, reconcileLease, releaseLease } from "../packages/pipeline/src/index.ts";
import type { AcquireLeaseInput } from "../packages/pipeline/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const AT = new Date("2026-10-30T00:00:00.000Z");

function makeRequest(overrides: Partial<ResourceRequest> = {}): ResourceRequest {
  return {
    idempotencyKey: "idem-lease-1",
    requestId: "REQ-LEASE-1",
    tenantId: "tenant-demo",
    projectId: "project-demo",
    taskId: "TASK-LEASE-1",
    kind: "gpu",
    count: 1,
    accelerator: "A100-40GB",
    wallClockSeconds: 600,
    maxCost: 5,
    currency: "CNY",
    checkpoint: { required: true, intervalSeconds: 60 },
    ...overrides,
  };
}

function makeStack() {
  return createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
}

function acquireInput(overrides: Partial<AcquireLeaseInput> = {}): AcquireLeaseInput {
  return {
    request: makeRequest(),
    holder: { type: "attempt", id: "attempt-lease-1" },
    ttlSeconds: 3600,
    budget: { limit: 100, currency: "CNY" },
    ledger: emptyCostLedger(),
    ...overrides,
  };
}

test("租约编排：准入报价、预算预留与提交", async () => {
  const stack = makeStack();
  const result = await acquireLease(acquireInput(), {
    compute: stack.compute,
    now: () => AT,
  });

  assert.equal(result.ok, true, JSON.stringify(result.findings));
  assert.ok(result.lease);
  assert.equal(result.lease!.state, "PREPARED");
  assert.equal(result.lease!.cost?.reserved, 5);
  assert.equal(result.lease!.resource.handle_id, "stub-job-1");
  assert.ok(result.handle);

  const totals = summarizeCost(result.ledger)[0];
  assert.equal(totals.reserved, 5);
  assert.equal(totals.committed, 5);

  const leaseSchema = await loadSchema("resource-lease.schema.json");
  assert.deepEqual(validateJsonSchema(result.lease, leaseSchema), []);
});

test("租约编排：预算不足时不提交作业", async () => {
  const stack = makeStack();
  const ledger: CostLedger = {
    entries: [
      {
        entry_id: "lease:OTHER:reserve",
        kind: "reserve",
        tenant_id: "tenant-demo",
        project_id: "project-demo",
        task_id: "TASK-OTHER",
        lease_id: "OTHER",
        currency: "CNY",
        amount: 99,
        at: AT.toISOString(),
      },
    ],
  };

  const result = await acquireLease(
    acquireInput({ ledger, budget: { limit: 100, currency: "CNY" } }),
    { compute: stack.compute, now: () => AT },
  );

  assert.equal(result.ok, false);
  assert.equal(result.error?.code, "E_BUDGET_EXCEEDED");
  assert.equal(result.lease?.state, "FAILED");
  assert.equal(result.ledger.entries.length, 1, "不得写入新的预留");

  const jobs = await stack.compute.list({ tenantId: "tenant-demo" });
  assert.equal(jobs.ok, true);
  if (jobs.ok) assert.equal(jobs.value.length, 0, "预算不足不得提交作业");
});

test("租约编排：报价超过成本上限时拒绝", async () => {
  const stack = makeStack();
  const result = await acquireLease(
    acquireInput({ request: makeRequest({ maxCost: 1 }) }),
    { compute: stack.compute, now: () => AT },
  );

  assert.equal(result.ok, false);
  assert.equal(result.error?.code, "E_LEASE_INFEASIBLE");
  assert.equal(result.lease?.state, "FAILED");
  assert.equal(result.ledger.entries.length, 0);
});

test("租约编排：释放后结算实际成本并退回预留", async () => {
  const stack = makeStack();
  const deps = { compute: stack.compute, now: () => AT };
  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true);
  assert.ok(acquired.lease && acquired.handle);

  const handleId = acquired.lease!.resource.handle_id!;
  let handle = acquired.handle!;
  for (let index = 0; index < 2; index += 1) {
    const status = await stack.compute.status(handleId);
    assert.equal(status.ok, true);
    if (status.ok) handle = status.value;
  }
  assert.equal(handle.state, "succeeded");

  const released = await releaseLease(
    {
      lease: acquired.lease!,
      ledger: acquired.ledger,
      handle,
      taskId: "TASK-LEASE-1",
      reason: "completed",
    },
    { compute: stack.compute, now: () => new Date("2026-10-30T00:10:00.000Z") },
  );

  assert.equal(released.ok, true, JSON.stringify(released.findings));
  assert.equal(released.lease?.state, "RELEASED");
  assert.equal(released.lease?.release_reason, "completed");

  const totals = summarizeCost(released.ledger)[0];
  assert.equal(totals.actual, 0.8);
  assert.equal(totals.released, 4.2);
  assert.equal(totals.committed, 0.8);

  const again = await releaseLease(
    { lease: released.lease!, ledger: released.ledger, taskId: "TASK-LEASE-1" },
    { compute: stack.compute, now: () => AT },
  );
  assert.equal(again.ok, true);
  assert.equal(again.ledger.entries.length, released.ledger.entries.length);
});

test("租约编排：释放失败时保留预留", async () => {
  const stack = makeStack();
  const deps = { compute: stack.compute, now: () => AT };
  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true);
  assert.ok(acquired.lease);

  const broken = {
    ...acquired.lease!,
    resource: { ...acquired.lease!.resource, handle_id: "missing-handle" },
  };
  const result = await releaseLease(
    { lease: broken, ledger: acquired.ledger, taskId: "TASK-LEASE-1" },
    deps,
  );

  assert.equal(result.ok, false);
  assert.equal(result.error?.code, "NOT_FOUND");
  assert.equal(result.lease?.state, "PREPARED");
  const totals = summarizeCost(result.ledger)[0];
  assert.equal(totals.reserved, 5, "释放失败不得退回预留");
});

test("租约编排：执行状态未知时禁止释放结算", async () => {
  const stack = createStubStack({
    compute: { scenario: "unknown", baseCostPerHour: 24 },
  });
  const deps = { compute: stack.compute, now: () => AT };
  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true);
  assert.ok(acquired.lease);

  const result = await releaseLease(
    { lease: acquired.lease!, ledger: acquired.ledger, taskId: "TASK-LEASE-1" },
    deps,
  );

  assert.equal(result.ok, false);
  assert.equal(result.error?.code, "UNKNOWN_EXECUTION");
  assert.equal(result.error?.retryable, false);
  const totals = summarizeCost(result.ledger)[0];
  assert.equal(totals.reserved, 5, "未知执行不得退回预留");
  assert.ok(
    result.findings.some((item) => item.code === "E_LEASE_UNKNOWN_EXECUTION"),
  );
});

test("租约对账：排队中继续等待，完成后结算", async () => {
  const stack = makeStack();
  const deps = { compute: stack.compute, now: () => AT };
  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true);
  assert.ok(acquired.lease);

  const waiting = await reconcileLease(
    { lease: acquired.lease!, ledger: acquired.ledger, taskId: "TASK-LEASE-1" },
    deps,
  );
  assert.equal(waiting.ok, true);
  assert.equal(waiting.action, "wait");
  assert.equal(waiting.lease?.state, "PREPARED");

  let handle = acquired.handle!;
  for (let index = 0; index < 2; index += 1) {
    const status = await stack.compute.status(handle.handleId);
    assert.equal(status.ok, true);
    if (status.ok) handle = status.value;
  }
  assert.equal(handle.state, "succeeded");

  const settled = await reconcileLease(
    { lease: waiting.lease!, ledger: waiting.ledger, taskId: "TASK-LEASE-1" },
    deps,
  );
  assert.equal(settled.ok, true, JSON.stringify(settled.findings));
  assert.equal(settled.action, "settle");
  assert.equal(settled.lease?.state, "RELEASED");
  const totals = summarizeCost(settled.ledger)[0];
  assert.equal(totals.actual, 0.8);
  assert.equal(totals.released, 4.2);
  assert.equal(totals.committed, 0.8);
});

test("租约对账：执行前取消退回全部预留", async () => {
  const stack = makeStack();
  const deps = { compute: stack.compute, now: () => AT };
  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true);
  assert.ok(acquired.lease?.resource.handle_id);

  await stack.compute.cancel(acquired.lease!.resource.handle_id!);

  const result = await reconcileLease(
    { lease: acquired.lease!, ledger: acquired.ledger, taskId: "TASK-LEASE-1" },
    deps,
  );
  assert.equal(result.ok, true);
  assert.equal(result.action, "cancelled");
  assert.equal(result.lease?.state, "REVOKED");
  const totals = summarizeCost(result.ledger)[0];
  assert.equal(totals.reserved, 5);
  assert.equal(totals.released, 5);
  assert.equal(totals.committed, 0);
});

test("租约对账：未知执行升级并保留预留", async () => {
  const stack = createStubStack({
    compute: { scenario: "unknown", baseCostPerHour: 24 },
  });
  const deps = { compute: stack.compute, now: () => AT };
  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true);
  assert.ok(acquired.lease);

  const result = await reconcileLease(
    { lease: acquired.lease!, ledger: acquired.ledger, taskId: "TASK-LEASE-1" },
    deps,
  );
  assert.equal(result.ok, false);
  assert.equal(result.action, "escalate");
  assert.equal(result.error?.code, "UNKNOWN_EXECUTION");
  assert.equal(result.error?.retryable, false);
  assert.equal(result.lease?.state, "PREPARED");
  const totals = summarizeCost(result.ledger)[0];
  assert.equal(totals.reserved, 5);
});

test("租约对账：缺少句柄时升级", async () => {
  const stack = makeStack();
  const deps = { compute: stack.compute, now: () => AT };
  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true);
  assert.ok(acquired.lease);

  const noHandle = {
    ...acquired.lease!,
    resource: { ...acquired.lease!.resource, handle_id: null },
  };
  const result = await reconcileLease(
    { lease: noHandle, ledger: acquired.ledger, taskId: "TASK-LEASE-1" },
    deps,
  );
  assert.equal(result.ok, false);
  assert.equal(result.action, "escalate");
  assert.equal(result.error?.code, "E_LEASE_NO_HANDLE");
});

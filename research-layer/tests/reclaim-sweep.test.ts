import { test } from "node:test";
import assert from "node:assert/strict";

import type { ComputePort, ResourceRequest, TelemetryPort } from "../contracts/src/index.ts";
import { fail, ok } from "../contracts/src/index.ts";
import { createStubStack, StubTelemetryPort } from "../adapters/stub/src/index.ts";
import { createLease, emptyCostLedger } from "../packages/domain/src/index.ts";
import type { CostLedger } from "../packages/domain/src/index.ts";
import { acquireLease, sweepLeases } from "../packages/pipeline/src/index.ts";
import type { AcquireLeaseInput } from "../packages/pipeline/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const START = "2026-10-30T00:00:00.000Z";

function makeRequest(overrides: Partial<ResourceRequest> = {}): ResourceRequest {
  return {
    idempotencyKey: "idem-reclaim-1",
    requestId: "REQ-RECLAIM-1",
    tenantId: "tenant-demo",
    projectId: "project-demo",
    taskId: "TASK-RECLAIM-1",
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

function acquireInput(overrides: Partial<AcquireLeaseInput> = {}): AcquireLeaseInput {
  return {
    request: makeRequest(),
    holder: { type: "attempt", id: "attempt-reclaim-1" },
    ttlSeconds: 3600,
    budget: { limit: 100, currency: "CNY" },
    ledger: emptyCostLedger(),
    ...overrides,
  };
}

function mutableClock(start = START) {
  let current = new Date(start);
  return {
    now: () => current,
    set(value: string) {
      current = new Date(value);
    },
  };
}

function countingRelease(compute: ComputePort): { port: ComputePort; releases: () => number } {
  let releases = 0;
  const port: ComputePort = {
    describe: () => compute.describe(),
    quote: (request) => compute.quote(request),
    submit: (request) => compute.submit(request),
    status: (handleId) => compute.status(handleId),
    list: (filter) => compute.list(filter),
    cancel: (handleId, reason) => compute.cancel(handleId, reason),
    reconcile: (handleId) => compute.reconcile(handleId),
    logs: (handleId, options) => compute.logs(handleId, options),
    release: async (handleId) => {
      releases += 1;
      return compute.release(handleId);
    },
  };
  return { port, releases: () => releases };
}

test("回收扫描：过期资源释放一次，再次扫描不再释放", async () => {
  const clock = mutableClock();
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const watched = countingRelease(stack.compute);
  const telemetry = new StubTelemetryPort();
  const deps = { compute: watched.port, telemetry, now: clock.now };

  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true, JSON.stringify(acquired.findings));
  assert.ok(acquired.lease);

  clock.set("2026-10-30T01:05:00.000Z");
  const first = await sweepLeases(
    {
      leases: [acquired.lease!],
      ledger: acquired.ledger,
      alertAfterSeconds: 300,
      sweepId: "sweep-1",
    },
    deps,
  );
  assert.equal(first.ok, true, JSON.stringify(first.findings));
  assert.equal(first.record.reclaimed, 1);
  assert.equal(first.record.alerts, 1);
  assert.equal(first.record.items[0].code, "LEAK_HELD_AFTER_EXPIRY");
  assert.equal(first.record.items[0].lease_state, "RELEASED");
  assert.equal(watched.releases(), 1);
  assert.equal(telemetry.collected().length, 1);
  assert.equal(telemetry.collected()[0].name, "resource.leak");
  assert.equal(telemetry.collected()[0].metrics?.[0].labels?.code, "LEAK_HELD_AFTER_EXPIRY");
  assert.equal(telemetry.collected()[0].metrics?.[0].labels?.lease_id, undefined);

  const schema = await loadSchema("reclaim-sweep.schema.json");
  assert.deepEqual(validateJsonSchema(first.record, schema), []);

  const second = await sweepLeases(
    { leases: first.leases, ledger: first.ledger, alertAfterSeconds: 300, sweepId: "sweep-2" },
    deps,
  );
  assert.equal(second.ok, true, JSON.stringify(second.findings));
  assert.equal(second.record.reclaimed, 0);
  assert.equal(second.record.alerts, 0);
  assert.equal(second.record.items[0].code, "LEASE_TERMINAL");
  assert.equal(watched.releases(), 1);
  assert.equal(telemetry.collected().length, 1);
});

test("回收扫描：释放时限内回收但不告警，宽限内不释放", async () => {
  const clock = mutableClock();
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const watched = countingRelease(stack.compute);
  const telemetry = new StubTelemetryPort();
  const deps = { compute: watched.port, telemetry, now: clock.now };
  const acquired = await acquireLease(acquireInput({ ttlSeconds: 60 }), deps);
  assert.equal(acquired.ok, true, JSON.stringify(acquired.findings));

  clock.set("2026-10-30T00:01:30.000Z");
  const waiting = await sweepLeases(
    {
      leases: [acquired.lease!],
      ledger: acquired.ledger,
      graceSeconds: 120,
      alertAfterSeconds: 300,
    },
    deps,
  );
  assert.equal(waiting.ok, true, JSON.stringify(waiting.findings));
  assert.equal(waiting.record.items[0].code, "RECONCILE_WAITING");
  assert.equal(waiting.record.alerts, 0);
  assert.equal(watched.releases(), 0);
  assert.notEqual(waiting.leases[0].state, "RELEASED");

  clock.set("2026-10-30T00:03:00.000Z");
  const reclaimed = await sweepLeases(
    {
      leases: waiting.leases,
      ledger: waiting.ledger,
      graceSeconds: 0,
      alertAfterSeconds: 300,
    },
    deps,
  );
  assert.equal(reclaimed.ok, true, JSON.stringify(reclaimed.findings));
  assert.equal(reclaimed.record.items[0].code, "RECLAIM_EXPIRED");
  assert.equal(reclaimed.record.alerts, 0);
  assert.equal(reclaimed.leases[0].state, "RELEASED");
  assert.equal(watched.releases(), 1);
  assert.equal(telemetry.collected().length, 0);
});

test("回收扫描：未知执行不释放，后续扫描也不释放", async () => {
  const clock = mutableClock();
  const stack = createStubStack({ compute: { scenario: "unknown", baseCostPerHour: 24 } });
  const watched = countingRelease(stack.compute);
  const telemetry = new StubTelemetryPort();
  const deps = { compute: watched.port, telemetry, now: clock.now };
  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true, JSON.stringify(acquired.findings));

  clock.set("2026-10-30T01:05:00.000Z");
  const first = await sweepLeases(
    { leases: [acquired.lease!], ledger: acquired.ledger, alertAfterSeconds: 0 },
    deps,
  );
  assert.equal(first.ok, false);
  assert.equal(first.record.escalated, 1);
  assert.equal(first.record.items[0].code, "LEAK_UNKNOWN_EXECUTION");
  assert.equal(watched.releases(), 0);
  assert.ok(first.leases[0].hold_reason?.includes("unknown_execution"));

  const second = await sweepLeases(
    { leases: first.leases, ledger: first.ledger, alertAfterSeconds: 0 },
    deps,
  );
  assert.equal(second.ok, false);
  assert.equal(second.record.items[0].action, "escalate");
  assert.equal(watched.releases(), 0);
  assert.equal(telemetry.collected().length, 2);
});

test("回收扫描：释放失败后下一轮补偿成功", async () => {
  const clock = mutableClock();
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  let attempts = 0;
  const compute: ComputePort = {
    describe: () => stack.compute.describe(),
    quote: (request) => stack.compute.quote(request),
    submit: (request) => stack.compute.submit(request),
    status: (handleId) => stack.compute.status(handleId),
    list: (filter) => stack.compute.list(filter),
    cancel: (handleId, reason) => stack.compute.cancel(handleId, reason),
    reconcile: (handleId) => stack.compute.reconcile(handleId),
    logs: (handleId, options) => stack.compute.logs(handleId, options),
    release: async (handleId) => {
      attempts += 1;
      if (attempts === 1) return fail("UNAVAILABLE", "模拟释放失败");
      return stack.compute.release(handleId);
    },
  };
  const deps = { compute, telemetry: new StubTelemetryPort(), now: clock.now };
  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true, JSON.stringify(acquired.findings));

  clock.set("2026-10-30T01:05:00.000Z");
  const failed = await sweepLeases(
    { leases: [acquired.lease!], ledger: acquired.ledger, alertAfterSeconds: 0 },
    deps,
  );
  assert.equal(failed.ok, false);
  assert.equal(failed.record.items[0].code, "LEAK_RELEASE_FAILED");
  assert.notEqual(failed.leases[0].state, "RELEASED");
  assert.ok(failed.leases[0].hold_reason?.startsWith("release_failed"));

  const recovered = await sweepLeases(
    { leases: failed.leases, ledger: failed.ledger, alertAfterSeconds: 0 },
    deps,
  );
  assert.equal(recovered.ok, true, JSON.stringify(recovered.findings));
  assert.equal(recovered.leases[0].state, "RELEASED");
  assert.equal(attempts, 2);
});

test("回收扫描：周期对账结束已完成作业，确认未执行时不重新提交", async () => {
  const clock = mutableClock();
  const stack = createStubStack({
    compute: { scenario: "success", baseCostPerHour: 24, stepsToTerminal: 1 },
  });
  let submits = 0;
  const compute: ComputePort = {
    describe: () => stack.compute.describe(),
    quote: (request) => stack.compute.quote(request),
    submit: async (request) => {
      submits += 1;
      return stack.compute.submit(request);
    },
    status: (handleId) => stack.compute.status(handleId),
    list: (filter) => stack.compute.list(filter),
    cancel: (handleId, reason) => stack.compute.cancel(handleId, reason),
    reconcile: (handleId) => stack.compute.reconcile(handleId),
    logs: (handleId, options) => stack.compute.logs(handleId, options),
    release: (handleId) => stack.compute.release(handleId),
  };
  const deps = { compute, now: clock.now };
  const acquired = await acquireLease(acquireInput(), deps);
  assert.equal(acquired.ok, true, JSON.stringify(acquired.findings));
  assert.equal(submits, 1);
  const handleId = acquired.lease!.resource.handle_id!;
  await stack.compute.status(handleId);

  const settled = await sweepLeases(
    { leases: [acquired.lease!], ledger: acquired.ledger },
    deps,
  );
  assert.equal(settled.ok, true, JSON.stringify(settled.findings));
  assert.equal(settled.record.items[0].code, "RECONCILE_SETTLED");
  assert.equal(settled.record.alerts, 0);
  assert.equal(settled.leases[0].state, "RELEASED");
  assert.equal(submits, 1);

  const absent = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  let resubmits = 0;
  const blocked: ComputePort = {
    describe: () => absent.compute.describe(),
    quote: (request) => absent.compute.quote(request),
    submit: async (request) => {
      resubmits += 1;
      return absent.compute.submit(request);
    },
    status: (handleId) => absent.compute.status(handleId),
    list: (filter) => absent.compute.list(filter),
    cancel: (handleId, reason) => absent.compute.cancel(handleId, reason),
    reconcile: async () => ok({ verdict: "not_executed_confirmed", reason: "供应商确认未执行" }),
    logs: (handleId, options) => absent.compute.logs(handleId, options),
    release: (handleId) => absent.compute.release(handleId),
  };
  const freshClock = mutableClock();
  const again = await acquireLease(acquireInput({
    request: makeRequest({ idempotencyKey: "idem-reclaim-2", requestId: "REQ-RECLAIM-2" }),
    ledger: emptyCostLedger(),
  }), { compute: blocked, now: freshClock.now });
  assert.equal(again.ok, true, JSON.stringify(again.findings));
  assert.equal(resubmits, 1);

  const allowed = await sweepLeases(
    { leases: [again.lease!], ledger: again.ledger },
    { compute: blocked, now: freshClock.now },
  );
  assert.equal(allowed.ok, true, JSON.stringify(allowed.findings));
  assert.equal(allowed.record.items[0].code, "RECONCILE_RESUBMIT_ALLOWED");
  assert.equal(allowed.leases[0].state, "FAILED");
  assert.equal(resubmits, 1, "扫描不得自动重新提交");
});

test("回收扫描：未持有资源的过期租约只就地过期，遥测失败不阻断回收", async () => {
  const clock = mutableClock();
  const created = createLease({
    lease_id: "LEASE-LOCAL",
    tenant_id: "tenant-demo",
    holder: { type: "task", id: "task-1" },
    resource: { type: "cpu", count: 1 },
    ttl_seconds: 60,
    not_before: START,
    now: new Date(START),
  });
  assert.equal(created.ok, true, JSON.stringify(created.findings));
  const stack = createStubStack();
  const watched = countingRelease(stack.compute);
  const telemetry: TelemetryPort = {
    describe: () => stack.telemetry.describe(),
    emit: async () => fail("UNAVAILABLE", "遥测不可用"),
  };
  clock.set("2026-10-30T00:02:00.000Z");
  const expired = await sweepLeases(
    { leases: [created.lease!], ledger: emptyCostLedger(), alertAfterSeconds: 0 },
    { compute: watched.port, telemetry, now: clock.now },
  );
  assert.equal(expired.ok, true, JSON.stringify(expired.findings));
  assert.equal(expired.record.expired, 1);
  assert.equal(expired.leases[0].state, "EXPIRED");
  assert.equal(watched.releases(), 0);

  const heldClock = mutableClock();
  const heldStack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const held = await acquireLease(acquireInput({
    request: makeRequest({ idempotencyKey: "idem-reclaim-3", requestId: "REQ-RECLAIM-3" }),
  }), { compute: heldStack.compute, now: heldClock.now });
  assert.equal(held.ok, true, JSON.stringify(held.findings));
  heldClock.set("2026-10-30T01:05:00.000Z");
  const reclaimed = await sweepLeases(
    { leases: [held.lease!], ledger: held.ledger, alertAfterSeconds: 0 },
    { compute: heldStack.compute, telemetry, now: heldClock.now },
  );
  assert.equal(reclaimed.ok, true, JSON.stringify(reclaimed.findings));
  assert.equal(reclaimed.leases[0].state, "RELEASED");
  assert.ok(reclaimed.findings.some((entry) => entry.code === "W_TELEMETRY"));
});

test("回收扫描：同一轮只回收过期租约，窗口内作业继续等待", async () => {
  const clock = mutableClock();
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const watched = countingRelease(stack.compute);
  const deps = { compute: watched.port, now: clock.now };
  const ledger: CostLedger = emptyCostLedger();
  const short = await acquireLease(acquireInput({
    ttlSeconds: 60,
    ledger,
    request: makeRequest({ idempotencyKey: "idem-short", requestId: "REQ-SHORT" }),
  }), deps);
  const long = await acquireLease(acquireInput({
    ttlSeconds: 7200,
    ledger: short.ledger,
    request: makeRequest({ idempotencyKey: "idem-long", requestId: "REQ-LONG", taskId: "TASK-LONG" }),
    holder: { type: "attempt", id: "attempt-long" },
  }), deps);
  assert.equal(short.ok, true, JSON.stringify(short.findings));
  assert.equal(long.ok, true, JSON.stringify(long.findings));

  clock.set("2026-10-30T00:02:00.000Z");
  const swept = await sweepLeases(
    {
      leases: [short.lease!, long.lease!],
      ledger: long.ledger,
      alertAfterSeconds: 0,
    },
    deps,
  );
  assert.equal(swept.ok, true, JSON.stringify(swept.findings));
  assert.equal(swept.record.examined, 2);
  assert.equal(swept.record.items[0].lease_state, "RELEASED");
  assert.equal(swept.record.items[1].code, "RECONCILE_WAITING");
  assert.equal(watched.releases(), 1);
  const schema = await loadSchema("reclaim-sweep.schema.json");
  assert.deepEqual(validateJsonSchema(swept.record, schema), []);
});

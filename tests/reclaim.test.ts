import { test } from "node:test";
import assert from "node:assert/strict";

import {
  createLease,
  planLeaseReclaim,
  planReclaimSweep,
  transitionLease,
} from "../packages/domain/src/index.ts";
import type { LeaseRecord } from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const NOT_BEFORE = "2026-10-30T00:00:00.000Z";
const AT = new Date("2026-10-30T00:10:00.000Z");
const EXPIRES = "2026-10-30T01:00:00.000Z";

function makeLease(overrides: Partial<LeaseRecord> = {}): LeaseRecord {
  const created = createLease({
    lease_id: "LEASE-1",
    tenant_id: "tenant-1",
    project_id: "project-1",
    holder: { type: "attempt", id: "attempt-1" },
    resource: { type: "gpu", count: 1 },
    ttl_seconds: 3600,
    not_before: NOT_BEFORE,
    now: new Date(NOT_BEFORE),
  });
  assert.equal(created.ok, true, JSON.stringify(created.findings));
  return { ...created.lease!, ...overrides };
}

function activate(lease: LeaseRecord): LeaseRecord {
  const prepared = transitionLease(lease, "prepare", AT);
  assert.equal(prepared.ok, true);
  const active = transitionLease(prepared.lease, "activate", AT);
  assert.equal(active.ok, true);
  return active.lease;
}

test("回收决策：窗口内保持，宽限内不回收", () => {
  const lease = activate(makeLease());
  const healthy = planLeaseReclaim(lease, AT);
  assert.equal(healthy.action, "keep");
  assert.equal(healthy.alert, false);
  assert.equal(healthy.code, "LEASE_HEALTHY");

  const inGrace = planLeaseReclaim(lease, new Date("2026-10-30T01:01:00.000Z"), {
    graceSeconds: 120,
    alertAfterSeconds: 300,
  });
  assert.equal(inGrace.action, "keep");
  assert.equal(inGrace.code, "LEASE_IN_GRACE");
  assert.equal(inGrace.alert, false);
});

test("回收决策：过期无资源则过期，超时持有资源则告警回收", () => {
  const requested = makeLease();
  const expired = planLeaseReclaim(requested, new Date("2026-10-30T01:05:00.000Z"), {
    alertAfterSeconds: 0,
  });
  assert.equal(expired.action, "expire");
  assert.equal(expired.alert, false);
  assert.equal(expired.code, "LEASE_EXPIRED_NO_RESOURCE");

  const held = makeLease({
    resource: { type: "gpu", count: 1, handle_id: "job-1" },
  });
  const prepared = transitionLease(held, "prepare", AT);
  assert.equal(prepared.ok, true);
  const quiet = planLeaseReclaim(prepared.lease, new Date("2026-10-30T01:01:00.000Z"), {
    alertAfterSeconds: 300,
  });
  assert.equal(quiet.action, "reclaim");
  assert.equal(quiet.alert, false);
  assert.equal(quiet.code, "RECLAIM_EXPIRED");

  const leak = planLeaseReclaim(prepared.lease, new Date("2026-10-30T01:05:00.000Z"), {
    alertAfterSeconds: 300,
  });
  assert.equal(leak.action, "reclaim");
  assert.equal(leak.alert, true);
  assert.equal(leak.code, "LEAK_HELD_AFTER_EXPIRY");
});

test("回收决策：未知执行与未确认回收只升级，释放失败则补偿", () => {
  const active = activate(makeLease({
    resource: { type: "gpu", count: 1, handle_id: "job-1" },
  }));
  const unknown = transitionLease(active, "drain", AT, { reason: "unknown_execution" });
  assert.equal(unknown.lease.hold_reason, "unknown_execution");
  assert.equal(unknown.lease.state, "DRAINING");
  const escalated = planLeaseReclaim(unknown.lease, AT);
  assert.equal(escalated.action, "escalate");
  assert.equal(escalated.code, "LEAK_UNKNOWN_EXECUTION");

  const failedRelease = transitionLease(active, "drain", AT, {
    reason: "release_failed:UNAVAILABLE",
  });
  const compensate = planLeaseReclaim(failedRelease.lease, AT);
  assert.equal(compensate.action, "reclaim");
  assert.equal(compensate.alert, true);
  assert.equal(compensate.code, "LEAK_RELEASE_FAILED");

  const bareDrain = transitionLease(active, "drain", AT);
  const unconfirmed = planLeaseReclaim(bareDrain.lease, AT);
  assert.equal(unconfirmed.action, "escalate");
  assert.equal(unconfirmed.code, "LEAK_DRAIN_UNCONFIRMED");
});

test("回收决策：已释放租约保持安静，ACTIVE 无句柄超时才告警", () => {
  const active = activate(makeLease());
  const released = transitionLease(active, "release", AT, { reason: "completed" });
  const quiet = planLeaseReclaim(released.lease, new Date(EXPIRES));
  assert.equal(quiet.action, "keep");
  assert.equal(quiet.code, "LEASE_TERMINAL");
  assert.equal(quiet.alert, false);

  const missing = planLeaseReclaim(active, new Date("2026-10-30T01:06:00.000Z"), {
    alertAfterSeconds: 300,
  });
  assert.equal(missing.action, "expire");
  assert.equal(missing.alert, true);
  assert.equal(missing.code, "LEAK_ACTIVE_WITHOUT_HANDLE");
});

test("回收决策：扫描计划保持输入顺序", async () => {
  const open = makeLease();
  const done = transitionLease(activate(makeLease({ lease_id: "LEASE-2" })), "release", AT);
  const plan = planReclaimSweep([open, done.lease], AT, { graceSeconds: 0, alertAfterSeconds: 300 });
  assert.equal(plan.examined, 2);
  assert.equal(plan.grace_seconds, 0);
  assert.equal(plan.alert_after_seconds, 300);
  assert.deepEqual(
    plan.items.map((entry) => entry.lease_id),
    ["LEASE-1", "LEASE-2"],
  );
  assert.equal(plan.items[0].code, "LEASE_HEALTHY");
  assert.equal(plan.items[1].code, "LEASE_TERMINAL");

  const schema = await loadSchema("resource-lease.schema.json");
  assert.deepEqual(validateJsonSchema(done.lease, schema), []);
});

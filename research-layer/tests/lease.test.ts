import { test } from "node:test";
import assert from "node:assert/strict";

import {
  canExecuteLease,
  createLease,
  isLeaseTerminal,
  renewLease,
  transitionLease,
} from "../packages/domain/src/index.ts";
import type { CreateLeaseInput, LeaseRecord } from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const NOT_BEFORE = "2026-10-30T00:00:00.000Z";
const AT_10MIN = new Date("2026-10-30T00:10:00.000Z");

function makeLease(overrides: Partial<CreateLeaseInput> = {}): LeaseRecord {
  const result = createLease({
    lease_id: "LEASE-1",
    tenant_id: "tenant-1",
    project_id: "project-1",
    holder: { type: "attempt", id: "attempt-1" },
    resource: { type: "gpu", count: 1, accelerator: "A100-40GB" },
    ttl_seconds: 3600,
    not_before: NOT_BEFORE,
    renewable_until: "2026-10-30T02:00:00.000Z",
    cost: { reserved: 10, currency: "CNY" },
    now: new Date(NOT_BEFORE),
    ...overrides,
  });
  assert.equal(result.ok, true, JSON.stringify(result.findings));
  return result.lease!;
}

function activate(lease: LeaseRecord): LeaseRecord {
  const prepared = transitionLease(lease, "prepare", AT_10MIN);
  assert.equal(prepared.ok, true, JSON.stringify(prepared.findings));
  const active = transitionLease(prepared.lease, "activate", AT_10MIN);
  assert.equal(active.ok, true, JSON.stringify(active.findings));
  return active.lease;
}

test("租约：创建记录符合 schema", async () => {
  const lease = makeLease();
  assert.equal(lease.state, "REQUESTED");
  assert.equal(lease.revision, 1);
  assert.equal(lease.expires_at, "2026-10-30T01:00:00.000Z");

  const schema = await loadSchema("resource-lease.schema.json");
  assert.deepEqual(validateJsonSchema(lease, schema), []);
});

test("租约：非法输入被拒绝", () => {
  const emptyId = createLease({
    lease_id: "",
    tenant_id: "tenant-1",
    holder: { type: "attempt", id: "attempt-1" },
    resource: { type: "gpu", count: 1 },
    ttl_seconds: 60,
  });
  assert.equal(emptyId.ok, false);
  assert.ok(emptyId.findings.some((item) => item.code === "E_LEASE_ID"));

  const badTtl = createLease({
    lease_id: "LEASE-2",
    tenant_id: "tenant-1",
    holder: { type: "attempt", id: "attempt-1" },
    resource: { type: "gpu", count: 1 },
    ttl_seconds: 0,
  });
  assert.equal(badTtl.ok, false);
  assert.ok(badTtl.findings.some((item) => item.code === "E_LEASE_TTL"));

  const badResource = createLease({
    lease_id: "LEASE-3",
    tenant_id: "tenant-1",
    holder: { type: "attempt", id: "attempt-1" },
    resource: { type: "gpu", count: 0 },
    ttl_seconds: 60,
  });
  assert.equal(badResource.ok, false);
  assert.ok(badResource.findings.some((item) => item.code === "E_LEASE_RESOURCE"));
});

test("租约：只有 ACTIVE 且未过期可以执行", () => {
  const lease = makeLease();
  assert.equal(canExecuteLease(lease, AT_10MIN).ok, false);

  const active = activate(lease);
  assert.equal(active.state, "ACTIVE");
  assert.equal(canExecuteLease(active, AT_10MIN).ok, true);
  assert.equal(
    canExecuteLease(active, new Date("2026-10-30T01:00:00.000Z")).ok,
    false,
  );
});

test("租约：状态迁移、幂等释放与终态保护", () => {
  const lease = makeLease();
  const prepared = transitionLease(lease, "prepare", AT_10MIN);
  assert.equal(prepared.lease.state, "PREPARED");

  const active = transitionLease(prepared.lease, "activate", AT_10MIN);
  assert.equal(active.lease.state, "ACTIVE");
  assert.equal(active.lease.revision, 3);

  const draining = transitionLease(active.lease, "drain", new Date("2026-10-30T00:20:00.000Z"));
  assert.equal(draining.lease.state, "DRAINING");

  const released = transitionLease(
    draining.lease,
    "release",
    new Date("2026-10-30T00:30:00.000Z"),
    { reason: "completed" },
  );
  assert.equal(released.ok, true);
  assert.equal(released.lease.state, "RELEASED");
  assert.equal(released.lease.release_reason, "completed");
  assert.equal(released.lease.released_at, "2026-10-30T00:30:00.000Z");
  assert.equal(isLeaseTerminal(released.lease.state), true);

  const again = transitionLease(released.lease, "release", new Date("2026-10-30T00:40:00.000Z"));
  assert.equal(again.ok, true);
  assert.equal(again.changed, false);

  const impossible = transitionLease(released.lease, "activate", new Date("2026-10-30T00:40:00.000Z"));
  assert.equal(impossible.ok, false);
  assert.ok(impossible.findings.some((item) => item.code === "E_LEASE_TERMINAL"));
});

test("租约：未生效、已过期与非法迁移被拒绝", () => {
  const lease = makeLease({
    not_before: "2026-10-30T00:30:00.000Z",
  });
  const tooEarly = transitionLease(
    transitionLease(lease, "prepare", AT_10MIN).lease,
    "activate",
    AT_10MIN,
  );
  assert.equal(tooEarly.ok, false);
  assert.ok(tooEarly.findings.some((item) => item.code === "E_LEASE_NOT_YET_VALID"));

  const normal = makeLease();
  const invalid = transitionLease(normal, "activate", AT_10MIN);
  assert.equal(invalid.ok, false);
  assert.ok(invalid.findings.some((item) => item.code === "E_LEASE_TRANSITION"));

  const expiredAttempt = transitionLease(
    transitionLease(normal, "prepare", AT_10MIN).lease,
    "activate",
    new Date("2026-10-30T01:00:00.000Z"),
  );
  assert.equal(expiredAttempt.ok, false);
  assert.ok(expiredAttempt.findings.some((item) => item.code === "E_LEASE_EXPIRED"));

  const notYetExpired = transitionLease(normal, "expire", AT_10MIN);
  assert.equal(notYetExpired.ok, false);
  assert.ok(notYetExpired.findings.some((item) => item.code === "E_LEASE_NOT_EXPIRED"));

  const expired = transitionLease(normal, "expire", new Date("2026-10-30T01:00:00.000Z"));
  assert.equal(expired.ok, true);
  assert.equal(expired.lease.state, "EXPIRED");
});

test("租约：续租提升 fencing token 并检查时间与预算", () => {
  const active = activate(makeLease());
  const renewed = renewLease(active, {
    expires_at: "2026-10-30T01:30:00.000Z",
    at: AT_10MIN,
    remainingBudget: 20,
    additionalCost: 5,
  });
  assert.equal(renewed.ok, true, JSON.stringify(renewed.findings));
  assert.equal(renewed.lease.fencing_token, active.fencing_token + 1);
  assert.equal(renewed.lease.revision, active.revision + 1);
  assert.equal(renewed.lease.expires_at, "2026-10-30T01:30:00.000Z");
  assert.equal(canExecuteLease(renewed.lease, new Date("2026-10-30T01:20:00.000Z")).ok, true);

  const overBudget = renewLease(active, {
    expires_at: "2026-10-30T01:30:00.000Z",
    at: AT_10MIN,
    remainingBudget: 1,
    additionalCost: 5,
  });
  assert.equal(overBudget.ok, false);
  assert.ok(overBudget.findings.some((item) => item.code === "E_LEASE_BUDGET"));

  const overLimit = renewLease(active, {
    expires_at: "2026-10-30T02:30:00.000Z",
    at: AT_10MIN,
  });
  assert.equal(overLimit.ok, false);
  assert.ok(overLimit.findings.some((item) => item.code === "E_LEASE_RENEW_LIMIT"));

  const afterExpiry = renewLease(active, {
    expires_at: "2026-10-30T01:30:00.000Z",
    at: new Date("2026-10-30T01:10:00.000Z"),
  });
  assert.equal(afterExpiry.ok, false);
  assert.ok(afterExpiry.findings.some((item) => item.code === "E_LEASE_EXPIRED"));

  const released = transitionLease(active, "release", AT_10MIN).lease;
  const terminalRenew = renewLease(released, {
    expires_at: "2026-10-30T02:00:00.000Z",
    at: AT_10MIN,
  });
  assert.equal(terminalRenew.ok, false);
  assert.ok(
    terminalRenew.findings.some((item) => item.code === "E_LEASE_RENEW_TERMINAL"),
  );
});

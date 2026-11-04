import { test } from "node:test";
import assert from "node:assert/strict";

import type { ResourceKind, ResourceRequest } from "../contracts/src/index.ts";
import { isRetryable } from "../contracts/src/index.ts";
import {
  COMPANY_ADAPTER,
  CompanyComputePort,
  assessConformance,
  mapProviderState,
} from "../adapters/company-agent/src/translate.ts";

function resource(overrides: Partial<ResourceRequest> = {}): ResourceRequest {
  return {
    idempotencyKey: "idem-1",
    requestId: "req-1",
    tenantId: "tenant-a",
    kind: "hpc",
    count: 1,
    wallClockSeconds: 60,
    ...overrides,
  };
}

test("company adapter stays degraded and keeps each resource kind", async () => {
  assert.equal(COMPANY_ADAPTER.degraded, true);
  const described = await new CompanyComputePort().describe();
  assert.equal(described.ok, true);
  if (!described.ok) return;
  assert.equal(described.value.degraded, true);
  assert.deepEqual(described.value.kinds, ["cpu", "gpu", "hpc", "cloud", "browser"]);

  for (const kind of ["cpu", "gpu", "hpc", "cloud", "browser"] as const satisfies readonly ResourceKind[]) {
    const port = new CompanyComputePort();
    const submitted = await port.submit(resource({ kind, requestId: kind, idempotencyKey: kind }));
    assert.equal(submitted.ok, true);
    if (!submitted.ok) return;
    assert.equal(submitted.value.kind, kind);
    const envelope = port.envelopeFor(submitted.value.handleId);
    assert.equal(envelope.ok, true);
    if (!envelope.ok) return;
    assert.equal(envelope.value.kind, kind);
    assert.equal(envelope.value.operation, `${kind}.submit`);
    assert.equal(envelope.value.protocol, "company-agent-provider/1.0");
    assert.equal(envelope.value.tenant_id, "tenant-a");
  }
});

test("repeated submit stays on the same adapter instance", async () => {
  const firstPort = new CompanyComputePort();
  const secondPort = new CompanyComputePort();
  const request = resource();
  const first = await firstPort.submit(request);
  const second = await firstPort.submit(request);
  assert.equal(first.ok, true);
  assert.equal(second.ok, true);
  if (!first.ok || !second.ok) return;
  assert.equal(second.value.handleId, first.value.handleId);
  assert.equal(firstPort.submissionCount, 1);
  const elsewhere = await secondPort.status(first.value.handleId);
  assert.equal(elsewhere.ok, false);
  const createdAgain = await secondPort.submit(request);
  assert.equal(createdAgain.ok, true);
  assert.equal(secondPort.submissionCount, 1);
  assert.equal(firstPort.submissionCount, 1);
});

test("secret fields are rejected before an envelope is built", async () => {
  const port = new CompanyComputePort();
  const result = await port.submit(resource({ env: { API_KEY: "hidden" } }));
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.error.code, "INVALID_ARGUMENT");
  assert.equal(isRetryable(result), false);
  assert.equal(port.submissionCount, 0);
});

test("observed states can be queried and cannot be resubmitted", () => {
  for (const providerState of ["", "timeout", "pending", "unknown", "TIMEOUT", "vendor-specific"]) {
    const mapped = mapProviderState(providerState);
    assert.equal(mapped.state, "unknown");
    assert.equal(mapped.queryable, true);
    assert.equal(mapped.resubmittable, false);
  }
  for (const providerState of ["queued", "starting", "running", "succeeded", "failed", "cancelled"]) {
    const mapped = mapProviderState(providerState);
    assert.equal(mapped.state, providerState);
    assert.equal(mapped.queryable, true);
    assert.equal(mapped.resubmittable, false);
  }
});

test("queued execution is not resubmitted", async () => {
  const port = new CompanyComputePort();
  const submitted = await port.submit(resource());
  assert.equal(submitted.ok, true);
  if (!submitted.ok) return;
  const noted = port.noteProviderState(submitted.value.handleId, "running");
  assert.equal(noted.ok, true);
  if (!noted.ok) return;
  assert.equal(noted.value.state, "running");
  const access = mapProviderState("running");
  assert.equal(access.queryable, true);
  assert.equal(access.resubmittable, false);
  const again = await port.submit(resource());
  assert.equal(again.ok, true);
  if (!again.ok) return;
  assert.equal(again.value.handleId, submitted.value.handleId);
  assert.equal(port.submissionCount, 1);
});

test("qpu produces a device approval handoff and no job", async () => {
  const port = new CompanyComputePort();
  const result = await port.submit(resource({ kind: "qpu" }));
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.error.code, "PERMISSION_DENIED");
  assert.equal(isRetryable(result), false);
  assert.deepEqual(result.error.details, {
    tenant_id: "tenant-a",
    request_id: "req-1",
    idempotency_key: "idem-1",
    mandate: "lab",
    tool: "quantum_device_run",
  });
  assert.equal(port.submissionCount, 0);
  assert.equal(JSON.stringify(result).includes("circuit"), false);
  const repeated = await port.submit(resource({ kind: "qpu" }));
  assert.equal(repeated.ok, false);
  if (repeated.ok) return;
  assert.deepEqual(repeated.error.details, result.error.details);
  const conflict = await port.submit(resource({ kind: "qpu", requestId: "req-2" }));
  assert.equal(conflict.ok, false);
  if (conflict.ok) return;
  assert.equal(conflict.error.code, "CONFLICT");
});

test("conformance admits only the safe cases while degraded", async () => {
  const admission = await assessConformance(new CompanyComputePort());
  assert.deepEqual(admission.passed, ["HP-02", "HP-05", "CL-01"]);
  assert.deepEqual(admission.blocked, ["HP-03", "HP-06", "HP-01", "MD-01"]);
  const claimed = [...admission.passed, ...admission.blocked];
  assert.equal(claimed.some((id) => id.startsWith("ID-")), false);
  assert.equal(claimed.some((id) => id.startsWith("OS-")), false);
  assert.equal(claimed.some((id) => id.startsWith("SS-")), false);
  const port = new CompanyComputePort();
  assert.equal("complete" in port, false);
  const quote = await port.quote(resource());
  const logs = await port.logs("company-job-1");
  assert.equal(quote.ok, false);
  assert.equal(logs.ok, false);
  if (quote.ok || logs.ok) return;
  assert.equal(JSON.stringify(quote).includes("estimatedCost"), false);
  assert.equal(JSON.stringify(logs).includes("lines"), false);
});

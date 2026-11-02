import { test } from "node:test";
import assert from "node:assert/strict";

import { CONTRACT_VERSION, isRetryable, unwrap } from "../contracts/src/index.ts";
import type { ModelRequest, ResourceRequest, Subject } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";

const agent: Subject = {
  type: "agent",
  id: "agent-1",
  tenantId: "tenant-demo",
  projectId: "project-demo",
  scopes: ["experiment:submit", "literature:read"],
};

function jobRequest(overrides: Partial<ResourceRequest> = {}): ResourceRequest {
  return {
    idempotencyKey: "idem-job-1",
    requestId: "req-1",
    tenantId: "tenant-demo",
    projectId: "project-demo",
    taskId: "task-1",
    kind: "gpu",
    count: 1,
    wallClockSeconds: 600,
    maxCost: 20,
    currency: "CNY",
    ...overrides,
  };
}

function modelRequest(overrides: Partial<ModelRequest> = {}): ModelRequest {
  return {
    requestId: "model-req-1",
    tenantId: "tenant-demo",
    taskType: "coding",
    messages: [{ role: "user", content: "hello" }],
    maxOutputTokens: 64,
    dataClass: "internal",
    ...overrides,
  };
}

test("所有桩通过 describe 声明 degraded 并给出原因", async () => {
  const stack = createStubStack();
  const ports = [
    stack.identity,
    stack.secrets,
    stack.artifacts,
    stack.model,
    stack.compute,
    stack.events,
    stack.session,
    stack.telemetry,
  ] as const;

  for (const port of ports) {
    const result = await port.describe();
    assert.equal(result.ok, true);
    if (!result.ok) continue;
    assert.equal(result.value.degraded, true);
    assert.ok(
      typeof result.value.degradedReason === "string" && result.value.degradedReason.length > 0,
      `${result.value.implementation} 缺少 degradedReason`,
    );
    assert.equal(result.value.contractVersion, CONTRACT_VERSION);
  }
});

test("端口方法齐全", () => {
  const stack = createStubStack();
  const expectations: Array<[object, string[]]> = [
    [stack.identity, ["describe", "verify", "authorize", "revoke"]],
    [stack.secrets, ["describe", "issue", "revoke", "status"]],
    [stack.artifacts, ["describe", "put", "stat", "get", "signedUrl", "list", "setRetention"]],
    [stack.model, ["describe", "complete", "stream", "health"]],
    [stack.compute, ["describe", "quote", "submit", "status", "list", "cancel", "reconcile", "logs", "release"]],
    [stack.events, ["describe", "publish", "subscribe"]],
    [stack.session, ["describe", "start", "subscribe", "wait", "cancel"]],
    [stack.telemetry, ["describe", "emit"]],
  ];

  for (const [target, methods] of expectations) {
    for (const method of methods) {
      assert.equal(
        typeof (target as Record<string, unknown>)[method],
        "function",
        `缺少方法 ${method}`,
      );
    }
  }
});

test("UNKNOWN_EXECUTION 不可重试", async () => {
  const stack = createStubStack({ compute: { scenario: "unknown" } });
  const handle = unwrap(await stack.compute.submit(jobRequest()));
  const status = unwrap(await stack.compute.status(handle.handleId));
  assert.equal(status.state, "unknown");

  const evidence = unwrap(await stack.compute.reconcile(handle.handleId));
  assert.equal(evidence.verdict, "unknown");

  const failed = { ok: false as const, error: { code: "UNKNOWN_EXECUTION" as const, message: "x", retryable: false } };
  assert.equal(isRetryable(failed), false);
});

test("身份端口：校验、撤销、越权", async () => {
  const stack = createStubStack();
  const verified = unwrap(await stack.identity.verify({ token: "stub-token" }));
  assert.equal(verified.subject.tenantId, "tenant-demo");

  const revoked = unwrap(await stack.identity.revoke(verified.tokenId));
  void revoked;
  const afterRevoke = await stack.identity.verify({ token: "stub-token" });
  assert.equal(afterRevoke.ok, false);

  const denied = unwrap(
    await stack.identity.authorize({
      subject: agent,
      action: "qpu:control",
      resource: { type: "qpu", tenantId: "tenant-demo" },
    }),
  );
  assert.equal(denied.decision, "REQUIRE_APPROVAL");

  const noScope = unwrap(
    await stack.identity.authorize({
      subject: agent,
      action: "workspace:admin",
      resource: { type: "workspace", tenantId: "tenant-demo" },
    }),
  );
  assert.equal(noScope.decision, "DENY");
});

test("凭据端口：拒绝通配 scope、TTL 上限与撤销", async () => {
  const stack = createStubStack({ secrets: { maxTtlSeconds: 600 } });

  const tooLong = await stack.secrets.issue({
    subject: agent,
    audience: "hpc",
    scope: ["submit"],
    ttlSeconds: 601,
  });
  assert.equal(tooLong.ok, false);

  const wildcard = await stack.secrets.issue({
    subject: agent,
    audience: "hpc",
    scope: ["*"],
    ttlSeconds: 60,
  });
  assert.equal(wildcard.ok, false);

  const issued = unwrap(
    await stack.secrets.issue({
      subject: agent,
      audience: "hpc",
      scope: ["submit"],
      ttlSeconds: 60,
      idempotencyKey: "cred-1",
    }),
  );
  const again = unwrap(
    await stack.secrets.issue({
      subject: agent,
      audience: "hpc",
      scope: ["submit"],
      ttlSeconds: 60,
      idempotencyKey: "cred-1",
    }),
  );
  assert.equal(issued.credentialId, again.credentialId);

  unwrap(await stack.secrets.revoke(issued.credentialId));
  const status = unwrap(await stack.secrets.status(issued.credentialId));
  assert.equal(status.active, false);
});

test("产物端口：哈希、租户隔离与签名 URL", async () => {
  const stack = createStubStack();
  const body = new TextEncoder().encode("hello");

  const bad = await stack.artifacts.put({
    tenantId: "tenant-demo",
    key: "a/b.json",
    contentType: "application/json",
    bytes: body,
    expectedSha256: "0".repeat(64),
  });
  assert.equal(bad.ok, false);

  const put = unwrap(
    await stack.artifacts.put({
      tenantId: "tenant-demo",
      key: "a/b.json",
      contentType: "application/json",
      bytes: body,
    }),
  );

  const cross = await stack.artifacts.get({ tenantId: "tenant-other", artifactId: put.artifactId });
  assert.equal(cross.ok, false);

  const read = unwrap(await stack.artifacts.get({ tenantId: "tenant-demo", artifactId: put.artifactId }));
  assert.equal(new TextDecoder().decode(read.bytes), "hello");

  const url = unwrap(
    await stack.artifacts.signedUrl({
      tenantId: "tenant-demo",
      artifactId: put.artifactId,
      method: "GET",
      ttlSeconds: 60,
    }),
  );
  assert.ok(url.url.startsWith("stub://signed/"));
});

test("模型端口：数据等级、结构化输出与流式", async () => {
  const stack = createStubStack({ model: { maxDataClass: "internal" } });

  const restricted = await stack.model.complete(modelRequest({ dataClass: "restricted" }));
  assert.equal(restricted.ok, false);
  if (!restricted.ok) assert.equal(restricted.error.code, "PERMISSION_DENIED");

  const structured = unwrap(
    await stack.model.complete(
      modelRequest({
        responseFormat: { type: "json_schema", name: "out", schema: { type: "object" } },
      }),
    ),
  );
  assert.deepEqual(structured.json, { stub: true, echo: "hello" });

  const chunks: string[] = [];
  for await (const event of stack.model.stream(modelRequest({ requestId: "s2" }))) {
    if (event.type === "text_delta") chunks.push(event.text);
  }
  assert.ok(chunks.join("").length > 0);

  const noStream = createStubStack({ model: { supportsStreaming: false } });
  const events = [];
  for await (const event of noStream.model.stream(modelRequest())) events.push(event);
  assert.equal(events[0]?.type, "error");
});

test("算力端口：幂等、报价、未知执行与释放", async () => {
  const stack = createStubStack();
  const first = unwrap(await stack.compute.submit(jobRequest()));
  const second = unwrap(await stack.compute.submit(jobRequest()));
  assert.equal(first.handleId, second.handleId);

  const quote = unwrap(await stack.compute.quote(jobRequest()));
  assert.ok((quote.estimatedCost ?? 0) > 0);

  const cancelled = unwrap(await stack.compute.cancel(first.handleId, "test"));
  assert.equal(cancelled.state, "cancelled");

  unwrap(await stack.compute.release(first.handleId));
});

test("事件端口：幂等发布与订阅过滤", async () => {
  const stack = createStubStack();
  const received: string[] = [];
  unwrap(
    await stack.events.subscribe({ tenantId: "tenant-demo", types: ["experiment.decided.v1"] }, async (event) => {
      received.push(event.id);
      return "ack";
    }),
  );

  const event = {
    id: "evt-1",
    type: "experiment.decided.v1",
    source: "test",
    tenantId: "tenant-demo",
    time: new Date().toISOString(),
    dataContentType: "application/json" as const,
    data: {},
  };
  unwrap(await stack.events.publish(event));
  unwrap(await stack.events.publish(event));
  assert.deepEqual(received, ["evt-1"]);
});

test("会话端口：预算超限与取消", async () => {
  const stack = createStubStack({ session: { turns: 2, exceedBudget: true } });
  const request = {
    sessionId: "s1",
    tenantId: "tenant-demo",
    taskId: "t1",
    agentId: "a1",
    workspaceId: "w1",
    allowedTools: ["read"],
    budget: { maxCost: 1, currency: "CNY", maxTurns: 3, maxToolCalls: 5, maxWallClockSeconds: 60 },
    instruction: "do it",
  };
  unwrap(await stack.session.start(request));
  const result = unwrap(await stack.session.wait("s1"));
  assert.equal(result.state, "budget_exceeded");

  const cancelStack = createStubStack();
  unwrap(await cancelStack.session.start({ ...request, sessionId: "s2" }));
  unwrap(await cancelStack.session.cancel("s2", "user"));
  const cancelled = unwrap(await cancelStack.session.wait("s2"));
  assert.equal(cancelled.state, "cancelled");
});

test("遥测端口：拒绝未脱敏与敏感字段", async () => {
  const stack = createStubStack();
  const base = {
    name: "x",
    at: new Date().toISOString(),
    traceId: "trace-1",
    tenantId: "tenant-demo",
    redactionApplied: true,
  };

  const notRedacted = await stack.telemetry.emit({ ...base, redactionApplied: false });
  assert.equal(notRedacted.ok, false);

  const sensitive = await stack.telemetry.emit({ ...base, attributes: { api_key: "x" } });
  assert.equal(sensitive.ok, false);

  const good = await stack.telemetry.emit({ ...base, attributes: { action: "keep" } });
  assert.equal(good.ok, true);
});

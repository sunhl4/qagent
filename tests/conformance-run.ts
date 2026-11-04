/**
 * 把 contracts/conformance/cases.yaml 的 36 条用例逐条跑在本地桩上。
 *
 * 状态约定：
 * - passed：桩的可观察行为满足用例。用例里的 POLICY_DENIED / INVALID_REQUEST / submitted
 *   分别对应契约的 PERMISSION_DENIED 或 authorize=DENY、INVALID_ARGUMENT、queued+submittedAt。
 * - blocked：现行端口类型或桩能力做不到原文，不能记成通过。
 * - failed：本应通过，但桩行为不符合。
 *
 * 这是 provenance=stub 的开发结果，不是 harness-core 的验收结果。
 */

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";

import { isRetryable, unwrap } from "../contracts/src/index.ts";
import type {
  ModelRequest,
  ResourceRequest,
  SessionRequest,
  Subject,
} from "../contracts/src/index.ts";
import { createStubStack, StubArtifactStorePort, StubTelemetryPort } from "../adapters/stub/src/index.ts";
import { evaluatePolicy } from "../packages/domain/src/index.ts";
import { validateJsonSchema } from "./schema-validator.ts";

export interface CaseRun {
  case_id: string;
  port: string;
  level: "MUST" | "SHOULD";
  status: "passed" | "failed" | "pending" | "blocked";
  notes?: string;
}

interface CaseMeta {
  case_id: string;
  port: string;
  level: "MUST" | "SHOULD";
}

const AGENT: Subject = {
  type: "agent",
  id: "agent-conformance",
  tenantId: "tenant-demo",
  projectId: "project-demo",
  scopes: ["experiment:submit", "literature:read"],
};

function meta(caseId: string, port: string, level: "MUST" | "SHOULD" = "MUST"): CaseMeta {
  return { case_id: caseId, port, level };
}

function passed(item: CaseMeta, notes: string): CaseRun {
  return { ...item, status: "passed", notes };
}

function blocked(item: CaseMeta, notes: string): CaseRun {
  return { ...item, status: "blocked", notes };
}

function failed(item: CaseMeta, error: unknown): CaseRun {
  const message = error instanceof Error ? error.message : String(error);
  return { ...item, status: "failed", notes: message };
}

async function attempt(item: CaseMeta, notes: string, run: () => Promise<void>): Promise<CaseRun> {
  try {
    await run();
    return passed(item, notes);
  } catch (error) {
    return failed(item, error);
  }
}

function sha256(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function job(overrides: Partial<ResourceRequest> = {}): ResourceRequest {
  return {
    idempotencyKey: "idem-conformance",
    requestId: "req-conformance",
    tenantId: "tenant-demo",
    projectId: "project-demo",
    taskId: "task-conformance",
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
    requestId: "model-conformance",
    tenantId: "tenant-demo",
    taskType: "coding",
    messages: [{ role: "user", content: "hello" }],
    maxOutputTokens: 64,
    dataClass: "internal",
    ...overrides,
  };
}

function sessionRequest(overrides: Partial<SessionRequest> = {}): SessionRequest {
  return {
    sessionId: "session-conformance",
    tenantId: "tenant-demo",
    taskId: "task-conformance",
    agentId: "agent-conformance",
    workspaceId: "workspace-conformance",
    allowedTools: ["read"],
    budget: { maxCost: 1, currency: "CNY", maxTurns: 3, maxToolCalls: 5, maxWallClockSeconds: 60 },
    instruction: "run the conformance case",
    ...overrides,
  };
}

async function identityCases(): Promise<CaseRun[]> {
  const id01 = meta("ID-01", "identity");
  const id02 = meta("ID-02", "identity");
  const id03 = meta("ID-03", "identity");
  const id04 = meta("ID-04", "identity");
  const id05 = meta("ID-05", "identity");

  return [
    await attempt(id01, "verify 返回 subject，含 tenantId 与 scopes。", async () => {
      const stack = createStubStack();
      const verified = unwrap(await stack.identity.verify({ token: "stub-token" }));
      assert.equal(verified.subject.tenantId, "tenant-demo");
      assert.ok((verified.subject.scopes ?? []).length > 0);
    }),
    await attempt(
      id02,
      "过期 token 返回 PERMISSION_DENIED 且 retryable=false。用例文案 POLICY_DENIED 对应该错误码。",
      async () => {
        let now = Date.parse("2026-11-03T00:00:00.000Z");
        const stack = createStubStack({ clock: () => new Date(now) });
        now += 3600_000 + 1;
        const expired = await stack.identity.verify({ token: "stub-token" });
        assert.equal(expired.ok, false);
        if (!expired.ok) {
          assert.equal(expired.error.code, "PERMISSION_DENIED");
          assert.equal(expired.error.retryable, false);
        }
      },
    ),
    await attempt(
      id03,
      "verify 没有 expectedTenantId。跨租户由 authorize 返回 DENY，对应用例的 POLICY_DENIED。",
      async () => {
        const stack = createStubStack();
        const verified = unwrap(await stack.identity.verify({ token: "stub-token" }));
        const decision = unwrap(
          await stack.identity.authorize({
            subject: verified.subject,
            action: "experiment:submit",
            resource: { type: "experiment", tenantId: "tenant-other" },
          }),
        );
        assert.equal(decision.decision, "DENY");
      },
    ),
    await attempt(
      id04,
      "父主体只有 read scope 时，申请 qpu:control 得到 DENY，不再升成审批。",
      async () => {
        const stack = createStubStack();
        const decision = unwrap(
          await stack.identity.authorize({
            subject: { ...AGENT, scopes: ["read"] },
            action: "qpu:control",
            resource: { type: "qpu", tenantId: AGENT.tenantId },
          }),
        );
        assert.equal(decision.decision, "DENY");
      },
    ),
    await attempt(id05, "revoke 之后再次 verify 失败。", async () => {
      const stack = createStubStack();
      const verified = unwrap(await stack.identity.verify({ token: "stub-token" }));
      unwrap(await stack.identity.revoke(verified.tokenId));
      const again = await stack.identity.verify({ token: "stub-token" });
      assert.equal(again.ok, false);
    }),
  ];
}

async function objectCases(): Promise<CaseRun[]> {
  const os01 = meta("OS-01", "object_store");
  const os02 = meta("OS-02", "object_store");
  const os03 = meta("OS-03", "object_store");
  const os04 = meta("OS-04", "object_store");
  const os05 = meta("OS-05", "object_store");

  return [
    await attempt(os01, "put 后 get，sha256 与内容一致。", async () => {
      const stack = createStubStack();
      const bytes = new TextEncoder().encode("hello");
      const put = unwrap(
        await stack.artifacts.put({
          tenantId: "tenant-demo",
          key: "runs/hello.txt",
          contentType: "text/plain",
          bytes,
          expectedSha256: sha256(bytes),
        }),
      );
      const read = unwrap(await stack.artifacts.get({ tenantId: "tenant-demo", artifactId: put.artifactId }));
      assert.equal(read.ref.sha256, put.sha256);
      assert.equal(new TextDecoder().decode(read.bytes), "hello");
    }),
    await attempt(
      os02,
      "声明哈希不符时返回 INVALID_ARGUMENT（用例文案 INVALID_REQUEST），对象数不变。",
      async () => {
        const stack = createStubStack();
        const store = stack.artifacts as StubArtifactStorePort;
        const bad = await store.put({
          tenantId: "tenant-demo",
          key: "runs/bad.txt",
          contentType: "text/plain",
          bytes: new TextEncoder().encode("hello"),
          expectedSha256: "0".repeat(64),
        });
        assert.equal(bad.ok, false);
        if (!bad.ok) assert.equal(bad.error.code, "INVALID_ARGUMENT");
        assert.equal(store.size(), 0);
      },
    ),
    await attempt(os03, "超过上限时返回 INVALID_ARGUMENT，不截断写入。", async () => {
      const stack = createStubStack({ artifacts: { maxObjectBytes: 4 } });
      const store = stack.artifacts as StubArtifactStorePort;
      const over = await store.put({
        tenantId: "tenant-demo",
        key: "runs/big.bin",
        contentType: "application/octet-stream",
        bytes: new Uint8Array(5),
      });
      assert.equal(over.ok, false);
      if (!over.ok) assert.equal(over.error.code, "INVALID_ARGUMENT");
      assert.equal(store.size(), 0);
    }),
    await attempt(os04, "不存在的 uri 返回 NOT_FOUND。", async () => {
      const stack = createStubStack();
      const missing = await stack.artifacts.get({ tenantId: "tenant-demo", uri: "stub://missing" });
      assert.equal(missing.ok, false);
      if (!missing.ok) assert.equal(missing.error.code, "NOT_FOUND");
    }),
    await attempt(
      os05,
      "端口没有兑付方法；桩的 accessSignedUrl 在 TTL 之后拒绝。真实存储在 HTTP 层做同样的事。",
      async () => {
        let now = Date.parse("2026-11-03T00:00:00.000Z");
        const stack = createStubStack({ clock: () => new Date(now) });
        const store = stack.artifacts as StubArtifactStorePort;
        const put = unwrap(
          await store.put({
            tenantId: "tenant-demo",
            key: "runs/signed.txt",
            contentType: "text/plain",
            bytes: new TextEncoder().encode("signed"),
          }),
        );
        const signed = unwrap(
          await store.signedUrl({
            tenantId: "tenant-demo",
            artifactId: put.artifactId,
            method: "GET",
            ttlSeconds: 30,
          }),
        );
        assert.equal(store.accessSignedUrl(signed.url).ok, true);
        now += 31_000;
        const expired = store.accessSignedUrl(signed.url);
        assert.equal(expired.ok, false);
      },
    ),
  ];
}

async function credentialCases(): Promise<CaseRun[]> {
  const cr01 = meta("CR-01", "credentials");
  const cr02 = meta("CR-02", "credentials");
  const cr03 = meta("CR-03", "credentials");
  const cr04 = meta("CR-04", "credentials");

  return [
    await attempt(cr01, "签发的凭据 TTL 不超过请求的 60 秒。", async () => {
      const stack = createStubStack();
      const issued = unwrap(
        await stack.secrets.issue({
          subject: AGENT,
          audience: "hpc",
          scope: ["experiment:submit"],
          ttlSeconds: 60,
        }),
      );
      assert.ok(issued.value.length > 0);
      const ttlMs = Date.parse(issued.expiresAt) - Date.parse(issued.issuedAt);
      assert.ok(ttlMs <= 60_000);
    }),
    await attempt(cr02, "scope 超出主体权限时返回 PERMISSION_DENIED。", async () => {
      const stack = createStubStack();
      const denied = await stack.secrets.issue({
        subject: { ...AGENT, scopes: ["read"] },
        audience: "hpc",
        scope: ["qpu:control"],
        ttlSeconds: 60,
      });
      assert.equal(denied.ok, false);
      if (!denied.ok) assert.equal(denied.error.code, "PERMISSION_DENIED");
    }),
    await attempt(cr03, "scope 中带 sk- 开头的密钥时返回 INVALID_ARGUMENT。", async () => {
      const stack = createStubStack();
      const denied = await stack.secrets.issue({
        subject: AGENT,
        audience: "hpc",
        scope: ["sk-live-secret"],
        ttlSeconds: 60,
      });
      assert.equal(denied.ok, false);
      if (!denied.ok) assert.equal(denied.error.code, "INVALID_ARGUMENT");
    }),
    await attempt(cr04, "revoke 后 status.active 为 false。", async () => {
      const stack = createStubStack();
      const issued = unwrap(
        await stack.secrets.issue({
          subject: AGENT,
          audience: "hpc",
          scope: ["experiment:submit"],
          ttlSeconds: 60,
        }),
      );
      unwrap(await stack.secrets.revoke(issued.credentialId));
      const status = unwrap(await stack.secrets.status(issued.credentialId));
      assert.equal(status.active, false);
    }),
  ];
}

async function modelCases(): Promise<CaseRun[]> {
  const md01 = meta("MD-01", "model");
  const md02 = meta("MD-02", "model");
  const md03 = meta("MD-03", "model");
  const md04 = meta("MD-04", "model");
  const md05 = meta("MD-05", "model", "SHOULD");
  const strictSchema = {
    type: "object",
    additionalProperties: false,
    required: ["answer"],
    properties: { answer: { type: "string" } },
  };

  const md02Run = await (async (): Promise<CaseRun> => {
    try {
      const stack = createStubStack();
      const result = await stack.model.complete(
        modelRequest({
          requestId: "model-schema",
          responseFormat: { type: "json_schema", name: "out", schema: strictSchema },
        }),
      );
      if (result.ok && validateJsonSchema(result.value.json, strictSchema).length === 0) {
        return passed(md02, "content 可解析且符合给定 schema。");
      }
    } catch (error) {
      return failed(md02, error);
    }
    return blocked(
      md02,
      "桩忽略 responseSchema，固定返回 {stub:true, echo}，不符合要求 answer 的 schema。补齐校验前不能记为通过。",
    );
  })();

  const md05Run = await (async (): Promise<CaseRun> => {
    try {
      const stack = createStubStack();
      const result = await stack.model.complete(
        modelRequest({ requestId: "model-fallback", preferredModelId: "missing-model" }),
      );
      if (
        result.ok &&
        (result.value.fallbackFrom ?? []).length > 0 &&
        typeof result.value.usage.cost === "number"
      ) {
        return passed(md05, "首选模型不可用时返回 fallbackFrom，usage 记录成本。");
      }
    } catch (error) {
      return failed(md05, error);
    }
    return blocked(md05, "桩不实现模型回退，响应没有 fallbackFrom。SHOULD，调用方按 describe() 降级。");
  })();

  return [
    await attempt(md01, "complete 返回 content、modelId、modelVersion 与 usage。", async () => {
      const stack = createStubStack();
      const response = unwrap(await stack.model.complete(modelRequest()));
      assert.equal(typeof response.text, "string");
      assert.ok(response.text && response.text.length > 0);
      assert.ok(response.modelId.length > 0);
      assert.ok(response.modelVersion.length > 0);
      assert.equal(typeof response.usage, "object");
    }),
    md02Run,
    await attempt(
      md03,
      "restricted 数据在仅支持 internal 的实现上返回 PERMISSION_DENIED，没有响应可降级到外部模型。",
      async () => {
        const stack = createStubStack({ model: { maxDataClass: "internal" } });
        const denied = await stack.model.complete(modelRequest({ requestId: "model-restricted", dataClass: "restricted" }));
        assert.equal(denied.ok, false);
        if (!denied.ok) {
          assert.equal(denied.error.code, "PERMISSION_DENIED");
          assert.equal(denied.error.retryable, false);
        }
      },
    ),
    await attempt(md04, "无流式能力时首个事件是 NOT_SUPPORTED，没有 done 事件冒充流式结果。", async () => {
      const stack = createStubStack({ model: { supportsStreaming: false } });
      const events = [];
      for await (const event of stack.model.stream(modelRequest({ requestId: "model-stream" }))) {
        events.push(event);
      }
      assert.equal(events.length, 1);
      assert.equal(events[0]?.type, "error");
      if (events[0]?.type === "error") assert.equal(events[0].error.code, "NOT_SUPPORTED");
    }),
    md05Run,
  ];
}

async function computeCases(): Promise<CaseRun[]> {
  const hp01 = meta("HP-01", "hpc");
  const hp02 = meta("HP-02", "hpc");
  const hp03 = meta("HP-03", "hpc");
  const hp04 = meta("HP-04", "hpc");
  const hp05 = meta("HP-05", "hpc");
  const hp06 = meta("HP-06", "hpc");
  const cl01 = meta("CL-01", "cloud");

  return [
    await attempt(
      hp01,
      "契约状态没有 submitted。受理态是 queued，并带 submittedAt。",
      async () => {
        const stack = createStubStack();
        const handle = unwrap(await stack.compute.submit(job({ idempotencyKey: "idem-hp01" })));
        assert.ok(handle.handleId.length > 0);
        assert.equal(handle.state, "queued");
        assert.ok(handle.submittedAt.length > 0);
      },
    ),
    await attempt(hp02, "相同 idempotencyKey 返回同一个 jobId，list 仍只有一条。", async () => {
      const stack = createStubStack();
      const request = job({ idempotencyKey: "idem-hp02" });
      const first = unwrap(await stack.compute.submit(request));
      const second = unwrap(await stack.compute.submit(request));
      assert.equal(first.handleId, second.handleId);
      const listed = unwrap(await stack.compute.list({ tenantId: "tenant-demo" }));
      assert.equal(listed.length, 1);
    }),
    await attempt(hp03, "可行报价含估计成本与排队时间；不支持的 kind 返回 NOT_SUPPORTED 原因。", async () => {
      const stack = createStubStack();
      const quote = unwrap(await stack.compute.quote(job({ idempotencyKey: "idem-hp03" })));
      assert.ok((quote.estimatedCost ?? 0) > 0);
      assert.equal(typeof quote.estimatedQueueSeconds, "number");
      const infeasible = await stack.compute.quote(job({ idempotencyKey: "idem-hp03-qpu", kind: "qpu" }));
      assert.equal(infeasible.ok, false);
      if (!infeasible.ok) assert.ok(infeasible.error.message.length > 0);
    }),
    await attempt(hp04, "running 作业调用 cancel 后状态为 cancelled。", async () => {
      const stack = createStubStack({ compute: { stepsToTerminal: 4 } });
      const handle = unwrap(await stack.compute.submit(job({ idempotencyKey: "idem-hp04" })));
      assert.equal((await stack.compute.status(handle.handleId)).ok, true);
      const running = unwrap(await stack.compute.status(handle.handleId));
      assert.equal(running.state, "running");
      const cancelled = unwrap(await stack.compute.cancel(handle.handleId, "stop"));
      assert.equal(cancelled.state, "cancelled");
    }),
    await attempt(
      hp05,
      "status.state=unknown，reconcile.verdict=unknown。UNKNOWN_EXECUTION 不可重试，策略拒绝自动再提交。",
      async () => {
        const stack = createStubStack({ compute: { scenario: "unknown" } });
        const handle = unwrap(await stack.compute.submit(job({ idempotencyKey: "idem-hp05" })));
        const status = unwrap(await stack.compute.status(handle.handleId));
        assert.equal(status.state, "unknown");
        const evidence = unwrap(await stack.compute.reconcile(handle.handleId));
        assert.equal(evidence.verdict, "unknown");
        assert.equal(
          isRetryable({ ok: false, error: { code: "UNKNOWN_EXECUTION", message: "x", retryable: false } }),
          false,
        );
        const policy = evaluatePolicy(
          { name: "compute.submit", risk: "high", retryAfterUnknown: true },
          { subject: { type: "agent", id: AGENT.id, tenantId: AGENT.tenantId } },
        );
        assert.equal(policy.decision, "DENY");
      },
    ),
    await attempt(hp06, "logs 返回行数组，并带 truncated 标记。", async () => {
      const stack = createStubStack();
      const handle = unwrap(await stack.compute.submit(job({ idempotencyKey: "idem-hp06" })));
      const logs = unwrap(await stack.compute.logs(handle.handleId));
      assert.ok(Array.isArray(logs.lines));
      assert.equal(typeof logs.truncated, "boolean");
    }),
    await attempt(cl01, "云作业对账为 unknown 后，同一幂等键再次 submit 不产生新作业。", async () => {
      const stack = createStubStack({ compute: { scenario: "unknown" } });
      const request = job({ idempotencyKey: "idem-cl01", kind: "cloud" });
      const handle = unwrap(await stack.compute.submit(request));
      const evidence = unwrap(await stack.compute.reconcile(handle.handleId));
      assert.equal(evidence.verdict, "unknown");
      const again = unwrap(await stack.compute.submit(request));
      assert.equal(again.handleId, handle.handleId);
      const listed = unwrap(await stack.compute.list({ tenantId: "tenant-demo" }));
      assert.equal(listed.length, 1);
    }),
  ];
}

async function sessionCases(): Promise<CaseRun[]> {
  const ss01 = meta("SS-01", "session");
  const ss02 = meta("SS-02", "session");
  const ss03 = meta("SS-03", "session");
  const ss04 = meta("SS-04", "session");
  const ss05 = meta("SS-05", "session");

  return [
    await attempt(ss01, "start 返回 sessionId，状态为 started。", async () => {
      const stack = createStubStack();
      const started = unwrap(await stack.session.start(sessionRequest()));
      assert.equal(started.sessionId, "session-conformance");
      assert.equal(started.state, "started");
    }),
    await attempt(ss02, "事件顺序为 turn_started、message、turn_finished，轮次不回退。", async () => {
      const stack = createStubStack({ session: { turns: 2 } });
      const events: Array<{ type: string; turn?: number }> = [];
      unwrap(await stack.session.start(sessionRequest({ sessionId: "session-order" })));
      unwrap(
        await stack.session.subscribe("session-order", (event) => {
          events.push("turn" in event ? { type: event.type, turn: event.turn } : { type: event.type });
        }),
      );
      unwrap(await stack.session.wait("session-order"));
      const types = events.map((event) => event.type);
      const started = types.indexOf("turn_started");
      const message = types.indexOf("message");
      const finished = types.indexOf("turn_finished");
      assert.ok(started >= 0 && started < message && message < finished);
      let lastTurn = 0;
      for (const event of events) {
        if (typeof event.turn === "number") {
          assert.ok(event.turn >= lastTurn);
          lastTurn = event.turn;
        }
      }
    }),
    await attempt(
      ss03,
      "桩用 exceedBudget 注入超限。状态为 budget_exceeded，且停在第 1 轮，不再跑后续轮次。",
      async () => {
        const stack = createStubStack({ session: { turns: 3, exceedBudget: true } });
        unwrap(await stack.session.start(sessionRequest({ sessionId: "session-budget" })));
        const result = unwrap(await stack.session.wait("session-budget"));
        assert.equal(result.state, "budget_exceeded");
        assert.equal(result.turns, 1);
      },
    ),
    await attempt(ss04, "cancel 后 wait 状态为 cancelled，不再产生事件。", async () => {
      const stack = createStubStack();
      const events: string[] = [];
      unwrap(await stack.session.start(sessionRequest({ sessionId: "session-cancel" })));
      unwrap(
        await stack.session.subscribe("session-cancel", (event) => {
          events.push(event.type);
        }),
      );
      unwrap(await stack.session.cancel("session-cancel", "user"));
      const result = unwrap(await stack.session.wait("session-cancel"));
      assert.equal(result.state, "cancelled");
      assert.deepEqual(events, []);
    }),
    await attempt(ss05, "未授权工具被记录为拒绝，toolCalls 仍为 0。", async () => {
      const stack = createStubStack({ session: { unauthorizedTool: "shell" } });
      const events: Array<{ type: string; ok?: boolean }> = [];
      unwrap(await stack.session.start(sessionRequest({ sessionId: "session-tool", allowedTools: ["read"] })));
      unwrap(
        await stack.session.subscribe("session-tool", (event) => {
          events.push(event.type === "tool_result" ? { type: event.type, ok: event.ok } : { type: event.type });
        }),
      );
      const result = unwrap(await stack.session.wait("session-tool"));
      assert.equal(result.state, "failed");
      assert.equal(result.toolCalls, 0);
      assert.ok(events.some((event) => event.type === "tool_result" && event.ok === false));
      assert.equal(events.some((event) => event.type === "tool_result" && event.ok === true), false);
    }),
  ];
}

async function telemetryCases(): Promise<CaseRun[]> {
  const tl01 = meta("TL-01", "telemetry");
  const tl02 = meta("TL-02", "telemetry");
  const base = {
    name: "conformance",
    at: "2026-11-03T00:00:00.000Z",
    traceId: "trace-conformance",
    tenantId: "tenant-demo",
    redactionApplied: true,
  };

  return [
    await attempt(tl01, "redactionApplied=false 时返回 INVALID_ARGUMENT。", async () => {
      const stack = createStubStack();
      const denied = await stack.telemetry.emit({ ...base, redactionApplied: false });
      assert.equal(denied.ok, false);
      if (!denied.ok) assert.equal(denied.error.code, "INVALID_ARGUMENT");
    }),
    await attempt(tl02, "attributes 含 api_key 时拒绝，不写入已采集事件。", async () => {
      const stack = createStubStack();
      const telemetry = stack.telemetry as StubTelemetryPort;
      const denied = await telemetry.emit({ ...base, attributes: { api_key: "secret" } });
      assert.equal(denied.ok, false);
      assert.equal(telemetry.collected().length, 0);
    }),
  ];
}

async function crossCases(): Promise<CaseRun[]> {
  const xp01 = meta("XP-01", "cross");
  const xp02 = meta("XP-02", "cross");
  const xp03 = meta("XP-03", "cross");

  const xp01Run = await (async (): Promise<CaseRun> => {
    try {
      const stack = createStubStack();
      const verified = unwrap(await stack.identity.verify({ token: "stub-token" }));
      const grant = unwrap(
        await stack.identity.authorize({
          subject: AGENT,
          action: "experiment:submit",
          resource: { type: "experiment", tenantId: verified.subject.tenantId },
        }),
      );
      assert.equal(grant.decision, "ALLOW");
      unwrap(
        await stack.secrets.issue({
          subject: AGENT,
          audience: "hpc",
          scope: ["experiment:submit"],
          ttlSeconds: 60,
          idempotencyKey: "idem-xp01-cred",
        }),
      );
      const handle = unwrap(await stack.compute.submit(job({ idempotencyKey: "idem-xp01-job" })));
      unwrap(await stack.compute.status(handle.handleId));
      unwrap(
        await stack.artifacts.put({
          tenantId: "tenant-demo",
          key: "runs/xp01.json",
          contentType: "application/json",
          bytes: new TextEncoder().encode("{}"),
          idempotencyKey: "idem-xp01-put",
        }),
      );
    } catch (error) {
      return failed(xp01, error);
    }
    return blocked(
      xp01,
      "链路能跑通，失败带稳定错误码。成功结果类型没有 traceId；verify、authorize、status 也没有幂等键。要验收这两条须双方改契约，本工程不单改 contracts/。",
    );
  })();

  return [
    xp01Run,
    await attempt(xp02, "unknown 之后 evaluatePolicy(retryAfterUnknown) 返回 DENY，原因要求人工对账。", async () => {
      const stack = createStubStack({ compute: { scenario: "unknown" } });
      const handle = unwrap(await stack.compute.submit(job({ idempotencyKey: "idem-xp02" })));
      const status = unwrap(await stack.compute.status(handle.handleId));
      assert.equal(status.state, "unknown");
      const policy = evaluatePolicy(
        { name: "compute.submit", risk: "high", retryAfterUnknown: true },
        { subject: { type: "agent", id: AGENT.id, tenantId: AGENT.tenantId } },
      );
      assert.equal(policy.decision, "DENY");
      assert.match(policy.reason, /对账/);
    }),
    await attempt(
      xp03,
      "describe() 的 degraded 为 true 且有 degradedReason。集成清单用 notes 写原因，其 schema 没有 degradedReason 字段。",
      async () => {
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
        ];
        for (const port of ports) {
          const described = unwrap(await port.describe());
          assert.equal(described.degraded, true);
          assert.equal(typeof described.degradedReason, "string");
          assert.ok((described.degradedReason ?? "").length > 0);
        }
        const manifest = JSON.parse(
          await readFile(new URL("../contracts/fixtures/integration-manifest.stub.json", import.meta.url), "utf8"),
        ) as { ports: Array<{ degraded?: boolean; notes?: string | null }> };
        assert.ok(manifest.ports.every((port) => port.degraded === true && (port.notes ?? "").length > 0));
      },
    ),
  ];
}

export async function runStubConformance(): Promise<CaseRun[]> {
  return [
    ...(await identityCases()),
    ...(await objectCases()),
    ...(await credentialCases()),
    ...(await modelCases()),
    ...(await computeCases()),
    ...(await sessionCases()),
    ...(await telemetryCases()),
    ...(await crossCases()),
  ];
}

import { test } from "node:test";
import assert from "node:assert/strict";

import { StubSessionPort } from "../adapters/stub/src/session.ts";
import {
  buildPlatformSignal,
  evaluateSoftwareMerge,
} from "../packages/domain/src/index.ts";
import type { SoftwareMergeInput, SoftwareSpec } from "../packages/domain/src/index.ts";
import {
  startDegradedSoftwareSession,
  validateSoftwareMergeInput,
} from "../packages/pipeline/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const AT = "2026-11-02T02:00:00.000Z";

function spec(): SoftwareSpec {
  return {
    spec_id: "SPEC-1",
    goal: "给合并候选补上可执行验收",
    non_goals: ["不自研编码路由器"],
    acceptance: [{ id: "unit", command: "node --test tests/software-gate.test.ts" }],
    rollback: "删除本次提交并恢复上一版门禁记录",
  };
}

function gates() {
  return (["unit", "integration", "e2e", "security"] as const).map((name) => ({
    name,
    passed: true,
    evidence_uri: `artifact://${name}`,
  }));
}

function input(overrides: Partial<SoftwareMergeInput> = {}): SoftwareMergeInput {
  return {
    work_id: "WORK-1",
    author_id: "author-1",
    workspace_id: "wt-work-1",
    runtime: "degraded",
    spec: spec(),
    gates: gates(),
    review: { reviewer_id: "reviewer-1", blockers: 0 },
    approval_id: "APR-1",
    delivery: "requested",
    session_id: "sw-WORK-1",
    evaluated_at: AT,
    ...overrides,
  };
}

test("合并门禁：证据齐全时允许合并，并符合 schema", async () => {
  const result = evaluateSoftwareMerge(input());
  assert.equal(result.ok, true);
  assert.equal(result.record?.decision, "allow_merge");
  assert.equal(result.record?.degraded, true);
  assert.equal(result.record?.upstream_version, null);

  const schema = await loadSchema("software-merge-record.schema.json");
  assert.deepEqual(validateJsonSchema(result.record, schema), []);
});

test("合并门禁：作者不能评审自己，跳过门禁一律拒绝", () => {
  const selfReview = evaluateSoftwareMerge(input({
    review: { reviewer_id: "Author-1", blockers: 0 },
  }));
  assert.equal(selfReview.record?.decision, "deny");
  assert.match(selfReview.record?.reason ?? "", /作者不能审查/);

  const bypass = evaluateSoftwareMerge(input({ bypass_requested: true }));
  assert.equal(bypass.record?.decision, "deny");
  assert.match(bypass.record?.reason ?? "", /不能跳过/);
});

test("合并门禁：没有书面规则的主动行为只记录", () => {
  const recorded = evaluateSoftwareMerge(input({ delivery: "proactive" }));
  assert.equal(recorded.record?.decision, "record_only");
});

test("合并门禁：未锁定版本不能声称使用上游，已有会话不是合并条件", () => {
  const claimed = evaluateSoftwareMerge(input({ runtime: "upstream", upstream_version: "  " }));
  assert.equal(claimed.record?.decision, "deny");
  assert.match(claimed.record?.reason ?? "", /未锁定上游版本/);

  const resumed = evaluateSoftwareMerge({ ...input(), gates: gates() });
  assert.equal(resumed.record?.decision, "allow_merge");
});

test("合并门禁：缺少审批时停在人工审批，缺证据或规格时拒绝", () => {
  const waiting = evaluateSoftwareMerge(input({ approval_id: null }));
  assert.equal(waiting.record?.decision, "needs_approval");

  const missingGate = evaluateSoftwareMerge(input({
    gates: gates().filter((gate) => gate.name !== "e2e"),
  }));
  assert.equal(missingGate.record?.decision, "deny");

  const badSpec = evaluateSoftwareMerge(input({
    spec: { ...spec(), rollback: " " },
  }));
  assert.equal(badSpec.ok, false);
  assert.equal(badSpec.record, undefined);
});

test("平台事件：实验完成、租约和预算可重复生成同一标识", async () => {
  const completed = buildPlatformSignal({
    type: "experiment.completed.v1",
    tenant_id: "tenant-1",
    project_id: "project-1",
    resource_id: "RUN-1",
    resource_version: 2,
    time: AT,
    data: { experiment_id: "EXP-1", decision: "keep" },
  });
  assert.equal(completed.ok, true);
  assert.equal(completed.signal?.id, "experiment.completed.v1:RUN-1:2");

  const again = buildPlatformSignal({
    type: "experiment.completed.v1",
    tenant_id: "tenant-1",
    resource_id: "RUN-1",
    resource_version: 2,
    time: AT,
    data: { experiment_id: "EXP-1", decision: "keep" },
  });
  assert.equal(again.signal?.id, completed.signal?.id);

  const schema = await loadSchema("platform-signal.schema.json");
  assert.deepEqual(validateJsonSchema(completed.signal, schema), []);

  const secret = buildPlatformSignal({
    type: "budget.exhausted.v1",
    tenant_id: "tenant-1",
    resource_id: "project-1",
    resource_version: 1,
    time: AT,
    data: { api_key: "nope" },
  });
  assert.equal(secret.ok, false);
});

test("降级执行：先会话后评估，证据不再是开会话的前提", async () => {
  const session = new StubSessionPort();
  const common = {
    workId: "WORK-1",
    authorId: "author-1",
    tenantId: "tenant-1",
    workspaceId: "wt-work-1",
    agentId: "agent-1",
    spec: spec(),
    budget: { maxTurns: 2, maxToolCalls: 4, maxWallClockSeconds: 60 },
  };

  const first = await startDegradedSoftwareSession({ session }, common);
  assert.equal(first.sessionStarted, true);
  assert.equal(first.ok, true);
  assert.equal(first.sessionId, "sw-WORK-1");
  assert.equal(first.state, "completed");
  assert.equal(JSON.stringify(session).includes("正在评审"), false);

  const afterSession = evaluateSoftwareMerge(input({ session_id: "sw-WORK-1" }));
  assert.equal(afterSession.record?.decision, "allow_merge");

  const second = await startDegradedSoftwareSession({ session }, {
    ...common,
    priorSessionIds: ["sw-WORK-1"],
  });
  assert.equal(second.sessionStarted, false);
  assert.match(second.findings[0]?.message ?? "", /只允许一次会话/);
  assert.equal(second.sessionId, undefined);
});

test("降级执行：结构非法不开会话，失败会话不产出伪造记录", async () => {
  const session = new StubSessionPort();

  const invalid = await startDegradedSoftwareSession({ session }, {
    workId: "WORK-2",
    authorId: "author-1",
    tenantId: "tenant-1",
    workspaceId: "wt-work-2",
    agentId: "agent-1",
    spec: { ...spec(), rollback: " " },
    budget: { maxTurns: 1, maxToolCalls: 1, maxWallClockSeconds: 30 },
  });
  assert.equal(invalid.sessionStarted, false);
  assert.match(invalid.findings[0]?.code ?? "", /E_SPEC_ROLLBACK/);
  assert.deepEqual(validateSoftwareMergeInput({
    work_id: "WORK-2",
    author_id: "author-1",
    workspace_id: "wt-work-2",
    runtime: "degraded",
    spec: { ...spec(), rollback: " " },
    gates: [],
    delivery: "requested",
  }), invalidateRollbackFindings());

  const failing = new StubSessionPort({ fail: true });
  const failedSession = await startDegradedSoftwareSession({ session: failing }, {
    workId: "WORK-3",
    authorId: "author-1",
    tenantId: "tenant-1",
    workspaceId: "wt-work-3",
    agentId: "agent-1",
    spec: spec(),
    budget: { maxTurns: 1, maxToolCalls: 1, maxWallClockSeconds: 30 },
  });
  assert.equal(failedSession.sessionStarted, true);
  assert.equal(failedSession.ok, false);
  assert.equal(failedSession.findings[0]?.code, "SESSION_NOT_COMPLETED");
  assert.match(failedSession.findings[0]?.message ?? "", /会话输出不能作为门禁证据/);
  assert.equal(session.stateOf("sw-WORK-2"), undefined);
});

function invalidateRollbackFindings() {
  const direct = evaluateSoftwareMerge({
    work_id: "WORK-2",
    author_id: "author-1",
    workspace_id: "wt-work-2",
    runtime: "degraded",
    spec: { ...spec(), rollback: " " },
    gates: [],
    delivery: "requested",
  });
  return direct.findings;
}

import { test } from "node:test";
import assert from "node:assert/strict";

import type { Subject } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";
import type { ExperimentSpec } from "../packages/domain/src/index.ts";
import { mergeFailureEntries, queryFailureLibrary } from "../packages/domain/src/index.ts";
import {
  loadFailureLibrary,
  runExperimentLoop,
} from "../packages/pipeline/src/index.ts";
import type { LoopInput } from "../packages/pipeline/src/index.ts";

const agent: Subject = {
  type: "agent",
  id: "agent-recall",
  tenantId: "tenant-recall",
  projectId: "project-recall",
  scopes: ["experiment:submit"],
};

const code = { repo: "github.com/company/example", commit: "c0ffee" };
const environment = {
  containerDigest: `sha256:${"a".repeat(64)}`,
  lockfileHash: "b".repeat(64),
};

function makeSpec(): ExperimentSpec {
  return {
    experiment_id: "EXP-RECALL-1",
    task_id: "TASK-RECALL-1",
    hypothesis: {
      statement: "加入预热可以降低验证损失",
      falsifiable_by: "若验证损失未下降，则假设不成立",
    },
    baseline: { name: "无预热基线", source: "内部复现", reproduced: true, metric_value: 1.0 },
    variables: {
      changed: ["src/train/scheduler.py"],
      controlled: ["dataset", "split"],
      allowed_paths: ["src/train/**"],
    },
    metrics: {
      primary: "val_loss",
      direction: "minimize",
      minimum_observable_effect: 0.02,
      guardrails: [{ name: "train_time_seconds", max_degradation: 0.1 }],
      repeats: 1,
      seeds: [13],
    },
    resources: {
      type: "gpu",
      count: 1,
      max_wall_clock_seconds: 600,
      max_cost: 5,
      currency: "CNY",
      checkpoint_required: true,
    },
    stopping: { max_attempts: 1, max_consecutive_failures: 1 },
    decision: { keep_if: "val_loss 下降 >= 0.02", discard_if: "护栏退化超过阈值" },
    artifacts: { required: ["code_hash", "env_lock", "raw_metrics", "manifest"] },
  };
}

test("失败库：跨循环 URI 读回并按条件召回", async () => {
  const stackA = createStubStack({ compute: { scenario: "fail", baseCostPerHour: 24 } });
  const loopA = await runExperimentLoop(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-recall-a",
      idempotencyKey: "idem-recall-a",
      code,
      environment,
      budget: { total: 100, currency: "CNY" },
      baselineGuardrails: { train_time_seconds: 200 },
    },
    { compute: stackA.compute, artifacts: stackA.artifacts },
  );
  assert.ok(loopA.failureRef, "失败循环应写 failures.json");

  const loaded = await loadFailureLibrary(
    { artifacts: stackA.artifacts },
    { tenantId: agent.tenantId, uris: [loopA.failureRef!.uri] },
  );
  assert.deepEqual(loaded.findings.filter((item) => item.severity === "error"), []);
  assert.equal(loaded.entries.length, 1);
  assert.equal(loaded.sources[0].count, 1);

  const recalled = queryFailureLibrary(loaded.entries, { category: "unknown", stage: "decision" });
  assert.equal(recalled.length, 1);
  assert.equal(recalled[0].code, "E_DECISION");
});

test("失败库：重复 entry_id 保留最新版本且查询不受影响", () => {
  const older = {
    entry_id: "run-1:submit:TIMEOUT",
    task_id: "TASK-1",
    experiment_id: "EXP-1",
    run_id: "run-1",
    category: "environment" as const,
    code: "TIMEOUT",
    message: "旧消息",
    retryable: true,
    stage: "submit" as const,
    decision: null,
    occurred_at: "2026-11-01T00:00:00.000Z",
  };
  const newer = { ...older, message: "新消息", occurred_at: "2026-11-02T00:00:00.000Z" };
  const otherRun = { ...older, entry_id: "run-2:submit:TIMEOUT", run_id: "run-2" };
  const merged = mergeFailureEntries([older, newer, otherRun]);
  assert.equal(merged.length, 2, "重放更新同一 ID 只保留最新，不同 ID 合并共存");
  const deduped = merged.find((entry) => entry.run_id === "run-1");
  assert.ok(deduped);
  assert.equal(deduped.message, "新消息");
  assert.ok(merged[0].occurred_at >= merged[1].occurred_at);

  const recalled = queryFailureLibrary(merged, { retryable: true, limit: 1 });
  assert.equal(recalled.length, 1);
});

test("失败库：新循环在同一存储读回历史 URI 并挂到结果上", async () => {
  const stack = createStubStack({ compute: { scenario: "fail", baseCostPerHour: 24 } });
  const loopA = await runExperimentLoop(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-recall-seed",
      idempotencyKey: "idem-recall-seed",
      code,
      environment,
      budget: { total: 100, currency: "CNY" },
      baselineGuardrails: { train_time_seconds: 200 },
    },
    { compute: stack.compute, artifacts: stack.artifacts },
  );
  assert.ok(loopA.failureRef);

  const loopB = await runExperimentLoop(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-recall-b",
      idempotencyKey: "idem-recall-b",
      code,
      environment,
      budget: { total: 100, currency: "CNY" },
      baselineGuardrails: { train_time_seconds: 200 },
      recallFailureUris: [loopA.failureRef!.uri],
    },
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(loopB.state, "consecutive_failures");
  assert.ok(loopB.recalledFailures, "循环应读回历史失败条目");
  assert.equal(loopB.recalledFailures!.length, 1);
  assert.ok(loopB.recalledFailures![0].entry_id.includes(":decision:E_DECISION"));
  assert.deepEqual(
    loopB.findings.filter((finding) => finding.code === "W_FAILURE_RECALL_READ"),
    [],
    "同存储读回不应有告警",
  );
});

test("失败库：跨存储读不到产物时告警且不阻断", async () => {
  const stackA = createStubStack({ compute: { scenario: "fail", baseCostPerHour: 24 } });
  const loopA = await runExperimentLoop(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-recall-cross",
      idempotencyKey: "idem-recall-cross",
      code,
      environment,
      budget: { total: 100, currency: "CNY" },
      baselineGuardrails: { train_time_seconds: 200 },
    },
    { compute: stackA.compute, artifacts: stackA.artifacts },
  );
  assert.ok(loopA.failureRef);

  const stackB = createStubStack();
  const crossStackRead = await loadFailureLibrary(
    { artifacts: stackB.artifacts },
    { tenantId: agent.tenantId, uris: [loopA.failureRef!.uri] },
  );
  assert.ok(crossStackRead.findings.some((item) => item.code === "W_FAILURE_RECALL_READ"));
  assert.equal(crossStackRead.entries.length, 0, "跨存储隔离：外部产物读不到");
  assert.equal(crossStackRead.sources[0].error_code, "NOT_FOUND");
});

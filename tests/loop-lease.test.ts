import { test } from "node:test";
import assert from "node:assert/strict";

import type { Subject } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";
import type { CheckpointRecord, CostLedger, ExperimentSpec } from "../packages/domain/src/index.ts";
import { summarizeCost } from "../packages/domain/src/index.ts";
import { runExperimentLoop } from "../packages/pipeline/src/index.ts";
import type { LoopInput } from "../packages/pipeline/src/index.ts";

const agent: Subject = {
  type: "agent",
  id: "agent-loop-lease",
  tenantId: "tenant-demo",
  projectId: "project-demo",
  scopes: ["experiment:submit"],
};

const code = { repo: "github.com/company/example", commit: "c0ffee" };
const environment = {
  containerDigest: `sha256:${"a".repeat(64)}`,
  lockfileHash: "b".repeat(64),
};

function makeSpec(overrides: Partial<ExperimentSpec> = {}): ExperimentSpec {
  return {
    experiment_id: "EXP-LOOPLEASE-1",
    task_id: "TASK-LOOPLEASE-1",
    hypothesis: {
      statement: "加入预热可以降低验证损失",
      falsifiable_by: "若验证损失未下降，则假设不成立",
    },
    baseline: {
      name: "无预热基线",
      source: "内部复现",
      reproduced: true,
      metric_value: 1.0,
    },
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
    stopping: { max_attempts: 5, max_consecutive_failures: 5 },
    decision: {
      keep_if: "val_loss 下降 >= 0.02",
      discard_if: "护栏退化超过阈值",
    },
    artifacts: { required: ["code_hash", "env_lock", "raw_metrics", "manifest"] },
    ...overrides,
  };
}

function discardSpec(): ExperimentSpec {
  return makeSpec({ baseline: { ...makeSpec().baseline, metric_value: 0.94 } });
}

function makeInput(overrides: Partial<LoopInput> = {}): LoopInput {
  return {
    spec: makeSpec(),
    subject: agent,
    traceId: "trace-loop-lease",
    idempotencyKey: "idem-loop-lease",
    code,
    environment,
    budget: { total: 100, currency: "CNY" },
    baselineGuardrails: { train_time_seconds: 200 },
    ...overrides,
  };
}

function makeStack(scenario: "success" | "fail" | "unknown" = "success") {
  return createStubStack({ compute: { scenario, baseCostPerHour: 24 } });
}

test("循环租约：保留轮释放资源并把账本串给调用方", async () => {
  const stack = makeStack();
  const outcome = await runExperimentLoop(
    makeInput({ lease: {} }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "kept");
  assert.ok(outcome.ledger, "循环应返回共享账本");
  assert.equal(outcome.ledger!.entries.length, 3, "预留 + 实际 + 释放");
  const totals = summarizeCost(outcome.ledger!)[0];
  assert.equal(totals.committed, 0.8);
  assert.ok(Math.abs(outcome.remainingBudget - (100 - 0.8)) < 1e-9);
  assert.ok(Math.abs(outcome.totalCost - 0.8) < 1e-9);
});

test("循环租约：跨轮共享同一账本，剩余预算按已承诺成本扣减", async () => {
  const stack = makeStack();
  const outcome = await runExperimentLoop(
    makeInput({
      spec: discardSpec(),
      earlyStopAfterDiscards: 2,
      lease: {},
      propose: () => discardSpec(),
    }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "stopped");
  assert.equal(outcome.attempts.length, 2);
  assert.ok(outcome.ledger);

  const totals = summarizeCost(outcome.ledger!)[0];
  assert.equal(totals.reserved, 10, "两轮各预留 5");
  assert.equal(totals.actual, 1.6);
  assert.equal(totals.released, 8.4);
  assert.equal(totals.committed, 1.6);

  assert.ok(Math.abs(outcome.remainingBudget - (100 - 1.6)) < 1e-9);
  assert.ok(Math.abs(outcome.totalCost - 1.6) < 1e-9);
});

test("循环租约：总预算低于单轮上限时不提交作业", async () => {
  const stack = makeStack();
  const outcome = await runExperimentLoop(
    makeInput({
      budget: { total: 1, currency: "CNY" },
      lease: {},
    }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "budget_exhausted");
  assert.equal(outcome.attempts.length, 0);
  assert.ok(outcome.ledger);
  assert.equal(outcome.ledger!.entries.length, 0);

  const jobs = await stack.compute.list({ tenantId: agent.tenantId });
  assert.ok(jobs.ok);
  if (jobs.ok) assert.equal(jobs.value.length, 0, "不得提交任何作业");
});

test("循环租约：预算随实际成本递减，不足以开新一轮时停止", async () => {
  const stack = makeStack();
  const outcome = await runExperimentLoop(
    makeInput({
      spec: discardSpec(),
      budget: { total: 5, currency: "CNY" },
      lease: {},
      propose: () => discardSpec(),
    }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "budget_exhausted");
  assert.equal(outcome.attempts.length, 1, "第一轮后剩余 4.2 < 上限 5，不再开新一轮");
  assert.ok(Math.abs(outcome.remainingBudget - 4.2) < 1e-9);
});

function checkpoint(attempt: number): CheckpointRecord {
  return {
    checkpoint_id: `CKPT-LOOPLEASE-${attempt}`,
    experiment_id: "EXP-LOOPLEASE-1",
    attempt,
    uri: `stub://checkpoints/attempt-${attempt}`,
    sha256: "c".repeat(64),
    step: attempt * 10,
    created_at: "2026-11-02T00:00:00.000Z",
    code_commit: "c0ffee",
    environment_hash: "b".repeat(64),
    valid: true,
  };
}

test("循环恢复决策：先恢复再因达到上限转人工", async () => {
  const stack = makeStack("fail");
  const checkpoints: CheckpointRecord[] = [checkpoint(1), checkpoint(2)];
  const outcome = await runExperimentLoop(
    makeInput({
      maxAttempts: 3,
      maxConsecutiveFailures: 5,
      checkpoints,
      resume: { max_resumes: 1, max_age_seconds: null },
      propose: () => makeSpec(),
    }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "escalated");
  assert.equal(outcome.attempts.length, 2);
  assert.ok(outcome.attempts[0].resume_plan?.startsWith("resume"));
  assert.equal(outcome.attempts[0].resume_from, "CKPT-LOOPLEASE-1");
  assert.ok(outcome.attempts[1].resume_plan?.startsWith("escalate"));
  assert.ok(outcome.summaryRef);

  const read = await stack.artifacts.get({
    tenantId: agent.tenantId,
    uri: outcome.summaryRef!.uri,
  });
  assert.equal(read.ok, true);
  if (read.ok) {
    const summary = JSON.parse(new TextDecoder().decode(read.value.bytes)) as {
      stop_reason: string;
      attempts: Array<{ resume_plan: string | null }>;
    };
    assert.equal(summary.stop_reason, "escalated");
    assert.equal(summary.attempts[0].resume_plan?.startsWith("resume"), true);
  }
});

test("循环恢复决策：检查点代码版本不一致时重启并记录", async () => {
  const stack = makeStack("fail");
  const stale = checkpoint(1);
  stale.code_commit = "deadbeef";
  const outcome = await runExperimentLoop(
    makeInput({
      maxAttempts: 2,
      maxConsecutiveFailures: 5,
      checkpoints: [stale],
      resume: { max_resumes: 3, max_age_seconds: null },
      propose: () => makeSpec(),
    }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "exhausted", "maxAttempts=2 用尽后停止");
  assert.equal(outcome.attempts.length, 2);
  assert.ok(outcome.attempts[0].resume_plan?.startsWith("restart"));
  assert.ok(outcome.attempts[1].resume_plan?.startsWith("restart"));
  assert.equal(outcome.attempts[0].resume_from, null, "重启不应绑定检查点");
});

import { test } from "node:test";
import assert from "node:assert/strict";

import type { Subject } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";
import { compileExperiment, decide, evaluatePolicy, transition } from "../packages/domain/src/index.ts";
import type { ExperimentSpec } from "../packages/domain/src/index.ts";
import { runExperiment } from "../packages/pipeline/src/index.ts";

const agent: Subject = {
  type: "agent",
  id: "agent-1",
  tenantId: "tenant-demo",
  projectId: "project-demo",
  scopes: ["experiment:submit"],
};

const code = { repo: "github.com/company/example", commit: "c0ffee", branch: "exp/test" };
const environment = {
  containerDigest: `sha256:${"a".repeat(64)}`,
  lockfileHash: "b".repeat(64),
};

function makeSpec(overrides: Partial<ExperimentSpec> = {}): ExperimentSpec {
  const spec: ExperimentSpec = {
    experiment_id: "EXP-TEST-1",
    task_id: "TASK-TEST-1",
    hypothesis: {
      statement: "加入预热可以降低验证损失",
      origin: "literature_gap",
      evidence_refs: ["paper:example"],
      falsifiable_by: "若验证损失未下降，则假设不成立",
      expected_effect: "验证损失下降 2%",
    },
    baseline: {
      name: "无预热基线",
      source: "内部复现",
      run_id: "RUN-BASE",
      reproduced: true,
      metric_value: 1.0,
      uncertainty: 0.01,
    },
    variables: {
      changed: ["src/train/scheduler.py"],
      controlled: ["dataset", "split", "model"],
      allowed_paths: ["src/train/**"],
      forbidden_paths: ["src/eval/**"],
    },
    metrics: {
      primary: "val_loss",
      direction: "minimize",
      minimum_observable_effect: 0.02,
      guardrails: [{ name: "train_time_seconds", max_degradation: 0.1 }],
      statistic: "mean",
      repeats: 1,
      seeds: [13],
    },
    resources: {
      type: "gpu",
      count: 1,
      accelerator: "A100-40GB",
      max_wall_clock_seconds: 600,
      max_cost: 20,
      currency: "CNY",
      checkpoint_required: true,
      checkpoint_interval_seconds: 60,
    },
    stopping: {
      max_attempts: 3,
      max_consecutive_failures: 1,
      deadline_at: null,
      early_stop: null,
    },
    decision: {
      keep_if: "val_loss 下降 >= 0.02 且护栏不退化",
      discard_if: "护栏退化超过阈值",
      on_unknown: "escalate",
    },
    artifacts: {
      required: ["code_hash", "env_lock", "raw_metrics", "manifest"],
      optional: ["report"],
    },
  };
  return { ...spec, ...overrides };
}

function makeInput(overrides: Partial<Parameters<typeof runExperiment>[0]> = {}) {
  return {
    spec: makeSpec(),
    subject: agent,
    traceId: "trace-pipeline-1",
    idempotencyKey: "idem-pipeline-1",
    code,
    environment,
    budget: { remaining: 100, currency: "CNY" },
    baselineGuardrails: { train_time_seconds: 200 },
    ...overrides,
  };
}

test("合法规格通过编译", () => {
  const result = compileExperiment(makeSpec());
  assert.equal(result.ok, true, JSON.stringify(result.errors));
});

test("未复现基线被拒绝", () => {
  const spec = makeSpec({ baseline: { ...makeSpec().baseline, reproduced: false } });
  const result = compileExperiment(spec);
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "E_BASELINE_NOT_REPRODUCED"));
});

test("变更越界被拒绝", () => {
  const spec = makeSpec({
    variables: {
      changed: ["src/eval/metrics.py"],
      controlled: ["dataset"],
      allowed_paths: ["src/train/**"],
      forbidden_paths: [],
    },
  });
  const result = compileExperiment(spec);
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "E_OUT_OF_SCOPE"));
});

test("长任务无检查点被拒绝", () => {
  const spec = makeSpec({
    resources: { ...makeSpec().resources, max_wall_clock_seconds: 7200, checkpoint_required: false },
  });
  const result = compileExperiment(spec);
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "E_CHECKPOINT_REQUIRED"));
});

test("执行状态未知时禁止 retry_once", () => {
  const spec = makeSpec();
  const legacy = {
    ...spec,
    decision: { ...spec.decision, on_unknown: "retry_once" },
  } as unknown as ExperimentSpec;
  const result = compileExperiment(legacy);
  assert.equal(result.ok, false);
  assert.ok(result.errors.some((error) => error.code === "E_UNKNOWN_RETRY_FORBIDDEN"));
});

test("决策：达标保留，未达标撤销，护栏退化撤销", () => {
  const spec = makeSpec();
  const base = {
    guardrailDegradations: { train_time_seconds: 0 },
    cost: 10,
    currency: "CNY",
    artifactsPresent: ["code_hash", "env_lock", "raw_metrics", "manifest"],
    executionState: "succeeded" as const,
  };

  assert.equal(decide(spec, { ...base, primaryDelta: 0.06, seedValues: [0.94] }).action, "keep");
  assert.equal(decide(spec, { ...base, primaryDelta: 0.001 }).action, "discard");
  assert.equal(
    decide(spec, { ...base, primaryDelta: 0.06, guardrailDegradations: { train_time_seconds: 0.5 } })
      .action,
    "discard",
  );
});

test("决策：未知执行必须升级", () => {
  const result = decide(makeSpec(), {
    primaryDelta: null,
    guardrailDegradations: {},
    cost: 0,
    currency: "CNY",
    artifactsPresent: [],
    executionState: "unknown_execution",
  });
  assert.equal(result.action, "escalate");
});

test("策略：未知执行后的重试、QPU 与生产写入", () => {
  const ctx = { subject: { type: "agent" as const, id: "a1", tenantId: "t1" } };

  assert.equal(
    evaluatePolicy(
      { name: "experiment.submit", risk: "medium", retryAfterUnknown: true },
      ctx,
    ).decision,
    "DENY",
  );

  assert.equal(
    evaluatePolicy({ name: "experiment.submit", risk: "critical", targetType: "qpu" }, ctx).decision,
    "REQUIRE_APPROVAL",
  );

  assert.equal(
    evaluatePolicy({ name: "git.merge", risk: "high", writesProduction: true }, ctx).decision,
    "REQUIRE_APPROVAL",
  );

  assert.equal(
    evaluatePolicy(
      { name: "git.merge", risk: "high", writesProduction: true },
      { ...ctx, approvedActions: ["git.merge"] },
    ).decision,
    "ALLOW_WITH_LIMIT",
  );
});

test("状态机拒绝非法迁移", () => {
  assert.equal(transition("draft", "start").ok, false);
  assert.equal(transition("draft", "submit").state, "queued");
  assert.equal(transition("running", "complete").state, "succeeded");
  assert.equal(transition("succeeded", "cancel").ok, false);
});

test("端到端：成功实验保留并写出清单", async () => {
  const stack = createStubStack({ compute: { scenario: "success" } });
  const outcome = await runExperiment(
    makeInput(),
    { compute: stack.compute, artifacts: stack.artifacts, telemetry: stack.telemetry, events: stack.events },
  );

  assert.equal(outcome.state, "succeeded", JSON.stringify(outcome.findings));
  assert.equal(outcome.decision?.action, "keep");
  assert.ok(outcome.manifest);
  assert.ok(outcome.manifestRef);

  const read = await stack.artifacts.get({
    tenantId: agent.tenantId,
    uri: outcome.manifestRef!.uri,
  });
  assert.equal(read.ok, true);
  if (read.ok) {
    const parsed = JSON.parse(new TextDecoder().decode(read.value.bytes));
    assert.equal(parsed.decision.action, "keep");
    assert.equal(parsed.experiment_id, "EXP-TEST-1");
    assert.equal(parsed.attempt, 1);
    assert.equal(parsed.resources.handle_id, "stub-job-1");
    assert.ok(parsed.artifacts.length >= 3);
    for (const artifact of parsed.artifacts) {
      assert.ok(artifact.type);
      assert.match(artifact.sha256, /^[a-f0-9]{64}$/);
    }
  }

  assert.equal(stack.telemetry.countByName("experiment.decided"), 1);
  const published = (
    stack.events as unknown as { publishedEvents(): Array<unknown> }
  ).publishedEvents();
  assert.equal(published.length, 1);
});

test("端到端：未知执行升级并保存不可重试的清单", async () => {
  const stack = createStubStack({ compute: { scenario: "unknown" } });
  const outcome = await runExperiment(
    makeInput(),
    { compute: stack.compute, artifacts: stack.artifacts, telemetry: stack.telemetry },
  );

  assert.equal(outcome.state, "unknown_execution");
  assert.equal(outcome.error?.retryable, false);
  assert.equal(outcome.manifest?.state, "unknown");
  assert.equal(outcome.manifest?.failure?.category, "unknown");
  assert.equal(outcome.manifest?.failure?.retryable, false);
  assert.ok(outcome.manifestRef, "未知执行也必须留下清单");

  const read = await stack.artifacts.get({
    tenantId: agent.tenantId,
    uri: outcome.manifestRef!.uri,
  });
  assert.equal(read.ok, true);
});

test("端到端：HPC 需要审批时不提交作业", async () => {
  const stack = createStubStack({ compute: { scenario: "success" } });
  const spec = makeSpec({ resources: { ...makeSpec().resources, type: "hpc" } });

  const outcome = await runExperiment(
    makeInput({ spec }),
    { compute: stack.compute, artifacts: stack.artifacts, telemetry: stack.telemetry },
  );

  assert.equal(outcome.state, "needs_approval");
  assert.equal(stack.artifacts.size(), 0, "审批前不应写入任何产物");
});

test("端到端：预算不足直接拒绝", async () => {
  const stack = createStubStack();
  const outcome = await runExperiment(
    makeInput({ budget: { remaining: 1, currency: "CNY" } }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );
  assert.equal(outcome.state, "denied");
});

test("端到端：失败实验进入 failed 并记录原因", async () => {
  const stack = createStubStack({ compute: { scenario: "fail" } });
  const outcome = await runExperiment(
    makeInput(),
    { compute: stack.compute, artifacts: stack.artifacts, telemetry: stack.telemetry },
  );

  assert.equal(outcome.decision?.action, "stop");
  assert.equal(outcome.manifest?.state, "failed");
});

test("端到端：产物缺失时升级而不是误判成功", async () => {
  const stack = createStubStack();
  const spec = makeSpec({
    artifacts: {
      required: ["code_hash", "env_lock", "raw_metrics", "manifest", "report"],
    },
  });
  const outcome = await runExperiment(
    makeInput({ spec }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.decision?.action, "escalate");
  assert.equal(outcome.state, "escalated");
  assert.ok(outcome.findings.some((finding) => finding.code === "E_ARTIFACT") === false);
  assert.ok(outcome.decision?.reasons.some((reason) => reason.includes("report")));
});

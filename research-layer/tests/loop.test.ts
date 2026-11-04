import { test } from "node:test";
import assert from "node:assert/strict";

import type { Subject } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";
import type { ExperimentSpec } from "../packages/domain/src/index.ts";
import { runExperimentLoop } from "../packages/pipeline/src/index.ts";
import type { LoopInput } from "../packages/pipeline/src/index.ts";

const agent: Subject = {
  type: "agent",
  id: "agent-loop",
  tenantId: "tenant-demo",
  projectId: "project-demo",
  scopes: ["experiment:submit"],
};

const code = { repo: "github.com/company/example", commit: "c0ffee", branch: "exp/loop" };
const environment = {
  containerDigest: `sha256:${"a".repeat(64)}`,
  lockfileHash: "b".repeat(64),
};

function makeSpec(overrides: Partial<ExperimentSpec> = {}): ExperimentSpec {
  const spec: ExperimentSpec = {
    experiment_id: "EXP-LOOP-1",
    task_id: "TASK-LOOP-1",
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
      max_cost: 5,
      currency: "CNY",
      checkpoint_required: true,
      checkpoint_interval_seconds: 60,
    },
    stopping: {
      max_attempts: 5,
      max_consecutive_failures: 2,
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

function discardSpec(): ExperimentSpec {
  return makeSpec({ baseline: { ...makeSpec().baseline, metric_value: 0.94 } });
}

function makeLoopInput(overrides: Partial<LoopInput> = {}): LoopInput {
  return {
    spec: makeSpec(),
    subject: agent,
    traceId: "trace-loop-1",
    idempotencyKey: "idem-loop-1",
    code,
    environment,
    budget: { total: 100, currency: "CNY" },
    baselineGuardrails: { train_time_seconds: 200 },
    ...overrides,
  };
}

function depsOf(stack: ReturnType<typeof createStubStack>) {
  return { compute: stack.compute, artifacts: stack.artifacts, telemetry: stack.telemetry };
}

async function readJson(
  stack: ReturnType<typeof createStubStack>,
  uri: string,
): Promise<Record<string, unknown>> {
  const read = await stack.artifacts.get({ tenantId: agent.tenantId, uri });
  assert.equal(read.ok, true);
  if (!read.ok) throw new Error("产物读取失败");
  return JSON.parse(new TextDecoder().decode(read.value.bytes)) as Record<string, unknown>;
}

test("循环：首轮保留后立即停止", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  let proposeCalls = 0;
  const outcome = await runExperimentLoop(
    makeLoopInput({
      propose: () => {
        proposeCalls += 1;
        return makeSpec();
      },
    }),
    depsOf(stack),
  );

  assert.equal(outcome.state, "kept");
  assert.equal(outcome.attempts.length, 1);
  assert.equal(proposeCalls, 0);
  assert.ok(Math.abs(outcome.totalCost - 0.8) < 1e-9);
  assert.ok(outcome.summaryRef);

  const summary = await readJson(stack, outcome.summaryRef!.uri);
  assert.equal(summary.stop_reason, "kept");
  assert.equal((summary.attempts as unknown[]).length, 1);
});

test("循环：负结果进入摘要并触发早停", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const outcome = await runExperimentLoop(
    makeLoopInput({
      spec: discardSpec(),
      earlyStopAfterDiscards: 2,
      propose: () => discardSpec(),
    }),
    depsOf(stack),
  );

  assert.equal(outcome.state, "stopped");
  assert.equal(outcome.attempts.length, 2);
  assert.equal(outcome.attempts[0].decision, "discard");
  assert.equal(outcome.attempts[0].failure?.category, "hypothesis");
  assert.ok(outcome.attempts.every((attempt) => attempt.manifest_ref));

  const summary = await readJson(stack, outcome.summaryRef!.uri);
  assert.equal(summary.stop_reason, "stopped");
  assert.equal((summary.attempts as Array<{ decision: string }>)[0].decision, "discard");
});

test("循环：连续失败达到上限后停止", async () => {
  const stack = createStubStack({ compute: { scenario: "fail", baseCostPerHour: 24 } });
  const outcome = await runExperimentLoop(
    makeLoopInput({ maxAttempts: 5, propose: () => makeSpec() }),
    depsOf(stack),
  );

  assert.equal(outcome.state, "consecutive_failures");
  assert.equal(outcome.attempts.length, 2);
  assert.equal(outcome.attempts[0].failure?.category, "unknown");
  assert.equal(outcome.attempts[0].decision, "stop");
});

test("循环：未知执行立即升级且不重试", async () => {
  const stack = createStubStack({ compute: { scenario: "unknown", baseCostPerHour: 24 } });
  let proposeCalls = 0;
  const outcome = await runExperimentLoop(
    makeLoopInput({
      propose: () => {
        proposeCalls += 1;
        return makeSpec();
      },
    }),
    depsOf(stack),
  );

  assert.equal(outcome.state, "escalated");
  assert.equal(outcome.attempts.length, 1);
  assert.equal(proposeCalls, 0);
  assert.equal(outcome.attempts[0].failure?.category, "unknown");
  assert.equal(outcome.attempts[0].failure?.retryable, false);
  const summary = await readJson(stack, outcome.summaryRef!.uri);
  assert.equal(summary.stop_reason, "escalated");
});

test("循环：剩余预算低于单轮上限时停止", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const outcome = await runExperimentLoop(
    makeLoopInput({
      spec: discardSpec(),
      budget: { total: 5.5, currency: "CNY" },
      propose: () => discardSpec(),
    }),
    depsOf(stack),
  );

  assert.equal(outcome.state, "budget_exhausted");
  assert.equal(outcome.attempts.length, 1);
  assert.ok(outcome.remainingBudget < 5);
});

test("循环：截止时间到达时不启动新一轮", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const outcome = await runExperimentLoop(
    makeLoopInput({ deadlineAt: new Date(Date.now() - 1000).toISOString() }),
    depsOf(stack),
  );

  assert.equal(outcome.state, "deadline");
  assert.equal(outcome.attempts.length, 0);
  assert.ok(outcome.summaryRef);
  const summary = await readJson(stack, outcome.summaryRef!.uri);
  assert.equal(summary.stop_reason, "deadline");
});

test("循环：第二轮的候选来自 propose", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  let proposeCalls = 0;
  const outcome = await runExperimentLoop(
    makeLoopInput({
      spec: discardSpec(),
      propose: () => {
        proposeCalls += 1;
        return makeSpec();
      },
    }),
    depsOf(stack),
  );

  assert.equal(outcome.state, "kept");
  assert.equal(outcome.attempts.length, 2);
  assert.equal(proposeCalls, 1);
  assert.deepEqual(
    outcome.attempts.map((attempt) => attempt.decision),
    ["discard", "keep"],
  );
  assert.notEqual(outcome.attempts[0].run_id, outcome.attempts[1].run_id);
});

test("循环：候选不能改变实验标识", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const outcome = await runExperimentLoop(
    makeLoopInput({
      spec: discardSpec(),
      propose: () => makeSpec({ experiment_id: "EXP-OTHER" }),
    }),
    depsOf(stack),
  );

  assert.equal(outcome.state, "invalid_candidate");
  assert.equal(outcome.attempts.length, 1);
  assert.ok(outcome.findings.some((finding) => finding.code === "E_LOOP_SPEC_MISMATCH"));
});

test("循环：编译失败也写出清单并停止", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const spec = makeSpec({ baseline: { ...makeSpec().baseline, reproduced: false } });
  const outcome = await runExperimentLoop(makeLoopInput({ spec }), depsOf(stack));

  assert.equal(outcome.state, "blocked");
  assert.equal(outcome.attempts.length, 1);
  assert.equal(outcome.attempts[0].failure?.category, "hypothesis");
  assert.ok(outcome.attempts[0].manifest_ref);
  const manifest = await readJson(stack, outcome.attempts[0].manifest_ref!);
  assert.equal(manifest.state, "failed");
});

test("循环：需要审批时停止且不提交作业", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const spec = makeSpec({
    resources: { ...makeSpec().resources, type: "hpc" },
  });
  const outcome = await runExperimentLoop(makeLoopInput({ spec }), depsOf(stack));

  assert.equal(outcome.state, "escalated");
  assert.equal(outcome.attempts.length, 1);
  assert.match(
    outcome.attempts[0].manifest_ref ?? "",
    /policy-decision\.json$/,
    "审批请求留痕是本轮唯一清单级产物，其余执行产物不入库",
  );
  assert.equal(stack.artifacts.size(), 2, "循环摘要 + 策略决定记录（审批请求留痕），无执行产物");
});


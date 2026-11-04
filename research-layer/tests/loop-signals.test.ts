import { test } from "node:test";
import assert from "node:assert/strict";

import type { DomainEvent, Subject } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";
import type { ExperimentSpec } from "../packages/domain/src/index.ts";
import { runExperimentLoop } from "../packages/pipeline/src/index.ts";

const agent: Subject = {
  type: "agent",
  id: "agent-loop-signal",
  tenantId: "tenant-signal",
  projectId: "project-signal",
  scopes: ["experiment:submit"],
};

const code = { repo: "github.com/company/example", commit: "c0ffee" };
const environment = {
  containerDigest: `sha256:${"a".repeat(64)}`,
  lockfileHash: "b".repeat(64),
};

function makeSpec(): ExperimentSpec {
  return {
    experiment_id: "EXP-SIGNAL-1",
    task_id: "TASK-SIGNAL-1",
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
    stopping: { max_attempts: 2, max_consecutive_failures: 2 },
    decision: {
      keep_if: "val_loss 下降 >= 0.02",
      discard_if: "护栏退化超过阈值",
    },
    artifacts: { required: ["code_hash", "env_lock", "raw_metrics", "manifest"] },
  };
}

function makeStack(scenario: "success" | "fail" = "success") {
  return createStubStack({ compute: { scenario, baseCostPerHour: 24 } });
}

function run(stack: ReturnType<typeof makeStack>, input: Record<string, unknown>) {
  return runExperimentLoop(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-loop-signal",
      idempotencyKey: `idem-signals-${input.budget ? "budget" : "kept"}`,
      code,
      environment,
      budget: { total: 100, currency: "CNY" },
      baselineGuardrails: { train_time_seconds: 200 },
      ...input,
    },
    { compute: stack.compute, artifacts: stack.artifacts, events: stack.events },
  );
}

function eventsOf(stack: ReturnType<typeof makeStack>): DomainEvent[] {
  return [
    ...(stack.events as unknown as { publishedEvents(): readonly DomainEvent[] }).publishedEvents(),
  ];
}

function countByType(stack: ReturnType<typeof makeStack>): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const event of eventsOf(stack)) {
    counts[event.type] = (counts[event.type] ?? 0) + 1;
  }
  return counts;
}

test("信号：保留循环发布租约变化与实验完成事件", async () => {
  const stack = makeStack();
  const outcome = await run(stack, { lease: {} });

  assert.equal(outcome.state, "kept");
  const counts = countByType(stack);
  assert.equal(counts["lease.changed.v1"], 2, "prepared + released");
  assert.equal(counts["experiment.completed.v1"], 1);
  assert.equal(counts["budget.exhausted.v1"], undefined);

  const leaseStates = eventsOf(stack)
    .filter((event) => event.type === "lease.changed.v1")
    .map((event) => event.data as { phase: string; state: string; fencing: number });
  assert.deepEqual(
    leaseStates.map((item) => item.phase),
    ["prepared", "released"],
  );
  assert.ok(leaseStates.every((item) => typeof item.fencing === "number" && item.fencing >= 1));

  const completed = eventsOf(stack).find((event) => event.type === "experiment.completed.v1");
  assert.ok(completed);
  assert.equal(completed.resourceId, "EXP-SIGNAL-1");
  assert.equal(completed.tenantId, "tenant-signal");
});

test("信号：预算耗尽发布预算事件且不发布实验完成", async () => {
  const stack = makeStack();
  const outcome = await run(stack, {
    lease: {},
    budget: { total: 1, currency: "CNY" },
  });

  assert.equal(outcome.state, "budget_exhausted");
  assert.equal(outcome.attempts.length, 0);

  const counts = countByType(stack);
  assert.equal(counts["budget.exhausted.v1"], 1);
  assert.equal(counts["experiment.completed.v1"], undefined);
  assert.equal(counts["lease.changed.v1"], undefined, "没有尝试就没有租约事件");

  const budget = eventsOf(stack).find((event) => event.type === "budget.exhausted.v1");
  assert.ok(budget);
  assert.equal(budget.resourceId, "EXP-SIGNAL-1");
  assert.deepEqual(budget.data, { stop_reason: "budget_exhausted", attempts: 0, remaining_budget: 1, currency: "CNY" });
});

test("信号：事件 id 确定且只承载事实数据", async () => {
  const stack = makeStack();
  await run(stack, { lease: {} });

  const completed = eventsOf(stack).find((event) => event.type === "experiment.completed.v1");
  assert.ok(completed);
  assert.equal(
    completed.id,
    "experiment.completed.v1:EXP-SIGNAL-1:2",
    "resource_version = 尝试数 + 1",
  );
  assert.equal(completed.source, "research-layer");
  assert.equal(completed.dataContentType, "application/json");
  assert.ok(
    Object.keys(completed.data as Record<string, unknown>).every(
      (key) => !/secret|token|password|prompt|credential|api_key/i.test(key),
    ),
  );
});

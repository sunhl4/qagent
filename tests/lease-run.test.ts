import { test } from "node:test";
import assert from "node:assert/strict";

import type { Subject } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";
import { emptyCostLedger } from "../packages/domain/src/index.ts";
import type { ExperimentSpec } from "../packages/domain/src/index.ts";
import { runExperiment } from "../packages/pipeline/src/index.ts";
import type { RunInput } from "../packages/pipeline/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const agent: Subject = {
  type: "agent",
  id: "agent-lease-run",
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
    experiment_id: "EXP-LEASERUN-1",
    task_id: "TASK-LEASERUN-1",
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
    stopping: { max_attempts: 1, max_consecutive_failures: 1 },
    decision: {
      keep_if: "val_loss 下降 >= 0.02",
      discard_if: "护栏退化超过阈值",
    },
    artifacts: { required: ["code_hash", "env_lock", "raw_metrics", "manifest"] },
    ...overrides,
  };
}

function makeInput(overrides: Partial<RunInput> = {}): RunInput {
  return {
    spec: makeSpec(),
    subject: agent,
    traceId: "trace-lease-run",
    idempotencyKey: "idem-lease-run",
    code,
    environment,
    budget: { remaining: 100, currency: "CNY" },
    baselineGuardrails: { train_time_seconds: 200 },
    ...overrides,
  };
}

function makeStack(scenario: "success" | "fail" | "unknown" = "success") {
  return createStubStack({ compute: { scenario, baseCostPerHour: 24 } });
}

async function readJson(stack: ReturnType<typeof makeStack>, uri: string): Promise<Record<string, unknown>> {
  const read = await stack.artifacts.get({ tenantId: agent.tenantId, uri });
  assert.equal(read.ok, true);
  if (!read.ok) throw new Error("产物读取失败");
  return JSON.parse(new TextDecoder().decode(read.value.bytes)) as Record<string, unknown>;
}

test("租约接入：成功运行后释放资源并结算成本", async () => {
  const stack = makeStack();
  const outcome = await runExperiment(
    makeInput({
      lease: { budget: { limit: 100, currency: "CNY" }, ledger: emptyCostLedger() },
    }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "succeeded", JSON.stringify(outcome.findings));
  assert.ok(outcome.lease);
  assert.equal(outcome.lease!.state, "RELEASED");

  assert.ok(outcome.costTotals);
  const totals = outcome.costTotals![0];
  assert.equal(totals.currency, "CNY");
  assert.equal(totals.reserved, 5);
  assert.equal(totals.actual, 0.8);
  assert.equal(totals.released, 4.2);
  assert.equal(totals.committed, 0.8);

  assert.ok(outcome.manifest);
  const costsArtifact = outcome.manifest!.artifacts.find((item) => item.type === "report");
  assert.ok(costsArtifact, "manifest 应包含成本快照产物");
  assert.match(costsArtifact!.sha256, /^[a-f0-9]{64}$/);

  const snapshot = await readJson(stack, costsArtifact!.uri);
  const errors = validateJsonSchema(snapshot, await loadSchema("cost-ledger.schema.json"));
  assert.deepEqual(errors, []);
  assert.equal((snapshot as { totals: Array<{ committed: number }> }).totals[0].committed, 0.8);

  const handleId = outcome.manifest!.resources.handle_id!;
  const finalStatus = await stack.compute.status(handleId);
  assert.ok(finalStatus.ok);
  if (finalStatus.ok) {
    assert.equal(finalStatus.value.state, "cancelled", "任务结束后资源应已释放");
    assert.equal(finalStatus.value.reason, "已释放");
  }
});

test("租约接入：预算不足时不提交作业并写出失败清单", async () => {
  const stack = makeStack();
  const outcome = await runExperiment(
    makeInput({
      lease: {
        budget: { limit: 1, currency: "CNY" },
        ledger: emptyCostLedger(),
      },
    }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "denied");
  assert.ok(outcome.failure);
  assert.equal(outcome.failure!.category, "resource");
  assert.ok(outcome.manifest, "拒绝也要留下运行清单");
  assert.equal(outcome.manifest!.state, "failed");

  const jobs = await stack.compute.list({ tenantId: agent.tenantId });
  assert.ok(jobs.ok);
  if (jobs.ok) assert.equal(jobs.value.length, 0, "预算不足不得提交作业");
});

test("租约接入：未知执行升级并保留预留", async () => {
  const stack = makeStack("unknown");
  const outcome = await runExperiment(
    makeInput({
      lease: { budget: { limit: 100, currency: "CNY" }, ledger: emptyCostLedger() },
    }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "unknown_execution");
  assert.ok(outcome.lease);
  assert.equal(outcome.lease!.state, "PREPARED");
  assert.equal(outcome.lease!.hold_reason, "unknown_execution");
  assert.equal(outcome.error?.retryable, false);

  assert.ok(outcome.costTotals);
  const totals = outcome.costTotals![0];
  assert.equal(totals.reserved, 5);
  assert.equal(totals.released, 0);
  assert.equal(totals.committed, 5, "预留保持占用，等待人工对账");

  assert.ok(outcome.manifest);
  assert.equal(outcome.manifest!.state, "unknown");
  assert.equal(outcome.manifest!.failure?.category, "unknown");

  const manifestSchema = await loadSchema("run-manifest.schema.json");
  assert.deepEqual(validateJsonSchema(outcome.manifest, manifestSchema), []);
});

test("租约接入：失败运行仍释放资源", async () => {
  const stack = makeStack("fail");
  const outcome = await runExperiment(
    makeInput({
      lease: { budget: { limit: 100, currency: "CNY" }, ledger: emptyCostLedger() },
    }),
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "stopped", "失败轮按预注册规则进入 stop");
  assert.ok(outcome.lease);
  assert.equal(outcome.lease!.state, "RELEASED");

  const totals = outcome.costTotals![0];
  assert.equal(totals.actual, outcome.manifest?.resources.cost ?? -1);
  assert.ok(totals.committed <= totals.reserved, "结算后已承诺成本不超过预留上界");
});

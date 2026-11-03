import { test } from "node:test";
import assert from "node:assert/strict";

import type { Subject } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";
import type { ExperimentSpec } from "../packages/domain/src/index.ts";
import { runExperiment } from "../packages/pipeline/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const agent: Subject = {
  type: "agent",
  id: "agent-policy-record",
  tenantId: "tenant-policy",
  projectId: "project-policy",
  scopes: ["experiment:submit"],
};

const code = { repo: "github.com/company/example", commit: "c0ffee" };
const environment = {
  containerDigest: `sha256:${"a".repeat(64)}`,
  lockfileHash: "b".repeat(64),
};

function makeSpec(): ExperimentSpec {
  return {
    experiment_id: "EXP-POLICY-1",
    task_id: "TASK-POLICY-1",
    hypothesis: {
      statement: "加入预热可以降低验证损失",
      falsifiable_by: "若验证损失未下降，则假设不成立",
    },
    baseline: { name: "无预热基线", source: "内部复现", reproduced: true, metric_value: 1.0 },
    variables: {
      changed: ["src/train/scheduler.py"],
      controlled: ["dataset"],
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

function makeStack() {
  return createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
}

async function readJson(stack: ReturnType<typeof makeStack>, uri: string): Promise<Record<string, unknown>> {
  const read = await stack.artifacts.get({ tenantId: agent.tenantId, uri });
  assert.equal(read.ok, true);
  if (!read.ok) throw new Error("产物读取失败");
  return JSON.parse(new TextDecoder().decode(read.value.bytes)) as Record<string, unknown>;
}

test("策略记录：拒绝路径落盘并通过 schema", async () => {
  const stack = makeStack();
  const outcome = await runExperiment(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-policy-deny",
      idempotencyKey: "idem-policy-deny",
      code,
      environment,
      budget: { remaining: 1, currency: "CNY" },
    },
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "denied");
  assert.ok(outcome.policyRecord);
  const schema = await loadSchema("policy-decision.schema.json");
  assert.deepEqual(validateJsonSchema(outcome.policyRecord, schema), []);
  assert.equal(outcome.policyRecord!.decision, "DENY");
  assert.equal(outcome.policyRecord!.matched_rules[0].rule_id, "R-BUDGET");
  assert.equal(outcome.policyRecord!.subject.tenant_id, "tenant-policy");

  assert.ok(outcome.policyRecordRef, "策略记录应有独立产物 URI");
  assert.match(outcome.policyRecordRef!.uri, /policy-decision\.json$/);
  const stored = await readJson(stack, outcome.policyRecordRef!.uri);
  assert.equal((stored as { decision: string }).decision, "DENY");
});

test("策略记录：审批路径允许并留痕", async () => {
  const stack = makeStack();
  const outcome = await runExperiment(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-policy-allow",
      idempotencyKey: "idem-policy-allow",
      code,
      environment,
      budget: { remaining: 100, currency: "CNY", approvedActions: ["experiment.submit"] },
    },
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "succeeded");
  assert.ok(outcome.policyRecord);
  assert.equal(outcome.policyRecord!.decision, "ALLOW");
  assert.match(outcome.policyRecord!.decision_id, /policy$/);
});

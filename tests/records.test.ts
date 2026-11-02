/**
 * 记录契约校验：用仓库内的 JSON Schema 校验实际产出的 manifest 与循环摘要。
 *
 * 本工程要求所有对外对象都能通过 schemas/ 中的 JSON Schema 校验。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import type { Subject } from "../contracts/src/index.ts";
import { createStubStack } from "../adapters/stub/src/index.ts";
import type { ExperimentSpec } from "../packages/domain/src/index.ts";
import { runExperiment, runExperimentLoop } from "../packages/pipeline/src/index.ts";
import { loadSchema, validateJsonSchema as validate } from "./schema-validator.ts";

const agent: Subject = {
  type: "agent",
  id: "agent-record",
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
  const spec: ExperimentSpec = {
    experiment_id: "EXP-RECORD-1",
    task_id: "TASK-RECORD-1",
    hypothesis: {
      statement: "加入预热可以降低验证损失",
      evidence_refs: ["paper:example"],
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
      controlled: ["dataset", "split", "model"],
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
    stopping: {
      max_attempts: 3,
      max_consecutive_failures: 2,
    },
    decision: {
      keep_if: "val_loss 下降 >= 0.02",
      discard_if: "护栏退化超过阈值",
    },
    artifacts: {
      required: ["code_hash", "env_lock", "raw_metrics", "manifest"],
    },
  };
  return { ...spec, ...overrides };
}

async function readJson(stack: ReturnType<typeof createStubStack>, uri: string) {
  const read = await stack.artifacts.get({ tenantId: agent.tenantId, uri });
  assert.equal(read.ok, true);
  if (!read.ok) throw new Error("产物读取失败");
  return JSON.parse(new TextDecoder().decode(read.value.bytes)) as unknown;
}

test("成功运行的 manifest 通过 run-manifest schema", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const outcome = await runExperiment(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-record-1",
      idempotencyKey: "idem-record-1",
      code,
      environment,
      budget: { remaining: 100, currency: "CNY" },
      baselineGuardrails: { train_time_seconds: 200 },
    },
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.ok(outcome.manifestRef);
  const manifest = await readJson(stack, outcome.manifestRef!.uri);
  const errors = validate(manifest, await loadSchema("run-manifest.schema.json"));
  assert.deepEqual(errors, []);
});

test("未知执行的 manifest 通过 schema 且不可重试", async () => {
  const stack = createStubStack({ compute: { scenario: "unknown", baseCostPerHour: 24 } });
  const outcome = await runExperiment(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-record-2",
      idempotencyKey: "idem-record-2",
      code,
      environment,
      budget: { remaining: 100, currency: "CNY" },
    },
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.ok(outcome.manifestRef);
  const manifest = await readJson(stack, outcome.manifestRef!.uri);
  const errors = validate(manifest, await loadSchema("run-manifest.schema.json"));
  assert.deepEqual(errors, []);
  assert.equal((manifest as { failure: { retryable: boolean } }).failure.retryable, false);
});

test("循环摘要通过 loop-summary schema", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const outcome = await runExperimentLoop(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-record-3",
      idempotencyKey: "idem-record-3",
      code,
      environment,
      budget: { total: 100, currency: "CNY" },
      baselineGuardrails: { train_time_seconds: 200 },
    },
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.ok(outcome.summaryRef);
  const summary = await readJson(stack, outcome.summaryRef!.uri);
  const errors = validate(summary, await loadSchema("loop-summary.schema.json"));
  assert.deepEqual(errors, []);
});

test("非法规格的失败记录仍能通过 schema", async () => {
  const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 24 } });
  const spec = makeSpec({
    resources: { ...makeSpec().resources, currency: "EURO" },
  });
  const outcome = await runExperiment(
    {
      spec,
      subject: agent,
      traceId: "trace-record-4",
      idempotencyKey: "idem-record-4",
      code,
      environment,
      budget: { remaining: 100, currency: "CNY" },
    },
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "rejected");
  assert.ok(outcome.manifestRef);
  const manifest = await readJson(stack, outcome.manifestRef!.uri);
  const errors = validate(manifest, await loadSchema("run-manifest.schema.json"));
  assert.deepEqual(errors, []);
  assert.equal(
    (manifest as { resources: { currency: string } }).resources.currency,
    "CNY",
  );
});

test("循环失败库通过 failure-library schema", async () => {
  const stack = createStubStack({ compute: { scenario: "fail", baseCostPerHour: 24 } });
  const outcome = await runExperimentLoop(
    {
      spec: makeSpec(),
      subject: agent,
      traceId: "trace-record-5",
      idempotencyKey: "idem-record-5",
      code,
      environment,
      budget: { total: 100, currency: "CNY" },
      baselineGuardrails: { train_time_seconds: 200 },
      maxAttempts: 3,
      propose: () => makeSpec(),
    },
    { compute: stack.compute, artifacts: stack.artifacts },
  );

  assert.equal(outcome.state, "consecutive_failures");
  assert.ok(outcome.failureRef);
  assert.equal(outcome.failures.length, 2);
  const library = await readJson(stack, outcome.failureRef!.uri);
  const errors = validate(library, await loadSchema("failure-library.schema.json"));
  assert.deepEqual(errors, []);
  assert.equal(
    (library as { stats: { total: number } }).stats.total,
    2,
  );
});

#!/usr/bin/env node
/**
 * 桩上演示：一次有界实验循环。
 *
 * 只使用本工程内存桩（全部端口声明 degraded），不访问真实资源、不产生真实成本。
 * 展示 `packages/pipeline` 的输入输出：租约预算下的单次实验、失败留痕与摘要产物。
 */

import { createStubStack } from "../adapters/stub/src/index.ts";
import { runExperimentLoop } from "../packages/pipeline/src/index.ts";

const agent = {
  type: "agent",
  id: "agent-demo",
  tenantId: "tenant-demo",
  projectId: "project-demo",
  scopes: ["experiment:submit"],
};

const spec = {
  experiment_id: "EXP-DEMO-1",
  task_id: "TASK-DEMO-1",
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

const stack = createStubStack({
  compute: { scenario: "success", baseCostPerHour: 12 },
});

console.log("== DeepSeekHarness 桩上演示：一次有界实验循环 ==");
const loop = await runExperimentLoop(
  {
    spec,
    subject: agent,
    traceId: "trace-demo",
    idempotencyKey: "idem-demo",
    code: { repo: "github.com/company/example", commit: "c0ffee" },
    environment: {
      containerDigest: `sha256:${"a".repeat(64)}`,
      lockfileHash: "b".repeat(64),
    },
    budget: { total: 100, currency: "CNY" },
    baselineGuardrails: { train_time_seconds: 200 },
  },
  { compute: stack.compute, artifacts: stack.artifacts },
);

console.log(`停止状态      : ${loop.state}`);
console.log(`尝试次数      : ${loop.attempts.length}`);
console.log(`失败条目      : ${loop.failures.length} 条`);
console.log(`worktree 记录 : ${loop.worktrees.length} 条`);
console.log(`总成本        : ${loop.totalCost} ${spec.resources.currency}（预算 100）`);
console.log(`摘要产物      : ${loop.summaryRef ? "已写入" : "无"}`);
console.log(`循环摘要      : stop_reason=${loop.summary.stop_reason}, 状态=${loop.summary.attempts.length} 次尝试`);
console.log(
  `提示          : 全部端口为本地桩（degraded），演示不产生真实成本；正式实现由 harness-core 提供。`,
);

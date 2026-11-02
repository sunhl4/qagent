import { test } from "node:test";
import assert from "node:assert/strict";

import { classifyFailure } from "../packages/domain/src/index.ts";

test("失败分类：编译错误按领域含义归类", () => {
  assert.equal(
    classifyFailure({ stage: "compile", code: "E_BASELINE_NOT_REPRODUCED" }).category,
    "hypothesis",
  );
  assert.equal(
    classifyFailure({ stage: "compile", code: "E_CHECKPOINT_REQUIRED" }).category,
    "resource",
  );
  assert.equal(classifyFailure({ stage: "compile", code: "E_OUT_OF_SCOPE" }).category, "implementation");
  assert.equal(classifyFailure({ stage: "compile", code: "E_ARTIFACT" }).category, "metric");
  assert.equal(classifyFailure({ stage: "compile", code: "E_MOE" }).category, "hypothesis");
});

test("失败分类：未知执行永远不可重试", () => {
  const record = classifyFailure({
    stage: "unknown_execution",
    code: "UNKNOWN_EXECUTION",
    retryable: true,
  });
  assert.equal(record.category, "unknown");
  assert.equal(record.retryable, false);
});

test("失败分类：策略规则与预算", () => {
  assert.equal(
    classifyFailure({ stage: "policy", code: "R-DATA-RESIDENCY" }).category,
    "policy",
  );
  assert.equal(classifyFailure({ stage: "policy", code: "R-BUDGET" }).category, "resource");
  assert.equal(
    classifyFailure({ stage: "policy", code: "R-UNKNOWN-NO-RETRY" }).category,
    "unknown",
  );
});

test("失败分类：端口错误的可重试性", () => {
  const timeout = classifyFailure({ stage: "submit", portErrorCode: "TIMEOUT" });
  assert.equal(timeout.category, "environment");
  assert.equal(timeout.retryable, true);

  const quota = classifyFailure({ stage: "quote", portErrorCode: "QUOTA_EXCEEDED" });
  assert.equal(quota.category, "resource");
  assert.equal(quota.retryable, false);

  const denied = classifyFailure({ stage: "submit", portErrorCode: "PERMISSION_DENIED" });
  assert.equal(denied.category, "policy");
  assert.equal(denied.retryable, false);
});

test("失败分类：决策原因映射", () => {
  assert.equal(
    classifyFailure({
      stage: "decision",
      decision: "discard",
      reasons: ["主指标改进 0.001 未达到最小可观测效应 0.02"],
    }).category,
    "hypothesis",
  );
  assert.equal(
    classifyFailure({
      stage: "decision",
      decision: "discard",
      reasons: ["护栏 train_time_seconds 退化 0.5，超过阈值 0.1"],
    }).category,
    "hypothesis",
  );
  assert.equal(
    classifyFailure({
      stage: "decision",
      decision: "extend",
      reasons: ["结果方差过大（相对标准差 0.80），需更多重复"],
    }).category,
    "instability",
  );
  assert.equal(
    classifyFailure({
      stage: "decision",
      decision: "escalate",
      reasons: ["缺少产物: report"],
    }).category,
    "metric",
  );
  assert.equal(
    classifyFailure({
      stage: "decision",
      decision: "stop",
      reasons: ["执行失败"],
    }).category,
    "unknown",
  );
});

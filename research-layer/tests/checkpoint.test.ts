import { test } from "node:test";
import assert from "node:assert/strict";

import {
  attemptArtifactPrefix,
  checkpointArtifactKey,
  latestCheckpoint,
  planResume,
} from "../packages/domain/src/index.ts";
import type {
  CheckpointRecord,
  ResumeRequest,
} from "../packages/domain/src/index.ts";
import { loadSchema, validateJsonSchema } from "./schema-validator.ts";

const NOW = new Date("2026-10-30T01:00:00.000Z");

function makeCheckpoint(overrides: Partial<CheckpointRecord> = {}): CheckpointRecord {
  return {
    checkpoint_id: "CKPT-1",
    experiment_id: "EXP-1",
    attempt: 1,
    uri: "s3://bucket/checkpoints/ckpt-1",
    sha256: "a".repeat(64),
    step: 100,
    created_at: "2026-10-30T00:50:00.000Z",
    code_commit: "c0ffee",
    environment_hash: "env-hash-1",
    seed: 13,
    size_bytes: 1024,
    ...overrides,
  };
}

function makeRequest(overrides: Partial<ResumeRequest> = {}): ResumeRequest {
  return {
    experiment_id: "EXP-1",
    previous_attempt: 1,
    previous_state: "failed",
    checkpoints: [makeCheckpoint()],
    policy: { required: true, max_age_seconds: 3600, max_resumes: 2 },
    current_code_commit: "c0ffee",
    current_environment_hash: "env-hash-1",
    resume_count: 0,
    now: NOW,
    ...overrides,
  };
}

test("检查点：有效检查点允许恢复到新 attempt", () => {
  const decision = planResume(makeRequest());
  assert.equal(decision.action, "resume");
  assert.equal(decision.next_attempt, 2);
  assert.equal(decision.from_checkpoint?.checkpoint_id, "CKPT-1");
  assert.ok(decision.reason.includes("CKPT-1"));
});

test("检查点：选择 step 最大的有效检查点", () => {
  const decision = planResume(
    makeRequest({
      checkpoints: [
        makeCheckpoint({ checkpoint_id: "OLD", step: 10 }),
        makeCheckpoint({ checkpoint_id: "NEW", step: 200, created_at: "2026-10-30T00:55:00.000Z" }),
        makeCheckpoint({ checkpoint_id: "INVALID", step: 300, valid: false }),
      ],
    }),
  );
  assert.equal(decision.action, "resume");
  assert.equal(decision.from_checkpoint?.checkpoint_id, "NEW");
  assert.equal(decision.from_checkpoint?.step, 200);

  assert.equal(
    latestCheckpoint(
      [makeCheckpoint({ checkpoint_id: "A", step: 1 }), makeCheckpoint({ checkpoint_id: "B", step: 2 })],
      "EXP-1",
      1,
    )?.checkpoint_id,
    "B",
  );
});

test("检查点：缺失、过期、代码或环境不一致时重启", () => {
  const missing = planResume(makeRequest({ checkpoints: [] }));
  assert.equal(missing.action, "restart");
  assert.ok(missing.findings.some((item) => item.code === "W_CHECKPOINT_MISSING"));

  const stale = planResume(
    makeRequest({
      checkpoints: [makeCheckpoint({ created_at: "2026-10-29T00:00:00.000Z" })],
    }),
  );
  assert.equal(stale.action, "restart");
  assert.ok(stale.findings.some((item) => item.code === "W_CHECKPOINT_STALE"));

  const codeMismatch = planResume(makeRequest({ current_code_commit: "deadbeef" }));
  assert.equal(codeMismatch.action, "restart");
  assert.ok(
    codeMismatch.findings.some((item) => item.code === "W_CHECKPOINT_CODE_MISMATCH"),
  );

  const envMismatch = planResume(makeRequest({ current_environment_hash: "env-hash-2" }));
  assert.equal(envMismatch.action, "restart");
  assert.ok(
    envMismatch.findings.some((item) => item.code === "W_CHECKPOINT_ENV_MISMATCH"),
  );
});

test("检查点：未知执行、恢复上限、成功与取消的决策", () => {
  const unknown = planResume(makeRequest({ previous_state: "unknown_execution" }));
  assert.equal(unknown.action, "escalate");
  assert.ok(
    unknown.findings.some((item) => item.code === "E_RESUME_UNKNOWN_EXECUTION"),
  );

  const limited = planResume(makeRequest({ resume_count: 2 }));
  assert.equal(limited.action, "escalate");
  assert.ok(limited.findings.some((item) => item.code === "E_RESUME_LIMIT"));

  assert.equal(
    planResume(makeRequest({ previous_state: "succeeded" })).action,
    "none",
  );
  assert.equal(
    planResume(makeRequest({ previous_state: "cancelled" })).action,
    "none",
  );
});

test("检查点：新 attempt 的产物 key 不覆盖旧产物", () => {
  const first = checkpointArtifactKey("EXP-1", 1, "CKPT-1");
  const second = checkpointArtifactKey("EXP-1", 2, "CKPT-1");
  assert.notEqual(first, second);
  assert.ok(first.includes("/attempt-1/"));
  assert.ok(second.includes("/attempt-2/"));
  assert.ok(attemptArtifactPrefix("EXP-1", 2).endsWith("/attempt-2/"));

  const encoded = checkpointArtifactKey("EXP/1", 1, "CKPT/1");
  assert.ok(!encoded.includes("EXP/1/"));
  assert.ok(!encoded.includes("CKPT/1."));
});

test("检查点：记录通过 schema", async () => {
  const schema = await loadSchema("checkpoint-record.schema.json");
  assert.deepEqual(validateJsonSchema(makeCheckpoint(), schema), []);
});

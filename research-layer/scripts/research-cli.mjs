/**
 * Narrow clock for company-agent. Reads one JSON object on stdin and writes
 * one JSON object on stdout. The stub clock does not submit real resources.
 * Later attempts reuse the same spec and the same file.
 */

import { readFileSync } from "node:fs";

import { createStubStack } from "../adapters/stub/src/index.ts";
import { compileExperiment } from "../packages/domain/src/experiment.ts";
import { runExperimentLoop } from "../packages/pipeline/src/index.ts";

const MAX_INPUT_BYTES = 16_000;
const DECISIONS = new Set(["keep", "discard", "extend", "stop", "escalate"]);
const STOPS = new Set([
  "kept",
  "exhausted",
  "budget_exhausted",
  "deadline",
  "stopped",
  "escalated",
  "blocked",
  "consecutive_failures",
  "no_candidate",
  "invalid_candidate",
]);

function fail(errorCode) {
  process.stdout.write(`${JSON.stringify({ ok: false, error_code: errorCode })}\n`);
}

function specFrom(input, mode) {
  const changed = String(input.changed_path);
  if (changed.includes("..")) return null;
  const attempts = Number(input.max_attempts);
  const total = Number(input.max_cost);
  const share = mode === "run" ? total / attempts : total;
  const wall = mode === "run" ? Math.min(600, Math.floor((share * 3600) / 12)) : 600;
  if (!(share > 0) || wall < 1) return null;
  return {
    experiment_id: String(input.experiment_id),
    task_id: String(input.task_id),
    hypothesis: {
      statement: String(input.hypothesis),
      falsifiable_by: String(input.falsifier),
    },
    baseline: {
      name: String(input.baseline_name),
      source: String(input.baseline_source),
      reproduced: input.baseline_reproduced === true,
      metric_value: Number(input.baseline_metric),
    },
    variables: {
      changed: [changed],
      controlled: ["dataset", "split", "evaluation"],
      allowed_paths: [changed],
    },
    metrics: {
      primary: String(input.primary_metric),
      direction: input.direction,
      minimum_observable_effect: 0.02,
      guardrails: [],
      repeats: 1,
      seeds: [13],
    },
    resources: {
      type: input.resource_type,
      count: 1,
      max_wall_clock_seconds: wall,
      max_cost: share,
      currency: "CNY",
      checkpoint_required: true,
    },
    stopping: {
      max_attempts: Number(input.max_attempts),
      max_consecutive_failures: 1,
    },
    decision: {
      keep_if: "primary metric improves by at least 0.02",
      discard_if: "the metric does not improve or a guardrail regresses",
    },
    artifacts: { required: ["code_hash", "env_lock", "raw_metrics", "manifest"] },
  };
}

const raw = readFileSync(0, "utf8");
if (Buffer.byteLength(raw) > MAX_INPUT_BYTES) {
  fail("E_INPUT");
  process.exit(0);
}

let input;
try {
  input = JSON.parse(raw);
} catch {
  fail("E_INPUT");
  process.exit(0);
}

const spec = input && typeof input === "object"
  ? specFrom(input, input.action === "run" ? "run" : "compile")
  : null;
if (spec === null) {
  fail("E_PATH");
  process.exit(0);
}

const compiled = compileExperiment(spec);
if (input.action === "compile" || compiled.ok !== true) {
  const error = compiled.errors[0]?.code ?? "";
  process.stdout.write(`${JSON.stringify({
    ok: compiled.ok === true,
    error_code: compiled.ok === true ? "" : String(error).slice(0, 40),
    approval_required: compiled.approvalReasons.length > 0,
  })}\n`);
  process.exit(0);
}

if (input.action !== "run" || input.resource_type === "qpu") {
  fail("E_ACTION");
  process.exit(0);
}

const stack = createStubStack({ compute: { scenario: "success", baseCostPerHour: 12 } });
const loop = await runExperimentLoop(
  {
    spec,
    subject: {
      type: "agent",
      id: "company-research",
      tenantId: String(input.tenant_id),
      projectId: String(input.project_id || input.tenant_id),
      scopes: ["experiment:submit"],
    },
    traceId: `trace-${String(input.idempotency_key)}`,
    idempotencyKey: String(input.idempotency_key),
    code: { repo: "local", commit: "unpinned" },
    environment: {
      containerDigest: `sha256:${"a".repeat(64)}`,
      lockfileHash: "b".repeat(64),
    },
    budget: { total: Number(input.max_cost), currency: "CNY" },
    propose() {
      return spec;
    },
  },
  { compute: stack.compute, artifacts: stack.artifacts },
);

const decisions = loop.attempts
  .map((row) => (DECISIONS.has(row.decision) ? row.decision : "none"))
  .join(",");
const last = decisions.split(",").at(-1);
const decision = DECISIONS.has(last) ? last : "none";
const stop = STOPS.has(loop.state) ? loop.state : "blocked";
process.stdout.write(`${JSON.stringify({
  ok: true,
  error_code: "",
  approval_required: compiled.approvalReasons.length > 0,
  stop_reason: stop,
  attempts: loop.attempts.length,
  decision,
  decisions,
  remaining_budget: loop.remainingBudget,
  total_cost: loop.totalCost,
  failure_count: loop.failures.length,
})}\n`);

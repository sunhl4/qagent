/**
 * 研究层流水线：把 ExperimentSpec 送到 ComputePort 执行，并产出可追溯的运行清单。
 *
 * 本模块只依赖 contracts/ 中的端口，不依赖任何云、HPC、模型或 Harness 实现。
 * 合并后只需把桩替换为 harness-core 的真实实现。
 */

import { createHash } from "node:crypto";
import type {
  ArtifactRef,
  ArtifactStorePort,
  DataClass,
  EventPort,
  HpcSchedulerPort,
  PortErrorCode,
  ResourceHandle,
  ResourceRequest,
  Subject,
  TelemetryPort,
} from "../../../contracts/src/index.ts";
import type { Decision, ExperimentSpec, Finding, FailureRecord } from "../../domain/src/index.ts";
import {
  buildCostLedgerSnapshot,
  buildPlatformSignal,
  buildPolicyDecisionRecord,
  checkpointArtifactKey,
  classifyFailure,
  compileExperiment,
  decide,
  emptyCostLedger,
  evaluatePolicy,
  summarizeCost,
} from "../../domain/src/index.ts";
import type {
  CheckpointRecord,
  CostLedger,
  CostTotals,
  LeaseRecord,
} from "../../domain/src/index.ts";
import type { PolicyDecisionRecord, PolicyResult } from "../../domain/src/index.ts";
import { acquireLease, reconcileLease, releaseLease } from "./lease.ts";

export interface RunLeaseOptions {
  /** 项目级预算上限；准入与预留都按它检查。 */
  budget: { limit: number; currency: string };
  /** 租约 TTL；默认 `max_wall_clock_seconds`。 */
  ttlSeconds?: number;
  /** 外部账本；不提供时本次运行使用独立账本。 */
  ledger?: CostLedger;
}

export type PipelineState =
  | "rejected"
  | "denied"
  | "needs_approval"
  | "infeasible"
  | "escalated"
  | "succeeded"
  | "failed"
  | "unknown_execution"
  | "partial"
  | "stopped";

export type ManifestArtifactType =
  | "code"
  | "config"
  | "env_lock"
  | "container"
  | "checkpoint"
  | "raw_result"
  | "log"
  | "report"
  | "figure"
  | "dataset_ref"
  | "sbom";

export interface ManifestArtifact {
  type: ManifestArtifactType;
  uri: string;
  sha256: string;
  size_bytes?: number | null;
  retention?: string | null;
}

export interface RunManifest {
  run_id: string;
  task_id: string;
  experiment_id: string;
  attempt: number;
  state: "created" | "staging" | "running" | "completed" | "failed" | "partial" | "unknown";
  code: { repo: string; commit: string; branch?: string | null; dirty?: boolean };
  environment: { container_digest: string; lockfile_hash: string };
  resources: {
    handle_id?: string | null;
    lease_id?: string | null;
    type: string;
    count: number;
    started_at?: string | null;
    ended_at?: string | null;
    cost?: number | null;
    currency?: string | null;
  };
  metrics: Array<{ name: string; value: number; seed?: number | null; split?: string | null }>;
  artifacts: ManifestArtifact[];
  decision?: { action: string; reason?: string | null; decided_by?: string | null; decided_at?: string | null };
  failure?: { category: string; message?: string | null; retryable?: boolean };
  trace_id?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export interface RunInput {
  spec: ExperimentSpec;
  subject: Subject;
  traceId: string;
  idempotencyKey: string;
  code: { repo: string; commit: string; branch?: string; dirty?: boolean };
  environment: { containerDigest: string; lockfileHash: string };
  budget?: { remaining?: number; currency?: string; approvedActions?: string[]; approvalId?: string };
  baselineGuardrails?: Record<string, number>;
  dataClass?: DataClass;
  /** 第几次尝试，从 1 开始；用于区分产物路径与 manifest。 */
  attempt?: number;
  /** 运行 ID；默认 `${experiment_id}-run-${attempt}`。 */
  runId?: string;
  /** 启用后走租约准入：预留 → 提交 → 结束释放与结算；未启用保持原直连路径。 */
  lease?: RunLeaseOptions;
}

export interface RunDeps {
  compute: HpcSchedulerPort;
  artifacts: ArtifactStorePort;
  telemetry?: TelemetryPort;
  events?: EventPort;
  now?: () => Date;
}

export interface RunOptions {
  maxPolls?: number;
  pollDelayMs?: number;
}

export interface RunOutcome {
  state: PipelineState;
  decision?: Decision;
  policy?: PolicyResult;
  /** 策略评估落盘后的决定记录（schemas/policy-decision.schema.json）。 */
  policyRecord?: PolicyDecisionRecord;
  /** 策略决定记录的产物 URI（与 manifest 产物独立）。 */
  policyRecordRef?: ArtifactRef;
  manifest?: RunManifest;
  manifestRef?: ArtifactRef;
  failure?: FailureRecord;
  findings: Finding[];
  error?: { code: PortErrorCode; message: string; retryable: boolean };
  /** 启用租约时返回各币种汇总。 */
  costTotals?: CostTotals[];
  /** 启用租约时返回最终租约记录。 */
  lease?: LeaseRecord;
  /** 启用租约时返回最终账本，供调用方跨轮串联。 */
  ledger?: CostLedger;
  /** 供应商返回检查点时的指针记录。 */
  checkpoint?: CheckpointRecord;
}

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function riskOf(spec: ExperimentSpec): "low" | "medium" | "high" | "critical" {
  if (spec.resources.type === "qpu") return "critical";
  if (spec.resources.type === "hpc") return "high";
  if (spec.resources.type === "gpu" && (spec.resources.count ?? 1) > 1) return "high";
  if (spec.resources.max_cost > 100) return "high";
  return "medium";
}

function stateForError(code: PortErrorCode): PipelineState {
  if (code === "UNKNOWN_EXECUTION") return "unknown_execution";
  if (code === "PERMISSION_DENIED" || code === "UNAUTHENTICATED") return "denied";
  if (code === "QUOTA_EXCEEDED") return "denied";
  if (code === "NOT_SUPPORTED") return "infeasible";
  if (code === "UNAVAILABLE" || code === "TIMEOUT") return "partial";
  return "failed";
}

function manifestStateFor(state: PipelineState): RunManifest["state"] {
  if (state === "succeeded") return "completed";
  if (state === "unknown_execution") return "unknown";
  if (state === "partial") return "partial";
  if (state === "needs_approval") return "created";
  return "failed";
}

function toManifestArtifact(
  ref: ArtifactRef,
  type: ManifestArtifactType,
): ManifestArtifact {
  return {
    type,
    uri: ref.uri,
    sha256: ref.sha256 ?? sha256(ref.uri),
    size_bytes: ref.sizeBytes ?? null,
    retention: ref.retention ?? null,
  };
}

export async function runExperiment(
  input: RunInput,
  deps: RunDeps,
  options: RunOptions = {},
): Promise<RunOutcome> {
  const findings: Finding[] = [];
  const now = deps.now ?? (() => new Date());
  const pollDelayMs = options.pollDelayMs ?? 0;
  const maxPolls = options.maxPolls ?? 20;

  const trace = (name: string, attributes: Record<string, string | number | boolean>): void => {
    if (!deps.telemetry) return;
    void deps.telemetry.emit({
      name,
      at: now().toISOString(),
      traceId: input.traceId,
      tenantId: input.subject.tenantId,
      projectId: input.subject.projectId,
      attributes,
      redactionApplied: true,
    });
  };

  const attempt = Math.max(1, input.attempt ?? 1);
  const runId = input.runId ?? `${input.spec.experiment_id}-run-${attempt}`;
  const attemptPrefix = `experiments/${input.spec.experiment_id}/attempt-${attempt}`;
  const startedAt = now().toISOString();

  const baseManifest = (
    state: RunManifest["state"],
    failure?: FailureRecord,
  ): RunManifest => ({
    run_id: runId,
    task_id: input.spec.task_id,
    experiment_id: input.spec.experiment_id,
    attempt,
    state,
    code: {
      repo: input.code.repo,
      commit: input.code.commit,
      branch: input.code.branch ?? null,
      dirty: input.code.dirty ?? false,
    },
    environment: {
      container_digest: input.environment.containerDigest,
      lockfile_hash: input.environment.lockfileHash,
    },
    resources: {
      handle_id: null,
      type: ["cpu", "gpu", "hpc", "qpu", "cloud", "browser"].includes(
        input.spec.resources?.type,
      )
        ? input.spec.resources.type
        : "cpu",
      count: input.spec.resources?.count ?? 1,
      started_at: null,
      ended_at: null,
      cost: null,
      currency: /^[A-Z]{3}$/.test(input.spec.resources?.currency ?? "")
        ? input.spec.resources.currency
        : "CNY",
    },
    metrics: [],
    artifacts: [],
    failure: failure
      ? { category: failure.category, message: failure.message, retryable: failure.retryable }
      : undefined,
    trace_id: input.traceId,
    created_at: startedAt,
    finished_at: now().toISOString(),
  });

  const persistManifest = async (manifest: RunManifest): Promise<ArtifactRef | undefined> => {
    const manifestJson = JSON.stringify(manifest, null, 2);
    const put = await deps.artifacts.put({
      tenantId: input.subject.tenantId,
      projectId: input.subject.projectId,
      key: `${attemptPrefix}/manifest.json`,
      contentType: "application/json",
      bytes: new TextEncoder().encode(manifestJson),
      expectedSha256: sha256(manifestJson),
      metadata: { task_id: input.spec.task_id, attempt: String(attempt) },
      idempotencyKey: `${input.idempotencyKey}:manifest`,
    });
    if (!put.ok) {
      findings.push({
        severity: "warning",
        code: "W_MANIFEST_UPLOAD",
        message: `运行清单写入失败: ${put.error.code} ${put.error.message}`,
      });
      return undefined;
    }
    return put.value;
  };

  /* 策略决定记录：在 failureOutcome 之前声明，避免 TDZ；写入失败只告警不阻塞。 */
  let policyRecord: PolicyDecisionRecord | undefined;
  let policyRecordRef: ArtifactRef | undefined;

  const persistCostSnapshot = async (
    ledger: CostLedger,
  ): Promise<{ ref?: ArtifactRef; totals?: CostTotals[] }> => {
    if (ledger.entries.length === 0) return {};
    const snapshot = buildCostLedgerSnapshot(ledger, { taskId: input.spec.task_id });
    const costsJson = JSON.stringify(snapshot, null, 2);
    const put = await deps.artifacts.put({
      tenantId: input.subject.tenantId,
      projectId: input.subject.projectId,
      key: `${attemptPrefix}/costs.json`,
      contentType: "application/json",
      bytes: new TextEncoder().encode(costsJson),
      expectedSha256: sha256(costsJson),
      metadata: { task_id: input.spec.task_id, attempt: String(attempt) },
      idempotencyKey: `${input.idempotencyKey}:costs`,
    });
    if (!put.ok) {
      findings.push({
        severity: "warning",
        code: "W_COSTS_UPLOAD",
        message: `成本快照写入失败: ${put.error.code} ${put.error.message}`,
      });
      return { totals: snapshot.totals };
    }
    return { ref: put.value, totals: snapshot.totals };
  };

  const failureOutcome = async (
    state: PipelineState,
    failure: FailureRecord,
    extra: { policy?: PolicyResult; error?: RunOutcome["error"]; costTotals?: CostTotals[]; lease?: LeaseRecord; ledger?: CostLedger } = {},
  ): Promise<RunOutcome> => {
    const manifest = baseManifest(manifestStateFor(state), failure);
    const manifestRef = await persistManifest(manifest);
    return {
      state,
      failure,
      manifest,
      manifestRef,
      findings,
      policyRecord: policyRecordRef ? policyRecord : undefined,
      policyRecordRef: policyRecordRef,
      ...extra,
    };
  };

  /** 发布租约生命周期事实事件；失败只记 finding，不阻断业务。 */
  const emitLeaseSignal = async (
    lease: LeaseRecord,
    phase: "prepared" | "released",
    sink: Finding[],
  ): Promise<void> => {
    if (!deps.events || !lease) return;
    const built = buildPlatformSignal({
      type: "lease.changed.v1",
      tenant_id: lease.tenant_id,
      project_id: lease.project_id ?? null,
      resource_id: lease.lease_id,
      resource_version: lease.revision ?? 1,
      time: now().toISOString(),
      data: {
        phase,
        state: lease.state,
        fencing: lease.fencing_token,
        handle: lease.resource.handle_id ?? null,
      },
    });
    if (!built.ok || !built.signal) {
      sink.push({
        severity: "warning",
        code: "W_SIGNAL_BUILD",
        message: `租约事件构造失败: ${built.findings.map((item) => item.message).join("; ")}`,
      });
      return;
    }
    const published = await deps.events.publish({
      id: built.signal.id,
      type: built.signal.type,
      source: "research-layer",
      tenantId: lease.tenant_id,
      projectId: lease.project_id ?? undefined,
      resourceId: built.signal.resource_id,
      resourceVersion: built.signal.resource_version,
      time: built.signal.time,
      dataContentType: "application/json",
      data: built.signal.data,
      traceId: input.traceId,
    });
    if (!published.ok) {
      sink.push({
        severity: "warning",
        code: "W_SIGNAL_PUBLISH",
        message: `租约事件发布失败: ${published.error.code} ${published.error.message}`,
      });
    }
  };

  /* 1. 编译与校验 */
  const compiled = compileExperiment(input.spec);
  findings.push(...compiled.errors, ...compiled.warnings);
  if (!compiled.ok) {
    const first = compiled.errors[0];
    return failureOutcome(
      "rejected",
      classifyFailure({ stage: "compile", code: first?.code, message: first?.message }),
    );
  }
  trace("experiment.compiled", {
    experiment_id: input.spec.experiment_id,
    warnings: compiled.warnings.length,
  });

  /* 2. 策略 */
  const policy = evaluatePolicy(
    {
      name: "experiment.submit",
      risk: riskOf(input.spec),
      targetType: input.spec.resources.type,
      targetId: input.spec.experiment_id,
      estimatedCost: input.spec.resources.max_cost,
      currency: input.spec.resources.currency,
      dataClass: input.dataClass,
      residency: undefined,
      requiredResidency: input.dataClass === "restricted" ? "on_prem" : undefined,
    },
    {
      subject: {
        type: input.subject.type,
        id: input.subject.id,
        tenantId: input.subject.tenantId,
      },
      remainingBudget: input.budget?.remaining,
      currency: input.budget?.currency ?? input.spec.resources.currency,
      approvalId: input.budget?.approvalId,
      approvedActions: input.budget?.approvedActions,
    },
  );

  /* 2.1 审批与决定留痕：策略评估结果落产物，任何路径都可追溯 */
  policyRecord = buildPolicyDecisionRecord({
    decision_id: `${input.idempotencyKey}:policy`,
    subject: {
      type: input.subject.type,
      id: input.subject.id,
      tenantId: input.subject.tenantId,
      projectId: input.subject.projectId ?? null,
    },
    action: {
      name: "experiment.submit",
      target_type: input.spec.resources.type,
      target_id: input.spec.experiment_id,
      reversible: false,
      estimated_cost: input.spec.resources.max_cost,
      currency: input.spec.resources.currency,
    },
    result: policy,
    approvalId: input.budget?.approvalId ?? null,
    evaluatedAt: now().toISOString(),
    traceId: input.traceId,
  });
  const policyRecordJson = JSON.stringify(policyRecord, null, 2);
  const policyPut = await deps.artifacts.put({
    tenantId: input.subject.tenantId,
    projectId: input.subject.projectId,
    key: `${attemptPrefix}/policy-decision.json`,
    contentType: "application/json",
    bytes: new TextEncoder().encode(policyRecordJson),
    expectedSha256: sha256(policyRecordJson),
    metadata: { task_id: input.spec.task_id, decision: policy.decision }
  , idempotencyKey: `${input.idempotencyKey}:policy-record`,
  });
  policyRecordRef = policyPut.ok
    ? policyPut.value
    : (findings.push({
        severity: "warning",
        code: "W_POLICY_RECORD",
        message: `策略决定写入失败: ${policyPut.error.code} ${policyPut.error.message}`,
      }), undefined);

  if (policy.decision === "DENY") {
    const rule = policy.matchedRules.find((item) => item.effect === "deny");
    return failureOutcome(
      "denied",
      classifyFailure({ stage: "policy", code: rule?.ruleId, message: policy.reason }),
      { policy },
    );
  }
  if (policy.decision === "REQUIRE_APPROVAL" || policy.decision === "DEFER") {
    return {
      state: "needs_approval",
      policy,
      policyRecord,
      policyRecordRef,
      manifestRef: policyRecordRef,
      findings,
    };
  }

  /* 3. 记录规格 */
  const specJson = JSON.stringify(input.spec, null, 2);
  const specPut = await deps.artifacts.put({
    tenantId: input.subject.tenantId,
    projectId: input.subject.projectId,
    key: `${attemptPrefix}/spec.json`,
    contentType: "application/json",
    bytes: new TextEncoder().encode(specJson),
    expectedSha256: sha256(specJson),
    metadata: { task_id: input.spec.task_id, attempt: String(attempt) },
    idempotencyKey: `${input.idempotencyKey}:spec`,
  });
  if (!specPut.ok) {
    return failureOutcome(
      stateForError(specPut.error.code),
      classifyFailure({
        stage: "artifacts",
        portErrorCode: specPut.error.code,
        message: specPut.error.message,
      }),
      { policy, error: specPut.error },
    );
  }

  const storedArtifacts: Array<{ ref: ArtifactRef; type: ManifestArtifactType }> = [
    { ref: specPut.value, type: "config" },
  ];
  if (policyRecordRef) storedArtifacts.push({ ref: policyRecordRef, type: "report" });
  const artifactsPresent = new Set<string>(["config", "manifest"]);

  /* 4. 报价 */
  const request: ResourceRequest = {
    idempotencyKey: `${input.idempotencyKey}:submit`,
    requestId: `${input.spec.experiment_id}-attempt-${attempt}`,
    tenantId: input.subject.tenantId,
    projectId: input.subject.projectId,
    taskId: input.spec.task_id,
    kind: input.spec.resources.type,
    accelerator: input.spec.resources.accelerator ?? undefined,
    count: input.spec.resources.count ?? 1,
    wallClockSeconds: input.spec.resources.max_wall_clock_seconds,
    maxCost: input.spec.resources.max_cost,
    currency: input.spec.resources.currency,
    checkpoint: {
      required: input.spec.resources.checkpoint_required ?? false,
      intervalSeconds: input.spec.resources.checkpoint_interval_seconds ?? undefined,
    },
  };

  let handle: ResourceHandle;
  let activeLedger: CostLedger | undefined;
  let activeLease: LeaseRecord | undefined;
  const leaseEnabled = input.lease !== undefined;

  const mapAcquireFailure = (
    code: string,
    message: string,
  ): { state: PipelineState; stage: "policy" | "quote" | "submit" | "unknown_execution"; classifyCode: string } => {
    switch (code) {
      case "E_BUDGET_EXCEEDED":
      case "E_CURRENCY":
        return { state: "denied", stage: "policy", classifyCode: "R-BUDGET" };
      case "E_LEASE_INFEASIBLE":
        return { state: "infeasible", stage: "quote", classifyCode: "E_INFEASIBLE" };
      case "E_LEASE_INVALID":
      case "E_COST_RESERVATION":
        return { state: "rejected", stage: "policy", classifyCode: "E_POLICY" };
      default:
        return { state: "failed", stage: "submit", classifyCode: code };
    }
  };

  if (leaseEnabled) {
    const acquired = await acquireLease(
      {
        request,
        holder: { type: "attempt", id: `${input.spec.experiment_id}-attempt-${attempt}` },
        ttlSeconds: input.lease!.ttlSeconds ?? input.spec.resources.max_wall_clock_seconds,
        budget: input.lease!.budget,
        ledger: input.lease!.ledger ?? emptyCostLedger(),
        policyDecisionId: input.budget?.approvalId,
      },
      deps,
    );
    findings.push(...acquired.findings);
    activeLedger = acquired.ledger;

    if (!acquired.ok) {
      const costResult = await persistCostSnapshot(acquired.ledger);
      const errorCode = acquired.error?.code ?? "E_LEASE_INVALID";
      const message = acquired.error?.message ?? "租约获取失败";
      if (errorCode === "UNKNOWN_EXECUTION") {
        trace("experiment.unknown_execution", {
          experiment_id: input.spec.experiment_id,
          retry_forbidden: true,
        });
        return failureOutcome(
          "unknown_execution",
          classifyFailure({ stage: "unknown_execution", code: "UNKNOWN_EXECUTION", message }),
          {
            policy,
            error: { code: "UNKNOWN_EXECUTION", message, retryable: false },
            costTotals: costResult.totals,
            lease: acquired.lease,
            ledger: acquired.ledger,
          },
        );
      }
      const mapped = mapAcquireFailure(errorCode, message);
      const isPortError = (
        [
          "INVALID_ARGUMENT",
          "UNAUTHENTICATED",
          "PERMISSION_DENIED",
          "NOT_FOUND",
          "CONFLICT",
          "QUOTA_EXCEEDED",
          "NOT_SUPPORTED",
          "UNAVAILABLE",
          "TIMEOUT",
          "UNKNOWN_EXECUTION",
          "INTERNAL",
        ] as const
      ).includes(errorCode as never);
      if (isPortError) {
        return failureOutcome(
          stateForError(errorCode as PortErrorCode),
          classifyFailure({
            stage: mapped.stage === "unknown_execution" ? "submit" : mapped.stage,
            portErrorCode: errorCode as PortErrorCode,
            message,
          }),
          {
            policy,
            error: {
              code: errorCode as PortErrorCode,
              message,
              retryable: acquired.error?.retryable ?? false,
            },
            costTotals: costResult.totals,
            lease: acquired.lease,
            ledger: acquired.ledger,
          },
        );
      }
      return failureOutcome(
        mapped.state,
        classifyFailure({ stage: mapped.stage, code: mapped.classifyCode, message }),
        { policy, costTotals: costResult.totals, lease: acquired.lease, ledger: acquired.ledger },
      );
    }

    handle = acquired.handle!;
    activeLease = acquired.lease;
    await emitLeaseSignal(activeLease, "prepared", findings);
  } else {
    const quote = await deps.compute.quote(request);
    if (!quote.ok) {
      findings.push({
        severity: "error",
        code: "E_QUOTE",
        message: `报价失败: ${quote.error.code} ${quote.error.message}`,
      });
      return failureOutcome(
        stateForError(quote.error.code),
        classifyFailure({
          stage: "quote",
          portErrorCode: quote.error.code,
          message: `报价失败: ${quote.error.code} ${quote.error.message}`,
        }),
        { policy, error: quote.error },
      );
    }
    if (
      typeof quote.value.estimatedCost === "number" &&
      quote.value.estimatedCost > input.spec.resources.max_cost
    ) {
      const message = `估计成本 ${quote.value.estimatedCost} 超过预算 ${input.spec.resources.max_cost}`;
      findings.push({ severity: "error", code: "E_INFEASIBLE", message });
      return failureOutcome(
        "infeasible",
        classifyFailure({ stage: "quote", code: "E_INFEASIBLE", message }),
        { policy },
      );
    }

    /* 5. 提交与轮询 */
    const submitted = await deps.compute.submit(request);
    if (!submitted.ok) {
      return failureOutcome(
        stateForError(submitted.error.code),
        classifyFailure({
          stage: "submit",
          portErrorCode: submitted.error.code,
          message: submitted.error.message,
        }),
        { policy, error: submitted.error },
      );
    }
    handle = submitted.value;
  }

  let polls = 0;
  for (;;) {
    polls += 1;
    const status = await deps.compute.status(handle.handleId);
    if (!status.ok) {
      return failureOutcome(
        stateForError(status.error.code),
        classifyFailure({
          stage: "execution",
          portErrorCode: status.error.code,
          message: status.error.message,
        }),
        { policy, error: status.error },
      );
    }
    handle = status.value;
    if (["succeeded", "failed", "cancelled", "unknown"].includes(handle.state)) break;
    if (polls >= maxPolls) {
      handle = { ...handle, state: "unknown", reason: `轮询 ${maxPolls} 次仍未终态` };
      break;
    }
    if (pollDelayMs > 0) await sleep(pollDelayMs);
  }

  /* 6. 未知执行：对账，不重试 */
  if (handle.state === "unknown") {
    trace("experiment.unknown_execution", {
      experiment_id: input.spec.experiment_id,
      retry_forbidden: true,
    });
    if (leaseEnabled && activeLease && activeLedger) {
      const reconciled = await reconcileLease(
        { lease: activeLease, ledger: activeLedger, taskId: input.spec.task_id, handle },
        deps,
      );
      findings.push(...reconciled.findings);
      const costResult = await persistCostSnapshot(reconciled.ledger);
      if (reconciled.lease) activeLease = reconciled.lease;
      activeLedger = reconciled.ledger;

      if (reconciled.action === "settle") {
        handle = reconciled.handle ?? handle;
      } else if (reconciled.action === "wait") {
        return failureOutcome(
          "partial",
          classifyFailure({
            stage: "execution",
            code: "E_STILL_RUNNING",
            message: "对账后仍在排队或运行，禁止重试",
          }),
          { policy, costTotals: costResult.totals, lease: activeLease, ledger: activeLedger },
        );
      } else if (reconciled.action === "resubmit" || reconciled.action === "cancelled") {
        const failure: FailureRecord = {
          category: "environment",
          code:
            reconciled.action === "cancelled"
              ? "E_CANCELLED_BEFORE_EXECUTION"
              : "E_NOT_EXECUTED",
          message:
            reconciled.evidence && "reason" in reconciled.evidence
              ? reconciled.evidence.reason
              : "确认执行前未执行或已取消",
          retryable: true,
          stage: "execution",
        };
        return failureOutcome("failed", failure, {
          policy,
          costTotals: costResult.totals,
          lease: activeLease,
          ledger: activeLedger,
        });
      } else {
        const message =
          reconciled.error?.message ?? "对账无法判定执行状态，转人工，禁止重试";
        return failureOutcome(
          "unknown_execution",
          classifyFailure({ stage: "unknown_execution", code: "UNKNOWN_EXECUTION", message }),
          {
            policy,
            error: { code: "UNKNOWN_EXECUTION", message, retryable: false },
            costTotals: costResult.totals,
            lease: activeLease,
            ledger: activeLedger,
          },
        );
      }
    } else {
      const evidence = await deps.compute.reconcile(handle.handleId);
      if (evidence.ok && evidence.value.verdict === "executed") {
        handle = evidence.value.handle;
      } else {
        const message = evidence.ok ? evidence.value.reason : evidence.error.message;
        return failureOutcome(
          "unknown_execution",
          classifyFailure({ stage: "unknown_execution", code: "UNKNOWN_EXECUTION", message }),
          {
            policy,
            error: { code: "UNKNOWN_EXECUTION", message, retryable: false },
          },
        );
      }
    }
  }

  /* 6.1 释放与结算：任务结束后统一释放资源 */
  if (
    leaseEnabled &&
    ["succeeded", "failed", "cancelled"].includes(handle.state) &&
    activeLease &&
    activeLedger
  ) {
    const settled = await releaseLease(
      {
        lease: activeLease,
        ledger: activeLedger,
        handle,
        taskId: input.spec.task_id,
        reason: `run:${handle.state}`,
      },
      deps,
    );
    findings.push(...settled.findings);
    if (settled.ok) {
      activeLedger = settled.ledger;
      activeLease = settled.lease;
      await emitLeaseSignal(activeLease, "released", findings);
    }
  }

  /* 7. 收集产物 */
  if (handle.metrics && handle.metrics.length > 0) {
    const metricsJson = JSON.stringify(handle.metrics, null, 2);
    const put = await deps.artifacts.put({
      tenantId: input.subject.tenantId,
      key: `${attemptPrefix}/metrics.json`,
      contentType: "application/json",
      bytes: new TextEncoder().encode(metricsJson),
      expectedSha256: sha256(metricsJson),
      idempotencyKey: `${input.idempotencyKey}:metrics`,
    });
    if (put.ok) {
      storedArtifacts.push({ ref: put.value, type: "raw_result" });
      artifactsPresent.add("raw_metrics");
    } else {
      findings.push({
        severity: "warning",
        code: "W_METRICS_UPLOAD",
        message: `指标上传失败: ${put.error.code}`,
      });
    }
  }

  const logResult = await deps.compute.logs(handle.handleId, { maxBytes: 64 * 1024 });
  if (logResult.ok) {
    const logJson = JSON.stringify(logResult.value.lines, null, 2);
    const put = await deps.artifacts.put({
      tenantId: input.subject.tenantId,
      key: `${attemptPrefix}/logs.json`,
      contentType: "application/json",
      bytes: new TextEncoder().encode(logJson),
      expectedSha256: sha256(logJson),
      idempotencyKey: `${input.idempotencyKey}:logs`,
    });
    if (put.ok) {
      storedArtifacts.push({ ref: put.value, type: "log" });
      artifactsPresent.add("logs");
    }
  } else {
    findings.push({
      severity: "warning",
      code: "W_NO_LOGS",
      message: `获取日志失败: ${logResult.error.code}`,
    });
  }

  /** 供应商侧返回检查点时，把指针记录写入产物，供 planResume 恢复决策使用。 */
  let checkpointRecord: CheckpointRecord | undefined;
  if (handle.checkpointUri) {
    artifactsPresent.add("checkpoint");
    const record: CheckpointRecord = {
      checkpoint_id: `${runId}-checkpoint-1`,
      experiment_id: input.spec.experiment_id,
      attempt,
      uri: handle.checkpointUri,
      /* sha256 摘自检查点 URI；真实载荷哈希由存储侧 put 校验后代管。 */
      sha256: sha256(handle.checkpointUri),
      step: 0,
      created_at: now().toISOString(),
      code_commit: input.code.commit,
      environment_hash: input.environment.lockfileHash,
      valid: true,
    };
    const recordJson = JSON.stringify(record, null, 2);
    const recordPut = await deps.artifacts.put({
      tenantId: input.subject.tenantId,
      projectId: input.subject.projectId,
      key: checkpointArtifactKey(input.spec.experiment_id, attempt, record.checkpoint_id),
      contentType: "application/json",
      bytes: new TextEncoder().encode(recordJson),
      expectedSha256: sha256(recordJson),
      metadata: { task_id: input.spec.task_id, attempt: String(attempt) },
      idempotencyKey: `${input.idempotencyKey}:checkpoint-record`,
    });
    if (recordPut.ok) {
      storedArtifacts.push({ ref: recordPut.value, type: "checkpoint" });
      checkpointRecord = record;
    } else {
      findings.push({
        severity: "warning",
        code: "W_CHECKPOINT_RECORD",
        message: `检查点记录写入失败: ${recordPut.error.code} ${recordPut.error.message}`,
      });
    }
  }
  artifactsPresent.add("code_hash");
  artifactsPresent.add("env_lock");
  artifactsPresent.add("container_digest");

  /* 8. 计算观测 */
  const primaryMetric = handle.metrics?.find((metric) => metric.name === input.spec.metrics.primary);
  const baselineValue = input.spec.baseline.metric_value ?? 0;
  const primaryDelta =
    primaryMetric === undefined
      ? null
      : input.spec.metrics.direction === "minimize"
        ? baselineValue - primaryMetric.value
        : primaryMetric.value - baselineValue;

  const guardrailDegradations: Record<string, number> = {};
  for (const guardrail of input.spec.metrics.guardrails ?? []) {
    const observedMetric = handle.metrics?.find((metric) => metric.name === guardrail.name);
    const baselineGuardrail = input.baselineGuardrails?.[guardrail.name];
    if (!observedMetric || baselineGuardrail === undefined || baselineGuardrail === 0) {
      findings.push({
        severity: "warning",
        code: "W_GUARDRAIL_BASELINE",
        message: `护栏 ${guardrail.name} 缺少基线或观测值，按 0 退化处理`,
      });
      guardrailDegradations[guardrail.name] = 0;
      continue;
    }
    guardrailDegradations[guardrail.name] = Math.max(
      0,
      (observedMetric.value - baselineGuardrail) / Math.abs(baselineGuardrail),
    );
  }

  const seedValues = (handle.metrics ?? [])
    .filter((metric) => metric.name === input.spec.metrics.primary && metric.seed !== undefined)
    .map((metric) => metric.value);

  const decision = decide(input.spec, {
    primaryDelta,
    guardrailDegradations,
    seedValues: seedValues.length > 0 ? seedValues : undefined,
    cost: handle.usage?.cost ?? 0,
    currency: handle.usage?.currency ?? input.spec.resources.currency,
    artifactsPresent: Array.from(artifactsPresent),
    executionState:
      handle.state === "succeeded"
        ? "succeeded"
        : handle.state === "failed" || handle.state === "cancelled"
          ? "failed"
          : "partial",
  });

  /* 8.1 成本快照：启用租约时写入 costs.json 并并入产物清单 */
  let costTotals: CostTotals[] | undefined;
  if (activeLedger && activeLedger.entries.length > 0) {
    const costResult = await persistCostSnapshot(activeLedger);
    costTotals = costResult.totals;
    if (costResult.ref) storedArtifacts.push({ ref: costResult.ref, type: "report" });
  }

  /* 9. 运行清单 */
  const decisionFailure =
    decision.action === "keep"
      ? undefined
      : classifyFailure({
          stage: "decision",
          decision: decision.action,
          reasons: decision.reasons,
          message: decision.reasons.join("; ") || `决策 ${decision.action}`,
        });

  const manifest: RunManifest = {
    ...baseManifest(
      handle.state === "succeeded"
        ? "completed"
        : handle.state === "failed"
          ? "failed"
          : "partial",
      decisionFailure,
    ),
    resources: {
      handle_id: handle.handleId,
      type: input.spec.resources.type,
      count: input.spec.resources.count ?? 1,
      started_at: handle.startedAt ?? null,
      ended_at: handle.endedAt ?? null,
      cost: handle.usage?.cost ?? null,
      currency: handle.usage?.currency ?? input.spec.resources.currency,
    },
    metrics: (handle.metrics ?? []).map((metric) => ({
      name: metric.name,
      value: metric.value,
      seed: metric.seed ?? null,
      split: metric.split ?? null,
    })),
    artifacts: storedArtifacts.map((item) => toManifestArtifact(item.ref, item.type)),
    decision: {
      action: decision.action,
      reason: decision.reasons.join("; ") || "通过预注册规则",
      decided_by: "policy-engine",
      decided_at: now().toISOString(),
    },
    created_at: handle.submittedAt,
    finished_at: handle.endedAt ?? now().toISOString(),
  };

  const manifestRef = await persistManifest(manifest);

  trace("experiment.decided", {
    experiment_id: input.spec.experiment_id,
    action: decision.action,
    cost: handle.usage?.cost ?? 0,
  });

  if (deps.events) {
    await deps.events.publish({
      id: `${input.spec.experiment_id}:attempt-${attempt}:decided`,
      type: "experiment.decided.v1",
      source: "research-layer",
      tenantId: input.subject.tenantId,
      projectId: input.subject.projectId,
      resourceId: input.spec.experiment_id,
      time: now().toISOString(),
      dataContentType: "application/json",
      data: {
        action: decision.action,
        reasons: decision.reasons,
        attempt,
        run_id: runId,
      },
      traceId: input.traceId,
    });
  }

  const state: PipelineState =
    decision.action === "keep"
      ? "succeeded"
      : decision.action === "discard"
        ? "failed"
        : decision.action === "extend"
          ? "partial"
          : decision.action === "stop"
            ? "stopped"
            : "escalated";

  return {
    state,
    decision,
    policy,
    policyRecord: policyRecordRef ? policyRecord : undefined,
    policyRecordRef,
    manifest,
    manifestRef,
    failure: decisionFailure,
    findings,
    costTotals,
    lease: activeLease,
    ledger: activeLedger,
    checkpoint: checkpointRecord,
  };
}

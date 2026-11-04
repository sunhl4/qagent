/**
 * 租约编排：把领域租约状态机与三段成本账本接到 ComputePort。
 *
 * 本模块不实现云/HPC 适配器；资源由 harness-core 的 ComputePort 提供。
 * 负责：
 * - 准入预算检查与悲观预留。
 * - 提交前报价与成本上限校验。
 * - 提交、准备、激活状态同步。
 * - 释放资源后再结算实际成本与退回预留。
 */

import type {
  ComputePort,
  ReconcileEvidence,
  ResourceHandle,
  ResourceRequest,
} from "../../../contracts/src/index.ts";
import type {
  CostLedger,
  Finding,
  LeaseHolder,
  LeaseRecord,
} from "../../domain/src/index.ts";
import {
  checkBudget,
  createLease,
  isLeaseTerminal,
  leaseCostSummary,
  recordActualCost,
  recordLeaseHold,
  releaseCostReservation,
  reserveCost,
  transitionLease,
} from "../../domain/src/index.ts";

export interface LeaseOperationError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface LeaseDeps {
  compute: ComputePort;
  now?: () => Date;
}

export interface AcquireLeaseInput {
  request: ResourceRequest;
  holder: LeaseHolder;
  ttlSeconds: number;
  budget: { limit: number; currency: string };
  ledger: CostLedger;
  leaseId?: string;
  policyDecisionId?: string;
}

export interface ReleaseLeaseInput {
  lease: LeaseRecord;
  ledger: CostLedger;
  /** 关联任务，用于成本归因。 */
  taskId?: string | null;
  /** 已知的资源句柄；不提供时按租约记录中的 handle_id 重新查询状态。 */
  handle?: ResourceHandle;
  reason?: string;
}

export interface LeaseOperationResult {
  ok: boolean;
  lease?: LeaseRecord;
  ledger: CostLedger;
  handle?: ResourceHandle;
  findings: Finding[];
  error?: LeaseOperationError;
}

export type ReconcileAction = "settle" | "wait" | "resubmit" | "cancelled" | "escalate";

export interface ReconcileLeaseInput {
  lease: LeaseRecord;
  ledger: CostLedger;
  taskId?: string | null;
  handle?: ResourceHandle;
}

export interface ReconcileLeaseResult extends LeaseOperationResult {
  action: ReconcileAction;
  evidence?: ReconcileEvidence;
}

function finding(
  severity: "error" | "warning",
  code: string,
  message: string,
): Finding {
  return { severity, code, message };
}

function currencyOf(input: AcquireLeaseInput): string {
  return input.request.currency ?? input.budget.currency;
}

function markFailed(
  lease: LeaseRecord,
  at: Date,
  reason: string,
): LeaseRecord {
  const transitioned = transitionLease(lease, "fail", at, { reason });
  if (transitioned.ok) return transitioned.lease;
  return {
    ...lease,
    state: "FAILED",
    released_at: at.toISOString(),
    release_reason: reason,
    revision: (lease.revision ?? 1) + 1,
  };
}

function failResult(
  lease: LeaseRecord | undefined,
  ledger: CostLedger,
  findings: Finding[],
  error: LeaseOperationError,
  handle?: ResourceHandle,
): LeaseOperationResult {
  return { ok: false, lease, ledger, handle, findings, error };
}

/** ACTIVE 进入 DRAINING；其他非终态只记录 hold_reason，避免把未知执行当成可释放。 */
function noteUnknownHold(lease: LeaseRecord, at: Date): LeaseRecord {
  if (lease.state === "ACTIVE") {
    const draining = transitionLease(lease, "drain", at, {
      reason: "unknown_execution",
    });
    if (draining.ok) return draining.lease;
  }
  return recordLeaseHold(lease, "unknown_execution");
}

function syncLeaseFromHandle(
  lease: LeaseRecord,
  handle: ResourceHandle,
  at: Date,
): LeaseRecord {
  let next = lease;
  if (handle.state === "running" && next.state === "PREPARED") {
    const activated = transitionLease(next, "activate", at);
    if (activated.ok) next = activated.lease;
  } else if (
    (handle.state === "queued" || handle.state === "starting") &&
    next.state === "REQUESTED"
  ) {
    const prepared = transitionLease(next, "prepare", at);
    if (prepared.ok) next = prepared.lease;
  }
  return {
    ...next,
    resource: {
      ...next.resource,
      handle_id: handle.handleId,
      provider_resource_id: handle.providerResourceId ?? null,
      provider: "compute-port",
    },
    checkpoint_uri: handle.checkpointUri ?? next.checkpoint_uri ?? null,
  };
}

function refundUnusedReservation(
  lease: LeaseRecord,
  ledger: CostLedger,
  taskId: string | null,
  at: Date,
  source: string,
): { ledger: CostLedger; findings: Finding[] } {
  const unused = leaseCostSummary(ledger, lease.lease_id).unusedReservation;
  if (unused <= 0) return { ledger, findings: [] };
  const returned = releaseCostReservation(ledger, {
    leaseId: lease.lease_id,
    tenantId: lease.tenant_id,
    projectId: lease.project_id ?? null,
    taskId,
    currency: lease.cost?.currency ?? "CNY",
    amount: unused,
    at: at.toISOString(),
    source,
  });
  return {
    ledger: returned.ok ? returned.ledger : ledger,
    findings: returned.findings,
  };
}

/**
 * 申请并提交资源租约。
 *
 * 预留额按 `request.maxCost` 的悲观上界计算；没有 maxCost 时退回报价。
 * 提交失败会释放预留；UNKNOWN_EXECUTION 例外，保留预留等待人工对账。
 */
export async function acquireLease(
  input: AcquireLeaseInput,
  deps: LeaseDeps,
): Promise<LeaseOperationResult> {
  const now = deps.now ?? (() => new Date());
  const at = now();
  const currency = currencyOf(input);
  const findings: Finding[] = [];

  if (input.request.currency && input.request.currency !== input.budget.currency) {
    return failResult(undefined, input.ledger, findings, {
      code: "E_CURRENCY",
      message: `请求币种 ${input.request.currency} 与预算币种 ${input.budget.currency} 不一致`,
      retryable: false,
    });
  }

  const reservation = Math.max(0, input.request.maxCost ?? 0);
  const created = createLease({
    lease_id: input.leaseId ?? `${input.request.requestId}-lease`,
    tenant_id: input.request.tenantId,
    project_id: input.request.projectId ?? null,
    holder: input.holder,
    resource: {
      type: input.request.kind,
      count: input.request.count,
      accelerator: input.request.accelerator ?? null,
    },
    ttl_seconds: input.ttlSeconds,
    not_before: at.toISOString(),
    cost: { reserved: reservation, currency },
    constraints: {
      max_wall_clock_seconds: input.request.wallClockSeconds,
      no_internet: true,
      data_residency: input.request.dataResidency ?? null,
    },
    policy_decision_id: input.policyDecisionId ?? null,
    now: at,
  });

  if (!created.ok || !created.lease) {
    return failResult(created.lease, input.ledger, created.findings, {
      code: "E_LEASE_INVALID",
      message: "租约请求不合法",
      retryable: false,
    });
  }

  let lease = created.lease;
  let ledger = input.ledger;

  const quote = await deps.compute.quote(input.request);
  if (!quote.ok) {
    lease = markFailed(lease, at, `quote_failed:${quote.error.code}`);
    findings.push(
      finding("error", "E_LEASE_QUOTE", `报价失败: ${quote.error.code} ${quote.error.message}`),
    );
    return failResult(lease, ledger, findings, quote.error);
  }

  if (
    input.request.maxCost !== undefined &&
    typeof quote.value.estimatedCost === "number" &&
    quote.value.estimatedCost > input.request.maxCost
  ) {
    lease = markFailed(lease, at, "infeasible");
    findings.push(
      finding(
        "error",
        "E_LEASE_INFEASIBLE",
        `估计成本 ${quote.value.estimatedCost} 超过上限 ${input.request.maxCost}`,
      ),
    );
    return failResult(lease, ledger, findings, {
      code: "E_LEASE_INFEASIBLE",
      message: "报价超过成本上限",
      retryable: false,
    });
  }

  const effectiveReservation = Math.max(
    reservation,
    quote.value.estimatedCost ?? 0,
  );
  lease = {
    ...lease,
    cost: { ...(lease.cost ?? {}), reserved: effectiveReservation, currency },
  };

  const existingReservation = leaseCostSummary(ledger, lease.lease_id).reserved;
  const budget = checkBudget(
    ledger,
    {
      tenantId: input.request.tenantId,
      projectId: input.request.projectId,
      currency,
      limit: input.budget.limit,
    },
    existingReservation > 0 ? 0 : effectiveReservation,
  );
  findings.push(...budget.findings);
  if (!budget.ok) {
    lease = markFailed(lease, at, "budget_exceeded");
    return failResult(lease, ledger, findings, {
      code: "E_BUDGET_EXCEEDED",
      message: `预算不足，缺少 ${budget.overBy}`,
      retryable: false,
    });
  }

  if (effectiveReservation > 0) {
    const reserved = reserveCost(ledger, {
      leaseId: lease.lease_id,
      tenantId: input.request.tenantId,
      projectId: input.request.projectId ?? null,
      taskId: input.request.taskId ?? null,
      currency,
      amount: effectiveReservation,
      at: at.toISOString(),
      source: "lease.acquire",
    });
    findings.push(...reserved.findings);
    if (!reserved.ok) {
      lease = markFailed(lease, at, "reservation_failed");
      return failResult(lease, ledger, findings, {
        code: "E_COST_RESERVATION",
        message: "成本预留失败",
        retryable: false,
      });
    }
    ledger = reserved.ledger;
  }

  const submitted = await deps.compute.submit(input.request);
  if (!submitted.ok) {
    if (submitted.error.code !== "UNKNOWN_EXECUTION") {
      const released = releaseCostReservation(ledger, {
        leaseId: lease.lease_id,
        tenantId: input.request.tenantId,
        projectId: input.request.projectId ?? null,
        taskId: input.request.taskId ?? null,
        currency,
        amount: effectiveReservation,
        at: now().toISOString(),
        source: "lease.submit_failed",
      });
      if (released.ok) ledger = released.ledger;
      else findings.push(...released.findings);
      lease = markFailed(lease, at, `submit_failed:${submitted.error.code}`);
    } else {
      lease = markFailed(lease, at, "unknown_execution");
      findings.push(
        finding(
          "error",
          "E_LEASE_UNKNOWN_EXECUTION",
          "提交结果未知，保留预留并禁止自动重试",
        ),
      );
    }
    return failResult(lease, ledger, findings, submitted.error);
  }

  const handle = submitted.value;
  const prepared = transitionLease(lease, "prepare", at);
  if (prepared.ok) lease = prepared.lease;
  lease = syncLeaseFromHandle(lease, handle, at);

  return { ok: true, lease, ledger, handle, findings };
}

/**
 * 释放租约。
 *
 * 先确认资源释放成功，再记录实际成本与退回未使用预留；
 * 释放失败时保留账本，租约进入 DRAINING 以便重试。
 */
export async function releaseLease(
  input: ReleaseLeaseInput,
  deps: LeaseDeps,
): Promise<LeaseOperationResult> {
  const now = deps.now ?? (() => new Date());
  const at = now();
  const findings: Finding[] = [];
  let lease = input.lease;
  let ledger = input.ledger;

  if (lease.state === "RELEASED") {
    return { ok: true, lease, ledger, handle: input.handle, findings };
  }
  if (isLeaseTerminal(lease.state)) {
    findings.push(
      finding(
        "error",
        "E_LEASE_TERMINAL",
        `租约 ${lease.lease_id} 已处于终态 ${lease.state}，不能重复释放`,
      ),
    );
    return failResult(lease, ledger, findings, {
      code: "E_LEASE_TERMINAL",
      message: `终态 ${lease.state} 不能释放`,
      retryable: false,
    });
  }

  const handleId = input.handle?.handleId ?? lease.resource.handle_id ?? null;
  let handle = input.handle;

  if (!handle && handleId) {
    const status = await deps.compute.status(handleId);
    if (status.ok) {
      handle = status.value;
    } else {
      findings.push(
        finding(
          "warning",
          "W_LEASE_STATUS",
          `释放前查询状态失败: ${status.error.code} ${status.error.message}`,
        ),
      );
    }
  }

  if (handle?.state === "unknown") {
    const evidence = await deps.compute.reconcile(handle.handleId);
    if (!evidence.ok || evidence.value.verdict === "unknown") {
      lease = noteUnknownHold(lease, at);

      findings.push(
        finding(
          "error",
          "E_LEASE_UNKNOWN_EXECUTION",
          "执行状态未知，禁止释放结算；必须先人工对账",
        ),
      );
      return failResult(
        lease,
        ledger,
        findings,
        {
          code: "UNKNOWN_EXECUTION",
          message: evidence.ok ? evidence.value.reason : evidence.error.message,
          retryable: false,
        },
        handle,
      );
    }
    if (evidence.value.verdict === "executed") {
      handle = evidence.value.handle;
    } else if (
      evidence.value.verdict === "not_executed_confirmed" ||
      evidence.value.verdict === "cancelled_before_execution_confirmed"
    ) {
      handle = undefined;
    }
  }

  if (handleId) {
    const released = await deps.compute.release(handleId);
    if (!released.ok) {
      if (lease.state === "ACTIVE") {
        const draining = transitionLease(lease, "drain", at, {
          reason: `release_failed:${released.error.code}`,
        });
        if (draining.ok) lease = draining.lease;
        else lease = recordLeaseHold(lease, `release_failed:${released.error.code}`);
      } else {
        lease = recordLeaseHold(lease, `release_failed:${released.error.code}`);
      }
      findings.push(
        finding(
          "error",
          "E_LEASE_RELEASE",
          `资源释放失败: ${released.error.code} ${released.error.message}`,
        ),
      );
      return failResult(lease, ledger, findings, released.error, handle);
    }
  }

  const actual = handle?.usage?.cost ?? 0;
  if (actual > 0) {
    const recorded = recordActualCost(ledger, {
      leaseId: lease.lease_id,
      tenantId: lease.tenant_id,
      projectId: lease.project_id ?? null,
      taskId: input.taskId ?? null,
      currency: lease.cost?.currency ?? "CNY",
      amount: actual,
      at: now().toISOString(),
      source: "lease.release",
    });
    findings.push(...recorded.findings);
    if (recorded.ok) ledger = recorded.ledger;
  }

  const unused = refundUnusedReservation(
    lease,
    ledger,
    input.taskId ?? null,
    now(),
    "lease.release",
  );
  ledger = unused.ledger;
  findings.push(...unused.findings);

  const released = transitionLease(lease, "release", at, {
    reason: input.reason ?? "released",
  });
  if (!released.ok) {
    findings.push(...released.findings);
    return failResult(released.lease, ledger, findings, {
      code: "E_LEASE_TRANSITION",
      message: "租约状态无法迁移到 RELEASED",
      retryable: false,
    }, handle);
  }

  return { ok: true, lease: released.lease, ledger, handle, findings };
}

/**
 * 对账：未知执行、排队/运行中、已执行、确认未执行与取消。
 *
 * - `unknown` → 升级人工，保留预留，禁止重试。
 * - `queued_or_running` → 同步状态，继续等待。
 * - `executed` 且终态 → 释放资源并结算。
 * - `not_executed_confirmed` → 退回预留，标记失败，可安全重新提交。
 * - `cancelled_before_execution_confirmed` → 退回预留并撤销租约。
 */
export async function reconcileLease(
  input: ReconcileLeaseInput,
  deps: LeaseDeps,
): Promise<ReconcileLeaseResult> {
  const now = deps.now ?? (() => new Date());
  const at = now();
  let lease = input.lease;
  let ledger = input.ledger;
  const findings: Finding[] = [];

  if (lease.state === "RELEASED") {
    return { ok: true, action: "settle", lease, ledger, handle: input.handle, findings };
  }

  const handleId = input.handle?.handleId ?? lease.resource.handle_id ?? null;
  if (!handleId) {
    findings.push(
      finding("error", "E_LEASE_NO_HANDLE", "租约没有可对账的资源句柄"),
    );
    return {
      ok: false,
      action: "escalate",
      lease,
      ledger,
      findings,
      error: { code: "E_LEASE_NO_HANDLE", message: "缺少资源句柄", retryable: false },
    };
  }

  const evidenceResult = await deps.compute.reconcile(handleId);
  if (!evidenceResult.ok) {
    findings.push(
      finding(
        "error",
        "E_LEASE_RECONCILE",
        `对账失败: ${evidenceResult.error.code} ${evidenceResult.error.message}`,
      ),
    );
    return {
      ok: false,
      action: "escalate",
      lease,
      ledger,
      handle: input.handle,
      findings,
      error: evidenceResult.error,
    };
  }

  const evidence = evidenceResult.value;

  if (evidence.verdict === "unknown") {
    lease = noteUnknownHold(lease, at);
    findings.push(
      finding(
        "error",
        "E_LEASE_UNKNOWN_EXECUTION",
        "对账仍无法确认执行状态，保留预留并转人工",
      ),
    );
    return {
      ok: false,
      action: "escalate",
      lease,
      ledger,
      handle: input.handle,
      evidence,
      findings,
      error: {
        code: "UNKNOWN_EXECUTION",
        message: evidence.reason,
        retryable: false,
      },
    };
  }

  if (evidence.verdict === "queued_or_running") {
    lease = syncLeaseFromHandle(lease, evidence.handle, at);
    return {
      ok: true,
      action: "wait",
      lease,
      ledger,
      handle: evidence.handle,
      evidence,
      findings,
    };
  }

  if (evidence.verdict === "not_executed_confirmed") {
    const refund = refundUnusedReservation(
      lease,
      ledger,
      input.taskId ?? null,
      at,
      "lease.reconcile.not_executed",
    );
    ledger = refund.ledger;
    findings.push(...refund.findings);
    const failed = transitionLease(lease, "fail", at, {
      reason: `not_executed:${evidence.reason}`,
    });
    if (failed.ok) lease = failed.lease;
    return {
      ok: true,
      action: "resubmit",
      lease,
      ledger,
      handle: input.handle,
      evidence,
      findings,
    };
  }

  if (evidence.verdict === "cancelled_before_execution_confirmed") {
    const refund = refundUnusedReservation(
      lease,
      ledger,
      input.taskId ?? null,
      at,
      "lease.reconcile.cancelled",
    );
    ledger = refund.ledger;
    findings.push(...refund.findings);
    const revoked = transitionLease(lease, "revoke", at, {
      reason: "cancelled_before_execution",
    });
    if (revoked.ok) lease = revoked.lease;
    return {
      ok: true,
      action: "cancelled",
      lease,
      ledger,
      handle: input.handle,
      evidence,
      findings,
    };
  }

  /* executed */
  const handle = evidence.handle;
  if (
    handle.state === "succeeded" ||
    handle.state === "failed" ||
    handle.state === "cancelled"
  ) {
    const released = await releaseLease(
      {
        lease,
        ledger,
        handle,
        taskId: input.taskId ?? null,
        reason: `reconciled:${handle.state}`,
      },
      deps,
    );
    return { ...released, action: "settle", evidence };
  }

  if (handle.state === "unknown") {
    lease = noteUnknownHold(lease, at);
    findings.push(
      finding("error", "E_LEASE_UNKNOWN_EXECUTION", "对账返回 executed 但句柄仍为 unknown"),
    );
    return {
      ok: false,
      action: "escalate",
      lease,
      ledger,
      handle,
      evidence,
      findings,
      error: {
        code: "UNKNOWN_EXECUTION",
        message: "句柄状态未知，禁止自动重试",
        retryable: false,
      },
    };
  }

  lease = syncLeaseFromHandle(lease, handle, at);
  return {
    ok: true,
    action: "wait",
    lease,
    ledger,
    handle,
    evidence,
    findings,
  };
}

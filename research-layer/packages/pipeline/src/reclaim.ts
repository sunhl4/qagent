/**
 * 单次租约扫描：周期对账、过期回收、泄漏告警。
 *
 * 本模块不实现云/HPC 适配器，也不启动常驻循环。
 * 调用方（Temporal 或外部定时器）每次触发只跑一轮。
 *
 * - 窗口内的租约做一次对账；任务已结束则结算释放。
 * - 过期仍持有资源则释放。确认未执行时只记录“允许重提”，本轮不提交。
 * - 未知执行只告警和升级，不释放结算、不重新提交。
 * - 遥测失败不阻断回收。
 */

import type { ComputePort, TelemetryPort } from "../../../contracts/src/index.ts";
import type { CostLedger, Finding, LeaseRecord } from "../../domain/src/index.ts";
import {
  isLeaseTerminal,
  planReclaimSweep,
  resolveReclaimPolicy,
  transitionLease,
} from "../../domain/src/index.ts";
import type { ReclaimItem } from "../../domain/src/index.ts";
import { reconcileLease, releaseLease } from "./lease.ts";

export type SweepAction = ReclaimItem["action"] | "reconciled";

export interface ReclaimSweepItem {
  lease_id: string;
  action: SweepAction;
  alert: boolean;
  code: string;
  reason: string;
  lease_state: string;
}

export interface ReclaimSweepRecord {
  sweep_id: string;
  at: string;
  grace_seconds: number;
  alert_after_seconds: number;
  examined: number;
  reclaimed: number;
  expired: number;
  escalated: number;
  alerts: number;
  items: ReclaimSweepItem[];
}

export interface SweepLeasesInput {
  leases: LeaseRecord[];
  ledger: CostLedger;
  sweepId?: string;
  taskId?: string | null;
  graceSeconds?: number;
  alertAfterSeconds?: number;
  traceId?: string;
}

export interface SweepDeps {
  compute: ComputePort;
  telemetry?: TelemetryPort;
  now?: () => Date;
}

export interface SweepLeasesResult {
  ok: boolean;
  record: ReclaimSweepRecord;
  leases: LeaseRecord[];
  ledger: CostLedger;
  findings: Finding[];
}

function finding(
  severity: "error" | "warning",
  code: string,
  message: string,
): Finding {
  return { severity, code, message };
}

function withState(item: ReclaimItem, lease: LeaseRecord, patch: Partial<ReclaimSweepItem> = {}): ReclaimSweepItem {
  return {
    lease_id: item.lease_id,
    action: item.action,
    alert: item.alert,
    code: item.code,
    reason: item.reason,
    lease_state: lease.state,
    ...patch,
  };
}

async function emitLeak(
  deps: SweepDeps,
  lease: LeaseRecord,
  item: ReclaimSweepItem,
  at: Date,
  traceId: string,
  findings: Finding[],
): Promise<void> {
  if (!deps.telemetry || !item.alert) return;
  const result = await deps.telemetry.emit({
    name: "resource.leak",
    at: at.toISOString(),
    traceId,
    tenantId: lease.tenant_id,
    ...(lease.project_id ? { projectId: lease.project_id } : {}),
    redactionApplied: true,
    attributes: {
      lease_id: lease.lease_id,
      code: item.code,
      action: item.action,
      resource_type: lease.resource.type,
    },
    metrics: [
      {
        name: "resource_leak",
        value: 1,
        labels: { code: item.code, resource_type: lease.resource.type },
      },
    ],
  });
  if (!result.ok) {
    findings.push(
      finding("warning", "W_TELEMETRY", `泄漏告警未送达: ${result.error.code} ${result.error.message}`),
    );
  }
}

/**
 * 扫描一批租约。每个租约最多对账或释放一次，不会在函数内重试到成功。
 */
export async function sweepLeases(
  input: SweepLeasesInput,
  deps: SweepDeps,
): Promise<SweepLeasesResult> {
  const now = deps.now ?? (() => new Date());
  const at = now();
  const policy = resolveReclaimPolicy({
    graceSeconds: input.graceSeconds,
    alertAfterSeconds: input.alertAfterSeconds,
  });
  const plan = planReclaimSweep(input.leases, at, policy);
  const sweepId = input.sweepId ?? `reclaim-${at.toISOString()}`;
  const traceId = input.traceId ?? sweepId;
  let ledger = input.ledger;
  const findings: Finding[] = [];
  const byId = new Map(input.leases.map((lease) => [lease.lease_id, lease]));
  const items: ReclaimSweepItem[] = [];

  for (const planned of plan.items) {
    let lease = byId.get(planned.lease_id);
    if (!lease) continue;
    let item = withState(planned, lease);

    if (planned.action === "expire") {
      const expired = transitionLease(lease, "expire", at, { reason: planned.reason });
      findings.push(...expired.findings);
      lease = expired.lease;
      item = expired.ok
        ? withState(planned, lease)
        : withState(planned, lease, {
            action: "escalate",
            alert: true,
            code: "LEAK_DRAIN_UNCONFIRMED",
            reason: expired.findings[0]?.message ?? planned.reason,
          });
    } else if (planned.action === "reclaim") {
      const released = await releaseLease(
        {
          lease,
          ledger,
          taskId: input.taskId ?? null,
          reason: planned.reason,
        },
        deps,
      );
      ledger = released.ledger;
      findings.push(...released.findings);
      if (released.lease) lease = released.lease;
      if (!released.ok && released.error?.code === "UNKNOWN_EXECUTION") {
        item = withState(planned, lease, {
          action: "escalate",
          alert: true,
          code: "LEAK_UNKNOWN_EXECUTION",
          reason: released.error.message,
        });
      } else if (!released.ok) {
        item = withState(planned, lease, {
          action: "reclaim",
          alert: true,
          code: "LEAK_RELEASE_FAILED",
          reason: released.error?.message ?? planned.reason,
        });
      } else {
        item = withState(planned, lease);
      }
    } else if (
      planned.action === "keep" &&
      lease.resource.handle_id &&
      !isLeaseTerminal(lease.state)
    ) {
      const reconciled = await reconcileLease(
        { lease, ledger, taskId: input.taskId ?? null },
        deps,
      );
      ledger = reconciled.ledger;
      findings.push(...reconciled.findings);
      if (reconciled.lease) lease = reconciled.lease;
      if (!reconciled.ok) {
        item = withState(planned, lease, {
          action: reconciled.error?.code === "UNKNOWN_EXECUTION" ? "escalate" : "reclaim",
          alert: true,
          code:
            reconciled.error?.code === "UNKNOWN_EXECUTION"
              ? "LEAK_UNKNOWN_EXECUTION"
              : "LEAK_RELEASE_FAILED",
          reason: reconciled.error?.message ?? "周期对账失败",
        });
      } else if (reconciled.action === "wait") {
        item = withState(planned, lease, {
          action: "reconciled",
          alert: false,
          code: "RECONCILE_WAITING",
          reason: "周期对账：仍在排队或运行",
        });
      } else if (reconciled.action === "settle") {
        item = withState(planned, lease, {
          action: "reconciled",
          alert: false,
          code: "RECONCILE_SETTLED",
          reason: "周期对账：执行已结束并回收",
        });
      } else if (reconciled.action === "resubmit") {
        item = withState(planned, lease, {
          action: "reconciled",
          alert: false,
          code: "RECONCILE_RESUBMIT_ALLOWED",
          reason: "确认未执行，允许上层重新提交；本轮不提交",
        });
      } else if (reconciled.action === "cancelled") {
        item = withState(planned, lease, {
          action: "reconciled",
          alert: false,
          code: "RECONCILE_CANCELLED",
          reason: "确认执行前已取消",
        });
      } else {
        item = withState(planned, lease);
      }
    } else {
      item = withState(planned, lease);
    }

    byId.set(lease.lease_id, lease);
    items.push(item);
    await emitLeak(deps, lease, item, at, traceId, findings);
  }

  const record: ReclaimSweepRecord = {
    sweep_id: sweepId,
    at: at.toISOString(),
    grace_seconds: policy.graceSeconds,
    alert_after_seconds: policy.alertAfterSeconds,
    examined: items.length,
    reclaimed: items.filter((entry) => entry.action === "reclaim" && entry.lease_state === "RELEASED").length,
    expired: items.filter((entry) => entry.action === "expire" && entry.lease_state === "EXPIRED").length,
    escalated: items.filter((entry) => entry.action === "escalate").length,
    alerts: items.filter((entry) => entry.alert).length,
    items,
  };
  const unresolved = items.some(
    (entry) =>
      entry.action === "escalate" ||
      (entry.action === "reclaim" && entry.lease_state !== "RELEASED") ||
      (entry.action === "expire" && entry.lease_state !== "EXPIRED"),
  );

  return {
    ok: !unresolved,
    record,
    leases: input.leases.map((lease) => byId.get(lease.lease_id) ?? lease),
    ledger,
    findings,
  };
}

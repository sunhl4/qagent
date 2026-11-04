/**
 * 租约回收决策。
 *
 * 纯函数，不做 IO。一次调用只给出一份扫描计划，不循环等待。
 * 持久调度由 Temporal 或外部定时器触发；本模块不实现定时器。
 *
 * 规则：
 * - 仍在窗口或宽限内：保持，交给周期对账。
 * - 过期且没有资源句柄：就地过期。
 * - 过期仍持有资源：回收。超过告警时限才记为泄漏。
 * - 上次释放失败：立即补偿回收并告警。
 * - 未知执行或回收原因不明：升级人工，禁止自动释放和重新提交。
 */

import type { LeaseRecord, LeaseState } from "./lease.ts";

export type ReclaimAction = "keep" | "expire" | "reclaim" | "escalate";

export interface ReclaimPolicy {
  /** 过期后等待多久再回收，留给检查点落盘。默认 0 秒。 */
  graceSeconds?: number;
  /** 过期后仍持有资源超过该秒数则告警。默认 300 秒，对应 5 分钟释放目标。 */
  alertAfterSeconds?: number;
}

export interface ResolvedReclaimPolicy {
  graceSeconds: number;
  alertAfterSeconds: number;
}

export interface ReclaimItem {
  lease_id: string;
  action: ReclaimAction;
  alert: boolean;
  code: string;
  reason: string;
}

export interface ReclaimPlan {
  at: string;
  grace_seconds: number;
  alert_after_seconds: number;
  examined: number;
  items: ReclaimItem[];
}

const QUIET_TERMINAL: ReadonlySet<LeaseState> = new Set<LeaseState>([
  "RELEASED",
  "REVOKED",
  "EXPIRED",
]);

export function resolveReclaimPolicy(policy: ReclaimPolicy = {}): ResolvedReclaimPolicy {
  return {
    graceSeconds: nonNegative(policy.graceSeconds, 0),
    alertAfterSeconds: nonNegative(policy.alertAfterSeconds, 300),
  };
}

function nonNegative(value: number | undefined, fallback: number): number {
  if (value === undefined || !Number.isFinite(value) || value < 0) return fallback;
  return value;
}

function hasHandle(lease: LeaseRecord): boolean {
  return typeof lease.resource.handle_id === "string" && lease.resource.handle_id.length > 0;
}

function reasonText(lease: LeaseRecord): string {
  return `${lease.hold_reason ?? ""} ${lease.release_reason ?? ""}`;
}

function isUnknownHold(lease: LeaseRecord): boolean {
  const text = reasonText(lease);
  return text.includes("unknown_execution") || text.includes("UNKNOWN_EXECUTION");
}

function isReleaseFailureHold(lease: LeaseRecord): boolean {
  return (lease.hold_reason ?? "").startsWith("release_failed");
}

function item(
  lease: LeaseRecord,
  action: ReclaimAction,
  alert: boolean,
  code: string,
  reason: string,
): ReclaimItem {
  return { lease_id: lease.lease_id, action, alert, code, reason };
}

/**
 * 为一条租约决定本轮动作。不调用端口，也不修改租约。
 */
export function planLeaseReclaim(
  lease: LeaseRecord,
  at: Date,
  policy: ReclaimPolicy = {},
): ReclaimItem {
  const resolved = resolveReclaimPolicy(policy);

  if (QUIET_TERMINAL.has(lease.state)) {
    return item(lease, "keep", false, "LEASE_TERMINAL", "租约已结束");
  }
  if (isUnknownHold(lease)) {
    return item(
      lease,
      "escalate",
      true,
      "LEAK_UNKNOWN_EXECUTION",
      "执行状态未知，禁止自动回收或重新提交",
    );
  }
  if (isReleaseFailureHold(lease)) {
    return item(lease, "reclaim", true, "LEAK_RELEASE_FAILED", "上次回收失败，本轮补偿释放");
  }
  if (lease.state === "FAILED") {
    return item(lease, "keep", false, "LEASE_TERMINAL", "租约已失败结案");
  }
  if (lease.state === "DRAINING") {
    return item(
      lease,
      "escalate",
      true,
      "LEAK_DRAIN_UNCONFIRMED",
      "租约正在回收但原因未确认，禁止自动释放",
    );
  }

  const expiresAt = Date.parse(lease.expires_at);
  if (!Number.isFinite(expiresAt)) {
    return item(lease, "escalate", true, "LEASE_EXPIRY_INVALID", "租约过期时间无效");
  }

  const elapsedMs = at.getTime() - expiresAt;
  if (elapsedMs < 0) {
    return item(lease, "keep", false, "LEASE_HEALTHY", "仍在租约窗口内");
  }
  if (elapsedMs < resolved.graceSeconds * 1000) {
    return item(lease, "keep", false, "LEASE_IN_GRACE", "已过期，仍在回收宽限内");
  }

  const overdue = elapsedMs >= resolved.alertAfterSeconds * 1000;
  if (!hasHandle(lease)) {
    if (lease.state === "ACTIVE") {
      return item(
        lease,
        "expire",
        overdue,
        "LEAK_ACTIVE_WITHOUT_HANDLE",
        "ACTIVE 租约已过期且没有资源句柄",
      );
    }
    return item(lease, "expire", false, "LEASE_EXPIRED_NO_RESOURCE", "租约过期且未持有资源");
  }

  if (overdue) {
    return item(lease, "reclaim", true, "LEAK_HELD_AFTER_EXPIRY", "超过释放时限仍持有资源");
  }
  return item(lease, "reclaim", false, "RECLAIM_EXPIRED", "租约过期，自动回收");
}

/** 对一组租约各做一次决策，保持输入顺序。 */
export function planReclaimSweep(
  leases: readonly LeaseRecord[],
  at: Date,
  policy: ReclaimPolicy = {},
): ReclaimPlan {
  const resolved = resolveReclaimPolicy(policy);
  return {
    at: at.toISOString(),
    grace_seconds: resolved.graceSeconds,
    alert_after_seconds: resolved.alertAfterSeconds,
    examined: leases.length,
    items: leases.map((lease) => planLeaseReclaim(lease, at, resolved)),
  };
}

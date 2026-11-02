/**
 * 资源租约领域规则。
 *
 * 与 schemas/resource-lease.schema.json 对应。租约是短期的资源使用权，
 * 不是资源本身；本模块只做状态机、时间窗口、续租与可执行判定，不做 IO。
 *
 * 核心不变量：
 * - 只有 ACTIVE 且未过期的租约可以执行。
 * - 旧 fencing token 在续租后失效。
 * - 终态不可回退；重复释放幂等。
 * - 过期后不得再激活或执行。
 */

import type { Finding } from "./experiment.ts";

export type LeaseState =
  | "REQUESTED"
  | "PREPARED"
  | "ACTIVE"
  | "DRAINING"
  | "RELEASED"
  | "REVOKED"
  | "EXPIRED"
  | "FAILED";

export type LeaseEvent =
  | "prepare"
  | "activate"
  | "drain"
  | "release"
  | "revoke"
  | "expire"
  | "fail";

export type LeaseHolderType = "task" | "attempt" | "session" | "maintenance";

export type LeaseResourceType =
  | "cpu"
  | "gpu"
  | "hpc"
  | "qpu"
  | "cloud"
  | "browser"
  | "storage";

export interface LeaseHolder {
  type: LeaseHolderType;
  id: string;
}

export interface LeaseResource {
  type: LeaseResourceType;
  count: number;
  accelerator?: string | null;
  region?: string | null;
  provider?: string | null;
  provider_resource_id?: string | null;
  handle_id?: string | null;
}

export interface LeaseCost {
  reserved?: number;
  currency?: string;
  actual?: number | null;
}

export interface LeaseConstraints {
  max_wall_clock_seconds?: number | null;
  no_internet?: boolean;
  data_residency?: string | null;
}

export interface LeaseRecord {
  lease_id: string;
  tenant_id: string;
  project_id?: string | null;
  holder: LeaseHolder;
  resource: LeaseResource;
  state: LeaseState;
  not_before: string;
  expires_at: string;
  renewable_until?: string | null;
  fencing_token: number;
  cost?: LeaseCost;
  checkpoint_uri?: string | null;
  capabilities?: string[];
  constraints?: LeaseConstraints;
  created_at?: string;
  released_at?: string | null;
  release_reason?: string | null;
  /** 非终态上的暂停原因，例如 unknown_execution、release_failed。 */
  hold_reason?: string | null;
  policy_decision_id?: string | null;
  revision?: number;
}

export interface CreateLeaseInput {
  lease_id: string;
  tenant_id: string;
  project_id?: string | null;
  holder: LeaseHolder;
  resource: LeaseResource;
  ttl_seconds: number;
  not_before?: string | null;
  fencing_token?: number;
  renewable_until?: string | null;
  cost?: LeaseCost;
  checkpoint_uri?: string | null;
  capabilities?: string[];
  constraints?: LeaseConstraints;
  policy_decision_id?: string | null;
  now?: Date;
}

export interface LeaseCreationResult {
  ok: boolean;
  lease?: LeaseRecord;
  findings: Finding[];
}

export interface LeaseTransitionContext {
  reason?: string | null;
}

export interface LeaseTransitionResult {
  ok: boolean;
  lease: LeaseRecord;
  changed: boolean;
  findings: Finding[];
}

export interface RenewLeaseInput {
  expires_at: string;
  at?: Date;
  /** 续租后可用预算；用于重新评估，不修改账本。 */
  remainingBudget?: number;
  /** 本次续租预计新增成本。 */
  additionalCost?: number;
}

export interface LeaseRenewResult {
  ok: boolean;
  lease: LeaseRecord;
  changed: boolean;
  findings: Finding[];
}

export interface LeaseExecutionCheck {
  ok: boolean;
  reason?: string;
}

const TERMINAL_STATES: ReadonlySet<LeaseState> = new Set<LeaseState>([
  "RELEASED",
  "REVOKED",
  "EXPIRED",
  "FAILED",
]);

const TRANSITIONS: Readonly<
  Record<LeaseState, Partial<Record<LeaseEvent, LeaseState>>>
> = {
  REQUESTED: {
    prepare: "PREPARED",
    release: "RELEASED",
    revoke: "REVOKED",
    expire: "EXPIRED",
    fail: "FAILED",
  },
  PREPARED: {
    activate: "ACTIVE",
    release: "RELEASED",
    revoke: "REVOKED",
    expire: "EXPIRED",
    fail: "FAILED",
  },
  ACTIVE: {
    drain: "DRAINING",
    release: "RELEASED",
    revoke: "REVOKED",
    expire: "EXPIRED",
    fail: "FAILED",
  },
  DRAINING: {
    release: "RELEASED",
    fail: "FAILED",
  },
  RELEASED: {},
  REVOKED: {},
  EXPIRED: {},
  FAILED: {},
};

function isNonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function parseTime(value: string | null | undefined): number {
  if (!value) return Number.NaN;
  return Date.parse(value);
}

function finding(
  severity: "error" | "warning",
  code: string,
  message: string,
  path?: string,
): Finding {
  return { severity, code, message, path };
}

function withRevision(lease: LeaseRecord, next: Partial<LeaseRecord>): LeaseRecord {
  return {
    ...lease,
    ...next,
    revision: (lease.revision ?? 1) + 1,
  };
}

/**
 * 创建 REQUESTED 状态的租约记录。不分配资源，也不写账本。
 */
export function createLease(input: CreateLeaseInput): LeaseCreationResult {
  const findings: Finding[] = [];
  const now = input.now ?? new Date();

  if (!isNonEmpty(input.lease_id)) {
    findings.push(finding("error", "E_LEASE_ID", "lease_id 不能为空", "lease_id"));
  }
  if (!isNonEmpty(input.tenant_id)) {
    findings.push(finding("error", "E_LEASE_TENANT", "tenant_id 不能为空", "tenant_id"));
  }
  if (!isNonEmpty(input.holder?.id)) {
    findings.push(finding("error", "E_LEASE_HOLDER", "holder.id 不能为空", "holder.id"));
  }
  if (
    !Number.isFinite(input.resource?.count) ||
    !Number.isInteger(input.resource.count) ||
    input.resource.count < 1
  ) {
    findings.push(
      finding("error", "E_LEASE_RESOURCE", "resource.count 必须是大于 0 的整数", "resource.count"),
    );
  }
  if (!Number.isFinite(input.ttl_seconds) || input.ttl_seconds <= 0) {
    findings.push(finding("error", "E_LEASE_TTL", "ttl_seconds 必须大于 0", "ttl_seconds"));
  }
  const fencingToken = input.fencing_token ?? 1;
  if (!Number.isInteger(fencingToken) || fencingToken < 1) {
    findings.push(
      finding("error", "E_LEASE_FENCING", "fencing_token 必须是大于 0 的整数", "fencing_token"),
    );
  }
  if (
    input.cost?.reserved !== undefined &&
    (!Number.isFinite(input.cost.reserved) || input.cost.reserved < 0)
  ) {
    findings.push(finding("error", "E_LEASE_COST", "cost.reserved 不能为负", "cost.reserved"));
  }
  if (
    input.cost?.reserved !== undefined &&
    (!input.cost.currency || input.cost.currency.length !== 3)
  ) {
    findings.push(
      finding("error", "E_LEASE_CURRENCY", "预留成本必须提供三位币种", "cost.currency"),
    );
  }

  const notBefore = input.not_before ? new Date(input.not_before) : now;
  if (Number.isNaN(notBefore.getTime())) {
    findings.push(
      finding("error", "E_LEASE_NOT_BEFORE", "not_before 不是合法时间", "not_before"),
    );
  }

  if (findings.some((item) => item.severity === "error")) {
    return { ok: false, findings };
  }

  const expiresAt = new Date(notBefore.getTime() + input.ttl_seconds * 1000);
  const lease: LeaseRecord = {
    lease_id: input.lease_id,
    tenant_id: input.tenant_id,
    project_id: input.project_id ?? null,
    holder: input.holder,
    resource: input.resource,
    state: "REQUESTED",
    not_before: notBefore.toISOString(),
    expires_at: expiresAt.toISOString(),
    renewable_until: input.renewable_until ?? null,
    fencing_token: fencingToken,
    ...(input.cost ? { cost: input.cost } : {}),
    checkpoint_uri: input.checkpoint_uri ?? null,
    capabilities: input.capabilities ?? [],
    ...(input.constraints ? { constraints: input.constraints } : {}),
    created_at: now.toISOString(),
    released_at: null,
    release_reason: null,
    policy_decision_id: input.policy_decision_id ?? null,
    revision: 1,
  };

  return { ok: true, lease, findings };
}

/**
 * 按事件迁移租约状态。
 *
 * 重复释放是幂等成功；终态的其他事件返回错误且不改变租约。
 */
export function transitionLease(
  lease: LeaseRecord,
  event: LeaseEvent,
  at: Date = new Date(),
  context: LeaseTransitionContext = {},
): LeaseTransitionResult {
  const findings: Finding[] = [];

  if (TERMINAL_STATES.has(lease.state)) {
    if (event === "release" && lease.state === "RELEASED") {
      return { ok: true, lease, changed: false, findings };
    }
    findings.push(
      finding(
        "error",
        "E_LEASE_TERMINAL",
        `租约 ${lease.lease_id} 已处于终态 ${lease.state}，不允许事件 ${event}`,
      ),
    );
    return { ok: false, lease, changed: false, findings };
  }

  if (event === "activate") {
    if (at.getTime() < parseTime(lease.not_before)) {
      findings.push(
        finding("error", "E_LEASE_NOT_YET_VALID", `租约 ${lease.lease_id} 尚未生效`),
      );
      return { ok: false, lease, changed: false, findings };
    }
    if (at.getTime() >= parseTime(lease.expires_at)) {
      findings.push(finding("error", "E_LEASE_EXPIRED", `租约 ${lease.lease_id} 已过期`));
      return { ok: false, lease, changed: false, findings };
    }
  }

  if (event === "expire" && at.getTime() < parseTime(lease.expires_at)) {
    findings.push(
      finding("error", "E_LEASE_NOT_EXPIRED", `租约 ${lease.lease_id} 尚未到期`),
    );
    return { ok: false, lease, changed: false, findings };
  }

  const nextState = TRANSITIONS[lease.state][event];
  if (!nextState) {
    findings.push(
      finding(
        "error",
        "E_LEASE_TRANSITION",
        `租约状态 ${lease.state} 不允许事件 ${event}`,
      ),
    );
    return { ok: false, lease, changed: false, findings };
  }

  if (nextState === lease.state) {
    return { ok: true, lease, changed: false, findings };
  }

  const terminalPatch =
    nextState === "RELEASED" ||
    nextState === "REVOKED" ||
    nextState === "EXPIRED" ||
    nextState === "FAILED"
      ? {
          released_at: at.toISOString(),
          release_reason: context.reason ?? null,
        }
      : {};
  const holdPatch =
    event === "drain"
      ? { hold_reason: context.reason ?? lease.hold_reason ?? null }
      : nextState === "RELEASED"
        ? { hold_reason: null }
        : {};

  return {
    ok: true,
    lease: withRevision(lease, { state: nextState, ...terminalPatch, ...holdPatch }),
    changed: true,
    findings,
  };
}

/**
 * 续租：延长过期时间并提升 fencing token，使旧 token 失效。
 *
 * 续租必须重新评估预算；本函数只做检查，账本变更由调用方完成。
 */
export function renewLease(
  lease: LeaseRecord,
  input: RenewLeaseInput,
): LeaseRenewResult {
  const findings: Finding[] = [];
  const at = input.at ?? new Date();

  if (lease.state !== "PREPARED" && lease.state !== "ACTIVE") {
    findings.push(
      finding("error", "E_LEASE_RENEW_TERMINAL", `状态 ${lease.state} 的租约不能续租`),
    );
    return { ok: false, lease, changed: false, findings };
  }

  const newExpiry = parseTime(input.expires_at);
  const currentExpiry = parseTime(lease.expires_at);
  if (Number.isNaN(newExpiry) || newExpiry <= at.getTime()) {
    findings.push(
      finding("error", "E_LEASE_RENEW_EXPIRY", "新过期时间必须晚于当前时间", "expires_at"),
    );
  }
  if (newExpiry <= currentExpiry) {
    findings.push(
      finding("error", "E_LEASE_RENEW_EXPIRY", "新过期时间必须晚于当前过期时间", "expires_at"),
    );
  }
  if (at.getTime() >= currentExpiry) {
    findings.push(
      finding("error", "E_LEASE_EXPIRED", "租约已过期，不能续租", "expires_at"),
    );
  }
  if (lease.renewable_until) {
    const renewableUntil = parseTime(lease.renewable_until);
    if (newExpiry > renewableUntil) {
      findings.push(
        finding("error", "E_LEASE_RENEW_LIMIT", "续租超过 renewable_until", "renewable_until"),
      );
    }
  }
  if (
    typeof input.remainingBudget === "number" &&
    typeof input.additionalCost === "number" &&
    input.additionalCost > input.remainingBudget
  ) {
    findings.push(
      finding(
        "error",
        "E_LEASE_BUDGET",
        `续租成本 ${input.additionalCost} 超过剩余预算 ${input.remainingBudget}`,
      ),
    );
  }

  if (findings.some((item) => item.severity === "error")) {
    return { ok: false, lease, changed: false, findings };
  }

  return {
    ok: true,
    lease: withRevision(lease, {
      expires_at: input.expires_at,
      fencing_token: lease.fencing_token + 1,
    }),
    changed: true,
    findings,
  };
}

/**
 * 判定租约当前是否允许执行。
 */
export function canExecuteLease(lease: LeaseRecord, at: Date = new Date()): LeaseExecutionCheck {
  if (lease.state !== "ACTIVE") {
    return { ok: false, reason: `租约状态为 ${lease.state}，只有 ACTIVE 可以执行` };
  }
  const notBefore = parseTime(lease.not_before);
  const expiresAt = parseTime(lease.expires_at);
  if (!Number.isFinite(notBefore) || !Number.isFinite(expiresAt)) {
    return { ok: false, reason: "租约时间窗口无效" };
  }
  if (at.getTime() < notBefore) {
    return { ok: false, reason: "租约尚未生效" };
  }
  if (at.getTime() >= expiresAt) {
    return { ok: false, reason: "租约已过期" };
  }
  return { ok: true };
}

export function isLeaseTerminal(state: LeaseState): boolean {
  return TERMINAL_STATES.has(state);
}

/**
 * 在不改变状态的前提下记录暂停原因。
 *
 * 未知执行发生在尚未 ACTIVE 的租约上时，状态机没有 drain 边，
 * 但仍必须记住“禁止自动释放和重试”。终态不修改。
 */
export function recordLeaseHold(lease: LeaseRecord, reason: string): LeaseRecord {
  if (isLeaseTerminal(lease.state)) return lease;
  if (!reason.trim() || lease.hold_reason === reason) return lease;
  return withRevision(lease, { hold_reason: reason });
}

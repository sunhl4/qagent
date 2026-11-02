/**
 * 三段成本账本：预留（admission）→ 实际（execution）→ 释放（completion）。
 *
 * 与 docs/06 的成本控制规则对应。本模块是纯函数，不做 IO：
 * - 准入时按悲观上界预留。
 * - 执行结束记录实际成本，并释放未使用预留。
 * - 预算检查按“净预留 + 实际”计算已承诺成本。
 * - 条目 ID 确定性去重，保证重试不会重复计费。
 */

import type { Finding } from "./experiment.ts";

export type CostEntryKind = "reserve" | "actual" | "release";

export interface CostEntry {
  entry_id: string;
  kind: CostEntryKind;
  tenant_id: string;
  project_id?: string | null;
  task_id?: string | null;
  lease_id?: string | null;
  currency: string;
  amount: number;
  at: string;
  source?: string | null;
}

export interface CostLedger {
  entries: CostEntry[];
}

export interface CostFilter {
  tenantId?: string;
  projectId?: string;
  taskId?: string;
  leaseId?: string;
  currency?: string;
}

export interface CostTotals {
  currency: string;
  reserved: number;
  actual: number;
  released: number;
  /** 已承诺成本 = max(实际, 净预留)；净预留 = reserved - released。 */
  committed: number;
  entries: number;
}

export interface CostLedgerSnapshot {
  entries: CostEntry[];
  totals: CostTotals[];
}

export interface CostMutationResult {
  ok: boolean;
  ledger: CostLedger;
  entry?: CostEntry;
  duplicate: boolean;
  findings: Finding[];
}

export interface LeaseCostInput {
  leaseId: string;
  tenantId: string;
  projectId?: string | null;
  taskId?: string | null;
  currency: string;
  amount: number;
  at?: string;
  source?: string | null;
}

export interface BudgetScope extends CostFilter {
  currency: string;
  limit: number;
}

export interface BudgetStatus {
  ok: boolean;
  currency: string;
  limit: number;
  reserved: number;
  actual: number;
  released: number;
  committed: number;
  additionalReservation: number;
  remaining: number;
  overBy: number;
  findings: Finding[];
}

export interface LeaseCostSummary {
  leaseId: string;
  reserved: number;
  actual: number;
  released: number;
  /** 尚未使用、应释放的预留额度。 */
  unusedReservation: number;
}

const SCALE = 100_000_000;

function roundAmount(value: number): number {
  return Math.round(value * SCALE) / SCALE;
}

function finding(
  severity: "error" | "warning",
  code: string,
  message: string,
  path?: string,
): Finding {
  return { severity, code, message, path };
}

function isNonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function matches(entry: CostEntry, filter: CostFilter): boolean {
  if (filter.tenantId && entry.tenant_id !== filter.tenantId) return false;
  if (filter.projectId && (entry.project_id ?? null) !== filter.projectId) return false;
  if (filter.taskId && (entry.task_id ?? null) !== filter.taskId) return false;
  if (filter.leaseId && (entry.lease_id ?? null) !== filter.leaseId) return false;
  if (filter.currency && entry.currency !== filter.currency) return false;
  return true;
}

function sameEntry(left: CostEntry, right: CostEntry): boolean {
  return (
    left.kind === right.kind &&
    left.tenant_id === right.tenant_id &&
    (left.project_id ?? null) === (right.project_id ?? null) &&
    (left.task_id ?? null) === (right.task_id ?? null) &&
    (left.lease_id ?? null) === (right.lease_id ?? null) &&
    left.currency === right.currency &&
    left.amount === right.amount &&
    (left.source ?? null) === (right.source ?? null)
  );
}

export function emptyCostLedger(): CostLedger {
  return { entries: [] };
}

/**
 * 追加账本条目。相同 entry_id 且内容一致时幂等返回；内容不一致时报冲突。
 */
export function appendCostEntry(
  ledger: CostLedger,
  entry: CostEntry,
): CostMutationResult {
  const findings: Finding[] = [];

  if (!isNonEmpty(entry.entry_id)) {
    findings.push(finding("error", "E_COST_ENTRY_ID", "entry_id 不能为空", "entry_id"));
  }
  if (!isNonEmpty(entry.tenant_id)) {
    findings.push(finding("error", "E_COST_TENANT", "tenant_id 不能为空", "tenant_id"));
  }
  if (entry.kind !== "reserve" && entry.kind !== "actual" && entry.kind !== "release") {
    findings.push(finding("error", "E_COST_KIND", "kind 非法", "kind"));
  }
  if (!isNonEmpty(entry.currency) || entry.currency.length !== 3) {
    findings.push(finding("error", "E_COST_CURRENCY", "currency 必须是三位代码", "currency"));
  }
  if (!Number.isFinite(entry.amount) || entry.amount < 0) {
    findings.push(finding("error", "E_COST_AMOUNT", "amount 必须是非负数", "amount"));
  }
  if (!isNonEmpty(entry.at) || Number.isNaN(Date.parse(entry.at))) {
    findings.push(finding("error", "E_COST_TIME", "at 必须是合法时间", "at"));
  }

  if (findings.some((item) => item.severity === "error")) {
    return { ok: false, ledger, duplicate: false, findings };
  }

  const existing = ledger.entries.find((item) => item.entry_id === entry.entry_id);
  if (existing) {
    if (sameEntry(existing, entry)) {
      return { ok: true, ledger, entry: existing, duplicate: true, findings };
    }
    findings.push(
      finding(
        "error",
        "E_COST_DUPLICATE_CONFLICT",
        `entry_id ${entry.entry_id} 已存在且内容不同`,
        "entry_id",
      ),
    );
    return { ok: false, ledger, duplicate: true, findings };
  }

  return {
    ok: true,
    ledger: { entries: [...ledger.entries, entry] },
    entry,
    duplicate: false,
    findings,
  };
}

function leaseEntryId(leaseId: string, kind: CostEntryKind): string {
  return `lease:${leaseId}:${kind}`;
}

function buildLeaseEntry(
  input: LeaseCostInput,
  kind: CostEntryKind,
): CostEntry {
  return {
    entry_id: leaseEntryId(input.leaseId, kind),
    kind,
    tenant_id: input.tenantId,
    project_id: input.projectId ?? null,
    task_id: input.taskId ?? null,
    lease_id: input.leaseId,
    currency: input.currency,
    amount: roundAmount(input.amount),
    at: input.at ?? new Date().toISOString(),
    source: input.source ?? "lease-manager",
  };
}

export function reserveCost(ledger: CostLedger, input: LeaseCostInput): CostMutationResult {
  return appendCostEntry(ledger, buildLeaseEntry(input, "reserve"));
}

export function recordActualCost(ledger: CostLedger, input: LeaseCostInput): CostMutationResult {
  return appendCostEntry(ledger, buildLeaseEntry(input, "actual"));
}

export function releaseCostReservation(
  ledger: CostLedger,
  input: LeaseCostInput,
): CostMutationResult {
  return appendCostEntry(ledger, buildLeaseEntry(input, "release"));
}

/**
 * 汇总账本。只统计与过滤条件匹配的条目，按币种分组。
 */
export function summarizeCost(ledger: CostLedger, filter: CostFilter = {}): CostTotals[] {
  const groups = new Map<string, CostTotals>();

  for (const entry of ledger.entries) {
    if (!matches(entry, filter)) continue;
    const totals = groups.get(entry.currency) ?? {
      currency: entry.currency,
      reserved: 0,
      actual: 0,
      released: 0,
      committed: 0,
      entries: 0,
    };
    if (entry.kind === "reserve") totals.reserved += entry.amount;
    else if (entry.kind === "actual") totals.actual += entry.amount;
    else totals.released += entry.amount;
    totals.entries += 1;
    groups.set(entry.currency, totals);
  }

  return [...groups.values()]
    .map((totals) => {
      const reserved = roundAmount(totals.reserved);
      const actual = roundAmount(totals.actual);
      const released = roundAmount(totals.released);
      const netReserved = roundAmount(reserved - released);
      return {
        ...totals,
        reserved,
        actual,
        released,
        committed: roundAmount(Math.max(actual, netReserved)),
      };
    })
    .sort((left, right) => left.currency.localeCompare(right.currency));
}

/**
 * 预算检查。committed 包含已有净预留与实际，additionalReservation 是本次拟新增的预留。
 */
export function checkBudget(
  ledger: CostLedger,
  scope: BudgetScope,
  additionalReservation = 0,
): BudgetStatus {
  const findings: Finding[] = [];
  if (!Number.isFinite(scope.limit) || scope.limit < 0) {
    findings.push(finding("error", "E_BUDGET_INVALID", "预算上限必须是非负数"));
  }
  if (!Number.isFinite(additionalReservation) || additionalReservation < 0) {
    findings.push(
      finding("error", "E_BUDGET_RESERVATION", "新增预留必须是非负数"),
    );
  }
  if (!isNonEmpty(scope.currency) || scope.currency.length !== 3) {
    findings.push(finding("error", "E_BUDGET_CURRENCY", "币种必须是三位代码"));
  }

  const totals = summarizeCost(ledger, {
    tenantId: scope.tenantId,
    projectId: scope.projectId,
    taskId: scope.taskId,
    leaseId: scope.leaseId,
    currency: scope.currency,
  }).find((item) => item.currency === scope.currency);

  const committed = totals?.committed ?? 0;
  const projected = roundAmount(committed + additionalReservation);
  const remaining = roundAmount(scope.limit - projected);
  const overBy = remaining < 0 ? roundAmount(-remaining) : 0;

  if (overBy > 0) {
    findings.push(
      finding(
        "error",
        "E_BUDGET_EXCEEDED",
        `已承诺 ${committed} + 本次预留 ${additionalReservation} 超过预算 ${scope.limit}，超出 ${overBy}`,
      ),
    );
  }

  return {
    ok: !findings.some((item) => item.severity === "error"),
    currency: scope.currency,
    limit: scope.limit,
    reserved: totals?.reserved ?? 0,
    actual: totals?.actual ?? 0,
    released: totals?.released ?? 0,
    committed,
    additionalReservation,
    remaining,
    overBy,
    findings,
  };
}

/**
 * 单个租约的成本汇总，用于计算释放时应退回的预留额度。
 */
export function leaseCostSummary(ledger: CostLedger, leaseId: string): LeaseCostSummary {
  let reserved = 0;
  let actual = 0;
  let released = 0;
  for (const entry of ledger.entries) {
    if ((entry.lease_id ?? null) !== leaseId) continue;
    if (entry.kind === "reserve") reserved += entry.amount;
    else if (entry.kind === "actual") actual += entry.amount;
    else released += entry.amount;
  }
  const roundedReserved = roundAmount(reserved);
  const roundedActual = roundAmount(actual);
  const roundedReleased = roundAmount(released);
  return {
    leaseId,
    reserved: roundedReserved,
    actual: roundedActual,
    released: roundedReleased,
    unusedReservation: Math.max(
      0,
      roundAmount(roundedReserved - roundedActual - roundedReleased),
    ),
  };
}

/**
 * 生成可持久化、可校验的账本快照。
 */
export function buildCostLedgerSnapshot(
  ledger: CostLedger,
  filter: CostFilter = {},
): CostLedgerSnapshot {
  return {
    entries: ledger.entries.filter((entry) => matches(entry, filter)),
    totals: summarizeCost(ledger, filter),
  };
}

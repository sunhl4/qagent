/**
 * 策略引擎：本工程侧的服务端策略判断。
 *
 * harness-core 提供身份、配额、模型与资源；本工程负责“这个研究动作是否允许”。
 * 两边都必须在服务端执行，不能靠提示词。
 */

import type { DataClass } from "../../../contracts/src/index.ts";

export type Risk = "low" | "medium" | "high" | "critical";
export type PolicyDecisionKind =
  | "ALLOW"
  | "DENY"
  | "REQUIRE_APPROVAL"
  | "ALLOW_WITH_LIMIT"
  | "DEFER";

export interface PolicyAction {
  name: string;
  risk: Risk;
  targetType?: string;
  targetId?: string;
  estimatedCost?: number;
  currency?: string;
  irreversible?: boolean;
  dataClass?: DataClass;
  /** 外部模型/服务的驻留地；用于数据合规判断。 */
  residency?: string;
  requiredResidency?: string;
  /** 是否是“执行状态未知后的重试尝试”。 */
  retryAfterUnknown?: boolean;
  /** 是否写入主分支或生产。 */
  writesProduction?: boolean;
}

export interface PolicySubject {
  type: "user" | "service" | "agent";
  id: string;
  tenantId: string;
}

export interface PolicyContext {
  subject: PolicySubject;
  /** 剩余预算；未提供表示不限制。 */
  remainingBudget?: number;
  currency?: string;
  approvalId?: string;
  /** 已批准的动作名；用于核验审批范围。 */
  approvedActions?: string[];
}

export interface PolicyRuleMatch {
  ruleId: string;
  effect: "allow" | "deny" | "require_approval" | "limit";
  detail?: string;
}

export interface PolicyResult {
  decision: PolicyDecisionKind;
  reason: string;
  matchedRules: PolicyRuleMatch[];
  limits?: {
    maxCost?: number;
    maxWallClockSeconds?: number;
    maxGpuCount?: number;
  };
}

const RISK_ORDER: Record<Risk, number> = {
  low: 0,
  medium: 1,
  high: 2,
  critical: 3,
};

/**
 * 规则顺序即优先级：先命中 deny / unknown-retry，再命中审批。
 */
export function evaluatePolicy(action: PolicyAction, ctx: PolicyContext): PolicyResult {
  const matched: PolicyRuleMatch[] = [];

  /* 1. 未知执行不得重试 */
  if (action.retryAfterUnknown) {
    matched.push({ ruleId: "R-UNKNOWN-NO-RETRY", effect: "deny" });
    return {
      decision: "DENY",
      reason: "执行状态未知时禁止自动重试，必须先人工对账",
      matchedRules: matched,
    };
  }

  /* 2. Agent 不得任意出网 */
  if (action.name === "network.internet" && ctx.subject.type === "agent") {
    matched.push({ ruleId: "R-AGENT-NO-INTERNET", effect: "deny" });
    return {
      decision: "DENY",
      reason: "Agent 默认无外网权限；需要外部数据时必须走受控工具",
      matchedRules: matched,
    };
  }

  /* 3. 数据等级与驻留 */
  if (action.dataClass === "restricted" && action.residency !== action.requiredResidency) {
    matched.push({
      ruleId: "R-DATA-RESIDENCY",
      effect: "deny",
      detail: `restricted 数据要求驻留 ${action.requiredResidency ?? "on_prem"}，实际 ${action.residency ?? "unknown"}`,
    });
    return {
      decision: "DENY",
      reason: "受限数据不能离开要求的驻留地",
      matchedRules: matched,
    };
  }

  /* 4. 预算 */
  if (
    typeof action.estimatedCost === "number" &&
    typeof ctx.remainingBudget === "number" &&
    action.estimatedCost > ctx.remainingBudget
  ) {
    matched.push({ ruleId: "R-BUDGET", effect: "deny" });
    return {
      decision: "DENY",
      reason: `估计成本 ${action.estimatedCost} 超过剩余预算 ${ctx.remainingBudget}`,
      matchedRules: matched,
    };
  }

  /* 5. 真实设备 / 生产写入 / 不可逆动作 */
  const needsApproval: string[] = [];
  if (action.targetType === "qpu") {
    needsApproval.push("R-QPU-APPROVAL");
  }
  if (action.writesProduction) {
    needsApproval.push("R-PRODUCTION-APPROVAL");
  }
  if (action.irreversible) {
    needsApproval.push("R-IRREVERSIBLE-APPROVAL");
  }
  if (RISK_ORDER[action.risk] >= RISK_ORDER.high) {
    needsApproval.push("R-RISK-APPROVAL");
  }

  const approved = ctx.approvedActions?.includes(action.name) ?? false;
  if (needsApproval.length > 0 && !approved) {
    for (const ruleId of needsApproval) {
      matched.push({ ruleId, effect: "require_approval" });
    }
    return {
      decision: "REQUIRE_APPROVAL",
      reason: `动作 ${action.name} 需要人工审批`,
      matchedRules: matched,
    };
  }

  /* 6. 高风险即使已批准也要限额 */
  if (needsApproval.length > 0 && approved) {
    matched.push({ ruleId: "R-APPROVED-LIMIT", effect: "limit" });
    return {
      decision: "ALLOW_WITH_LIMIT",
      reason: "已批准，但按高风险限额执行",
      matchedRules: matched,
      limits: {
        maxCost: action.estimatedCost,
        maxWallClockSeconds: 3600,
      },
    };
  }

  /* 7. 中等风险且缺少审批上下文 → 延迟到人工确认 */
  if (RISK_ORDER[action.risk] === RISK_ORDER.medium && !ctx.approvalId && action.irreversible) {
    matched.push({ ruleId: "R-MEDIUM-IRREVERSIBLE", effect: "require_approval" });
    return {
      decision: "REQUIRE_APPROVAL",
      reason: "中等风险但不可逆，需确认",
      matchedRules: matched,
    };
  }

  matched.push({ ruleId: "R-DEFAULT-ALLOW", effect: "allow" });
  return {
    decision: "ALLOW",
    reason: "未命中拒绝或审批规则",
    matchedRules: matched,
  };
}

/**
 * 策略决定记录（schemas/policy-decision.schema.json）。
 *
 * `evaluatePolicy()` 只返回判定；审计与审批流需要一份可持久化、可校验的记录。
 * 本函数是纯映射：多给的字符串键一律丢弃，保证不携带凭据类字段。
 */

export interface PolicyDecisionRecord {
  decision_id: string;
  subject: {
    type: "user" | "service" | "agent" | "operator";
    id: string;
    tenant_id: string;
    project_id: string | null;
  };
  action: {
    name: string;
    risk: "low" | "medium" | "high" | "critical";
    target_type: string | null;
    target_id: string | null;
    reversible: boolean;
    estimated_cost: number | null;
    currency: string | null;
  };
  decision: PolicyDecisionKind;
  reason: string;
  matched_rules: PolicyRuleMatch[];
  limits: {
    max_cost: number | null;
    max_wall_clock_seconds: number | null;
    max_gpu_count: number | null;
  };
  approval: {
    required_by: string[];
    approval_id: string | null;
    expires_at: string | null;
    scope: string | null;
  };
  evaluated_at: string;
  trace_id: string | null;
}

export interface PolicyDecisionActionDetail {
  name: string;
  target_type?: string | null;
  target_id?: string | null;
  reversible?: boolean;
  estimated_cost?: number | null;
  currency?: string | null;
}

export interface PolicyDecisionInput {
  decision_id: string;
  subject: PolicySubject & { projectId?: string | null };
  action: PolicyDecisionActionDetail;
  result: PolicyResult;
  /** 审批人/按需扩展：与 schema 的 approval.required_by 对应。 */
  requiredBy?: string[];
  approvalId?: string | null;
  evaluatedAt?: string;
  traceId?: string;
  policyVersion?: string | null;
}

export function buildPolicyDecisionRecord(input: PolicyDecisionInput): PolicyDecisionRecord {
  const limits = input.result.limits;
  const record: PolicyDecisionRecord = {
    decision_id: input.decision_id,
    subject: {
      type: input.subject.type,
      id: input.subject.id,
      tenant_id: input.subject.tenantId,
      project_id: input.subject.projectId ?? null,
    },
    action: {
      name: input.action.name,
      risk: "low",
      target_type: input.action.target_type ?? null,
      target_id: input.action.target_id ?? null,
      reversible: input.action.reversible ?? true,
      estimated_cost: input.action.estimated_cost ?? null,
      currency: input.action.currency ?? null,
    },
    decision: input.result.decision,
    reason: input.result.reason,
    matched_rules: input.result.matchedRules.map((rule) => ({
      rule_id: rule.ruleId,
      effect: rule.effect,
      detail: rule.detail ?? null,
    })),
    limits: {
      max_cost: null,
      max_wall_clock_seconds: null,
      max_gpu_count: null,
    },
    approval: {
      required_by: input.requiredBy ?? [],
      approval_id: input.approvalId ?? null,
      expires_at: null,
      scope: null,
    },
    evaluated_at: input.evaluatedAt ?? new Date().toISOString(),
    trace_id: input.traceId ?? null,
  };

  if (limits?.maxCost !== undefined) record.limits.max_cost = limits.maxCost;
  if (limits?.maxWallClockSeconds !== undefined) {
    record.limits.max_wall_clock_seconds = limits.maxWallClockSeconds;
  }
  if (limits?.maxGpuCount !== undefined) record.limits.max_gpu_count = limits.maxGpuCount;

  return record;
}

(function ensureShapeTypes() {
  const sample: PolicyDecisionRecord["subject"]["type"] = "operator";
  void sample;
})();

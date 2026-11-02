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

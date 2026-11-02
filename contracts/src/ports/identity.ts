/**
 * IdentityPort：身份校验与授权决策的唯一入口。
 *
 * 由 harness-core 或公司 IdP 实现。
 * 本工程不建第二套用户/租户表，只做项目视图与领域级策略。
 */

import type { DataClass, Iso8601, PortCapabilities, PortResult, Subject } from "../types.ts";

export interface TokenVerifyInput {
  /** Bearer token，仅在内存中使用，禁止落盘。 */
  token: string;
  /** 期望受众。 */
  audience?: string;
}

export interface TokenVerifyResult {
  subject: Subject;
  issuedAt: Iso8601;
  expiresAt: Iso8601;
  /** token 唯一 ID，用于撤销与审计。 */
  tokenId: string;
  /** 数据分类上限。 */
  dataClassMax?: DataClass;
}

export interface AuthorizationInput {
  subject: Subject;
  action: string;
  resource: {
    type: string;
    id?: string;
    tenantId?: string;
    projectId?: string;
  };
  context?: {
    risk?: "low" | "medium" | "high" | "critical";
    estimatedCost?: number;
    currency?: string;
    dataClass?: DataClass;
  };
}

export type AuthorizationDecision = "ALLOW" | "DENY" | "REQUIRE_APPROVAL" | "DEFER";

export interface AuthorizationResult {
  decision: AuthorizationDecision;
  reason: string;
  matchedRules?: string[];
  limits?: {
    maxCost?: number;
    maxWallClockSeconds?: number;
    allowedModels?: string[];
    allowedRegions?: string[];
  };
  /** 需要审批时返回审批范围与有效期。 */
  approval?: { scope: string; expiresAt: Iso8601 };
}

export interface IdentityCapabilities extends PortCapabilities {
  supportsApproval?: boolean;
  supportsAttributeBased?: boolean;
  supportsTokenRevocation?: boolean;
}

/**
 * 实现方必须保证：
 * - verify 对过期、伪造、受众不符的 token 返回明确错误码。
 * - authorize 默认拒绝；未知动作不得放行。
 * - 决策可解释，matchedRules 可用于审计。
 * - subject 中的 tenantId 不可由调用方伪造。
 */
export interface IdentityPort {
  describe(): Promise<PortResult<IdentityCapabilities>>;
  verify(input: TokenVerifyInput): Promise<PortResult<TokenVerifyResult>>;
  authorize(input: AuthorizationInput): Promise<PortResult<AuthorizationResult>>;
  revoke(tokenId: string): Promise<PortResult<void>>;
}

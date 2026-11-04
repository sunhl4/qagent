import type {
  AuthorizationInput,
  AuthorizationResult,
  IdentityCapabilities,
  IdentityPort,
  PortResult,
  Subject,
  TokenVerifyInput,
  TokenVerifyResult,
} from "../../../contracts/src/index.ts";
import { fail, ok } from "../../../contracts/src/index.ts";
import { StubBase } from "./common.ts";
import type { StubBaseOptions } from "./common.ts";

interface TokenRecord {
  tokenId: string;
  subject: Subject;
  expiresAt: string;
  audience?: string;
}

export interface StubIdentityOptions extends Partial<StubBaseOptions> {
  tokens?: Record<string, string>;
  subjects?: Subject[];
  supportsApproval?: boolean;
}

export class StubIdentityPort extends StubBase implements IdentityPort {
  private readonly tokens = new Map<string, TokenRecord>();
  private readonly subjects = new Map<string, Subject>();
  private readonly revoked = new Set<string>();
  private readonly supportsApproval: boolean;
  private counter = 0;

  constructor(options: StubIdentityOptions = {}) {
    super({
      implementation: options.implementation ?? "stub-identity",
      degradedReason:
        options.degradedReason ?? "内存实现：无真实 IdP、无签名校验、无跨进程撤销传播",
      features: options.features ?? ["verify", "authorize", "revoke"],
      clock: options.clock,
      residency: options.residency,
    });

    const defaults: Subject[] = options.subjects ?? [
      {
        type: "user",
        id: "user-1",
        tenantId: "tenant-demo",
        projectId: "project-demo",
        scopes: ["literature:read", "experiment:submit", "workspace:write", "test:run"],
      },
    ];
    for (const subject of defaults) this.subjects.set(subject.id, subject);

    const tokenMap = options.tokens ?? { "stub-token": "user-1" };
    for (const [token, subjectId] of Object.entries(tokenMap)) {
      this.counter += 1;
      this.tokens.set(token, {
        tokenId: `token-${this.counter}`,
        subject: this.subjects.get(subjectId) ?? {
          type: "service",
          id: subjectId,
          tenantId: "tenant-demo",
          scopes: [],
        },
        expiresAt: new Date(this.clock().getTime() + 3600_000).toISOString(),
      });
    }
    this.supportsApproval = options.supportsApproval ?? true;
  }

  async describe(): Promise<PortResult<IdentityCapabilities>> {
    return ok({
      ...this.caps(),
      supportsApproval: this.supportsApproval,
      supportsAttributeBased: true,
      supportsTokenRevocation: true,
    });
  }

  async verify(input: TokenVerifyInput): Promise<PortResult<TokenVerifyResult>> {
    const record = this.tokens.get(input.token);
    if (!record) {
      return fail("UNAUTHENTICATED", "未知 token", { reason: "unknown_token" });
    }
    if (this.revoked.has(record.tokenId)) {
      return fail("UNAUTHENTICATED", "token 已撤销", { tokenId: record.tokenId });
    }
    if (Date.parse(record.expiresAt) <= this.clock().getTime()) {
      return fail("PERMISSION_DENIED", "token 已过期", { tokenId: record.tokenId });
    }
    if (input.audience && record.audience && input.audience !== record.audience) {
      return fail("PERMISSION_DENIED", "受众不匹配", {
        expected: record.audience,
        actual: input.audience,
      });
    }
    return ok({
      subject: record.subject,
      issuedAt: new Date(this.clock().getTime() - 1000).toISOString(),
      expiresAt: record.expiresAt,
      tokenId: record.tokenId,
      dataClassMax: "confidential",
    });
  }

  async authorize(input: AuthorizationInput): Promise<PortResult<AuthorizationResult>> {
    const { subject, action, resource, context } = input;

    if (!action) {
      return fail("INVALID_ARGUMENT", "action 缺失");
    }

    if (subject.tenantId !== resource.tenantId && resource.tenantId !== undefined) {
      return ok({ decision: "DENY", reason: "跨租户访问", matchedRules: ["R-TENANT"] });
    }

    if (action === "network.internet" && subject.type === "agent") {
      return ok({
        decision: "DENY",
        reason: "Agent 默认无外网权限",
        matchedRules: ["R-AGENT-NO-INTERNET"],
      });
    }

    if (
      context?.dataClass === "restricted" &&
      resource.type === "model" &&
      resource.id === "external"
    ) {
      return ok({
        decision: "DENY",
        reason: "受限数据不得使用外部模型",
        matchedRules: ["R-DATA-RESIDENCY"],
      });
    }

    const scopes = subject.scopes ?? [];
    if (scopes.length > 0 && !scopes.includes(action)) {
      return ok({
        decision: "DENY",
        reason: `主体缺少 scope: ${action}`,
        matchedRules: ["R-SCOPE"],
      });
    }

    if (
      typeof context?.estimatedCost === "number" &&
      typeof context.currency === "string" &&
      context.estimatedCost > 1000
    ) {
      return ok({
        decision: "REQUIRE_APPROVAL",
        reason: "估计成本过高",
        matchedRules: ["R-BUDGET-APPROVAL"],
        approval: {
          scope: `cost<=${context.estimatedCost}`,
          expiresAt: new Date(this.clock().getTime() + 3600_000).toISOString(),
        },
      });
    }

    if (context?.risk === "critical" || resource.type === "qpu") {
      return ok({
        decision: "REQUIRE_APPROVAL",
        reason: "高风险动作需要审批",
        matchedRules: ["R-HIGH-RISK"],
        approval: {
          scope: action,
          expiresAt: new Date(this.clock().getTime() + 3600_000).toISOString(),
        },
      });
    }

    return ok({ decision: "ALLOW", reason: "未命中拒绝规则", matchedRules: ["R-DEFAULT"] });
  }

  async revoke(tokenId: string): Promise<PortResult<void>> {
    this.revoked.add(tokenId);
    return ok(undefined);
  }

  /** 测试辅助。 */
  subject(subjectId: string): Subject | undefined {
    return this.subjects.get(subjectId);
  }
}

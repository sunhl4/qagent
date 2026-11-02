import { randomUUID } from "node:crypto";
import type {
  CallContext,
  IssueScopedTokenRequest,
  ScopedToken,
} from "../../../contracts/src/index.ts";
import { PortError } from "../../../contracts/src/index.ts";
import type { CredentialsPort } from "../../../contracts/src/index.ts";
import { StubPortBase, addSeconds } from "./common.ts";
import type { StubBaseOptions } from "./common.ts";

const FORBIDDEN_SECRET_PATTERNS = [
  /^sk-[A-Za-z0-9_-]{16,}$/,
  /^AKIA[0-9A-Z]{16}$/,
  /^ghp_[A-Za-z0-9]{20,}$/,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
];

export interface StubCredentialsOptions extends Partial<StubBaseOptions> {
  /** 允许的最大 TTL；用于测试超时。 */
  maxTtlSeconds?: number;
}

export class StubCredentialsPort extends StubPortBase implements CredentialsPort {
  private readonly tokens = new Map<string, ScopedToken>();
  private readonly revoked = new Set<string>();
  private readonly maxTtlSeconds: number;
  private counter = 0;

  constructor(options: StubCredentialsOptions = {}) {
    super({
      componentId: options.componentId ?? "stub-credentials",
      port: "credentials",
      implementation: "in-memory",
      capabilities: ["issueScopedToken", "revoke"],
      degradedReason: "内存实现：token 未签名、未加密、不可跨进程验证",
      clock: options.clock,
      residency: options.residency,
    });
    this.maxTtlSeconds = options.maxTtlSeconds ?? 900;
  }

  async issueScopedToken(ctx: CallContext, req: IssueScopedTokenRequest): Promise<ScopedToken> {
    this.assertContext(ctx);

    if (req.secretRef && FORBIDDEN_SECRET_PATTERNS.some((pattern) => pattern.test(req.secretRef!))) {
      throw new PortError("INVALID_REQUEST", "不得传入明文长期密钥", {});
    }
    if (req.ttlSeconds <= 0 || req.ttlSeconds > this.maxTtlSeconds) {
      throw new PortError("INVALID_REQUEST", "ttlSeconds 超出允许范围", {
        requested: req.ttlSeconds,
        max: this.maxTtlSeconds,
      });
    }
    if (req.actions.length === 0) {
      throw new PortError("INVALID_REQUEST", "actions 不能为空", {});
    }
    if (ctx.subjectType !== "agent" && ctx.subjectType !== "service") {
      throw new PortError("POLICY_DENIED", "只有 agent 或 service 可以申请短期 token", {
        subjectType: ctx.subjectType,
      });
    }

    this.counter += 1;
    const token: ScopedToken = {
      token: `stub-token-${this.counter}-${randomUUID()}`,
      expiresAt: addSeconds(this.clock, req.ttlSeconds),
      audience: req.audience,
      actions: [...req.actions],
    };
    this.tokens.set(token.token, token);
    return token;
  }

  async revoke(ctx: CallContext, token: string, _reason: string): Promise<void> {
    this.assertContext(ctx);
    if (!this.tokens.has(token)) {
      throw new PortError("NOT_FOUND", "token 不存在", {});
    }
    this.revoked.add(token);
  }

  isRevoked(token: string): boolean {
    return this.revoked.has(token);
  }
}

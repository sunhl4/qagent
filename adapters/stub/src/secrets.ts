import type {
  IssueCredentialInput,
  IssuedCredential,
  PortResult,
  SecretCapabilities,
  SecretPort,
  Subject,
} from "../../../contracts/src/index.ts";
import { fail, ok } from "../../../contracts/src/index.ts";
import { StubBase } from "./common.ts";
import type { StubBaseOptions } from "./common.ts";

export interface StubSecretOptions extends Partial<StubBaseOptions> {
  maxTtlSeconds?: number;
}

export class StubSecretPort extends StubBase implements SecretPort {
  private readonly credentials = new Map<string, IssuedCredential>();
  private readonly revoked = new Set<string>();
  private readonly maxTtlSeconds: number;
  private readonly idempotency = new Map<string, IssuedCredential>();
  private counter = 0;

  constructor(options: StubSecretOptions = {}) {
    super({
      implementation: options.implementation ?? "stub-secret",
      degradedReason: options.degradedReason ?? "内存实现：凭据未签名、未加密，进程重启即失效",
      features: options.features ?? ["issue", "revoke", "status"],
      clock: options.clock,
      residency: options.residency,
    });
    this.maxTtlSeconds = options.maxTtlSeconds ?? 900;
  }

  async describe(): Promise<PortResult<SecretCapabilities>> {
    return ok({
      ...this.caps(),
      maxTtlSeconds: this.maxTtlSeconds,
      supportsRevocation: true,
      supportsBinding: true,
      types: ["bearer", "opaque_handle"],
    });
  }

  async issue(input: IssueCredentialInput): Promise<PortResult<IssuedCredential>> {
    if (input.idempotencyKey) {
      const cached = this.idempotency.get(input.idempotencyKey);
      if (cached) return ok(cached);
    }
    if (!input.subject || !input.subject.tenantId) {
      return fail("INVALID_ARGUMENT", "subject 缺失");
    }
    if (input.ttlSeconds <= 0 || input.ttlSeconds > this.maxTtlSeconds) {
      return fail("INVALID_ARGUMENT", "ttlSeconds 超出允许范围", {
        requested: input.ttlSeconds,
        max: this.maxTtlSeconds,
      });
    }
    if (input.scope.length === 0) {
      return fail("INVALID_ARGUMENT", "scope 不能为空");
    }
    if (input.scope.includes("*") || input.scope.includes("admin")) {
      return fail("PERMISSION_DENIED", "不允许申请通配或管理 scope");
    }
    if (input.subject.type !== "agent" && input.subject.type !== "service") {
      return fail("PERMISSION_DENIED", "只有 agent 或 service 可以申请短期凭据");
    }

    this.counter += 1;
    const issuedAt = this.now();
    const credential: IssuedCredential = {
      credentialId: `cred-${this.counter}`,
      value: `stub-credential-${this.counter}`,
      type: "opaque_handle",
      issuedAt,
      expiresAt: new Date(this.clock().getTime() + input.ttlSeconds * 1000).toISOString(),
      audience: input.audience,
      scope: [...input.scope],
    };
    this.credentials.set(credential.credentialId, credential);
    if (input.idempotencyKey) this.idempotency.set(input.idempotencyKey, credential);
    return ok(credential);
  }

  async revoke(credentialId: string): Promise<PortResult<void>> {
    if (!this.credentials.has(credentialId)) {
      return fail("NOT_FOUND", "凭据不存在", { credentialId });
    }
    this.revoked.add(credentialId);
    return ok(undefined);
  }

  async status(
    credentialId: string,
  ): Promise<PortResult<{ credentialId: string; active: boolean; expiresAt: string }>> {
    const credential = this.credentials.get(credentialId);
    if (!credential) {
      return fail("NOT_FOUND", "凭据不存在", { credentialId });
    }
    const active =
      !this.revoked.has(credentialId) && Date.parse(credential.expiresAt) > this.clock().getTime();
    return ok({ credentialId, active, expiresAt: credential.expiresAt });
  }

  /** 测试辅助：判断是否已撤销。 */
  isRevoked(credentialId: string): boolean {
    return this.revoked.has(credentialId);
  }

  /** 测试辅助：签发数量。 */
  issuedCount(): number {
    return this.credentials.size;
  }

  /** 受限主体场景。 */
  static restrictedSubject(): Subject {
    return { type: "user", id: "user-2", tenantId: "tenant-demo", scopes: ["read"] };
  }
}

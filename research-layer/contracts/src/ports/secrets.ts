/**
 * SecretPort：短期凭据的唯一签发入口。
 *
 * 由 harness-core 或公司 Vault/KMS 实现。
 * Agent 永远拿不到长期密钥；本工程只申请短期、可撤销、范围受限的凭据。
 */

import type { Iso8601, PortCapabilities, PortResult, Subject } from "../types.ts";

export interface IssueCredentialInput {
  /** 申请主体。 */
  subject: Subject;
  /** 凭据用途，如 cloud:submit、hpc:submit、model:invoke。 */
  audience: string;
  /** 权限范围。 */
  scope: string[];
  /** 有效期秒数。 */
  ttlSeconds: number;
  /** 绑定的资源，如 taskId、handleId。 */
  binding?: {
    taskId?: string;
    resourceId?: string;
    leaseId?: string;
    fencingToken?: number;
  };
  /** 幂等键。 */
  idempotencyKey?: string;
}

export interface IssuedCredential {
  credentialId: string;
  /** 凭据值，只在内存中使用；调用方禁止写日志或持久化。 */
  value: string;
  /** 凭据类型。 */
  type: "bearer" | "mtls_cert" | "signed_url" | "opaque_handle";
  issuedAt: Iso8601;
  expiresAt: Iso8601;
  audience: string;
  scope: string[];
}

export interface SecretCapabilities extends PortCapabilities {
  maxTtlSeconds?: number;
  supportsRevocation?: boolean;
  supportsBinding?: boolean;
  types?: string[];
}

/**
 * 实现方必须保证：
 * - ttl 不超过请求值，也不超过策略上限。
 * - 凭据与 subject、audience、scope、binding 绑定。
 * - revoke 后立即失效；传播延迟需在能力声明中说明。
 * - 不记录凭据明文。
 * - 不签发超出请求范围的权限。
 */
export interface SecretPort {
  describe(): Promise<PortResult<SecretCapabilities>>;
  issue(input: IssueCredentialInput): Promise<PortResult<IssuedCredential>>;
  revoke(credentialId: string): Promise<PortResult<void>>;
  /** 查询凭据状态，用于对账。 */
  status(credentialId: string): Promise<PortResult<{ credentialId: string; active: boolean; expiresAt: Iso8601 }>>;
}

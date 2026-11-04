/**
 * ArtifactStorePort：产物与证据的唯一存储入口。
 *
 * 由 harness-core 或公司对象存储实现。
 * 本工程只写入 RunManifest、原始结果、日志、报告，不管理存储集群。
 */

import type {
  ArtifactRef,
  Iso8601,
  PortCapabilities,
  PortResult,
  Sha256,
} from "../types.ts";

export interface PutArtifactInput {
  tenantId: string;
  projectId?: string;
  /** 逻辑键，如 runs/2026/xxx/metrics.json。 */
  key: string;
  contentType: string;
  bytes?: Uint8Array;
  stream?: AsyncIterable<Uint8Array>;
  /** 期望哈希，服务端必须校验。 */
  expectedSha256?: Sha256;
  /** 元数据，不得含密钥。 */
  metadata?: Record<string, string>;
  /** 保留策略。 */
  retention?: "ephemeral" | "standard" | "long" | "legal_hold";
  /** 幂等键。 */
  idempotencyKey?: string;
}

export interface GetArtifactInput {
  tenantId: string;
  artifactId?: string;
  uri?: string;
}

export interface ArtifactStoreCapabilities extends PortCapabilities {
  maxObjectBytes?: number;
  supportsSignedUrl?: boolean;
  supportsVersioning?: boolean;
  supportsRetention?: boolean;
  supportsServerSideEncryption?: boolean;
}

export interface SignedUrl {
  url: string;
  expiresAt: Iso8601;
  /** 只允许的方法。 */
  method: "GET" | "PUT";
}

/**
 * 实现方必须保证：
 * - put 在写入后校验哈希，不匹配则删除并返回错误。
 * - get 返回内容或签名 URL，不返回明文凭据。
 * - 租户隔离：不同 tenantId 不能读取对方对象。
 * - 删除语义明确；默认不提供物理删除，只有保留策略到期。
 * - signedUrl 有效期不得超过请求值。
 */
export interface ArtifactStorePort {
  describe(): Promise<PortResult<ArtifactStoreCapabilities>>;
  put(input: PutArtifactInput): Promise<PortResult<ArtifactRef>>;
  stat(input: GetArtifactInput): Promise<PortResult<ArtifactRef>>;
  get(input: GetArtifactInput): Promise<PortResult<{ ref: ArtifactRef; bytes: Uint8Array }>>;
  signedUrl(input: GetArtifactInput & { method: "GET" | "PUT"; ttlSeconds: number }): Promise<PortResult<SignedUrl>>;
  list(input: { tenantId: string; projectId?: string; prefix: string; limit?: number; cursor?: string }): Promise<
    PortResult<{ items: ArtifactRef[]; nextCursor?: string }>
  >;
  /** 标记保留策略，防止误删。 */
  setRetention(input: { tenantId: string; artifactId: string; retention: string; until?: Iso8601 }): Promise<PortResult<ArtifactRef>>;
}

/**
 * 契约公共类型与结果封装。
 *
 * 设计约束：
 * - 所有跨工程调用返回 `PortResult<T>`，不抛未捕获异常。
 * - 错误必须可序列化，且明确是否可重试。
 * - `UNKNOWN_EXECUTION` 永远不可重试。
 * - 能力必须自描述，并如实声明 degraded。
 */

export type Iso8601 = string;
export type Sha256 = string;

export type DataClass = "public" | "internal" | "confidential" | "restricted";

export type SubjectType = "user" | "service" | "agent";

export interface Subject {
  type: SubjectType;
  id: string;
  tenantId: string;
  projectId?: string;
  /** 该主体被授予的 scope；空表示只读。 */
  scopes?: string[];
  /** 附加属性，用于 ABAC；不得含密钥。 */
  attributes?: Record<string, string>;
}

export interface ArtifactRef {
  artifactId?: string;
  uri: string;
  sha256?: Sha256;
  sizeBytes?: number;
  contentType?: string;
  createdAt?: Iso8601;
  retention?: string;
}

export interface Usage {
  inputTokens?: number;
  outputTokens?: number;
  cost?: number;
  currency?: string;
  cpuSeconds?: number;
  gpuSeconds?: number;
  wallClockSeconds?: number;
}

export interface LogChunk {
  lines: string[];
  /** 下一次增量读取的游标。 */
  nextSequence?: number;
  truncated: boolean;
}

/** 所有带幂等语义的请求都必须携带。 */
export interface Idempotent {
  idempotencyKey: string;
}

export interface PortCapabilities {
  contractVersion: string;
  /** 实现方标识，例如 "harness-core" / "research-stub"。 */
  implementation: string;
  /** true 表示只能用于开发/测试。 */
  degraded: boolean;
  degradedReason?: string;
  /** 实现支持的特性名；调用方据此降级。 */
  features?: string[];
  /** 数据驻留。 */
  residency?: string;
  limits?: Record<string, unknown>;
}

export type PortErrorCode =
  | "INVALID_ARGUMENT"
  | "UNAUTHENTICATED"
  | "PERMISSION_DENIED"
  | "NOT_FOUND"
  | "CONFLICT"
  | "QUOTA_EXCEEDED"
  | "NOT_SUPPORTED"
  | "UNAVAILABLE"
  | "TIMEOUT"
  | "UNKNOWN_EXECUTION"
  | "INTERNAL";

const NON_RETRYABLE: ReadonlySet<PortErrorCode> = new Set<PortErrorCode>([
  "INVALID_ARGUMENT",
  "UNAUTHENTICATED",
  "PERMISSION_DENIED",
  "NOT_FOUND",
  "CONFLICT",
  "QUOTA_EXCEEDED",
  "NOT_SUPPORTED",
  "UNKNOWN_EXECUTION",
]);

export interface PortErrorInfo {
  code: PortErrorCode;
  message: string;
  retryable: boolean;
  details?: Record<string, unknown>;
  traceId?: string;
}

export type PortResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: PortErrorInfo };

export function ok<T>(value: T): PortResult<T> {
  return { ok: true, value };
}

export function fail<T = never>(
  code: PortErrorCode,
  message: string,
  details?: Record<string, unknown>,
  traceId?: string,
): PortResult<T> {
  return {
    ok: false,
    error: {
      code,
      message,
      retryable: !NON_RETRYABLE.has(code),
      details,
      traceId,
    },
  };
}

export function unwrap<T>(result: PortResult<T>): T {
  if (!result.ok) {
    const error = new Error(`${result.error.code}: ${result.error.message}`) as Error & {
      code: PortErrorCode;
      retryable: boolean;
      details?: Record<string, unknown>;
    };
    error.code = result.error.code;
    error.retryable = result.error.retryable;
    error.details = result.error.details;
    throw error;
  }
  return result.value;
}

export function isRetryable<T>(result: PortResult<T>): boolean {
  return !result.ok && result.error.retryable;
}

/**
 * ComputePort / HpcSchedulerPort：算力资源的唯一入口。
 *
 * 由 harness-core 实现（云平台、本地 HPC、GPU 池）。
 * 本工程只定义请求、检查能力、做预算与对账、做上层编排。
 */

import type {
  ArtifactRef,
  Idempotent,
  Iso8601,
  LogChunk,
  PortCapabilities,
  PortResult,
  Usage,
} from "../types.ts";

export type ResourceKind = "cpu" | "gpu" | "hpc" | "cloud" | "qpu" | "browser";

export interface ResourceRequest extends Idempotent {
  requestId: string;
  tenantId: string;
  projectId?: string;
  /** 关联任务，用于计费与审计。 */
  taskId?: string;
  kind: ResourceKind;
  /** 加速卡型号，如 A100-40GB。 */
  accelerator?: string;
  /** 卡数或节点数。 */
  count: number;
  cpu?: number;
  memoryGb?: number;
  /** 最大运行时长（秒）。 */
  wallClockSeconds: number;
  /** 成本上限。 */
  maxCost?: number;
  currency?: string;
  /** 容器镜像 digest。 */
  image?: string;
  /** 启动命令。 */
  command?: string[];
  /** 环境变量；禁止放长期密钥。 */
  env?: Record<string, string>;
  /** 数据驻留要求。 */
  dataResidency?: string;
  priority?: "low" | "normal" | "high";
  /** 检查点要求。 */
  checkpoint?: { required: boolean; intervalSeconds?: number };
  /** 标签。 */
  labels?: Record<string, string>;
}

export type ResourceState =
  | "queued"
  | "starting"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "unknown";

export interface ResourceHandle {
  handleId: string;
  /** 供应商侧 ID，用于对账。 */
  providerResourceId?: string;
  kind: ResourceKind;
  state: ResourceState;
  submittedAt: Iso8601;
  queuedAt?: Iso8601;
  startedAt?: Iso8601;
  endedAt?: Iso8601;
  exitCode?: number;
  /** 供应商原始状态，仅用于排障，调用方不得依赖。 */
  providerState?: string;
  usage?: Usage;
  artifacts?: ArtifactRef[];
  /** 检查点 URI。 */
  checkpointUri?: string;
  /**
   * 小型指标的内联返回，便于调度器/模拟器直接回传。
   * 大结果与原始数据必须通过 ArtifactStorePort 交换。
   */
  metrics?: Array<{
    name: string;
    value: number;
    unit?: string;
    seed?: number;
    split?: string;
  }>;
  /** fencing token，防止旧 worker 继续操作。 */
  fencingToken?: string;
  /** 状态原因。 */
  reason?: string;
}

export interface Quote {
  requestId: string;
  estimatedCost?: number;
  currency?: string;
  estimatedQueueSeconds?: number;
  estimatedRunSeconds?: number;
  /** 预估置信度。 */
  confidence?: "low" | "medium" | "high";
  expiresAt?: Iso8601;
}

export type ReconcileEvidence =
  | { verdict: "executed"; handle: ResourceHandle }
  | { verdict: "queued_or_running"; handle: ResourceHandle }
  | { verdict: "not_executed_confirmed"; reason: string }
  | { verdict: "cancelled_before_execution_confirmed"; reason: string }
  | { verdict: "unknown"; reason: string };

export interface ComputeCapabilities extends PortCapabilities {
  kinds: ResourceKind[];
  accelerators?: string[];
  maxWallClockSeconds?: number;
  supportsCheckpoint?: boolean;
  supportsCancel?: boolean;
  supportsReconcile?: boolean;
  supportsReservation?: boolean;
}

/**
 * 实现方必须保证：
 * - submit 按 idempotencyKey 去重；重复提交返回同一 handle。
 * - cancel 幂等；对终态返回当前状态而非错误。
 * - release 幂等；资源已释放时返回成功。
 * - 无法确认是否执行时必须返回 unknown，不得返回 failed。
 * - 用量必须可归因到 tenantId/projectId/taskId。
 */
export interface ComputePort {
  describe(): Promise<PortResult<ComputeCapabilities>>;
  quote(request: ResourceRequest): Promise<PortResult<Quote>>;
  submit(request: ResourceRequest): Promise<PortResult<ResourceHandle>>;
  status(handleId: string): Promise<PortResult<ResourceHandle>>;
  list(filter: { tenantId: string; projectId?: string; taskId?: string; state?: ResourceState }): Promise<PortResult<ResourceHandle[]>>;
  cancel(handleId: string, reason?: string): Promise<PortResult<ResourceHandle>>;
  /** 与供应商对账，判断是否执行。 */
  reconcile(handleId: string): Promise<PortResult<ReconcileEvidence>>;
  logs(handleId: string, options?: { fromSequence?: number; maxBytes?: number }): Promise<PortResult<LogChunk>>;
  release(handleId: string): Promise<PortResult<void>>;
}

/**
 * HPC 专用扩展：Reservation / hold / release。
 * 若实现方不支持，describe() 中不声明 features，调用方降级为普通 submit。
 */
export interface HpcReservation {
  reservationId: string;
  tenantId: string;
  projectId?: string;
  startAt: Iso8601;
  endAt: Iso8601;
  nodes: number;
  gpusPerNode?: number;
  state: "requested" | "confirmed" | "active" | "released" | "expired" | "failed";
  providerReservationId?: string;
}

export interface HpcSchedulerPort extends ComputePort {
  reserve(input: {
    tenantId: string;
    projectId?: string;
    startAt: Iso8601;
    endAt: Iso8601;
    nodes: number;
    gpusPerNode?: number;
    idempotencyKey: string;
  }): Promise<PortResult<HpcReservation>>;
  releaseReservation(reservationId: string): Promise<PortResult<void>>;
  /** 队列深度与预计等待，用于两队列门控。 */
  queueInfo(input: { tenantId: string; partition?: string }): Promise<
    PortResult<{
      pending: number;
      running: number;
      estimatedWaitSeconds?: number;
      confidence?: "low" | "medium" | "high";
    }>
  >;
}

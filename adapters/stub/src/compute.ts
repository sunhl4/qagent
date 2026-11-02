import type {
  ComputeCapabilities,
  HpcReservation,
  HpcSchedulerPort,
  LogChunk,
  PortResult,
  Quote,
  ReconcileEvidence,
  ResourceHandle,
  ResourceRequest,
  ResourceState,
} from "../../../contracts/src/index.ts";
import { fail, ok } from "../../../contracts/src/index.ts";
import { StubBase } from "./common.ts";
import type { StubBaseOptions } from "./common.ts";

export type JobScenario = "success" | "fail" | "unknown" | "slow";

export interface StubComputeOptions extends Partial<StubBaseOptions> {
  scenario?: JobScenario;
  /** 达到该轮询次数后进入终态。 */
  stepsToTerminal?: number;
  baseCostPerHour?: number;
  kinds?: Array<"cpu" | "gpu" | "hpc" | "cloud" | "qpu" | "browser">;
}

interface RecordedJob {
  request: ResourceRequest;
  handle: ResourceHandle;
  polls: number;
  released: boolean;
}

export class StubComputePort extends StubBase implements HpcSchedulerPort {
  private readonly jobs = new Map<string, RecordedJob>();
  private readonly idempotency = new Map<string, ResourceHandle>();
  private readonly reservations = new Map<string, HpcReservation>();
  private readonly scenario: JobScenario;
  private readonly stepsToTerminal: number;
  private readonly baseCostPerHour: number;
  private readonly kinds: Array<"cpu" | "gpu" | "hpc" | "cloud" | "qpu" | "browser">;
  private counter = 0;

  constructor(options: StubComputeOptions = {}) {
    super({
      implementation: options.implementation ?? "stub-compute",
      degradedReason:
        options.degradedReason ?? "内存模拟：不提交真实 Slurm/云作业，不产生真实计算与费用",
      features:
        options.features ??
        ["quote", "submit", "status", "cancel", "reconcile", "logs", "release", "reserve"],
      clock: options.clock,
      residency: options.residency ?? "on_prem",
    });
    this.scenario = options.scenario ?? "success";
    this.stepsToTerminal = Math.max(1, options.stepsToTerminal ?? 2);
    this.baseCostPerHour = options.baseCostPerHour ?? 10;
    this.kinds = options.kinds ?? ["cpu", "gpu", "hpc", "cloud"];
  }

  async describe(): Promise<PortResult<ComputeCapabilities>> {
    return ok({
      ...this.caps(),
      kinds: this.kinds,
      accelerators: ["A100-40GB", "H100-80GB"],
      maxWallClockSeconds: 86400,
      supportsCheckpoint: true,
      supportsCancel: true,
      supportsReconcile: true,
      supportsReservation: true,
    });
  }

  async quote(request: ResourceRequest): Promise<PortResult<Quote>> {
    if (!this.kinds.includes(request.kind)) {
      return fail("NOT_SUPPORTED", "不支持的资源类型", { kind: request.kind });
    }
    const estimatedCost =
      (request.wallClockSeconds / 3600) * this.baseCostPerHour * Math.max(1, request.count);
    return ok({
      requestId: request.requestId,
      estimatedCost,
      currency: request.currency ?? "CNY",
      estimatedQueueSeconds: 60,
      estimatedRunSeconds: request.wallClockSeconds,
      confidence: "medium",
      expiresAt: new Date(this.clock().getTime() + 300_000).toISOString(),
    });
  }

  async submit(request: ResourceRequest): Promise<PortResult<ResourceHandle>> {
    const cached = this.idempotency.get(request.idempotencyKey);
    if (cached) return ok(cached);

    if (!request.tenantId) return fail("INVALID_ARGUMENT", "tenantId 缺失");
    if (request.count <= 0) return fail("INVALID_ARGUMENT", "count 必须大于 0");
    if (request.wallClockSeconds <= 0) {
      return fail("INVALID_ARGUMENT", "wallClockSeconds 必须大于 0");
    }
    if (!this.kinds.includes(request.kind)) {
      return fail("NOT_SUPPORTED", "不支持的资源类型", { kind: request.kind });
    }

    this.counter += 1;
    const handle: ResourceHandle = {
      handleId: `stub-job-${this.counter}`,
      providerResourceId: `stub-ext-${this.counter}`,
      kind: request.kind,
      state: "queued",
      submittedAt: this.now(),
      queuedAt: this.now(),
      fencingToken: String(this.counter),
    };
    this.jobs.set(handle.handleId, { request, handle, polls: 0, released: false });
    this.idempotency.set(request.idempotencyKey, handle);
    return ok(handle);
  }

  async status(handleId: string): Promise<PortResult<ResourceHandle>> {
    const record = this.jobs.get(handleId);
    if (!record) return fail("NOT_FOUND", "作业不存在", { handleId });
    if (record.released) {
      return ok({ ...record.handle, state: "cancelled", reason: "已释放" });
    }

    record.polls += 1;

    if (this.scenario === "unknown") {
      const handle: ResourceHandle = {
        ...record.handle,
        state: "unknown",
        reason: "无法确认是否执行，必须人工对账；禁止自动重试",
      };
      record.handle = handle;
      return ok(handle);
    }

    if (record.polls < this.stepsToTerminal) {
      const handle: ResourceHandle = {
        ...record.handle,
        state: record.polls === 1 ? "starting" : "running",
        startedAt: record.polls >= 1 ? this.now() : undefined,
      };
      record.handle = handle;
      return ok(handle);
    }

    const wallClockSeconds = Math.min(record.request.wallClockSeconds, 60 * this.stepsToTerminal);
    const cost = (wallClockSeconds / 3600) * this.baseCostPerHour * Math.max(1, record.request.count);

    if (this.scenario === "fail") {
      const handle: ResourceHandle = {
        ...record.handle,
        state: "failed",
        endedAt: this.now(),
        exitCode: 1,
        reason: "桩：注入失败",
        usage: { wallClockSeconds, cost, currency: record.request.currency ?? "CNY" },
      };
      record.handle = handle;
      return ok(handle);
    }

    const handle: ResourceHandle = {
      ...record.handle,
      state: "succeeded",
      startedAt: this.now(),
      endedAt: this.now(),
      exitCode: 0,
      usage: { wallClockSeconds, cost, currency: record.request.currency ?? "CNY" },
      metrics: [
        { name: "val_loss", value: 0.94, seed: 13, split: "val" },
        { name: "train_time_seconds", value: wallClockSeconds, split: "train" },
        { name: "val_accuracy", value: 0.9, seed: 13, split: "val" },
      ],
      checkpointUri: `stub://checkpoints/${handleId}/latest`,
    };
    record.handle = handle;
    return ok(handle);
  }

  async list(filter: {
    tenantId: string;
    projectId?: string;
    taskId?: string;
    state?: ResourceState;
  }): Promise<PortResult<ResourceHandle[]>> {
    const items = [...this.jobs.values()]
      .filter((record) => record.request.tenantId === filter.tenantId)
      .filter((record) => (filter.taskId ? record.request.taskId === filter.taskId : true))
      .filter((record) => (filter.state ? record.handle.state === filter.state : true))
      .map((record) => record.handle);
    return ok(items);
  }

  async cancel(handleId: string, _reason?: string): Promise<PortResult<ResourceHandle>> {
    const record = this.jobs.get(handleId);
    if (!record) return fail("NOT_FOUND", "作业不存在", { handleId });
    record.released = true;
    const handle: ResourceHandle = {
      ...record.handle,
      state: "cancelled",
      endedAt: this.now(),
      reason: "取消已受理",
    };
    record.handle = handle;
    return ok(handle);
  }

  async reconcile(handleId: string): Promise<PortResult<ReconcileEvidence>> {
    const record = this.jobs.get(handleId);
    if (!record) return ok({ verdict: "unknown", reason: "作业记录缺失" });

    if (this.scenario === "unknown") {
      return ok({ verdict: "unknown", reason: "供应商未返回可判定证据" });
    }
    if (record.handle.state === "succeeded" || record.handle.state === "failed") {
      return ok({ verdict: "executed", handle: record.handle });
    }
    if (record.handle.state === "cancelled") {
      return ok({ verdict: "cancelled_before_execution_confirmed", reason: "已被取消" });
    }
    return ok({ verdict: "queued_or_running", handle: record.handle });
  }

  async logs(
    handleId: string,
    options?: { fromSequence?: number; maxBytes?: number },
  ): Promise<PortResult<LogChunk>> {
    const record = this.jobs.get(handleId);
    if (!record) return fail("NOT_FOUND", "作业不存在", { handleId });
    const all = [
      `[stub] job ${handleId}`,
      "[stub] 这是模拟日志，不代表真实执行",
      "[stub] epoch 1/1 loss=0.94",
    ];
    const from = options?.fromSequence ?? 0;
    return ok({
      lines: all.slice(from),
      nextSequence: all.length,
      truncated: false,
    });
  }

  async release(handleId: string): Promise<PortResult<void>> {
    const record = this.jobs.get(handleId);
    if (!record) return fail("NOT_FOUND", "作业不存在", { handleId });
    record.released = true;
    return ok(undefined);
  }

  async reserve(input: {
    tenantId: string;
    projectId?: string;
    startAt: string;
    endAt: string;
    nodes: number;
    gpusPerNode?: number;
    idempotencyKey: string;
  }): Promise<PortResult<HpcReservation>> {
    if (Date.parse(input.endAt) <= Date.parse(input.startAt)) {
      return fail("INVALID_ARGUMENT", "endAt 必须晚于 startAt");
    }
    const reservation: HpcReservation = {
      reservationId: `stub-res-${this.reservations.size + 1}`,
      tenantId: input.tenantId,
      projectId: input.projectId,
      startAt: input.startAt,
      endAt: input.endAt,
      nodes: input.nodes,
      gpusPerNode: input.gpusPerNode,
      state: "confirmed",
      providerReservationId: `stub-provider-res-${this.reservations.size + 1}`,
    };
    this.reservations.set(reservation.reservationId, reservation);
    return ok(reservation);
  }

  async releaseReservation(reservationId: string): Promise<PortResult<void>> {
    const reservation = this.reservations.get(reservationId);
    if (!reservation) return fail("NOT_FOUND", "预留不存在", { reservationId });
    reservation.state = "released";
    return ok(undefined);
  }

  async queueInfo(input: { tenantId: string; partition?: string }): Promise<
    PortResult<{
      pending: number;
      running: number;
      estimatedWaitSeconds?: number;
      confidence?: "low" | "medium" | "high";
    }>
  > {
    const all = [...this.jobs.values()].filter(
      (record) => record.request.tenantId === input.tenantId,
    );
    return ok({
      pending: all.filter((record) => record.handle.state === "queued").length,
      running: all.filter((record) => record.handle.state === "running").length,
      estimatedWaitSeconds: 60,
      confidence: "medium",
    });
  }
}

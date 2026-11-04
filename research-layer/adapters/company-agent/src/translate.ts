/**
 * 研究层 ComputePort 到 company-agent-provider/1.0 的翻译。
 *
 * 这里不连接云、HPC、模型或设备。默认运行仍使用 adapters/stub。
 * 进程内去重只属于这一次适配器实例，不是公司事实源。
 * QPU 只生成设备审批交接，不提交作业。
 */

import type {
  ComputeCapabilities,
  ComputePort,
  LogChunk,
  PortResult,
  Quote,
  ReconcileEvidence,
  ResourceHandle,
  ResourceKind,
  ResourceRequest,
  ResourceState,
} from "../../../contracts/src/index.ts";
import { CONTRACT_VERSION, fail, ok } from "../../../contracts/src/index.ts";

export const COMPANY_PROVIDER_PROTOCOL = "company-agent-provider/1.0";

export const COMPANY_ADAPTER = {
  implementation: "company-agent-translation",
  degraded: true,
  degradedReason: "翻译层只保留信封和审批交接；不提交真实云、HPC 或模型作业",
} as const;

const EXECUTABLE_KINDS = ["cpu", "gpu", "hpc", "cloud", "browser"] as const;
type ExecutableKind = (typeof EXECUTABLE_KINDS)[number];

export interface CompanyEnvelope {
  protocol: typeof COMPANY_PROVIDER_PROTOCOL;
  request_id: string;
  idempotency_key: string;
  tenant_id: string;
  kind: ExecutableKind;
  operation: string;
}

export interface DeviceApprovalHandoff {
  tenant_id: string;
  request_id: string;
  idempotency_key: string;
  mandate: "lab";
  tool: "quantum_device_run";
}

export interface MappedState {
  state: ResourceState;
  queryable: boolean;
  resubmittable: boolean;
}

const KNOWN_STATES: Record<string, ResourceState> = {
  queued: "queued",
  starting: "starting",
  running: "running",
  succeeded: "succeeded",
  failed: "failed",
  cancelled: "cancelled",
};

const SECRET_FIELD = /secret|token|password|credential|api_key/i;

interface RecordedJob {
  envelope: CompanyEnvelope;
  handle: ResourceHandle;
  providerState: string;
  projectId?: string;
  taskId?: string;
}

function secretField(value: string): boolean {
  return SECRET_FIELD.test(value);
}

function rejectSecrets(request: ResourceRequest): PortResult<never> | undefined {
  const fields = [...Object.keys(request.env ?? {}), ...Object.keys(request.labels ?? {})];
  if (fields.find(secretField)) return fail("INVALID_ARGUMENT", "密钥字段不能进入公司信封");
  return undefined;
}

export function mapProviderState(providerState: string | null | undefined): MappedState {
  const normalized = (providerState ?? "").trim().toLowerCase();
  const state = KNOWN_STATES[normalized];
  if (!state || normalized === "timeout" || normalized === "pending" || normalized === "unknown") {
    return { state: "unknown", queryable: true, resubmittable: false };
  }
  return { state, queryable: true, resubmittable: false };
}

function handoffFor(request: ResourceRequest): DeviceApprovalHandoff {
  return {
    tenant_id: request.tenantId,
    request_id: request.requestId,
    idempotency_key: request.idempotencyKey,
    mandate: "lab",
    tool: "quantum_device_run",
  };
}

function handoffDetails(handoff: DeviceApprovalHandoff): Record<string, unknown> {
  return {
    tenant_id: handoff.tenant_id,
    request_id: handoff.request_id,
    idempotency_key: handoff.idempotency_key,
    mandate: handoff.mandate,
    tool: handoff.tool,
  };
}

function sampleRequest(kind: ResourceKind, idempotencyKey: string, requestId: string): ResourceRequest {
  return {
    idempotencyKey,
    requestId,
    tenantId: "tenant-a",
    kind,
    count: 1,
    wallClockSeconds: 60,
  };
}

export class CompanyComputePort implements ComputePort {
  private readonly jobs = new Map<string, RecordedJob>();
  private readonly byKey = new Map<string, string>();
  private readonly handoffs = new Map<string, DeviceApprovalHandoff>();
  private counter = 0;

  get submissionCount(): number {
    return this.jobs.size;
  }

  private cacheKey(tenantId: string, idempotencyKey: string): string {
    return `${tenantId}:${idempotencyKey}`;
  }

  private view(job: RecordedJob): ResourceHandle {
    const mapped = mapProviderState(job.providerState);
    return {
      ...job.handle,
      kind: job.envelope.kind,
      state: mapped.state,
      providerState: job.providerState,
      reason: mapped.state === "unknown" ? "unknown_execution" : job.providerState,
    };
  }

  async describe(): Promise<PortResult<ComputeCapabilities>> {
    return ok({
      contractVersion: CONTRACT_VERSION,
      implementation: COMPANY_ADAPTER.implementation,
      degraded: true,
      degradedReason: COMPANY_ADAPTER.degradedReason,
      features: ["submit", "status", "reconcile"],
      kinds: [...EXECUTABLE_KINDS],
      supportsCheckpoint: false,
      supportsCancel: false,
      supportsReconcile: true,
      supportsReservation: false,
    });
  }

  async quote(_request: ResourceRequest): Promise<PortResult<Quote>> {
    return fail("NOT_SUPPORTED", "报价需要真实调度器，翻译层不估计成本");
  }

  async submit(request: ResourceRequest): Promise<PortResult<ResourceHandle>> {
    const secret = rejectSecrets(request);
    if (secret) return secret;
    if (!request.requestId || !request.tenantId || !request.idempotencyKey) {
      return fail("INVALID_ARGUMENT", "请求缺少公司信封所需的标识");
    }
    if (request.kind === "qpu") {
      const key = this.cacheKey(request.tenantId, request.idempotencyKey);
      const existing = this.handoffs.get(key);
      if (existing) {
        if (existing.request_id !== request.requestId) {
          return fail("CONFLICT", "幂等键已用于另一条设备审批");
        }
        return fail("PERMISSION_DENIED", "QPU 需要设备审批", handoffDetails(existing));
      }
      const handoff = handoffFor(request);
      this.handoffs.set(key, handoff);
      return fail("PERMISSION_DENIED", "QPU 需要设备审批", handoffDetails(handoff));
    }
    if (!EXECUTABLE_KINDS.includes(request.kind as ExecutableKind)) {
      return fail("NOT_SUPPORTED", "翻译层不接受该资源种类");
    }
    const key = this.cacheKey(request.tenantId, request.idempotencyKey);
    const existingId = this.byKey.get(key);
    if (existingId) {
      const existing = this.jobs.get(existingId);
      if (!existing) return fail("NOT_FOUND", "未知作业");
      return ok(this.view(existing));
    }
    const kind = request.kind as ExecutableKind;
    this.counter += 1;
    const handle: ResourceHandle = {
      handleId: `company-job-${this.counter}`,
      kind,
      state: "unknown",
      submittedAt: new Date().toISOString(),
      reason: "unknown_execution",
    };
    const job: RecordedJob = {
      envelope: {
        protocol: COMPANY_PROVIDER_PROTOCOL,
        request_id: request.requestId,
        idempotency_key: request.idempotencyKey,
        tenant_id: request.tenantId,
        kind,
        operation: `${kind}.submit`,
      },
      handle,
      providerState: "unknown",
      projectId: request.projectId,
      taskId: request.taskId,
    };
    this.jobs.set(handle.handleId, job);
    this.byKey.set(key, handle.handleId);
    return ok(this.view(job));
  }

  noteProviderState(handleId: string, providerState: string): PortResult<ResourceHandle> {
    const job = this.jobs.get(handleId);
    if (!job) return fail("NOT_FOUND", "未知作业");
    job.providerState = providerState;
    job.handle = this.view(job);
    return ok(job.handle);
  }

  envelopeFor(handleId: string): PortResult<CompanyEnvelope> {
    const job = this.jobs.get(handleId);
    if (!job) return fail("NOT_FOUND", "未知作业");
    return ok(job.envelope);
  }

  async status(handleId: string): Promise<PortResult<ResourceHandle>> {
    const job = this.jobs.get(handleId);
    if (!job) return fail("NOT_FOUND", "未知作业");
    return ok(this.view(job));
  }

  async list(filter: {
    tenantId: string;
    projectId?: string;
    taskId?: string;
    state?: ResourceState;
  }): Promise<PortResult<ResourceHandle[]>> {
    const items = [...this.jobs.values()]
      .filter((job) => job.envelope.tenant_id === filter.tenantId)
      .filter((job) => !filter.projectId || job.projectId === filter.projectId)
      .filter((job) => !filter.taskId || job.taskId === filter.taskId)
      .filter((job) => !filter.state || mapProviderState(job.providerState).state === filter.state)
      .map((job) => this.view(job));
    return ok(items);
  }

  async cancel(_handleId: string, _reason?: string): Promise<PortResult<ResourceHandle>> {
    return fail("NOT_SUPPORTED", "取消需要真实调度器");
  }

  async reconcile(handleId: string): Promise<PortResult<ReconcileEvidence>> {
    const job = this.jobs.get(handleId);
    if (!job) return fail("NOT_FOUND", "未知作业");
    const mapped = mapProviderState(job.providerState);
    const handle = this.view(job);
    if (mapped.state === "unknown") {
      return ok({ verdict: "unknown", reason: "unknown_execution" });
    }
    if (mapped.state === "queued" || mapped.state === "starting" || mapped.state === "running") {
      return ok({ verdict: "queued_or_running", handle });
    }
    if (mapped.state === "cancelled") {
      return ok({ verdict: "cancelled_before_execution_confirmed", reason: "cancelled" });
    }
    return ok({ verdict: "executed", handle });
  }

  async logs(
    _handleId: string,
    _options?: { fromSequence?: number; maxBytes?: number },
  ): Promise<PortResult<LogChunk>> {
    return fail("NOT_SUPPORTED", "日志需要真实作业，翻译层不返回日志正文");
  }

  async release(_handleId: string): Promise<PortResult<void>> {
    return fail("NOT_SUPPORTED", "释放需要真实调度器");
  }
}

export async function assessConformance(port: CompanyComputePort): Promise<{
  passed: string[];
  blocked: string[];
}> {
  const passed: string[] = [];
  const blocked: string[] = [];
  const described = await port.describe();
  if (!described.ok || described.value.degraded !== true) {
    throw new Error("company adapter must stay degraded");
  }

  const hpc = sampleRequest("hpc", "hp-02", "hp-02");
  const first = await port.submit(hpc);
  const second = await port.submit(hpc);
  if (
    first.ok &&
    second.ok &&
    first.value.handleId === second.value.handleId &&
    port.submissionCount === 1
  ) {
    passed.push("HP-02");
  }

  if (first.ok) {
    const status = await port.status(first.value.handleId);
    const reconciled = await port.reconcile(first.value.handleId);
    const access = mapProviderState("unknown");
    if (
      status.ok &&
      status.value.state === "unknown" &&
      status.value.reason === "unknown_execution" &&
      reconciled.ok &&
      reconciled.value.verdict === "unknown" &&
      access.queryable &&
      !access.resubmittable &&
      port.submissionCount === 1
    ) {
      passed.push("HP-05");
    }
  }

  const beforeCloud = port.submissionCount;
  const cloud = sampleRequest("cloud", "cl-01", "cl-01");
  const submitted = await port.submit(cloud);
  if (submitted.ok) {
    const noted = port.noteProviderState(submitted.value.handleId, "timeout");
    const reconciled = await port.reconcile(submitted.value.handleId);
    const again = await port.submit(cloud);
    if (
      noted.ok &&
      noted.value.state === "unknown" &&
      reconciled.ok &&
      reconciled.value.verdict === "unknown" &&
      reconciled.value.reason === "unknown_execution" &&
      again.ok &&
      again.value.handleId === submitted.value.handleId &&
      port.submissionCount === beforeCloud + 1
    ) {
      passed.push("CL-01");
    }
  }

  const quote = await port.quote(hpc);
  if (quote.ok) passed.push("HP-03");
  else blocked.push("HP-03");

  const logs = await port.logs("company-job-1");
  if (logs.ok) passed.push("HP-06");
  else blocked.push("HP-06");

  blocked.push("HP-01");
  blocked.push("MD-01");
  return { passed, blocked };
}
